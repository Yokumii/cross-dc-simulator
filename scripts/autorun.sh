#!/bin/bash

cecho(){  # source: https://stackoverflow.com/a/53463162/2886168
    RED="\033[0;31m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    NC="\033[0m" # No Color
    printf "${!1}${2} ${NC}\n"
}

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"
RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="autorun"
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RUN_DIR}"

cecho "GREEN" "Running RDMA Network Load Balancing Simulations (leaf-spine topology)"

TOPOLOGY="leaf_spine_128_100G_OS2" # or, fat_k8_100G_OS2
NETLOAD="50" # network load 50%
RUNTIME="0.1" # 0.1 second (traffic generation)

cecho "YELLOW" "\n----------------------------------"
cecho "YELLOW" "TOPOLOGY: ${TOPOLOGY}"
cecho "YELLOW" "NETWORK LOAD: ${NETLOAD}"
cecho "YELLOW" "TIME: ${RUNTIME}"
cecho "YELLOW" "----------------------------------\n"

pushd "${SIM_DIR}" >/dev/null

# Lossless RDMA
cecho "GREEN" "Run Lossless RDMA experiments..."
python3 run.py --lb fecmp --pfc 1 --irn 0 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 5
python3 run.py --lb letflow --pfc 1 --irn 0 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1
python3 run.py --lb conga --pfc 1 --irn 0 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1
python3 run.py --lb conweave --pfc 1 --irn 0 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1

# IRN RDMA
cecho "GREEN" "Run IRN RDMA experiments..."
python3 run.py --lb fecmp --pfc 0 --irn 1 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 5
python3 run.py --lb letflow --pfc 0 --irn 1 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1
python3 run.py --lb conga --pfc 0 --irn 1 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1
python3 run.py --lb conweave --pfc 0 --irn 1 --simul_time ${RUNTIME} --netload ${NETLOAD} --topo ${TOPOLOGY} &
sleep 0.1

popd >/dev/null

cecho "GREEN" "Runing all in parallel."

# 记录运行前已有的输出ID（本脚本不能精确匹配多并发ID，采用整体搬运）
if [ -d "${SIM_DIR}/mix/output" ]; then
  mkdir -p "${RUN_DIR}/outputs"
  # 拷贝后清空，避免重复累计
  cp -r "${SIM_DIR}/mix/output"/* "${RUN_DIR}/outputs/" 2>/dev/null || true
fi