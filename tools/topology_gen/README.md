# Topology Generator
This folder includes scripts for generating network topology files for the simulator.

## Scripts

### cross_dc_topology_gen.py
Generate cross-datacenter fat-tree topology files.

**Usage:**
```bash
python3 cross_dc_topology_gen.py [k_fat] [oversubscript] [num_datacenters] [intra_dc_link_rate] [intra_dc_link_latency] [inter_dc_link_rate] [inter_dc_link_latency]
```

**Parameters:**
- `k_fat`: Fat-tree topology parameter K (default: 4)
- `oversubscript`: Over-subscription ratio (default: 2)
- `num_datacenters`: Number of datacenters (default: 2)
- `intra_dc_link_rate`: Intra-datacenter link bandwidth in Gbps (default: 100)
- `intra_dc_link_latency`: Intra-datacenter link latency in ms (default: 0.01)
- `inter_dc_link_rate`: Inter-datacenter link bandwidth in Gbps (default: 400)
- `inter_dc_link_latency`: Inter-datacenter link latency in ms (default: 4)

**Example:**
```bash
python3 cross_dc_topology_gen.py 4 2 2 100 0.01 400 4
```

**Output:** Generates `cross_dc_k4_dc2_os2.txt` topology file.

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