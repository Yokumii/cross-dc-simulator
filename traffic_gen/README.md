# Traffic Generator
This folder includes the scripts for generating traffic.

## Usage

`python3 traffic_gen.py -h` for help.

Example:
`python3 traffic_gen.py -c WebSearch_distribution.txt -n 320 -l 0.3 -b 100G -t 0.1` generates traffic according to the web search flow size distribution, for 320 hosts, at 30% network load with 100Gbps host bandwidth for 0.1 seconds.

The generate traffic can be directly used by the simulation.

## Cross-Datacenter Traffic Generator

`python3 cross_dc_traffic_gen.py -h` for help.

Example:
`python3 cross_dc_traffic_gen.py -k 4 -d 2 --intra-load 0.5 --inter-load 0.2 -t 0.1` generates traffic for a cross-datacenter topology with:
- Fat-tree K=4 for each datacenter
- 2 datacenters
- Intra-datacenter load: 50% of link capacity
- Inter-datacenter load: 20% of link capacity
- Simulation time: 0.1 seconds
- Intra-datacenter flows use port 100, inter-datacenter flows use port 200

The generated traffic includes both intra-datacenter and inter-datacenter flows with different port numbers to distinguish them.

## Intra-Datacenter Only Traffic Generator

`python3 intra_dc_traffic_gen.py -h` for help.

Example:
`python3 intra_dc_traffic_gen.py -k 4 -d 2 --intra-load 0.5 -t 0.1` generates traffic for a cross-datacenter topology with:
- Fat-tree K=4 for each datacenter
- 2 datacenters
- Intra-datacenter load: 50% of link capacity
- Simulation time: 0.1 seconds
- Only generates flows within each datacenter (no inter-datacenter traffic)

This script is useful when you want to simulate traffic that only stays within each datacenter.

## Traffic format
The first line is the number of flows.

Each line after that is a flow: `<source host> <dest host> 3 <dest port number> <flow size (bytes)> <start time (seconds)>`
