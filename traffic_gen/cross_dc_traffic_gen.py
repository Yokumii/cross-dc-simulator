#!/usr/bin/env python3
import sys
import random
import math
import heapq
from optparse import OptionParser
from custom_rand import CustomRand

class Flow:
    def __init__(self, src, dst, size, t, port=100):
        self.src, self.dst, self.size, self.t, self.port = src, dst, size, t, port
    def __str__(self):
        return "%d %d 3 %d %d %.9f"%(self.src, self.dst, self.port, self.size, self.t)

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

def is_same_dc(host_id1, host_id2, n_server_per_dc):
    """Check if two hosts are in the same datacenter"""
    dc1 = host_id1 // n_server_per_dc
    dc2 = host_id2 // n_server_per_dc
    return dc1 == dc2

if __name__ == "__main__":
    # Default parameters
    cdf_file = "AliStorage2019.txt"
    k_fat = 4
    oversubscript = 2
    num_datacenters = 2
    intra_dc_load = 0.5
    inter_dc_load = 0.2
    intra_dc_link_rate = 100
    inter_dc_link_rate = 400
    simulation_time = 0.1
    intra_dc_port = 100
    inter_dc_port = 200

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
    parser.add_option("--inter-load", dest="inter_dc_load", 
                      help="inter-datacenter load (percentage of total bandwidth), default: %.1f" % inter_dc_load, 
                      default=str(inter_dc_load))
    parser.add_option("--intra-bw", dest="intra_dc_link_rate", 
                      help="intra-datacenter link bandwidth (Gbps), default: %d" % intra_dc_link_rate, 
                      default=str(intra_dc_link_rate))
    parser.add_option("--inter-bw", dest="inter_dc_link_rate", 
                      help="inter-datacenter link bandwidth (Gbps), default: %d" % inter_dc_link_rate, 
                      default=str(inter_dc_link_rate))
    parser.add_option("-t", "--time", dest="time", 
                      help="the total run time (s), default: %.1f" % simulation_time, 
                      default=str(simulation_time))
    parser.add_option("--intra-port", dest="intra_dc_port", 
                      help="port number for intra-datacenter flows, default: %d" % intra_dc_port, 
                      default=str(intra_dc_port))
    parser.add_option("--inter-port", dest="inter_dc_port", 
                      help="port number for inter-datacenter flows, default: %d" % inter_dc_port, 
                      default=str(inter_dc_port))
    parser.add_option("-o", "--output", dest="output", 
                      help="the output file", 
                      default="cross_dc_traffic.txt")
    options, args = parser.parse_args()

    # Parse parameters
    cdf_file = options.cdf_file
    k_fat = int(options.k_fat)
    oversubscript = int(options.oversubscript)
    num_datacenters = int(options.num_datacenters)
    intra_dc_load = float(options.intra_dc_load)
    inter_dc_load = float(options.inter_dc_load)
    intra_dc_link_rate = float(options.intra_dc_link_rate)
    inter_dc_link_rate = float(options.inter_dc_link_rate)
    simulation_time = float(options.time)
    intra_dc_port = int(options.intra_dc_port)
    inter_dc_port = int(options.inter_dc_port)
    output_file = options.output

    # Calculate datacenter parameters
    n_pod = k_fat
    n_server_per_tor = int(k_fat / 2 * oversubscript)
    n_tor_per_pod = int(k_fat / 2)
    n_server_per_pod = n_server_per_tor * n_tor_per_pod
    n_server_per_dc = n_server_per_pod * n_pod
    n_server_total = n_server_per_dc * num_datacenters

    # Display configuration
    print("Cross-Datacenter Traffic Generator")
    print("----------------------------------")
    print(f"Fat-tree K: {k_fat}")
    print(f"Over-subscription ratio: {oversubscript}")
    print(f"Number of datacenters: {num_datacenters}")
    print(f"Servers per datacenter: {n_server_per_dc}")
    print(f"Total servers: {n_server_total}")
    print(f"Intra-datacenter load: {intra_dc_load}")
    print(f"Inter-datacenter load: {inter_dc_load}")
    print(f"Intra-datacenter link bandwidth: {intra_dc_link_rate}Gbps")
    print(f"Inter-datacenter link bandwidth: {inter_dc_link_rate}Gbps")
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

    # Calculate inter-arrival times for intra and inter DC traffic
    intra_dc_bandwidth = intra_dc_link_rate * 1e9  # convert to bps
    inter_dc_bandwidth = inter_dc_link_rate * 1e9  # convert to bps
    
    intra_dc_avg_inter_arrival = 1 / (intra_dc_bandwidth * intra_dc_load / 8.0 / avg_flow_size) * 1e9  # in ns
    inter_dc_avg_inter_arrival = 1 / (inter_dc_bandwidth * inter_dc_load / 8.0 / avg_flow_size) * 1e9  # in ns

    # Estimate number of flows
    intra_dc_flow_estimate = int(simulation_time_ns / intra_dc_avg_inter_arrival * n_server_total)
    inter_dc_flow_estimate = int(simulation_time_ns / inter_dc_avg_inter_arrival * n_server_total)
    total_flow_estimate = intra_dc_flow_estimate + inter_dc_flow_estimate
    
    # Initialize flow counter
    n_flow = 0
    
    # Write estimated flow count as placeholder (will update later)
    ofile.write(f"{total_flow_estimate}\n")

    # Generate intra-datacenter flows
    print("Generating intra-datacenter flows...")
    intra_host_list = [(base_t + int(poisson(intra_dc_avg_inter_arrival)), i) for i in range(n_server_total)]
    heapq.heapify(intra_host_list)
    
    intra_flow_count = 0
    while len(intra_host_list) > 0:
        t, src = intra_host_list[0]
        inter_t = int(poisson(intra_dc_avg_inter_arrival))
        
        # Determine source datacenter
        src_dc = src // n_server_per_dc
        src_dc_start = src_dc * n_server_per_dc
        src_dc_end = src_dc_start + n_server_per_dc - 1
        
        # Select destination within same datacenter
        dst = random.randint(src_dc_start, src_dc_end)
        while dst == src:
            dst = random.randint(src_dc_start, src_dc_end)
            
        if (t + inter_t > simulation_time_ns + base_t):
            heapq.heappop(intra_host_list)
        else:
            size = int(customRand.rand())
            if size <= 0:
                size = 1
            n_flow += 1
            intra_flow_count += 1
            ofile.write(f"{src} {dst} 3 {intra_dc_port} {size} {t * 1e-9:.9f}\n")
            heapq.heapreplace(intra_host_list, (t + inter_t, src))

    # Generate inter-datacenter flows
    print("Generating inter-datacenter flows...")
    inter_host_list = [(base_t + int(poisson(inter_dc_avg_inter_arrival)), i) for i in range(n_server_total)]
    heapq.heapify(inter_host_list)
    
    inter_flow_count = 0
    while len(inter_host_list) > 0:
        t, src = inter_host_list[0]
        inter_t = int(poisson(inter_dc_avg_inter_arrival))
        
        # Determine source datacenter
        src_dc = src // n_server_per_dc
        
        # Select destination from a different datacenter
        dst_dc = random.randint(0, num_datacenters - 2)
        if dst_dc >= src_dc:
            dst_dc += 1  # Skip source datacenter
            
        dst_dc_start = dst_dc * n_server_per_dc
        dst_dc_end = dst_dc_start + n_server_per_dc - 1
        dst = random.randint(dst_dc_start, dst_dc_end)
            
        if (t + inter_t > simulation_time_ns + base_t):
            heapq.heappop(inter_host_list)
        else:
            size = int(customRand.rand())
            if size <= 0:
                size = 1
            n_flow += 1
            inter_flow_count += 1
            ofile.write(f"{src} {dst} 3 {inter_dc_port} {size} {t * 1e-9:.9f}\n")
            heapq.heapreplace(inter_host_list, (t + inter_t, src))

    # Update actual flow count
    ofile.seek(0)
    ofile.write(f"{n_flow}")
    ofile.close()

    print(f"Traffic generation complete.")
    print(f"Total flows: {n_flow}")
    print(f"Intra-datacenter flows: {intra_flow_count}")
    print(f"Inter-datacenter flows: {inter_flow_count}")
    print(f"Output written to: {output_file}") 