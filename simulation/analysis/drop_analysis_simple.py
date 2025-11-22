#!/usr/bin/env python3
"""
简化版丢包分析脚本

根据srcId和dstId判断是否属于同一数据中心
根据type字段区分交换机丢包和网卡丢包

使用方法:
python3 drop_analysis_simple.py <drop_file_path> [options]
"""

import argparse
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
import gc
import time

def is_same_datacenter(src_id, dst_id, nodes_per_dc=53):
    """
    判断两个节点是否属于同一数据中心
    假设每个数据中心有53个节点 (32服务器 + 20交换机 + 1DCI)
    """
    src_dc = src_id // nodes_per_dc
    dst_dc = dst_id // nodes_per_dc
    return src_dc == dst_dc

def get_drop_cause_type(drop_type):
    """根据type字段判断丢包原因"""
    if drop_type == 0:
        return "Random Drop (Error Model)"
    elif drop_type == 1:
        return "Congestion Drop (Switch Ingress)"
    elif drop_type == 2:
        return "Congestion Drop (Switch Egress)"
    else:
        return f"Unknown Type {drop_type}"

def get_switch_type(node_id, nodes_per_dc=53):
    """
    判断交换机类型
    假设每个数据中心有53个节点 (32服务器 + 20交换机 + 1DCI)
    DCI交换机是每个数据中心的最后一个节点
    """
    dc_id = node_id // nodes_per_dc
    local_id = node_id % nodes_per_dc
    
    # 假设DCI交换机是每个数据中心的最后一个节点 (ID = 52)
    if local_id == 52:
        return "DCI Switch"
    elif local_id >= 32:  # 交换机节点ID范围: 32-51
        return "DCN Internal Switch"
    else:  # 服务器节点ID范围: 0-31
        return "Server"

def parse_drop_file_simple(file_path, chunk_size=100000, sample_rate=1.0):
    """
    简化版流式解析丢包文件
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"丢包文件不存在: {file_path}")
    
    print(f"开始解析文件: {file_path}")
    print(f"分块大小: {chunk_size}, 采样率: {sample_rate}")
    
    chunk_data = []
    line_count = 0
    processed_count = 0
    
    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 采样处理
            if sample_rate < 1.0 and np.random.random() > sample_rate:
                continue
            
            parts = line.split()
            if len(parts) != 8:
                continue
            
            try:
                time_ns = int(parts[0])
                drop_type = int(parts[1])
                node = int(parts[2])
                interface = int(parts[3])
                src_id = int(parts[4])
                dst_id = int(parts[5])
                sport = int(parts[6])
                dport = int(parts[7])
                
                # 判断是否属于同一数据中心
                same_dc = is_same_datacenter(src_id, dst_id)
                link_type = "Intra-DC Link" if same_dc else "Inter-DC Link"
                
                # 获取丢包原因类型
                drop_cause = get_drop_cause_type(drop_type)
                
                # 获取交换机类型
                switch_type = get_switch_type(node)
                
                chunk_data.append({
                    'time_ns': time_ns,
                    'type': drop_type,
                    'node': node,
                    'interface': interface,
                    'src_id': src_id,
                    'dst_id': dst_id,
                    'sport': sport,
                    'dport': dport,
                    'link_type': link_type,
                    'drop_cause': drop_cause,
                    'switch_type': switch_type
                })
                
                processed_count += 1
                
                # 当达到分块大小时，返回数据并清空
                if len(chunk_data) >= chunk_size:
                    yield pd.DataFrame(chunk_data)
                    chunk_data = []
                    gc.collect()
                    
            except ValueError:
                continue
    
    # 处理剩余数据
    if chunk_data:
        yield pd.DataFrame(chunk_data)
    
    print(f"处理完成，共处理 {processed_count} 条记录")

def analyze_drop_statistics_simple(file_path, chunk_size=100000, sample_rate=1.0):
    """
    简化版流式分析丢包统计信息
    """
    print("开始分析丢包统计...")
    
    # 初始化统计变量
    total_drops = 0
    min_time = float('inf')
    max_time = 0
    
    # 按链路类型统计
    link_type_counts = Counter()
    drop_cause_counts = Counter()
    switch_type_counts = Counter()
    type_by_link = {"Intra-DC Link": Counter(), "Inter-DC Link": Counter()}
    drop_cause_by_link = {"Intra-DC Link": Counter(), "Inter-DC Link": Counter()}
    switch_type_by_link = {"Intra-DC Link": Counter(), "Inter-DC Link": Counter()}
    node_by_link = {"Intra-DC Link": Counter(), "Inter-DC Link": Counter()}
    
    chunk_num = 0
    for chunk_df in parse_drop_file_simple(file_path, chunk_size, sample_rate):
        chunk_num += 1
        print(f"处理第 {chunk_num} 个数据块，大小: {len(chunk_df)}")
        
        if chunk_df.empty:
            continue
        
        # 更新基本统计
        total_drops += len(chunk_df)
        min_time = min(min_time, chunk_df['time_ns'].min())
        max_time = max(max_time, chunk_df['time_ns'].max())
        
        # 按链路类型统计
        link_type_counts.update(chunk_df['link_type'].value_counts().to_dict())
        drop_cause_counts.update(chunk_df['drop_cause'].value_counts().to_dict())
        switch_type_counts.update(chunk_df['switch_type'].value_counts().to_dict())
        
        # 按链路类型和丢包类型统计
        for _, row in chunk_df.iterrows():
            link_type = row['link_type']
            drop_type = row['type']
            drop_cause = row['drop_cause']
            switch_type = row['switch_type']
            node = row['node']
            
            type_by_link[link_type][drop_type] += 1
            drop_cause_by_link[link_type][drop_cause] += 1
            switch_type_by_link[link_type][switch_type] += 1
            node_by_link[link_type][node] += 1
        
        # 释放内存
        del chunk_df
        gc.collect()
    
    # 计算最终统计
    stats = {
        'total_drops': total_drops,
        'time_range_ns': max_time - min_time if max_time > min_time else 0,
        'time_range_ms': (max_time - min_time) / 1e6 if max_time > min_time else 0,
        'link_type_distribution': dict(link_type_counts),
        'drop_cause_distribution': dict(drop_cause_counts),
        'switch_type_distribution': dict(switch_type_counts),
        'type_by_link': {k: dict(v) for k, v in type_by_link.items()},
        'drop_cause_by_link': {k: dict(v) for k, v in drop_cause_by_link.items()},
        'switch_type_by_link': {k: dict(v) for k, v in switch_type_by_link.items()},
        'node_by_link': {k: dict(v) for k, v in node_by_link.items()}
    }
    
    return stats

def create_simple_visualizations(stats, output_dir):
    """创建可视化图表"""
    print("生成可视化图表...")
    
    # 设置英文字体
    plt.rcParams['font.family'] = 'DejaVu Sans'
    
    # 1. 链路类型丢包分布饼图
    if stats['link_type_distribution']:
        plt.figure(figsize=(10, 8))
        labels = list(stats['link_type_distribution'].keys())
        sizes = list(stats['link_type_distribution'].values())
        colors = ['#ff9999', '#66b3ff']
        
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
        plt.title('Packet Drop Distribution by Link Type')
        plt.axis('equal')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'drop_by_link_type.png'), dpi=300, bbox_inches='tight')
        plt.close()
    
    # 2. 丢包原因类型分布饼图
    if stats['drop_cause_distribution']:
        plt.figure(figsize=(10, 8))
        labels = list(stats['drop_cause_distribution'].keys())
        sizes = list(stats['drop_cause_distribution'].values())
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
        plt.title('Packet Drop Distribution by Drop Cause')
        plt.axis('equal')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'drop_by_cause_type.png'), dpi=300, bbox_inches='tight')
        plt.close()
    
    # 3. 交换机类型丢包分布饼图
    if stats['switch_type_distribution']:
        plt.figure(figsize=(10, 8))
        labels = list(stats['switch_type_distribution'].keys())
        sizes = list(stats['switch_type_distribution'].values())
        colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99']
        
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
        plt.title('Packet Drop Distribution by Switch Type')
        plt.axis('equal')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'drop_by_switch_type.png'), dpi=300, bbox_inches='tight')
        plt.close()
    
    # 4. 按链路类型的丢包原因分布
    if stats['drop_cause_by_link']:
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        
        for i, (link_type, cause_counts) in enumerate(stats['drop_cause_by_link'].items()):
            if cause_counts:
                labels = list(cause_counts.keys())
                sizes = list(cause_counts.values())
                
                axes[i].pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
                axes[i].set_title(f'Drop Cause in {link_type}')
        
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'drop_cause_by_link_type.png'), dpi=300, bbox_inches='tight')
        plt.close()
    
    # 5. DCN内部交换机 vs DCI交换机丢包比较
    if stats['switch_type_by_link']:
        # 提取DCN内部交换机和DCI交换机的丢包数据
        dcn_switches = {}
        dci_switches = {}
        
        for link_type, switch_counts in stats['switch_type_by_link'].items():
            dcn_switches[link_type] = switch_counts.get('DCN Internal Switch', 0)
            dci_switches[link_type] = switch_counts.get('DCI Switch', 0)
        
        if any(dcn_switches.values()) or any(dci_switches.values()):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
            
            # DCN内部交换机丢包
            link_types = list(dcn_switches.keys())
            dcn_values = list(dcn_switches.values())
            ax1.bar(link_types, dcn_values, color='#66b3ff', alpha=0.7)
            ax1.set_title('DCN Internal Switch Drops')
            ax1.set_ylabel('Number of Drops')
            ax1.tick_params(axis='x', rotation=45)
            
            # DCI交换机丢包
            dci_values = list(dci_switches.values())
            ax2.bar(link_types, dci_values, color='#ff9999', alpha=0.7)
            ax2.set_title('DCI Switch Drops')
            ax2.set_ylabel('Number of Drops')
            ax2.tick_params(axis='x', rotation=45)
            
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'switch_comparison.png'), dpi=300, bbox_inches='tight')
            plt.close()

def generate_simple_report(stats, output_dir):
    """生成分析报告"""
    report_path = os.path.join(output_dir, 'drop_analysis_report.txt')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Packet Drop Analysis Report\n")
        f.write("=" * 50 + "\n\n")
        
        # 基本统计
        f.write(f"Total Drops: {stats['total_drops']:,}\n")
        f.write(f"Time Range: {stats['time_range_ms']:.2f} ms\n")
        f.write(f"Average Drop Rate: {stats['total_drops'] / max(stats['time_range_ms'] / 1000, 1):.2f} drops/sec\n\n")
        
        # 链路类型分布
        f.write("Link Type Drop Distribution:\n")
        f.write("-" * 30 + "\n")
        for link_type, count in sorted(stats['link_type_distribution'].items()):
            percentage = (count / stats['total_drops']) * 100
            f.write(f"{link_type}: {count:,} ({percentage:.1f}%)\n")
        
        f.write("\n")
        
        # 丢包原因类型分布
        f.write("Drop Cause Distribution:\n")
        f.write("-" * 30 + "\n")
        for drop_cause, count in sorted(stats['drop_cause_distribution'].items()):
            percentage = (count / stats['total_drops']) * 100
            f.write(f"{drop_cause}: {count:,} ({percentage:.1f}%)\n")
        
        f.write("\n")
        
        # 交换机类型分布
        f.write("Switch Type Drop Distribution:\n")
        f.write("-" * 30 + "\n")
        for switch_type, count in sorted(stats['switch_type_distribution'].items()):
            percentage = (count / stats['total_drops']) * 100
            f.write(f"{switch_type}: {count:,} ({percentage:.1f}%)\n")
        
        f.write("\n")
        
        # 按链路类型的详细分析
        for link_type, cause_counts in stats['drop_cause_by_link'].items():
            if cause_counts:
                f.write(f"{link_type} - Drop Cause Distribution:\n")
                f.write("-" * 30 + "\n")
                
                total_link_drops = sum(cause_counts.values())
                for drop_cause, count in sorted(cause_counts.items()):
                    percentage = (count / total_link_drops) * 100
                    f.write(f"  {drop_cause}: {count:,} ({percentage:.1f}%)\n")
                
                f.write("\n")
        
        # DCN内部交换机 vs DCI交换机比较
        f.write("DCN Internal Switch vs DCI Switch Comparison:\n")
        f.write("-" * 30 + "\n")
        for link_type, switch_counts in stats['switch_type_by_link'].items():
            if switch_counts:
                dcn_drops = switch_counts.get('DCN Internal Switch', 0)
                dci_drops = switch_counts.get('DCI Switch', 0)
                total_switch_drops = dcn_drops + dci_drops
                
                if total_switch_drops > 0:
                    f.write(f"{link_type}:\n")
                    f.write(f"  DCN Internal Switch: {dcn_drops:,} ({(dcn_drops/total_switch_drops)*100:.1f}%)\n")
                    f.write(f"  DCI Switch: {dci_drops:,} ({(dci_drops/total_switch_drops)*100:.1f}%)\n")
                    f.write("\n")
        
        # 按链路类型的节点分布 (Top 5)
        for link_type, node_counts in stats['node_by_link'].items():
            if node_counts:
                f.write(f"{link_type} - Top 5 Nodes with Most Drops:\n")
                f.write("-" * 30 + "\n")
                
                sorted_nodes = sorted(node_counts.items(), key=lambda x: x[1], reverse=True)
                total_link_drops = sum(node_counts.values())
                for node, count in sorted_nodes[:5]:
                    percentage = (count / total_link_drops) * 100
                    f.write(f"  Node {node}: {count:,} ({percentage:.1f}%)\n")
                
                f.write("\n")
    
    print(f"Analysis report saved to: {report_path}")

def main():
    parser = argparse.ArgumentParser(description='丢包分析工具')
    parser.add_argument('drop_file', help='丢包文件路径')
    parser.add_argument('-o', '--output', default='drop_analysis_output', 
                       help='输出目录 (默认: drop_analysis_output)')
    parser.add_argument('-c', '--chunk-size', type=int, default=1000000,
                       help='分块大小 (默认: 1000000)')
    parser.add_argument('-s', '--sample-rate', type=float, default=1.0,
                       help='采样率 0.0-1.0 (默认: 1.0，即不采样)')
    parser.add_argument('--no-plots', action='store_true',
                       help='跳过图表生成，仅生成统计报告')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.drop_file):
        print(f"错误: 文件不存在 {args.drop_file}")
        return 1
    
    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)
    
    # 显示文件信息
    file_size = os.path.getsize(args.drop_file) / (1024 * 1024)  # MB
    print(f"文件大小: {file_size:.1f} MB")
    
    if args.sample_rate < 1.0:
        print(f"采样率: {args.sample_rate:.1%}")
    
    # 开始分析
    start_time = time.time()
    
    try:
        stats = analyze_drop_statistics_simple(
            args.drop_file, 
            chunk_size=args.chunk_size,
            sample_rate=args.sample_rate
        )
        
        # 生成报告
        generate_simple_report(stats, args.output)
        
        # 生成图表
        if not args.no_plots:
            create_simple_visualizations(stats, args.output)
        
        elapsed_time = time.time() - start_time
        print(f"\n分析完成！耗时: {elapsed_time:.1f} 秒")
        print(f"结果保存在: {args.output}")
        
        return 0
        
    except Exception as e:
        print(f"分析过程中出错: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())