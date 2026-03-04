#!/usr/bin/python3
from genericpath import exists
import subprocess
import os
import time
from xmlrpc.client import boolean
import numpy as np
import copy
import shutil
import random
from datetime import datetime
import sys
import os
import argparse
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tools', 'topo2bdp'))
from topo_bdp import get_bdp
from datetime import date

# randomID
# Python 3.12+ 的 random.seed 不再接受 datetime 对象，使用时间戳整数保证兼容性
random.seed(int(datetime.now().timestamp() * 1e6))
MAX_RAND_RANGE = 1000000000

# config template
config_template = """TOPOLOGY_FILE config/{topo}.txt
FLOW_FILE config/{flow}.txt

FLOW_INPUT_FILE mix/output/{id}/{id}_in.txt
CNP_OUTPUT_FILE mix/output/{id}/{id}_out_cnp.txt
FCT_OUTPUT_FILE mix/output/{id}/{id}_out_fct.txt
PFC_OUTPUT_FILE mix/output/{id}/{id}_out_pfc.txt
DROP_MON_FILE mix/output/{id}/{id}_out_drop.txt
QLEN_MON_FILE mix/output/{id}/{id}_out_qlen.txt
VOQ_MON_FILE mix/output/{id}/{id}_out_voq.txt
VOQ_MON_DETAIL_FILE mix/output/{id}/{id}_out_voq_per_dst.txt
UPLINK_MON_FILE mix/output/{id}/{id}_out_uplink.txt
CONN_MON_FILE mix/output/{id}/{id}_out_conn.txt
EST_ERROR_MON_FILE mix/output/{id}/{id}_out_est_error.txt
RTO_MON_FILE mix/output/{id}/{id}_out_rto.txt
FEC_MON_FILE mix/output/{id}/{id}_out_fec.txt
FEC_STATE_MON_FILE mix/output/{id}/{id}_out_fec_state.txt

QLEN_MON_START {qlen_mon_start}
QLEN_MON_END {qlen_mon_end}
SW_MONITORING_INTERVAL {sw_monitoring_interval}

FLOWGEN_START_TIME {flowgen_start_time}
FLOWGEN_STOP_TIME {flowgen_stop_time}
BUFFER_SIZE {buffer_size}
DCI_BUFFER_SIZE {dci_buffer_size}
DCI_SWITCH_IDS {dci_switch_ids}
ENABLE_EDGE_CNP {enable_edge_cnp}
EDGE_CNP_INTERVAL 4

CC_MODE {cc_mode}
LB_MODE {lb_mode}
ENABLE_PFC {enabled_pfc}
ENABLE_IRN {enabled_irn}

FEC_ENABLED {fec_enabled}
FEC_BLOCK_SIZE {fec_block_size}
FEC_INTERLEAVING_DEPTH {fec_interleaving_depth}
FEC_TAIL_FLUSH_MIN_PKTS {fec_tail_flush_min_pkts}
FEC_MAX_REPAIRS_PER_BLOCK {fec_max_repairs_per_block}
FEC_REPAIR_PACING_ENABLED {fec_repair_pacing_enabled}
FEC_REPAIR_RATE_RATIO {fec_repair_rate_ratio}
FEC_REPAIR_BURST_BYTES {fec_repair_burst_bytes}
FEC_REPAIR_MAX_BACKLOG_BYTES {fec_repair_max_backlog_bytes}
FEC_LOG_ENABLED {fec_log_enabled}
FEC_STATE_MON_ENABLED {fec_state_mon_enabled}
FEC_STATE_MON_INTERVAL_NS {fec_state_mon_interval_ns}

CONWEAVE_TX_EXPIRY_TIME {cwh_tx_expiry_time}
CONWEAVE_REPLY_TIMEOUT_EXTRA {cwh_extra_reply_deadline}
CONWEAVE_PATH_PAUSE_TIME {cwh_path_pause_time}
CONWEAVE_EXTRA_VOQ_FLUSH_TIME {cwh_extra_voq_flush_time}
CONWEAVE_DEFAULT_VOQ_WAITING_TIME {cwh_default_voq_waiting_time}

ALPHA_RESUME_INTERVAL 1
RATE_DECREASE_INTERVAL 4
CLAMP_TARGET_RATE 0
RP_TIMER 300 
FAST_RECOVERY_TIMES 1
EWMA_GAIN {ewma_gain}
RATE_AI {ai}Mb/s
RATE_HAI {hai}Mb/s
MIN_RATE 100Mb/s
DCTCP_RATE_AI {dctcp_ai}Mb/s

ERROR_RATE_PER_LINK {error_rate_per_link}
L2_CHUNK_SIZE 4000
L2_ACK_INTERVAL 1
L2_BACK_TO_ZERO 0

RATE_BOUND 1
HAS_WIN {has_win}
VAR_WIN {var_win}
FAST_REACT {fast_react}
MI_THRESH {mi}
INT_MULTI {int_multi}
GLOBAL_T 1
U_TARGET 0.95
MULTI_RATE 0
SAMPLE_FEEDBACK 0

ENABLE_QCN 1
USE_DYNAMIC_PFC_THRESHOLD 1
PACKET_PAYLOAD_SIZE 1000

LINK_DOWN 0 0 0
KMAX_MAP {kmax_map}
KMIN_MAP {kmin_map}
PMAX_MAP {pmax_map}
LOAD {load}
RANDOM_SEED 1
"""

# LB/CC mode matching
cc_modes = {
    "dcqcn": 1,
    "hpcc": 3,
    "timely": 7,
    "dctcp": 8,
}

lb_modes = {
    "fecmp": 0,
    "drill": 2,
    "conga": 3,
    "letflow": 6,
    "conweave": 9,
}

# Legacy topology mapping moved to topo_bdp.py

FLOWGEN_DEFAULT_TIME = 2.0  # see /traffic_gen/traffic_gen.py::base_t

def main():
    # make directory if not exists
    isExist = os.path.exists(os.getcwd() + "/mix/output/")
    if not isExist:
        os.makedirs(os.getcwd() + "/mix/output/")
        print("The new directory is created - {}".format(os.getcwd() + "/mix/output/"))

    parser = argparse.ArgumentParser(description='run simulation')
    # primary parameters
    parser.add_argument('--cc', dest='cc', action='store',
                        default='dcqcn', help="hpcc/dcqcn/timely/dctcp (default: dcqcn)")
    parser.add_argument('--lb', dest='lb', action='store',
                        default='fecmp', help="fecmp/drill/conga/letflow/conweave (default: fecmp)")
    parser.add_argument('--pfc', dest='pfc', action='store',
                        type=int, default=1, help="enable PFC (default: 1)")
    parser.add_argument('--irn', dest='irn', action='store',
                        type=int, default=0, help="enable IRN (default: 0)")
    parser.add_argument('--simul_time', dest='simul_time', action='store',
                        type=float, default=0.01, help="traffic time to simulate (up to 3 seconds) (default: 0.01)")
    parser.add_argument('--buffer', dest="buffer", action='store',
                        type=int, default=16, help="the switch buffer size (MB) (default: 16)")
    parser.add_argument('--cdf', dest='cdf', action='store',
                        default='AliStorage2019', help="the name of the cdf file (default: AliStorage2019)")
    parser.add_argument('--enforce_win', dest='enforce_win', action='store',
                        type=int, default=0, help="enforce to use window scheme (default: 0)")
    parser.add_argument('--sw_monitoring_interval', dest='sw_monitoring_interval', action='store',
                        type=int, default=10000, help="interval of sampling statistics for queue status (default: 10000ns)")
    parser.add_argument('--traffic-type', dest='traffic_type', action='store',
                      default='mixed', help="traffic type: mixed/intra_only (default: mixed)")
    parser.add_argument('--k-fat', dest='k_fat', action='store',
                      type=int, default=4, help="Fat-tree K parameter (default: 4)")
    parser.add_argument('--num-dc', dest='num_dc', action='store',
                      type=int, default=2, help="Number of datacenters (default: 2)")
    parser.add_argument('--dci-buffer', dest='dci_buffer', action='store',
                      type=int, default=128, help="DCI switch buffer size (MB) (default: 128)")
    parser.add_argument('--enable-edge-cnp', dest='enable_edge_cnp', action='store',
                        type=int, default=0, help="enable edge CNP (default: 0)")
    parser.add_argument('--intra-load', dest='intra_load', action='store',
                      type=float, default=0.5, help="Intra-datacenter load (default: 0.5)")
    parser.add_argument('--inter-load', dest='inter_load', action='store',
                      type=float, default=0.2, help="Inter-datacenter load (default: 0.2)")
    parser.add_argument('--intra-bw', dest='intra_bw', action='store',
                      type=int, default=100, help="Intra-datacenter bandwidth (Gbps) (default: 100)")
    parser.add_argument('--inter-bw', dest='inter_bw', action='store',
                      type=int, default=400, help="Inter-datacenter bandwidth (Gbps) (default: 400)")
    parser.add_argument('--intra-error', dest='intra_error', action='store',
                      type=float, default=0.0, help="Intra-datacenter link error rate (default: 0.0)")
    parser.add_argument('--inter-error', dest='inter_error', action='store',
                      type=float, default=0.0, help="Inter-datacenter link error rate (default: 0.0)")
    parser.add_argument('--flow-scale', dest='flow_scale', action='store',
                      type=float, default=1.0, help="Flow scale factor (larger values = fewer flows) (default: 1.0)")
    parser.add_argument('--intra-latency', dest='intra_latency', action='store',
                      type=float, default=1000, help="Intra-datacenter link latency (ns) (default: 1000 - 1us)")
    parser.add_argument('--inter-latency', dest='inter_latency', action='store',
                      type=float, default=400000, help="Inter-datacenter link latency (ns) (default: 400000 - 400us)")
    parser.add_argument('--fec-enabled', dest='fec_enabled', action='store',
                      type=int, default=1, help="Enable FEC (default: 1)")
    parser.add_argument('--fec-block-size', dest='fec_block_size', action='store',
                      type=int, default=64, help="FEC block size r (default: 64)")
    parser.add_argument('--fec-interleaving-depth', dest='fec_interleaving_depth', action='store',
                      type=int, default=8, help="FEC interleaving depth c (default: 8)")
    parser.add_argument('--fec-tail-flush-min-pkts', dest='fec_tail_flush_min_pkts', action='store',
                      type=int, default=8, help="Tail flush min data pkts (default: 8)")
    parser.add_argument('--fec-max-repairs-per-block', dest='fec_max_repairs_per_block', action='store',
                      type=int, default=0, help="Max repairs per block (0=unlimited, default: 0)")
    parser.add_argument('--fec-repair-pacing-enabled', dest='fec_repair_pacing_enabled', action='store',
                      type=int, default=1, help="Enable repair injection pacing (default: 1)")
    parser.add_argument('--fec-repair-rate-ratio', dest='fec_repair_rate_ratio', action='store',
                      type=float, default=0.0, help="Repair pacing ratio (0=auto c/r, default: 0.0)")
    parser.add_argument('--fec-repair-burst-bytes', dest='fec_repair_burst_bytes', action='store',
                      type=int, default=65536, help="Repair pacing burst bytes (default: 65536)")
    parser.add_argument('--fec-repair-max-backlog-bytes', dest='fec_repair_max_backlog_bytes', action='store',
                      type=int, default=8 * 1024 * 1024, help="Max pending repair backlog bytes (default: 8MiB)")
    parser.add_argument('--fec-log-enabled', dest='fec_log_enabled', action='store',
                      type=int, default=1, help="Enable FEC debug log file output (default: 1)")
    parser.add_argument('--fec-state-mon-enabled', dest='fec_state_mon_enabled', action='store',
                      type=int, default=0, help="Enable FEC state monitor output (default: 0)")
    parser.add_argument('--fec-state-mon-interval-ns', dest='fec_state_mon_interval_ns', action='store',
                      type=int, default=10000000, help="FEC state monitor interval (ns) (default: 10000000)")
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                      help="Only generate topology/traffic/config then exit (no waf run / analysis)")
    parser.add_argument('--minimal-flows', dest='minimal_flows', action='store',
                      type=int, default=0,
                      help="Generate a tiny flow file with N flows (skips traffic generators). Useful for tests.")

    args = parser.parse_args()

    # make running ID of this config
    isExist = True
    config_ID = 0
    while (isExist):
        config_ID = str(random.randrange(MAX_RAND_RANGE))
        isExist = os.path.exists(os.getcwd() + "/mix/output/" + config_ID)

    # make necessary directories
    os.makedirs(os.getcwd() + "/mix/output/" + config_ID)
    os.makedirs("config", exist_ok=True)

    # input parameters
    cc_mode = cc_modes[args.cc]
    lb_mode = lb_modes[args.lb]
    enabled_pfc = int(args.pfc)
    enabled_irn = int(args.irn)
    buffer = args.buffer
    dci_buffer = args.dci_buffer
    enable_edge_cnp = int(args.enable_edge_cnp)
    enforce_win = args.enforce_win
    cdf = args.cdf
    flowgen_start_time = FLOWGEN_DEFAULT_TIME
    flowgen_stop_time = flowgen_start_time + args.simul_time
    sw_monitoring_interval = args.sw_monitoring_interval

    # generate topology file
    print("Generating topology...")
    # Generate detailed topology filename with parameters (used for BDP mapping key as well)
    # 统一浮点格式，避免 1000 与 1000.0 在文件名/BDP key 上不一致
    intra_lat_str = str(float(args.intra_latency))
    inter_lat_str = str(float(args.inter_latency))
    topo_detailed = (
        f"cross_dc_k{args.k_fat}_dc{args.num_dc}_os2_"
        f"ib{args.intra_bw}_il{intra_lat_str}_"
        f"eb{args.inter_bw}_el{inter_lat_str}_"
        f"ie{args.intra_error}_ee{args.inter_error}"
    )
    topo_file = f"config/{topo_detailed}.txt"
    
    if not os.path.exists(topo_file):
        os.system(f"python3 ../tools/topology_gen/cross_dc_topology_gen.py {args.k_fat} 2 {args.num_dc} {args.intra_bw} {args.intra_latency} {args.inter_bw} {args.inter_latency} {args.intra_error} {args.inter_error}")
        print(f"Topology file generated: {topo_file}")
    else:
        print(f"Using existing topology file: {topo_file}")
    
    # Use detailed topology name as BDP key (parameters affect BDP)
    topo = topo_detailed
    # Simple topology name (for traffic/trace filenames)
    topo_simple = f"cross_dc_k{args.k_fat}_dc{args.num_dc}_os2"

    # 计算 DCI switch IDs（避免从拓扑文件“最后一行”误解析）
    # 注意：跨 DC 拓扑生成器按每个 DC 固定追加 1 个 DCI switch。
    oversubscript = 2
    n_core = int(args.k_fat / 2 * args.k_fat / 2)
    n_pod = args.k_fat
    n_agg_per_pod = int(args.k_fat / 2)
    n_tor_per_pod = int(args.k_fat / 2)
    n_server_per_tor = int(args.k_fat / 2 * oversubscript)
    n_server_per_pod = n_server_per_tor * n_tor_per_pod
    n_server_per_dc = n_server_per_pod * n_pod
    n_tor_per_dc = n_tor_per_pod * n_pod
    n_agg_per_dc = n_agg_per_pod * n_pod
    n_core_per_dc = n_core
    n_switch_per_dc = n_tor_per_dc + n_agg_per_dc + n_core_per_dc
    n_dci_per_dc = 1

    dci_switch_ids = []
    for dc_id in range(args.num_dc):
        dc_offset = dc_id * (n_server_per_dc + n_switch_per_dc + n_dci_per_dc)
        dci_switch_id = dc_offset + n_server_per_dc + n_switch_per_dc
        dci_switch_ids.append(dci_switch_id)
    print(f"Computed DCI switch IDs: {dci_switch_ids}")

    # Sanity checks
    if (args.cc == "timely" or args.cc == "hpcc") and args.lb == "conweave":
        raise Exception("CONFIG ERROR : ConWeave currently does not support RTT-based protocols.")
    if enabled_irn == 1 and enabled_pfc == 1:
        raise Exception("CONFIG ERROR : If IRN is turn-on, then you should turn off PFC.")
    if enabled_irn == 0 and enabled_pfc == 0:
        raise Exception("CONFIG ERROR : Either IRN or PFC should be true.")
    if args.simul_time < 0.005:
        raise Exception("CONFIG ERROR : Runtime must be larger than 5ms.")

    # generate traffic file
    print("Generating traffic...")
    # generate different file names for different traffic types (simple topo name; no link params)
    flow_suffix = "mixed" if args.traffic_type == "mixed" else "intra_only"
    flow_file = f"{topo_simple}_{flow_suffix}_flow.txt"
    flow_path = f"config/{flow_file}"
    
    if args.minimal_flows > 0:
        # 生成最小可用流量文件（用于测试/冒烟检查），避免生成大量流
        print(f"Generating minimal traffic file with {args.minimal_flows} flows: {flow_path}")

        oversubscript = 2
        n_core = int(args.k_fat / 2 * args.k_fat / 2)
        n_pod = args.k_fat
        n_agg_per_pod = int(args.k_fat / 2)
        n_tor_per_pod = int(args.k_fat / 2)
        n_server_per_tor = int(args.k_fat / 2 * oversubscript)
        n_server_per_pod = n_server_per_tor * n_tor_per_pod
        n_server_per_dc = n_server_per_pod * n_pod
        n_tor_per_dc = n_tor_per_pod * n_pod
        n_agg_per_dc = n_agg_per_pod * n_pod
        n_core_per_dc = n_core
        n_switch_per_dc = n_tor_per_dc + n_agg_per_dc + n_core_per_dc
        n_dci_per_dc = 1

        def server_id(dc_id: int, server_idx: int) -> int:
            dc_offset = dc_id * (n_server_per_dc + n_switch_per_dc + n_dci_per_dc)
            return dc_offset + server_idx

        n_flow = int(args.minimal_flows)
        t0 = FLOWGEN_DEFAULT_TIME
        dt = 1e-6
        with open(flow_path, "w") as f:
            f.write(f"{n_flow}\n")
            for i in range(n_flow):
                pg = 3
                size = 1000
                t = t0 + i * dt

                if args.traffic_type == "mixed" and (i % 2 == 1) and args.num_dc >= 2:
                    # inter-DC
                    src_dc = 0
                    dst_dc = 1
                    src = server_id(src_dc, i % n_server_per_dc)
                    dst = server_id(dst_dc, (i + 1) % n_server_per_dc)
                else:
                    # intra-DC（若 intra_only，则全部走这里）
                    dc = 0
                    src = server_id(dc, i % n_server_per_dc)
                    dst = server_id(dc, (i + 1) % n_server_per_dc)

                f.write(f"{src} {dst} {pg} {size} {t:.9f}\n")
        print(f"Minimal traffic file generated: {flow_path}")
    else:
        if not os.path.exists(flow_path):
            # traffic_gen moved to tools/traffic_gen at repo root; simulation/ is one level deeper
            gen_root = "../tools/traffic_gen"
            if args.traffic_type == "mixed":
                os.system(f"python3 {gen_root}/cross_dc_traffic_gen.py -k {args.k_fat} -d {args.num_dc} --intra-load {args.intra_load} --inter-load {args.inter_load} --intra-bw {args.intra_bw} --inter-bw {args.inter_bw} -t {args.simul_time} -c {gen_root}/AliStorage2019.txt -o {flow_path} --flow-scale {args.flow_scale}")
            else:  # intra_only
                os.system(f"python3 {gen_root}/intra_dc_traffic_gen.py -k {args.k_fat} -d {args.num_dc} --intra-load {args.intra_load} --intra-bw {args.intra_bw} -t {args.simul_time} -c {gen_root}/AliStorage2019.txt -o {flow_path} --flow-scale {args.flow_scale}")
            print(f"Traffic file generated: {flow_path}")
        else:
            print(f"Using existing traffic file: {flow_path}")

    # config file path
    config_name = os.getcwd() + "/mix/output/" + config_ID + "/config.txt"
    print("Config filename: {}".format(config_name))

    # window settings
    has_win = 0
    var_win = 0
    if (cc_mode == 3 or cc_mode == 8 or enforce_win == 1):  # HPCC or DCTCP or enforcement
        has_win = 1
        var_win = 1
        if enforce_win == 1:
            print("### INFO: Enforced to use window scheme! ###")

    # ConWeave parameters
    if (lb_mode == 9):  # ConWeave
        cwh_extra_reply_deadline = 4  # 4us, NOTE: this is "extra" term to base RTT
        cwh_path_pause_time = 16  # 8us (K_min) or 16us
        cwh_extra_voq_flush_time = 16
        cwh_default_voq_waiting_time = 300
        cwh_tx_expiry_time = 1000  # 1ms
    else:
        # Default ConWeave parameters (not used)
        cwh_extra_reply_deadline = 4
        cwh_path_pause_time = 16
        cwh_extra_voq_flush_time = 64
        cwh_default_voq_waiting_time = 400
        cwh_tx_expiry_time = 1000

    # record to history
    simulday = datetime.now().strftime("%m/%d/%y")
    with open("./mix/.history", "a") as history:
        history.write("{simulday},{config_ID},{cc_mode},{lb_mode},{cwh_tx_expiry_time},{cwh_extra_reply_deadline},{cwh_path_pause_time},{cwh_extra_voq_flush_time},{cwh_default_voq_waiting_time},{pfc},{irn},{has_win},{var_win},{topo},{bw},{cdf},{load},{time}\n".format(
            simulday=simulday,
            config_ID=config_ID,
            cc_mode=cc_mode,
            lb_mode=lb_mode,
            cwh_tx_expiry_time=cwh_tx_expiry_time,
            cwh_extra_reply_deadline=cwh_extra_reply_deadline,
            cwh_path_pause_time=cwh_path_pause_time,
            cwh_extra_voq_flush_time=cwh_extra_voq_flush_time,
            cwh_default_voq_waiting_time=cwh_default_voq_waiting_time,
            pfc=enabled_pfc,
            irn=enabled_irn,
            has_win=has_win,
            var_win=var_win,
            topo=topo,
            bw=args.intra_bw,
            cdf=cdf,
            load=float(args.intra_load) if args.traffic_type == "intra_only" else float(args.intra_load) + float(args.inter_load),
            time=args.simul_time,
        ))

    # dry-run 只需要验证“文件/配置是否正确生成”，不应阻塞在 BDP 映射表上
    if args.dry_run:
        bdp = 0
    else:
        # Lookup BDP via shared topo2bdp utility using detailed name; no Python-side computation
        bdp_val = get_bdp(topo)
        if bdp_val is None:
            print(f"ERROR - BDP not found for topology: {topo}. Please add it to tools/topo2bdp/topo_bdp.txt")
            return
        bdp = int(bdp_val)
        print("1BDP = {}".format(bdp))

    # DCQCN parameters
    kmax_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        args.intra_bw*200000000, 400, 
        args.intra_bw*500000000, 400, 
        args.intra_bw*1000000000, 400, 
        args.intra_bw*2*1000000000, 400, 
        args.intra_bw*2500000000, 400, 
        args.intra_bw*4*1000000000, 400)
    kmin_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        args.intra_bw*200000000, 100, 
        args.intra_bw*500000000, 100, 
        args.intra_bw*1000000000, 100, 
        args.intra_bw*2*1000000000, 100, 
        args.intra_bw*2500000000, 100, 
        args.intra_bw*4*1000000000, 100)
    pmax_map = "6 %d %d %d %d %d %.2f %d %.2f %d %.2f %d %.2f" % (
        args.intra_bw*200000000, 0.2, 
        args.intra_bw*500000000, 0.2, 
        args.intra_bw*1000000000, 0.2, 
        args.intra_bw*2*1000000000, 0.2, 
        args.intra_bw*2500000000, 0.2, 
        args.intra_bw*4*1000000000, 0.2)

    # queue monitoring
    qlen_mon_start = flowgen_start_time
    qlen_mon_end = flowgen_stop_time

    if (cc_mode == 1):  # DCQCN
        ai = 10 * args.intra_bw / 25
        hai = 25 * args.intra_bw / 25
        dctcp_ai = 1000
        fast_react = 0
        mi = 0
        int_multi = 1
        ewma_gain = 0.00390625

        config = config_template.format(
            id=config_ID,
            topo=topo,
            flow=flow_file.replace(".txt", ""),
            qlen_mon_start=qlen_mon_start,
            qlen_mon_end=qlen_mon_end,
            flowgen_start_time=flowgen_start_time,
            flowgen_stop_time=flowgen_stop_time,
            sw_monitoring_interval=sw_monitoring_interval,
            buffer_size=buffer,
            dci_buffer_size=dci_buffer,
            dci_switch_ids=f"{len(dci_switch_ids)} {' '.join(map(str, dci_switch_ids))}",
            enable_edge_cnp=enable_edge_cnp,
            lb_mode=lb_mode,
            enabled_pfc=enabled_pfc,
            enabled_irn=enabled_irn,
            cc_mode=cc_mode,
            ai=ai,
            hai=hai,
            dctcp_ai=dctcp_ai,
            has_win=has_win,
            var_win=var_win,
            fast_react=fast_react,
            mi=mi,
            int_multi=int_multi,
            ewma_gain=ewma_gain,
            kmax_map=kmax_map,
            kmin_map=kmin_map,
            pmax_map=pmax_map,
            load=float(args.intra_load) if args.traffic_type == "intra_only" else float(args.intra_load) + float(args.inter_load),
            cwh_tx_expiry_time=cwh_tx_expiry_time,
            cwh_extra_reply_deadline=cwh_extra_reply_deadline,
            cwh_path_pause_time=cwh_path_pause_time,
            cwh_extra_voq_flush_time=cwh_extra_voq_flush_time,
            cwh_default_voq_waiting_time=cwh_default_voq_waiting_time,
            # 全局链路错误率仅作为“拓扑未显式指定 error_rate 时”的兜底；
            # 跨 DC 场景的 intra/inter 错误率应由 topology file 的 per-link 字段决定。
            error_rate_per_link=0.0,
            fec_enabled=args.fec_enabled,
            fec_block_size=args.fec_block_size,
            fec_interleaving_depth=args.fec_interleaving_depth,
            fec_tail_flush_min_pkts=args.fec_tail_flush_min_pkts,
            fec_max_repairs_per_block=args.fec_max_repairs_per_block,
            fec_repair_pacing_enabled=args.fec_repair_pacing_enabled,
            fec_repair_rate_ratio=args.fec_repair_rate_ratio,
            fec_repair_burst_bytes=args.fec_repair_burst_bytes,
            fec_repair_max_backlog_bytes=args.fec_repair_max_backlog_bytes,
            fec_log_enabled=args.fec_log_enabled,
            fec_state_mon_enabled=args.fec_state_mon_enabled,
            fec_state_mon_interval_ns=args.fec_state_mon_interval_ns
        )
    else:
        print("unknown cc:{}".format(args.cc))
        return

    with open(config_name, "w") as file:
        file.write(config)

    if args.dry_run:
        print("Dry-run enabled. Generated artifacts:")
        print(f"- Topology: {topo_file}")
        print(f"- Traffic:  {flow_path}")
        print(f"- Config:   {config_name}")
        return

    # run simulation
    print("Running simulation...")
    output_log = config_name.replace(".txt", ".log")
    run_command = "NS_LOG='QbbNetDevice=debug|info:FecDecoder=debug|info' ./waf --run 'scratch/cross_dc {config_name}' > {output_log} 2>&1".format(
        config_name=config_name, output_log=output_log)
    
    with open("./mix/.history", "a") as history:
        history.write(run_command + "\n")
        history.write(
            "./waf --run 'scratch/cross_dc' --command-template='gdb --args %s {config_name}'\n".format(
                config_name=config_name)
        )
        history.write("\n")

    print(run_command)
    os.system(run_command)

    ####################################################
    #                 Analyze the output FCT           #
    ####################################################
    # NOTE: collect data except warm-up and cold-finish period
    fct_analysis_time_limit_begin = int(flowgen_start_time * 1e9) + int(0.005 * 1e9)
    fct_analysistime_limit_end = int(flowgen_stop_time * 1e9) + int(0.05 * 1e9)

    print("Analyzing output FCT...")
    print("python3 fctAnalysis.py -id {config_ID} -dir {dir} -bdp {bdp} -sT {fct_analysis_time_limit_begin} -fT {fct_analysistime_limit_end} > /dev/null 2>&1".format(
        config_ID=config_ID,
        dir=os.getcwd(),
        bdp=bdp,
        fct_analysis_time_limit_begin=fct_analysis_time_limit_begin,
        fct_analysistime_limit_end=fct_analysistime_limit_end
    ))
    os.system("python3 fctAnalysis.py -id {config_ID} -dir {dir} -bdp {bdp} -sT {fct_analysis_time_limit_begin} -fT {fct_analysistime_limit_end} > /dev/null 2>&1".format(
        config_ID=config_ID,
        dir=os.getcwd(),
        bdp=bdp,
        fct_analysis_time_limit_begin=fct_analysis_time_limit_begin,
        fct_analysistime_limit_end=fct_analysistime_limit_end
    ))

    # analyze queue (ConWeave)
    if lb_mode == 9:
        ################################################################
        #             Analyze hardware resource of ConWeave            #
        ################################################################
        # NOTE: collect data except warm-up and cold-finish period
        queue_analysis_time_limit_begin = int(flowgen_start_time * 1e9) + int(0.005 * 1e9)
        queue_analysistime_limit_end = int(flowgen_stop_time * 1e9)
        print("Analyzing output Queue...")
        print("python3 queueAnalysis.py -id {config_ID} -dir {dir} -sT {queue_analysis_time_limit_begin} -fT {queue_analysistime_limit_end} > /dev/null 2>&1".format(
            config_ID=config_ID,
            dir=os.getcwd(),
            queue_analysis_time_limit_begin=queue_analysis_time_limit_begin,
            queue_analysistime_limit_end=queue_analysistime_limit_end
        ))
        os.system("python3 queueAnalysis.py -id {config_ID} -dir {dir} -sT {queue_analysis_time_limit_begin} -fT {queue_analysistime_limit_end} > /dev/null 2>&1".format(
            config_ID=config_ID,
            dir=os.getcwd(),
            queue_analysis_time_limit_begin=queue_analysis_time_limit_begin,
            queue_analysistime_limit_end=queue_analysistime_limit_end,
            monitoringInterval=sw_monitoring_interval
        ))

    print("\n\n============== Done ============== ")

if __name__ == "__main__":
    main() 
