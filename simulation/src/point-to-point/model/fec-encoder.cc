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
    m_currentBlockBase(0),
    m_packetsInBlock(0),
    m_hasFirst(false),
    m_hasLast(false),
    m_lastRel(0),
    m_lastLength(0)
{
  NS_LOG_FUNCTION_NOARGS();

  // 初始化 coding units
  m_units.resize(m_interleavingDepth);
}

FecEncoder::FecEncoder(uint32_t blockSize, uint32_t interleavingDepth)
  : m_blockSize(blockSize),
    m_interleavingDepth(interleavingDepth),
    m_currentBlockBase(0),
    m_packetsInBlock(0),
    m_hasFirst(false),
    m_hasLast(false),
    m_lastRel(0),
    m_lastLength(0)
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

  // 初始化 coding units
  m_units.resize(m_interleavingDepth);
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
      // 在本实现里每条消息的 PSN 从 0 开始，因此 bPSN==0 的块包含消息首包
      m_hasFirst = (psn == 0);
      m_hasLast = false;
      m_lastRel = 0;
      m_lastLength = 0;
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

  // 仅选择一个 coding unit 进行 XOR 更新
  uint32_t unitIdx = (m_interleavingDepth == 0) ? 0 : (relativePsn % m_interleavingDepth);
  if (unitIdx < m_units.size())
    {
      AddPacketToCodingUnit(m_units[unitIdx], dataPacket, psn);
      NS_LOG_DEBUG("Added packet PSN=" << psn << " to unit=" << unitIdx);
    }
  else
    {
      NS_LOG_ERROR("Unit index " << unitIdx << " out of range");
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
FecEncoder::GenerateRepairPackets(bool allowIncomplete)
{
  NS_LOG_FUNCTION(allowIncomplete);

  std::vector<Ptr<Packet>> repairPackets;

  if (!allowIncomplete && !IsBlockComplete())
    {
      NS_LOG_WARN("GenerateRepairPackets called on incomplete block ("
                  << m_packetsInBlock << "/" << m_blockSize << ")");
      return repairPackets;
    }
  if (allowIncomplete && m_packetsInBlock == 0)
    {
      return repairPackets;
    }

  NS_LOG_DEBUG("Generating repair packets for block bPSN=" << m_currentBlockBase);

  // 每个 coding unit 最多生成一个 repair 包
  for (uint32_t isn = 0; isn < m_units.size(); ++isn)
    {
      CodingUnit& unit = m_units[isn];

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
      fecHdr.SetISN(isn);
      fecHdr.SetHasFirst(m_hasFirst);
      fecHdr.SetHasLast(m_hasLast);
      fecHdr.SetLastRel(m_lastRel);
      fecHdr.SetLastLength(m_lastLength);
      fecHdr.SetRecipe(unit.recipe);

      repairPacket->AddHeader(fecHdr);

      repairPackets.push_back(repairPacket);

      NS_LOG_DEBUG("Generated repair packet ISN=" << isn
                                                   << " recipe_size=" << unit.recipe.size());
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
  m_hasFirst = false;
  m_hasLast = false;
  m_lastRel = 0;
  m_lastLength = 0;

  // Clear block packets
  m_blockPackets.clear();

  // Clear all coding units
  for (uint32_t unitIdx = 0; unitIdx < m_units.size(); ++unitIdx)
    {
      CodingUnit& unit = m_units[unitIdx];
      unit.xorBuffer.clear();
      unit.recipe.clear();
      unit.maxPacketSize = 0;
    }

  NS_LOG_DEBUG("Reset complete, new bPSN=" << m_currentBlockBase);
}

void
FecEncoder::MarkHasLast(uint16_t lastRel, uint16_t lastLength)
{
  m_hasLast = true;
  m_lastRel = lastRel;
  m_lastLength = lastLength;
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


} // namespace ns3
