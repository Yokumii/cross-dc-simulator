#!/usr/bin/python3
import subprocess
import os
import time
import random
from datetime import datetime
import sys
import argparse

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

ENABLE_QCN 0
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

# BDP for cross-dc topology with k=4, 2 datacenters, over-subscription=2
topo2bdp = {
    "cross_dc_k4_dc2_os2": 102008250,  # cross-dc -> 100G internal, 100G DCI
}

FLOWGEN_DEFAULT_TIME = 2.0  # see /traffic_gen/traffic_gen.py::base_t

def main():
    # make directory if not exists
    isExist = os.path.exists(os.getcwd() + "/mix/output/")
    if not isExist:
        os.makedirs(os.getcwd() + "/mix/output/")
        print("The new directory is created - {}".format(os.getcwd() + "/mix/output/"))

    parser = argparse.ArgumentParser(description='run collision simulation')
    # primary parameters
    parser.add_option = parser.add_argument
    parser.add_option('--cc', dest='cc', action='store',
                    default='dcqcn', help="hpcc/dcqcn/timely/dctcp (default: dcqcn)")
    parser.add_option('--pfc', dest='pfc', action='store',
                    type=int, default=0, help="enable PFC (default: 0)")
    parser.add_option('--irn', dest='irn', action='store',
                    type=int, default=0, help="enable IRN (default: 0)")
    parser.add_option('--simul_time', dest='simul_time', action='store',
                    type=float, default=0.01, help="traffic time to simulate (default: 0.01)")
    parser.add_option('--buffer', dest="buffer", action='store',
                    type=int, default=4, help="the switch buffer size (MB) (default: 4)")
    parser.add_option('--sw_monitoring_interval', dest='sw_monitoring_interval', action='store',
                    type=int, default=10000, help="interval of sampling statistics for queue status (default: 10000ns)")
    parser.add_option('--dci-buffer', dest='dci_buffer', action='store',
                    type=int, default=32, help="DCI switch buffer size (MB) (default: 32)")
    parser.add_option('--bg-size', dest='bg_size', action='store',
                    type=int, default=100000000, help="Background flow size (bytes) (default: 100000000)")
    parser.add_option('--burst-size', dest='burst_size', action='store',
                    type=int, default=1000000, help="Burst flow size (bytes) (default: 1000000)")

    args = parser.parse_args()

    # make running ID of this config
    isExist = True
    config_ID = 0
    while (isExist):
        config_ID = str(random.randrange(MAX_RAND_RANGE))
        isExist = os.path.exists(os.getcwd() + "/mix/output/" + config_ID)

    # make necessary directories
    os.makedirs(os.getcwd() + "/mix/output/" + config_ID)

    # input parameters
    cc_mode = cc_modes[args.cc]
    lb_mode = lb_modes["fecmp"]  # 使用ECMP负载均衡
    enabled_pfc = int(args.pfc)
    enabled_irn = int(args.irn)
    buffer = args.buffer
    dci_buffer = args.dci_buffer
    flowgen_start_time = FLOWGEN_DEFAULT_TIME
    flowgen_stop_time = flowgen_start_time + args.simul_time
    sw_monitoring_interval = args.sw_monitoring_interval

    # 使用自定义的碰撞流量模型
    topo = "cross_dc_k4_dc2_os2"
    flow = "cross_dc_collision_flow"
    
    # 获取DCI交换机ID
    dci_switch_ids = [52, 105]  # 对于k=4，num_dc=2，DCI交换机ID是52和105
    print(f"Using DCI switch IDs: {dci_switch_ids}")

    # Sanity checks
    if (args.cc == "timely" or args.cc == "hpcc") and lb_mode == lb_modes["conweave"]:
        raise Exception("CONFIG ERROR : ConWeave currently does not support RTT-based protocols.")
    if enabled_irn == 1 and enabled_pfc == 1:
        raise Exception("CONFIG ERROR : If IRN is turn-on, then you should turn off PFC.")
    if enabled_irn == 0 and enabled_pfc == 0:
        raise Exception("CONFIG ERROR : Either IRN or PFC should be true.")
    if args.simul_time < 0.005:
        raise Exception("CONFIG ERROR : Runtime must be larger than 5ms.")

    # config file path
    config_name = os.getcwd() + "/mix/output/" + config_ID + "/config.txt"
    print("Config filename: {}".format(config_name))

    # window settings
    has_win = 0
    var_win = 0
    if (cc_mode == 3 or cc_mode == 8):  # HPCC or DCTCP
        has_win = 1
        var_win = 1

    # ConWeave parameters (default values)
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
            bw=100,
            cdf="custom",
            load=0.7,
            time=args.simul_time,
        ))

    # BDP calculation
    if topo2bdp.get(topo) == None:
        print("ERROR - topology is not registered in run.py!!", flush=True)
        return
    bdp = int(topo2bdp[topo])
    print("1BDP = {}".format(bdp))

    # DCQCN parameters
    intra_bw = 100  # 100Gbps
    kmax_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        intra_bw*200000000, 400, 
        intra_bw*500000000, 400, 
        intra_bw*1000000000, 400, 
        intra_bw*2*1000000000, 400, 
        intra_bw*2500000000, 400, 
        intra_bw*4*1000000000, 400)
    kmin_map = "6 %d %d %d %d %d %d %d %d %d %d %d %d" % (
        intra_bw*200000000, 100, 
        intra_bw*500000000, 100, 
        intra_bw*1000000000, 100, 
        intra_bw*2*1000000000, 100, 
        intra_bw*2500000000, 100, 
        intra_bw*4*1000000000, 100)
    pmax_map = "6 %d %d %d %d %d %.2f %d %.2f %d %.2f %d %.2f" % (
        intra_bw*200000000, 0.2, 
        intra_bw*500000000, 0.2, 
        intra_bw*1000000000, 0.2, 
        intra_bw*2*1000000000, 0.2, 
        intra_bw*2500000000, 0.2, 
        intra_bw*4*1000000000, 0.2)

    # queue monitoring
    qlen_mon_start = flowgen_start_time * 10e9
    qlen_mon_end = flowgen_stop_time * 10e9

    if (cc_mode == 1):  # DCQCN
        ai = 10 * intra_bw / 25
        hai = 25 * intra_bw / 25
        dctcp_ai = 1000
        fast_react = 0
        mi = 0
        int_multi = 1
        ewma_gain = 0.00390625

        config = config_template.format(
            id=config_ID,
            topo=topo,
            flow=flow,
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
            load=0.7,  # 假设负载为70%
            cwh_tx_expiry_time=cwh_tx_expiry_time,
            cwh_extra_reply_deadline=cwh_extra_reply_deadline,
            cwh_path_pause_time=cwh_path_pause_time,
            cwh_extra_voq_flush_time=cwh_extra_voq_flush_time,
            cwh_default_voq_waiting_time=cwh_default_voq_waiting_time
        )
    elif (cc_mode == 3):  # HPCC
        ai = 10 * intra_bw / 25
        hai = 50 * intra_bw / 25
        dctcp_ai = 1000
        fast_react = 1
        mi = 5
        int_multi = 1
        ewma_gain = 0.00390625

        config = config_template.format(
            id=config_ID,
            topo=topo,
            flow=flow,
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
            load=0.7,  # 假设负载为70%
            cwh_tx_expiry_time=cwh_tx_expiry_time,
            cwh_extra_reply_deadline=cwh_extra_reply_deadline,
            cwh_path_pause_time=cwh_path_pause_time,
            cwh_extra_voq_flush_time=cwh_extra_voq_flush_time,
            cwh_default_voq_waiting_time=cwh_default_voq_waiting_time
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

    print("\n\n============== Done ============== ")

if __name__ == "__main__":
    main() 