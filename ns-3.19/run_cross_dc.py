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
from datetime import date

# randomID
random.seed(datetime.now())
MAX_RAND_RANGE = 1000000000

# config template
config_template = """TOPOLOGY_FILE config/{topo}.txt
FLOW_FILE config/{flow}.txt

FLOW_INPUT_FILE mix/output/{id}/{id}_in.txt
CNP_OUTPUT_FILE mix/output/{id}/{id}_out_cnp.txt
FCT_OUTPUT_FILE mix/output/{id}/{id}_out_fct.txt
PFC_OUTPUT_FILE mix/output/{id}/{id}_out_pfc.txt
QLEN_MON_FILE mix/output/{id}/{id}_out_qlen.txt
VOQ_MON_FILE mix/output/{id}/{id}_out_voq.txt
VOQ_MON_DETAIL_FILE mix/output/{id}/{id}_out_voq_per_dst.txt
UPLINK_MON_FILE mix/output/{id}/{id}_out_uplink.txt
CONN_MON_FILE mix/output/{id}/{id}_out_conn.txt
EST_ERROR_MON_FILE mix/output/{id}/{id}_out_est_error.txt

QLEN_MON_START {qlen_mon_start}
QLEN_MON_END {qlen_mon_end}
SW_MONITORING_INTERVAL {sw_monitoring_interval}

FLOWGEN_START_TIME {flowgen_start_time}
FLOWGEN_STOP_TIME {flowgen_stop_time}
BUFFER_SIZE {buffer_size}
DCI_BUFFER_SIZE {dci_buffer_size}
DCI_SWITCH_IDS {dci_switch_ids}

CC_MODE {cc_mode}
LB_MODE {lb_mode}
ENABLE_PFC {enabled_pfc}
ENABLE_IRN {enabled_irn}

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

ERROR_RATE_PER_LINK 0.0000
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

topo2bdp = {
    "cross_dc_k4_dc2_os2": 208000,  # cross-dc -> 100G internal, 400G DCI
    "cross_dc_k4_dc3_os2": 312000,  # cross-dc -> 100G internal, 400G DCI
}

FLOWGEN_DEFAULT_TIME = 2.0  # see /traffic_gen/traffic_gen.py::base_t

def main():
    # make directory if not exists
    isExist = os.path.exists("mix/output")
    if not isExist:
        os.makedirs("mix/output")
        print("The new directory is created - mix/output/")

    parser = argparse.ArgumentParser(description='run simulation')
    # 基本参数
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

    # 跨数据中心参数
    parser.add_argument('--traffic-type', dest='traffic_type', action='store',
                      default='mixed', help="traffic type: mixed/intra_only (default: mixed)")
    parser.add_argument('--k-fat', dest='k_fat', action='store',
                      type=int, default=4, help="Fat-tree K parameter (default: 4)")
    parser.add_argument('--num-dc', dest='num_dc', action='store',
                      type=int, default=2, help="Number of datacenters (default: 2)")
    parser.add_argument('--dci-buffer', dest='dci_buffer', action='store',
                      type=int, default=128, help="DCI switch buffer size (MB) (default: 128)")
    parser.add_argument('--intra-load', dest='intra_load', action='store',
                      type=float, default=0.5, help="Intra-datacenter load (default: 0.5)")
    parser.add_argument('--inter-load', dest='inter_load', action='store',
                      type=float, default=0.2, help="Inter-datacenter load (default: 0.2)")
    parser.add_argument('--intra-bw', dest='intra_bw', action='store',
                      type=int, default=100, help="Intra-datacenter bandwidth (Gbps) (default: 100)")
    parser.add_argument('--inter-bw', dest='inter_bw', action='store',
                      type=int, default=400, help="Inter-datacenter bandwidth (Gbps) (default: 400)")

    args = parser.parse_args()

    # make running ID of this config
    isExist = True
    config_ID = 0
    while (isExist):
        config_ID = str(random.randrange(MAX_RAND_RANGE))
        isExist = os.path.exists(f"mix/output/{config_ID}")

    # 创建必要的目录
    os.makedirs(f"mix/output/{config_ID}")
    os.makedirs("config", exist_ok=True)

    # input parameters
    cc_mode = cc_modes[args.cc]
    lb_mode = lb_modes[args.lb]
    enabled_pfc = args.pfc
    enabled_irn = args.irn
    buffer = args.buffer
    dci_buffer = args.dci_buffer
    enforce_win = args.enforce_win
    cdf = args.cdf
    flowgen_start_time = FLOWGEN_DEFAULT_TIME
    flowgen_stop_time = flowgen_start_time + args.simul_time
    sw_monitoring_interval = args.sw_monitoring_interval

    # 生成拓扑文件
    print("Generating topology...")
    topo = f"cross_dc_k{args.k_fat}_dc{args.num_dc}_os2"
    topo_file = f"config/{topo}.txt"
    
    # 如果拓扑文件不存在，才生成
    if not os.path.exists(topo_file):
        os.system(f"python3 config/cross_dc_topology_gen.py {args.k_fat} 2 {args.num_dc} {args.intra_bw} 0.01 {args.inter_bw} 4")
        print(f"Topology file generated: {topo_file}")
    else:
        print(f"Using existing topology file: {topo_file}")

    # 从拓扑文件中获取DCI交换机ID
    dci_switch_ids = []
    
    if os.path.exists(topo_file):
        # 读取最后一行，获取DCI交换机ID
        with open(topo_file, 'r') as f:
            lines = f.readlines()
            if lines:  # 确保文件不为空
                last_line = lines[-1].strip()
                # 最后一行格式应该是: id1 id2 400Gbps 4000000ns 0.0
                parts = last_line.split()
                if len(parts) >= 2:
                    dci_switch_ids.append(int(parts[0]))  # 第一个DC的DCI交换机ID
                    dci_switch_ids.append(int(parts[1]))  # 第二个DC的DCI交换机ID
                    print(f"Found DCI switch IDs from topology file: {dci_switch_ids}")
                else:
                    print("Warning: Could not parse DCI switch IDs from topology file")
            else:
                print("Warning: Topology file is empty")
    
    # 如果从拓扑文件中无法获取DCI交换机ID，则使用默认值
    if not dci_switch_ids and args.num_dc == 2:
        dci_switch_ids = [52, 105]  # 对于k=4, num_dc=2的情况，DCI交换机ID是52和105
        print(f"Using default DCI switch IDs: {dci_switch_ids}")

    # Sanity checks
    if (args.cc == "timely" or args.cc == "hpcc") and args.lb == "conweave":
        raise Exception("CONFIG ERROR : ConWeave currently does not support RTT-based protocols.")
    if enabled_irn == 1 and enabled_pfc == 1:
        raise Exception("CONFIG ERROR : If IRN is turn-on, then you should turn off PFC.")
    if enabled_irn == 0 and enabled_pfc == 0:
        raise Exception("CONFIG ERROR : Either IRN or PFC should be true.")
    if args.simul_time < 0.005:
        raise Exception("CONFIG ERROR : Runtime must be larger than 5ms.")

    # 生成流量文件
    print("Generating traffic...")
    # 为不同的流量类型生成不同的文件名
    flow_suffix = "mixed" if args.traffic_type == "mixed" else "intra_only"
    flow_file = f"{topo}_{flow_suffix}_flow.txt"
    flow_path = f"config/{flow_file}"
    
    # 如果流量文件不存在，才生成
    if not os.path.exists(flow_path):
        if args.traffic_type == "mixed":
            os.system(f"python3 traffic_gen/cross_dc_traffic_gen.py -k {args.k_fat} -d {args.num_dc} --intra-load {args.intra_load} --inter-load {args.inter_load} --intra-bw {args.intra_bw} --inter-bw {args.inter_bw} -t {args.simul_time} -c traffic_gen/AliStorage2019.txt -o {flow_path}")
        else:  # intra_only
            os.system(f"python3 traffic_gen/intra_dc_traffic_gen.py -k {args.k_fat} -d {args.num_dc} --intra-load {args.intra_load} --intra-bw {args.intra_bw} -t {args.simul_time} -c traffic_gen/AliStorage2019.txt -o {flow_path}")
        print(f"Traffic file generated: {flow_path}")
    else:
        print(f"Using existing traffic file: {flow_path}")

    # 配置文件路径
    config_name = f"mix/output/{config_ID}/config.txt"
    print(f"Config filename: {config_name}")

    # window settings
    has_win = 0
    var_win = 0
    if (cc_mode == 3 or cc_mode == 8 or enforce_win == 1):
        has_win = 1
        var_win = 1
        if enforce_win == 1:
            print("### INFO: Enforced to use window scheme! ###")

    # record to history
    simulday = datetime.now().strftime("%m/%d/%y")
    with open("./mix/.history", "a") as history:
        history.write("{simulday},{config_ID},{cc_mode},{lb_mode},{pfc},{irn},{has_win},{var_win},{topo},{cdf},{time}\n".format(
            simulday=simulday,
            config_ID=config_ID,
            cc_mode=cc_mode,
            lb_mode=lb_mode,
            pfc=enabled_pfc,
            irn=enabled_irn,
            has_win=has_win,
            var_win=var_win,
            topo=topo,
            cdf=cdf,
            time=args.simul_time,
        ))

    # BDP calculation
    if topo2bdp.get(topo) == None:
        print("ERROR - topology is not registered in run.py!!", flush=True)
        return
    bdp = int(topo2bdp[topo])
    print("1BDP = {}".format(bdp))

    # DCQCN parameters
    kmax_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        100*1000000000, 400,
        200*1000000000, 400,
        400*1000000000, 400,
        800*1000000000, 400,
        1000*1000000000, 400,
        1600*1000000000, 400)
    kmin_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        100*1000000000, 100,
        200*1000000000, 100,
        400*1000000000, 100,
        800*1000000000, 100,
        1000*1000000000, 100,
        1600*1000000000, 100)
    pmax_map = "6 %d %d %d %d %d %.2f %d %.2f %d %.2f %d %.2f" % (
        100*1000000000, 0.2,
        200*1000000000, 0.2,
        400*1000000000, 0.2,
        800*1000000000, 0.2,
        1000*1000000000, 0.2,
        1600*1000000000, 0.2)

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
            load=float(args.intra_load) if args.traffic_type == "intra_only" else float(args.intra_load) + float(args.inter_load)
        )
    else:
        print("unknown cc:{}".format(args.cc))
        return

    with open(config_name, "w") as file:
        file.write(config)

    # run simulation
    print("Running simulation...")
    output_log = config_name.replace(".txt", ".log")
    run_command = "./waf --run 'scratch/cross_dc {config_name}' > {output_log} 2>&1".format(
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

    # analyze FCT
    fct_analysis_time_limit_begin = int(flowgen_start_time * 1e9) + int(0.005 * 1e9)
    fct_analysistime_limit_end = int(flowgen_stop_time * 1e9) + int(0.05 * 1e9)

    print("Analyzing output FCT...")
    os.system("python3 fctAnalysis.py -id {config_ID} -dir {dir} -bdp {bdp} -sT {fct_analysis_time_limit_begin} -fT {fct_analysistime_limit_end} > /dev/null 2>&1".format(
        config_ID=config_ID,
        dir=os.getcwd(),
        bdp=bdp,
        fct_analysis_time_limit_begin=fct_analysis_time_limit_begin,
        fct_analysistime_limit_end=fct_analysistime_limit_end
    ))

    # analyze queue (ConWeave)
    if lb_mode == 9:
        queue_analysis_time_limit_begin = int(flowgen_start_time * 1e9) + int(0.005 * 1e9)
        queue_analysistime_limit_end = int(flowgen_stop_time * 1e9)
        print("Analyzing output Queue...")
        os.system("python3 queueAnalysis.py -id {config_ID} -dir {dir} -sT {queue_analysis_time_limit_begin} -fT {queue_analysistime_limit_end} > /dev/null 2>&1".format(
            config_ID=config_ID,
            dir=os.getcwd(),
            queue_analysis_time_limit_begin=queue_analysis_time_limit_begin,
            queue_analysistime_limit_end=queue_analysistime_limit_end
        ))

    print("\n\n============== Done ============== ")

if __name__ == "__main__":
    main() 