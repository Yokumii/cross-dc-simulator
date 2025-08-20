#!/usr/bin/env python3
import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import argparse
import seaborn as sns
from matplotlib.ticker import FuncFormatter

def format_time(x, pos):
    """将时间步格式化为微秒"""
    return f"{x/1000:.0f}μs"

def analyze_pfc_file(pfc_file, default_pause_time=5000):  # 默认5微秒 = 5000纳秒
    """分析PFC日志文件，返回PFC统计信息"""
    if not os.path.exists(pfc_file):
        print(f"文件不存在: {pfc_file}")
        return None
    
    # 读取PFC日志文件
    # 格式: time nodeID nodeType interfaceIdx type(0:resume, 1:pause)
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
        print(f"文件为空或格式错误: {pfc_file}")
        return None
    
    # 转换为DataFrame
    df = pd.DataFrame(data)
    
    # 获取仿真的最后时间点
    max_time = df['time_step'].max()
    
    # 按节点和接口分组，计算PFC事件
    pfc_events = []
    for (node_id, if_idx), group in df.groupby(['node_id', 'if_idx']):
        group = group.sort_values('time_step')
        
        # 找出所有的pause和resume事件
        pauses = group[group['pfc_type'] == 1]
        resumes = group[group['pfc_type'] == 0]
        
        # 处理每个pause事件
        for idx, pause in pauses.iterrows():
            pause_time = pause['time_step']
            
            # 寻找匹配的resume事件
            matching_resumes = resumes[resumes['time_step'] > pause_time]
            
            if not matching_resumes.empty:
                # 找到匹配的resume
                next_resume = matching_resumes['time_step'].min()
                duration = next_resume - pause_time
            else:
                # 没有匹配的resume，使用默认的pause time
                next_resume = min(pause_time + default_pause_time, max_time)
                duration = next_resume - pause_time
            
            pfc_events.append({
                'node_id': node_id,
                'if_idx': if_idx,
                'pause_time': pause_time,
                'resume_time': next_resume,
                'duration': duration
            })
    
    pfc_events_df = pd.DataFrame(pfc_events)
    
    # 计算统计数据
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
    """比较有无EdgeCNP的PFC结果并生成可视化"""
    with_stats = analyze_pfc_file(with_edge_cnp_file, default_pause_time)
    without_stats = analyze_pfc_file(without_edge_cnp_file, default_pause_time)
    
    if not with_stats or not without_stats:
        print("无法比较PFC结果，请检查文件路径")
        return
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 准备比较数据
    comparison_data = {
        'Metric': [
            'PFC总数', 
            'PFC总时间 (ns)', 
            'PFC平均时间 (ns)', 
            'PFC最大时间 (ns)', 
            'PFC最小时间 (ns)'
        ],
        '开启EdgeCNP': [
            with_stats['total_pfc_count'],
            with_stats['total_pfc_time'],
            with_stats['avg_pfc_time'],
            with_stats['max_pfc_time'],
            with_stats['min_pfc_time']
        ],
        '不开启EdgeCNP': [
            without_stats['total_pfc_count'],
            without_stats['total_pfc_time'],
            without_stats['avg_pfc_time'],
            without_stats['max_pfc_time'],
            without_stats['min_pfc_time']
        ]
    }
    
    comparison_df = pd.DataFrame(comparison_data)
    
    # 保存比较数据到CSV
    comparison_df.to_csv(f"{output_dir}/pfc_comparison.csv", index=False)
    
    # 1. 绘制PFC总数对比柱状图
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'Enable EdgeCNP', 'Disable EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['Enable EdgeCNP', 'Disable EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'PFC Count'"))
    plt.title('PFC Count Comparison')
    plt.ylabel('Count')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_count_comparison.png", dpi=300)
    plt.close()
    
    # 2. 绘制PFC总时间对比柱状图
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'Enable EdgeCNP', 'Disable EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['Enable EdgeCNP', 'Disable EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'PFC Total Time (ns)'"))
    plt.title('PFC Total Time Comparison')
    plt.ylabel('Time (ns)')
    plt.gca().yaxis.set_major_formatter(FuncFormatter(format_time))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_total_time_comparison.png", dpi=300)
    plt.close()
    
    # 3. 绘制PFC平均时间对比柱状图
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Metric', y='value', hue='variable', 
                data=pd.melt(comparison_df[['Metric', 'Enable EdgeCNP', 'Disable EdgeCNP']], 
                             id_vars=['Metric'], value_vars=['Enable EdgeCNP', 'Disable EdgeCNP'],
                             var_name='variable', value_name='value').query("Metric == 'PFC Average Time (ns)'"))
    plt.title('PFC Average Time Comparison')
    plt.ylabel('Time (ns)')
    plt.gca().yaxis.set_major_formatter(FuncFormatter(format_time))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_avg_time_comparison.png", dpi=300)
    plt.close()
    
    # 4. 绘制PFC时间分布对比
    plt.figure(figsize=(12, 6))
    with_events = with_stats['pfc_events']
    without_events = without_stats['pfc_events']
    
    if not with_events.empty and not without_events.empty:
        plt.subplot(1, 2, 1)
        sns.histplot(with_events['duration'], kde=True)
        plt.title('Enable EdgeCNP PFC Duration Distribution')
        plt.xlabel('PFC Duration (ns)')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.subplot(1, 2, 2)
        sns.histplot(without_events['duration'], kde=True)
        plt.title('Disable EdgeCNP PFC Duration Distribution')
        plt.xlabel('PFC Duration (ns)')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/pfc_duration_distribution.png", dpi=300)
    plt.close()
    
    # 5. 绘制PFC时间序列对比
    plt.figure(figsize=(14, 8))
    
    if not with_events.empty and not without_events.empty:
        plt.subplot(2, 1, 1)
        for _, event in with_events.iterrows():
            plt.hlines(event['node_id'] * 100 + event['if_idx'], 
                      event['pause_time'], event['resume_time'], 
                      linewidth=2, color='red')
        plt.title('Enable EdgeCNP PFC Time Series')
        plt.xlabel('Time (ns)')
        plt.ylabel('Node ID*100 + Interface ID')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.subplot(2, 1, 2)
        for _, event in without_events.iterrows():
            plt.hlines(event['node_id'] * 100 + event['if_idx'], 
                      event['pause_time'], event['resume_time'], 
                      linewidth=2, color='blue')
        plt.title('Disable EdgeCNP PFC Time Series')
        plt.xlabel('Time (ns)')
        plt.ylabel('Node ID*100 + Interface ID')
        plt.gca().xaxis.set_major_formatter(FuncFormatter(format_time))
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/pfc_time_series.png", dpi=300)
    plt.close()
    
    # 6. 绘制综合对比图表
    plt.figure(figsize=(15, 10))
    
    # 准备数据
    metrics = ['PFC Count', 'PFC Total Time (ns)', 'PFC Average Time (ns)']
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
    
    # 计算改进百分比
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
    
    # 绘制柱状图
    rects1 = ax1.bar(x - width/2, with_values, width, label='Enable EdgeCNP')
    rects2 = ax1.bar(x + width/2, without_values, width, label='Disable EdgeCNP')
    
    # 添加改进百分比标签
    for i, imp in enumerate(improvements):
        if imp != 0:
            plt.annotate(f'{imp:.1f}%', 
                         xy=(x[i], max(with_values[i], without_values[i]) * 1.05),
                         ha='center', va='bottom',
                         color='green' if imp > 0 else 'red',
                         fontsize=12, fontweight='bold')
    
    ax1.set_xlabel('Metric')
    ax1.set_ylabel('Value')
    ax1.set_title('EdgeCNP Impact on PFC Comprehensive Comparison')
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics)
    ax1.legend()
    
    plt.tight_layout()
    plt.savefig(f"{output_dir}/pfc_comprehensive_comparison.png", dpi=300)
    plt.close()
    
    print(f"分析完成，结果保存在 {output_dir} 目录下")
    
    # 返回比较结果的摘要
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
    parser = argparse.ArgumentParser(description='分析和比较有无EdgeCNP的PFC结果')
    parser.add_argument('--with-edge-cnp', required=True, help='开启EdgeCNP的PFC日志文件路径')
    parser.add_argument('--without-edge-cnp', required=True, help='不开启EdgeCNP的PFC日志文件路径')
    parser.add_argument('--output-dir', default='pfc_analysis_results', help='输出目录')
    parser.add_argument('--default-pause-time', type=int, default=5000, 
                        help='默认的pause time，单位为纳秒，默认为5微秒(5000纳秒)')
    
    args = parser.parse_args()
    
    summary = compare_pfc_results(args.with_edge_cnp, args.without_edge_cnp, 
                                 args.output_dir, args.default_pause_time)
    
    if summary:
        print("\n=== EdgeCNP对PFC影响的分析摘要 ===")
        print(f"开启EdgeCNP: PFC总数={summary['with_edge_cnp']['total_count']}, " +
              f"PFC总时间={summary['with_edge_cnp']['total_time']}ns, " +
              f"PFC平均时间={summary['with_edge_cnp']['avg_time']:.2f}ns")
        print(f"不开启EdgeCNP: PFC总数={summary['without_edge_cnp']['total_count']}, " +
              f"PFC总时间={summary['without_edge_cnp']['total_time']}ns, " +
              f"PFC平均时间={summary['without_edge_cnp']['avg_time']:.2f}ns")
        print(f"改进百分比: PFC总数={summary['improvements']['total_count']:.2f}%, " +
              f"PFC总时间={summary['improvements']['total_time']:.2f}%, " +
              f"PFC平均时间={summary['improvements']['avg_time']:.2f}%")