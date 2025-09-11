#!/usr/bin/env python3
import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import argparse
import seaborn as sns
from matplotlib.ticker import FuncFormatter

def format_time(x, pos):
    """Format time steps to microseconds"""
    return f"{x/1000:.0f}μs"

def analyze_pfc_file(pfc_file, default_pause_time=5000):  # Default 5 microseconds = 5000 nanoseconds
    """Analyze PFC log file and return statistics"""
    if not os.path.exists(pfc_file):
        print(f"File does not exist: {pfc_file}")
        return None
    
    # Read PFC log file
    # Format: time nodeID nodeType interfaceIdx type(0:resume, 1:pause)
    data = []
    with open(pfc_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 5:
                time_step, node_id, node_type, if_idx, pfc_type = map(int, parts)
                data.append({
                    'time_step': time_step,
                    'node_id': node_id,
                    'node_type': node_type,
                    'if_idx': if_idx,
                    'pfc_type': pfc_type  # 0:resume, 1:pause
                })
    
    if not data:
        print(f"File is empty or has incorrect format: {pfc_file}")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(data)
    
    # Get the last time point of the simulation
    max_time = df['time_step'].max()
    
    # Group by node and interface, calculate PFC events
    pfc_events = []
    for (node_id, if_idx), group in df.groupby(['node_id', 'if_idx']):
        group = group.sort_values('time_step')
        
        # Track current pause state
        is_paused = False
        current_pause_start = None
        last_pause_time = None
        
        # Process each event
        for idx, row in group.iterrows():
            time_step = row['time_step']
            pfc_type = row['pfc_type']
            
            if pfc_type == 1:  # pause
                if not is_paused:  # If not currently paused, record new pause start
                    is_paused = True
                    current_pause_start = time_step
                # Always update the last pause time
                last_pause_time = time_step
            
            elif pfc_type == 0:  # resume
                if is_paused:  # If currently paused, record pause end
                    is_paused = False
                    duration = time_step - current_pause_start
                    pfc_events.append({
                        'node_id': node_id,
                        'if_idx': if_idx,
                        'pause_time': current_pause_start,
                        'resume_time': time_step,
                        'last_pause_time': last_pause_time,
                        'duration': duration
                    })
                    current_pause_start = None
                    last_pause_time = None
                # If not currently paused, ignore this resume event
        
        # Handle the last unmatched pause event
        if is_paused and current_pause_start is not None:
            # Use the last pause time plus default pause time as end time
            resume_time = min(last_pause_time + default_pause_time, max_time)
            duration = resume_time - current_pause_start
            pfc_events.append({
                'node_id': node_id,
                'if_idx': if_idx,
                'pause_time': current_pause_start,
                'resume_time': resume_time,
                'last_pause_time': last_pause_time,
                'duration': duration
            })
    
    pfc_events_df = pd.DataFrame(pfc_events)
    
    # Calculate statistics
    stats = {
        'total_pfc_count': len(pfc_events),
        'total_pfc_time': pfc_events_df['duration'].sum() if not pfc_events_df.empty else 0,
        'avg_pfc_time': pfc_events_df['duration'].mean() if not pfc_events_df.empty else 0,
        'max_pfc_time': pfc_events_df['duration'].max() if not pfc_events_df.empty else 0,
        'min_pfc_time': pfc_events_df['duration'].min() if not pfc_events_df.empty else 0,
        'pfc_events': pfc_events_df
    }
    
    return stats

def compare_pfc_results(with_edge_cnp_file, without_edge_cnp_file, output_dir, default_pause_time=5000):
    """Compare PFC results with and without EdgeCNP and generate visualizations"""
    with_stats = analyze_pfc_file(with_edge_cnp_file, default_pause_time)
    without_stats = analyze_pfc_file(without_edge_cnp_file, default_pause_time)
    
    if not with_stats or not without_stats:
        print("Cannot compare PFC results, please check file paths")
        return
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Prepare comparison data
    comparison_data = {
        'Metric': [
            'Total PFC Count', 
            'Total PFC Time (ns)', 
            'Avg PFC Time (ns)', 
            'Max PFC Time (ns)', 
            'Min PFC Time (ns)'
        ],
        'With EdgeCNP': [
            with_stats['total_pfc_count'],
            with_stats['total_pfc_time'],
            with_stats['avg_pfc_time'],
            with_stats['max_pfc_time'],
            with_stats['min_pfc_time']
        ],
        'Without EdgeCNP': [
            without_stats['total_pfc_count'],
            without_stats['total_pfc_time'],
            without_stats['avg_pfc_time'],
            without_stats['max_pfc_time'],
            without_stats['min_pfc_time']
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    
    # Save comparison data to CSV
    comparison_df.to_csv(f"{output_dir}/pfc_comparison.csv", index=False)
    
    # 1. Plot PFC count comparison bar chart
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'With EdgeCNP', 'Without EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['With EdgeCNP', 'Without EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'Total PFC Count'"))
    plt.title('Total PFC Count Comparison')
    plt.ylabel('Count')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_count_comparison.png", dpi=300)
    plt.close()
    
    # 2. Plot PFC total time comparison bar chart
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'With EdgeCNP', 'Without EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['With EdgeCNP', 'Without EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'Total PFC Time (ns)'"))
    plt.title('Total PFC Time Comparison')
    plt.ylabel('Time (ns)')
    plt.gca().yaxis.set_major_formatter(FuncFormatter(format_time))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_total_time_comparison.png", dpi=300)
    plt.close()
    
    # 3. Plot PFC average time comparison bar chart
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'With EdgeCNP', 'Without EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['With EdgeCNP', 'Without EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'Avg PFC Time (ns)'"))
    plt.title('Average PFC Time Comparison')
    plt.ylabel('Time (ns)')
    plt.gca().yaxis.set_major_formatter(FuncFormatter(format_time))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_avg_time_comparison.png", dpi=300)
    plt.close()
    
    # 4. Plot PFC duration distribution comparison
    plt.figure(figsize=(12, 6))
    with_events = with_stats['pfc_events']
    without_events = without_stats['pfc_events']
    
    if not with_events.empty and not without_events.empty:
        plt.subplot(1, 2, 1)
        sns.histplot(with_events['duration'], kde=True)
        plt.title('PFC Duration Distribution with EdgeCNP')
        plt.xlabel('PFC Duration (ns)')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.subplot(1, 2, 2)
        sns.histplot(without_events['duration'], kde=True)
        plt.title('PFC Duration Distribution without EdgeCNP')
        plt.xlabel('PFC Duration (ns)')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/pfc_duration_distribution.png", dpi=300)
    plt.close()
    
    # 5. Plot PFC time series comparison
    plt.figure(figsize=(14, 8))
    
    if not with_events.empty and not without_events.empty:
        plt.subplot(2, 1, 1)
        for _, event in with_events.iterrows():
            plt.hlines(event['node_id'] * 100 + event['if_idx'], 
                      event['pause_time'], event['resume_time'], 
                      linewidth=2, color='red')
        plt.title('PFC Time Series with EdgeCNP')
        plt.xlabel('Time (ns)')
        plt.ylabel('NodeID*100 + InterfaceID')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.subplot(2, 1, 2)
        for _, event in without_events.iterrows():
            plt.hlines(event['node_id'] * 100 + event['if_idx'], 
                      event['pause_time'], event['resume_time'], 
                      linewidth=2, color='blue')
        plt.title('PFC Time Series without EdgeCNP')
        plt.xlabel('Time (ns)')
        plt.ylabel('NodeID*100 + InterfaceID')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/pfc_time_series.png", dpi=300)
    plt.close()
    
    # 6. Plot comprehensive comparison chart
    plt.figure(figsize=(15, 10))
    
    # Prepare data
    metrics = ['Total PFC Count', 'Total PFC Time (ns)', 'Avg PFC Time (ns)']
    with_values = [
        with_stats['total_pfc_count'], 
        with_stats['total_pfc_time'], 
        with_stats['avg_pfc_time']
    ]
    without_values = [
        without_stats['total_pfc_count'], 
        without_stats['total_pfc_time'], 
        without_stats['avg_pfc_time']
    ]
    
    # Calculate improvement percentages
    improvements = []
    for w, wo in zip(with_values, without_values):
        if wo > 0:
            imp = (wo - w) / wo * 100
            improvements.append(imp)
        else:
            improvements.append(0)
    
    x = np.arange(len(metrics))
    width = 0.35
    
    fig, ax1 = plt.subplots(figsize=(12, 8))
    
    # Draw bar chart
    rects1 = ax1.bar(x - width/2, with_values, width, label='With EdgeCNP')
    rects2 = ax1.bar(x + width/2, without_values, width, label='Without EdgeCNP')
    
    # Add improvement percentage labels
    for i, imp in enumerate(improvements):
        if imp != 0:
            plt.annotate(f'{imp:.1f}%', 
                         xy=(x[i], max(with_values[i], without_values[i]) * 1.05),
                         ha='center', va='bottom',
                         color='green' if imp > 0 else 'red',
                         fontsize=12, fontweight='bold')
    
    ax1.set_xlabel('Metrics')
    ax1.set_ylabel('Values')
    ax1.set_title('Comprehensive Comparison of EdgeCNP Impact on PFC')
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics)
    ax1.legend()
    
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_comprehensive_comparison.png", dpi=300)
    plt.close()
    
    print(f"Analysis completed, results saved in {output_dir} directory")
    
    # Return comparison summary
    summary = {
        'with_edge_cnp': {
            'total_count': with_stats['total_pfc_count'],
            'total_time': with_stats['total_pfc_time'],
            'avg_time': with_stats['avg_pfc_time']
        },
        'without_edge_cnp': {
            'total_count': without_stats['total_pfc_count'],
            'total_time': without_stats['total_pfc_time'],
            'avg_time': without_stats['avg_pfc_time']
        },
        'improvements': {
            'total_count': improvements[0],
            'total_time': improvements[1],
            'avg_time': improvements[2]
        }
    }
    
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze and compare PFC results with and without EdgeCNP')
    parser.add_argument('--with-edge-cnp', required=True, help='Path to PFC log file with EdgeCNP enabled')
    parser.add_argument('--without-edge-cnp', required=True, help='Path to PFC log file with EdgeCNP disabled')
    parser.add_argument('--output-dir', default='pfc_analysis_results', help='Output directory')
    parser.add_argument('--default-pause-time', type=int, default=5000, 
                        help='Default pause time in nanoseconds, default is 5 microseconds (5000 ns)')
    
    args = parser.parse_args()
    
    summary = compare_pfc_results(args.with_edge_cnp, args.without_edge_cnp, 
                                 args.output_dir, args.default_pause_time)
    
    if summary:
        print("\n=== EdgeCNP Impact on PFC Analysis Summary ===")
        print(f"With EdgeCNP: Total PFC Count={summary['with_edge_cnp']['total_count']}, " +
              f"Total PFC Time={summary['with_edge_cnp']['total_time']}ns, " +
              f"Avg PFC Time={summary['with_edge_cnp']['avg_time']:.2f}ns")
        print(f"Without EdgeCNP: Total PFC Count={summary['without_edge_cnp']['total_count']}, " +
              f"Total PFC Time={summary['without_edge_cnp']['total_time']}ns, " +
              f"Avg PFC Time={summary['without_edge_cnp']['avg_time']:.2f}ns")
        print(f"Improvement Percentages: Total PFC Count={summary['improvements']['total_count']:.2f}%, " +
              f"Total PFC Time={summary['improvements']['total_time']:.2f}%, " +
              f"Avg PFC Time={summary['improvements']['avg_time']:.2f}%")