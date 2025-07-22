#!/usr/bin/env python3
# Cross-datacenter topology generation script

# Default parameters
k_fat = 4                   # Fat-tree topology parameter K
oversubscript = 2           # Over-subscription ratio between ToR uplink and downlink
num_datacenters = 2         # Number of datacenters
intra_dc_link_rate = 100    # Intra-datacenter link bandwidth (Gbps)
intra_dc_link_latency = 10000  # Intra-datacenter link latency (ns, 0.01ms)
inter_dc_link_rate = 400    # Inter-datacenter link bandwidth (Gbps)
inter_dc_link_latency = 4000000  # Inter-datacenter link latency (ns, 4ms)
link_error_rate = 0.0       # Link error rate

import sys

# Process command line arguments
if len(sys.argv) > 1:
    k_fat = int(sys.argv[1])
if len(sys.argv) > 2:
    oversubscript = int(sys.argv[2])
if len(sys.argv) > 3:
    num_datacenters = int(sys.argv[3])
if len(sys.argv) > 4:
    intra_dc_link_rate = int(sys.argv[4])
if len(sys.argv) > 5:
    intra_dc_link_latency = float(sys.argv[5]) * 1000000  # Convert to ns
if len(sys.argv) > 6:
    inter_dc_link_rate = int(sys.argv[6])
if len(sys.argv) > 7:
    inter_dc_link_latency = float(sys.argv[7]) * 1000000  # Convert to ns

# Validate parameters
assert(k_fat % 2 == 0), "K must be an even number"
assert(num_datacenters >= 2), "Number of datacenters must be at least 2"

print("Cross-Datacenter Topology Parameters:")
print(f"Fat-tree K: {k_fat}")
print(f"Over-subscription ratio: {oversubscript}")
print(f"Number of datacenters: {num_datacenters}")
print(f"Intra-datacenter link bandwidth: {intra_dc_link_rate}Gbps")
print(f"Intra-datacenter link latency: {intra_dc_link_latency/1000000}ms")
print(f"Inter-datacenter link bandwidth: {inter_dc_link_rate}Gbps")
print(f"Inter-datacenter link latency: {inter_dc_link_latency/1000000}ms")

# Calculate node counts for a single datacenter
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
n_dci_per_dc = 1  # One DCI switch per datacenter

# Calculate total node counts
n_server_total = n_server_per_dc * num_datacenters
n_tor_total = n_tor_per_dc * num_datacenters
n_agg_total = n_agg_per_dc * num_datacenters
n_core_total = n_core_per_dc * num_datacenters
n_dci_total = n_dci_per_dc * num_datacenters

# Calculate total switch count
n_switch_total = n_tor_total + n_agg_total + n_core_total + n_dci_total

# Calculate total node count
n_node_total = n_server_total + n_switch_total

# Output detailed information
print("\nPer-Datacenter Details:")
print(f"Number of core switches: {n_core_per_dc}")
print(f"Number of pods: {n_pod}")
print(f"Number of aggregation switches per pod: {n_agg_per_pod}, total: {n_agg_per_dc}")
print(f"Number of ToR switches per pod: {n_tor_per_pod}, total: {n_tor_per_dc}")
print(f"Number of servers per ToR: {n_server_per_tor} (over-subscription ratio: {oversubscript})")
print(f"Number of servers per pod: {n_server_per_pod}, total per datacenter: {n_server_per_dc}")
print(f"Number of DCI switches: {n_dci_per_dc}")

print("\nOverall Topology Information:")
print(f"Total number of servers: {n_server_total}")
print(f"Total number of switches: {n_switch_total}")
print(f"Total number of nodes: {n_node_total}")

# Generate topology file
filename = f"cross_dc_k{k_fat}_dc{num_datacenters}_os{oversubscript}.txt"
num_links = 0

with open(filename, "w") as f:
    # Generate links for each datacenter
    for dc_id in range(num_datacenters):
        dc_offset = dc_id * (n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc + n_dci_per_dc)
        
        # Server to ToR links
        for p in range(n_tor_per_dc):
            for i in range(n_server_per_tor):
                id_server = dc_offset + p * n_server_per_tor + i
                id_tor = dc_offset + n_server_per_dc + p
                f.write(f"{id_server} {id_tor} {intra_dc_link_rate}Gbps {intra_dc_link_latency}ns {link_error_rate}\n")
                num_links += 1
        
        # ToR to aggregation layer links
        for i in range(n_pod):
            pod_offset = dc_offset + n_server_per_dc
            for j in range(n_tor_per_pod):
                for l in range(n_agg_per_pod):
                    id_tor = pod_offset + i * n_tor_per_pod + j
                    id_agg = pod_offset + n_tor_per_dc + i * n_agg_per_pod + l
                    f.write(f"{id_tor} {id_agg} {intra_dc_link_rate}Gbps {intra_dc_link_latency}ns {link_error_rate}\n")
                    num_links += 1
        
        # Aggregation layer to core layer links
        n_jump = int(k_fat / 2)
        for i in range(n_pod):
            for j in range(n_agg_per_pod):
                for l in range(int(k_fat / 2)):
                    id_agg = dc_offset + n_server_per_dc + n_tor_per_dc + i * n_agg_per_pod + j
                    id_core = dc_offset + n_server_per_dc + n_tor_per_dc + n_agg_per_dc + j * n_jump + l
                    f.write(f"{id_agg} {id_core} {intra_dc_link_rate}Gbps {intra_dc_link_latency}ns {link_error_rate}\n")
                    num_links += 1
        
        # Core layer to DCI switch links
        id_dci = dc_offset + n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc
        for i in range(n_core_per_dc):
            id_core = dc_offset + n_server_per_dc + n_tor_per_dc + n_agg_per_dc + i
            f.write(f"{id_core} {id_dci} {intra_dc_link_rate}Gbps {intra_dc_link_latency}ns {link_error_rate}\n")
            num_links += 1
    
    # DCI switch interconnections (full mesh)
    for i in range(num_datacenters):
        for j in range(i+1, num_datacenters):
            id_dci1 = i * (n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc + n_dci_per_dc) + n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc
            id_dci2 = j * (n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc + n_dci_per_dc) + n_server_per_dc + n_tor_per_dc + n_agg_per_dc + n_core_per_dc
            f.write(f"{id_dci1} {id_dci2} {inter_dc_link_rate}Gbps {inter_dc_link_latency}ns {link_error_rate}\n")
            num_links += 1

# Add topology file header information
def line_prepender(filename, line):
    with open(filename, "r+") as f:
        content = f.read()
        f.seek(0, 0)
        f.write(line.rstrip('\r\n') + '\n' + content)

# Add switch ID list (second line)
switch_ids = ""
for i in range(n_switch_total):
    if i == n_switch_total - 1:
        switch_ids += f"{i + n_server_total}\n"
    else:
        switch_ids += f"{i + n_server_total} "
line_prepender(filename, switch_ids)

# Add total node count, switch count, and link count (first line)
line_prepender(filename, f"{n_node_total} {n_switch_total} {num_links}")

print(f"\nTopology file generated: {filename}")
print(f"Total number of links: {num_links}")

# Generate server trace file
trace_filename = f"cross_dc_k{k_fat}_dc{num_datacenters}_trace.txt"
with open(trace_filename, "w") as f:
    f.write(f"{n_server_total}\n")
    
    server_ids = ""
    for i in range(n_server_total):
        if i == n_server_total - 1:
            server_ids += f"{i}"
        else:
            server_ids += f"{i} "
    f.write(server_ids)

print(f"Server trace file generated: {trace_filename}") 