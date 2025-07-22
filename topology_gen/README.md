# Topology Generator

This folder includes the scripts for generating topology.

## Usage

### Fat-tree topology generate

`python3 fat_topology_gen.py` generates a fat-tree topology with default parameters (k=12, oversubscription=2).

### Cross-datacenter topology with DCI switches

`python3 cross_dc_topology_gen.py [k] [oversubscription] [num_datacenters] [intra_dc_link_rate] [intra_dc_link_latency] [inter_dc_link_rate] [inter_dc_link_latency]`

Example:
`python3 cross_dc_topology_gen.py 4 2 2 100 0.01 400 4` generates a cross-datacenter topology with:
- Fat-tree K=4 for each datacenter
- Oversubscription ratio=2
- 2 datacenters
- Intra-datacenter link bandwidth=100Gbps
- Intra-datacenter link latency=0.01ms
- Inter-datacenter link bandwidth=400Gbps
- Inter-datacenter link latency=4ms

This script creates two files:
1. Topology file: `cross_dc_k{k}_dc{num_datacenters}_os{oversubscription}.txt`
2. Server trace file: `cross_dc_k{k}_dc{num_datacenters}_trace.txt`

## Topology format

The first line is `total node #, switch node #, link #`.

The second line is switch node IDs.

each line after that is a link: `<src> <dst> <rate> <delay> <error_rate>`