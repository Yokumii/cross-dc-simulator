/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Standalone FEC Test Program
 *
 * This is a simplified standalone test for FEC functionality
 * that doesn't require NS3's test framework to be enabled.
 */

#include "ns3/core-module.h"
#include "ns3/fec-header.h"
#include "ns3/fec-xor-engine.h"
#include "ns3/fec-encoder.h"
#include "ns3/fec-decoder.h"
#include "ns3/packet.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("FecStandaloneTest");

// Test result tracking
static int tests_passed = 0;
static int tests_failed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cout << "✗ FAIL: " << msg << std::endl; \
            tests_failed++; \
            return false; \
        } \
    } while(0)

#define TEST_PASS(msg) \
    do { \
        std::cout << "✓ PASS: " << msg << std::endl; \
        tests_passed++; \
        return true; \
    } while(0)

/**
 * Test 1: FEC Header Serialization
 */
bool TestFecHeader()
{
    std::cout << "\n=== Test 1: FEC Header ===" << std::endl;

    // Test DATA header
    FecHeader dataHeader;
    dataHeader.SetType(FecHeader::FEC_DATA);
    dataHeader.SetBlockSize(64);
    dataHeader.SetInterleavingDepth(8);
    dataHeader.SetPSN(42);
    dataHeader.SetBasePSN(0);

    Ptr<Packet> packet = Create<Packet>(100);
    packet->AddHeader(dataHeader);

    FecHeader receivedHeader;
    packet->RemoveHeader(receivedHeader);

    TEST_ASSERT(receivedHeader.GetType() == FecHeader::FEC_DATA,
                "DATA type mismatch");
    TEST_ASSERT(receivedHeader.GetPSN() == 42,
                "PSN mismatch");
    TEST_ASSERT(receivedHeader.GetBlockSize() == 64,
                "Block size mismatch");

    // Test REPAIR header with recipe
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

    TEST_ASSERT(receivedRepairHeader.GetType() == FecHeader::FEC_REPAIR,
                "REPAIR type mismatch");
    TEST_ASSERT(receivedRepairHeader.GetISN() == 3,
                "ISN mismatch");

    std::vector<uint32_t> receivedRecipe = receivedRepairHeader.GetRecipe();
    TEST_ASSERT(receivedRecipe.size() == 3,
                "Recipe size mismatch");
    TEST_ASSERT(receivedRecipe[0] == 0 && receivedRecipe[1] == 8 && receivedRecipe[2] == 16,
                "Recipe content mismatch");

    TEST_PASS("FEC Header serialization/deserialization");
}

/**
 * Test 2: XOR Engine Operations
 */
bool TestXorEngine()
{
    std::cout << "\n=== Test 2: XOR Engine ===" << std::endl;

    // Create test packets with known data
    Ptr<Packet> p1 = Create<Packet>(100);
    Ptr<Packet> p2 = Create<Packet>(100);
    Ptr<Packet> p3 = Create<Packet>(100);

    std::vector<Ptr<Packet>> packets;
    packets.push_back(p1);
    packets.push_back(p2);
    packets.push_back(p3);

    // Generate repair packet
    FecXorEngine xorEngine;
    Ptr<Packet> repairPacket = xorEngine.XorPackets(packets);

    TEST_ASSERT(repairPacket != 0, "Repair packet creation failed");
    TEST_ASSERT(repairPacket->GetSize() == 100, "Repair packet size mismatch");

    // Test recovery - recover p2 (index 1) from p1, p3, and repair
    // RecoverPacket expects: (receivedPackets with nulls, repairPacket, missingIndex)
    std::vector<Ptr<Packet>> receivedPackets;
    receivedPackets.push_back(p1);       // Index 0: received
    receivedPackets.push_back(0);        // Index 1: missing (p2)
    receivedPackets.push_back(p3);       // Index 2: received

    uint32_t missingIndex = 1;  // p2 is at index 1
    Ptr<Packet> recoveredP2 = xorEngine.RecoverPacket(receivedPackets, repairPacket, missingIndex);

    TEST_ASSERT(recoveredP2 != 0, "Packet recovery failed");
    TEST_ASSERT(recoveredP2->GetSize() == p2->GetSize(),
                "Recovered packet size mismatch");

    // Verify recovered packet equals original
    uint8_t buffer1[100], buffer2[100];
    p2->CopyData(buffer1, 100);
    recoveredP2->CopyData(buffer2, 100);

    bool identical = true;
    for (int i = 0; i < 100; i++) {
        if (buffer1[i] != buffer2[i]) {
            identical = false;
            break;
        }
    }
    TEST_ASSERT(identical, "Recovered packet data mismatch");

    TEST_PASS("XOR Engine encode and decode");
}

/**
 * Test 3: FEC Encoder
 */
bool TestEncoder()
{
    std::cout << "\n=== Test 3: FEC Encoder ===" << std::endl;

    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecEncoder> encoder = Ptr<FecEncoder>(new FecEncoder(blockSize, interleavingDepth));

    TEST_ASSERT(encoder != 0, "Encoder creation failed");

    // Add packets to the block
    for (uint32_t i = 0; i < blockSize; i++) {
        Ptr<Packet> packet = Create<Packet>(100);
        encoder->EncodePacket(packet, i);

        if (i < blockSize - 1) {
            TEST_ASSERT(!encoder->IsBlockComplete(),
                        "Block should not be complete yet");
        }
    }

    TEST_ASSERT(encoder->IsBlockComplete(),
                "Block should be complete after r packets");

    // Generate repair packets
    // For LoWAR(8, 4): buckets = 8 + 4 + 2 + 1 = 15 repair packets
    std::vector<Ptr<Packet>> repairPackets = encoder->GenerateRepairPackets();
    uint32_t expectedRepairPackets = 15;  // sum of buckets across all layers
    TEST_ASSERT(repairPackets.size() == expectedRepairPackets,
                "Should generate 15 repair packets for LoWAR(8,4)");

    // Verify repair packet headers
    for (size_t i = 0; i < repairPackets.size(); i++) {
        FecHeader header;
        repairPackets[i]->PeekHeader(header);

        TEST_ASSERT(header.GetType() == FecHeader::FEC_REPAIR,
                    "Repair packet type mismatch");
        TEST_ASSERT(header.GetISN() == i,
                    "ISN mismatch");
        TEST_ASSERT(header.GetRecipe().size() > 0,
                    "Recipe should not be empty");
    }

    // Reset and verify
    encoder->ResetBlock();
    TEST_ASSERT(!encoder->IsBlockComplete(),
                "Block should not be complete after reset");

    TEST_PASS("FEC Encoder block management");
}

/**
 * Test 4: FEC Decoder
 */
bool TestDecoder()
{
    std::cout << "\n=== Test 4: FEC Decoder ===" << std::endl;

    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecDecoder> decoder = Ptr<FecDecoder>(new FecDecoder(blockSize, interleavingDepth));

    TEST_ASSERT(decoder != 0, "Decoder creation failed");

    // Receive all data packets except one (simulate single loss)
    uint32_t lostPSN = 3;
    for (uint32_t i = 0; i < blockSize; i++) {
        if (i != lostPSN) {
            Ptr<Packet> packet = Create<Packet>(100);
            FecHeader header;
            header.SetType(FecHeader::FEC_DATA);
            header.SetPSN(i);
            packet->AddHeader(header);

            decoder->ReceiveDataPacket(packet, i);
        }
    }

    // Create repair packet
    std::vector<uint32_t> recipe;
    for (uint32_t i = 0; i < blockSize; i++) {
        recipe.push_back(i);
    }

    Ptr<Packet> repairPayload = Create<Packet>(100);
    decoder->ReceiveRepairPacket(repairPayload, 0, 0, recipe);

    // Attempt recovery
    std::vector<Ptr<Packet>> recoveredPackets = decoder->RecoverLostPackets();

    TEST_ASSERT(recoveredPackets.size() == 1,
                "Should recover 1 packet");

    TEST_PASS("FEC Decoder recovery logic");
}

/**
 * Test 5: End-to-End
 */
bool TestEndToEnd()
{
    std::cout << "\n=== Test 5: End-to-End ===" << std::endl;

    uint32_t blockSize = 8;
    uint32_t interleavingDepth = 4;
    Ptr<FecEncoder> encoder = Ptr<FecEncoder>(new FecEncoder(blockSize, interleavingDepth));
    Ptr<FecDecoder> decoder = Ptr<FecDecoder>(new FecDecoder(blockSize, interleavingDepth));

    // Encode a full block
    std::vector<Ptr<Packet>> originalPackets;
    for (uint32_t i = 0; i < blockSize; i++) {
        Ptr<Packet> packet = Create<Packet>(100);
        originalPackets.push_back(packet->Copy());

        FecHeader header;
        header.SetType(FecHeader::FEC_DATA);
        header.SetPSN(i);
        header.SetBasePSN(0);
        packet->AddHeader(header);

        encoder->EncodePacket(packet, i);
    }

    TEST_ASSERT(encoder->IsBlockComplete(),
                "Encoding block should be complete");

    // Generate repair packets
    // For LoWAR(8, 4): buckets = 8 + 4 + 2 + 1 = 15 repair packets
    std::vector<Ptr<Packet>> repairPackets = encoder->GenerateRepairPackets();
    uint32_t expectedRepairPackets = 15;
    TEST_ASSERT(repairPackets.size() == expectedRepairPackets,
                "Should generate 15 repair packets for LoWAR(8,4)");

    // Simulate reception with one packet loss
    uint32_t lostPSN = 5;
    for (uint32_t i = 0; i < blockSize; i++) {
        if (i != lostPSN) {
            Ptr<Packet> packet = Create<Packet>(100);
            FecHeader header;
            header.SetType(FecHeader::FEC_DATA);
            header.SetPSN(i);
            packet->AddHeader(header);
            decoder->ReceiveDataPacket(packet, i);
        }
    }

    // Receive repair packets and attempt recovery
    bool recovered = false;
    for (size_t i = 0; i < repairPackets.size(); i++) {
        FecHeader header;
        repairPackets[i]->PeekHeader(header);

        Ptr<Packet> payload = repairPackets[i]->Copy();
        payload->RemoveHeader(header);

        decoder->ReceiveRepairPacket(payload, header.GetBasePSN(),
                                    header.GetISN(), header.GetRecipe());

        std::vector<Ptr<Packet>> recoveredPkts = decoder->RecoverLostPackets();
        if (!recoveredPkts.empty()) {
            TEST_ASSERT(recoveredPkts.size() == 1,
                        "Should recover exactly 1 packet");
            recovered = true;
            std::cout << "  → Recovered packet with repair packet " << i << std::endl;
            break;
        }
    }

    TEST_ASSERT(recovered, "Failed to recover lost packet");

    TEST_PASS("End-to-end FEC encode-decode cycle");
}

/**
 * Main test runner
 */
int main(int argc, char *argv[])
{
    std::cout << "\n";
    std::cout << "╔════════════════════════════════════════════╗\n";
    std::cout << "║   FEC Standalone Test Suite               ║\n";
    std::cout << "║   LoWAR Forward Error Correction          ║\n";
    std::cout << "╚════════════════════════════════════════════╝\n";

    // Run all tests
    TestFecHeader();
    TestXorEngine();
    TestEncoder();
    TestDecoder();
    TestEndToEnd();

    // Summary
    std::cout << "\n";
    std::cout << "╔════════════════════════════════════════════╗\n";
    std::cout << "║           Test Results Summary             ║\n";
    std::cout << "╠════════════════════════════════════════════╣\n";
    std::cout << "║  Tests Passed: " << tests_passed << "                           ║\n";
    std::cout << "║  Tests Failed: " << tests_failed << "                           ║\n";
    std::cout << "╚════════════════════════════════════════════╝\n";

    if (tests_failed == 0) {
        std::cout << "\n🎉 All tests passed!\n" << std::endl;
        return 0;
    } else {
        std::cout << "\n❌ Some tests failed.\n" << std::endl;
        return 1;
    }
}
