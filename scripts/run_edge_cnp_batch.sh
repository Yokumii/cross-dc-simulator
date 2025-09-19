#!/bin/bash
# cross-datacenter simulation batch script
# run both with and without EdgeCNP in background

# check if screen is installed
if ! command -v screen &> /dev/null; then
    echo "Error: screen is not installed. Please install it using 'apt-get install screen'."
    exit 1
fi

# set default parameters
K_FAT=4
NUM_DC=2
SIMUL_TIME=0.01
INTRA_LOAD=0.5
INTER_LOAD=0.2
INTRA_BW=100
INTER_BW=400
INTRA_ERROR=0.0
INTER_ERROR=0.0
BUFFER=16
DCI_BUFFER=128
CC="dcqcn"
LB="fecmp"
FLOW_SCALE=10.0
TRAFFIC_TYPE="mixed"  # default to mixed traffic

# parse command line parameters
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --k-fat)
            K_FAT="$2"
            shift 2
            ;;
        --num-dc)
            NUM_DC="$2"
            shift 2
            ;;
        --simul_time)
            SIMUL_TIME="$2"
            shift 2
            ;;
        --intra-load)
            INTRA_LOAD="$2"
            shift 2
            ;;
        --inter-load)
            INTER_LOAD="$2"
            shift 2
            ;;
        --intra-bw)
            INTRA_BW="$2"
            shift 2
            ;;
        --inter-bw)
            INTER_BW="$2"
            shift 2
            ;;
        --intra-error)
            INTRA_ERROR="$2"
            shift 2
            ;;
        --inter-error)
            INTER_ERROR="$2"
            shift 2
            ;;
        --buffer)
            BUFFER="$2"
            shift 2
            ;;
        --dci-buffer)
            DCI_BUFFER="$2"
            shift 2
            ;;
        --cc)
            CC="$2"
            shift 2
            ;;
        --lb)
            LB="$2"
            shift 2
            ;;
        --flow-scale)
            FLOW_SCALE="$2"
            shift 2
            ;;
        --traffic-type)
            TRAFFIC_TYPE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done

# show parameter information
echo "Running cross-datacenter simulations with the following parameters:"
echo "Fat-tree K: $K_FAT"
echo "Number of datacenters: $NUM_DC"
echo "Simulation time: $SIMUL_TIME s"
echo "Intra-datacenter load: $INTRA_LOAD"
echo "Inter-datacenter load: $INTER_LOAD"
echo "Intra-datacenter bandwidth: $INTRA_BW Gbps"
echo "Inter-datacenter bandwidth: $INTER_BW Gbps"
echo "Intra-datacenter error rate: $INTRA_ERROR"
echo "Inter-datacenter error rate: $INTER_ERROR"
echo "Buffer size: $BUFFER MB"
echo "DCI buffer size: $DCI_BUFFER MB"
echo "Congestion control: $CC"
echo "Load balancing: $LB"
echo "Flow scale factor: $FLOW_SCALE"
echo "Traffic type: $TRAFFIC_TYPE"

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"
RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="run_edge_cnp_batch"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_${TIMESTAMP}"
mkdir -p "${RUN_DIR}"

# define file paths
# Create topology filename with all parameters
TOPO_PARTS=(
    "cross_dc_k${K_FAT}_dc${NUM_DC}_os2"
    "ib${INTRA_BW}"
    "il0.0001"  # intra latency is fixed at 0.0001ms for edge CNP
    "eb${INTER_BW}"
    "el0.04"    # inter latency is fixed at 0.04ms for edge CNP
)

# Add error rates if they are greater than 0
if (( $(echo "$INTRA_ERROR > 0" | bc -l) )) || (( $(echo "$INTER_ERROR > 0" | bc -l) )); then
    TOPO_PARTS+=("ie${INTRA_ERROR}")
    TOPO_PARTS+=("ee${INTER_ERROR}")
fi

TOPO=$(IFS="_"; echo "${TOPO_PARTS[*]}")
TOPO_FILE="${SIM_DIR}/config/${TOPO}.txt"
FLOW_FILE="${SIM_DIR}/config/${TOPO}_${TRAFFIC_TYPE}_flow.txt"

# check and generate topology file if needed
if [ -f "$TOPO_FILE" ]; then
    echo "Topology file $TOPO_FILE already exists, skipping generation."
else
    echo "Generating topology file $TOPO_FILE..."
        (cd "$SIM_DIR" && python3 ../tools/topology_gen/cross_dc_topology_gen.py $K_FAT 2 $NUM_DC $INTRA_BW 0.0001 $INTER_BW 0.04 $INTRA_ERROR $INTER_ERROR)
    if [ $? -eq 0 ]; then
        echo "Topology file generated successfully."
    else
        echo "Error: Failed to generate topology file. Check $LOG_DIR/topology_gen.log for details."
        exit 1
    fi
fi

# ensure topology file exists before proceeding
if [ ! -f "$TOPO_FILE" ]; then
    echo "Error: Topology file $TOPO_FILE does not exist. Cannot proceed."
    exit 1
fi

# check and generate traffic file if needed
if [ -f "$FLOW_FILE" ]; then
    echo "Traffic file $FLOW_FILE already exists, skipping generation."
else
    echo "Generating $TRAFFIC_TYPE traffic file $FLOW_FILE..."
    if [ "$TRAFFIC_TYPE" == "mixed" ]; then
        (cd "$SIM_DIR" && python3 ../tools/traffic_gen/cross_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --inter-load $INTER_LOAD --intra-bw $INTRA_BW --inter-bw $INTER_BW -t $SIMUL_TIME -c ../tools/traffic_gen/AliStorage2019.txt -o "$FLOW_FILE" --flow-scale $FLOW_SCALE)
    else
        (cd "$SIM_DIR" && python3 ../tools/traffic_gen/intra_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --intra-bw $INTRA_BW -t $SIMUL_TIME -c ../tools/traffic_gen/AliStorage2019.txt -o "$FLOW_FILE" --flow-scale $FLOW_SCALE)
    fi
    
    if [ $? -eq 0 ]; then
        echo "Traffic file generated successfully."
    else
        echo "Error: Failed to generate traffic file. Check $LOG_DIR/traffic_gen.log for details."
        exit 1
    fi
fi

# ensure traffic file exists before proceeding
if [ ! -f "$FLOW_FILE" ]; then
    echo "Error: Required traffic file does not exist. Cannot proceed."
    exit 1
fi

echo "All required files are ready. Starting simulations..."
sleep 1

# 记录运行前已有的输出ID
pre_ids=$(ls -1 "${SIM_DIR}/mix/output" 2>/dev/null || true)

# start simulation without EdgeCNP
echo "Starting simulation WITHOUT EdgeCNP..."
screen -dmS without_edgecnp bash -c "cd ${SIM_DIR} && python3 run_cross_dc.py \
    --traffic-type $TRAFFIC_TYPE \
    --k-fat $K_FAT \
    --num-dc $NUM_DC \
    --simul_time $SIMUL_TIME \
    --intra-load $INTRA_LOAD \
    --inter-load $INTER_LOAD \
    --intra-bw $INTRA_BW \
    --inter-bw $INTER_BW \
    --buffer $BUFFER \
    --dci-buffer $DCI_BUFFER \
    --cc $CC \
    --lb $LB \
    --flow-scale $FLOW_SCALE \
    --enable-edge-cnp 0 \
    2>&1 | cat"

# start simulation with EdgeCNP
echo "Starting simulation WITH EdgeCNP..."
screen -dmS with_edgecnp bash -c "cd ${SIM_DIR} && python3 run_cross_dc.py \
    --traffic-type $TRAFFIC_TYPE \
    --k-fat $K_FAT \
    --num-dc $NUM_DC \
    --simul_time $SIMUL_TIME \
    --intra-load $INTRA_LOAD \
    --inter-load $INTER_LOAD \
    --intra-bw $INTRA_BW \
    --inter-bw $INTER_BW \
    --buffer $BUFFER \
    --dci-buffer $DCI_BUFFER \
    --cc $CC \
    --lb $LB \
    --flow-scale $FLOW_SCALE \
    --enable-edge-cnp 1 \
    2>&1 | cat"

echo "Simulations started in background screen sessions."
echo "To attach to the sessions, use:"
echo "  screen -r without_edgecnp  # For simulation without EdgeCNP"
echo "  screen -r with_edgecnp     # For simulation with EdgeCNP"
echo "To detach from a session, press Ctrl+A followed by D"
echo "Outputs will be archived to $RUN_DIR"

# create a summary file in the log directory
cat > "$RUN_DIR/simulation_summary.txt" << EOF
Cross-datacenter Simulation Summary
==================================
Date and Time: $(date)
Topology: $TOPO
Topology File: $TOPO_FILE
Traffic File: $FLOW_FILE
Traffic Type: $TRAFFIC_TYPE

Parameters:
- Fat-tree K: $K_FAT
- Number of datacenters: $NUM_DC
- Simulation time: $SIMUL_TIME s
- Intra-datacenter load: $INTRA_LOAD
- Inter-datacenter load: $INTER_LOAD
- Intra-datacenter bandwidth: $INTRA_BW Gbps
- Inter-datacenter bandwidth: $INTER_BW Gbps
- Buffer size: $BUFFER MB
- DCI buffer size: $DCI_BUFFER MB
- Congestion control: $CC
- Load balancing: $LB
- Flow scale factor: $FLOW_SCALE

Comparison:
- Simulation 1: WITHOUT EdgeCNP (--enable-edge-cnp 0)
- Simulation 2: WITH EdgeCNP (--enable-edge-cnp 1)
EOF

echo "Summary information saved to $RUN_DIR/simulation_summary.txt"

# 移动新增的输出ID到 RUN_DIR
post_ids=$(ls -1 "${SIM_DIR}/mix/output" 2>/dev/null || true)
for id in ${post_ids}; do
  if ! echo "${pre_ids}" | grep -qx "${id}"; then
    if [ -d "${SIM_DIR}/mix/output/${id}" ]; then
      mkdir -p "${RUN_DIR}/outputs"
      mv "${SIM_DIR}/mix/output/${id}" "${RUN_DIR}/outputs/" 2>/dev/null || cp -r "${SIM_DIR}/mix/output/${id}" "${RUN_DIR}/outputs/"
    fi
  fi
done

echo "Outputs saved to: ${RUN_DIR}"