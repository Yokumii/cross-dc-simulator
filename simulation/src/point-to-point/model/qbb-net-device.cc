/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2006 Georgia Tech Research Corporation, INRIA
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
 *
 * Author: Yuliang Li <yuliangli@g.harvard.com>
 */

#define __STDC_LIMIT_MACROS 1
#include "ns3/qbb-net-device.h"
#include "fec-header.h"
#include "fec-xor-engine.h"
#include "fec-encoder.h"
#include "fec-decoder.h"

#include <algorithm>
#include <stdint.h>
#include <stdio.h>
#include <utility>

#include <iostream>
#include <unordered_map>

#include "ns3/assert.h"
#include "ns3/boolean.h"
#include "ns3/cn-header.h"
#include "ns3/custom-header.h"
#include "ns3/data-rate.h"
#include "ns3/double.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/error-model.h"
#include "ns3/flow-id-num-tag.h"
#include "ns3/flow-id-tag.h"
#include "ns3/flow-stat-tag.h"
#include "ns3/ipv4-header.h"
#include "ns3/ipv4.h"
#include "ns3/log.h"
#include "ns3/object-vector.h"
#include "ns3/pause-header.h"
#include "ns3/point-to-point-channel.h"
#include "ns3/pointer.h"
#include "ns3/ppp-header.h"
#include "ns3/qbb-channel.h"
#include "ns3/qbb-header.h"
#include "ns3/random-variable.h"
#include "ns3/rdma-hw.h"
#include "ns3/seq-ts-header.h"
#include "ns3/settings.h"
#include "ns3/simulator.h"
#include "ns3/udp-header.h"
#include "ns3/uinteger.h"

#define MAP_KEY_EXISTS(map, key) (((map).find(key) != (map).end()))

NS_LOG_COMPONENT_DEFINE("QbbNetDevice");

namespace ns3 {

extern std::unordered_map<unsigned, Time> acc_pause_time;

namespace {
static inline uint32_t
PackRc(uint32_t r, uint32_t c)
{
    return (r & 0xFFFFu) | ((c & 0xFFFFu) << 16);
}

static inline uint16_t
ReadNtohU16(const uint8_t* p)
{
    return (static_cast<uint16_t>(p[0]) << 8) | static_cast<uint16_t>(p[1]);
}

static inline uint32_t
ReadNtohU32(const uint8_t* p)
{
    return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | static_cast<uint32_t>(p[3]);
}

// 安全判定：避免对非 FEC 的 UDP 包误解码（否则 PeekHeader/Deserialize 可能读取随机字段造成异常或 OOM）。
static inline bool
LooksLikeFecDataPacket(Ptr<Packet> pkt)
{
    if (!pkt)
    {
        return false;
    }
    if (pkt->GetSize() < FecHeader::GetBaseSize())
    {
        return false;
    }

    uint8_t buf[12];
    if (pkt->CopyData(buf, sizeof(buf)) != sizeof(buf))
    {
        return false;
    }

    uint8_t type = buf[0];
    if (type != static_cast<uint8_t>(FecHeader::FEC_DATA))
    {
        return false;
    }

    uint16_t blockSize = ReadNtohU16(buf + 1);
    uint8_t interDepth = buf[3];
    uint32_t basePsn = ReadNtohU32(buf + 4);
    uint32_t psn = ReadNtohU32(buf + 8);

    if (blockSize == 0 || blockSize > 4096)
    {
        return false;
    }
    if (interDepth == 0 || interDepth > 64)
    {
        return false;
    }
    if ((basePsn % blockSize) != 0)
    {
        return false;
    }
    if (psn < basePsn || (psn - basePsn) >= blockSize)
    {
        return false;
    }
    return true;
}

static inline bool
IsCrossDcFlowForFec(uint32_t sip, uint32_t dip)
{
    if (Settings::servers_per_dc == 0 || Settings::num_dc <= 1)
    {
        return false;
    }

    uint32_t srcId = Settings::ip_to_node_id(Ipv4Address(sip));
    uint32_t dstId = Settings::ip_to_node_id(Ipv4Address(dip));
    if (srcId >= Settings::host_num || dstId >= Settings::host_num)
    {
        return false;
    }

    uint32_t srcDc = srcId / Settings::servers_per_dc;
    uint32_t dstDc = dstId / Settings::servers_per_dc;
    return srcDc != dstDc;
}
}  // namespace

// uint32_t RdmaEgressQueue::ack_q_idx = 3; // 3: Middle priority
uint32_t RdmaEgressQueue::ack_q_idx = 0; // 0: high priority
// RdmaEgressQueue
TypeId RdmaEgressQueue::GetTypeId(void) {
    static TypeId tid =
        TypeId("ns3::RdmaEgressQueue")
            .SetParent<Object>()
            .AddTraceSource("RdmaEnqueue", "Enqueue a packet in the RdmaEgressQueue.",
                            MakeTraceSourceAccessor(&RdmaEgressQueue::m_traceRdmaEnqueue))
            .AddTraceSource("RdmaDequeue", "Dequeue a packet in the RdmaEgressQueue.",
                            MakeTraceSourceAccessor(&RdmaEgressQueue::m_traceRdmaDequeue));
    return tid;
}

RdmaEgressQueue::RdmaEgressQueue() {
    m_rrlast = 0;
    m_qlast = 0;
    m_mtu = 1000;
    m_ackQ = CreateObject<DropTailQueue>();
    m_ackQ->SetAttribute("MaxBytes",
                         UintegerValue(0xffffffff));  // queue limit is on a higher level, not here
    m_repairQ.resize(qCnt);
    for (uint32_t i = 0; i < qCnt; ++i)
    {
        m_repairQ[i] = CreateObject<DropTailQueue>();
        m_repairQ[i]->SetAttribute("MaxBytes",
                                   UintegerValue(0xffffffff));  // limit is on higher level
    }
}

Ptr<Packet> RdmaEgressQueue::DequeueQindex(int qIndex) {
    if (qIndex == -1) {  // high prio
        Ptr<Packet> p = m_ackQ->Dequeue();
        m_qlast = -1;
        m_traceRdmaDequeue(p, 0);
        return p;
    }
    if (qIndex <= -2 && qIndex >= -static_cast<int>(2 + qCnt - 1)) {  // repair per-PG
        uint32_t pg = static_cast<uint32_t>(-(qIndex + 2));
        if (pg < m_repairQ.size() && m_repairQ[pg])
        {
            Ptr<Packet> p = m_repairQ[pg]->Dequeue();
            m_qlast = qIndex;
            m_traceRdmaDequeue(p, pg);
            return p;
        }
        return 0;
    }
    if (qIndex >= 0) {  // qp
        Ptr<Packet> p = m_rdmaGetNxtPkt(m_qpGrp->Get(qIndex));
        m_rrlast = qIndex;
        m_qlast = qIndex;
        m_traceRdmaDequeue(p, m_qpGrp->Get(qIndex)->m_pg);
        return p;
    }
    return 0;
}
int RdmaEgressQueue::GetNextQindex(bool paused[]) {
    if (!paused[ack_q_idx] && m_ackQ->GetNPackets() > 0) return -1;

    // Repair packets: choose a non-paused PG queue (round-robin) so repairs do not bypass PFC.
    if (!m_repairQ.empty())
    {
        for (uint32_t off = 1; off <= qCnt; ++off)
        {
            uint32_t pg = (m_repairRrlast + off) % qCnt;
            if (!paused[pg] && m_repairQ[pg] && m_repairQ[pg]->GetNPackets() > 0)
            {
                m_repairRrlast = pg;
                return -static_cast<int>(2 + pg);  // -2..-(2+qCnt-1)
            }
        }
    }

    // no pkt in highest priority queue, do rr for each qp
    uint32_t fcount = m_qpGrp->GetN();
    uint32_t qIndex;
    for (qIndex = 1; qIndex <= fcount; qIndex++) {
        if (m_qpGrp->IsQpFinished((qIndex + m_rrlast) % fcount)) continue;
        Ptr<RdmaQueuePair> qp = m_qpGrp->Get((qIndex + m_rrlast) % fcount);
        bool cond1 = !paused[qp->m_pg];
        bool cond_window_allowed =
            (!qp->IsWinBound() && (!qp->irn.m_enabled || qp->CanIrnTransmit(m_mtu)));
        bool cond2 = (qp->GetBytesLeft() > 0 && cond_window_allowed);

        if (!cond2 && !m_qpGrp->IsQpFinished((qIndex + m_rrlast) % fcount)) {
            if (qp->IsFinishedConst()) {
                m_qpGrp->SetQpFinished((qIndex + m_rrlast) % fcount);
            }
        }
        if (!cond1 && cond2) {
            if (m_qpGrp->Get((qIndex + m_rrlast) % fcount)->m_nextAvail.GetTimeStep() >
                Simulator::Now().GetTimeStep()) {
                // not available now
            } else {
                // blocked by PFC
                int32_t flowid = m_qpGrp->Get((qIndex + m_rrlast) % fcount)->m_flow_id;
                if (!MAP_KEY_EXISTS(current_pause_time, flowid))
                    current_pause_time[flowid] = Simulator::Now();
            }
        } else if (cond1 && cond2) {
            if (m_qpGrp->Get((qIndex + m_rrlast) % fcount)->m_nextAvail.GetTimeStep() >
                Simulator::Now().GetTimeStep())  // not available now
                continue;
            // Check if the flow has been blocked by PFC
            {
                int32_t flowid = m_qpGrp->Get((qIndex + m_rrlast) % fcount)->m_flow_id;
                if (MAP_KEY_EXISTS(current_pause_time, flowid)) {
                    Time tdiff = Simulator::Now() - current_pause_time[flowid];
                    if (!MAP_KEY_EXISTS(acc_pause_time, flowid))
                        acc_pause_time[flowid] = Seconds(0);
                    acc_pause_time[flowid] = acc_pause_time[flowid] + tdiff;
                    current_pause_time.erase(flowid);
                }
            }
            return (qIndex + m_rrlast) % fcount;
        }
    }
    return -1024;
}

int RdmaEgressQueue::GetLastQueue() { return m_qlast; }

uint32_t RdmaEgressQueue::GetNBytes(uint32_t qIndex) {
    NS_ASSERT_MSG(qIndex < m_qpGrp->GetN(),
                  "RdmaEgressQueue::GetNBytes: qIndex >= m_qpGrp->GetN()");
    return m_qpGrp->Get(qIndex)->GetBytesLeft();
}

uint32_t RdmaEgressQueue::GetFlowCount(void) { return m_qpGrp->GetN(); }

Ptr<RdmaQueuePair> RdmaEgressQueue::GetQp(uint32_t i) { return m_qpGrp->Get(i); }

void RdmaEgressQueue::RecoverQueue(uint32_t i) {
    NS_ASSERT_MSG(i < m_qpGrp->GetN(), "RdmaEgressQueue::RecoverQueue: qIndex >= m_qpGrp->GetN()");
    m_qpGrp->Get(i)->snd_nxt = m_qpGrp->Get(i)->snd_una;
}

void RdmaEgressQueue::EnqueueHighPrioQ(Ptr<Packet> p) {
    m_traceRdmaEnqueue(p, 0);
    m_ackQ->Enqueue(p);
}

void RdmaEgressQueue::EnqueueRepairQ(Ptr<Packet> p, uint32_t pg)
{
    uint32_t idx = (pg < qCnt) ? pg : 0;
    if (idx >= m_repairQ.size() || !m_repairQ[idx])
    {
        return;
    }
    m_traceRdmaEnqueue(p, idx);
    m_repairQ[idx]->Enqueue(p);
}

void RdmaEgressQueue::CleanHighPrio(TracedCallback<Ptr<const Packet>, uint32_t> dropCb) {
    while (m_ackQ->GetNPackets() > 0) {
        Ptr<Packet> p = m_ackQ->Dequeue();
        dropCb(p, 0);
    }
}

/******************
 * QbbNetDevice
 *****************/
NS_OBJECT_ENSURE_REGISTERED(QbbNetDevice);

TypeId QbbNetDevice::GetTypeId(void) {
    static TypeId tid =
        TypeId("ns3::QbbNetDevice")
            .SetParent<PointToPointNetDevice>()
            .AddConstructor<QbbNetDevice>()
            .AddAttribute("QbbEnabled", "Enable the generation of PAUSE packet.",
                          BooleanValue(true), MakeBooleanAccessor(&QbbNetDevice::m_qbbEnabled),
                          MakeBooleanChecker())
            .AddAttribute("QcnEnabled", "Enable the generation of PAUSE packet.",
                          BooleanValue(false), MakeBooleanAccessor(&QbbNetDevice::m_qcnEnabled),
                          MakeBooleanChecker())
            .AddAttribute("DynamicThreshold", "Enable dynamic threshold.", BooleanValue(false),
                          MakeBooleanAccessor(&QbbNetDevice::m_dynamicth), MakeBooleanChecker())
            .AddAttribute("PauseTime", "Number of microseconds to pause upon congestion",
                          UintegerValue(671),  // 65535*(64Bytes/50Gbps)
                          MakeUintegerAccessor(&QbbNetDevice::m_pausetime),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("TxBeQueue", "A queue to use as the transmit queue in the device.",
                          PointerValue(), MakePointerAccessor(&QbbNetDevice::m_queue),
                          MakePointerChecker<Queue>())
            .AddAttribute("RdmaEgressQueue", "A queue to use as the transmit queue in the device.",
                          PointerValue(), MakePointerAccessor(&QbbNetDevice::m_rdmaEQ),
                          MakePointerChecker<Object>())
            .AddTraceSource("QbbEnqueue", "Enqueue a packet in the QbbNetDevice.",
                            MakeTraceSourceAccessor(&QbbNetDevice::m_traceEnqueue))
            .AddTraceSource("QbbDequeue", "Dequeue a packet in the QbbNetDevice.",
                            MakeTraceSourceAccessor(&QbbNetDevice::m_traceDequeue))
            .AddTraceSource("QbbDrop", "Drop a packet in the QbbNetDevice.",
                            MakeTraceSourceAccessor(&QbbNetDevice::m_traceDrop))
            .AddTraceSource("RdmaQpDequeue", "A qp dequeue a packet.",
                            MakeTraceSourceAccessor(&QbbNetDevice::m_traceQpDequeue))
            .AddTraceSource("QbbPfc", "get a PFC packet. 0: resume, 1: pause",
                            MakeTraceSourceAccessor(&QbbNetDevice::m_tracePfc));

    return tid;
}

QbbNetDevice::QbbNetDevice() {
    NS_LOG_FUNCTION(this);
    m_ecn_source = new std::vector<ECNAccount>;
    for (uint32_t i = 0; i < qCnt; i++) {
        m_paused[i] = false;
    }

    m_rdmaEQ = CreateObject<RdmaEgressQueue>();

    // FEC initialization
    m_fecEnabled = false;
    m_fecBlockSize = 64;  // Default LoWAR(64, 8)
    m_fecInterleavingDepth = 8;
    m_fecEncodedPackets = 0;
    m_fecRepairPackets = 0;
    m_fecRecoveredPackets = 0;
    m_fecUnrecoverablePackets = 0;
    m_fecFlows.clear();
}

QbbNetDevice::~QbbNetDevice() { NS_LOG_FUNCTION(this); }

void QbbNetDevice::DoDispose() {
    NS_LOG_FUNCTION(this);

    PointToPointNetDevice::DoDispose();
}

void QbbNetDevice::TransmitComplete(void) {
    NS_LOG_FUNCTION(this);
    NS_ASSERT_MSG(m_txMachineState == BUSY, "Must be BUSY if transmitting");
    m_txMachineState = READY;
    NS_ASSERT_MSG(m_currentPkt != 0, "QbbNetDevice::TransmitComplete(): m_currentPkt zero");
    m_phyTxEndTrace(m_currentPkt);
    m_currentPkt = 0;
    DequeueAndTransmit();
}

void QbbNetDevice::DequeueAndTransmit(void) {
    NS_LOG_FUNCTION(this);
    if (!m_linkUp) return;                 // if link is down, return
    if (m_txMachineState == BUSY) return;  // Quit if channel busy
    Ptr<Packet> p;
    if (m_node->GetNodeType() == 0) {  // server
        int qIndex = m_rdmaEQ->GetNextQindex(m_paused);
        if (qIndex != -1024) {
            if (qIndex == -1) {  // high prio
                p = m_rdmaEQ->DequeueQindex(qIndex);
                m_traceDequeue(p, 0);
                TransmitStart(p);
                return;
            }
            if (qIndex <= -2 && qIndex >= -static_cast<int>(2 + RdmaEgressQueue::qCnt - 1)) {  // repair per-PG
                uint32_t pg = static_cast<uint32_t>(-(qIndex + 2));
                p = m_rdmaEQ->DequeueQindex(qIndex);
                m_traceDequeue(p, pg);
                TransmitStart(p);
                return;
            }
            // a qp dequeue a packet
            Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);
            p = m_rdmaEQ->DequeueQindex(qIndex);

            // transmit
            m_traceQpDequeue(p, lastQp);
            TransmitStart(p);

            // update for the next avail time
            m_rdmaPktSent(lastQp, p, m_tInterframeGap);
        } else {  // no packet to send
            NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
            Time t = Simulator::GetMaximumSimulationTime();
            bool valid = false;
            for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++) {
                Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
                if (qp->GetBytesLeft() == 0 || qp->m_nextAvail <= Simulator::Now()) continue;
                t = Min(qp->m_nextAvail, t);
                valid = true;
            }
            if (valid && m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() &&
                t > Simulator::Now()) {
                m_nextSend = Simulator::Schedule(t - Simulator::Now(),
                                                 &QbbNetDevice::DequeueAndTransmit, this);
            }
        }
        return;
    } else {                               // switch, doesn't care about qcn, just send
        p = m_queue->DequeueRR(m_paused);  // this is round-robin
        if (p != 0) {
            m_snifferTrace(p);
            m_promiscSnifferTrace(p);
            Ipv4Header h;
            Ptr<Packet> packet = p->Copy();
            uint16_t protocol = 0;
            ProcessHeader(packet, protocol);
            packet->RemoveHeader(h);
            FlowIdTag t;
            uint32_t qIndex = m_queue->GetLastQueue();
            if (qIndex == 0) {  // this is a pause or cnp, send it immediately!
                m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
                p->RemovePacketTag(t);
            } else {
                m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
                p->RemovePacketTag(t);
            }
            m_traceDequeue(p, qIndex);
            TransmitStart(p);
            return;
        } else {  // No queue can deliver any packet
            NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
            if (m_node->GetNodeType() == 0 &&
                m_qcnEnabled) {  // nothing to send, possibly due to qcn flow control, if so
                                 // reschedule sending
                Time t = Simulator::GetMaximumSimulationTime();
                for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++) {
                    Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
                    if (qp->GetBytesLeft() == 0) continue;
                    t = Min(qp->m_nextAvail, t);
                }
                if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() &&
                    t > Simulator::Now()) {
                    m_nextSend = Simulator::Schedule(t - Simulator::Now(),
                                                     &QbbNetDevice::DequeueAndTransmit, this);
                }
            }
        }
    }
    return;
}

void QbbNetDevice::Resume(unsigned qIndex) {
    NS_LOG_FUNCTION(this << qIndex);
    NS_ASSERT_MSG(m_paused[qIndex], "Must be PAUSEd");
    m_paused[qIndex] = false;
    NS_LOG_INFO("Node " << m_node->GetId() << " dev " << m_ifIndex << " queue " << qIndex
                        << " resumed at " << Simulator::Now().GetSeconds());
    DequeueAndTransmit();
}

void QbbNetDevice::Receive(Ptr<Packet> packet) {
    NS_LOG_FUNCTION(this << packet);
    if (!m_linkUp) {
        m_traceDrop(packet, 0);
        return;
    }

    if (m_receiveErrorModel && m_receiveErrorModel->IsCorrupt(packet)) {
        //
        // If we have an error model and it indicates that it is time to lose a
        // corrupted packet, don't forward this packet up, let it go.
        //
        m_phyRxDropTrace(packet);
        return;
    }

    m_macRxTrace(packet);

    // First, peek at CustomHeader to check packet type
    CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    ch.getInt = 1;  // parse INT header
    packet->PeekHeader(ch);

    // Check for FEC packets if FEC enabled (only at receiving endpoints)
    if (m_fecEnabled && m_node->GetNodeType() == 0)
    {
        if (ch.l3Prot == 0xFA)  // FEC negotiation packet
        {
            Ptr<Packet> fecPacket = packet->Copy();
            CustomHeader tempCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
            fecPacket->RemoveHeader(tempCh);

            FecReceive(fecPacket, tempCh);
            return;
        }
        if (ch.l3Prot == 0xFB)  // FEC repair packet (use 0xFB, as 0xFD is used by NACK)
        {
            // Remove CustomHeader to access FecHeader
            Ptr<Packet> fecPacket = packet->Copy();
            CustomHeader tempCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
            fecPacket->RemoveHeader(tempCh);

            // Now we can access FecHeader
            FecHeader fecHeader;
            fecPacket->PeekHeader(fecHeader);

            // Process FEC repair packet
            FecReceive(fecPacket, tempCh);  // Pass CustomHeader to FecReceive

            // Don't forward repair packets to upper layers
            return;
        }
        else if (ch.l3Prot == 0x11)  // UDP data packet with FEC
        {
            // Data packets MAY have structure: [CustomHeader][FecHeader][Payload].
            // 大规模场景下我们可能只对跨 DC 流启用 FEC；因此需要先做轻量判定再解码。
            Ptr<Packet> fecPacket = packet->Copy();
            CustomHeader tempCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
            fecPacket->RemoveHeader(tempCh);
            if (LooksLikeFecDataPacket(fecPacket))
            {
                FecReceive(fecPacket, tempCh);

                // Remove FecHeader from original packet to restore normal structure
                // Original packet: [CustomHeader][FecHeader][Payload]
                CustomHeader savedCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
                packet->RemoveHeader(savedCh);
                FecHeader tempFecHeader;
                packet->RemoveHeader(tempFecHeader);
                packet->AddHeader(savedCh);
                // Now packet is: [CustomHeader][Payload] - normal structure
            }

            // Continue with normal processing (fall through to line below)
        }
    }

    if (ch.l3Prot == 0xFE) {  // PFC
        if (!m_qbbEnabled) return;
        unsigned qIndex = ch.pfc.qIndex;
        // std::cerr << "PFC!!" << std::endl;
        if (ch.pfc.time > 0) {
            m_tracePfc(1);
            m_paused[qIndex] = true;
            Simulator::Cancel(m_resumeEvt[qIndex]);
            m_resumeEvt[qIndex] =
                Simulator::Schedule(MicroSeconds(ch.pfc.time), &QbbNetDevice::Resume, this, qIndex);
        } else {
            m_tracePfc(0);
            Simulator::Cancel(m_resumeEvt[qIndex]);
            Resume(qIndex);
        }
    } else {                              // non-PFC packets (data, ACK, NACK, CNP...)
        if (m_node->GetNodeType() > 0) {  // switch
            packet->AddPacketTag(FlowIdTag(m_ifIndex));
            m_node->SwitchReceiveFromDevice(this, packet, ch);
        } else {  // NIC
            // send to RdmaHw
            int ret = m_rdmaReceiveCb(packet, ch);
            // TODO we may based on the ret do something
            if (ret == 0) DoMpiReceive(packet);
        }
    }
    return;
}

bool QbbNetDevice::Send(Ptr<Packet> packet, const Address &dest, uint16_t protocolNumber) {
    NS_ASSERT_MSG(false, "QbbNetDevice::Send not implemented yet\n");
    return false;
}

bool QbbNetDevice::SwitchSend(uint32_t qIndex, Ptr<Packet> packet, CustomHeader &ch) {
    m_macTxTrace(packet);
    m_traceEnqueue(packet, qIndex);
    m_queue->Enqueue(packet, qIndex);
    DequeueAndTransmit();
    return true;
}

uint32_t QbbNetDevice::SendPfc(uint32_t qIndex, uint32_t type) {
    if (!m_qbbEnabled) return 0;
    Ptr<Packet> p = Create<Packet>(0);
    PauseHeader pauseh((type == 0 ? m_pausetime : 0), m_queue->GetNBytes(qIndex), qIndex);
    p->AddHeader(pauseh);
    Ipv4Header ipv4h;  // Prepare IPv4 header
    ipv4h.SetProtocol(0xFE);
    ipv4h.SetSource(m_node->GetObject<Ipv4>()->GetAddress(m_ifIndex, 0).GetLocal());
    ipv4h.SetDestination(Ipv4Address("255.255.255.255"));
    ipv4h.SetPayloadSize(p->GetSize());
    ipv4h.SetTtl(1);
    ipv4h.SetIdentification(UniformVariable(0, 65536).GetValue());
    p->AddHeader(ipv4h);
    AddHeader(p, 0x800);
    CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    p->PeekHeader(ch);
    SwitchSend(0, p, ch);
    return (type == 0 ? m_pausetime : 0);
}

bool QbbNetDevice::Attach(Ptr<QbbChannel> ch) {
    NS_LOG_FUNCTION(this << &ch);
    m_channel = ch;
    m_channel->Attach(this);
    NotifyLinkUp();
    return true;
}

bool QbbNetDevice::TransmitStart(Ptr<Packet> p) {
    NS_LOG_FUNCTION(this << p);
    NS_LOG_LOGIC("UID is " << p->GetUid() << ")");
    //
    // This function is called to start the process of transmitting a packet.
    // We need to tell the channel that we've started wiggling the wire and
    // schedule an event that will be executed when the transmission is complete.
    //
    NS_ASSERT_MSG(m_txMachineState == READY, "Must be READY to transmit");
    m_txMachineState = BUSY;
    m_currentPkt = p;
    m_phyTxBeginTrace(m_currentPkt);

    // Apply FEC encoding if enabled
    if (m_fecEnabled && m_node->GetNodeType() == 0)  // Only encode at servers (endpoints)
    {
        FecTransmit(p);
    }

    Time txTime = Seconds(m_bps.CalculateTxTime(p->GetSize()));
    Time txCompleteTime = txTime + m_tInterframeGap;
    NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.GetSeconds() << "sec");
    Simulator::Schedule(txCompleteTime, &QbbNetDevice::TransmitComplete, this);

    bool result = m_channel->TransmitStart(p, this, txTime);
    if (result == false) {
        m_phyTxDropTrace(p);
    }
    return result;
}

Ptr<Channel> QbbNetDevice::GetChannel(void) const { return m_channel; }

bool QbbNetDevice::IsQbb(void) const { return true; }

void QbbNetDevice::NewQp(Ptr<RdmaQueuePair> qp) {
    qp->m_nextAvail = Simulator::Now();
    DequeueAndTransmit();
}
void QbbNetDevice::ReassignedQp(Ptr<RdmaQueuePair> qp) { DequeueAndTransmit(); }
void QbbNetDevice::TriggerTransmit(void) { DequeueAndTransmit(); }

void QbbNetDevice::SetQueue(Ptr<BEgressQueue> q) {
    NS_LOG_FUNCTION(this << q);
    m_queue = q;
}

Ptr<BEgressQueue> QbbNetDevice::GetQueue() { return m_queue; }

Ptr<RdmaEgressQueue> QbbNetDevice::GetRdmaQueue() { return m_rdmaEQ; }

void QbbNetDevice::RdmaEnqueueHighPrioQ(Ptr<Packet> p) {
    m_traceEnqueue(p, 0);
    m_rdmaEQ->EnqueueHighPrioQ(p);
}

void QbbNetDevice::TakeDown() {
    // TODO: delete packets in the queue, set link down
    if (m_node->GetNodeType() == 0) {
        // clean the high prio queue
        m_rdmaEQ->CleanHighPrio(m_traceDrop);
        // notify driver/RdmaHw that this link is down
        m_rdmaLinkDownCb(this);
    } else {  // switch
        // clean the queue
        for (uint32_t i = 0; i < qCnt; i++) m_paused[i] = false;
        while (1) {
            Ptr<Packet> p = m_queue->DequeueRR(m_paused);
            if (p == 0) break;
            m_traceDrop(p, m_queue->GetLastQueue());
        }
        // TODO: Notify switch that this link is down
    }
    m_linkUp = false;
}

void QbbNetDevice::UpdateNextAvail(Time t) {
    if (!m_nextSend.IsExpired() && t < m_nextSend.GetTs()) {
        Simulator::Cancel(m_nextSend);
        Time delta = t < Simulator::Now() ? Time(0) : t - Simulator::Now();
        m_nextSend = Simulator::Schedule(delta, &QbbNetDevice::DequeueAndTransmit, this);
    }
}

// FEC Methods
void
QbbNetDevice::EnableFec(bool enable)
{
    NS_LOG_FUNCTION(this << enable);

    if (enable && !m_fecEnabled)
    {
        // Per-flow encoder/decoder 状态按需创建
        m_fecFlows.clear();
        m_fecPendingCfgs.clear();
        m_fecEnabled = true;
        m_fecLastGcNs = 0;
        if (m_fecMaintenanceEvent.IsRunning())
        {
            Simulator::Cancel(m_fecMaintenanceEvent);
        }
        m_fecMaintenanceEvent =
            Simulator::Schedule(NanoSeconds(1000000ull /* 1ms */), &QbbNetDevice::FecMaintenanceTick, this);

        NS_LOG_INFO("FEC enabled on device with parameters: r=" << m_fecBlockSize
                    << " c=" << m_fecInterleavingDepth);
    }
    else if (!enable && m_fecEnabled)
    {
        // Disable FEC
        if (m_fecMaintenanceEvent.IsRunning())
        {
            Simulator::Cancel(m_fecMaintenanceEvent);
        }
        m_fecFlows.clear();
        m_fecPendingCfgs.clear();
        m_fecEnabled = false;

        NS_LOG_INFO("FEC disabled on device");
    }
}

void
QbbNetDevice::SetFecParameters(uint32_t blockSize, uint32_t interleavingDepth)
{
    NS_LOG_FUNCTION(this << blockSize << interleavingDepth);

    if (m_fecEnabled)
    {
        NS_LOG_WARN("Cannot change FEC parameters while FEC is enabled");
        return;
    }

    m_fecBlockSize = blockSize;
    m_fecInterleavingDepth = interleavingDepth;
    m_fecFlows.clear();
    m_fecPendingCfgs.clear();

    NS_LOG_INFO("FEC parameters set: r=" << m_fecBlockSize
                << " c=" << m_fecInterleavingDepth);
}

QbbNetDevice::FecStatistics
QbbNetDevice::GetFecStatistics() const
{
    FecStatistics stats;
    stats.encoded = m_fecEncodedPackets;
    stats.repair = m_fecRepairPackets;
    stats.recovered = m_fecRecoveredPackets;
    stats.unrecoverable = m_fecUnrecoverablePackets;
    return stats;
}

QbbNetDevice::FecInternalStats
QbbNetDevice::GetFecInternalStats() const
{
    FecInternalStats s;
    s.flowCount = m_fecFlows.size();
    for (const auto& kv : m_fecFlows)
    {
        const FecFlowState& f = kv.second;
        s.totalRxBlockHeaders += f.rxBlockHeaders.size();
        if (f.decoder)
        {
            s.totalDecoderBlocks += f.decoder->GetBlockStateCount();
            s.totalDecoderRepairs += f.decoder->GetRepairBufferCount();
            s.totalDecoderXorBytes += f.decoder->GetApproxXorBytes();
        }
    }
    return s;
}

void
QbbNetDevice::FecMaintenanceTick()
{
    if (!m_fecEnabled)
    {
        return;
    }

    uint64_t nowNs = Simulator::Now().GetNanoSeconds();
    FecGcFlows(nowNs);

    // 周期性维护：确保“流结束后无后续包”时也能触发回收，避免 FEC per-flow 状态常驻导致内存线性增长。
    m_fecMaintenanceEvent =
        Simulator::Schedule(NanoSeconds(1000000ull /* 1ms */), &QbbNetDevice::FecMaintenanceTick, this);
}

void
QbbNetDevice::FecGcFlows(uint64_t nowNs)
{
    const uint64_t gcIntervalNs = 1000000ull;   // 1ms
    const uint64_t idleTimeoutNs = 5000000ull;  // 5ms
    const uint64_t hardIdleTimeoutNs = 50000000ull; // 50ms：兜底防常驻
    const uint64_t pendingCfgTtlNs = 50000000ull; // 50ms：协商待生效参数 TTL

    if (nowNs - m_fecLastGcNs <= gcIntervalNs)
    {
        return;
    }

    // 清理过期的 pending cfg，避免协商包在“无后续消息”时制造常驻状态
    if (!m_fecPendingCfgs.empty())
    {
        for (auto it = m_fecPendingCfgs.begin(); it != m_fecPendingCfgs.end(); )
        {
            if (it->second.updatedNs != 0 &&
                nowNs > it->second.updatedNs &&
                (nowNs - it->second.updatedNs) > pendingCfgTtlNs)
            {
                it = m_fecPendingCfgs.erase(it);
                continue;
            }
            ++it;
        }
    }

    for (auto it = m_fecFlows.begin(); it != m_fecFlows.end(); )
    {
        FecFlowState& s = it->second;
        if (s.lastActiveNs != 0 && nowNs > s.lastActiveNs)
        {
            uint64_t idleNs = nowNs - s.lastActiveNs;

            // LoWAR 对齐：FEC 追求“快速恢复”。对已观测到尾块（flush 后）的 flow，如果在较短窗口内仍无进展，
            // 直接回收其 FEC 状态，让后续由 RDMA 重传/超时机制接管，避免 decoder/headers 常驻导致内存线性增长。
            if (s.rxSawTail && s.rxTailSeenNs != 0 && nowNs > s.rxTailSeenNs &&
                (nowNs - s.rxTailSeenNs) > idleTimeoutNs)
            {
                if (!m_fecDebugCallback.IsNull())
                {
                    uint32_t flowHash = static_cast<uint32_t>(FecFlowKeyHash{}(it->first));
                    m_fecDebugCallback(m_node->GetId(), 24, flowHash, 1 /*tail_idle_gc*/,
                                       static_cast<uint32_t>(m_fecFlows.size()), 0);
                }
                it = m_fecFlows.erase(it);
                continue;
            }

            // 兜底：即使未看到尾块（例如 repair/尾块相关包全丢），也不能无限期保留状态。
            if (idleNs > hardIdleTimeoutNs)
            {
                if (!m_fecDebugCallback.IsNull())
                {
                    uint32_t flowHash = static_cast<uint32_t>(FecFlowKeyHash{}(it->first));
                    m_fecDebugCallback(m_node->GetId(), 24, flowHash, 2 /*hard_idle_gc*/,
                                       static_cast<uint32_t>(m_fecFlows.size()), 0);
                }
                it = m_fecFlows.erase(it);
                continue;
            }

            // 普通 idle：encoder 已空时，清掉接收侧 header 缓存，降低常驻内存（decoder 的窗口化清理由接收路径负责）。
            if (idleNs > idleTimeoutNs)
            {
                bool encoderIdle = (!s.encoder) || !s.encoder->HasData();
                if (encoderIdle)
                {
                    s.rxBlockHeaders.clear();
                }
            }
        }
        ++it;
    }

    m_fecLastGcNs = nowNs;
}

void
QbbNetDevice::FecTransmit(Ptr<Packet> packet)
{
    NS_LOG_FUNCTION(this << packet);

    if (!m_fecEnabled)
    {
        NS_LOG_WARN("FEC not enabled, cannot encode packet");
        return;
    }

    // Check if this is a control packet - only encode UDP data packets (0x11)
    CustomHeader checkHeader(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    packet->PeekHeader(checkHeader);

    // Control packets: 0xFB (FEC repair), 0xFC (ACK), 0xFD (NACK), 0xFE (PFC), 0xFF (CNP)
    // Only encode UDP data packets (0x11)
    if (checkHeader.l3Prot != 0x11)
    {
        // Don't encode control packets, only encode UDP data packets
        return;
    }

    // 以五元组（sip,dip,sport,dport）为粒度维护 FEC 状态，避免跨流/跨消息编码。
    CustomHeader peekCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    packet->PeekHeader(peekCh);

    // LoWAR 的目标是“跨 WAN 的透明纠错”。在跨 DC 仿真中，优先只对跨 DC 流启用 FEC，
    // 避免对大量 intra-DC 流额外注入 repair 导致队列/内存爆炸。
    if (Settings::num_dc > 1 && Settings::servers_per_dc > 0)
    {
        if (!IsCrossDcFlowForFec(peekCh.sip, peekCh.dip))
        {
            return;
        }
    }

    FecFlowKey key{peekCh.sip, peekCh.dip, peekCh.udp.sport, peekCh.udp.dport};
    uint32_t flowHash = static_cast<uint32_t>(FecFlowKeyHash{}(key));
    uint64_t nowNs = Simulator::Now().GetNanoSeconds();

    // LoWAR：消息结束时也应结束本轮编码周期并 flush repair（避免尾块不受保护）
    bool isMsgEnd = false;
    {
        FlowStatTag fst;
        if (packet->PeekPacketTag(fst))
        {
            uint8_t t = fst.GetType();
            isMsgEnd = (t == FlowStatTag::FLOW_END) || (t == FlowStatTag::FLOW_START_AND_END);
        }
    }

    FecFlowState& flow = m_fecFlows[key];
    flow.lastActiveNs = nowNs;
    if (!flow.encoder)
    {
        flow.cfgBlockSize = m_fecBlockSize;
        flow.cfgInterleavingDepth = m_fecInterleavingDepth;
        flow.encoder = Ptr<FecEncoder>(new FecEncoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
        flow.txNextPsn = 0;
        flow.txHasBlockHeader = false;
        flow.rxBlockHeaders.clear();
    }

    // LoWAR 参数协商：把协商得到的新 (r,c) 延迟到“下一条消息开始”（txNextPsn==0）再生效，
    // 避免中途切参导致编码/解码不一致。
    if (flow.txNextPsn == 0)
    {
        auto itPending = m_fecPendingCfgs.find(key);
        if (itPending != m_fecPendingCfgs.end())
        {
            // 仅对“下一条消息”生效；一旦应用就清掉 pending，避免常驻。
            uint32_t oldR = flow.cfgBlockSize;
            uint32_t oldC = flow.cfgInterleavingDepth;
            flow.cfgBlockSize = itPending->second.blockSize;
            flow.cfgInterleavingDepth = itPending->second.interleavingDepth;
            m_fecPendingCfgs.erase(itPending);

            flow.encoder = Ptr<FecEncoder>(new FecEncoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
            flow.txHasBlockHeader = false;
            flow.rxBlockHeaders.clear();

            // Debug callback: log_type=22 (negotiate_apply_tx), param0=flowHash, param1=old(r,c), param2=new(r,c)
            if (!m_fecDebugCallback.IsNull())
            {
                m_fecDebugCallback(m_node->GetId(), 22, flowHash, PackRc(oldR, oldC),
                                   PackRc(flow.cfgBlockSize, flow.cfgInterleavingDepth), 0);
            }
        }
    }

    uint32_t psn = flow.txNextPsn;
    uint32_t basePSN = (psn / flow.cfgBlockSize) * flow.cfgBlockSize;

    // If this is the first packet of a new block, save its CustomHeader for repair packets
    if (psn == basePSN)
    {
        flow.txBlockHeader = peekCh;
        flow.txHasBlockHeader = true;
        NS_LOG_DEBUG("FEC: Saved CustomHeader from first packet of block " << basePSN
                  << " sip=" << flow.txBlockHeader.sip << " dip=" << flow.txBlockHeader.dip);
    }

    // CRITICAL: Add FEC header AFTER CustomHeader in the ORIGINAL packet
    // This is necessary so the receiver knows the PSN of each data packet
    // Packet structure becomes: [CustomHeader][FecHeader][Payload]
    FecHeader fecHeader;
    fecHeader.SetType(FecHeader::FEC_DATA);
    fecHeader.SetBlockSize(flow.cfgBlockSize);
    fecHeader.SetInterleavingDepth(flow.cfgInterleavingDepth);
    fecHeader.SetPSN(psn);
    fecHeader.SetBasePSN(basePSN);

    // Remove CustomHeader temporarily
    CustomHeader savedCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    packet->RemoveHeader(savedCh);

    // Add FecHeader
    packet->AddHeader(fecHeader);

    // Add CustomHeader back
    packet->AddHeader(savedCh);

    // Now packet has structure: [CustomHeader][FecHeader][Payload]
    // IMPORTANT: For FEC encoding, we should ONLY encode [FecHeader][Payload]
    // NOT including CustomHeader, because:
    // 1. CustomHeader will be removed before FecReceive on the receiver side
    // 2. Encoding CustomHeader causes mismatch between encoder and decoder
    // 3. This leads to corrupted recovered packets

    // Create a copy WITHOUT CustomHeader for encoding
    Ptr<Packet> encodingPacket = packet->Copy();
    CustomHeader chForEncoding(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
    encodingPacket->RemoveHeader(chForEncoding);  // Remove CustomHeader before encoding

    // Now encodingPacket has structure: [FecHeader][Payload]
    // Encode with FEC encoder
    flow.encoder->EncodePacket(encodingPacket, psn);
    m_fecEncodedPackets++;

    // 记录“消息尾包”的边界信息，供 repair header 携带并在解码时做尾包裁剪
    if (isMsgEnd)
    {
        uint16_t lastRel = static_cast<uint16_t>(psn - basePSN);
        uint16_t lastLen = static_cast<uint16_t>(encodingPacket->GetSize());
        flow.encoder->MarkHasLast(lastRel, lastLen);
    }

    NS_LOG_DEBUG("FEC encoded packet PSN=" << psn << " (block " << basePSN << ")"
                 << " encoded_size=" << encodingPacket->GetSize());

    // Increment sequence number
    flow.txNextPsn++;

    // Check if coding block is complete
    if (flow.encoder->IsBlockComplete())
    {
        NS_LOG_INFO("FEC: Coding block complete at PSN " << flow.txNextPsn - 1
                  << ", generating repair packets");

        // Generate repair packets
        std::vector<Ptr<Packet>> repairPackets = flow.encoder->GenerateRepairPackets(false);
        m_fecRepairPackets += repairPackets.size();

        NS_LOG_INFO("FEC: Generated " << repairPackets.size() << " repair packets");
        
        // Removed: FEC block complete event (event_type=0) - using debug callback only
        // if (!m_fecEventCallback.IsNull()) {
        //     m_fecEventCallback(m_node->GetId(), 0, basePSN, m_fecBlockSize, repairPackets.size());
        // }

        // Send repair packets
        if (flow.txHasBlockHeader)
        {
            SendRepairPackets(repairPackets, flow.txBlockHeader);
        }

        // Reset encoder for next block
        flow.encoder->ResetBlock();
        flow.txHasBlockHeader = false;

        NS_LOG_DEBUG("Generated and sent " << repairPackets.size() << " repair packets");
    }

    // 尾块 flush：消息结束但编码块未满 r 时，仍生成 repair 包（LoWAR message-aware coding）
    if (isMsgEnd)
    {
        if (flow.encoder->HasData())
        {
            std::vector<Ptr<Packet>> tailRepairs = flow.encoder->GenerateRepairPackets(true);
            if (!tailRepairs.empty() && flow.txHasBlockHeader)
            {
                m_fecRepairPackets += tailRepairs.size();
                SendRepairPackets(tailRepairs, flow.txBlockHeader);
            }

            // Debug callback: log_type=4 (tail_flush), param0=flowHash, param1=basePSN, param2=tailDataCnt, param3=repairCnt
            if (!m_fecDebugCallback.IsNull())
            {
                uint32_t tailDataCnt = (psn >= basePSN) ? (psn - basePSN + 1) : 0;
                m_fecDebugCallback(m_node->GetId(), 4, flowHash, basePSN, tailDataCnt, tailRepairs.size());
            }
        }

        // 下一条消息从 0 开始，避免跨消息编码/解码状态污染
        flow.encoder = Ptr<FecEncoder>(new FecEncoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
        flow.txNextPsn = 0;
        flow.txHasBlockHeader = false;
        flow.rxBlockHeaders.clear();

        // 大规模流量下五元组数量可能非常大；消息结束后该 flow 不再复用时，
        // 直接回收条目可显著降低常驻内存，避免 OOM/SIGKILL。
        m_fecFlows.erase(key);
    }

    // 大规模场景下：周期性回收 idle 的 flow 状态，避免常驻内存持续增长。
    FecGcFlows(nowNs);
}

void
QbbNetDevice::FecReceive(Ptr<Packet> packet, const CustomHeader& ch)
{
    NS_LOG_FUNCTION(this << packet);

    if (!m_fecEnabled)
    {
        NS_LOG_WARN("FEC not enabled, cannot decode packet");
        return;
    }

    // Parse FEC header
    FecHeader fecHeader;
    packet->PeekHeader(fecHeader);

    if (fecHeader.GetType() == FecHeader::FEC_NEGOTIATE)
    {
        // Negotiation packet: update per-flow FEC parameters for future messages.
        // Note: negotiation packet's CustomHeader is reversed (sip/dip swapped) for routing.
        uint32_t newR = fecHeader.GetBlockSize();
        uint32_t newC = fecHeader.GetInterleavingDepth();
        uint16_t negOp = fecHeader.GetISN();

        // Map reversed direction back to the data-flow key
        FecFlowKey dataKey{ch.dip, ch.sip, ch.udp.dport, ch.udp.sport};
        uint32_t flowHash = static_cast<uint32_t>(FecFlowKeyHash{}(dataKey));
        uint64_t nowNs = Simulator::Now().GetNanoSeconds();

        // 只记录“下一条消息”的参数；不要在这里创建/复活 m_fecFlows 条目，否则在“无后续消息”的场景会制造常驻内存。
        FecPendingCfg& pending = m_fecPendingCfgs[dataKey];
        pending.blockSize = newR;
        pending.interleavingDepth = newC;
        pending.updatedNs = nowNs;
        pending.negOp = negOp;

        // Debug callback: log_type=21 (negotiate_recv), param0=flowHash, param1=new(r,c), param2=negOp
        if (!m_fecDebugCallback.IsNull())
        {
            m_fecDebugCallback(m_node->GetId(), 21, flowHash, PackRc(newR, newC), negOp, 0);
        }
        return;
    }

    // Per-flow decoder keyed by (sip,dip,sport,dport) to avoid cross-flow coding/decoding.
    FecFlowKey key{ch.sip, ch.dip, ch.udp.sport, ch.udp.dport};
    FecFlowState& flow = m_fecFlows[key];
    uint32_t flowHash = static_cast<uint32_t>(FecFlowKeyHash{}(key));
    uint64_t nowNs = Simulator::Now().GetNanoSeconds();
    flow.lastActiveNs = nowNs;
    if (!flow.decoder)
    {
        flow.cfgBlockSize = fecHeader.GetBlockSize();
        flow.cfgInterleavingDepth = fecHeader.GetInterleavingDepth();
        if (flow.cfgBlockSize == 0) flow.cfgBlockSize = m_fecBlockSize;
        if (flow.cfgInterleavingDepth == 0) flow.cfgInterleavingDepth = m_fecInterleavingDepth;
        flow.decoder = Ptr<FecDecoder>(new FecDecoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
        flow.txNextPsn = 0;
        flow.txHasBlockHeader = false;
        flow.rxBlockHeaders.clear();
    }

    if (fecHeader.GetType() == FecHeader::FEC_DATA)
    {
        // Data packet - store in decoder
        uint32_t psn = fecHeader.GetPSN();
        // 若该数据包携带“消息结束”标记，则把它视为 tail 观测点：即便尾块 repair 丢失，也应在短窗口后回收状态。
        {
            FlowStatTag fst;
            if (packet->PeekPacketTag(fst))
            {
                uint8_t t = fst.GetType();
                if (t == FlowStatTag::FLOW_END || t == FlowStatTag::FLOW_START_AND_END)
                {
                    flow.rxSawTail = true;
                    flow.rxTailSeenNs = nowNs;
                }
            }
        }

        // 若对端切换了 (r,c)，约定会在“下一条消息”从 psn=0 重新开始；
        // 因此在 psn==0 且参数变化时重置解码器，避免跨消息状态污染。
        if (psn == 0 &&
            (fecHeader.GetBlockSize() != flow.cfgBlockSize ||
             fecHeader.GetInterleavingDepth() != flow.cfgInterleavingDepth))
        {
            uint32_t oldR = flow.cfgBlockSize;
            uint32_t oldC = flow.cfgInterleavingDepth;
            flow.cfgBlockSize = fecHeader.GetBlockSize();
            flow.cfgInterleavingDepth = fecHeader.GetInterleavingDepth();
            if (flow.cfgBlockSize == 0) flow.cfgBlockSize = m_fecBlockSize;
            if (flow.cfgInterleavingDepth == 0) flow.cfgInterleavingDepth = m_fecInterleavingDepth;

            flow.decoder = Ptr<FecDecoder>(new FecDecoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
            flow.txNextPsn = 0;
            flow.txHasBlockHeader = false;
            flow.rxBlockHeaders.clear();

            // Debug callback: log_type=23 (param_switch_rx), param0=flowHash, param1=old(r,c), param2=new(r,c), param3=0(data)
            if (!m_fecDebugCallback.IsNull())
            {
                m_fecDebugCallback(m_node->GetId(), 23, flowHash, PackRc(oldR, oldC),
                                   PackRc(flow.cfgBlockSize, flow.cfgInterleavingDepth), 0);
            }
        }

        // 直接传入该 data packet（[FecHeader][Payload]）；decoder 内部只做轻量 XOR 累计，不会长期持有包对象。
        flow.decoder->ReceiveDataPacket(packet, psn);

	        // Save CustomHeader from first packet of the block (for recovery)
	        uint32_t basePSN = (psn / flow.cfgBlockSize) * flow.cfgBlockSize;
	        if (psn == basePSN)
	        {
	            flow.rxBlockHeaders[basePSN] = ch;
	            NS_LOG_DEBUG("FEC RX: Saved CustomHeader from first packet of block " << basePSN
	                      << " sip=" << ch.sip << " dip=" << ch.dip);
	        }

        NS_LOG_DEBUG("FEC received data packet PSN=" << psn);

        // Debug callback: log_type=0 (data_recv), param0=psn, param1=basePSN, param2=flowHash, param3=pack(r,c)
        if (!m_fecDebugCallback.IsNull())
        {
            m_fecDebugCallback(m_node->GetId(), 0, psn, basePSN, flowHash,
                               PackRc(flow.cfgBlockSize, flow.cfgInterleavingDepth));
        }

        // 数据包到达也尝试恢复（覆盖“repair 先到、数据后到”的时序）
        while (true)
        {
            std::vector<Ptr<Packet>> recoveredPackets = flow.decoder->RecoverLostPackets();
            if (recoveredPackets.empty())
            {
                break;
            }
            m_fecRecoveredPackets += recoveredPackets.size();

            for (auto recoveredPkt : recoveredPackets)
            {
                FecHeader recoveredFecHeader;
                recoveredPkt->PeekHeader(recoveredFecHeader);
                uint32_t recoveredBase = recoveredFecHeader.GetBasePSN();

                auto itHdr = flow.rxBlockHeaders.find(recoveredBase);
                if (itHdr == flow.rxBlockHeaders.end())
                {
                    continue;
                }
                CustomHeader outCh = itHdr->second;
                outCh.getInt = 1;
                outCh.l3Prot = 0x11;

                recoveredPkt->RemoveHeader(recoveredFecHeader);
                recoveredPkt->AddHeader(outCh);

                if (m_node->GetNodeType() > 0)  // switch
                {
                    recoveredPkt->AddPacketTag(FlowIdTag(m_ifIndex));
                    m_node->SwitchReceiveFromDevice(this, recoveredPkt, outCh);
                }
                else  // NIC
                {
                    m_rdmaReceiveCb(recoveredPkt, outCh);
                }
            }
        }

        // LoWAR：ROB/bitmap 仅需覆盖有限窗口；丢失严重时应及时丢弃旧块状态，避免内存常驻增长。
        // 这里保留最近 4 个 block 的状态即可（超出窗口交由 RDMA 重传兜底）。
        uint32_t keepBlocks = 4;
        if (basePSN >= flow.cfgBlockSize * keepBlocks)
        {
            uint32_t threshold = basePSN - flow.cfgBlockSize * keepBlocks;
            flow.decoder->CleanupOldBlocks(threshold);
            for (auto it = flow.rxBlockHeaders.begin(); it != flow.rxBlockHeaders.end(); )
            {
                if (it->first < threshold)
                {
                    it = flow.rxBlockHeaders.erase(it);
                }
                else
                {
                    ++it;
                }
            }
        }
    }
    else if (fecHeader.GetType() == FecHeader::FEC_REPAIR)
    {
        // Repair packet - attempt recovery
        uint32_t basePSN = fecHeader.GetBasePSN();
        uint16_t isn = fecHeader.GetISN();
        std::vector<uint32_t> recipe = fecHeader.GetRecipe();

        // Repair 可能先于 data 到达；若对端切换了 (r,c)，通常会从 basePSN=0 开启新消息。
        // 因此在 basePSN==0 且参数变化时重置解码器，避免不同参数的 repair/data 混用。
        if (basePSN == 0 &&
            (fecHeader.GetBlockSize() != flow.cfgBlockSize ||
             fecHeader.GetInterleavingDepth() != flow.cfgInterleavingDepth))
        {
            uint32_t oldR = flow.cfgBlockSize;
            uint32_t oldC = flow.cfgInterleavingDepth;
            flow.cfgBlockSize = fecHeader.GetBlockSize();
            flow.cfgInterleavingDepth = fecHeader.GetInterleavingDepth();
            if (flow.cfgBlockSize == 0) flow.cfgBlockSize = m_fecBlockSize;
            if (flow.cfgInterleavingDepth == 0) flow.cfgInterleavingDepth = m_fecInterleavingDepth;

            flow.decoder = Ptr<FecDecoder>(new FecDecoder(flow.cfgBlockSize, flow.cfgInterleavingDepth));
            flow.txNextPsn = 0;
            flow.txHasBlockHeader = false;
            flow.rxBlockHeaders.clear();

            // Debug callback: log_type=23 (param_switch_rx), param0=flowHash, param1=old(r,c), param2=new(r,c), param3=1(repair)
            if (!m_fecDebugCallback.IsNull())
            {
                m_fecDebugCallback(m_node->GetId(), 23, flowHash, PackRc(oldR, oldC),
                                   PackRc(flow.cfgBlockSize, flow.cfgInterleavingDepth), 1);
            }
        }

        // 即便块内首个 data 包丢失，也要能用 repair 包携带的五元组信息重建回放头部。
        // 注意：回放到上层的 recovered 包应按“数据包”处理，因此强制 l3Prot=0x11。
        if (flow.rxBlockHeaders.find(basePSN) == flow.rxBlockHeaders.end())
        {
            CustomHeader base = ch;
            base.l3Prot = 0x11;
            flow.rxBlockHeaders[basePSN] = base;
        }

        // Log repair packet reception with recipe details
        std::stringstream recipeStr;
        recipeStr << "[";
        for (size_t i = 0; i < recipe.size(); i++) {
            if (i > 0) recipeStr << ",";
            recipeStr << recipe[i];
        }
        recipeStr << "]";
        NS_LOG_DEBUG("FEC Node " << m_node->GetId() << " received REPAIR packet: ISN=" << isn 
                     << " basePSN=" << basePSN << " recipe=" << recipeStr.str());
        
        // Debug callback: log_type=1 (repair_recv), param0=isn, param1=basePSN, param2=recipe_size
        if (!m_fecDebugCallback.IsNull()) {
            m_fecDebugCallback(m_node->GetId(), 1, isn, basePSN, recipe.size(), flowHash);
        }

        // Remove FEC header to get repair payload
        Ptr<Packet> repairPayload = packet->Copy();
        repairPayload->RemoveHeader(fecHeader);

        flow.decoder->ReceiveRepairPacket(repairPayload, basePSN, isn, recipe,
                                          fecHeader.GetHasFirst(),
                                          fecHeader.GetHasLast(),
                                          fecHeader.GetLastRel(),
                                          fecHeader.GetLastLength());

        NS_LOG_DEBUG("FEC stored repair packet in decoder buffer");

        // Debug callback: log_type=2 (recovery_attempt), param0=isn, param1=basePSN, param2=flowHash
        if (!m_fecDebugCallback.IsNull())
        {
            m_fecDebugCallback(m_node->GetId(), 2, isn, basePSN, flowHash, 0);
        }

        // Attempt recovery with this new repair packet (loop until stable)
        uint32_t totalRecovered = 0;
        while (true)
        {
            std::vector<Ptr<Packet>> recoveredPackets = flow.decoder->RecoverLostPackets();
            if (recoveredPackets.empty())
            {
                break;
            }

            totalRecovered += recoveredPackets.size();
            m_fecRecoveredPackets += recoveredPackets.size();

            // Forward recovered packets to upper layer
            for (auto recoveredPkt : recoveredPackets)
            {
                FecHeader recoveredFecHeader;
                recoveredPkt->PeekHeader(recoveredFecHeader);
                uint32_t recoveredBase = recoveredFecHeader.GetBasePSN();
                auto itHdr = flow.rxBlockHeaders.find(recoveredBase);
                if (itHdr == flow.rxBlockHeaders.end())
                {
                    continue;
                }
                CustomHeader outCh = itHdr->second;
                outCh.getInt = 1;
                outCh.l3Prot = 0x11;

                recoveredPkt->RemoveHeader(recoveredFecHeader);
                recoveredPkt->AddHeader(outCh);

                // Process as normal received packet
                if (m_node->GetNodeType() > 0)  // switch
                {
                    recoveredPkt->AddPacketTag(FlowIdTag(m_ifIndex));
                    m_node->SwitchReceiveFromDevice(this, recoveredPkt, outCh);
                }
                else  // NIC
                {
                    m_rdmaReceiveCb(recoveredPkt, outCh);
                }
            }
        }

        NS_LOG_DEBUG("FEC recovery attempt result: " << totalRecovered << " packets recovered");

        // Debug callback: log_type=3 (recovery_result), param0=isn, param1=recovered_count
        if (!m_fecDebugCallback.IsNull())
        {
            m_fecDebugCallback(m_node->GetId(), 3, isn, totalRecovered, flowHash, basePSN);
        }

        if (totalRecovered > 0)
        {
            NS_LOG_INFO("FEC Node " << m_node->GetId() << " successfully recovered "
                                    << totalRecovered << " packets using repair ISN=" << isn);
        }

        // LoWAR：当“包含消息尾包”的编码块在 flush 后仍存在未恢复的丢包时，触发一次最小协商请求（提高冗余）
        if (fecHeader.GetHasLast())
        {
            // 观测到尾块：后续若长时间无进展，应回收该 flow 的 FEC 状态（由周期性 GC 兜底）。
            flow.rxSawTail = true;
            flow.rxTailSeenNs = nowNs;

            uint32_t missing = 0;
            uint32_t lastRel = fecHeader.GetLastRel();
            for (uint32_t rel = 0; rel <= lastRel; ++rel)
            {
                uint32_t psn = basePSN + rel;
                if (!flow.decoder->HasPacket(psn))
                {
                    missing++;
                }
            }

            // 消息尾块已经完整（全部 data 已到或已恢复）时回收该 flow 的解码状态，避免大规模场景内存常驻增长。
            if (missing == 0)
            {
                m_fecFlows.erase(key);
                return;
            }

            if (missing > 0)
            {
                uint64_t curNs = Simulator::Now().GetNanoSeconds();
                if (curNs - flow.lastNegotiateSentNs > 1000000ull) // 1ms 冷却
                {
                    uint32_t curR = flow.cfgBlockSize;
                    uint32_t curC = flow.cfgInterleavingDepth;
                    uint32_t newR = curR;
                    uint32_t newC = curC < 16 ? (curC + 1) : curC;
                    if (newC == curC && curR > 4)
                    {
                        newR = std::max<uint32_t>(4, curR / 2);
                    }

                    if (newR != curR || newC != curC)
                    {
                        // Debug callback: log_type=20 (negotiate_request), param0=flowHash, param1=cur(r,c), param2=new(r,c), param3=missing
                        if (!m_fecDebugCallback.IsNull())
                        {
                            m_fecDebugCallback(m_node->GetId(), 20, flowHash, PackRc(curR, curC),
                                               PackRc(newR, newC), missing);
                        }
                        SendNegotiatePacket(ch, newR, newC, 0 /*request*/);
                        flow.lastNegotiateSentNs = curNs;
                    }
                }
            }
        }

        // 同样对 repair 到达路径执行窗口化清理（避免 repairBuffer/reorderBuffer 累积）。
        uint32_t keepBlocks = 4;
        if (basePSN >= flow.cfgBlockSize * keepBlocks)
        {
            uint32_t threshold = basePSN - flow.cfgBlockSize * keepBlocks;
            flow.decoder->CleanupOldBlocks(threshold);
            for (auto it = flow.rxBlockHeaders.begin(); it != flow.rxBlockHeaders.end(); )
            {
                if (it->first < threshold)
                {
                    it = flow.rxBlockHeaders.erase(it);
                }
                else
                {
                    ++it;
                }
            }
        }
    }

    // 周期性回收 idle flow（仅在接收路径触发也足够）
    FecGcFlows(nowNs);
}

void
QbbNetDevice::SendRepairPackets(const std::vector<Ptr<Packet>>& repairPackets, const CustomHeader& baseHeader)
{
    NS_LOG_FUNCTION(this << repairPackets.size());

    NS_LOG_DEBUG("FEC: Using saved header - sip=" << baseHeader.sip
              << " dip=" << baseHeader.dip);

    for (size_t i = 0; i < repairPackets.size(); ++i)
    {
        Ptr<Packet> repairPkt = repairPackets[i]->Copy();

        NS_LOG_DEBUG("FEC: Repair packet " << i << " size before CustomHeader: "
                  << repairPkt->GetSize());

        // Create CustomHeader for repair packet using saved header from first data packet
        // This ensures repair packets have the correct source/destination IP for routing
        CustomHeader ch = baseHeader;  // Copy the saved header

        // Mark this as a repair packet by setting l3Prot to a special value
        ch.l3Prot = 0xFB;  // Use 0xFB to indicate FEC repair packet (0xFD is used by NACK)

        NS_LOG_DEBUG("FEC: Created CustomHeader with l3Prot=0x"
                  << std::hex << (uint32_t)ch.l3Prot << std::dec);

        // Add CustomHeader to repair packet so switches can route it
        repairPkt->AddHeader(ch);

        NS_LOG_DEBUG("FEC: Repair packet " << i << " after adding CustomHeader: size="
                  << repairPkt->GetSize()
                  << " sip=" << ch.sip << " dip=" << ch.dip);

        // Enqueue repair packet for transmission
        // Repair packets MUST respect PFC pause classes; do not enqueue into ackQ (qIndex=0),
        // otherwise they can bypass PAUSE and cause queue/MMU/memory blow-up in large runs.
        if (m_node->GetNodeType() == 0)  // server
        {
            uint32_t pg = (ch.udp.pg < RdmaEgressQueue::qCnt) ? ch.udp.pg : 0;
            m_rdmaEQ->EnqueueRepairQ(repairPkt, pg);
            m_traceEnqueue(repairPkt, pg);
            
            // Removed: repair packet sent event (event_type=1) - using debug callback only
            // if (!m_fecEventCallback.IsNull()) {
            //     FecHeader fh;
            //     Ptr<Packet> copy = repairPkt->Copy();
            //     CustomHeader tempCh(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
            //     copy->RemoveHeader(tempCh);
            //     copy->PeekHeader(fh);
            //     m_fecEventCallback(m_node->GetId(), 1, fh.GetBasePSN(), fh.GetISN(), repairPkt->GetSize());
            // }
        }
        else  // switch
        {
            SwitchSend(0, repairPkt, ch);
        }
    }

    // Trigger transmission
    DequeueAndTransmit();
}

void
QbbNetDevice::SendNegotiatePacket(const CustomHeader& rxCh, uint32_t newR, uint32_t newC, uint16_t negOp)
{
    Ptr<Packet> p = Create<Packet>(0);

    FecHeader fh;
    fh.SetType(FecHeader::FEC_NEGOTIATE);
    fh.SetBlockSize(static_cast<uint16_t>(newR));
    fh.SetInterleavingDepth(static_cast<uint8_t>(newC));
    fh.SetBasePSN(0);
    fh.SetISN(negOp);
    fh.SetHasFirst(false);
    fh.SetHasLast(false);
    fh.SetLastRel(0);
    fh.SetLastLength(0);
    std::vector<uint32_t> empty;
    fh.SetRecipe(empty);
    p->AddHeader(fh);

    // Reverse direction for routing back to the sender
    CustomHeader ch = rxCh;
    std::swap(ch.sip, ch.dip);
    std::swap(ch.udp.sport, ch.udp.dport);
    ch.l3Prot = 0xFA;

    p->AddHeader(ch);

    if (m_node->GetNodeType() == 0)
    {
        m_rdmaEQ->EnqueueHighPrioQ(p);
        m_traceEnqueue(p, 0);
    }
    else
    {
        SwitchSend(0, p, ch);
    }

    DequeueAndTransmit();
}

}  // namespace ns3
