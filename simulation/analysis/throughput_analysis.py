#!/usr/bin/python3

import os
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import pandas as pd

def parse_fct_file(fct_file_path):
    """
    解析 FCT 文件，返回 DataFrame
    格式：srcId dstId sport dport flowSize startTime actualFCT standaloneFCT
    """
    data = []
    with open(fct_file_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 8:
                data.append({
                    'srcId': int(parts[0]),
                    'dstId': int(parts[1]),
                    'sport': int(parts[2]),
                    'dport': int(parts[3]),
                    'flowSize': int(parts[4]),  # bytes
                    'startTime': int(parts[5]),  # ns
                    'actualFCT': int(parts[6]),  # ns
                    'standaloneFCT': int(parts[7])  # ns
                })
    
    return pd.DataFrame(data)

def calculate_flow_throughput(df):
    """
    计算每个流的吞吐量 (bytes/second)
    """
    # 将 FCT 从纳秒转换为秒
    df['actualFCT_sec'] = df['actualFCT'] / 1e9
    df['standaloneFCT_sec'] = df['standaloneFCT'] / 1e9
    
    # 计算吞吐量
    df['throughput_bps'] = df['flowSize'] / df['actualFCT_sec']
    df['throughput_mbps'] = df['throughput_bps'] / 1e6
    df['standalone_throughput_bps'] = df['flowSize'] / df['standaloneFCT_sec']
    df['standalone_throughput_mbps'] = df['standalone_throughput_bps'] / 1e6
    
    # 计算 slowdown
    df['slowdown'] = df['actualFCT'] / df['standaloneFCT']
    
    return df

def calculate_aggregate_throughput(df, time_window_ms=100):
    """
    计算时间窗口内的聚合吞吐量
    """
    # 将开始时间从纳秒转换为毫秒
    df['startTime_ms'] = df['startTime'] / 1e6
    
    # 计算时间范围
    min_time = df['startTime_ms'].min()
    max_time = df['startTime_ms'].max()
    
    # 创建时间窗口
    time_windows = np.arange(min_time, max_time + time_window_ms, time_window_ms)
    
    window_stats = []
    for i in range(len(time_windows) - 1):
        start_t = time_windows[i]
        end_t = time_windows[i + 1]
        
        # 找到在此时间窗口内完成的流
        window_flows = df[(df['startTime_ms'] >= start_t) & (df['startTime_ms'] < end_t)]
        
        if len(window_flows) > 0:
            total_bytes = window_flows['flowSize'].sum()
            total_time = window_flows['actualFCT_sec'].sum()
            avg_throughput = total_bytes / total_time if total_time > 0 else 0
            
            window_stats.append({
                'time_start': start_t,
                'time_end': end_t,
                'num_flows': len(window_flows),
                'total_bytes': total_bytes,
                'total_time': total_time,
                'avg_throughput_mbps': avg_throughput / 1e6,
                'max_throughput_mbps': window_flows['throughput_mbps'].max(),
                'min_throughput_mbps': window_flows['throughput_mbps'].min(),
                'median_throughput_mbps': window_flows['throughput_mbps'].median()
            })
    
    return pd.DataFrame(window_stats)

def calculate_per_host_throughput(df):
    """
    计算每个主机的吞吐量统计
    """
    host_stats = []
    
    # 按源主机统计
    src_stats = df.groupby('srcId').agg({
        'flowSize': ['count', 'sum'],
        'throughput_mbps': ['mean', 'std', 'min', 'max', 'median'],
        'slowdown': ['mean', 'std', 'min', 'max', 'median']
    }).round(3)
    
    # 按目标主机统计
    dst_stats = df.groupby('dstId').agg({
        'flowSize': ['count', 'sum'],
        'throughput_mbps': ['mean', 'std', 'min', 'max', 'median'],
        'slowdown': ['mean', 'std', 'min', 'max', 'median']
    }).round(3)
    
    return src_stats, dst_stats

def plot_throughput_analysis(df, window_df, output_dir):
    """
    Plot throughput analysis charts
    """
    # 1. Flow throughput distribution
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Throughput histogram
    axes[0, 0].hist(df['throughput_mbps'], bins=50, alpha=0.7, edgecolor='black')
    axes[0, 0].set_xlabel('Throughput (Mbps)')
    axes[0, 0].set_ylabel('Number of Flows')
    axes[0, 0].set_title('Flow Throughput Distribution')
    axes[0, 0].grid(True, alpha=0.3)
    
    # Throughput CDF
    sorted_throughput = np.sort(df['throughput_mbps'])
    cdf = np.arange(1, len(sorted_throughput) + 1) / len(sorted_throughput)
    axes[0, 1].plot(sorted_throughput, cdf, linewidth=2)
    axes[0, 1].set_xlabel('Throughput (Mbps)')
    axes[0, 1].set_ylabel('CDF')
    axes[0, 1].set_title('Flow Throughput CDF')
    axes[0, 1].grid(True, alpha=0.3)
    
    # Time window aggregated throughput
    if len(window_df) > 0:
        axes[1, 0].plot(window_df['time_start'], window_df['avg_throughput_mbps'], 
                       marker='o', markersize=3, linewidth=1)
        axes[1, 0].set_xlabel('Time (ms)')
        axes[1, 0].set_ylabel('Average Throughput (Mbps)')
        axes[1, 0].set_title('Time Window Aggregated Throughput')
        axes[1, 0].grid(True, alpha=0.3)
    
    # Flow size vs throughput scatter plot
    axes[1, 1].scatter(df['flowSize'] / 1024, df['throughput_mbps'], alpha=0.6, s=10)
    axes[1, 1].set_xlabel('Flow Size (KB)')
    axes[1, 1].set_ylabel('Throughput (Mbps)')
    axes[1, 1].set_title('Flow Size vs Throughput')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'throughput_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Slowdown analysis
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Slowdown distribution
    axes[0].hist(df['slowdown'], bins=50, alpha=0.7, edgecolor='black')
    axes[0].set_xlabel('Slowdown')
    axes[0].set_ylabel('Number of Flows')
    axes[0].set_title('Slowdown Distribution')
    axes[0].grid(True, alpha=0.3)
    
    # Slowdown CDF
    sorted_slowdown = np.sort(df['slowdown'])
    cdf = np.arange(1, len(sorted_slowdown) + 1) / len(sorted_slowdown)
    axes[1].plot(sorted_slowdown, cdf, linewidth=2)
    axes[1].set_xlabel('Slowdown')
    axes[1].set_ylabel('CDF')
    axes[1].set_title('Slowdown CDF')
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'slowdown_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()

def generate_summary_report(df, window_df, src_stats, dst_stats, output_dir):
    """
    Generate summary report
    """
    report_file = os.path.join(output_dir, 'throughput_summary.txt')
    
    with open(report_file, 'w') as f:
        f.write("=== Throughput Analysis Report ===\n\n")
        f.write(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Flows: {len(df)}\n\n")
        
        # Overall statistics
        f.write("=== Overall Statistics ===\n")
        f.write(f"Average Throughput: {df['throughput_mbps'].mean():.2f} Mbps\n")
        f.write(f"Median Throughput: {df['throughput_mbps'].median():.2f} Mbps\n")
        f.write(f"Max Throughput: {df['throughput_mbps'].max():.2f} Mbps\n")
        f.write(f"Min Throughput: {df['throughput_mbps'].min():.2f} Mbps\n")
        f.write(f"Throughput Std Dev: {df['throughput_mbps'].std():.2f} Mbps\n\n")
        
        f.write(f"Average Slowdown: {df['slowdown'].mean():.2f}\n")
        f.write(f"Median Slowdown: {df['slowdown'].median():.2f}\n")
        f.write(f"Max Slowdown: {df['slowdown'].max():.2f}\n")
        f.write(f"Min Slowdown: {df['slowdown'].min():.2f}\n\n")
        
        # Flow size statistics
        f.write("=== Flow Size Statistics ===\n")
        f.write(f"Average Flow Size: {df['flowSize'].mean() / 1024:.2f} KB\n")
        f.write(f"Median Flow Size: {df['flowSize'].median() / 1024:.2f} KB\n")
        f.write(f"Max Flow Size: {df['flowSize'].max() / 1024:.2f} KB\n")
        f.write(f"Min Flow Size: {df['flowSize'].min() / 1024:.2f} KB\n\n")
        
        # Time window statistics
        if len(window_df) > 0:
            f.write("=== Time Window Statistics ===\n")
            f.write(f"Number of Time Windows: {len(window_df)}\n")
            f.write(f"Average Window Throughput: {window_df['avg_throughput_mbps'].mean():.2f} Mbps\n")
            f.write(f"Max Window Throughput: {window_df['avg_throughput_mbps'].max():.2f} Mbps\n")
            f.write(f"Min Window Throughput: {window_df['avg_throughput_mbps'].min():.2f} Mbps\n\n")

def main():
    parser = argparse.ArgumentParser(description='Calculate application layer throughput from FCT data')
    parser.add_argument('-f', '--fct-file', required=True, help='FCT file path')
    parser.add_argument('-o', '--output-dir', default='.', help='Output directory')
    parser.add_argument('-w', '--window-size', type=int, default=100, help='Time window size (ms)')
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    print("Parsing FCT file...")
    df = parse_fct_file(args.fct_file)
    print(f"Parsing completed, {len(df)} flows found")
    
    print("Calculating throughput...")
    df = calculate_flow_throughput(df)
    
    print("Calculating time window aggregated throughput...")
    window_df = calculate_aggregate_throughput(df, args.window_size)
    
    print("Calculating per-host statistics...")
    src_stats, dst_stats = calculate_per_host_throughput(df)
    
    print("Generating plots...")
    plot_throughput_analysis(df, window_df, args.output_dir)
    
    print("Generating report...")
    generate_summary_report(df, window_df, src_stats, dst_stats, args.output_dir)
    
    print(f"Analysis completed! Results saved to: {args.output_dir}")
    
    # Print brief statistics
    print(f"\n=== Brief Statistics ===")
    print(f"Total Flows: {len(df)}")
    print(f"Average Throughput: {df['throughput_mbps'].mean():.2f} Mbps")
    print(f"Average Slowdown: {df['slowdown'].mean():.2f}")

if __name__ == "__main__":
    main()