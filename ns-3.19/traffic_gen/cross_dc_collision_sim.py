#!/usr/bin/env python3
import sys
import random
import math
from optparse import OptionParser

class Flow:
    def __init__(self, src, dst, size, t):
        self.src, self.dst, self.size, self.t = src, dst, size, t
    def __str__(self):
        return "%d %d 3 %d %.9f"%(self.src, self.dst, self.size, self.t)

def get_server_id(server_index, dc_id, n_server_per_dc, n_switch_per_dc, n_dci_per_dc):
    """Convert server index to actual server ID in the topology"""
    dc_offset = dc_id * (n_server_per_dc + n_switch_per_dc + n_dci_per_dc)
    return dc_offset + server_index

if __name__ == "__main__":
    # Default parameters
    k_fat = 4
    oversubscript = 2
    num_datacenters = 2
    intra_dc_link_rate = 100  # Gbps
    inter_dc_link_rate = 100  # Gbps
    simulation_time = 0.01    # 10ms
    background_flow_size = 100000000  # 100MB background flow
    burst_flow_size = 1000000       # 1MB burst flow
    
    parser = OptionParser()
    parser.add_option("-k", "--k-fat", dest="k_fat", 
                      help="fat-tree topology parameter K, default: %d" % k_fat, 
                      default=str(k_fat))
    parser.add_option("-s", "--oversubscript", dest="oversubscript", 
                      help="over-subscription ratio, default: %d" % oversubscript, 
                      default=str(oversubscript))
    parser.add_option("-d", "--datacenters", dest="num_datacenters", 
                      help="number of datacenters, default: %d" % num_datacenters, 
                      default=str(num_datacenters))
    parser.add_option("--intra-bw", dest="intra_dc_link_rate", 
                      help="intra-datacenter link bandwidth (Gbps), default: %d" % intra_dc_link_rate, 
                      default=str(intra_dc_link_rate))
    parser.add_option("--inter-bw", dest="inter_dc_link_rate", 
                      help="inter-datacenter link bandwidth (Gbps), default: %d" % inter_dc_link_rate, 
                      default=str(inter_dc_link_rate))
    parser.add_option("-t", "--time", dest="time", 
                      help="the total run time (s), default: %.3f" % simulation_time, 
                      default=str(simulation_time))
    parser.add_option("-o", "--output", dest="output", 
                      help="the output file", 
                      default="cross_dc_collision.txt")
    parser.add_option("--bg-size", dest="background_flow_size", 
                      help="background flow size in bytes, default: %d" % background_flow_size, 
                      default=str(background_flow_size))
    parser.add_option("--burst-size", dest="burst_flow_size", 
                      help="burst flow size in bytes, default: %d" % burst_flow_size, 
                      default=str(burst_flow_size))
    options, args = parser.parse_args()

    # Parse parameters
    k_fat = int(options.k_fat)
    oversubscript = int(options.oversubscript)
    num_datacenters = int(options.num_datacenters)
    intra_dc_link_rate = float(options.intra_dc_link_rate)
    inter_dc_link_rate = float(options.inter_dc_link_rate)
    simulation_time = float(options.time)
    output_file = options.output
    background_flow_size = int(options.background_flow_size)
    burst_flow_size = int(options.burst_flow_size)

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
    print("Cross-Datacenter Collision Simulation Traffic Generator")
    print("------------------------------------------------------")
    print(f"Fat-tree K: {k_fat}")
    print(f"Over-subscription ratio: {oversubscript}")
    print(f"Number of datacenters: {num_datacenters}")
    print(f"Servers per datacenter: {n_server_per_dc}")
    print(f"Total servers: {n_server_total}")
    print(f"Intra-datacenter link bandwidth: {intra_dc_link_rate}Gbps")
    print(f"Inter-datacenter link bandwidth: {inter_dc_link_rate}Gbps")
    print(f"Simulation time: {simulation_time}s")
    print(f"Background flow size: {background_flow_size} bytes")
    print(f"Burst flow size: {burst_flow_size} bytes")
    print(f"Output file: {output_file}")

    # Open output file
    ofile = open(output_file, "w")
    
    # Total number of flows: 1 background + 7 sending bursts + 7 receiving bursts
    total_flows = 1 + 7 + 7
    ofile.write(f"{total_flows}\n")
    
    # For simplicity, we'll use specific servers in each datacenter
    # DC A: datacenter 0
    # DC B: datacenter 1
    
    # Select a specific ToR switch in each datacenter to ensure collision
    # We'll use the first ToR switch in each datacenter
    tor_a_servers = []
    tor_b_servers = []
    
    # Get servers connected to the first ToR in DC A
    for i in range(n_server_per_tor):
        server_idx = i  # First n_server_per_tor servers are connected to first ToR
        server_id = get_server_id(server_idx, 0, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
        tor_a_servers.append(server_id)
    
    # Get servers connected to the first ToR in DC B
    for i in range(n_server_per_tor):
        server_idx = i  # First n_server_per_tor servers are connected to first ToR
        server_id = get_server_id(server_idx, 1, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
        tor_b_servers.append(server_id)
    
    # Create the background flow (long-haul flow)
    # From DC A to DC B, starting at time 0
    bg_src = tor_a_servers[0]  # First server in DC A's first ToR
    bg_dst = tor_b_servers[0]  # First server in DC B's first ToR
    bg_start_time = 0.0  # Start at time 0
    
    # Write background flow
    ofile.write(f"{bg_src} {bg_dst} 3 {background_flow_size} {bg_start_time:.9f}\n")
    print(f"Background flow: {bg_src} -> {bg_dst}, size: {background_flow_size}, start: {bg_start_time}")
    
    # Create burst flows from DC A (sending datacenter)
    # 7 flows starting at 800us
    burst_start_time_a = 0.000800  # 800us
    
    for i in range(7):
        if i+1 >= len(tor_a_servers):
            # If we run out of servers, wrap around
            src = tor_a_servers[i % len(tor_a_servers)]
        else:
            src = tor_a_servers[i+1]  # Skip the first server (used for background flow)
            
        # Destination is a server in the same DC but different ToR
        # We'll use servers from the second ToR
        dst_idx = n_server_per_tor + i  # Servers in the second ToR
        dst = get_server_id(dst_idx, 0, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
        
        # Write burst flow
        ofile.write(f"{src} {dst} 3 {burst_flow_size} {burst_start_time_a:.9f}\n")
        print(f"DC A burst flow {i+1}: {src} -> {dst}, size: {burst_flow_size}, start: {burst_start_time_a}")
    
    # Create burst flows from DC B (receiving datacenter)
    # 7 flows starting at 4800us
    burst_start_time_b = 0.004800  # 4800us
    
    for i in range(7):
        if i+1 >= len(tor_b_servers):
            # If we run out of servers, wrap around
            src = tor_b_servers[i % len(tor_b_servers)]
        else:
            src = tor_b_servers[i+1]  # Skip the first server (used for background flow)
            
        # Destination is a server in the same DC but different ToR
        # We'll use servers from the second ToR
        dst_idx = n_server_per_tor + i  # Servers in the second ToR
        dst = get_server_id(dst_idx, 1, n_server_per_dc, n_switch_per_dc, n_dci_per_dc)
        
        # Write burst flow
        ofile.write(f"{src} {dst} 3 {burst_flow_size} {burst_start_time_b:.9f}\n")
        print(f"DC B burst flow {i+1}: {src} -> {dst}, size: {burst_flow_size}, start: {burst_start_time_b}")
    
    ofile.close()
    print(f"Traffic generation complete.")
    print(f"Total flows: {total_flows}")
    print(f"Output written to: {output_file}") 