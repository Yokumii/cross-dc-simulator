#!/bin/bash

# 检查参数
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <log_file> [output_file]"
    exit 1
fi

LOG_FILE=$1
OUTPUT_DIR=${2:-"rate_analysis"}

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 提取速率变化记录
grep "RATE_CHANGE" "$LOG_FILE" > "$OUTPUT_DIR/all_rate_changes.txt"

echo "Rate changes extracted to $OUTPUT_DIR/all_rate_changes.txt"

# 统计流的数量
NUM_FLOWS=$(grep "RATE_CHANGE" "$LOG_FILE" | awk '{print $3}' | sed 's/flow_id=//' | sort -n | uniq | wc -l)
echo "Number of flows detected: $NUM_FLOWS"

# 统计每个流的记录数量
echo "Records per flow:"
grep "RATE_CHANGE" "$LOG_FILE" | awk '{print $3}' | sed 's/flow_id=//' | sort -n | uniq -c

# 提取每个流的速率变化记录
echo "Extracting rate changes for each flow..."
for flow_id in $(grep "RATE_CHANGE" "$LOG_FILE" | awk '{print $3}' | sed 's/flow_id=//' | sort -n | uniq); do
    grep "flow_id=$flow_id" "$OUTPUT_DIR/all_rate_changes.txt" > "$OUTPUT_DIR/flow_${flow_id}_changes.txt"
    echo "  - Flow $flow_id: $(wc -l < "$OUTPUT_DIR/flow_${flow_id}_changes.txt") records"
done

# 创建汇总文件，按时间排序
echo "Creating summary file..."
echo "Time,FlowID,OldRate,NewRate" > "$OUTPUT_DIR/rate_changes_summary.csv"
grep "RATE_CHANGE" "$LOG_FILE" | sed -E 's/([0-9.]+) RATE_CHANGE flow_id=([0-9]+) .* old_rate=([0-9.]+) Gbps new_rate=([0-9.]+) Gbps/\1,\2,\3,\4/' | sort -n >> "$OUTPUT_DIR/rate_changes_summary.csv"

echo "Summary file created: $OUTPUT_DIR/rate_changes_summary.csv"

# 分析背景流和突发流
echo "Analyzing background and burst flows..."
grep "flow_id=0" "$OUTPUT_DIR/all_rate_changes.txt" > "$OUTPUT_DIR/background_flow_changes.txt"
grep -v "flow_id=0" "$OUTPUT_DIR/all_rate_changes.txt" > "$OUTPUT_DIR/burst_flows_changes.txt"

echo "Background flow: $(wc -l < "$OUTPUT_DIR/background_flow_changes.txt") records"
echo "Burst flows: $(wc -l < "$OUTPUT_DIR/burst_flows_changes.txt") records"

# 提取发送端和接收端突发流
grep -E "flow_id=[1-7]" "$OUTPUT_DIR/all_rate_changes.txt" > "$OUTPUT_DIR/sending_burst_flows_changes.txt"
grep -E "flow_id=[8-9]|flow_id=1[0-9]" "$OUTPUT_DIR/all_rate_changes.txt" > "$OUTPUT_DIR/receiving_burst_flows_changes.txt"

echo "Sending burst flows: $(wc -l < "$OUTPUT_DIR/sending_burst_flows_changes.txt") records"
echo "Receiving burst flows: $(wc -l < "$OUTPUT_DIR/receiving_burst_flows_changes.txt") records"

echo "Extraction completed. Results saved to $OUTPUT_DIR" 