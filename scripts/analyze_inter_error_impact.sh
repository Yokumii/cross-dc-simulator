#!/bin/bash

cecho(){  # Simple colored output
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    RED="\033[0;31m"
    BLUE="\033[0;34m"
    NC="\033[0m" # No Color
    printf "${!1}${2} ${NC}\n"
}

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
SIM_DIR="${ROOT_DIR}/simulation"
ANALYSIS_DIR="${ROOT_DIR}/analysis"

# Default parameters
SIM_TIME=${SIM_TIME:-"0.1"}
INTRA_LOAD=${INTRA_LOAD:-"0.3"}
INTER_LOAD=${INTER_LOAD:-"0.1"}
K_FAT=${K_FAT:-"4"}
NUM_DC=${NUM_DC:-"2"}
INTRA_BW=${INTRA_BW:-"100"}
INTER_BW=${INTER_BW:-"400"}
FLOW_SCALE=${FLOW_SCALE:-"1.0"}
INTRA_ERROR=${INTRA_ERROR:-"0.0"}
INTRA_LATENCY=${INTRA_LATENCY:-"1000"}
INTER_LATENCY=${INTER_LATENCY:-"400000"}

# Inter-DC error rates to test
INTER_ERROR_RATES=(
    "0"
    "0.00001"
    "0.00005"
    "0.0001"
    "0.0005"
    "0.001"
    "0.005"
    "0.01"
    "0.05"
)

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
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
    --intra-latency)
      INTRA_LATENCY="$2"
      shift 2
      ;;
    --inter-latency)
      INTER_LATENCY="$2"
      shift 2
      ;;
    --max-parallel)
      MAX_PARALLEL="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo "Options:"
      echo "  --simul-time TIME     Simulation time (default: 0.1)"
      echo "  --intra-load LOAD     Intra-DC load (default: 0.3)"
      echo "  --inter-load LOAD     Inter-DC load (default: 0.1)"
      echo "  --k-fat K             Fat-tree k value (default: 4)"
      echo "  --num-dc DC           Number of datacenters (default: 2)"
      echo "  --intra-bw BW         Intra-DC bandwidth in Gbps (default: 100)"
      echo "  --inter-bw BW         Inter-DC bandwidth in Gbps (default: 400)"
      echo "  --flow-scale SCALE    Flow scale factor (default: 1.0)"
      echo "  --intra-error RATE    Intra-DC link error rate (default: 0.0)"
      echo "  --intra-latency NS    Intra-DC link latency in ns (default: 1000)"
      echo "  --inter-latency NS    Inter-DC link latency in ns (default: 400000)"
      echo "  --max-parallel N      Maximum parallel simulations (default: 4)"
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

MAX_PARALLEL=${MAX_PARALLEL:-4}

# Create results directory
RESULTS_ROOT="${ROOT_DIR}/results"
SCRIPT_TAG="inter_error_impact"
RUN_DIR="${RESULTS_ROOT}/${SCRIPT_TAG}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RUN_DIR}"

cecho "GREEN" "Starting inter-DC error rate impact analysis"
cecho "YELLOW" "Parameters: simul_time=${SIM_TIME}, intra_load=${INTRA_LOAD}, inter_load=${INTER_LOAD}"
cecho "YELLOW" "Testing ${#INTER_ERROR_RATES[@]} error rates: ${INTER_ERROR_RATES[*]}"
cecho "YELLOW" "Max parallel simulations: ${MAX_PARALLEL}"

# Function to run a single simulation
run_simulation() {
    local error_rate="$1"
    local run_id="$2"
    
    cecho "BLUE" "Running simulation ${run_id}: INTER_ERROR=${error_rate}"
    
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
      --flow-scale "${FLOW_SCALE}" \
      --intra-error "${INTRA_ERROR}" \
      --inter-error "${error_rate}" \
      --intra-latency "${INTRA_LATENCY}" \
      --inter-latency "${INTER_LATENCY}" > "${RUN_DIR}/sim_${run_id}.log" 2>&1
    
    local exit_code=$?
    popd >/dev/null
    
    if [ $exit_code -eq 0 ]; then
        cecho "GREEN" "Simulation ${run_id} completed successfully"
        return 0
    else
        cecho "RED" "Simulation ${run_id} failed with exit code ${exit_code}"
        return 1
    fi
}

# Function to collect results from a simulation
collect_results() {
    local error_rate="$1"
    local run_id="$2"
    
    # Find the output directory
    local output_dir=$(find "${SIM_DIR}/mix/output" -maxdepth 1 -type d -name "*" | sort | tail -1)
    
    if [ -d "${output_dir}" ]; then
        # Move results to our run directory
        local result_dir="${RUN_DIR}/error_${error_rate}_${run_id}"
        mkdir -p "${result_dir}"
        cp -r "${output_dir}"/* "${result_dir}/"
        
        # Clean up the original output
        rm -rf "${output_dir}"
        
        echo "${result_dir}"
    else
        cecho "RED" "No output directory found for simulation ${run_id}"
        return 1
    fi
}

# Run simulations in parallel
declare -a pids
declare -a error_rates
declare -a run_ids
declare -a result_dirs

run_id=0
for error_rate in "${INTER_ERROR_RATES[@]}"; do
    # Wait if we have too many parallel jobs
    while [ ${#pids[@]} -ge $MAX_PARALLEL ]; do
        for i in "${!pids[@]}"; do
            if ! kill -0 "${pids[$i]}" 2>/dev/null; then
                # Process finished
                wait "${pids[$i]}"
                exit_code=$?
                if [ $exit_code -eq 0 ]; then
                    result_dir=$(collect_results "${error_rates[$i]}" "${run_ids[$i]}")
                    if [ $? -eq 0 ]; then
                        result_dirs+=("${result_dir}")
                    fi
                fi
                unset pids[$i]
                unset error_rates[$i]
                unset run_ids[$i]
            fi
        done
        sleep 1
    done
    
    # Start new simulation
    run_simulation "${error_rate}" "${run_id}" &
    pids+=($!)
    error_rates+=("${error_rate}")
    run_ids+=("${run_id}")
    ((run_id++))
done

# Wait for all remaining simulations to complete
for i in "${!pids[@]}"; do
    if [ -n "${pids[$i]}" ]; then
        wait "${pids[$i]}"
        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            result_dir=$(collect_results "${error_rates[$i]}" "${run_ids[$i]}")
            if [ $? -eq 0 ]; then
                result_dirs+=("${result_dir}")
            fi
        fi
    fi
done

cecho "GREEN" "All simulations completed. Found ${#result_dirs[@]} result directories."

# Run the analysis using the standalone script
cecho "GREEN" "Running analysis..."
python3 "${ROOT_DIR}/scripts/generate_error_analysis.py" "${RUN_DIR}"

cecho "GREEN" "Analysis completed!"
cecho "YELLOW" "Results saved to: ${RUN_DIR}"
cecho "YELLOW" "Check the following files:"
cecho "YELLOW" "  - inter_error_impact_analysis.png: Main analysis plots"
cecho "YELLOW" "  - throughput_vs_error_detailed.png: Detailed throughput analysis"
cecho "YELLOW" "  - error_impact_summary.txt: Summary report"