/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2024 NUS
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#include "ns3/test.h"
#include "ns3/fec-header.h"
#include "ns3/fec-xor-engine.h"
#include "ns3/fec-encoder.h"
#include "ns3/fec-decoder.h"
#include "ns3/packet.h"
#include "ns3/log.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("FecTest");

/**
 * \brief FEC Header Test Case
 */
class FecHeaderTest : public TestCase
{
public:
    FecHeaderTest();
    virtual ~FecHeaderTest();

private:
    virtual void DoRun(void);
};

FecHeaderTest::FecHeaderTest()
    : TestCase("FEC Header serialization and deserialization")
{
}

FecHeaderTest::~FecHeaderTest()
{
}

void
FecHeaderTest::DoRun(void)
{
    // Test DATA packet header
    FecHeader dataHeader;
    dataHeader.SetType(FecHeader::FEC_DATA);
    dataHeader.SetBlockSize(64);
    dataHeader.SetInterleavingDepth(8);
    dataHeader.SetPSN(42);
    dataHeader.SetBasePSN(0);

    // Serialize and deserialize
    Ptr<Packet> packet = Create<Packet>(100);
    packet->AddHeader(dataHeader);

    FecHeader receivedHeader;
    packet->RemoveHeader(receivedHeader);

    NS_TEST_ASSERT_MSG_EQ(receivedHeader.GetType(), FecHeader::FEC_DATA, "DATA type mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedHeader.GetBlockSize(), 64, "Block size mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedHeader.GetInterleavingDepth(), 8, "Interleaving depth mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedHeader.GetPSN(), 42, "PSN mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedHeader.GetBasePSN(), 0, "Base PSN mismatch");

    // Test REPAIR packet header with recipe
    FecHeader repairHeader;
    repairHeader.SetType(FecHeader::FEC_REPAIR);
    repairHeader.SetBlockSize(64);
    repairHeader.SetInterleavingDepth(8);
    repairHeader.SetBasePSN(0);
    repairHeader.SetISN(3);

    std::vector<uint32_t> recipe;
    recipe.push_back(0);
    recipe.push_back(8);
    recipe.push_back(16);
    repairHeader.SetRecipe(recipe);

    Ptr<Packet> repairPacket = Create<Packet>(100);
    repairPacket->AddHeader(repairHeader);

    FecHeader receivedRepairHeader;
    repairPacket->RemoveHeader(receivedRepairHeader);

    NS_TEST_ASSERT_MSG_EQ(receivedRepairHeader.GetType(), FecHeader::FEC_REPAIR, "REPAIR type mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedRepairHeader.GetISN(), 3, "ISN mismatch");

    std::vector<uint32_t> receivedRecipe = receivedRepairHeader.GetRecipe();
    NS_TEST_ASSERT_MSG_EQ(receivedRecipe.size(), 3, "Recipe size mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedRecipe[0], 0, "Recipe[0] mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedRecipe[1], 8, "Recipe[1] mismatch");
    NS_TEST_ASSERT_MSG_EQ(receivedRecipe[2], 16, "Recipe[2] mismatch");

    NS_LOG_INFO("FEC Header test passed");
}

/**
 * \brief FEC XOR Engine Test Case
 */
class FecXorEngineTest : public TestCase
{
public:
    FecXorEngineTest();
    virtual ~FecXorEngineTest();

private:
    virtual void DoRun(void);
};

FecXorEngineTest::FecXorEngineTest()
    : TestCase("FEC XOR Engine encode and decode")
{
}

FecXorEngineTest::~FecXorEngineTest()
{
}

void
FecXorEngineTest::DoRun(void)
{
    // Create test packets with known data
    Ptr<Packet> p1 = Create<Packet>(100);
    Ptr<Packet> p2 = Create<Packet>(100);
    Ptr<Packet> p3 = Create<Packet>(100);

    std::vector<Ptr<Packet>> packets;
    packets.push_back(p1);
    packets.push_back(p2);
    packets.push_back(p3);

    // Create XOR engine and generate repair packet
    FecXorEngine xorEngine;
    Ptr<Packet> repairPacket = xorEngine.XorPackets(packets);

    NS_TEST_ASSERT_MSG_NE(repairPacket, 0, "Repair packet creation failed");
    NS_TEST_ASSERT_MSG_EQ(repairPacket->GetSize(), 100, "Repair packet size mismatch");

    // Test recovery - recover p2 from p1, p3, and repair
    std::vector<Ptr<Packet>> availablePackets;
    availablePackets.push_back(p1);
    availablePackets.push_back(p3);

    Ptr<Packet> recoveredP2 = xorEngine.RecoverPacket(repairPacket, availablePackets);

    NS_TEST_ASSERT_MSG_NE(recoveredP2, 0, "Packet recovery failed");
    NS_TEST_ASSERT_MSG_EQ(recoveredP2->GetSize(), p2->GetSize(), "Recovered packet size mismatch");

    // Verify recovered packet equals original
    uint8_t buffer1[100], buffer2[100];
    p2->CopyData(buffer1, 100);
    recoveredP2->CopyData(buffer2, 100);

    bool identical = true;
    for (int i = 0; i < 100; i++)
    {
        if (buffer1[i] != buffer2[i])
        {
            identical = false;
            break;
        }
    }

    NS_TEST_ASSERT_MSG_EQ(identical, true, "Recovered packet data mismatch");

    NS_LOG_INFO("FEC XOR Engine test passed");
}

/**
 * \brief FEC Encoder Test Case
 */
class FecEncoderTest : public TestCase
{
public:
    FecEncoderTest();
    virtual ~FecEncoderTest();

private:
    virtual void DoRun(void);
};

FecEncoderTest::FecEncoderTest()
    : TestCase("FEC Encoder block management and repair generation")
{
}

FecEncoderTest::~FecEncoderTest()
{
}

void
FecEncoderTest::DoRun(void)
{
    // Create encoder with LoWAR(8, 4) parameters
    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecEncoder> encoder = Ptr<FecEncoder>(new FecEncoder(blockSize, interleavingDepth));

    NS_TEST_ASSERT_MSG_NE(encoder, 0, "Encoder creation failed");

    // Add packets to the block
    for (uint32_t i = 0; i < blockSize; i++)
    {
        Ptr<Packet> packet = Create<Packet>(100);
        encoder->EncodePacket(packet, i);

        if (i < blockSize - 1)
        {
            NS_TEST_ASSERT_MSG_EQ(encoder->IsBlockComplete(), false, "Block should not be complete yet");
        }
    }

    // After adding blockSize packets, block should be complete
    NS_TEST_ASSERT_MSG_EQ(encoder->IsBlockComplete(), true, "Block should be complete");

    // Generate repair packets
    std::vector<Ptr<Packet>> repairPackets = encoder->GenerateRepairPackets();

    NS_TEST_ASSERT_MSG_EQ(repairPackets.size(), interleavingDepth, "Should generate c repair packets");

    // Verify each repair packet has proper header
    for (size_t i = 0; i < repairPackets.size(); i++)
    {
        FecHeader header;
        repairPackets[i]->PeekHeader(header);

        NS_TEST_ASSERT_MSG_EQ(header.GetType(), FecHeader::FEC_REPAIR, "Repair packet type mismatch");
        NS_TEST_ASSERT_MSG_EQ(header.GetISN(), i, "ISN mismatch");
        NS_TEST_ASSERT_MSG_NE(header.GetRecipe().size(), 0, "Recipe should not be empty");
    }

    // Reset and verify encoder is ready for next block
    encoder->ResetBlock();
    NS_TEST_ASSERT_MSG_EQ(encoder->IsBlockComplete(), false, "Block should not be complete after reset");

    NS_LOG_INFO("FEC Encoder test passed");
}

/**
 * \brief FEC Decoder Test Case
 */
class FecDecoderTest : public TestCase
{
public:
    FecDecoderTest();
    virtual ~FecDecoderTest();

private:
    virtual void DoRun(void);
};

FecDecoderTest::FecDecoderTest()
    : TestCase("FEC Decoder recovery logic")
{
}

FecDecoderTest::~FecDecoderTest()
{
}

void
FecDecoderTest::DoRun(void)
{
    // Create decoder with LoWAR(8, 4) parameters
    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecDecoder> decoder = Ptr<FecDecoder>(new FecDecoder(blockSize, interleavingDepth));

    NS_TEST_ASSERT_MSG_NE(decoder, 0, "Decoder creation failed");

    // Receive all data packets except one (simulate single loss)
    uint32_t lostPSN = 3;
    for (uint32_t i = 0; i < blockSize; i++)
    {
        if (i != lostPSN)
        {
            Ptr<Packet> packet = Create<Packet>(100);
            FecHeader header;
            header.SetType(FecHeader::FEC_DATA);
            header.SetPSN(i);
            packet->AddHeader(header);

            decoder->ReceiveDataPacket(packet, i);
        }
    }

    // Create a simple repair packet that can recover the lost packet
    // For simplicity, we'll create a repair packet manually
    std::vector<uint32_t> recipe;
    for (uint32_t i = 0; i < blockSize; i++)
    {
        recipe.push_back(i);
    }

    Ptr<Packet> repairPayload = Create<Packet>(100);
    decoder->ReceiveRepairPacket(repairPayload, 0, 0, recipe);

    // Attempt recovery
    std::vector<Ptr<Packet>> recoveredPackets = decoder->RecoverLostPackets();

    // Should recover the lost packet
    NS_TEST_ASSERT_MSG_EQ(recoveredPackets.size(), 1, "Should recover 1 packet");

    NS_LOG_INFO("FEC Decoder test passed");
}

/**
 * \brief FEC End-to-End Test Case
 */
class FecEndToEndTest : public TestCase
{
public:
    FecEndToEndTest();
    virtual ~FecEndToEndTest();

private:
    virtual void DoRun(void);
};

FecEndToEndTest::FecEndToEndTest()
    : TestCase("FEC end-to-end encode-decode cycle")
{
}

FecEndToEndTest::~FecEndToEndTest()
{
}

void
FecEndToEndTest::DoRun(void)
{
    // Create encoder and decoder with LoWAR(8, 4)
    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecEncoder> encoder = Ptr<FecEncoder>(new FecEncoder(blockSize, interleavingDepth));
    Ptr<FecDecoder> decoder = Ptr<FecDecoder>(new FecDecoder(blockSize, interleavingDepth));

    // Encode a full block
    std::vector<Ptr<Packet>> originalPackets;
    for (uint32_t i = 0; i < blockSize; i++)
    {
        Ptr<Packet> packet = Create<Packet>(100);
        originalPackets.push_back(packet->Copy());

        FecHeader header;
        header.SetType(FecHeader::FEC_DATA);
        header.SetPSN(i);
        header.SetBasePSN(0);
        packet->AddHeader(header);

        encoder->EncodePacket(packet, i);
    }

    NS_TEST_ASSERT_MSG_EQ(encoder->IsBlockComplete(), true, "Encoding block should be complete");

    // Generate repair packets
    std::vector<Ptr<Packet>> repairPackets = encoder->GenerateRepairPackets();
    NS_TEST_ASSERT_MSG_EQ(repairPackets.size(), interleavingDepth, "Should generate c repair packets");

    // Simulate reception with one packet loss
    uint32_t lostPSN = 5;
    for (uint32_t i = 0; i < blockSize; i++)
    {
        if (i != lostPSN)
        {
            Ptr<Packet> packet = Create<Packet>(100);
            FecHeader header;
            header.SetType(FecHeader::FEC_DATA);
            header.SetPSN(i);
            packet->AddHeader(header);
            decoder->ReceiveDataPacket(packet, i);
        }
    }

    // Receive repair packets and attempt recovery
    for (size_t i = 0; i < repairPackets.size(); i++)
    {
        FecHeader header;
        repairPackets[i]->PeekHeader(header);

        Ptr<Packet> payload = repairPackets[i]->Copy();
        payload->RemoveHeader(header);

        decoder->ReceiveRepairPacket(payload, header.GetBasePSN(), header.GetISN(), header.GetRecipe());

        // Try recovery after each repair packet
        std::vector<Ptr<Packet>> recovered = decoder->RecoverLostPackets();

        if (!recovered.empty())
        {
            NS_TEST_ASSERT_MSG_EQ(recovered.size(), 1, "Should recover exactly 1 packet");
            NS_LOG_INFO("Successfully recovered lost packet with repair packet " << i);
            break;
        }
    }

    NS_LOG_INFO("FEC end-to-end test passed");
}

/**
 * \brief FEC Test Suite
 */
class FecTestSuite : public TestSuite
{
public:
    FecTestSuite();
};

FecTestSuite::FecTestSuite()
    : TestSuite("fec", UNIT)
{
    AddTestCase(new FecHeaderTest, TestCase::QUICK);
    AddTestCase(new FecXorEngineTest, TestCase::QUICK);
    AddTestCase(new FecEncoderTest, TestCase::QUICK);
    AddTestCase(new FecDecoderTest, TestCase::QUICK);
    AddTestCase(new FecEndToEndTest, TestCase::QUICK);
}

static FecTestSuite fecTestSuite;
