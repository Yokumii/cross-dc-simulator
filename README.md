# NS-3 跨数据中心 RDMA 网络仿真器

这是一个基于 [High-Precision-Congestion-Control](https://github.com/alibaba-edu/High-Precision-Congestion-Control) 和 [conweave-ns3](https://github.com/conweave-project/conweave-ns3) 的 NS-3 仿真器，用于研究跨数据中心 RDMA 网络。

本项目在原有单数据中心 RDMA 网络负载均衡功能的基础上，扩展了以下功能：

- **跨数据中心仿真**：支持多数据中心 Fat-tree 拓扑，区分数据中心内（intra-DC）和跨数据中心（inter-DC）流量
- **FEC（前向纠错）**：实现了支持消息感知编码块与交织编码的 FEC 方案，用于在链路错误环境下提高传输可靠性
- **EdgeCNP（边缘拥塞通知）**：在边缘交换机生成 CNP 包，改善跨数据中心流的拥塞控制性能

## 项目结构

```
cross-dc-simulator/
├── simulation/          # NS-3 仿真核心代码
│   ├── src/             # 源代码
│   ├── scratch/         # 仿真脚本
│   ├── config/          # 拓扑和流量配置文件
│   └── mix/output/      # 仿真输出结果
├── scripts/             # 运行脚本
│   ├── run_cross_dc_quick.sh          # 快速运行跨数据中心仿真
│   ├── run_cross_dc_fec_quick.sh      # 快速运行带 FEC 的跨数据中心仿真
│   ├── run_cross_dc_batch.sh          # 批量运行跨数据中心仿真
│   ├── run_edge_cnp_batch.sh          # 批量运行 EdgeCNP 对比实验
│   └── run_fec_comparison_parallel.sh  # 并行运行 FEC 性能对比实验
├── tools/               # 工具脚本
│   ├── topology_gen/    # 拓扑生成器
│   │   ├── cross_dc_topology_gen.py   # 跨数据中心拓扑生成
│   │   └── fat_topology_gen.py        # 单数据中心 Fat-tree 拓扑生成
│   ├── traffic_gen/    # 流量生成器
│   │   ├── cross_dc_traffic_gen.py    # 跨数据中心流量生成
│   │   └── intra_dc_traffic_gen.py    # 数据中心内流量生成
│   └── topo2bdp/       # 拓扑到 BDP 计算工具
└── results/            # 仿真结果输出目录
```

## 快速开始

### 使用 Docker 运行（推荐）

```shell
# 构建 Docker 镜像
docker build -t ns-docker .

# 运行 Docker 容器
docker run -it -v $(pwd):/root ns-docker
```

### 配置和构建 NS-3

```shell
cd simulation
./waf configure --build-profile=optimized
./waf build
```

## 运行仿真

### 1. 跨数据中心基础仿真

运行不带 FEC 的跨数据中心仿真（PFC 关闭，IRN 开启）：

```shell
bash scripts/run_cross_dc_quick.sh
```

支持的主要参数：
- `--simul-time`: 仿真时间（默认：0.02 秒）
- `--intra-load`: 数据中心内负载（默认：0.5）
- `--inter-load`: 跨数据中心负载（默认：0.2）
- `--k-fat`: Fat-tree K 值（默认：4）
- `--num-dc`: 数据中心数量（默认：2）
- `--intra-bw`: 数据中心内带宽 Gbps（默认：100）
- `--inter-bw`: 跨数据中心带宽 Gbps（默认：400）
- `--intra-error`: 数据中心内链路错误率（默认：0.0）
- `--inter-error`: 跨数据中心链路错误率（默认：0.05）
- `--intra-latency`: 数据中心内链路延迟 ns（默认：1000，即 1μs）
- `--inter-latency`: 跨数据中心链路延迟 ns（默认：400000，即 400μs）

示例：
```shell
bash scripts/run_cross_dc_quick.sh \
  --simul-time 0.05 \
  --intra-load 0.6 \
  --inter-load 0.3 \
  --inter-error 0.01
```

### 2. 带 FEC 的跨数据中心仿真

运行带 FEC（前向纠错）的跨数据中心仿真：

```shell
bash scripts/run_cross_dc_fec_quick.sh
```

FEC 相关参数：
- `--fec-enabled`: 是否启用 FEC（默认：1，启用）
- `--fec-block-size`: FEC 块大小 r（默认：64）
- `--fec-interleaving-depth`: FEC 交织深度 c（默认：8）

示例：
```shell
bash scripts/run_cross_dc_fec_quick.sh \
  --inter-error 0.01 \
  --fec-block-size 64 \
  --fec-interleaving-depth 8
```

### 3. FEC 性能对比实验

并行运行多个 FEC 对比实验，测试不同错误率下 FEC 的效果：

```shell
bash scripts/run_fec_comparison_parallel.sh
```

该脚本会：
- 测试多个 inter-DC 错误率（默认：1e-4, 1e-3, 1e-2）
- 对每个错误率运行有/无 FEC 的对比实验
- 使用 screen 在后台并行运行所有实验
- 结果保存在 `results/fec_comparison_parallel_<timestamp>/`

### 4. EdgeCNP 对比实验

批量运行 EdgeCNP 开启/关闭的对比实验：

```shell
bash scripts/run_edge_cnp_batch.sh
```

支持的主要参数：
- `--k-fat`: Fat-tree K 值（默认：4）
- `--num-dc`: 数据中心数量（默认：2）
- `--simul_time`: 仿真时间（默认：0.01）
- `--intra-load`: 数据中心内负载（默认：0.5）
- `--inter-load`: 跨数据中心负载（默认：0.2）
- `--cc`: 拥塞控制算法（默认：dcqcn）
- `--lb`: 负载均衡算法（默认：fecmp）
- `--traffic-type`: 流量类型，`mixed`（混合）或 `intra_only`（仅数据中心内）（默认：mixed）

该脚本会：
- 自动生成所需的拓扑和流量文件
- 在后台并行运行两个仿真（有/无 EdgeCNP）
- 结果保存在 `results/run_edge_cnp_batch_<timestamp>/`

## 结果分析

仿真结果保存在 `results/<script_tag>_<timestamp>/` 目录下，每个仿真运行会生成：

- `*_out_fct.txt`: 流完成时间（FCT）数据
- `*_out_cnp.txt`: 拥塞通知包（CNP）数据
- `*_out_pfc.txt`: PFC 生成数据
- `*_out_drop.txt`: 丢包数据
- `*_out_qlen.txt`: 队列长度监控数据
- `*_out_uplink.txt`: 上行链路利用率数据
- `*_out_fec.txt`: FEC 统计信息（如果启用 FEC）
- `*_out_rto.txt`: RTO 超时信息
- `config.txt`: 仿真配置参数
- `config.log`: 仿真运行日志

## 工具说明

### 拓扑生成

生成跨数据中心 Fat-tree 拓扑：

```shell
cd simulation
python3 ../tools/topology_gen/cross_dc_topology_gen.py \
  <k_fat> <oversubscript> <num_datacenters> \
  <intra_dc_link_rate> <intra_dc_link_latency> \
  <inter_dc_link_rate> <inter_dc_link_latency> \
  [intra_dc_link_error_rate] [inter_dc_link_error_rate]
```

详细说明请参考 [tools/topology_gen/README.md](tools/topology_gen/README.md)。

### 流量生成

生成跨数据中心混合流量：

```shell
cd simulation
python3 ../tools/traffic_gen/cross_dc_traffic_gen.py \
  -k <k_fat> -d <num_datacenters> \
  --intra-load <intra_load> --inter-load <inter_load> \
  --intra-bw <intra_bw> --inter-bw <inter_bw> \
  -t <simulation_time> \
  -c ../tools/traffic_gen/AliStorage2019.txt \
  -o config/<topology>_mixed_flow.txt
```

详细说明请参考 [tools/traffic_gen/README.md](tools/traffic_gen/README.md)。

## 主要功能特性

### 跨数据中心支持

- 支持多数据中心 Fat-tree 拓扑
- 区分数据中心内（intra-DC）和跨数据中心（inter-DC）流量
- 可配置不同的带宽、延迟和错误率
- 支持数据中心互连（DCI）交换机

### FEC（前向纠错）实现机制

本项目实现了一套面向跨数据中心（lossy WAN）场景的透明 FEC 机制，参考 LoWAR 思路做了两点关键工程化对齐：

- **消息感知（message-aware）**：在“消息结束”时对尾块执行 flush，避免尾块不受保护。
- **运行期可观测与可控**：提供可选的 FEC 日志与状态监控，便于定位内存/排队问题。

> 实现位置：`simulation/src/point-to-point/model/qbb-net-device.*`、`fec-encoder.*`、`fec-decoder.*`、`fec-header.*`。

#### 编码过程

1. **编码块组织**：
   - 数据包按序列号分组为编码块，每个块包含 `r` 个数据包（块大小）
   - 每个编码块有唯一的基序列号（base PSN, bPSN），范围从 `bPSN` 到 `bPSN + r - 1`
   - 当前实现按 **五元组（sip/dip/sport/dport）** 维护 FEC 状态，避免跨流/跨消息混编
   - 在跨数据中心仿真中，默认只对 **跨 DC 流** 启用 FEC（intra-DC 流不编码），减少不必要的 repair 注入

2. **交织编码（c 个 coding unit）**：
   - 编码器维护 `c` 个 coding unit（可理解为 `c` 个交织桶）
   - 数据包按 `relativePSN % c` 分配到对应 coding unit
   - 每个 coding unit 维护：
     - `xorBuffer`：该 unit 内数据包载荷的 XOR
     - `recipe`：参与 XOR 的数据包 PSN 列表（用于恢复）

3. **修复包生成**：
   - 当编码块填满（收到 `r` 个数据包）时，最多生成 `c` 个修复包（每个 coding unit 一个）
   - 每个修复包是其所在 coding unit 的 XOR 结果（一个 unit 最多生成一个 repair）
   - 修复包包含：
     - 类型标识（REPAIR）
     - 基序列号（bPSN）
     - 交织序列号（ISN，标识修复包所属 unit）
     - 配方（Recipe）：参与 XOR 的数据包 PSN 列表
   - **尾块 flush**：若消息结束但当前块未满 `r`，仍会生成 repair（携带尾块边界元信息），避免尾块完全依赖重传

4. **包头格式**：
   ```
   - Type (1 byte): DATA (0) / REPAIR (1) / NEGOTIATE (2)
   - Block Size r (2 bytes)
   - Interleaving Depth c (1 byte)
   - Base PSN (4 bytes)
   - DATA: PSN (4 bytes)
   - REPAIR/NEGOTIATE:
     - ISN (2 bytes)（NEGOTIATE 复用为 op-code）
     - EdgeFlags (1 byte): bit0=hasFirst, bit1=hasLast
     - LastRel (2 bytes), LastLength (2 bytes)（尾块裁剪用）
     - RecipeLen (2 bytes) + RecipePSNs (4 bytes each)
   ```

#### 解码与恢复过程

1. **数据包接收**：
   - 使用位图（bitmap）跟踪每个编码块中已接收的数据包
   - 解码器按 flow/block 维护必要的恢复状态，并在完成/超时/窗口推进时回收旧状态，避免常驻内存增长

2. **修复包处理**：
   - 修复包携带 recipe；解码器对 recipe 中“已到达的数据包”做 XOR 抵消，尝试恢复缺失包
   - 为控制内存，解码器不会长期缓存整块数据包副本（更偏向保存 XOR/位图与必要元信息）

3. **丢失包恢复**：
   - 当修复包的配方中**恰好只有一个**数据包丢失时，可以恢复该包
   - 恢复算法：
     ```
     丢失包 = 修复包 XOR (配方中所有已接收的数据包)
     ```
   - 恢复是迭代的：恢复一个包可能使其他修复包能够恢复更多包

4. **恢复条件**：
   - 配方中恰好丢失 1 个包：可恢复
   - 配方中丢失 0 个包：无需恢复
   - 配方中丢失 ≥2 个包：无法恢复（需要更多修复包或等待更多数据包）

5. **缓冲区管理**：
   - 对每个 flow 维护 GC（idle 回收 / 完成回收 / 超时回收），避免大规模五元组导致状态常驻
   - 对无法恢复的包，记录统计信息（可在 `*_out_fec.txt` / 日志中查看）

#### 关键参数

- **块大小 r**：每个编码块包含的数据包数量。较大的 `r` 提供更好的错误恢复能力，但增加延迟和内存开销
- **交织深度 c**：交织层数。更多的层提供更好的突发丢失容忍能力，但增加修复包数量

#### 发送与排队（非常重要）

- **repair 包不会进入 ACK/NACK 的最高优先级队列（qIndex=0）**，而是进入按 PG 的 repair 队列：
  - 目的：避免 repair 绕过背压/准入控制导致交换机侧队列爆炸
  - 当启用 PFC 时，repair 会遵循 `paused[pg]`（不会在暂停类上持续注入）

#### 参数协商（NEGOTIATE）

- 支持通过 NEGOTIATE 包同步未来消息使用的 `(r,c)`；协商结果会延迟到“下一条消息开始”生效，避免中途切参导致编解码不一致。

#### 性能特性

- **突发丢失容忍**：通过将一个块内的数据包条带化地分散到 `c` 个 coding unit，可提升对突发丢失的鲁棒性
- **低延迟**：修复包在编码块完成后立即生成，无需等待确认
- **消息感知**：编码块基于数据包序列号自然划分，无需额外分组逻辑

#### 可观测性（调试/定位内存与排队）

- `--fec-log-enabled 0|1`：是否写入 `*_out_fec.txt`（详细事件日志）
- `--fec-state-mon-enabled 0|1`：是否写入 `*_out_fec_state.txt`（轻量状态监控）
  - 典型字段：`rss_kb / flows / blocks / repairs / xor_bytes / ackq_* / beq_* / sw_mmu_used`

#### 部分仿真结果

**FEC 对 FCT 的改善效果：**

![](https://webp-pic.yokumi.cn/2025/11/20251130135215280.png)

在较大的 Inter-DC 链路丢包率下，启用 FEC 对 FCT 有一定的改善效果。

**启用 FEC 对 RTO 依赖的改善效果：**

在 Inter-DC 链路丢包率为 1% 时，启用 FEC 时对 RTO 超时次数的改善效果高达 43%。

**启用 FEC 对网络拥塞的影响：**

由于 FEC 会额外注入 repair，若不做节流/背压对齐，可能加重排队与拥塞；建议结合状态监控指标评估（尤其是 `beq_pkts/sw_mmu_used`）。

### EdgeCNP（边缘拥塞通知）实现机制

EdgeCNP 是一种在边缘交换机主动生成拥塞通知包（CNP）的机制，专门用于改善跨数据中心长延迟链路的拥塞控制性能。

#### 工作原理

1. **流识别**：
   - 边缘交换机检查每个数据包的源 IP 和目的 IP
   - 使用 `IsCrossDcFlow()` 函数判断是否为跨数据中心流

2. **拥塞检测**：
   - 在数据包通过交换机的出口队列时，检查队列拥塞状态
   - 调用 `ShouldSendCN(outDev, qIndex)` 判断是否应该发送 CNP
   - 拥塞判断基于出口队列的共享缓冲区使用量：
     - 如果使用量 > `kmax[ifindex]`：立即发送 CNP
     - 如果使用量在 `kmin[ifindex]` 和 `kmax[ifindex]` 之间：按概率发送 CNP
       ```
       p = (used - kmin) / (kmax - kmin) * pmax
       ```
     - 如果使用量 < `kmin[ifindex]`：不发送 CNP

3. **CNP 生成**：
   - 创建新的 CNP 包，包含以下信息：
     - **QBB 头部**：
       - 序列号设为 `UINT32_MAX`（标识为 CNP）
       - 优先级组（PG）使用原始数据包的 PG
       - 源端口和目的端口互换（用于路由回发送端）
       - 设置 CNP 标志
       - 复制原始数据包的 INT 头部（如果存在）
     - **IP 头部**：
       - 源 IP = 原始数据包的目的 IP
       - 目的 IP = 原始数据包的源 IP
       - 协议号 = 0xFC（NACK 协议号）
     - **流标识**：复制原始数据包的 FlowIDNUMTag，确保 CNP 能正确路由到对应的流

4. **频率限制**：
   - 为每个流维护一个流键（flow key），包含：源 IP、目的 IP、源端口、目的端口、优先级组
   - 记录每个流上次发送 CNP 的时间
   - 如果距离上次发送 CNP 的时间间隔 < `EdgeCnpInterval`（默认 4 微秒），则跳过本次发送
   - 这避免了在短时间内对同一流发送过多 CNP，减少网络开销

5. **CNP 发送**：
   - CNP 包通过交换机的入口设备发送回发送端
   - 使用 `SwitchSend()` 函数将 CNP 注入网络

#### 设计优势

1. **早期拥塞检测**：
   - 在边缘交换机检测拥塞，无需等待数据包到达核心网络或接收端
   - 对于跨数据中心的长延迟链路，可以更早地通知发送端降低速率

2. **针对跨数据中心流**：
   - 只对跨数据中心流生成 EdgeCNP，避免对数据中心内流产生不必要的开销
   - 数据中心内流通常延迟较低，传统的端到端拥塞控制已足够

3. **频率控制**：
   - 通过最小间隔限制，避免对同一流发送过多 CNP
   - 减少网络开销和发送端的处理负担

4. **与现有机制兼容**：
   - EdgeCNP 与传统的端到端 CNP 机制可以共存
   - 发送端可以同时接收来自边缘交换机和接收端的 CNP

#### 配置参数

- **EdgeCnpEnabled**：是否启用 EdgeCNP（默认：false）
- **EdgeCnpInterval**：同一流的最小 CNP 发送间隔（默认：4 微秒）
- **拥塞阈值**（kmin, kmax, pmax）：在 `switch-mmu.cc` 中配置，控制拥塞检测的敏感度

#### 使用场景

EdgeCNP 特别适用于：
- 跨数据中心的长延迟链路（延迟 > 100μs）
- 高带宽利用率场景
- 需要快速响应拥塞的实时应用

#### 部分仿真结果

**启用 EdgeCNP 对 FCT 的改善效果：**

![](https://webp-pic.yokumi.cn/2025/11/20251130141453296.png)

**其他指标：**

| Metric            | With EdgeCNP        | Without EdgeCNP     | Improvement (%) |
|-------------------|----------------------|-----------------------|------------------|
| Total PFC Count   | 83,148              | 102,909              | 19.20%           |
| Total PFC Time    | 510,941,555 ns      | 694,859,383 ns       | 26.47%           |
| Avg PFC Time      | 6,144.97 ns         | 6,752.17 ns          | 8.99%            |
| Total CNP Count   | 4,075               | 4,483                | -9.10%           |

Edge-CNP 能有效减少网络中 PFC 触发的频率，同时也能使每次 PFC 事件的严重程度降低，能够快速得到恢复。一定程度上验证了针对跨数据中心场景，通过在边界交换机直接发送 CNP 信号，能够缩短拥塞反馈路径，从而提高网络性能。

另外，虽然项目暂时未对 CNP 重复发送的可能加以限制，但实际实验中 CNP 的发送总数（包括 Edge-CNP）甚至少于不开启的情况。

## 主要修改

主要实现位于 `simulation/src/point-to-point/model/`：

- `switch-node.h/cc`: 交换机逻辑，包括路由和 EdgeCNP 生成
- `switch-mmu.h/cc`: 入口/出口准入控制和 PFC
- `qbb-net-device.h/cc`: QBB 网络设备，包含 FEC 编码/解码逻辑
- `fec-encoder.h/cc`: FEC 编码器，实现 LoWAR 编码算法
- `fec-decoder.h/cc`: FEC 解码器，处理修复包和数据包恢复
- `fec-xor-engine.h/cc`: FEC XOR 引擎，提供核心 XOR 操作
- `fec-header.h/cc`: FEC 包头定义
- `rdma-hw.h/cc`: RDMA 硬件 NIC 行为模型
- `settings.h/cc`: 全局变量和配置

## 清理

清理所有之前的仿真结果：

```shell
bash scripts/cleanup.sh
```

## TODO

- [ ] 优化 FEC 模块，当前 FEC 模块启用后事件模拟器整体运行速度较慢；
- [ ] 优化 FEC 机制；

## LICENSE

See the [LICENSE](LICENSE) file for more details.
