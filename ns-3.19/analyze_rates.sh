#!/bin/bash

# 检查参数
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <log_file> [output_dir]"
    exit 1
fi

LOG_FILE=$1
OUTPUT_DIR=${2:-"rate_analysis"}

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 提取速率变化记录
echo "Extracting rate changes..."
./extract_rate_changes.sh "$LOG_FILE" "$OUTPUT_DIR"

# 运行可视化脚本
echo "Generating visualizations..."
python3 rate_visualization.py "$LOG_FILE" "$OUTPUT_DIR"

echo "Analysis completed. Results saved to $OUTPUT_DIR"
echo "Generated files:"
ls -la "$OUTPUT_DIR" | grep -v "^d" | awk '{print $9}'

# 打印一些统计信息
if [ -f "$OUTPUT_DIR/rate_changes_summary.csv" ]; then
    echo ""
    echo "Rate change statistics:"
    echo "----------------------"
    echo "Total rate changes: $(grep -c "," "$OUTPUT_DIR/rate_changes_summary.csv" | awk '{print $1-1}')"
    echo "Time span: $(head -n 2 "$OUTPUT_DIR/rate_changes_summary.csv" | tail -n 1 | cut -d, -f1) to $(tail -n 1 "$OUTPUT_DIR/rate_changes_summary.csv" | cut -d, -f1) seconds"
    
    # 计算平均速率变化
    echo ""
    echo "Average rate changes:"
    awk -F, 'NR>1 {sum+=$4; count++} END {print "Average new rate: " sum/count " Gbps"}' "$OUTPUT_DIR/rate_changes_summary.csv"
    
    # 按流ID分组统计
    echo ""
    echo "Rate changes by flow ID:"
    awk -F, 'NR>1 {flows[$2]++} END {for (flow in flows) print "Flow " flow ": " flows[flow] " changes"}' "$OUTPUT_DIR/rate_changes_summary.csv" | sort -t' ' -k2 -n
fi

echo ""
echo "Visualization files:"
find "$OUTPUT_DIR" -name "*.png" | sort