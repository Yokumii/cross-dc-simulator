#!/bin/bash
# FEC性能对比实验 - 并行运行多个仿真
# 对比不同inter-dc链路错误率下，FEC开启和关闭的性能差异

cecho(){
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    CYAN="\033[0;36m"
    RED="\033[0;31m"
    NC="\033[0m"
    printf "${!1}${2} ${NC}\n"
}

# 检查 screen 是否安装
if ! command -v screen &> /dev/null; then
    cecho "RED" "错误: 未安装 screen。请使用 'apt-get install screen' 或 'yum install screen' 安装。"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"
RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="fec_comparison_parallel"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_${TIMESTAMP}"
mkdir -p "${RUN_DIR}"

# 固定的仿真参数（基于 run_cross_dc_fec_quick.sh）
SIM_TIME="0.02"
INTRA_LOAD="0.5"
INTER_LOAD="0.2"
K_FAT="4"
NUM_DC="2"
INTRA_BW="100"
INTER_BW="400"
FLOW_SCALE="10.0"
INTRA_ERROR="0.0"
INTRA_LATENCY="1000"
INTER_LATENCY="400000"
FEC_BLOCK_SIZE="64"
FEC_INTERLEAVING_DEPTH="8"

# 要测试的 inter-dc 错误率（科学计数法）
ERROR_RATES=("0.0001" "0.001" "0.01")  # 10^-4, 10^-3, 10^-2
ERROR_LABELS=("1e-4" "1e-3" "1e-2")

# FEC 配置
FEC_CONFIGS=("0" "1")  # 0=关闭, 1=开启
FEC_LABELS=("no-fec" "with-fec")

cecho "CYAN" "==========================================="
cecho "CYAN" "   FEC 性能对比实验 - 并行运行"
cecho "CYAN" "==========================================="
echo ""
cecho "GREEN" "实验配置:"
echo "  · 仿真时间: ${SIM_TIME}s"
echo "  · 拓扑: Fat-tree k=${K_FAT}, 数据中心数=${NUM_DC}"
echo "  · 负载: intra=${INTRA_LOAD}, inter=${INTER_LOAD}"
echo "  · 带宽: intra=${INTRA_BW}Gbps, inter=${INTER_BW}Gbps"
echo "  · 延迟: intra=${INTRA_LATENCY}ns, inter=${INTER_LATENCY}ns"
echo "  · FEC参数: block_size=${FEC_BLOCK_SIZE}, depth=${FEC_INTERLEAVING_DEPTH}"
echo ""
cecho "YELLOW" "测试场景 (共6个):"
for i in "${!ERROR_RATES[@]}"; do
    error_rate="${ERROR_RATES[$i]}"
    error_label="${ERROR_LABELS[$i]}"
    echo "  · Inter-DC错误率 ${error_label}:"
    echo "      - 场景 $(( i*2 + 1 )): 无FEC"
    echo "      - 场景 $(( i*2 + 2 )): 启用FEC"
done
echo ""
cecho "GREEN" "结果保存目录: ${RUN_DIR}"
echo ""

# 创建实验汇总文件
cat > "${RUN_DIR}/experiment_plan.txt" << EOF
FEC性能对比实验
==============
时间: $(date)
脚本: $0

固定参数:
---------
仿真时间: ${SIM_TIME}s
Intra-DC负载: ${INTRA_LOAD}
Inter-DC负载: ${INTER_LOAD}
Fat-tree K: ${K_FAT}
数据中心数量: ${NUM_DC}
Intra-DC带宽: ${INTRA_BW} Gbps
Inter-DC带宽: ${INTER_BW} Gbps
Flow scale: ${FLOW_SCALE}
Intra-DC错误率: ${INTRA_ERROR}
Intra-DC延迟: ${INTRA_LATENCY} ns
Inter-DC延迟: ${INTER_LATENCY} ns
FEC block size: ${FEC_BLOCK_SIZE}
FEC interleaving depth: ${FEC_INTERLEAVING_DEPTH}

测试场景:
---------
EOF

# 启动所有仿真任务
task_num=0
for i in "${!ERROR_RATES[@]}"; do
    error_rate="${ERROR_RATES[$i]}"
    error_label="${ERROR_LABELS[$i]}"

    for j in "${!FEC_CONFIGS[@]}"; do
        fec_enabled="${FEC_CONFIGS[$j]}"
        fec_label="${FEC_LABELS[$j]}"

        ((task_num++))

        # 生成任务标识
        task_id="err_${error_label}_${fec_label}"
        screen_name="fec_${task_num}_${task_id}"

        # 记录到实验计划
        echo "场景 ${task_num}: inter_error=${error_rate}, FEC=${fec_enabled}" >> "${RUN_DIR}/experiment_plan.txt"

        # 创建任务专属输出目录
        task_dir="${RUN_DIR}/${task_id}"
        mkdir -p "${task_dir}"

        # 启动 screen 会话运行仿真
        cecho "YELLOW" "[$(date +'%H:%M:%S')] 启动场景 ${task_num}/${#ERROR_RATES[@]*#FEC_CONFIGS[@]}: ${task_id}"

        screen -dmS "${screen_name}" bash -c "
            cd '${SIM_DIR}'

            echo '=========================================' | tee '${task_dir}/simulation.log'
            echo '场景: ${task_id}' | tee -a '${task_dir}/simulation.log'
            echo 'Inter-DC错误率: ${error_rate}' | tee -a '${task_dir}/simulation.log'
            echo 'FEC启用: ${fec_enabled}' | tee -a '${task_dir}/simulation.log'
            echo '开始时间: $(date)' | tee -a '${task_dir}/simulation.log'
            echo '=========================================' | tee -a '${task_dir}/simulation.log'
            echo '' | tee -a '${task_dir}/simulation.log'

            # 记录运行前的输出ID
            pre_ids=\$(ls -1 mix/output 2>/dev/null || true)

            # 运行仿真
            python3 run_cross_dc.py \\
                --pfc 1 \\
                --irn 0 \\
                --simul_time '${SIM_TIME}' \\
                --intra-load '${INTRA_LOAD}' \\
                --inter-load '${INTER_LOAD}' \\
                --k-fat '${K_FAT}' \\
                --num-dc '${NUM_DC}' \\
                --intra-bw '${INTRA_BW}' \\
                --inter-bw '${INTER_BW}' \\
                --flow-scale '${FLOW_SCALE}' \\
                --intra-error '${INTRA_ERROR}' \\
                --inter-error '${error_rate}' \\
                --intra-latency '${INTRA_LATENCY}' \\
                --inter-latency '${INTER_LATENCY}' \\
                --fec-enabled '${fec_enabled}' \\
                --fec-block-size '${FEC_BLOCK_SIZE}' \\
                --fec-interleaving-depth '${FEC_INTERLEAVING_DEPTH}' \\
                2>&1 | tee -a '${task_dir}/simulation.log'

            exit_code=\$?

            # 移动输出结果
            post_ids=\$(ls -1 mix/output 2>/dev/null || true)
            for id in \${post_ids}; do
                if ! echo \"\${pre_ids}\" | grep -qx \"\${id}\"; then
                    if [ -d \"mix/output/\${id}\" ]; then
                        mv \"mix/output/\${id}\" '${task_dir}/' 2>/dev/null || cp -r \"mix/output/\${id}\" '${task_dir}/'
                        echo \"输出已移动到: ${task_dir}/\${id}\" | tee -a '${task_dir}/simulation.log'
                    fi
                fi
            done

            echo '' | tee -a '${task_dir}/simulation.log'
            echo '=========================================' | tee -a '${task_dir}/simulation.log'
            if [ \$exit_code -eq 0 ]; then
                echo '✓ 仿真成功完成' | tee -a '${task_dir}/simulation.log'
            else
                echo '✗ 仿真失败 (退出码: '\$exit_code')' | tee -a '${task_dir}/simulation.log'
            fi
            echo '结束时间: $(date)' | tee -a '${task_dir}/simulation.log'
            echo '=========================================' | tee -a '${task_dir}/simulation.log'

            # 创建完成标记
            if [ \$exit_code -eq 0 ]; then
                touch '${task_dir}/.completed'
            else
                touch '${task_dir}/.failed'
            fi
        "

        # 短暂延迟，避免同时启动造成资源竞争
        sleep 2
    done
done

echo ""
cecho "GREEN" "==========================================="
cecho "GREEN" "所有仿真任务已启动！"
cecho "GREEN" "==========================================="
echo ""
cecho "CYAN" "监控命令:"
echo "  · 查看所有 screen 会话:"
echo "      screen -ls"
echo ""
echo "  · 连接到特定场景 (例如场景1):"
echo "      screen -r fec_1_err_1e-4_no-fec"
echo ""
echo "  · 从 screen 会话中退出 (不关闭):"
echo "      按 Ctrl+A 然后按 D"
echo ""
echo "  · 实时监控所有任务进度:"
echo "      watch -n 5 'ls -lh ${RUN_DIR}/*/simulation.log 2>/dev/null'"
echo ""
echo "  · 检查完成状态:"
echo "      ls ${RUN_DIR}/*/.completed ${RUN_DIR}/*/.failed 2>/dev/null"
echo ""
cecho "YELLOW" "结果目录: ${RUN_DIR}"
echo ""

# 创建监控脚本
cat > "${RUN_DIR}/check_status.sh" << 'EOF'
#!/bin/bash
# 检查所有仿真任务的状态

RUN_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "FEC对比实验 - 任务状态检查"
echo "========================================="
echo ""

total=0
completed=0
failed=0
running=0

for task_dir in "$RUN_DIR"/err_*; do
    if [ -d "$task_dir" ]; then
        ((total++))
        task_name=$(basename "$task_dir")

        if [ -f "$task_dir/.completed" ]; then
            echo "✓ $task_name - 已完成"
            ((completed++))
        elif [ -f "$task_dir/.failed" ]; then
            echo "✗ $task_name - 失败"
            ((failed++))
        else
            echo "⟳ $task_name - 运行中"
            ((running++))
        fi
    fi
done

echo ""
echo "========================================="
echo "总计: $total 个任务"
echo "  · 已完成: $completed"
echo "  · 运行中: $running"
echo "  · 失败: $failed"
echo "========================================="

if [ $completed -eq $total ]; then
    echo ""
    echo "🎉 所有任务已完成！可以开始分析结果。"
fi
EOF

chmod +x "${RUN_DIR}/check_status.sh"

cecho "GREEN" "提示: 可以运行以下命令检查状态"
echo "  ${RUN_DIR}/check_status.sh"
echo ""
