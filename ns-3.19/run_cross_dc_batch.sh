#!/bin/bash
# cross-datacenter simulation batch script
# run both intra-only and mixed simulations in background

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
BUFFER=16
DCI_BUFFER=128
CC="dcqcn"
LB="fecmp"

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
echo "Buffer size: $BUFFER MB"
echo "DCI buffer size: $DCI_BUFFER MB"
echo "Congestion control: $CC"
echo "Load balancing: $LB"

# create log directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="simulation_logs_${TIMESTAMP}"
mkdir -p $LOG_DIR

# define file paths
TOPO="cross_dc_k${K_FAT}_dc${NUM_DC}_os2"
TOPO_FILE="config/${TOPO}.txt"
INTRA_FLOW_FILE="config/${TOPO}_intra_only_flow.txt"
MIXED_FLOW_FILE="config/${TOPO}_mixed_flow.txt"

# check and generate topology file if needed
if [ -f "$TOPO_FILE" ]; then
    echo "Topology file $TOPO_FILE already exists, skipping generation."
else
    echo "Generating topology file $TOPO_FILE..."
    python3 config/cross_dc_topology_gen.py $K_FAT 2 $NUM_DC $INTRA_BW 0.01 $INTER_BW 4 > $LOG_DIR/topology_gen.log 2>&1
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

# check and generate intra-only traffic file if needed
if [ -f "$INTRA_FLOW_FILE" ]; then
    echo "Intra-only traffic file $INTRA_FLOW_FILE already exists, skipping generation."
else
    echo "Generating intra-only traffic file $INTRA_FLOW_FILE..."
    python3 traffic_gen/intra_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --intra-bw $INTRA_BW -t $SIMUL_TIME -c traffic_gen/AliStorage2019.txt -o $INTRA_FLOW_FILE > $LOG_DIR/intra_traffic_gen.log 2>&1
    if [ $? -eq 0 ]; then
        echo "Intra-only traffic file generated successfully."
    else
        echo "Error: Failed to generate intra-only traffic file. Check $LOG_DIR/intra_traffic_gen.log for details."
        exit 1
    fi
fi

# check and generate mixed traffic file if needed
if [ -f "$MIXED_FLOW_FILE" ]; then
    echo "Mixed traffic file $MIXED_FLOW_FILE already exists, skipping generation."
else
    echo "Generating mixed traffic file $MIXED_FLOW_FILE..."
    python3 traffic_gen/cross_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --inter-load $INTER_LOAD --intra-bw $INTRA_BW --inter-bw $INTER_BW -t $SIMUL_TIME -c traffic_gen/AliStorage2019.txt -o $MIXED_FLOW_FILE > $LOG_DIR/mixed_traffic_gen.log 2>&1
    if [ $? -eq 0 ]; then
        echo "Mixed traffic file generated successfully."
    else
        echo "Error: Failed to generate mixed traffic file. Check $LOG_DIR/mixed_traffic_gen.log for details."
        exit 1
    fi
fi

# ensure traffic files exist before proceeding
if [ ! -f "$INTRA_FLOW_FILE" ] || [ ! -f "$MIXED_FLOW_FILE" ]; then
    echo "Error: Required traffic files do not exist. Cannot proceed."
    exit 1
fi

echo "All required files are ready. Starting simulations..."
sleep 1

# start intra-only simulation
echo "Starting intra-only simulation..."
screen -dmS intra_only bash -c "cd $(pwd) && python3 run_cross_dc.py \
    --traffic-type intra_only \
    --k-fat $K_FAT \
    --num-dc $NUM_DC \
    --simul_time $SIMUL_TIME \
    --intra-load $INTRA_LOAD \
    --intra-bw $INTRA_BW \
    --inter-bw $INTER_BW \
    --buffer $BUFFER \
    --dci-buffer $DCI_BUFFER \
    --cc $CC \
    --lb $LB \
    2>&1 | tee $LOG_DIR/intra_only.log"

# start mixed simulation
echo "Starting mixed simulation..."
screen -dmS mixed bash -c "cd $(pwd) && python3 run_cross_dc.py \
    --traffic-type mixed \
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
    2>&1 | tee $LOG_DIR/mixed.log"

echo "Simulations started in background screen sessions."
echo "To attach to the sessions, use:"
echo "  screen -r intra_only  # For intra-datacenter only simulation"
echo "  screen -r mixed       # For mixed simulation"
echo "To detach from a session, press Ctrl+A followed by D"
echo "Logs are being saved to $LOG_DIR/"