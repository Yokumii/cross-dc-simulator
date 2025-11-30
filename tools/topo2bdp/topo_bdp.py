import os

# Load BDP mapping from text configuration file
def _load_bdp_mapping():
    """Load BDP mapping from text configuration file"""
    txt_path = os.path.join(os.path.dirname(__file__), 'topo_bdp.txt')
    mapping = {}
    
    try:
        with open(txt_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse format: topology_name=bdp_value
                if '=' in line:
                    topo_name, bdp_str = line.split('=', 1)
                    topo_name = topo_name.strip()
                    bdp_str = bdp_str.strip()
                    
                    try:
                        bdp_value = int(bdp_str)
                        mapping[topo_name] = bdp_value
                    except ValueError as e:
                        print(f"Warning: Invalid BDP value for {topo_name}: {bdp_str}")
                        
    except FileNotFoundError:
        print(f"Warning: Could not load BDP mapping from {txt_path}, using fallback values")
        # Fallback to hardcoded values
        mapping = {
            "leaf_spine_128_100G_OS2": 104000,  # 2-tier
            "fat_k4_100G_OS2": 153000, # 3-tier -> core 400G
            "fat_k8_100G_OS2": 156000, # 3-tier -> core 400G
            "cross_dc_k4_dc2_os2": 102008250,  # cross-dc -> 100G internal, 400G DCI
        }
    
    return mapping

# Load the mapping
topo2bdp = _load_bdp_mapping()

def get_bdp(topo_name: str):
    """Get BDP value for a topology name"""
    return topo2bdp.get(topo_name)

def reload_bdp_mapping():
    """Reload BDP mapping from JSON file (useful for testing)"""
    global topo2bdp
    topo2bdp = _load_bdp_mapping()
    return topo2bdp

