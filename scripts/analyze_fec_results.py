#!/usr/bin/python3
"""
FEC性能对比实验 - 结果分析脚本
分析6个场景的FCT、丢包率等关键指标
"""

import os
import sys
import re
from pathlib import Path

def parse_fct_file(fct_file):
    """解析FCT文件，返回平均FCT和99th百分位FCT"""
    if not os.path.exists(fct_file):
        return None, None

    fcts = []
    with open(fct_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 7:
                try:
                    fct = float(parts[6])  # FCT在第7列
                    fcts.append(fct)
                except ValueError:
                    continue

    if not fcts:
        return None, None

    fcts.sort()
    avg_fct = sum(fcts) / len(fcts)
    p99_idx = int(len(fcts) * 0.99)
    p99_fct = fcts[p99_idx] if p99_idx < len(fcts) else fcts[-1]

    return avg_fct, p99_fct

def parse_config_log(log_file):
    """从config.log中提取统计信息"""
    stats = {}

    if not os.path.exists(log_file):
        return stats

    with open(log_file, 'r') as f:
        content = f.read()

        # 提取丢包统计
        drop_match = re.search(r'Total drops: (\d+)', content)
        if drop_match:
            stats['total_drops'] = int(drop_match.group(1))

        # 提取FEC统计
        encoded_match = re.search(r'FEC encoded packets: (\d+)', content)
        if encoded_match:
            stats['fec_encoded'] = int(encoded_match.group(1))

        recovered_match = re.search(r'FEC recovered packets: (\d+)', content)
        if recovered_match:
            stats['fec_recovered'] = int(recovered_match.group(1))

    return stats

def analyze_results(results_dir):
    """分析实验结果"""
    results_dir = Path(results_dir)

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    print("=" * 80)
    print("FEC性能对比实验 - 结果分析")
    print("=" * 80)
    print()

    # 收集所有场景的结果
    scenarios = {}

    for task_dir in sorted(results_dir.glob("err_*")):
        if not task_dir.is_dir():
            continue

        task_name = task_dir.name

        # 查找输出目录
        output_dirs = list(task_dir.glob("[0-9]*"))
        if not output_dirs:
            print(f"⚠ {task_name}: 未找到输出目录")
            continue

        output_dir = output_dirs[0]  # 取第一个

        # 查找FCT文件
        fct_files = list(output_dir.glob("*_out_fct.txt"))
        if not fct_files:
            print(f"⚠ {task_name}: 未找到FCT文件")
            continue

        fct_file = fct_files[0]
        config_log = output_dir / "config.log"

        # 解析结果
        avg_fct, p99_fct = parse_fct_file(fct_file)
        stats = parse_config_log(config_log)

        scenarios[task_name] = {
            'avg_fct': avg_fct,
            'p99_fct': p99_fct,
            'stats': stats
        }

    if not scenarios:
        print("错误: 未找到任何有效的结果数据")
        return

    # 按错误率分组显示
    error_rates = ['1e-4', '1e-3', '1e-2']

    print(f"{'场景':<25} {'平均FCT (us)':<15} {'P99 FCT (us)':<15} {'总丢包':<12} {'FEC恢复':<12}")
    print("-" * 80)

    comparison = {}  # 用于保存对比数据

    for error_label in error_rates:
        print(f"\nInter-DC错误率 = {error_label}:")
        print("-" * 80)

        no_fec_key = f"err_{error_label}_no-fec"
        with_fec_key = f"err_{error_label}_with-fec"

        fec_improvement = {}

        for fec_label, scenario_key in [("无FEC", no_fec_key), ("启用FEC", with_fec_key)]:
            if scenario_key in scenarios:
                data = scenarios[scenario_key]
                avg_fct = data['avg_fct']
                p99_fct = data['p99_fct']
                drops = data['stats'].get('total_drops', 'N/A')
                recovered = data['stats'].get('fec_recovered', 'N/A')

                if avg_fct is not None:
                    print(f"  {fec_label:<23} {avg_fct:>13.2f}   {p99_fct:>13.2f}   {str(drops):>10}   {str(recovered):>10}")

                    # 保存用于对比
                    if fec_label == "无FEC":
                        fec_improvement['no_fec_avg'] = avg_fct
                        fec_improvement['no_fec_p99'] = p99_fct
                    else:
                        fec_improvement['with_fec_avg'] = avg_fct
                        fec_improvement['with_fec_p99'] = p99_fct
                else:
                    print(f"  {fec_label:<23} {'N/A':>13}   {'N/A':>13}   {str(drops):>10}   {str(recovered):>10}")
            else:
                print(f"  {fec_label:<23} {'未运行':>13}")

        # 计算改善百分比
        if 'no_fec_avg' in fec_improvement and 'with_fec_avg' in fec_improvement:
            avg_improvement = (fec_improvement['no_fec_avg'] - fec_improvement['with_fec_avg']) / fec_improvement['no_fec_avg'] * 100
            p99_improvement = (fec_improvement['no_fec_p99'] - fec_improvement['with_fec_p99']) / fec_improvement['no_fec_p99'] * 100

            comparison[error_label] = {
                'avg_improvement': avg_improvement,
                'p99_improvement': p99_improvement
            }

            print(f"\n  → FEC改善: 平均FCT {avg_improvement:+.2f}%, P99 FCT {p99_improvement:+.2f}%")

    # 总结
    print("\n" + "=" * 80)
    print("总结: FEC性能改善")
    print("=" * 80)

    for error_label in error_rates:
        if error_label in comparison:
            data = comparison[error_label]
            print(f"错误率 {error_label:>6}: 平均FCT改善 {data['avg_improvement']:>6.2f}%, P99改善 {data['p99_improvement']:>6.2f}%")

    print("\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 analyze_fec_results.py <结果目录>")
        print("示例: python3 analyze_fec_results.py ../results/fec_comparison_parallel_20251128_150000/")
        sys.exit(1)

    results_dir = sys.argv[1]
    analyze_results(results_dir)
