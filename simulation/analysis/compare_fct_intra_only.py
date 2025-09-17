#!/usr/bin/python3

import subprocess
import os
import sys
import argparse
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as tick
import math
from cycler import cycler

# color configuration
C = [
    'xkcd:blue',
    'xkcd:red',
    'xkcd:green',
    'xkcd:purple',
    'xkcd:orange',
    'xkcd:teal',
]

LS = [
    'solid',
    'dashed',
]

M = [
    'o',
    's',
]

def setup():
    """Called before plotting to set up matplotlib"""

    def lcm(a, b):
        return abs(a*b) // math.gcd(a, b)

    def a(c1, c2):
        """Add cyclers with lcm."""
        l = lcm(len(c1), len(c2))
        c1 = c1 * (l//len(c1))
        c2 = c2 * (l//len(c2))
        return c1 + c2

    def add(*cyclers):
        s = None
        for c in cyclers:
            if s is None:
                s = c
            else:
                s = a(s, c)
        return s

    plt.rc('axes', prop_cycle=(add(cycler(color=C),
                                   cycler(linestyle=LS),
                                   cycler(marker=M))))
    plt.rc('lines', markersize=5)
    plt.rc('legend', handlelength=3, handleheight=1.5, labelspacing=0.25)
    plt.rcParams["font.family"] = "sans"
    plt.rcParams["font.size"] = 10
    plt.rcParams['pdf.fonttype'] = 42
    plt.rcParams['ps.fonttype'] = 42


def getFilePath():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    print("script path: {}".format(dir_path))
    return dir_path

def get_pctl(a, p):
    i = int(len(a) * p)
    return a[i]

def size2str(steps):
    result = []
    for step in steps:
        if step < 10000:
            result.append("{:.1f}K".format(step / 1000))
        elif step < 1000000:
            result.append("{:.0f}K".format(step / 1000))
        else:
            result.append("{:.1f}M".format(step / 1000000))

    return result

def is_intra_dc_flow(src, dst, n_server_per_dc, n_switch_per_dc, n_dci_per_dc):
    """judge if the flow is intra-dc"""
    nodes_per_dc = n_server_per_dc + n_switch_per_dc + n_dci_per_dc
    
    dc_src = src // nodes_per_dc
    dc_dst = dst // nodes_per_dc
    
    return dc_src == dc_dst

def get_steps_from_raw(filename, time_start, time_end, step=5, n_server_per_dc=None, n_switch_per_dc=None, n_dci_per_dc=None, filter_inter_dc=False):
    if filter_inter_dc and (n_server_per_dc is None or n_switch_per_dc is None or n_dci_per_dc is None):
        print("error: when filtering inter-dc flows, the number of servers, switches, and DCI switches must be provided")
        return None
    
    if not filter_inter_dc:
        cmd_slowdown = "cat %s"%(filename)+" | awk '{ if ($6>"+"%d"%time_start+" && $6+$7<"+"%d"%(time_end)+") { slow=$7/$8; print slow<1?1:slow, $5, $1, $2} }' | sort -n -k 2"
    else:
        cmd_slowdown = "cat %s"%(filename)+" | awk '{ if ($6>"+"%d"%time_start+" && $6+$7<"+"%d"%(time_end)+") { slow=$7/$8; print slow<1?1:slow, $5, $1, $2} }'"
    
    output_slowdown = subprocess.check_output(cmd_slowdown, shell=True)
    aa_raw = output_slowdown.decode("utf-8").split('\n')[:-1]
    
    total_flows_before_filter = len(aa_raw)
    
    if filter_inter_dc:
        aa = []
        intra_dc_flows = 0
        inter_dc_flows = 0
        
        for line in aa_raw:
            parts = line.split()
            if len(parts) >= 4:
                slow, size, src, dst = float(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                if is_intra_dc_flow(src, dst, n_server_per_dc, n_switch_per_dc, n_dci_per_dc):
                    aa.append(f"{slow} {size}")
                    intra_dc_flows += 1
                else:
                    inter_dc_flows += 1
        
        # print flow stats
        print(f"flow stats ({os.path.basename(filename)}):")
        print(f"total flows: {total_flows_before_filter}")
        print(f"intra-dc flows: {intra_dc_flows} ({intra_dc_flows/total_flows_before_filter*100:.2f}%)")
        print(f"inter-dc flows: {inter_dc_flows} ({inter_dc_flows/total_flows_before_filter*100:.2f}%)")
        
        # sort by flow size
        aa.sort(key=lambda x: int(x.split()[1]))
    else:
        aa = [' '.join(line.split()[:2]) for line in aa_raw if len(line.split()) >= 2]
        aa.sort(key=lambda x: int(x.split()[1]))
        print(f"flow stats ({os.path.basename(filename)}):")
        print(f"total flows: {total_flows_before_filter}")
    
    nn = len(aa)
    
    if nn == 0:
        print(f"warning: no data in the specified time range for {filename}")
        return None

    # CDF of FCT
    res = [[i/100.] for i in range(0, 100, step)]
    for i in range(0,100,step):
        l = int(i * nn / 100)
        r = int((i+step) * nn / 100)
        fct_size = aa[l:r]
        fct_size = [[float(x.split(" ")[0]), int(x.split(" ")[1])] for x in fct_size]
        fct = sorted(map(lambda x: x[0], fct_size))
        
        if not fct:  # check if it is empty
            res[int(i/step)].append(0)  # flow size
            res[int(i/step)].append(0)  # average FCT
            res[int(i/step)].append(0)  # median FCT
            res[int(i/step)].append(0)  # 95%FCT
            res[int(i/step)].append(0)  # 99%FCT
            res[int(i/step)].append(0)  # 99.9%FCT
            continue
            
        res[int(i/step)].append(fct_size[-1][1]) # flow size
        
        res[int(i/step)].append(sum(fct) / len(fct)) # average FCT
        res[int(i/step)].append(get_pctl(fct, 0.5)) # median FCT
        res[int(i/step)].append(get_pctl(fct, 0.95)) # 95%FCT
        res[int(i/step)].append(get_pctl(fct, 0.99)) # 99%FCT
        res[int(i/step)].append(get_pctl(fct, 0.999)) # 99.9%FCT
    
    result = {"avg": [], "p50": [], "p95": [], "p99": [], "size": [], "total_flows": total_flows_before_filter}
    if filter_inter_dc:
        result["intra_dc_flows"] = intra_dc_flows
        result["inter_dc_flows"] = inter_dc_flows
        
    for item in res:
        result["avg"].append(item[2])
        result["p50"].append(item[3])
        result["p95"].append(item[4])
        result["p99"].append(item[5])
        result["size"].append(item[1])

    return result

def main():
    parser = argparse.ArgumentParser(description='compare the FCT results of intra-dc flows and mixed flows (filter inter-dc flows)')
    parser.add_argument('-intra', dest='intra_id', action='store', required=True, help="intra-dc flow simulation ID")
    parser.add_argument('-mixed', dest='mixed_id', action='store', required=True, help="mixed flow simulation ID")
    parser.add_argument('-k', dest='k_fat', action='store', type=int, default=4, help="Fat-tree K parameter, default=4")
    parser.add_argument('-d', dest='num_dc', action='store', type=int, default=2, help="number of DCs, default=2")
    parser.add_argument('-sT', dest='time_limit_begin', action='store', type=int, default=2005000000, help="only consider flows completed after T, default=2005000000 ns")
    parser.add_argument('-fT', dest='time_limit_end', action='store', type=int, default=10000000000, help="only consider flows completed before T, default=10000000000 ns")
    parser.add_argument('-o', dest='output_dir', action='store', default=None, help="output directory, default=current directory")
    
    args = parser.parse_args()
    time_start = args.time_limit_begin
    time_end = args.time_limit_end
    STEP = 5  # 5% step
    
    intra_id = args.intra_id
    mixed_id = args.mixed_id
    k_fat = args.k_fat
    num_dc = args.num_dc

    n_core = int(k_fat / 2 * k_fat / 2)
    n_pod = k_fat
    n_agg_per_pod = int(k_fat / 2)
    n_tor_per_pod = int(k_fat / 2)
    n_server_per_tor = int(k_fat / 2 * 2)
    n_server_per_pod = n_server_per_tor * n_tor_per_pod
    n_server_per_dc = n_server_per_pod * n_pod

    n_tor_per_dc = n_tor_per_pod * n_pod
    n_agg_per_dc = n_agg_per_pod * n_pod
    n_core_per_dc = n_core
    n_switch_per_dc = n_tor_per_dc + n_agg_per_dc + n_core_per_dc
    n_dci_per_dc = 1
    
    nodes_per_dc = n_server_per_dc + n_switch_per_dc + n_dci_per_dc
    
    file_dir = getFilePath()
    if args.output_dir:
        fig_dir = args.output_dir
    else:
        fig_dir = file_dir
    
    os.makedirs(fig_dir, exist_ok=True)
    
    output_dir = file_dir + "/../mix/output"

    intra_fct_file = f"{output_dir}/{intra_id}/{intra_id}_out_fct.txt"
    mixed_fct_file = f"{output_dir}/{mixed_id}/{mixed_id}_out_fct.txt"
    
    if not os.path.exists(intra_fct_file):
        print(f"error: no intra-dc flow FCT file found: {intra_fct_file}")
        return
    
    if not os.path.exists(mixed_fct_file):
        print(f"error: no mixed flow FCT file found: {mixed_fct_file}")
        return
    
    intra_result = get_steps_from_raw(intra_fct_file, time_start, time_end, STEP)
    
    mixed_result = get_steps_from_raw(mixed_fct_file, time_start, time_end, STEP, n_server_per_dc, n_switch_per_dc, n_dci_per_dc, True)
    
    if not intra_result or not mixed_result:
        print("error: no valid data found in FCT files")
        return
    
    # flow stats summary
    print("\nflow stats summary:")
    print(f"intra-dc flow file: {os.path.basename(intra_fct_file)}")
    print(f"total flows: {intra_result['total_flows']}") 
    
    print(f"mixed flow file: {os.path.basename(mixed_fct_file)}")
    print(f"total flows: {mixed_result['total_flows']}")
    print(f"intra-dc flows: {mixed_result['intra_dc_flows']} ({mixed_result['intra_dc_flows']/mixed_result['total_flows']*100:.2f}%)")
    print(f"inter-dc flows: {mixed_result['inter_dc_flows']} ({mixed_result['inter_dc_flows']/mixed_result['total_flows']*100:.2f}%)")
    
    # save flow stats to file
    stats_file = f"{fig_dir}/flow_stats_intra_{intra_id}_mixed_{mixed_id}.txt"
    with open(stats_file, "w") as f:
        f.write("flow stats summary\n")
        f.write("============\n\n")
        f.write(f"intra-dc flow file: {os.path.basename(intra_fct_file)}\n")
        f.write(f"total flows: {intra_result['total_flows']}\n\n")
        
        f.write(f"mixed flow file: {os.path.basename(mixed_fct_file)}\n")
        f.write(f"total flows: {mixed_result['total_flows']}\n")
        f.write(f"intra-dc flows: {mixed_result['intra_dc_flows']} ({mixed_result['intra_dc_flows']/mixed_result['total_flows']*100:.2f}%)\n")
        f.write(f"inter-dc flows: {mixed_result['inter_dc_flows']} ({mixed_result['inter_dc_flows']/mixed_result['total_flows']*100:.2f}%)\n\n")
         
    print(f"flow stats saved to: {stats_file}")
    
    print(f"\nsegment count:")
    print(f"intra-dc flow: {len(intra_result['avg'])} segments")
    print(f"mixed flow (intra-dc only): {len(mixed_result['avg'])} segments")
    
    print("\nto avoid the last segment being incomplete or abnormal, we will remove the last segment")
    
    segment_count = min(len(intra_result['avg']), len(mixed_result['avg'])) - 1
    
    for key in ['avg', 'p50', 'p95', 'p99', 'size']:
        intra_result[key] = intra_result[key][:segment_count]
        mixed_result[key] = mixed_result[key][:segment_count]
    
    print(f"plot using {segment_count} segments")
    
    xvals = [i for i in range(STEP, STEP * segment_count + 1, STEP)]
    
    # generate average FCT plot
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    ax.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax.set_ylabel("Average FCT Slowdown", fontsize=11.5)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_ticks_position('left')
    ax.xaxis.set_ticks_position('bottom')
    
    ax.plot(xvals, intra_result["avg"], markersize=4.0, linewidth=2.0, label="intra_only")
    ax.plot(xvals, mixed_result["avg"], markersize=4.0, linewidth=2.0, label="mixed(intra_only)")
    
    ax.legend(loc="best", frameon=False, fontsize=12)
    
    ax.tick_params(axis="x", rotation=40)
    ax.set_xticks(([0] + xvals)[::2])
    ax.set_xticklabels(([0] + size2str(intra_result["size"]))[::2], fontsize=10.5)
    ax.set_ylim(bottom=1)
    
    fig.tight_layout()
    ax.grid(which='minor', alpha=0.2)
    ax.grid(which='major', alpha=0.5)
    
    avg_fig_filename = f"{fig_dir}/avg_fct_intra_{intra_id}_mixed_intra_only_{mixed_id}.pdf"
    print(f"save average FCT plot: {avg_fig_filename}")
    plt.savefig(avg_fig_filename, transparent=False, bbox_inches='tight')
    
    # generate p99 FCT plot
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    ax.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax.set_ylabel("p99 FCT Slowdown", fontsize=11.5)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_ticks_position('left')
    ax.xaxis.set_ticks_position('bottom')
    
    ax.plot(xvals, intra_result["p99"], markersize=4.0, linewidth=2.0, label="intra_only")
    ax.plot(xvals, mixed_result["p99"], markersize=4.0, linewidth=2.0, label="mixed(intra_only)")
    
    ax.legend(loc="best", frameon=False, fontsize=12)
    
    ax.tick_params(axis="x", rotation=40)
    ax.set_xticks(([0] + xvals)[::2])
    ax.set_xticklabels(([0] + size2str(intra_result["size"]))[::2], fontsize=10.5)
    ax.set_ylim(bottom=1)
    
    fig.tight_layout()
    ax.grid(which='minor', alpha=0.2)
    ax.grid(which='major', alpha=0.5)
    
    p99_fig_filename = f"{fig_dir}/p99_fct_intra_{intra_id}_mixed_intra_only_{mixed_id}.pdf"
    print(f"save p99 FCT plot: {p99_fig_filename}")
    plt.savefig(p99_fig_filename, transparent=False, bbox_inches='tight')
    
    # generate p50 FCT plot
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    
    ax.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax.set_ylabel("p50 FCT Slowdown", fontsize=11.5)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_ticks_position('left')
    ax.xaxis.set_ticks_position('bottom')
    
    ax.plot(xvals, intra_result["p50"], markersize=4.0, linewidth=2.0, label="intra_only")
    ax.plot(xvals, mixed_result["p50"], markersize=4.0, linewidth=2.0, label="mixed(intra_only)")
    
    ax.legend(loc="best", frameon=False, fontsize=12)
    
    ax.tick_params(axis="x", rotation=40)
    ax.set_xticks(([0] + xvals)[::2])
    ax.set_xticklabels(([0] + size2str(intra_result["size"]))[::2], fontsize=10.5)
    ax.set_ylim(bottom=1)
    
    fig.tight_layout()
    ax.grid(which='minor', alpha=0.2)
    ax.grid(which='major', alpha=0.5)
    
    p50_fig_filename = f"{fig_dir}/p50_fct_intra_{intra_id}_mixed_intra_only_{mixed_id}.pdf"
    print(f"save p50 FCT plot: {p50_fig_filename}")
    plt.savefig(p50_fig_filename, transparent=False, bbox_inches='tight')
    
    # generate combined comparison plot
    fig = plt.figure(figsize=(10, 6))
    
    # average FCT
    ax1 = fig.add_subplot(131)
    ax1.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax1.set_ylabel("Average FCT Slowdown", fontsize=11.5)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.plot(xvals, intra_result["avg"], markersize=3.0, linewidth=2.0, label="intra_only")
    ax1.plot(xvals, mixed_result["avg"], markersize=3.0, linewidth=2.0, label="mixed(intra_only)")
    ax1.legend(loc="best", frameon=False, fontsize=10)
    ax1.tick_params(axis="x", rotation=40)
    ax1.set_xticks(([0] + xvals)[::4])
    ax1.set_xticklabels(([0] + size2str(intra_result["size"]))[::4], fontsize=9)
    ax1.set_ylim(bottom=1)
    ax1.grid(which='major', alpha=0.5)
    ax1.set_title("average FCT", fontsize=12)
    
    # p50 FCT
    ax2 = fig.add_subplot(132)
    ax2.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax2.set_ylabel("p50 FCT Slowdown", fontsize=11.5)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.plot(xvals, intra_result["p50"], markersize=3.0, linewidth=2.0, label="intra_only")
    ax2.plot(xvals, mixed_result["p50"], markersize=3.0, linewidth=2.0, label="mixed(intra_only)")
    ax2.legend(loc="best", frameon=False, fontsize=10)
    ax2.tick_params(axis="x", rotation=40)
    ax2.set_xticks(([0] + xvals)[::4])
    ax2.set_xticklabels(([0] + size2str(intra_result["size"]))[::4], fontsize=9)
    ax2.set_ylim(bottom=1)
    ax2.grid(which='major', alpha=0.5)
    ax2.set_title("median FCT", fontsize=12)
    
    # p99 FCT
    ax3 = fig.add_subplot(133)
    ax3.set_xlabel("Flow Size (Bytes)", fontsize=11.5)
    ax3.set_ylabel("p99 FCT Slowdown", fontsize=11.5)
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)
    ax3.plot(xvals, intra_result["p99"], markersize=3.0, linewidth=2.0, label="intra_only")
    ax3.plot(xvals, mixed_result["p99"], markersize=3.0, linewidth=2.0, label="mixed(intra_only)")
    ax3.legend(loc="best", frameon=False, fontsize=10)
    ax3.tick_params(axis="x", rotation=40)
    ax3.set_xticks(([0] + xvals)[::4])
    ax3.set_xticklabels(([0] + size2str(intra_result["size"]))[::4], fontsize=9)
    ax3.set_ylim(bottom=1)
    ax3.grid(which='major', alpha=0.5)
    ax3.set_title("p99 FCT", fontsize=12)
    
    fig.tight_layout()
    
    combined_fig_filename = f"{fig_dir}/combined_fct_intra_{intra_id}_mixed_intra_only_{mixed_id}.pdf"
    print(f"save combined comparison plot: {combined_fig_filename}")
    plt.savefig(combined_fig_filename, transparent=False, bbox_inches='tight')
    
    combined_png_filename = f"{fig_dir}/combined_fct_intra_{intra_id}_mixed_intra_only_{mixed_id}.png"
    plt.savefig(combined_png_filename, transparent=False, bbox_inches='tight', dpi=150)
    
    print("all plots generated!")

if __name__=="__main__":
    setup()
    main()