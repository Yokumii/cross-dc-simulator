#!/bin/bash

cecho(){  # 简单彩色输出
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    NC="\033[0m" # No Color
    printf "${!1}${2} ${NC}\n"
}

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"

# 可选：环境变量或参数控制基础运行时间与负载（留空则用脚本内默认）
SIM_TIME=${SIM_TIME:-"0.02"}
INTRA_LOAD=${INTRA_LOAD:-"0.5"}
INTER_LOAD=${INTER_LOAD:-"0.2"}
K_FAT=${K_FAT:-"4"}
NUM_DC=${NUM_DC:-"2"}
INTRA_BW=${INTRA_BW:-"100"}
INTER_BW=${INTER_BW:-"400"}
FLOW_SCALE=${FLOW_SCALE:-"10.0"}

RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="run_cross_dc_quick"
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RUN_DIR}"

cecho "GREEN" "Running lossy cross-dc simulation (PFC off, IRN on)"
cecho "YELLOW" "simul_time=${SIM_TIME}, intra_load=${INTRA_LOAD}, inter_load=${INTER_LOAD}"

# 记录运行前已有的输出ID
pre_ids=$(ls -1 "${SIM_DIR}/mix/output" 2>/dev/null || true)

pushd "${SIM_DIR}" >/dev/null

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

# 移动新增的输出ID到 results 目录
post_ids=$(ls -1 "${SIM_DIR}/mix/output" 2>/dev/null || true)
for id in ${post_ids}; do
  if ! echo "${pre_ids}" | grep -qx "${id}"; then
    if [ -d "${SIM_DIR}/mix/output/${id}" ]; then
      mv "${SIM_DIR}/mix/output/${id}" "${RUN_DIR}/" 2>/dev/null || cp -r "${SIM_DIR}/mix/output/${id}" "${RUN_DIR}/" 
    fi
  fi
done

cecho "GREEN" "Outputs saved to: ${RUN_DIR}"
