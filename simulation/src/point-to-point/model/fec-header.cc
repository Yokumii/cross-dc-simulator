/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 */

#include "fec-header.h"
#include "ns3/log.h"

NS_LOG_COMPONENT_DEFINE("FecHeader");

namespace ns3 {

NS_OBJECT_ENSURE_REGISTERED(FecHeader);

FecHeader::FecHeader()
  : m_type(FEC_DATA),
    m_blockSize(0),
    m_interleavingDepth(0),
    m_basePSN(0),
    m_psn(0),
    m_isn(0),
    m_edgeFlags(0),
    m_lastRel(0),
    m_lastLength(0)
{
}

FecHeader::~FecHeader()
{
}

void
FecHeader::SetType(FecPacketType type)
{
  m_type = static_cast<uint8_t>(type);
}

void
FecHeader::SetBlockSize(uint16_t blockSize)
{
  m_blockSize = blockSize;
}

void
FecHeader::SetInterleavingDepth(uint8_t depth)
{
  m_interleavingDepth = depth;
}

void
FecHeader::SetBasePSN(uint32_t bPSN)
{
  m_basePSN = bPSN;
}

void
FecHeader::SetPSN(uint32_t psn)
{
  m_psn = psn;
}

void
FecHeader::SetISN(uint16_t isn)
{
  m_isn = isn;
}

void
FecHeader::SetRecipe(const std::vector<uint32_t>& recipe)
{
  m_recipe = recipe;
}

void
FecHeader::SetHasFirst(bool hasFirst)
{
  if (hasFirst) m_edgeFlags |= 0x01;
  else m_edgeFlags &= static_cast<uint8_t>(~0x01);
}

void
FecHeader::SetHasLast(bool hasLast)
{
  if (hasLast) m_edgeFlags |= 0x02;
  else m_edgeFlags &= static_cast<uint8_t>(~0x02);
}

void
FecHeader::SetLastRel(uint16_t lastRel)
{
  m_lastRel = lastRel;
}

void
FecHeader::SetLastLength(uint16_t lastLength)
{
  m_lastLength = lastLength;
}

FecHeader::FecPacketType
FecHeader::GetType() const
{
  return static_cast<FecPacketType>(m_type);
}

uint16_t
FecHeader::GetBlockSize() const
{
  return m_blockSize;
}

uint8_t
FecHeader::GetInterleavingDepth() const
{
  return m_interleavingDepth;
}

uint32_t
FecHeader::GetBasePSN() const
{
  return m_basePSN;
}

uint32_t
FecHeader::GetPSN() const
{
  return m_psn;
}

uint16_t
FecHeader::GetISN() const
{
  return m_isn;
}

const std::vector<uint32_t>&
FecHeader::GetRecipe() const
{
  return m_recipe;
}

uint16_t
FecHeader::GetRecipeLength() const
{
  return static_cast<uint16_t>(m_recipe.size());
}

bool
FecHeader::GetHasFirst() const
{
  return (m_edgeFlags & 0x01) != 0;
}

bool
FecHeader::GetHasLast() const
{
  return (m_edgeFlags & 0x02) != 0;
}

uint16_t
FecHeader::GetLastRel() const
{
  return m_lastRel;
}

uint16_t
FecHeader::GetLastLength() const
{
  return m_lastLength;
}

TypeId
FecHeader::GetTypeId(void)
{
  static TypeId tid = TypeId("ns3::FecHeader")
    .SetParent<Header>()
    .AddConstructor<FecHeader>()
    ;
  return tid;
}

TypeId
FecHeader::GetInstanceTypeId(void) const
{
  return GetTypeId();
}

void
FecHeader::Print(std::ostream &os) const
{
  os << "FecHeader: ";
  if (m_type == FEC_DATA) os << "Type=DATA ";
  else if (m_type == FEC_REPAIR) os << "Type=REPAIR ";
  else if (m_type == FEC_NEGOTIATE) os << "Type=NEGOTIATE ";
  else os << "Type=" << static_cast<uint32_t>(m_type) << " ";
  os << "BlockSize=" << m_blockSize << " ";
  os << "InterleavingDepth=" << static_cast<uint32_t>(m_interleavingDepth) << " ";
  os << "BasePSN=" << m_basePSN << " ";

  if (m_type == FEC_DATA)
    {
      os << "PSN=" << m_psn;
    }
  else if (m_type == FEC_REPAIR)
    {
      os << "ISN=" << m_isn << " ";
      os << "HasFirst=" << (GetHasFirst() ? 1 : 0) << " ";
      os << "HasLast=" << (GetHasLast() ? 1 : 0) << " ";
      if (GetHasLast())
        {
          os << "LastRel=" << m_lastRel << " ";
          os << "LastLen=" << m_lastLength << " ";
        }
      os << "RecipeLen=" << m_recipe.size() << " ";
      os << "Recipe=[";
      for (size_t i = 0; i < m_recipe.size(); ++i)
        {
          if (i > 0) os << ",";
          os << m_recipe[i];
        }
      os << "]";
    }
  else
    {
      // negotiation: reuse ISN as op-code (0=request,1=ack)
      os << "NegOp=" << m_isn;
    }
}

uint32_t
FecHeader::GetSerializedSize(void) const
{
  // Base header: type(1) + blockSize(2) + interleavingDepth(1) + basePSN(4)
  uint32_t size = 8;

  if (m_type == FEC_DATA)
    {
      // Data packet: + PSN(4)
      size += 4;
    }
  else
    {
      // Repair/Negotiate: + ISN(2) + edgeFlags(1) + lastRel(2) + lastLen(2) + recipeLen(2) + recipe(4 * len)
      // For NEGOTIATE, recipeLen is 0 and recipe is empty.
      size += 2 + 1 + 2 + 2 + 2 + 4 * m_recipe.size();
    }

  return size;
}

void
FecHeader::Serialize(Buffer::Iterator start) const
{
  Buffer::Iterator i = start;

  // Write base header
  i.WriteU8(m_type);
  i.WriteHtonU16(m_blockSize);
  i.WriteU8(m_interleavingDepth);
  i.WriteHtonU32(m_basePSN);

  if (m_type == FEC_DATA)
    {
      // Write data packet fields
      i.WriteHtonU32(m_psn);
    }
  else
    {
      // Write repair/negotiate packet fields
      i.WriteHtonU16(m_isn);
      i.WriteU8(m_edgeFlags);
      i.WriteHtonU16(m_lastRel);
      i.WriteHtonU16(m_lastLength);
      i.WriteHtonU16(static_cast<uint16_t>(m_recipe.size()));

      // Write recipe PSNs
      for (std::vector<uint32_t>::const_iterator it = m_recipe.begin();
           it != m_recipe.end(); ++it)
        {
          i.WriteHtonU32(*it);
        }
    }
}

uint32_t
FecHeader::Deserialize(Buffer::Iterator start)
{
  Buffer::Iterator i = start;

  // Read base header
  m_type = i.ReadU8();
  m_blockSize = i.ReadNtohU16();
  m_interleavingDepth = i.ReadU8();
  m_basePSN = i.ReadNtohU32();

  if (m_type == FEC_DATA)
    {
      // Read data packet fields
      m_psn = i.ReadNtohU32();
    }
  else
    {
      // Read repair/negotiate packet fields
      m_isn = i.ReadNtohU16();
      m_edgeFlags = i.ReadU8();
      m_lastRel = i.ReadNtohU16();
      m_lastLength = i.ReadNtohU16();
      uint16_t recipeLen = i.ReadNtohU16();

      // Read recipe PSNs
      m_recipe.clear();
      m_recipe.reserve(recipeLen);
      for (uint16_t j = 0; j < recipeLen; ++j)
        {
          m_recipe.push_back(i.ReadNtohU32());
        }
    }

  return GetSerializedSize();
}

uint32_t
FecHeader::GetBaseSize()
{
  // Minimum size for data packet
  return 8 + 4; // base(8) + PSN(4)
}

} // namespace ns3
