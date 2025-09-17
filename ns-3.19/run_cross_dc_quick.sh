#!/bin/bash

cecho(){  # 简单彩色输出
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    NC="\033[0m" # No Color
    printf "${!1}${2} ${NC}\n"
}

# 可选：环境变量或参数控制基础运行时间与负载（留空则用脚本内默认）
SIM_TIME=${SIM_TIME:-"0.02"}
INTRA_LOAD=${INTRA_LOAD:-"0.5"}
INTER_LOAD=${INTER_LOAD:-"0.2"}
K_FAT=${K_FAT:-"4"}
NUM_DC=${NUM_DC:-"2"}
INTRA_BW=${INTRA_BW:-"100"}
INTER_BW=${INTER_BW:-"400"}
FLOW_SCALE=${FLOW_SCALE:-"10.0"}

cecho "GREEN" "Running lossy cross-dc simulation (PFC off, IRN on)"
cecho "YELLOW" "simul_time=${SIM_TIME}, intra_load=${INTRA_LOAD}, inter_load=${INTER_LOAD}"

pushd "$(dirname "$0")" >/dev/null

python3 run_cross_dc.py \
  --pfc 0 \
  --irn 1 \
  --simul_time "${SIM_TIME}" \
  --intra-load "${INTRA_LOAD}" \
  --inter-load "${INTER_LOAD}" \
  --k-fat "${K_FAT}" \
  --num-dc "${NUM_DC}" \
  --intra-bw "${INTRA_BW}" \
  --inter-bw "${INTER_BW}" \
  --flow-scale "${FLOW_SCALE}"

popd >/dev/null

