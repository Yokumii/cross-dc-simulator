#!/usr/bin/python3

import subprocess
import os
import sys
import argparse
import time
import re
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Check PFC packet loss')
    parser.add_argument('--k-fat', dest='k_fat', action='store',
                      type=int, default=4, help="Fat-tree K parameter (default: 4)")
    parser.add_argument('--num-dc', dest='num_dc', action='store',
                      type=int, default=2, help="Number of datacenters (default: 2)")
    parser.add_argument('--simul_time', dest='simul_time', action='store',
                      type=float, default=0.01, help="Simulation time (default: 0.01s)")
    parser.add_argument('--intra-load', dest='intra_load', action='store',
                      type=float, default=0.5, help="Intra-datacenter load (default: 0.5)")
    parser.add_argument('--inter-load', dest='inter_load', action='store',
                      type=float, default=0.2, help="Inter-datacenter load (default: 0.2)")
    parser.add_argument('--buffer', dest="buffer", action='store',
                      type=int, default=16, help="Switch buffer size (MB) (default: 16)")
    parser.add_argument('--dci-buffer', dest='dci_buffer', action='store',
                      type=int, default=128, help="DCI switch buffer size (MB) (default: 128)")
    parser.add_argument('--cc', dest='cc', action='store',
                      default='dcqcn', help="Congestion control algorithm: dcqcn/hpcc/timely/dctcp (default: dcqcn)")
    
    args = parser.parse_args()
    
    # create result directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = f"pfc_test_results_{timestamp}"
    os.makedirs(result_dir, exist_ok=True)
    
    print(f"Test started, results will be saved in {result_dir} directory")
    
    # record test parameters
    with open(f"{result_dir}/test_parameters.txt", "w") as f:
        f.write(f"Test time: {timestamp}\n")
        f.write(f"Fat-tree K parameter: {args.k_fat}\n")
        f.write(f"Number of datacenters: {args.num_dc}\n")
        f.write(f"Simulation time: {args.simul_time}s\n")
        f.write(f"Intra-datacenter load: {args.intra_load}\n")
        f.write(f"Inter-datacenter load: {args.inter_load}\n")
        f.write(f"Switch buffer size: {args.buffer}MB\n")
        f.write(f"DCI switch buffer size: {args.dci_buffer}MB\n")
        f.write(f"Congestion control algorithm: {args.cc}\n")
    
    # run simulation with PFC enabled
    print("Running simulation with PFC enabled...")
    pfc_enabled_id = run_simulation(args, pfc_enabled=True)
    
    # run simulation with PFC disabled
    print("Running simulation with PFC disabled...")
    pfc_disabled_id = run_simulation(args, pfc_enabled=False)
    
    # analyze results
    print("Analyzing results...")
    analyze_results(pfc_enabled_id, pfc_disabled_id, result_dir)
    
    print(f"Test completed, results saved to {result_dir} directory")

def run_simulation(args, pfc_enabled):
    """Run a single simulation and return the simulation ID"""
    cmd = [
        "python3", "run_cross_dc.py",
        "--traffic-type", "mixed",
        "--k-fat", str(args.k_fat),
        "--num-dc", str(args.num_dc),
        "--simul_time", str(args.simul_time),
        "--intra-load", str(args.intra_load),
        "--inter-load", str(args.inter_load),
        "--buffer", str(args.buffer),
        "--dci-buffer", str(args.dci_buffer),
        "--cc", args.cc,
        "--pfc", "1" if pfc_enabled else "0",
        "--irn", "0" if pfc_enabled else "1"  # if PFC is disabled, enable IRN
    ]
    
    # run simulation
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    stdout, stderr = process.communicate()
    
    # extract simulation ID from output
    config_id_match = re.search(r"Config filename: mix/output/(\d+)/config\.txt", stdout)
    if config_id_match:
        config_id = config_id_match.group(1)
        print(f"Simulation ID: {config_id}")
        return config_id
    else:
        print("Error: cannot extract simulation ID from output")
        print("Output content:")
        print(stdout)
        print(stderr)
        sys.exit(1)

def analyze_packet_loss(config_id):
    """Analyze packet loss for a specific simulation"""
    # check PFC file
    pfc_file = f"mix/output/{config_id}/{config_id}_out_pfc.txt"
    if not os.path.exists(pfc_file):
        print(f"Error: PFC file not found: {pfc_file}")
        return None
    
    # analyze PFC file
    pause_count = 0
    resume_count = 0
    
    with open(pfc_file, 'r') as f:
        for line in f:
            if "PAUSE" in line:
                pause_count += 1
            if "RESUME" in line:
                resume_count += 1
    
    # check connection file
    conn_file = f"mix/output/{config_id}/{config_id}_out_conn.txt"
    drop_count = 0
    
    if os.path.exists(conn_file):
        with open(conn_file, 'r') as f:
            for line in f:
                if "DROP" in line:
                    drop_count += 1
    
    # check FCT summary file
    fct_summary_file = f"mix/output/{config_id}/{config_id}_out_fct_summary.txt"
    total_flows = 0
    completed_flows = 0
    
    if os.path.exists(fct_summary_file):
        with open(fct_summary_file, 'r') as f:
            for line in f:
                if "Total flows:" in line:
                    total_flows = int(line.split(":")[1].strip())
                if "Completed flows:" in line:
                    completed_flows = int(line.split(":")[1].strip())
    
    return {
        "pause_count": pause_count,
        "resume_count": resume_count,
        "drop_count": drop_count,
        "total_flows": total_flows,
        "completed_flows": completed_flows,
        "completion_rate": completed_flows / total_flows if total_flows > 0 else 0
    }

def analyze_results(pfc_enabled_id, pfc_disabled_id, result_dir):
    """Compare results between PFC enabled and disabled"""
    # analyze PFC enabled results
    print("Analyzing PFC enabled results...")
    pfc_enabled_results = analyze_packet_loss(pfc_enabled_id)
    
    # analyze PFC disabled results
    print("Analyzing PFC disabled results...")
    pfc_disabled_results = analyze_packet_loss(pfc_disabled_id)
    
    # save analysis results
    with open(f"{result_dir}/analysis_results.txt", "w") as f:
        f.write("=== PFC enabled results ===\n")
        f.write(f"Simulation ID: {pfc_enabled_id}\n")
        f.write(f"PAUSE signal count: {pfc_enabled_results['pause_count']}\n")
        f.write(f"RESUME signal count: {pfc_enabled_results['resume_count']}\n")
        f.write(f"Packet loss count: {pfc_enabled_results['drop_count']}\n")
        f.write(f"Total flow count: {pfc_enabled_results['total_flows']}\n")
        f.write(f"Completed flow count: {pfc_enabled_results['completed_flows']}\n")
        f.write(f"Completion rate: {pfc_enabled_results['completion_rate']:.4f}\n\n")
        
        f.write("=== PFC disabled results ===\n")
        f.write(f"Simulation ID: {pfc_disabled_id}\n")
        f.write(f"PAUSE signal count: {pfc_disabled_results['pause_count']}\n")
        f.write(f"RESUME signal count: {pfc_disabled_results['resume_count']}\n")
        f.write(f"Packet loss count: {pfc_disabled_results['drop_count']}\n")
        f.write(f"Total flow count: {pfc_disabled_results['total_flows']}\n")
        f.write(f"Completed flow count: {pfc_disabled_results['completed_flows']}\n")
        f.write(f"Completion rate: {pfc_disabled_results['completion_rate']:.4f}\n\n")
    
    # Copy config files and logs for reference
    os.system(f"cp mix/output/{pfc_enabled_id}/config.txt {result_dir}/pfc_enabled_config.txt")
    os.system(f"cp mix/output/{pfc_enabled_id}/config.log {result_dir}/pfc_enabled_config.log")
    os.system(f"cp mix/output/{pfc_disabled_id}/config.txt {result_dir}/pfc_disabled_config.txt")
    os.system(f"cp mix/output/{pfc_disabled_id}/config.log {result_dir}/pfc_disabled_config.log")
    
    # Generate FCT comparison figures using compare_fct.py
    print("Generating FCT comparison figures...")
    os.system(f"python3 analysis/compare_fct.py -intra {pfc_enabled_id} -mixed {pfc_disabled_id} -o {result_dir}")
    
    # Print summary results
    print("\n=== Test results summary ===")
    print(f"PFC enabled packet loss count: {pfc_enabled_results['drop_count']}")
    print(f"PFC disabled packet loss count: {pfc_disabled_results['drop_count']}")
    print(f"PFC enabled completion rate: {pfc_enabled_results['completion_rate']:.4f}")
    print(f"PFC disabled completion rate: {pfc_disabled_results['completion_rate']:.4f}")
    
if __name__ == "__main__":
    main() 