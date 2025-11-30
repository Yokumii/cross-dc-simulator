/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#include "fec-encoder.h"
#include "fec-header.h"
#include "fec-xor-engine.h"
#include "ns3/log.h"
#include "ns3/object.h"
#include <cmath>
#include <cstring>
#include <algorithm>

NS_LOG_COMPONENT_DEFINE("FecEncoder");

namespace ns3 {

NS_OBJECT_ENSURE_REGISTERED(FecEncoder);

TypeId
FecEncoder::GetTypeId(void)
{
  static TypeId tid = TypeId("ns3::FecEncoder")
    .SetParent<Object>()
    .SetGroupName("PointToPoint")
    .AddConstructor<FecEncoder>()
  ;
  return tid;
}

FecEncoder::FecEncoder()
  : m_blockSize(64),
    m_interleavingDepth(8),
    m_interleavingIndex(2),
    m_currentBlockBase(0),
    m_packetsInBlock(0)
{
  NS_LOG_FUNCTION_NOARGS();

  // Initialize coding layers
  m_codingLayers.resize(m_interleavingDepth);

  for (uint32_t layer = 0; layer < m_interleavingDepth; ++layer)
    {
      uint32_t bucketsInLayer = GetBucketsPerLayer(layer);
      m_codingLayers[layer].resize(bucketsInLayer);

      NS_LOG_DEBUG("Layer " << layer << " has " << bucketsInLayer << " buckets");
    }
}

FecEncoder::FecEncoder(uint32_t blockSize, uint32_t interleavingDepth)
  : m_blockSize(blockSize),
    m_interleavingDepth(interleavingDepth),
    m_interleavingIndex(2),  // Standard LoWAR uses i=2
    m_currentBlockBase(0),
    m_packetsInBlock(0)
{
  NS_LOG_FUNCTION(blockSize << interleavingDepth);

  // 边界检查：确保 blockSize 不超过上限
  if (blockSize > MAX_BLOCK_SIZE)
    {
      std::cerr << "[FEC-ENCODER-INIT] WARNING: Block size " << blockSize
                << " exceeds maximum " << MAX_BLOCK_SIZE
                << ", truncating to " << MAX_BLOCK_SIZE << std::endl;
      m_blockSize = MAX_BLOCK_SIZE;
    }

  // Initialize coding layers
  m_codingLayers.resize(m_interleavingDepth);

  for (uint32_t layer = 0; layer < m_interleavingDepth; ++layer)
    {
      uint32_t bucketsInLayer = GetBucketsPerLayer(layer);
      m_codingLayers[layer].resize(bucketsInLayer);

      NS_LOG_DEBUG("Layer " << layer << " has " << bucketsInLayer << " buckets");
    }
}

FecEncoder::~FecEncoder()
{
  NS_LOG_FUNCTION_NOARGS();
}

void
FecEncoder::EncodePacket(Ptr<Packet> dataPacket, uint32_t psn)
{
  NS_LOG_FUNCTION(psn);

  if (dataPacket == 0)
    {
      NS_LOG_WARN("EncodePacket called with null packet");
      return;
    }

  // If this is the first packet of a new block, set base PSN
  if (m_packetsInBlock == 0)
    {
      m_currentBlockBase = psn;
      NS_LOG_DEBUG("Starting new coding block at bPSN=" << m_currentBlockBase);
    }

  // Verify PSN is within current block
  uint32_t relativePsn = psn - m_currentBlockBase;
  if (relativePsn >= m_blockSize)
    {
      NS_LOG_ERROR("PSN " << psn << " exceeds block boundary (base=" << m_currentBlockBase
                          << ", size=" << m_blockSize << ")");
      return;
    }

  // Store packet for later repair generation
  m_blockPackets[psn] = dataPacket->Copy();

  // Add packet to all interleaving layers
  for (uint32_t layer = 0; layer < m_interleavingDepth; ++layer)
    {
      uint32_t bucketIdx = GetBucketIndex(relativePsn, layer);

      if (bucketIdx < m_codingLayers[layer].size())
        {
          AddPacketToCodingUnit(m_codingLayers[layer][bucketIdx], dataPacket, psn);

          NS_LOG_DEBUG("Added packet PSN=" << psn << " to layer=" << layer
                                            << " bucket=" << bucketIdx);
        }
      else
        {
          NS_LOG_ERROR("Bucket index " << bucketIdx << " out of range for layer " << layer);
        }
    }

  m_packetsInBlock++;

  NS_LOG_DEBUG("Encoded packet " << m_packetsInBlock << "/" << m_blockSize);
}

bool
FecEncoder::IsBlockComplete() const
{
  return m_packetsInBlock >= m_blockSize;
}

std::vector<Ptr<Packet>>
FecEncoder::GenerateRepairPackets()
{
  NS_LOG_FUNCTION_NOARGS();

  std::vector<Ptr<Packet>> repairPackets;

  if (!IsBlockComplete())
    {
      NS_LOG_WARN("GenerateRepairPackets called on incomplete block ("
                  << m_packetsInBlock << "/" << m_blockSize << ")");
      return repairPackets;
    }

  NS_LOG_DEBUG("Generating repair packets for block bPSN=" << m_currentBlockBase);

  uint32_t isn = 0; // Interleaving sequence number for repair packets

  // Generate one repair packet from each coding unit across all layers
  for (uint32_t layer = 0; layer < m_interleavingDepth; ++layer)
    {
      for (uint32_t bucket = 0; bucket < m_codingLayers[layer].size(); ++bucket)
        {
          CodingUnit& unit = m_codingLayers[layer][bucket];

          // Skip empty coding units
          if (unit.recipe.empty())
            {
              continue;
            }

          // Create repair packet from XOR buffer
          Ptr<Packet> repairPacket = Create<Packet>(unit.xorBuffer.data(),
                                                     unit.maxPacketSize);

          // Add FEC header
          FecHeader fecHdr;
          fecHdr.SetType(FecHeader::FEC_REPAIR);
          fecHdr.SetBlockSize(m_blockSize);
          fecHdr.SetInterleavingDepth(m_interleavingDepth);
          fecHdr.SetBasePSN(m_currentBlockBase);
          fecHdr.SetISN(isn++);
          fecHdr.SetRecipe(unit.recipe);

          repairPacket->AddHeader(fecHdr);

          repairPackets.push_back(repairPacket);

          NS_LOG_DEBUG("Generated repair packet ISN=" << (isn - 1)
                                                       << " from layer=" << layer
                                                       << " bucket=" << bucket
                                                       << " recipe_size=" << unit.recipe.size());
        }
    }

  NS_LOG_INFO("Generated " << repairPackets.size() << " repair packets for block bPSN="
                           << m_currentBlockBase);

  return repairPackets;
}

void
FecEncoder::ResetBlock()
{
  NS_LOG_FUNCTION_NOARGS();

  NS_LOG_DEBUG("Resetting encoder, old bPSN=" << m_currentBlockBase);

  // Advance to next block
  m_currentBlockBase += m_blockSize;
  m_packetsInBlock = 0;

  // Clear block packets
  m_blockPackets.clear();

  // Clear all coding units
  for (uint32_t layer = 0; layer < m_interleavingDepth; ++layer)
    {
      for (uint32_t bucket = 0; bucket < m_codingLayers[layer].size(); ++bucket)
        {
          CodingUnit& unit = m_codingLayers[layer][bucket];
          unit.xorBuffer.clear();
          unit.recipe.clear();
          unit.maxPacketSize = 0;
        }
    }

  NS_LOG_DEBUG("Reset complete, new bPSN=" << m_currentBlockBase);
}

uint32_t
FecEncoder::GetCurrentBlockBase() const
{
  return m_currentBlockBase;
}

uint32_t
FecEncoder::GetPacketsInBlock() const
{
  return m_packetsInBlock;
}

void
FecEncoder::AddPacketToCodingUnit(CodingUnit& unit, Ptr<Packet> packet, uint32_t psn)
{
  uint32_t packetSize = packet->GetSize();

  // Update maximum packet size for this unit
  if (packetSize > unit.maxPacketSize)
    {
      unit.maxPacketSize = packetSize;

      // Resize XOR buffer if needed
      if (unit.xorBuffer.size() < packetSize)
        {
          unit.xorBuffer.resize(packetSize, 0);
        }
    }

  // Copy packet data to temporary buffer
  uint8_t* packetBuffer = new uint8_t[packetSize];
  packet->CopyData(packetBuffer, packetSize);

  // XOR packet into coding unit buffer
  for (uint32_t i = 0; i < packetSize; ++i)
    {
      // Ensure buffer is large enough
      if (i >= unit.xorBuffer.size())
        {
          unit.xorBuffer.push_back(packetBuffer[i]);
        }
      else
        {
          unit.xorBuffer[i] ^= packetBuffer[i];
        }
    }

  delete[] packetBuffer;

  // Add PSN to recipe
  unit.recipe.push_back(psn);
}

uint32_t
FecEncoder::GetBucketIndex(uint32_t psn, uint32_t layer) const
{
  // LoWAR interleaving formula: bucket = (psn / i^layer) % bucketsPerLayer
  // where i is the interleaving index (typically 2)

  uint32_t divisor = static_cast<uint32_t>(std::pow(m_interleavingIndex, layer));
  uint32_t bucketsInLayer = GetBucketsPerLayer(layer);

  uint32_t bucketIdx = (psn / divisor) % bucketsInLayer;

  return bucketIdx;
}

uint32_t
FecEncoder::GetBucketsPerLayer(uint32_t layer) const
{
  // Number of buckets = ceil(r / i^layer)
  uint32_t divisor = static_cast<uint32_t>(std::pow(m_interleavingIndex, layer));

  uint32_t buckets = (m_blockSize + divisor - 1) / divisor;

  return buckets;
}

} // namespace ns3
