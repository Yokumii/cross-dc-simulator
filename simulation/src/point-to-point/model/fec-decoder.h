/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#ifndef FEC_DECODER_H
#define FEC_DECODER_H

#include <vector>
#include <map>
#include <bitset>
#include "ns3/object.h"
#include "ns3/packet.h"
#include "ns3/ptr.h"

namespace ns3 {

/**
 * \ingroup point-to-point
 * \brief LoWAR FEC decoder with reordering buffer and recovery
 *
 * This class implements the LoWAR FEC decoding algorithm. It maintains:
 * - Reordering buffer for received data packets
 * - Bitmap tracking received/missing packets
 * - Repair packet buffer for recovery attempts
 *
 * Recovery algorithm:
 * 1. Track received data packets via bitmap
 * 2. Store repair packets with their recipes
 * 3. When repair packet can recover a missing packet (only 1 missing in recipe):
 *    - XOR all received packets in recipe with repair packet
 *    - Result is the missing packet
 * 4. Iteratively attempt recovery as new packets/repairs arrive
 */

class FecDecoder : public Object
{
public:
  /**
   * \brief Get the type ID.
   * \return the object TypeId
   */
  static TypeId GetTypeId(void);

  /**
   * \brief Maximum block size supported (for bitmap)
   */
  static const uint32_t MAX_BLOCK_SIZE = 256;

  /**
   * \brief Default constructor (required by NS3 Object system)
   */
  FecDecoder();

  /**
   * \brief Constructor
   * \param blockSize Number of packets per coding block (r parameter)
   * \param interleavingDepth Number of interleaving layers (c parameter)
   */
  FecDecoder(uint32_t blockSize, uint32_t interleavingDepth);

  /**
   * \brief Destructor
   */
  ~FecDecoder();

  /**
   * \brief Receive a data packet
   *
   * Stores packet in reordering buffer and marks as received in bitmap.
   * May trigger recovery attempts if repair packets are waiting.
   *
   * \param packet The data packet
   * \param psn Packet sequence number
   */
  void ReceiveDataPacket(Ptr<Packet> packet, uint32_t psn);

  /**
   * \brief Receive a repair packet
   *
   * Stores repair packet and attempts to recover missing packets.
   * Recovery succeeds when exactly one packet in recipe is missing.
   *
   * \param repairPacket The repair packet (with FEC header)
   * \param basePSN Base PSN of the coding block
   * \param isn Interleaving sequence number
   * \param recipe List of PSNs XORed in this repair packet
   */
  void ReceiveRepairPacket(Ptr<Packet> repairPacket,
                           uint32_t basePSN,
                           uint16_t isn,
                           const std::vector<uint32_t>& recipe,
                           bool hasFirst,
                           bool hasLast,
                           uint16_t lastRel,
                           uint16_t lastLength);

  /**
   * \brief Attempt to recover missing packets
   *
   * Iterates through stored repair packets and attempts recovery.
   * Should be called after receiving new data or repair packets.
   *
   * \return Vector of successfully recovered packets
   */
  std::vector<Ptr<Packet>> RecoverLostPackets();

  /**
   * \brief Check if a coding block is complete
   *
   * A block is complete when all packets are received or recovered.
   *
   * \param basePSN Base PSN of the block to check
   * \return True if all packets in block are available
   */
  bool IsBlockComplete(uint32_t basePSN) const;

  /**
   * \brief Get a packet from the reordering buffer
   *
   * \param psn Packet sequence number
   * \return Packet if available, null otherwise
   */
  Ptr<Packet> GetPacket(uint32_t psn) const;

  /**
   * \brief Remove old blocks from buffer
   *
   * Frees memory for blocks that are complete or too old.
   *
   * \param threshold Only keep blocks with bPSN >= threshold
   */
  void CleanupOldBlocks(uint32_t threshold);

  /**
   * \brief Get number of packets recovered so far
   * \return Recovery count
   */
  uint32_t GetRecoveredCount() const;

  /**
   * \brief Get number of packets that could not be recovered
   * \return Unrecoverable packet count
   */
  uint32_t GetUnrecoverableCount() const;

  /**
   * \brief Whether decoder has any buffered state
   *
   * Used by upper-layer GC to reclaim per-flow decoder state in large simulations.
   */
  bool IsIdle() const;

private:
  /**
   * \brief Repair packet information
   */
  struct RepairPacketInfo
  {
    Ptr<Packet> packet;           ///< The repair packet data
    uint32_t basePSN;             ///< Base PSN of coding block
    uint16_t isn;                 ///< Interleaving sequence number
    std::vector<uint32_t> recipe; ///< PSNs XORed in this repair
    bool hasFirst;                ///< Whether this block contains message first packet
    bool hasLast;                 ///< Whether this block contains message last packet
    uint16_t lastRel;             ///< Relative index of message last packet within block
    uint16_t lastLength;          ///< Byte length of message last packet ([FecHeader][Payload])
    bool used;                    ///< Whether this repair was used for recovery
  };

  /**
   * \brief Coding block state
   */
  struct BlockState
  {
    uint32_t basePSN;                          ///< Base PSN of this block
    std::bitset<MAX_BLOCK_SIZE> receivedBits;  ///< Bitmap of received packets
    uint32_t receivedCount;                    ///< Number of received packets
  };

  /**
   * \brief Attempt recovery using a specific repair packet
   *
   * \param repairInfo The repair packet to use
   * \return Recovered packet if successful, null otherwise
   */
  Ptr<Packet> AttemptRecoveryWithRepair(RepairPacketInfo& repairInfo);

  /**
   * \brief Check how many packets are missing from a recipe
   *
   * \param recipe List of PSNs
   * \param missingPsn Output: PSN of the missing packet (if exactly one)
   * \return Number of missing packets in recipe
   */
  uint32_t CountMissingInRecipe(const std::vector<uint32_t>& recipe,
                                uint32_t& missingPsn) const;

  /**
   * \brief Get block state for a given base PSN
   *
   * Creates new state if doesn't exist.
   *
   * \param basePSN Base PSN of the block
   * \return Reference to block state
   */
  BlockState& GetOrCreateBlockState(uint32_t basePSN);

  uint32_t m_blockSize;             ///< r: Coding block size
  uint32_t m_interleavingDepth;     ///< c: Number of interleaving layers

  /**
   * \brief Reordering buffer: PSN → Packet
   */
  std::map<uint32_t, Ptr<Packet>> m_reorderBuffer;

  /**
   * \brief Block state tracking: bPSN → BlockState
   */
  std::map<uint32_t, BlockState> m_blockStates;

  /**
   * \brief Repair packet buffer
   */
  std::vector<RepairPacketInfo> m_repairBuffer;

  uint32_t m_recoveredCount;        ///< Total packets recovered
  uint32_t m_unrecoverableCount;    ///< Total unrecoverable packets
};

} // namespace ns3

#endif /* FEC_DECODER_H */
