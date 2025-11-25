/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#ifndef FEC_XOR_ENGINE_H
#define FEC_XOR_ENGINE_H

#include <vector>
#include "ns3/packet.h"
#include "ns3/ptr.h"

namespace ns3 {

/**
 * \ingroup point-to-point
 * \brief XOR encoding/decoding engine for FEC
 *
 * This class provides the core XOR operations for Forward Error Correction.
 * It implements byte-wise XOR for generating repair packets and recovering
 * lost packets from repair packets.
 *
 * Key operations:
 * - XorPackets: Combine multiple packets via XOR to create a repair packet
 * - RecoverPacket: Use repair packet to recover a single missing packet
 * - XorBuffers: Low-level byte-wise XOR operation
 */

class FecXorEngine
{
public:
  /**
   * \brief XOR multiple packets to create a repair packet
   *
   * This function performs byte-wise XOR of all input packets to generate
   * a repair packet. All packets are expected to be padded to the same size
   * (the maximum size among them).
   *
   * \param packets Vector of packets to XOR
   * \return Repair packet (XOR result)
   */
  static Ptr<Packet> XorPackets(const std::vector<Ptr<Packet>>& packets);

  /**
   * \brief Recover a lost packet using a repair packet
   *
   * Given a set of received packets and a repair packet, recover the missing
   * packet by XORing all received packets with the repair packet.
   *
   * Formula: missing = repair ⊕ packet1 ⊕ packet2 ⊕ ... ⊕ packetN
   *
   * \param receivedPackets Vector of received packets (may contain nullptrs for missing packets)
   * \param repairPacket Repair packet
   * \param missingIndex Index of the missing packet in receivedPackets
   * \return Recovered packet
   */
  static Ptr<Packet> RecoverPacket(const std::vector<Ptr<Packet>>& receivedPackets,
                                     Ptr<Packet> repairPacket,
                                     uint32_t missingIndex);

  /**
   * \brief Get maximum packet size from a vector
   *
   * \param packets Vector of packets
   * \return Maximum size in bytes
   */
  static uint32_t GetMaxPacketSize(const std::vector<Ptr<Packet>>& packets);

  /**
   * \brief Pad packet to specified size
   *
   * If packet is smaller than targetSize, pad with zeros.
   * If packet is larger or equal, return a copy.
   *
   * \param packet Original packet
   * \param targetSize Target size in bytes
   * \return Padded packet
   */
  static Ptr<Packet> PadPacket(Ptr<Packet> packet, uint32_t targetSize);

private:
  /**
   * \brief Perform byte-wise XOR on two buffers
   *
   * Result is stored in dst buffer.
   * Formula: dst[i] = dst[i] ⊕ src[i] for all i
   *
   * \param dst Destination buffer (input/output)
   * \param src Source buffer (input only)
   * \param len Length in bytes
   */
  static void XorBuffers(uint8_t* dst, const uint8_t* src, size_t len);
};

} // namespace ns3

#endif /* FEC_XOR_ENGINE_H */
