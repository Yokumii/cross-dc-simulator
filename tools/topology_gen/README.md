# Topology Generator
This folder includes scripts for generating network topology files for the simulator.

## Scripts

### cross_dc_topology_gen.py
Generate cross-datacenter fat-tree topology files.

**Usage:**
```bash
python3 cross_dc_topology_gen.py [k_fat] [oversubscript] [num_datacenters] [intra_dc_link_rate] [intra_dc_link_latency] [inter_dc_link_rate] [inter_dc_link_latency] [intra_dc_link_error_rate] [inter_dc_link_error_rate]
```

**Parameters:**
- `k_fat`: Fat-tree topology parameter K (default: 4)
- `oversubscript`: Over-subscription ratio (default: 2)
- `num_datacenters`: Number of datacenters (default: 2)
- `intra_dc_link_rate`: Intra-datacenter link bandwidth in Gbps (default: 100)
- `intra_dc_link_latency`: Intra-datacenter link latency in ms (default: 0.01)
- `inter_dc_link_rate`: Inter-datacenter link bandwidth in Gbps (default: 400)
- `inter_dc_link_latency`: Inter-datacenter link latency in ms (default: 4)
- `intra_dc_link_error_rate`: Intra-datacenter link error rate (default: 0.0)
- `inter_dc_link_error_rate`: Inter-datacenter link error rate (default: 0.0)

**Examples:**
```bash
# No error rates
python3 cross_dc_topology_gen.py 4 2 2 100 0.01 400 4
# Output: cross_dc_k4_dc2_os2_ib100_il0.01_eb400_el4.txt

# With error rates
python3 cross_dc_topology_gen.py 4 2 2 100 0.01 400 4 0.001 0.01
# Output: cross_dc_k4_dc2_os2_ib100_il0.01_eb400_el4_ie0.001_ee0.01.txt
```

**Output:** 
- Base format: `cross_dc_k{k}_dc{dc}_os{os}_ib{intra_bw}_il{intra_latency}_eb{inter_bw}_el{inter_latency}.txt`
- With error rates: `..._ie{intra_error}_ee{inter_error}.txt`

**Filename components:**
- `k{k}`: Fat-tree K parameter
- `dc{dc}`: Number of datacenters
- `os{os}`: Over-subscription ratio
- `ib{intra_bw}`: Intra-datacenter bandwidth (Gbps)
- `il{intra_latency}`: Intra-datacenter latency (ms)
- `eb{inter_bw}`: Inter-datacenter bandwidth (Gbps)
- `el{inter_latency}`: Inter-datacenter latency (ms)
- `ie{intra_error}`: Intra-datacenter error rate (if > 0)
- `ee{inter_error}`: Inter-datacenter error rate (if > 0)

### fat_topology_gen.py
Generate single datacenter fat-tree topology files.

**Usage:**
```bash
python3 fat_topology_gen.py
```

**Parameters:** (hardcoded in script)
- `k_fat`: Fat-tree topology parameter K (default: 12)
- `oversubscript`: Over-subscription ratio (default: 2)
- `link_rate`: Link bandwidth in Gbps (default: 100)
- `link_latency`: Link latency in ns (default: 1000)

**Output:** Generates `fat_k12_100G_OS2.txt` topology file.

## Topology File Format
Each topology file contains:
- First line: Number of nodes
- Following lines: `<src_node> <dst_node> <bandwidth> <latency> <error_rate>`

Example:
```
320
0 64 100Gbps 1000ns 0.000000
1 64 100Gbps 1000ns 0.000000
...
```

## Integration
These scripts are called by:
- `simulation/run_cross_dc.py`
- `scripts/run_cross_dc_batch.sh`
- `scripts/run_edge_cnp_batch.sh`

The generated topology files are saved in `simulation/config/` directory.