#!/bin/bash

cecho(){  # 简单彩色输出
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    NC="\033[0m" # No Color
    printf "${!1}${2} ${NC}\n"
}

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"

# cross_dc 运行开关：默认按跨 DC lossy 场景配置（PFC off, IRN on）
PFC_ENABLED=0
IRN_ENABLED=1

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --pfc)
      PFC_ENABLED="$2"
      shift 2
      ;;
    --irn)
      IRN_ENABLED="$2"
      shift 2
      ;;
    --simul-time)
      SIM_TIME="$2"
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
    --k-fat)
      K_FAT="$2"
      shift 2
      ;;
    --num-dc)
      NUM_DC="$2"
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
    --flow-scale)
      FLOW_SCALE="$2"
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
    --intra-latency)
      INTRA_LATENCY="$2"
      shift 2
      ;;
    --inter-latency)
      INTER_LATENCY="$2"
      shift 2
      ;;
    --fec-enabled)
      FEC_ENABLED="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo "Options:"
      echo "  --pfc 0|1           Enable PFC (default: 0)"
      echo "  --irn 0|1           Enable IRN (default: 1)"
      echo "  --simul-time TIME     Simulation time (default: 0.02)"
      echo "  --intra-load LOAD     Intra-DC load (default: 0.5)"
      echo "  --inter-load LOAD     Inter-DC load (default: 0.2)"
      echo "  --k-fat K             Fat-tree k value (default: 4)"
      echo "  --num-dc DC           Number of datacenters (default: 2)"
      echo "  --intra-bw BW         Intra-DC bandwidth in Gbps (default: 100)"
      echo "  --inter-bw BW         Inter-DC bandwidth in Gbps (default: 400)"
      echo "  --flow-scale SCALE    Flow scale factor (default: 10.0)"
      echo "  --intra-error RATE    Intra-DC link error rate (default: 0.0)"
      echo "  --inter-error RATE    Inter-DC link error rate (default: 0.0)"
      echo "  --intra-latency NS    Intra-DC link latency in ns (default: 1000 - 1us)"
      echo "  --inter-latency NS    Inter-DC link latency in ns (default: 400000 - 400us)"
      echo "  --fec-enabled 0|1     Enable FEC (default: 0)"
      echo "  -h, --help            Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# 参数校验
if [[ "${PFC_ENABLED}" != "0" && "${PFC_ENABLED}" != "1" ]]; then
  echo "Invalid --pfc: ${PFC_ENABLED} (expected: 0|1)"
  exit 1
fi
if [[ "${IRN_ENABLED}" != "0" && "${IRN_ENABLED}" != "1" ]]; then
  echo "Invalid --irn: ${IRN_ENABLED} (expected: 0|1)"
  exit 1
fi

# 可选：环境变量或参数控制基础运行时间与负载（留空则用脚本内默认）
SIM_TIME=${SIM_TIME:-"0.02"}
INTRA_LOAD=${INTRA_LOAD:-"0.5"}
INTER_LOAD=${INTER_LOAD:-"0.2"}
K_FAT=${K_FAT:-"4"}
NUM_DC=${NUM_DC:-"2"}
INTRA_BW=${INTRA_BW:-"100"}
INTER_BW=${INTER_BW:-"400"}
FLOW_SCALE=${FLOW_SCALE:-"10.0"}
INTRA_ERROR=${INTRA_ERROR:-"0.0"}
INTER_ERROR=${INTER_ERROR:-"0.05"}
INTRA_LATENCY=${INTRA_LATENCY:-"1000"}
INTER_LATENCY=${INTER_LATENCY:-"400000"}
FEC_ENABLED=${FEC_ENABLED:-"0"}

RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="run_cross_dc_quick"
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RUN_DIR}"

cecho "GREEN" "Running lossy cross-dc simulation (PFC=${PFC_ENABLED}, IRN=${IRN_ENABLED}, FEC=${FEC_ENABLED})"
cecho "YELLOW" "simul_time=${SIM_TIME}, intra_load=${INTRA_LOAD}, inter_load=${INTER_LOAD}"
cecho "YELLOW" "intra_error=${INTRA_ERROR}, inter_error=${INTER_ERROR}"
cecho "YELLOW" "intra_latency=${INTRA_LATENCY}ns, inter_latency=${INTER_LATENCY}ns"

# 记录运行前已有的输出ID
pre_ids=$(ls -1 "${SIM_DIR}/mix/output" 2>/dev/null || true)

pushd "${SIM_DIR}" >/dev/null

python3 run_cross_dc.py \
  --pfc "${PFC_ENABLED}" \
  --irn "${IRN_ENABLED}" \
  --fec-enabled "${FEC_ENABLED}" \
  --simul_time "${SIM_TIME}" \
  --intra-load "${INTRA_LOAD}" \
  --inter-load "${INTER_LOAD}" \
  --k-fat "${K_FAT}" \
  --num-dc "${NUM_DC}" \
  --intra-bw "${INTRA_BW}" \
  --inter-bw "${INTER_BW}" \
  --flow-scale "${FLOW_SCALE}" \
  --intra-error "${INTRA_ERROR}" \
  --inter-error "${INTER_ERROR}" \
  --intra-latency "${INTRA_LATENCY}" \
  --inter-latency "${INTER_LATENCY}"

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
