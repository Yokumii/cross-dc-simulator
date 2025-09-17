#!/bin/bash

set -e
ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"

# 清理 mix/output 下内容（保留目录本身）
OUT_DIR="${SIM_DIR}/mix/output"
if [ -d "${OUT_DIR}" ]; then
  # 删除普通项
  if compgen -A file ${OUT_DIR}/* >/dev/null 2>&1; then
    rm -rf ${OUT_DIR}/*
  fi
  # 删除隐藏项（.xxx），排除 . 与 ..
  if compgen -A file ${OUT_DIR}/.[!.]* >/dev/null 2>&1; then
    rm -rf ${OUT_DIR}/.[!.]*
  fi
  if compgen -A file ${OUT_DIR}/..?* >/dev/null 2>&1; then
    rm -rf ${OUT_DIR}/..?*
  fi
fi

echo "date,id,ccmode,lbmode,cwh_tx_expiry_time,cwh_extra_reply_deadline,cwh_path_pause_time,cwh_extra_voq_flush_time,cwh_default_voq_waiting_time,pfc,irn,has_win,var_win,topo,bw,cdf,load,time" > "${SIM_DIR}/mix/.history"

# 清理生成的图表
FIG_DIR="${SIM_DIR}/analysis/figures"
if [ -d "${FIG_DIR}" ]; then
  find "${FIG_DIR}" -type f -name "*.pdf" -delete
fi
# rm -rf "${ROOT_DIR}/results"/* 保留实验的关键文件防止误操作