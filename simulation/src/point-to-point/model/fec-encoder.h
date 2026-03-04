/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#ifndef FEC_ENCODER_H
#define FEC_ENCODER_H

#include <vector>
#include "ns3/object.h"
#include "ns3/packet.h"
#include "ns3/ptr.h"

namespace ns3 {

/**
 * \ingroup point-to-point
 * \brief LoWAR FEC encoder with layered interleaving
 *
 * This class implements the LoWAR(r, c) encoding algorithm with message-aware
 * coding blocks. It maintains encoding state for the current block and generates
 * repair packets using layered interleaving for burst loss tolerance.
 *
 * Key parameters:
 * - r (block size): Number of data packets per coding block
 * - c (interleaving depth): Number of repair layers
 *
 * Algorithm:
 * 1. Encode data packets into the current block
 * 2. When block is complete (r packets), generate c repair packets
 * 3. Each repair layer uses different interleaving index for burst tolerance
 * 4. Reset block and continue with next bPSN
 */

class FecEncoder : public Object
{
public:
  /**
   * \brief Get the type ID.
   * \return the object TypeId
   */
  static TypeId GetTypeId(void);

  /**
   * \brief Maximum block size supported
   */
  static const uint32_t MAX_BLOCK_SIZE = 256;

  /**
   * \brief Default constructor (required by NS3 Object system)
   */
  FecEncoder();

  /**
   * \brief Constructor
   * \param blockSize Number of packets per coding block (r parameter)
   * \param interleavingDepth Number of interleaving layers (c parameter)
   */
  FecEncoder(uint32_t blockSize, uint32_t interleavingDepth);

  /**
   * \brief Destructor
   */
  ~FecEncoder();

  /**
   * \brief 将数据包编码到当前编码块
   *
   * 每个数据包只选择一个 coding unit 进行 XOR 更新。
   *
   * \param dataPacket 待编码的数据包
   * \param psn 包序号
   */
  void EncodePacket(Ptr<Packet> dataPacket, uint32_t psn);

  /**
   * \brief Check if current coding block is complete
   *
   * A block is complete when it contains r packets.
   *
   * \return True if block is complete and ready for repair generation
   */
  bool IsBlockComplete() const;

  /**
   * \brief 生成当前块的 repair 包
   *
   * 每个 coding unit 最多生成一个 repair 包。
   * 默认仅在 IsBlockComplete() 为 true 时调用；若 allowIncomplete=true，则用于“消息结束时的尾块 flush”，
   * 会对当前已编码的数据包集合生成 repair 包（与 LoWAR 的 message-aware coding 对齐）。
   *
   * \param allowIncomplete 是否允许对未满 r 的尾块生成 repair
   * \return 带 FEC 头部的 repair 包列表
   */
  std::vector<Ptr<Packet>> GenerateRepairPackets(bool allowIncomplete = false);

  /**
   * \brief Reset encoder state for next coding block
   *
   * Clears all encoding buffers and advances to next block base PSN.
   * Should be called after GenerateRepairPackets().
   */
  void ResetBlock();

  /**
   * \brief Get current block base PSN
   * \return Base packet sequence number of current coding block
   */
  uint32_t GetCurrentBlockBase() const;

  /**
   * \brief Get number of packets in current block
   * \return Count of packets encoded in current block
   */
  uint32_t GetPacketsInBlock() const;

  /**
   * \brief 当前块是否已有数据包
   */
  bool HasData() const { return m_packetsInBlock > 0; }

  /**
   * \brief 标记当前编码块包含消息尾包（用于 repair header edge metadata）
   *
   * \param lastRel 尾包在块内的相对序号（0..r-1）
   * \param lastLength 尾包长度（[FecHeader][Payload] 的字节数）
   */
  void MarkHasLast(uint16_t lastRel, uint16_t lastLength);

private:
  /**
   * \brief 编码单元
   *
   * 保存该单元的 XOR 累加结果与 recipe。
   */
  struct CodingUnit
  {
    std::vector<uint8_t> xorBuffer;  ///< XOR accumulation buffer
    std::vector<uint32_t> recipe;     ///< PSNs of packets in this bucket
    uint32_t maxPacketSize;           ///< Maximum packet size in bucket
  };

  /**
   * \brief Add packet to a specific coding unit
   *
   * \param unit The coding unit to update
   * \param packet The packet to add
   * \param psn Packet sequence number
   */
  void AddPacketToCodingUnit(CodingUnit& unit, Ptr<Packet> packet, uint32_t psn);

  bool m_hasFirst;
  bool m_hasLast;
  uint16_t m_lastRel;
  uint16_t m_lastLength;

  uint32_t m_blockSize;             ///< r: Coding block size
  uint32_t m_interleavingDepth;     ///< c: Number of interleaving layers

  uint32_t m_currentBlockBase;      ///< bPSN: Base PSN of current block
  uint32_t m_packetsInBlock;        ///< Number of packets in current block

  /**
   * \brief coding units 列表，数量等于 interleaving depth
   */
  std::vector<CodingUnit> m_units;

};

} // namespace ns3

#endif /* FEC_ENCODER_H */
