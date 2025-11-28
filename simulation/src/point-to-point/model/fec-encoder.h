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
#include <map>
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
   * \brief Encode a data packet into the current coding block
   *
   * Adds the packet to all interleaving layers according to LoWAR algorithm.
   * Each layer uses different interleaving index to provide burst tolerance.
   *
   * \param dataPacket The data packet to encode
   * \param psn Packet sequence number
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
   * \brief Generate repair packets for the current block
   *
   * Creates c repair packets using layered interleaving. Each repair packet
   * is the XOR of packets from its layer's buckets.
   *
   * Must be called only when IsBlockComplete() returns true.
   *
   * \return Vector of repair packets with FEC headers
   */
  std::vector<Ptr<Packet>> GenerateRepairPackets();

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

private:
  /**
   * \brief Coding unit for one interleaving layer bucket
   *
   * Stores the XOR accumulation for packets in this bucket.
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

  /**
   * \brief Calculate bucket index for a packet in a layer
   *
   * Uses LoWAR interleaving formula: bucket = (psn / i^layer) % bucketsPerLayer
   * where i is the interleaving index (typically 2).
   *
   * \param psn Packet sequence number (relative to block base)
   * \param layer Interleaving layer index (0 to c-1)
   * \return Bucket index within the layer
   */
  uint32_t GetBucketIndex(uint32_t psn, uint32_t layer) const;

  /**
   * \brief Get number of buckets per layer
   *
   * Calculated as: ceil(r / i^layer)
   *
   * \param layer Interleaving layer index
   * \return Number of buckets in this layer
   */
  uint32_t GetBucketsPerLayer(uint32_t layer) const;

  uint32_t m_blockSize;             ///< r: Coding block size
  uint32_t m_interleavingDepth;     ///< c: Number of interleaving layers
  uint32_t m_interleavingIndex;     ///< i: Interleaving index (default 2)

  uint32_t m_currentBlockBase;      ///< bPSN: Base PSN of current block
  uint32_t m_packetsInBlock;        ///< Number of packets in current block

  /**
   * \brief Coding units organized by [layer][bucket]
   *
   * Each layer has multiple buckets, each bucket accumulates XOR of
   * packets assigned to it by the interleaving algorithm.
   */
  std::vector<std::vector<CodingUnit>> m_codingLayers;

  /**
   * \brief Map from PSN to packet for current block
   *
   * Stores packets temporarily for repair generation.
   */
  std::map<uint32_t, Ptr<Packet>> m_blockPackets;
};

} // namespace ns3

#endif /* FEC_ENCODER_H */
