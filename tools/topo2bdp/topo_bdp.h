#ifndef TOPO_BDP_H
#define TOPO_BDP_H

#include <map>
#include <string>
#include <fstream>
#include <iostream>
#include <sstream>

// Load BDP mapping from configuration file
inline std::map<std::string, uint32_t> load_bdp_mapping() {
    std::map<std::string, uint32_t> mapping;
    
    // Try to find the config file relative to this header
    std::string config_path = "tools/topo2bdp/topo_bdp.txt";
    std::ifstream file(config_path);
    
    if (!file.is_open()) {
        // Fallback: try alternative paths
        std::string alt_paths[] = {
            "../tools/topo2bdp/topo_bdp.txt",
            "../../tools/topo2bdp/topo_bdp.txt",
            "topo_bdp.txt"
        };
        
        for (const auto& alt_path : alt_paths) {
            file.open(alt_path);
            if (file.is_open()) {
                config_path = alt_path;
                break;
            }
        }
    }
    
    if (!file.is_open()) {
        std::cerr << "Warning: Could not open BDP config file, using fallback values" << std::endl;
        // Fallback to hardcoded values
        mapping["leaf_spine_128_100G_OS2"] = 104000;
        mapping["fat_k4_100G_OS2"] = 153000;
        mapping["fat_k8_100G_OS2"] = 156000;
        mapping["cross_dc_k4_dc2_os2"] = 102008250;
        return mapping;
    }
    
    std::string line;
    while (std::getline(file, line)) {
        // Skip empty lines and comments
        if (line.empty() || line[0] == '#') {
            continue;
        }
        
        // Parse format: topology_name=bdp_value
        size_t pos = line.find('=');
        if (pos != std::string::npos) {
            std::string topo_name = line.substr(0, pos);
            std::string bdp_str = line.substr(pos + 1);
            
            // Trim whitespace
            topo_name.erase(0, topo_name.find_first_not_of(" \t"));
            topo_name.erase(topo_name.find_last_not_of(" \t") + 1);
            bdp_str.erase(0, bdp_str.find_first_not_of(" \t"));
            bdp_str.erase(bdp_str.find_last_not_of(" \t") + 1);
            
            try {
                uint32_t bdp_value = std::stoul(bdp_str);
                mapping[topo_name] = bdp_value;
            } catch (const std::exception& e) {
                std::cerr << "Warning: Invalid BDP value for " << topo_name << ": " << bdp_str << std::endl;
            }
        }
    }
    
    file.close();
    std::cout << "Loaded BDP mapping from " << config_path << " with " << mapping.size() << " entries" << std::endl;
    return mapping;
}

// Global BDP mapping (loaded once)
static std::map<std::string, uint32_t> topo2bdpMap = load_bdp_mapping();

// Function to get BDP for a topology name
// Returns 0 if topology not found
inline uint32_t get_bdp(const std::string& topo_name) {
    auto it = topo2bdpMap.find(topo_name);
    return (it != topo2bdpMap.end()) ? it->second : 0;
}

// Function to find BDP by partial topology file path matching
// Returns 0 if no match found
inline uint32_t find_bdp_by_path(const std::string& topology_file) {
    for (const auto& pair : topo2bdpMap) {
        if (topology_file.find(pair.first) != std::string::npos) {
            return pair.second;
        }
    }
    return 0;
}

// Function to reload BDP mapping (useful for testing)
inline void reload_bdp_mapping() {
    topo2bdpMap = load_bdp_mapping();
}

#endif // TOPO_BDP_H