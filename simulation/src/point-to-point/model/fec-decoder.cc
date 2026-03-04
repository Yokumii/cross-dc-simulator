/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#include "fec-decoder.h"
#include "fec-xor-engine.h"
#include "ns3/log.h"
#include "ns3/object.h"
#include <algorithm>

NS_LOG_COMPONENT_DEFINE("FecDecoder");

namespace ns3 {

NS_OBJECT_ENSURE_REGISTERED(FecDecoder);

TypeId
FecDecoder::GetTypeId(void)
{
  static TypeId tid = TypeId("ns3::FecDecoder")
    .SetParent<Object>()
    .SetGroupName("PointToPoint")
    .AddConstructor<FecDecoder>()
  ;
  return tid;
}

FecDecoder::FecDecoder()
  : m_blockSize(64),
    m_interleavingDepth(8),
    m_recoveredCount(0),
    m_unrecoverableCount(0)
{
  NS_LOG_FUNCTION_NOARGS();
}

FecDecoder::FecDecoder(uint32_t blockSize, uint32_t interleavingDepth)
  : m_blockSize(blockSize),
    m_interleavingDepth(interleavingDepth),
    m_recoveredCount(0),
    m_unrecoverableCount(0)
{
  NS_LOG_FUNCTION(blockSize << interleavingDepth);

  if (blockSize > MAX_BLOCK_SIZE)
    {
      std::cerr << "[FEC-DECODER-INIT] WARNING: Block size " << blockSize
                << " exceeds maximum " << MAX_BLOCK_SIZE
                << ", truncating to " << MAX_BLOCK_SIZE << std::endl;
      m_blockSize = MAX_BLOCK_SIZE;
    }

}

FecDecoder::~FecDecoder()
{
  NS_LOG_FUNCTION_NOARGS();
}

void
FecDecoder::ReceiveDataPacket(Ptr<Packet> packet, uint32_t psn)
{
  NS_LOG_FUNCTION(psn);

  if (packet == 0)
    {
      NS_LOG_WARN("ReceiveDataPacket called with null packet");
      return;
    }

  if (psn < m_dropBeforePsn)
    {
      return;
    }

  // Calculate block base PSN
  uint32_t basePSN = (psn / m_blockSize) * m_blockSize;
  uint32_t relativePsn = psn - basePSN;

  // 边界检查：防止数组越界
  if (relativePsn >= MAX_BLOCK_SIZE)
    {
      std::cerr << "[FEC-DECODER-ERROR] relativePsn " << relativePsn
                << " exceeds MAX_BLOCK_SIZE " << MAX_BLOCK_SIZE
                << " (PSN=" << psn << ", basePSN=" << basePSN
                << ", blockSize=" << m_blockSize << ")" << std::endl;
      return;
    }

  // Update block state
  BlockState& state = GetOrCreateBlockState(basePSN);

  if (!state.receivedBits[relativePsn])
    {
      state.receivedBits[relativePsn] = true;
      state.receivedCount++;

      // Update unit XOR (LoWAR: only keep lightweight XOR state per unit, not every packet)
      uint32_t unitIdx =
          (m_interleavingDepth == 0) ? 0 : (relativePsn % m_interleavingDepth);
      if (unitIdx < state.unitXor.size())
        {
          auto& unit = state.unitXor[unitIdx];
          uint32_t packetSize = packet->GetSize();
          if (packetSize > unit.maxLen)
            {
              unit.maxLen = packetSize;
              if (unit.xorBuf.size() < packetSize)
                {
                  unit.xorBuf.resize(packetSize, 0);
                }
            }
          if (packetSize > 0)
            {
              std::vector<uint8_t> buf(packetSize);
              packet->CopyData(buf.data(), packetSize);
              for (uint32_t i = 0; i < packetSize; ++i)
                {
                  unit.xorBuf[i] ^= buf[i];
                }
            }
        }

      NS_LOG_DEBUG("Received data packet PSN=" << psn << " (block " << basePSN
                                                << ", " << state.receivedCount << "/"
                                                << m_blockSize << ")");
    }

  // 块已完整：旧块的数据/repair 不再需要，立即清理以避免缓存所有数据包导致内存线性增长。
  if (state.receivedCount >= m_blockSize)
    {
      CleanupOldBlocks(basePSN + m_blockSize);
    }
}

void
FecDecoder::ReceiveRepairPacket(Ptr<Packet> repairPacket,
                                uint32_t basePSN,
                                uint16_t isn,
                                const std::vector<uint32_t>& recipe,
                                bool hasFirst,
                                bool hasLast,
                                uint16_t lastRel,
                                uint16_t lastLength)
{
  NS_LOG_FUNCTION(basePSN << isn << recipe.size() << hasLast << lastRel << lastLength);

  if (repairPacket == 0)
    {
      NS_LOG_WARN("ReceiveRepairPacket called with null packet");
      return;
    }

  if (basePSN < m_dropBeforePsn)
    {
      return;
    }

  if (recipe.empty())
    {
      // Empty recipe carries no redundancy information.
      return;
    }

  // 验证 recipe 中的 PSN 是否合理
  for (size_t i = 0; i < recipe.size(); ++i)
    {
      uint32_t psn = recipe[i];
      uint32_t expectedBasePSN = (psn / m_blockSize) * m_blockSize;

      if (expectedBasePSN != basePSN)
        {
          std::cerr << "[FEC-DECODER-ERROR-REPAIR] Recipe PSN " << psn
                    << " has basePSN=" << expectedBasePSN
                    << " but repair packet claims basePSN=" << basePSN
                    << " (blockSize=" << m_blockSize << ")" << std::endl;
        }

      uint32_t relativePsn = psn - basePSN;
      if (relativePsn >= MAX_BLOCK_SIZE)
        {
          std::cerr << "[FEC-DECODER-ERROR-REPAIR] Recipe PSN " << psn
                    << " results in relativePsn=" << relativePsn
                    << " which exceeds MAX_BLOCK_SIZE=" << MAX_BLOCK_SIZE
                    << " (basePSN=" << basePSN << ")" << std::endl;
        }
    }

  // 如果 repair 的 recipe 当前已无缺失（missingCount==0），该 repair 永远不可能用于恢复，直接丢弃以节省内存。
  // （后续不会“新增丢包”，missingCount 只会随数据到达/恢复而减少）
  uint32_t dummyMissing = 0;
  uint32_t missingCount = CountMissingInRecipe(recipe, dummyMissing);
  if (missingCount == 0)
    {
      return;
    }

  // Store repair packet info
  RepairPacketInfo info;
  info.payloadLen = repairPacket->GetSize();
  info.payload.resize(info.payloadLen);
  if (info.payloadLen > 0)
    {
      repairPacket->CopyData(info.payload.data(), info.payloadLen);
    }
  info.basePSN = basePSN;
  info.isn = isn;
  info.recipe = recipe;
  info.hasFirst = hasFirst;
  info.hasLast = hasLast;
  info.lastRel = lastRel;
  info.lastLength = lastLength;
  info.used = false;

  m_repairBuffer.push_back(info);

  NS_LOG_DEBUG("Stored repair packet ISN=" << isn << " for block " << basePSN
                                            << " with recipe size " << recipe.size());

  // Note: Caller should call RecoverLostPackets() to attempt recovery
}

std::vector<Ptr<Packet>>
FecDecoder::RecoverLostPackets()
{
  NS_LOG_FUNCTION_NOARGS();

  std::vector<Ptr<Packet>> recovered;

  NS_LOG_DEBUG("FEC decoder attempting recovery: repairBuffer=" << m_repairBuffer.size()
               << " packets, blockStates=" << m_blockStates.size());

  // Try to recover using each repair packet
  for (auto it = m_repairBuffer.begin(); it != m_repairBuffer.end(); ++it)
    {
      if (it->used)
        {
          NS_LOG_DEBUG("Skipping already-used repair ISN=" << it->isn);
          continue; // Already used this repair
        }

      NS_LOG_DEBUG("Attempting recovery with repair ISN=" << it->isn);
      Ptr<Packet> recoveredPacket = AttemptRecoveryWithRepair(*it);

      if (recoveredPacket != 0)
        {
          recovered.push_back(recoveredPacket);
          it->used = true; // Mark as used
          m_recoveredCount++;

          NS_LOG_INFO("Successfully recovered packet using repair ISN=" << it->isn);

          // 回收已使用/冗余的 repair，避免 m_repairBuffer 长期增长导致内存膨胀。
          m_repairBuffer.erase(
            std::remove_if(m_repairBuffer.begin(), m_repairBuffer.end(),
                           [](const RepairPacketInfo& info) { return info.used; }),
            m_repairBuffer.end());

          // Recovery may enable more recoveries, so restart loop
          return recovered; // Return immediately to allow caller to process
        }
    }

  if (recovered.empty())
    {
      NS_LOG_DEBUG("No packets recovered in this attempt (checked " << m_repairBuffer.size() << " repairs)");
    }

  // 无恢复进展时，也回收“已经无意义”的 repair（missingCount==0 会在 AttemptRecoveryWithRepair 标记 used）。
  if (!m_repairBuffer.empty())
    {
      m_repairBuffer.erase(
        std::remove_if(m_repairBuffer.begin(), m_repairBuffer.end(),
                       [](const RepairPacketInfo& info) { return info.used; }),
        m_repairBuffer.end());
    }

  return recovered;
}

bool
FecDecoder::IsBlockComplete(uint32_t basePSN) const
{
  auto it = m_blockStates.find(basePSN);

  if (it == m_blockStates.end())
    {
      return false;
    }

  return it->second.receivedCount >= m_blockSize;
}

bool
FecDecoder::HasPacket(uint32_t psn) const
{
  uint32_t basePSN = (psn / m_blockSize) * m_blockSize;
  uint32_t relativePsn = psn - basePSN;
  if (relativePsn >= MAX_BLOCK_SIZE)
    {
      return false;
    }
  auto it = m_blockStates.find(basePSN);
  if (it == m_blockStates.end())
    {
      return false;
    }
  return it->second.receivedBits[relativePsn];
}

void
FecDecoder::CleanupOldBlocks(uint32_t threshold)
{
  NS_LOG_FUNCTION(threshold);

  if (threshold > m_dropBeforePsn)
    {
      m_dropBeforePsn = threshold;
    }

  // Remove block states before threshold
  for (auto it = m_blockStates.begin(); it != m_blockStates.end(); )
    {
      if (it->first < threshold)
        {
          it = m_blockStates.erase(it);
        }
      else
        {
          ++it;
        }
    }

  // Remove repair packets for old blocks
  m_repairBuffer.erase(
    std::remove_if(m_repairBuffer.begin(), m_repairBuffer.end(),
                   [threshold](const RepairPacketInfo& info) {
                     return info.basePSN < threshold;
                   }),
    m_repairBuffer.end());

  NS_LOG_DEBUG("Cleaned up blocks before PSN " << threshold);
}

uint32_t
FecDecoder::GetRecoveredCount() const
{
  return m_recoveredCount;
}

uint32_t
FecDecoder::GetUnrecoverableCount() const
{
  return m_unrecoverableCount;
}

bool
FecDecoder::IsIdle() const
{
  return m_blockStates.empty() && m_repairBuffer.empty();
}

Ptr<Packet>
FecDecoder::AttemptRecoveryWithRepair(RepairPacketInfo& repairInfo)
{
  NS_LOG_FUNCTION(repairInfo.isn);

  // Check how many packets are missing from recipe
  uint32_t missingPsn = 0;
  uint32_t missingCount = CountMissingInRecipe(repairInfo.recipe, missingPsn);

  // Log recipe analysis
  std::stringstream recipeStr;
  recipeStr << "[";
  for (size_t i = 0; i < repairInfo.recipe.size(); i++) {
      if (i > 0) recipeStr << ",";
      recipeStr << repairInfo.recipe[i];
  }
  recipeStr << "]";
  
  NS_LOG_DEBUG("Analyzing repair ISN=" << repairInfo.isn << " recipe=" << recipeStr.str() 
               << " missingCount=" << missingCount);

  if (missingCount == 0)
    {
      NS_LOG_DEBUG("Repair ISN=" << repairInfo.isn << " - all packets already received, no recovery needed");
      // 该 repair 再也不会用于恢复，标记为 used 以便回收。
      repairInfo.used = true;
      return 0;
    }

  if (missingCount > 1)
    {
      NS_LOG_DEBUG("Repair ISN=" << repairInfo.isn << " - " << missingCount
                                  << " packets missing (need exactly 1 for XOR recovery)");
      return 0;
    }

  // Exactly one packet missing - we can recover it!
  NS_LOG_INFO("FEC decoder attempting recovery of PSN=" << missingPsn << " using repair ISN="
                                              << repairInfo.isn);

  BlockState& state = GetOrCreateBlockState(repairInfo.basePSN);

  uint32_t basePSN = repairInfo.basePSN;
  uint32_t relativePsn = missingPsn - basePSN;
  uint32_t unitIdx = repairInfo.isn;
  if (m_interleavingDepth == 0)
    {
      unitIdx = 0;
    }
  else if (unitIdx >= state.unitXor.size())
    {
      unitIdx = relativePsn % m_interleavingDepth;
    }
  if (unitIdx >= state.unitXor.size())
    {
      return 0;
    }

  auto& unit = state.unitXor[unitIdx];
  uint32_t recLen = std::max<uint32_t>(repairInfo.payloadLen, unit.maxLen);
  if (recLen == 0)
    {
      return 0;
    }

  std::vector<uint8_t> recoveredBytes(recLen, 0);
  for (uint32_t i = 0; i < repairInfo.payloadLen && i < recLen; ++i)
    {
      recoveredBytes[i] = repairInfo.payload[i];
    }
  for (uint32_t i = 0; i < unit.xorBuf.size() && i < recLen; ++i)
    {
      recoveredBytes[i] ^= unit.xorBuf[i];
    }

  Ptr<Packet> recoveredPacket = Create<Packet>(recoveredBytes.data(), recLen);

  if (recoveredPacket == 0)
    {
      NS_LOG_ERROR("XOR recovery failed for PSN=" << missingPsn);
      return 0;
    }

  // Edge trimming: 若丢失的是消息尾包且尾包长度小于修复得到的 maxLen，则裁剪到准确长度
  if (repairInfo.hasLast)
    {
      uint32_t rel = missingPsn - basePSN;
      if (rel == repairInfo.lastRel)
        {
          uint32_t cur = recoveredPacket->GetSize();
          uint32_t want = repairInfo.lastLength;
          if (want > 0 && cur > want)
            {
              recoveredPacket->RemoveAtEnd(cur - want);
            }
        }
    }

  // Update block state
  // 边界检查：防止数组越界
  if (relativePsn >= MAX_BLOCK_SIZE)
    {
      std::cerr << "[FEC-DECODER-ERROR-RECOVER] relativePsn " << relativePsn
                << " exceeds MAX_BLOCK_SIZE " << MAX_BLOCK_SIZE
                << " (missingPsn=" << missingPsn << ", basePSN=" << basePSN
                << ", blockSize=" << m_blockSize << ")" << std::endl;
      return recoveredPacket;
    }

  state.receivedBits[relativePsn] = true;
  state.receivedCount++;

  // Incorporate recovered packet into unit XOR state for subsequent recoveries
  uint32_t actualLen = recoveredPacket->GetSize();
  if (actualLen > unit.maxLen)
    {
      unit.maxLen = actualLen;
      if (unit.xorBuf.size() < actualLen)
        {
          unit.xorBuf.resize(actualLen, 0);
        }
    }
  for (uint32_t i = 0; i < actualLen && i < recoveredBytes.size(); ++i)
    {
      unit.xorBuf[i] ^= recoveredBytes[i];
    }

  NS_LOG_INFO("Successfully recovered PSN=" << missingPsn << " (block " << basePSN
                                             << " now " << state.receivedCount << "/"
                                             << m_blockSize << ")");

  if (state.receivedCount >= m_blockSize)
    {
      CleanupOldBlocks(basePSN + m_blockSize);
    }

  return recoveredPacket;
}

uint32_t
FecDecoder::CountMissingInRecipe(const std::vector<uint32_t>& recipe,
                                 uint32_t& missingPsn) const
{
  uint32_t missingCount = 0;
  std::vector<uint32_t> missingPsns;

  for (uint32_t psn : recipe)
    {
      if (!HasPacket(psn))
        {
          missingCount++;
          missingPsn = psn;
          missingPsns.push_back(psn);
        }
    }

  // Log missing packet analysis
  if (missingCount > 0) {
      std::stringstream missingStr;
      missingStr << "[";
      for (size_t i = 0; i < missingPsns.size(); i++) {
          if (i > 0) missingStr << ",";
          missingStr << missingPsns[i];
      }
      missingStr << "]";
      NS_LOG_DEBUG("Recipe analysis: " << missingCount << " missing PSNs=" << missingStr.str());
  }

  return missingCount;
}

FecDecoder::BlockState&
FecDecoder::GetOrCreateBlockState(uint32_t basePSN)
{
  auto it = m_blockStates.find(basePSN);

  if (it != m_blockStates.end())
    {
      return it->second;
    }

  // Create new block state
  BlockState newState;
  newState.basePSN = basePSN;
  newState.receivedBits.reset();
  newState.receivedCount = 0;
  newState.unitXor.resize(m_interleavingDepth == 0 ? 1 : m_interleavingDepth);

  m_blockStates[basePSN] = newState;

  NS_LOG_DEBUG("Created new block state for bPSN=" << basePSN);

  return m_blockStates[basePSN];
}

} // namespace ns3
