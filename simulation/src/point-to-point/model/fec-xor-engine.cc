/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#include "fec-xor-engine.h"
#include "ns3/log.h"
#include "ns3/packet.h"
#include <algorithm>
#include <cstring>

NS_LOG_COMPONENT_DEFINE("FecXorEngine");

namespace ns3 {

Ptr<Packet>
FecXorEngine::XorPackets(const std::vector<Ptr<Packet>>& packets)
{
  NS_LOG_FUNCTION_NOARGS();

  if (packets.empty())
    {
      NS_LOG_WARN("XorPackets called with empty packet vector");
      return Create<Packet>(0);
    }

  // Find maximum packet size
  uint32_t maxSize = GetMaxPacketSize(packets);

  NS_LOG_DEBUG("XORing " << packets.size() << " packets, max size: " << maxSize);

  // Create result buffer initialized to zero
  uint8_t* resultBuffer = new uint8_t[maxSize];
  std::memset(resultBuffer, 0, maxSize);

  // XOR all packets into result buffer
  for (std::vector<Ptr<Packet>>::const_iterator it = packets.begin();
       it != packets.end(); ++it)
    {
      if (*it == 0)
        {
          // Skip null packets
          continue;
        }

      uint32_t packetSize = (*it)->GetSize();

      // Copy packet data to temporary buffer
      uint8_t* packetBuffer = new uint8_t[packetSize];
      (*it)->CopyData(packetBuffer, packetSize);

      // XOR with result buffer
      XorBuffers(resultBuffer, packetBuffer, packetSize);

      delete[] packetBuffer;
    }

  // Create repair packet from result buffer
  Ptr<Packet> repairPacket = Create<Packet>(resultBuffer, maxSize);

  delete[] resultBuffer;

  NS_LOG_DEBUG("Generated repair packet of size: " << repairPacket->GetSize());

  return repairPacket;
}

Ptr<Packet>
FecXorEngine::RecoverPacket(const std::vector<Ptr<Packet>>& receivedPackets,
                             Ptr<Packet> repairPacket,
                             uint32_t missingIndex)
{
  NS_LOG_FUNCTION(missingIndex);

  if (repairPacket == 0)
    {
      NS_LOG_ERROR("RecoverPacket called with null repair packet");
      return 0;
    }

  uint32_t repairSize = repairPacket->GetSize();

  // Create result buffer from repair packet
  uint8_t* resultBuffer = new uint8_t[repairSize];
  repairPacket->CopyData(resultBuffer, repairSize);

  // XOR all received packets (except the missing one) with repair packet
  for (size_t i = 0; i < receivedPackets.size(); ++i)
    {
      if (i == missingIndex)
        {
          // Skip the missing packet
          continue;
        }

      if (receivedPackets[i] == 0)
        {
          NS_LOG_WARN("RecoverPacket: packet at index " << i << " is null (not expected)");
          continue;
        }

      uint32_t packetSize = receivedPackets[i]->GetSize();

      // Copy packet data to temporary buffer
      uint8_t* packetBuffer = new uint8_t[packetSize];
      receivedPackets[i]->CopyData(packetBuffer, packetSize);

      // XOR with result buffer
      XorBuffers(resultBuffer, packetBuffer, std::min(packetSize, repairSize));

      delete[] packetBuffer;
    }

  // Create recovered packet from result buffer
  Ptr<Packet> recoveredPacket = Create<Packet>(resultBuffer, repairSize);

  delete[] resultBuffer;

  NS_LOG_DEBUG("Recovered packet of size: " << recoveredPacket->GetSize());

  return recoveredPacket;
}

uint32_t
FecXorEngine::GetMaxPacketSize(const std::vector<Ptr<Packet>>& packets)
{
  uint32_t maxSize = 0;

  for (std::vector<Ptr<Packet>>::const_iterator it = packets.begin();
       it != packets.end(); ++it)
    {
      if (*it != 0)
        {
          uint32_t size = (*it)->GetSize();
          if (size > maxSize)
            {
              maxSize = size;
            }
        }
    }

  return maxSize;
}

Ptr<Packet>
FecXorEngine::PadPacket(Ptr<Packet> packet, uint32_t targetSize)
{
  if (packet == 0)
    {
      NS_LOG_WARN("PadPacket called with null packet");
      return Create<Packet>(targetSize);
    }

  uint32_t currentSize = packet->GetSize();

  if (currentSize >= targetSize)
    {
      // No padding needed, return a copy
      return packet->Copy();
    }

  // Create padded packet
  uint32_t paddingSize = targetSize - currentSize;

  // Copy original data
  uint8_t* buffer = new uint8_t[currentSize];
  packet->CopyData(buffer, currentSize);

  // Create packet with original data
  Ptr<Packet> paddedPacket = Create<Packet>(buffer, currentSize);

  delete[] buffer;

  // Add padding (zeros)
  uint8_t* paddingBuffer = new uint8_t[paddingSize];
  std::memset(paddingBuffer, 0, paddingSize);

  Ptr<Packet> padding = Create<Packet>(paddingBuffer, paddingSize);
  paddedPacket->AddAtEnd(padding);

  delete[] paddingBuffer;

  NS_LOG_DEBUG("Padded packet from " << currentSize << " to " << targetSize << " bytes");

  return paddedPacket;
}

void
FecXorEngine::XorBuffers(uint8_t* dst, const uint8_t* src, size_t len)
{
  // Byte-wise XOR operation
  for (size_t i = 0; i < len; ++i)
    {
      dst[i] ^= src[i];
    }
}

} // namespace ns3
