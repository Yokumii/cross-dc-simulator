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

# color config
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
    print("script directory: {}".format(dir_path))
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


def get_steps_from_raw(filename, time_start, time_end, step=5):
    cmd_slowdown = "cat %s"%(filename)+" | awk '{ if ($6>"+"%d"%time_start+" && $6+$7<"+"%d"%(time_end)+") { slow=$7/$8; print slow<1?1:slow, $5} }' | sort -n -k 2"    
    output_slowdown = subprocess.check_output(cmd_slowdown, shell=True)
    aa = output_slowdown.decode("utf-8").split('\n')[:-2]
    nn = len(aa)
    
    if nn == 0:
        print(f"warning: file {filename} has no data in the time range")
        return None

    # CDF of FCT
    res = [[i/100.] for i in range(0, 100, step)]
    for i in range(0,100,step):
        l = int(i * nn / 100)
        r = int((i+step) * nn / 100)
        fct_size = aa[l:r]
        fct_size = [[float(x.split(" ")[0]), int(x.split(" ")[1])] for x in fct_size]
        fct = sorted(map(lambda x: x[0], fct_size))
        
        if not fct:  # check if the list is empty
            res[int(i/step)].append(0)  # flow size
            res[int(i/step)].append(0)  # avg FCT
            res[int(i/step)].append(0)  # median FCT
            res[int(i/step)].append(0)  # 95%FCT
            res[int(i/step)].append(0)  # 99%FCT
            res[int(i/step)].append(0)  # 99.9%FCT
            continue
            
        res[int(i/step)].append(fct_size[-1][1]) # flow size
        
        res[int(i/step)].append(sum(fct) / len(fct)) # avg FCT
        res[int(i/step)].append(get_pctl(fct, 0.5)) # median FCT
        res[int(i/step)].append(get_pctl(fct, 0.95)) # 95%FCT
        res[int(i/step)].append(get_pctl(fct, 0.99)) # 99%FCT
        res[int(i/step)].append(get_pctl(fct, 0.999)) # 99.9%FCT
    
    result = {"avg": [], "p50": [], "p95": [], "p99": [], "size": []}
    for item in res:
        result["avg"].append(item[2])
        result["p50"].append(item[3])
        result["p95"].append(item[4])
        result["p99"].append(item[5])
        result["size"].append(item[1])

    return result

def get_config_info(config_id, output_dir):
    """get the simulation parameters from the config file"""
    config_file = f"{output_dir}/{config_id}/config.txt"
    info = {
        "cc_mode": "unknown",
        "lb_mode": "unknown",
        "pfc": "unknown",
        "irn": "unknown",
        "topo": "unknown",
        "load": "unknown"
    }
    
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if "CC_MODE" in line:
                    info["cc_mode"] = line.strip().split(' ')[1]
                elif "LB_MODE" in line:
                    info["lb_mode"] = line.strip().split(' ')[1]
                elif "ENABLE_PFC" in line:
                    info["pfc"] = line.strip().split(' ')[1]
                elif "ENABLE_IRN" in line:
                    info["irn"] = line.strip().split(' ')[1]
                elif "TOPOLOGY_FILE" in line:
                    topo_file = line.strip().split(' ')[1]
                    info["topo"] = topo_file.split('/')[-1].replace('.txt', '')
                elif "LOAD" in line:
                    info["load"] = line.strip().split(' ')[1]
    
    # convert the number mode to the name
    cc_modes = {
        "1": "DCQCN",
        "3": "HPCC",
        "7": "Timely",
        "8": "DCTCP"
    }
    lb_modes = {
        "0": "FECMP",
        "2": "DRILL",
        "3": "CONGA",
        "6": "LetFlow",
        "9": "ConWeave"
    }
    
    if info["cc_mode"] in cc_modes:
        info["cc_mode"] = cc_modes[info["cc_mode"]]
    
    if info["lb_mode"] in lb_modes:
        info["lb_mode"] = lb_modes[info["lb_mode"]]
    
    if info["pfc"] == "1":
        info["flow_control"] = "Lossless"
    elif info["irn"] == "1":
        info["flow_control"] = "IRN"
    else:
        info["flow_control"] = "Unknown"
    
    return info

def main():
    parser = argparse.ArgumentParser(description='plot the FCT figure for a single simulation result')
    parser.add_argument('-id', dest='config_id', action='store', required=True, help="simulation ID")
    parser.add_argument('-sT', dest='time_limit_begin', action='store', type=int, default=2005000000, help="only consider the flows completed after T, default=2005000000 ns")
    parser.add_argument('-fT', dest='time_limit_end', action='store', type=int, default=10000000000, help="only consider the flows completed before T, default=10000000000 ns")
    parser.add_argument('-o', dest='output_dir', action='store', default=None, help="output directory, default is the current directory")
    
    args = parser.parse_args()
    time_start = args.time_limit_begin
    time_end = args.time_limit_end
    STEP = 5  # 5% step
    
    config_id = args.config_id

    file_dir = getFilePath()
    if args.output_dir:
        fig_dir = args.output_dir
    else:
        fig_dir = file_dir
    
    # ensure the output directory exists
    os.makedirs(fig_dir, exist_ok=True)
    
    output_dir = file_dir + "/../mix/output"

    # get the FCT data
    fct_file = f"{output_dir}/{config_id}/{config_id}_out_fct.txt"
    
    if not os.path.exists(fct_file):
        print(f"error: cannot find the FCT file: {fct_file}")
        return
    
    print(f"processing the FCT file: {fct_file}")
    result = get_steps_from_raw(fct_file, time_start, time_end, STEP)
    
    if not result:
        print("error: cannot get the valid data from the FCT file")
        return
    
    # get the config info
    config_info = get_config_info(config_id, output_dir)
    title = f"ID: {config_id}, {config_info['topo']}, {config_info['cc_mode']}, {config_info['lb_mode']}, {config_info['flow_control']}, Load: {config_info['load']}"
    
    xvals = [i for i in range(STEP, 100 + STEP, STEP)]
    
    # generate the comprehensive comparison figure
    fig = plt.figure(figsize=(10, 6))
    
    # avg FCT
    ax1 = fig.add_subplot(131)
    ax1.set_xlabel("flow size (Bytes)", fontsize=11.5)
    ax1.set_ylabel("avg FCT slowdown", fontsize=11.5)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.plot(xvals, result["avg"], markersize=3.0, linewidth=2.0, label=f"ID: {config_id}")
    ax1.legend(loc="best", frameon=False, fontsize=10)
    ax1.tick_params(axis="x", rotation=40)
    ax1.set_xticks(([0] + xvals)[::4])
    ax1.set_xticklabels(([0] + size2str(result["size"]))[::4], fontsize=9)
    ax1.set_ylim(bottom=1)
    ax1.grid(which='major', alpha=0.5)
    ax1.set_title("avg FCT", fontsize=12)
    
    # p50 FCT
    ax2 = fig.add_subplot(132)
    ax2.set_xlabel("flow size (Bytes)", fontsize=11.5)
    ax2.set_ylabel("p50 FCT slowdown", fontsize=11.5)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.plot(xvals, result["p50"], markersize=3.0, linewidth=2.0, label=f"ID: {config_id}")
    ax2.legend(loc="best", frameon=False, fontsize=10)
    ax2.tick_params(axis="x", rotation=40)
    ax2.set_xticks(([0] + xvals)[::4])
    ax2.set_xticklabels(([0] + size2str(result["size"]))[::4], fontsize=9)
    ax2.set_ylim(bottom=1)
    ax2.grid(which='major', alpha=0.5)
    ax2.set_title("median FCT", fontsize=12)
    
    # p99 FCT
    ax3 = fig.add_subplot(133)
    ax3.set_xlabel("flow size (Bytes)", fontsize=11.5)
    ax3.set_ylabel("p99 FCT slowdown", fontsize=11.5)
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)
    ax3.plot(xvals, result["p99"], markersize=3.0, linewidth=2.0, label=f"ID: {config_id}")
    ax3.legend(loc="best", frameon=False, fontsize=10)
    ax3.tick_params(axis="x", rotation=40)
    ax3.set_xticks(([0] + xvals)[::4])
    ax3.set_xticklabels(([0] + size2str(result["size"]))[::4], fontsize=9)
    ax3.set_ylim(bottom=1)
    ax3.grid(which='major', alpha=0.5)
    ax3.set_title("p99 FCT", fontsize=12)
    
    plt.suptitle(title, fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    
    # save the image
    fig_filename = f"{fig_dir}/fct_id_{config_id}.pdf"
    print(f"saving the FCT figure: {fig_filename}")
    plt.savefig(fig_filename, transparent=False, bbox_inches='tight')
    
    # save the PNG image
    png_filename = f"{fig_dir}/fct_id_{config_id}.png"
    plt.savefig(png_filename, transparent=False, bbox_inches='tight', dpi=150)
    
    print("FCT figure generated!")
    
    # generate the separate figure
    metrics = [
        {"name": "avg", "title": "avg FCT slowdown", "filename": f"avg_fct_id_{config_id}"},
        {"name": "p50", "title": "p50 FCT slowdown", "filename": f"p50_fct_id_{config_id}"},
        {"name": "p99", "title": "p99 FCT slowdown", "filename": f"p99_fct_id_{config_id}"}
    ]
    
    for metric in metrics:
        fig = plt.figure(figsize=(6, 4))
        ax = fig.add_subplot(111)
        
        ax.set_xlabel("flow size (Bytes)", fontsize=11.5)
        ax.set_ylabel(metric["title"], fontsize=11.5)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.yaxis.set_ticks_position('left')
        ax.xaxis.set_ticks_position('bottom')
        
        ax.plot(xvals, result[metric["name"]], markersize=4.0, linewidth=2.0, label=f"ID: {config_id}")
        
        ax.legend(loc="best", frameon=False, fontsize=12)
        
        ax.tick_params(axis="x", rotation=40)
        ax.set_xticks(([0] + xvals)[::2])
        ax.set_xticklabels(([0] + size2str(result["size"]))[::2], fontsize=10.5)
        ax.set_ylim(bottom=1)
        
        plt.title(title, fontsize=12)
        fig.tight_layout()
        ax.grid(which='minor', alpha=0.2)
        ax.grid(which='major', alpha=0.5)
        
        metric_filename = f"{fig_dir}/{metric['filename']}.pdf"
        print(f"saving the {metric['title']} figure: {metric_filename}")
        plt.savefig(metric_filename, transparent=False, bbox_inches='tight')
        plt.savefig(f"{fig_dir}/{metric['filename']}.png", transparent=False, bbox_inches='tight', dpi=150)
    
    print("all figures generated!")

if __name__=="__main__":
    setup()
    main() 