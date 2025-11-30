#!/usr/bin/python3

import os
import sys
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import argparse

def parse_fct_file(fct_file):
    """Parse FCT file and return DataFrame"""
    data = []
    with open(fct_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 8:
                try:
                    data.append({
                        'srcId': int(parts[0]),
                        'dstId': int(parts[1]),
                        'sport': int(parts[2]),
                        'dport': int(parts[3]),
                        'flowSize': int(parts[4]),
                        'startTime': int(parts[5]),
                        'actualFCT': int(parts[6]),
                        'standaloneFCT': int(parts[7])
                    })
                except ValueError:
                    continue
    return pd.DataFrame(data)

def calculate_throughput(df):
    """Calculate throughput for each flow"""
    df['actualFCT_sec'] = df['actualFCT'] / 1e9
    df['throughput_bps'] = df['flowSize'] / df['actualFCT_sec']
    df['throughput_mbps'] = df['throughput_bps'] / 1e6
    df['slowdown'] = df['actualFCT'] / df['standaloneFCT']
    return df

def is_inter_dc_flow(df):
    """Identify inter-DC flows based on source and destination IDs"""
    # This is a simplified heuristic - adjust based on your topology
    # For cross-DC topology, we assume inter-DC flows have different DC IDs
    return df['srcId'] != df['dstId']

def analyze_error_impact(results_dir):
    """Analyze the impact of error rates on throughput"""
    error_data = []
    
    # Find all result directories
    result_dirs = glob.glob(os.path.join(results_dir, "error_*"))
    
    if not result_dirs:
        # Try to find any subdirectories that might contain results
        result_dirs = glob.glob(os.path.join(results_dir, "*"))
        result_dirs = [d for d in result_dirs if os.path.isdir(d)]
    
    print(f"Found {len(result_dirs)} result directories")
    
    for result_dir in sorted(result_dirs):
        # Extract error rate from directory name
        dir_name = os.path.basename(result_dir)
        print(f"Processing directory: {dir_name}")
        
        # Try to extract error rate from directory name
        error_rate = None
        if 'error_' in dir_name:
            try:
                error_rate = float(dir_name.split('_')[1])
            except (IndexError, ValueError):
                pass
        
        # If we can't extract from directory name, try to find it in config files
        if error_rate is None:
            config_files = glob.glob(os.path.join(result_dir, "config.txt"))
            if config_files:
                with open(config_files[0], 'r') as f:
                    for line in f:
                        if 'ERROR_RATE_PER_LINK' in line:
                            try:
                                error_rate = float(line.split()[-1])
                                break
                            except (IndexError, ValueError):
                                pass
        
        if error_rate is None:
            print(f"Warning: Could not determine error rate for {dir_name}, skipping")
            continue
        
        # Find FCT file
        fct_files = glob.glob(os.path.join(result_dir, "*_out_fct.txt"))
        if not fct_files:
            print(f"Warning: No FCT file found in {result_dir}")
            continue
        
        fct_file = fct_files[0]
        print(f"Processing {fct_file} (error_rate={error_rate})")
        
        # Parse FCT data
        df = parse_fct_file(fct_file)
        if df.empty:
            print(f"Warning: No data in {fct_file}")
            continue
        
        # Calculate throughput
        df = calculate_throughput(df)
        
        # Identify inter-DC flows (simplified heuristic)
        inter_dc_mask = (df['srcId'] != df['dstId'])
        inter_dc_flows = df[inter_dc_mask]
        
        if len(inter_dc_flows) == 0:
            print(f"Warning: No inter-DC flows found in {fct_file}")
            continue
        
        # Calculate statistics
        stats = {
            'error_rate': error_rate,
            'total_flows': len(df),
            'inter_dc_flows': len(inter_dc_flows),
            'avg_throughput_mbps': inter_dc_flows['throughput_mbps'].mean(),
            'median_throughput_mbps': inter_dc_flows['throughput_mbps'].median(),
            'p95_throughput_mbps': inter_dc_flows['throughput_mbps'].quantile(0.95),
            'p99_throughput_mbps': inter_dc_flows['throughput_mbps'].quantile(0.99),
            'avg_slowdown': inter_dc_flows['slowdown'].mean(),
            'median_slowdown': inter_dc_flows['slowdown'].median(),
            'p95_slowdown': inter_dc_flows['slowdown'].quantile(0.95),
            'p99_slowdown': inter_dc_flows['slowdown'].quantile(0.99),
            'avg_fct_ms': inter_dc_flows['actualFCT'].mean() / 1e6,
            'median_fct_ms': inter_dc_flows['actualFCT'].median() / 1e6,
            'p95_fct_ms': inter_dc_flows['actualFCT'].quantile(0.95) / 1e6,
            'p99_fct_ms': inter_dc_flows['actualFCT'].quantile(0.99) / 1e6
        }
        
        error_data.append(stats)
        print(f"  Inter-DC flows: {len(inter_dc_flows)}")
        print(f"  Avg throughput: {stats['avg_throughput_mbps']:.2f} Mbps")
        print(f"  Avg slowdown: {stats['avg_slowdown']:.2f}")
    
    return pd.DataFrame(error_data)

def plot_error_impact(df, output_dir):
    """Plot the impact of error rates on throughput and FCT"""
    if df.empty:
        print("No data to plot")
        return
    
    # Sort by error rate
    df = df.sort_values('error_rate')
    
    # Create plots
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # 1. Throughput vs Error Rate
    axes[0, 0].plot(df['error_rate'], df['avg_throughput_mbps'], 'o-', label='Average', linewidth=2, markersize=6)
    axes[0, 0].plot(df['error_rate'], df['median_throughput_mbps'], 's-', label='Median', linewidth=2, markersize=6)
    axes[0, 0].plot(df['error_rate'], df['p95_throughput_mbps'], '^-', label='95th percentile', linewidth=2, markersize=6)
    axes[0, 0].set_xlabel('Inter-DC Error Rate')
    axes[0, 0].set_ylabel('Throughput (Mbps)')
    axes[0, 0].set_title('Inter-DC Flow Throughput vs Error Rate')
    axes[0, 0].set_xscale('log')
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend()
    
    # 2. Slowdown vs Error Rate
    axes[0, 1].plot(df['error_rate'], df['avg_slowdown'], 'o-', label='Average', linewidth=2, markersize=6)
    axes[0, 1].plot(df['error_rate'], df['median_slowdown'], 's-', label='Median', linewidth=2, markersize=6)
    axes[0, 1].plot(df['error_rate'], df['p95_slowdown'], '^-', label='95th percentile', linewidth=2, markersize=6)
    axes[0, 1].set_xlabel('Inter-DC Error Rate')
    axes[0, 1].set_ylabel('Slowdown')
    axes[0, 1].set_title('Inter-DC Flow Slowdown vs Error Rate')
    axes[0, 1].set_xscale('log')
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].legend()
    
    # 3. FCT vs Error Rate
    axes[1, 0].plot(df['error_rate'], df['avg_fct_ms'], 'o-', label='Average', linewidth=2, markersize=6)
    axes[1, 0].plot(df['error_rate'], df['median_fct_ms'], 's-', label='Median', linewidth=2, markersize=6)
    axes[1, 0].plot(df['error_rate'], df['p95_fct_ms'], '^-', label='95th percentile', linewidth=2, markersize=6)
    axes[1, 0].set_xlabel('Inter-DC Error Rate')
    axes[1, 0].set_ylabel('FCT (ms)')
    axes[1, 0].set_title('Inter-DC Flow FCT vs Error Rate')
    axes[1, 0].set_xscale('log')
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].legend()
    
    # 4. Number of flows vs Error Rate
    axes[1, 1].plot(df['error_rate'], df['inter_dc_flows'], 'o-', linewidth=2, markersize=6)
    axes[1, 1].set_xlabel('Inter-DC Error Rate')
    axes[1, 1].set_ylabel('Number of Inter-DC Flows')
    axes[1, 1].set_title('Number of Inter-DC Flows vs Error Rate')
    axes[1, 1].set_xscale('log')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'inter_error_impact_analysis.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # Create detailed throughput analysis
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    
    # Plot with error bars (using std as proxy for uncertainty)
    ax.errorbar(df['error_rate'], df['avg_throughput_mbps'], 
                yerr=df['p95_throughput_mbps'] - df['avg_throughput_mbps'],
                fmt='o-', capsize=5, capthick=2, linewidth=2, markersize=6)
    
    ax.set_xlabel('Inter-DC Error Rate')
    ax.set_ylabel('Average Throughput (Mbps)')
    ax.set_title('Inter-DC Flow Throughput vs Error Rate (with 95th percentile bounds)')
    ax.set_xscale('log')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'throughput_vs_error_detailed.png'), dpi=300, bbox_inches='tight')
    plt.close()

def generate_summary_report(df, output_dir):
    """Generate a summary report"""
    report_file = os.path.join(output_dir, 'error_impact_summary.txt')
    
    with open(report_file, 'w') as f:
        f.write("=== Inter-DC Error Rate Impact Analysis ===\n\n")
        f.write(f"Analysis completed at: {pd.Timestamp.now()}\n")
        f.write(f"Number of error rates tested: {len(df)}\n\n")
        
        f.write("=== Summary Statistics ===\n")
        f.write(f"Error rates tested: {sorted(df['error_rate'].tolist())}\n")
        f.write(f"Total inter-DC flows across all tests: {df['inter_dc_flows'].sum()}\n\n")
        
        f.write("=== Throughput Analysis ===\n")
        f.write(f"Average throughput range: {df['avg_throughput_mbps'].min():.2f} - {df['avg_throughput_mbps'].max():.2f} Mbps\n")
        f.write(f"Median throughput range: {df['median_throughput_mbps'].min():.2f} - {df['median_throughput_mbps'].max():.2f} Mbps\n")
        f.write(f"95th percentile throughput range: {df['p95_throughput_mbps'].min():.2f} - {df['p95_throughput_mbps'].max():.2f} Mbps\n\n")
        
        f.write("=== Slowdown Analysis ===\n")
        f.write(f"Average slowdown range: {df['avg_slowdown'].min():.2f} - {df['avg_slowdown'].max():.2f}\n")
        f.write(f"Median slowdown range: {df['median_slowdown'].min():.2f} - {df['median_slowdown'].max():.2f}\n")
        f.write(f"95th percentile slowdown range: {df['p95_slowdown'].min():.2f} - {df['p95_slowdown'].max():.2f}\n\n")
        
        f.write("=== FCT Analysis ===\n")
        f.write(f"Average FCT range: {df['avg_fct_ms'].min():.2f} - {df['avg_fct_ms'].max():.2f} ms\n")
        f.write(f"Median FCT range: {df['median_fct_ms'].min():.2f} - {df['median_fct_ms'].max():.2f} ms\n")
        f.write(f"95th percentile FCT range: {df['p95_fct_ms'].min():.2f} - {df['p95_fct_ms'].max():.2f} ms\n\n")
        
        f.write("=== Detailed Results ===\n")
        f.write(df.to_string(index=False, float_format='%.4f'))

def main():
    parser = argparse.ArgumentParser(description='Generate inter-DC error rate impact analysis')
    parser.add_argument('results_dir', help='Directory containing simulation results')
    parser.add_argument('-o', '--output-dir', help='Output directory for analysis results (default: same as results_dir)')
    
    args = parser.parse_args()
    
    results_dir = args.results_dir
    output_dir = args.output_dir or results_dir
    
    if not os.path.exists(results_dir):
        print(f"Error: Results directory {results_dir} does not exist")
        sys.exit(1)
    
    print("Analyzing error rate impact on inter-DC flows...")
    df = analyze_error_impact(results_dir)
    
    if df.empty:
        print("No data found for analysis")
        sys.exit(1)
    
    print(f"Found data for {len(df)} error rates")
    
    print("Generating plots...")
    plot_error_impact(df, output_dir)
    
    print("Generating summary report...")
    generate_summary_report(df, output_dir)
    
    print(f"Analysis completed! Results saved to: {output_dir}")
    
    # Print brief summary
    print(f"\n=== Brief Summary ===")
    print(f"Error rates tested: {len(df)}")
    print(f"Throughput range: {df['avg_throughput_mbps'].min():.2f} - {df['avg_throughput_mbps'].max():.2f} Mbps")
    print(f"Slowdown range: {df['avg_slowdown'].min():.2f} - {df['avg_slowdown'].max():.2f}")

if __name__ == "__main__":
    main()