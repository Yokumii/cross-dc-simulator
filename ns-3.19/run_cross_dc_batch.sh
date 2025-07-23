#!/bin/bash
# 跨数据中心模拟批处理脚本
# 同时在后台运行单独intra和混跑的场景

# 检查screen是否安装
if ! command -v screen &> /dev/null; then
    echo "Error: screen is not installed. Please install it using 'apt-get install screen'."
    exit 1
fi

# 设置默认参数
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

# 解析命令行参数
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

# 显示参数信息
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

# 创建日志目录
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="simulation_logs_${TIMESTAMP}"
mkdir -p $LOG_DIR

# 生成拓扑文件（只需生成一次）
echo "Generating topology..."
python3 config/cross_dc_topology_gen.py $K_FAT 2 $NUM_DC $INTRA_BW 0.01 $INTER_BW 4 > $LOG_DIR/topology_gen.log 2>&1

# 确保拓扑文件已经完全生成
sleep 2

# 预先生成流量文件，避免同时访问冲突
echo "Generating traffic files..."
TOPO="cross_dc_k${K_FAT}_dc${NUM_DC}_os2"

# 生成intra-only流量
echo "Generating intra-only traffic..."
python3 traffic_gen/intra_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --intra-bw $INTRA_BW -t $SIMUL_TIME -c traffic_gen/AliStorage2019.txt -o config/${TOPO}_intra_only_flow.txt > $LOG_DIR/intra_traffic_gen.log 2>&1

# 生成mixed流量
echo "Generating mixed traffic..."
python3 traffic_gen/cross_dc_traffic_gen.py -k $K_FAT -d $NUM_DC --intra-load $INTRA_LOAD --inter-load $INTER_LOAD --intra-bw $INTRA_BW --inter-bw $INTER_BW -t $SIMUL_TIME -c traffic_gen/AliStorage2019.txt -o config/${TOPO}_mixed_flow.txt > $LOG_DIR/mixed_traffic_gen.log 2>&1

# 确保流量文件已经完全生成
sleep 2

# 启动intra-only场景的screen会话
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

# 启动mixed场景的screen会话
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