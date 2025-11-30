# Traffic Generator
This folder includes scripts for generating input flow traces for the simulator.

## Common
- CDF files: `AliStorage2019.txt`, `GoogleRPC2008.txt`, `FbHdp2015.txt`, `Solar2022.txt`
- Output format:
  - First line: total number of flows
  - Following lines: `<srcId> <dstId> 3 <sizeBytes> <startTimeSec>`

## cross_dc_traffic_gen.py
Generate mixed intra-/inter-datacenter flows for a cross-DC fat-tree topology.

Parameters (defaults in brackets):
- `-c, --cdf <file>`: flow-size CDF file [`AliStorage2019.txt`]
- `-k, --k-fat <K>`: fat-tree K [`4`]
- `-s, --oversubscript <ratio>`: oversubscription ratio [`2`]
- `-d, --datacenters <N>`: number of datacenters [`2`]
- `--intra-load <0..1>`: intra-DC load fraction [`0.5`]
- `--inter-load <0..1>`: inter-DC load fraction [`0.2`]
- `--intra-bw <Gbps>`: intra-DC link rate [`100`]
- `--inter-bw <Gbps>`: inter-DC link rate [`400`]
- `-t, --time <sec>`: simulation time [`0.1`]
- `--flow-scale <f>`: scale factor on arrival interval (larger ⇒ fewer flows) [`1.0`]
- `-o, --output <path>`: output file (e.g., `simulation/config/<topo>_mixed_flow.txt`)

Usage example:
```
python cross_dc_traffic_gen.py \
  -c AliStorage2019.txt -k 4 -d 2 \
  --intra-load 0.5 --inter-load 0.2 \
  --intra-bw 100 --inter-bw 400 \
  -t 0.1 --flow-scale 1.0 \
  -o ../../simulation/config/cross_dc_k4_dc2_os2_mixed_flow.txt
```

## intra_dc_traffic_gen.py
Generate intra-datacenter-only flows for a fat-tree topology.

Parameters (defaults in brackets):
- `-c, --cdf <file>`: flow-size CDF file [`AliStorage2019.txt`]
- `-k, --k-fat <K>`: fat-tree K [`4`]
- `-s, --oversubscript <ratio>`: oversubscription ratio [`2`]
- `-d, --datacenters <N>`: number of datacenters [`2`]
- `--intra-load <0..1>`: intra-DC load fraction [`0.5`]
- `--intra-bw <Gbps>`: intra-DC link rate [`100`]
- `-t, --time <sec>`: simulation time [`0.1`]
- `--flow-scale <f>`: scale factor on arrival interval [`1.0`]
- `-o, --output <path>`: output file (e.g., `simulation/config/<topo>_intra_only_flow.txt`)

Usage example:
```
python intra_dc_traffic_gen.py \
  -c AliStorage2019.txt -k 4 -d 2 \
  --intra-load 0.5 --intra-bw 100 \
  -t 0.1 --flow-scale 1.0 \
  -o ../../simulation/config/cross_dc_k4_dc2_os2_intra_only_flow.txt
```

## Legacy traffic_gen.py
Generic generator used by some scripts (e.g., `simulation/run.py`) to create host-based traffic from a CDF. See `-h` for options.
