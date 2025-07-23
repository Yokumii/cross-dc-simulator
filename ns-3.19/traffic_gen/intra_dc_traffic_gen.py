#!/usr/bin/env python3
import sys
import random
import math
import heapq
from optparse import OptionParser
from custom_rand import CustomRand

class Flow:
    def __init__(self, src, dst, size, t):
        self.src, self.dst, self.size, self.t = src, dst, size, t
    def __str__(self):
        return "%d %d 3 %d %.9f"%(self.src, self.dst, self.size, self.t)

def translate_bandwidth(b):
    if b == None:
        return None
    if type(b)!=str:
        return None
    if b[-1] == 'G':
        return float(b[:-1])*1e9
    if b[-1] == 'M':
        return float(b[:-1])*1e6
    if b[-1] == 'K':
        return float(b[:-1])*1e3
    return float(b)

def poisson(lam):
    return -math.log(1-random.random())*lam

def is_same_dc(host_id1, host_id2, n_server_per_dc, n_switch_per_dc, n_dci_per_dc):
    """Check if two hosts are in the same datacenter"""
    dc1 = host_id1 // n_server_per_dc
    dc2 = host_id2 // n_server_per_dc
    return dc1 == dc2

def get_server_id(server_index, dc_id, n_server_per_dc, n_switch_per_dc, n_dci_per_dc):
    """Convert server index to actual server ID in the topology"""
    dc_offset = dc_id * (n_server_per_dc + n_switch_per_dc + n_dci_per_dc)
    return dc_offset + server_index

if __name__ == "__main__":
    # Default parameters
    cdf_file = "AliStorage2019.txt"
    k_fat = 4
    oversubscript = 2
    num_datacenters = 2
    intra_dc_load = 0.5
    intra_dc_link_rate = 100
    simulation_time = 0.1

    parser = OptionParser()
    parser.add_option("-c", "--cdf", dest="cdf_file", 
                      help="the file of the traffic size cdf, default: %s" % cdf_file, 
                      default=cdf_file)
    parser.add_option("-k", "--k-fat", dest="k_fat", 
                      help="fat-tree topology parameter K, default: %d" % k_fat, 
                      default=str(k_fat))
    parser.add_option("-s", "--oversubscript", dest="oversubscript", 
                      help="over-subscription ratio, default: %d" % oversubscript, 
                      default=str(oversubscript))
    parser.add_option("-d", "--datacenters", dest="num_datacenters", 
                      help="number of datacenters, default: %d" % num_datacenters, 
                      default=str(num_datacenters))
    parser.add_option("--intra-load", dest="intra_dc_load", 
                      help="intra-datacenter load (percentage of total bandwidth), default: %.1f" % intra_dc_load, 
                      default=str(intra_dc_load))
    parser.add_option("--intra-bw", dest="intra_dc_link_rate", 
                      help="intra-datacenter link bandwidth (Gbps), default: %d" % intra_dc_link_rate, 
                      default=str(intra_dc_link_rate))
    parser.add_option("-t", "--time", dest="time", 
                      help="the total run time (s), default: %.1f" % simulation_time, 
                      default=str(simulation_time))
    parser.add_option("-o", "--output", dest="output", 
                      help="the output file", 
                      default="intra_dc_traffic.txt")
    options, args = parser.parse_args()

    # Parse parameters
    cdf_file = options.cdf_file
    k_fat = int(options.k_fat)
    oversubscript = int(options.oversubscript)
    num_datacenters = int(options.num_datacenters)
    intra_dc_load = float(options.intra_dc_load)
    intra_dc_link_rate = float(options.intra_dc_link_rate)
    simulation_time = float(options.time)
    output_file = options.output

    # Calculate datacenter parameters
    n_core = int(k_fat / 2 * k_fat / 2)
    n_pod = k_fat
    n_agg_per_pod = int(k_fat / 2)
    n_tor_per_pod = int(k_fat / 2)
    n_server_per_tor = int(k_fat / 2 * oversubscript)
    n_server_per_pod = n_server_per_tor * n_tor_per_pod
    n_server_per_dc = n_server_per_pod * n_pod

    n_tor_per_dc = n_tor_per_pod * n_pod
    n_agg_per_dc = n_agg_per_pod * n_pod
    n_core_per_dc = n_core
    n_switch_per_dc = n_tor_per_dc + n_agg_per_dc + n_core_per_dc
    n_dci_per_dc = 1  # One DCI switch per datacenter

    # Calculate total node counts
    n_server_total = n_server_per_dc * num_datacenters

    # Display configuration
    print("Intra-Datacenter Traffic Generator")
    print("----------------------------------")
    print(f"Fat-tree K: {k_fat}")
    print(f"Over-subscription ratio: {oversubscript}")
    print(f"Number of datacenters: {num_datacenters}")
    print(f"Servers per datacenter: {n_server_per_dc}")
    print(f"Total servers: {n_server_total}")
    print(f"Intra-datacenter load: {intra_dc_load}")
    print(f"Intra-datacenter link bandwidth: {intra_dc_link_rate}Gbps")
    print(f"Simulation time: {simulation_time}s")
    print(f"CDF file: {cdf_file}")
    print(f"Output file: {output_file}")

    # Base time for simulation
    base_t = 2000000000  # 2 seconds in nanoseconds
    simulation_time_ns = simulation_time * 1e9  # convert to nanoseconds

    # Read CDF file
    try:
        file = open(cdf_file, "r")
        lines = file.readlines()
        file.close()
    except FileNotFoundError:
        print(f"Error: CDF file '{cdf_file}' not found.")
        sys.exit(1)

    # Parse CDF data
    cdf = []
    for line in lines:
        x, y = map(float, line.strip().split(' '))
        cdf.append([x, y])

    # Create custom random generator for flow sizes
    customRand = CustomRand()
    if not customRand.setCdf(cdf):
        print("Error: Not valid CDF data")
        sys.exit(1)

    # Open output file
    ofile = open(output_file, "w")

    # Calculate average flow size
    avg_flow_size = customRand.getAvg()

    # Calculate inter-arrival times for intra DC traffic
    intra_dc_bandwidth = intra_dc_link_rate * 1e9  # convert to bps
    
    intra_dc_avg_inter_arrival = 1 / (intra_dc_bandwidth * intra_dc_load / 8.0 / avg_flow_size) * 1e9  # in ns

    # Estimate number of flows
    intra_dc_flow_estimate = int(simulation_time_ns / intra_dc_avg_inter_arrival * n_server_total)
    
    # Initialize flow counter
    n_flow = 0
    
    # Write estimated flow count as placeholder (will update later)
    ofile.write(f"{intra_dc_flow_estimate}\n")

    # Generate intra-datacenter flows
    print("Generating intra-datacenter flows...")
    # Create a list of server indices for each datacenter
    server_indices = []
    for dc_id in range(num_datacenters):
        for i in range(n_server_per_dc):
            server_indices.append((dc_id, i))
    
    # Create host list with poisson arrival times
    intra_host_list = []
    for dc_id, server_idx in server_indices:
        server_id = get_server_id(server_idx, dc_id, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
        intra_host_list.append((base_t + int(poisson(intra_dc_avg_inter_arrival)), server_id, dc_id, server_idx))
    heapq.heapify(intra_host_list)
    
    intra_flow_count = 0
    while len(intra_host_list) > 0:
        t, src_id, src_dc, src_idx = intra_host_list[0]
        inter_t = int(poisson(intra_dc_avg_inter_arrival))
        
        # Select destination within same datacenter (by index)
        dst_idx = random.randint(0, n_server_per_dc - 1)
        while dst_idx == src_idx:
            dst_idx = random.randint(0, n_server_per_dc - 1)
            
        # Convert destination index to actual node ID
        dst_id = get_server_id(dst_idx, src_dc, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
            
        if (t + inter_t > simulation_time_ns + base_t):
            heapq.heappop(intra_host_list)
        else:
            size = int(customRand.rand())
            if size <= 0:
                size = 1
            n_flow += 1
            intra_flow_count += 1
            ofile.write(f"{src_id} {dst_id} 3 {size} {t * 1e-9:.9f}\n")
            heapq.heapreplace(intra_host_list, (t + inter_t, src_id, src_dc, src_idx))

    # Update actual flow count
    ofile.seek(0)
    ofile.write(f"{n_flow}")
    ofile.close()

    print(f"Traffic generation complete.")
    print(f"Total flows: {n_flow}")
    print(f"Output written to: {output_file}") 