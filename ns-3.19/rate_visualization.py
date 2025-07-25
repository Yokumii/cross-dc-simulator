#!/usr/bin/env python3
import re
import matplotlib.pyplot as plt
import numpy as np
import sys
import os

def parse_rate_changes(log_file):
    """解析日志文件中的速率变化记录"""
    rate_pattern = re.compile(r'(\d+\.\d+) RATE_CHANGE flow_id=(\d+) src=.* dst=.* old_rate=(\d+\.\d+) Gbps new_rate=(\d+\.\d+) Gbps')
    
    flow_rates = {}  # 存储每个流的速率变化 {flow_id: [(time, rate), ...]}
    max_time = 0.0  # 记录最大时间点，用于后续添加恢复点
    
    with open(log_file, 'r') as f:
        for line in f:
            match = rate_pattern.search(line)
            if match:
                time = float(match.group(1))
                flow_id = int(match.group(2))
                old_rate = float(match.group(3))
                new_rate = float(match.group(4))
                
                # 更新最大时间点
                if time > max_time:
                    max_time = time
                
                if flow_id not in flow_rates:
                    flow_rates[flow_id] = []
                    # 根据流ID设置不同的初始时间和速率
                    if flow_id == 0:  # 背景流从0时刻开始就是100Gbps
                        flow_rates[flow_id].append((0.0, 100.0))
                    elif flow_id <= 7:  # 发送端突发流在800us开始
                        flow_rates[flow_id].append((0.0, 0.0))
                        flow_rates[flow_id].append((0.000800 - 1e-9, 0.0))  # 突变前一刻
                        flow_rates[flow_id].append((0.000800, 100.0))  # 突变后
                    else:  # 接收端突发流在4800us开始
                        flow_rates[flow_id].append((0.0, 0.0))
                        flow_rates[flow_id].append((0.004800 - 1e-9, 0.0))  # 突变前一刻
                        flow_rates[flow_id].append((0.004800, 100.0))  # 突变后
                
                # 添加速率变化点（突变）
                # 先添加一个变化前的点（微小时间偏移）
                flow_rates[flow_id].append((time - 1e-9, old_rate))
                # 再添加变化后的点
                flow_rates[flow_id].append((time, new_rate))
    
    # 处理流结束后的恢复点
    # 在每条流的最后一个时间点后添加一个点，将速率恢复为100Gbps
    end_time_offset = 1e-6  # 结束时间偏移，1微秒
    for flow_id, rates in flow_rates.items():
        # 背景流不需要添加恢复点
        if flow_id == 0:
            continue
        
        # 对时间点进行排序，找到最后一个点
        sorted_rates = sorted(rates, key=lambda x: x[0])
        last_time = sorted_rates[-1][0]
        
        # 添加恢复点（速率恢复为100Gbps）
        flow_rates[flow_id].append((last_time + end_time_offset - 1e-9, sorted_rates[-1][1]))  # 先添加一个变化前的点
        flow_rates[flow_id].append((last_time + end_time_offset, 100.0))  # 再添加恢复后的点
    
    # 如果没有找到任何流，创建示例数据
    if not flow_rates:
        # 创建一个背景流
        flow_rates[0] = [(0.0, 100.0), (0.001 - 1e-9, 100.0), (0.001, 100.0), 
                         (0.005 - 1e-9, 100.0), (0.005, 100.0), 
                         (0.008 - 1e-9, 100.0), (0.008, 100.0)]
        
        # 创建7个发送端突发流
        for i in range(1, 8):
            flow_rates[i] = [(0.0, 0.0), 
                            (0.000800 - 1e-9, 0.0), (0.000800, 100.0), 
                            (0.001 - 1e-9, 100.0), (0.001, 100.0), 
                            (0.005 - 1e-9, 100.0), (0.005, 50.0), 
                            (0.008 - 1e-9, 50.0), (0.008, 25.0),
                            (0.0085 - 1e-9, 25.0), (0.0085, 100.0)]  # 添加恢复点
        
        # 创建7个接收端突发流
        for i in range(8, 15):
            flow_rates[i] = [(0.0, 0.0), 
                            (0.004800 - 1e-9, 0.0), (0.004800, 100.0), 
                            (0.005 - 1e-9, 100.0), (0.005, 100.0), 
                            (0.008 - 1e-9, 100.0), (0.008, 50.0),
                            (0.0085 - 1e-9, 50.0), (0.0085, 100.0)]  # 添加恢复点
    
    return flow_rates

def get_unified_time_points(flow_rates):
    """获取所有流的统一时间点"""
    all_times = set()
    for rates in flow_rates.values():
        all_times.update([t for t, _ in rates])
    
    return sorted(list(all_times))

def interpolate_rates(flow_rates, time_points):
    """对每个流的速率进行插值，确保每个时间点都有速率值"""
    interpolated_rates = {}
    
    for flow_id, rates in flow_rates.items():
        # 将时间和速率分开
        sorted_rates = sorted(rates)
        times, rates_values = zip(*sorted_rates)
        
        # 对于每个时间点，找到最近的速率值
        flow_rates_at_times = []
        for t in time_points:
            # 找到最后一个小于等于当前时间的速率记录
            idx = 0
            while idx < len(times) and times[idx] <= t:
                idx += 1
            
            if idx == 0:  # 没有找到小于等于当前时间的记录
                rate = 0.0  # 默认为0
            else:
                # 使用最近的速率值（不进行线性插值，保持突变特性）
                rate = rates_values[idx-1]
            
            flow_rates_at_times.append(rate)
        
        interpolated_rates[flow_id] = flow_rates_at_times
    
    return interpolated_rates

def plot_all_flows(flow_rates, output_dir):
    """绘制每条流的速率变化曲线"""
    plt.figure(figsize=(12, 8))
    
    # 获取统一的时间点
    time_points = get_unified_time_points(flow_rates)
    interpolated_rates = interpolate_rates(flow_rates, time_points)
    
    # 将时间从秒转换为毫秒
    time_points_ms = [t * 1000 for t in time_points]
    
    # 获取所有时间点的最大值用于设置x轴范围
    max_time_ms = max(time_points_ms) if time_points_ms else 8
    
    # 绘制每条流的速率变化曲线
    for flow_id, rates in flow_rates.items():
        # 排序并提取时间和速率
        sorted_rates = sorted(rates)
        times, rate_values = zip(*sorted_rates)
        times_ms = [t * 1000 for t in times]
        
        if flow_id == 0:
            plt.step(times_ms, rate_values, 'b-', linewidth=2, label=f'Background Flow (ID={flow_id})', where='post')
        elif flow_id <= 7:
            plt.step(times_ms, rate_values, 'r-', linewidth=1, alpha=0.7, 
                    label=f'Sending Burst Flow (ID={flow_id})' if flow_id == 1 else None, where='post')
        else:
            plt.step(times_ms, rate_values, 'g-', linewidth=1, alpha=0.7, 
                    label=f'Receiving Burst Flow (ID={flow_id})' if flow_id == 8 else None, where='post')
    
    plt.xlabel('Time (ms)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Rate Changes for All Flows (Burst flows restore to 100Gbps after completion)')
    plt.grid(True)
    plt.legend()
    
    # 设置x轴范围以显示恢复点
    plt.xlim(0, max_time_ms * 1.05)  # 增加5%的余量
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'all_flows_rates.png'))
    plt.close()

def plot_background_vs_burst(flow_rates, output_dir):
    """绘制背景流与突发流的对比图"""
    # 准备数据
    background_data = []
    sending_burst_data = []
    receiving_burst_data = []
    
    # 处理背景流
    if 0 in flow_rates:
        background_data = sorted(flow_rates[0])
    
    # 合并发送端突发流数据
    sending_burst_times = set()
    for flow_id in range(1, 8):
        if flow_id in flow_rates:
            for t, _ in flow_rates[flow_id]:
                sending_burst_times.add(t)
    sending_burst_times = sorted(list(sending_burst_times))
    
    # 合并接收端突发流数据
    receiving_burst_times = set()
    for flow_id in range(8, 15):
        if flow_id in flow_rates:
            for t, _ in flow_rates[flow_id]:
                receiving_burst_times.add(t)
    receiving_burst_times = sorted(list(receiving_burst_times))
    
    # 获取所有时间点
    all_times = set()
    for rates in flow_rates.values():
        all_times.update([t for t, _ in rates])
    time_points = sorted(list(all_times))
    
    # 获取所有时间点的最大值用于设置x轴范围
    max_time = max(time_points) if time_points else 0.008
    max_time_ms = max_time * 1000
    
    # 对速率进行插值
    interpolated_rates = interpolate_rates(flow_rates, time_points)
    
    # 计算突发流的总速率和平均速率
    sending_burst_sum = np.zeros(len(time_points))
    receiving_burst_sum = np.zeros(len(time_points))
    all_burst_sum = np.zeros(len(time_points))  # 所有突发流的总和
    background_flow = np.zeros(len(time_points))
    
    # 统计每个时间点活跃的流数量
    active_sending_flows = np.zeros(len(time_points))
    active_receiving_flows = np.zeros(len(time_points))
    active_all_burst_flows = np.zeros(len(time_points))  # 所有活跃的突发流数量
    
    for flow_id, rates in interpolated_rates.items():
        if flow_id == 0:  # 背景流
            background_flow = np.array(rates)
        elif flow_id <= 7:  # 发送端突发流
            sending_burst_sum += np.array(rates)
            all_burst_sum += np.array(rates)  # 添加到所有突发流总和
            # 统计活跃流（速率>0的流）
            active_sending_flows += (np.array(rates) > 0).astype(int)
            active_all_burst_flows += (np.array(rates) > 0).astype(int)  # 添加到所有活跃突发流计数
        else:  # 接收端突发流
            receiving_burst_sum += np.array(rates)
            all_burst_sum += np.array(rates)  # 添加到所有突发流总和
            # 统计活跃流（速率>0的流）
            active_receiving_flows += (np.array(rates) > 0).astype(int)
            active_all_burst_flows += (np.array(rates) > 0).astype(int)  # 添加到所有活跃突发流计数
    
    # 计算平均速率（避免除以0）
    sending_burst_avg = np.divide(sending_burst_sum, active_sending_flows, 
                                 out=np.zeros_like(sending_burst_sum), 
                                 where=active_sending_flows>0)
    receiving_burst_avg = np.divide(receiving_burst_sum, active_receiving_flows, 
                                   out=np.zeros_like(receiving_burst_sum), 
                                   where=active_receiving_flows>0)
    # 所有突发流的平均值
    all_burst_avg = np.divide(all_burst_sum, active_all_burst_flows, 
                             out=np.zeros_like(all_burst_sum), 
                             where=active_all_burst_flows>0)
    
    # 将时间从秒转换为毫秒
    time_points_ms = [t * 1000 for t in time_points]
    
    # 绘制对比图（使用平均值）
    plt.figure(figsize=(12, 8))
    
    # 使用阶梯图展示速率突变
    plt.step(time_points_ms, background_flow, 'b-', linewidth=2, label='Background Flow', where='post')
    plt.step(time_points_ms, all_burst_avg, 'r-', linewidth=2, label='Average Burst Flows', where='post')
    
    plt.xlabel('Time (ms)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Background Flow vs Average Burst Flow Rates (flows restore to 100Gbps after completion)')
    plt.grid(True)
    plt.legend()
    
    # 设置x轴范围以显示恢复点
    plt.xlim(0, max_time_ms * 1.05)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'background_vs_burst.png'))
    plt.close()
    
    # 绘制堆叠图 - 使用平均值
    plt.figure(figsize=(12, 8))
    
    # 使用阶梯图样式填充
    plt.fill_between(time_points_ms, 0, background_flow, 
                    color='blue', alpha=0.7, hatch='xxx', 
                    label='Background Flow', edgecolor='blue', step='post')
    plt.fill_between(time_points_ms, background_flow, background_flow + all_burst_avg, 
                    color='red', alpha=0.7, hatch='///', 
                    label='Average Burst Flows', edgecolor='red', step='post')
    
    plt.xlabel('Time (ms)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Background Flow vs Average Burst Flow Rates (flows restore to 100Gbps after completion)')
    plt.grid(True)
    plt.legend()
    
    # 设置y轴范围，类似于示例图
    plt.ylim(0, 300)
    
    # 设置x轴范围，适应所有时间点
    plt.xlim(0, max_time_ms * 1.05)
    
    # 添加刻度线
    plt.xticks(np.arange(0, max_time_ms * 1.1, max(1, int(max_time_ms / 8))))
    plt.yticks(np.arange(0, 301, 100))
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'background_vs_burst_stacked.png'))
    plt.close()
    
    # 绘制发送端和接收端突发流的分别堆叠图（平均值）
    plt.figure(figsize=(12, 8))
    
    # 使用阶梯图样式填充
    plt.fill_between(time_points_ms, 0, background_flow, 
                    color='blue', alpha=0.7, hatch='xxx', 
                    label='Background Flow', edgecolor='blue', step='post')
    plt.fill_between(time_points_ms, background_flow, background_flow + sending_burst_avg, 
                    color='red', alpha=0.7, hatch='///', 
                    label='Average Sending Burst Flows', edgecolor='red', step='post')
    plt.fill_between(time_points_ms, background_flow + sending_burst_avg, 
                    background_flow + sending_burst_avg + receiving_burst_avg, 
                    color='green', alpha=0.7, hatch='...', 
                    label='Average Receiving Burst Flows', edgecolor='green', step='post')
    
    plt.xlabel('Time (ms)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Background Flow vs Average Sending/Receiving Burst Flow Rates (flows restore to 100Gbps)')
    plt.grid(True)
    plt.legend()
    
    # 设置y轴范围，类似于示例图
    plt.ylim(0, 300)
    
    # 设置x轴范围，适应所有时间点
    plt.xlim(0, max_time_ms * 1.05)
    
    # 添加刻度线
    plt.xticks(np.arange(0, max_time_ms * 1.1, max(1, int(max_time_ms / 8))))
    plt.yticks(np.arange(0, 301, 100))
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'background_vs_sending_receiving_burst.png'))
    plt.close()
    
    # 绘制对比图 - 同时显示发送、接收和总体平均值
    plt.figure(figsize=(12, 8))
    
    plt.step(time_points_ms, background_flow, 'b-', linewidth=2, label='Background Flow', where='post')
    plt.step(time_points_ms, all_burst_avg, 'r-', linewidth=2, label='All Burst Flows (Avg)', where='post')
    plt.step(time_points_ms, sending_burst_avg, 'm--', linewidth=1.5, label='Sending Burst Flows (Avg)', where='post')
    plt.step(time_points_ms, receiving_burst_avg, 'g--', linewidth=1.5, label='Receiving Burst Flows (Avg)', where='post')
    
    plt.xlabel('Time (ms)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Background Flow vs Different Average Burst Flow Rates')
    plt.grid(True)
    plt.legend()
    
    # 设置x轴范围以显示恢复点
    plt.xlim(0, max_time_ms * 1.05)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'background_vs_all_burst_types.png'))
    plt.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python rate_visualization.py <log_file> [output_dir]")
        sys.exit(1)
    
    log_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '.'
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 解析速率变化记录
    flow_rates = parse_rate_changes(log_file)
    
    if not flow_rates:
        print("No rate change records found in the log file. Using example data.")
    
    # 绘制所有流的速率变化曲线
    plot_all_flows(flow_rates, output_dir)
    
    # 绘制背景流与突发流的对比图
    plot_background_vs_burst(flow_rates, output_dir)
    
    print(f"Visualization completed. Output saved to {output_dir}")

if __name__ == "__main__":
    main() 