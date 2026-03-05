/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#ifndef FEC_HEADER_H
#define FEC_HEADER_H

#include <stdint.h>
#include <vector>
#include "ns3/header.h"
#include "ns3/buffer.h"

namespace ns3 {

/**
 * \ingroup point-to-point
 * \brief Header for Forward Error Correction (FEC) packets
 *
 * This header implements the LoWAR FEC scheme with message-aware
 * coding blocks. It supports both data packets and repair packets
 * with layered interleaving for burst loss tolerance.
 *
 * Header format:
 * - Type (1 byte): DATA (0) or REPAIR (1)
 * - Block Size r (2 bytes): Number of packets per coding block
 * - Interleaving Depth c (1 byte): Number of repair layers
 * - Base PSN (4 bytes): Starting sequence number of coding block
 * - ISN (2 bytes): Interleaving Sequence Number (for repair packets)
 * - Edge Flags (1 byte): bit0=hasFirst, bit1=hasLast (repair only)
 * - Last Rel (2 bytes): last packet index within block (repair only)
 * - Last Length (2 bytes): byte length of last packet ([FecHeader][Payload]) (repair only)
 * - Recipe Length (2 bytes): Number of PSNs in recipe (repair only)
 * - Recipe PSNs (4 bytes each): Packet sequence numbers (repair only)
 */

class FecHeader : public Header
{
public:
  /**
   * \brief FEC packet types
   */
  enum FecPacketType {
    FEC_DATA = 0,    ///< Data packet (original packet with FEC metadata)
    FEC_REPAIR = 1,  ///< Repair packet (XOR of multiple data packets)
    FEC_NEGOTIATE = 2 ///< Negotiation packet (parameter sync/request)
  };

  /**
   * \brief Constructor
   */
  FecHeader();

  /**
   * \brief Destructor
   */
  virtual ~FecHeader();

  // Setters
  /**
   * \brief Set packet type
   * \param type FEC_DATA or FEC_REPAIR
   */
  void SetType(FecPacketType type);

  /**
   * \brief Set coding block size (r parameter)
   * \param blockSize Number of packets per coding block
   */
  void SetBlockSize(uint16_t blockSize);

  /**
   * \brief Set interleaving depth (c parameter)
   * \param depth Number of interleaving layers
   */
  void SetInterleavingDepth(uint8_t depth);

  /**
   * \brief Set base packet sequence number
   * \param bPSN Starting PSN of the coding block
   */
  void SetBasePSN(uint32_t bPSN);

  /**
   * \brief Set packet sequence number (for data packets)
   * \param psn Packet sequence number
   */
  void SetPSN(uint32_t psn);

  /**
   * \brief Set interleaving sequence number (for repair packets)
   * \param isn Repair packet sequence within coding block
   */
  void SetISN(uint16_t isn);

  /**
   * \brief Set recipe list (for repair packets)
   * \param recipe Vector of PSNs that were XORed to create this repair packet
   */
  void SetRecipe(const std::vector<uint32_t>& recipe);

  /**
   * \brief Set edge metadata (repair packets only)
   */
  void SetHasFirst(bool hasFirst);
  void SetHasLast(bool hasLast);
  void SetLastRel(uint16_t lastRel);
  void SetLastLength(uint16_t lastLength);

  // Getters
  /**
   * \brief Get packet type
   * \return FEC_DATA or FEC_REPAIR
   */
  FecPacketType GetType() const;

  /**
   * \brief Get coding block size
   * \return Block size (r parameter)
   */
  uint16_t GetBlockSize() const;

  /**
   * \brief Get interleaving depth
   * \return Interleaving depth (c parameter)
   */
  uint8_t GetInterleavingDepth() const;

  /**
   * \brief Get base PSN
   * \return Starting PSN of coding block
   */
  uint32_t GetBasePSN() const;

  /**
   * \brief Get packet sequence number
   * \return PSN for data packets
   */
  uint32_t GetPSN() const;

  /**
   * \brief Get ISN
   * \return Interleaving sequence number for repair packets
   */
  uint16_t GetISN() const;

  /**
   * \brief Get recipe list
   * \return Vector of PSNs in the repair packet's recipe
   */
  const std::vector<uint32_t>& GetRecipe() const;

  /**
   * \brief Get number of PSNs in recipe
   * \return Recipe length
   */
  uint16_t GetRecipeLength() const;

  bool GetHasFirst() const;
  bool GetHasLast() const;
  uint16_t GetLastRel() const;
  uint16_t GetLastLength() const;

  // NS3 Header interface
  static TypeId GetTypeId(void);
  virtual TypeId GetInstanceTypeId(void) const;
  virtual void Print(std::ostream &os) const;
  virtual uint32_t GetSerializedSize(void) const;
  virtual void Serialize(Buffer::Iterator start) const;
  virtual uint32_t Deserialize(Buffer::Iterator start);

  /**
   * \brief Get base header size (without recipe)
   * \return Size in bytes
   */
  static uint32_t GetBaseSize();

private:
  uint8_t m_type;              ///< Packet type (DATA or REPAIR)
  uint16_t m_blockSize;        ///< Coding block size (r)
  uint8_t m_interleavingDepth; ///< Interleaving depth (c)
  uint32_t m_basePSN;          ///< Base PSN of coding block
  uint32_t m_psn;              ///< Packet sequence number (for data packets)
  uint16_t m_isn;              ///< Interleaving sequence number (for repair packets)
  uint8_t m_edgeFlags;         ///< Edge flags (repair packets only)
  uint16_t m_lastRel;          ///< Last packet index within this block (repair packets only)
  uint16_t m_lastLength;       ///< Byte length of last packet ([FecHeader][Payload]) (repair only)
  std::vector<uint32_t> m_recipe; ///< Recipe list (for repair packets)
};

} // namespace ns3

#endif /* FEC_HEADER_H */
