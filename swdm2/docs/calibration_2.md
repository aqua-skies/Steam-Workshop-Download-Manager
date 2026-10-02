# SWDM 2.0 D4.8 参数重标定报告 B3（并发上限）

> 日期：2026-10-03 06:05(+08:00）  · 执行：arch-20(t37)
> 基准：`swdm2/tests/Swdm2.UiTests/Calibration/`（B3ConcurrencyCalibration 本地 Kestrel fixture **禁公网** + MetadataApiConcurrencyCalibration **真 API**)
> 环境：代理 http://127.0.0.1:7897 · Kestrel 127.0.0.1:0(IPv4 loopback) · 真元数据 API store.steampowered.com storesearch（匿名+Accept-Language 指纹头）
> 依据：DAG v2.3 D4.8、t3 §5.3/§5.5。设计对照纪律：以下均为**实测事实**，网络失败≠不可行。
> 数据：calibration_2.csv(109 行原始逐行）+ calibration_2.json(机器快照）。

## 推理起点（经验复验：先问"能否更大/能否更小"）

| 参数 | 起点锚 | 问的方向 | 候选 |
|---|---|---|---|
| MaxChunkParallelism | DepotDownloader 默认 8 | **能否更小**（少连接=抵单主机限流） | {1,2,4,8,16} |
| MaxConnectionsPerServer | 同池=8 | **能否更小** | {2,4,8,16} |
| OverlapBytes | D5 spec 16-64 区间（实现 32) | **能否更小**（省带宽） | {16,32,64} |
| ChunkTimeoutMs | bezzad 5000 | 错误率拐点 | {2000,5000,15000} |
| 元数据并发 | 1.x=1（串行） | **能否更大** | {1,2,4} |

判据：**增益≥10% 最大档为默认 + 错误率<2% 门槛**。

## A · 分段并发（本地 Kestrel,8MiB ×2rep,禁公网）

| maxParallel | rep1 | rep2 | ok |
|---|---|---|---|
| 1 | 102ms/80.2MB/s | 22ms/362.6MB/s | 2/2 |
| 2 | 19ms/428.4MB/s | 16ms/487.6MB/s | 2/2 |
| 4 | 17ms/464.2MB/s | 15ms/515.5MB/s | 2/2 |
| 8 | 28ms/284.9MB/s | 19ms/411.1MB/s | 2/2 |
| 16 | 26ms/307.6MB/s | 31ms/259.0MB/s | 2/2 |

- **结论**：localhost=内存级，**rep 方差（4.5x)≫候选差**，无任何候选复现 ≥10% 增益（1 的 rep1 甚至最慢）。
- **锁定 MaxChunkParallelism=8**（不变）：无可复现增益证据 + DepotDownloader 锚 + 风险厌恶（少连接抵单主机限流）。真 CDN 复测留 D5+。

## B · MaxConnectionsPerServer（连接池上限，同 fixture ×2rep)

| maxConn | rep1 | rep2 | ok |
|---|---|---|---|
| 2 | 218.5MB/s | 424.8MB/s | 2/2 |
| 4 | 294.8MB/s | 366.7MB/s | 2/2 |
| 8 | 215.5MB/s | 424.7MB/s | 2/2 |
| 16 | 308.1MB/s | 390.3MB/s | 2/2 |

- **结论**：同 A 无判别力；**锁 8**（对齐 MaxChunkParallelism，连接复用同池）。

## C · OverlapBytes（拼接点校验，D5 spec 16-64,×2rep)

| overlap | 性能 | 拼接校验 | 全字节匹配 |
|---|---|---|---|
| 16 | 250-286MB/s | 过 | 过 |
| 32 | 218-320MB/s | 过 | 过 |
| 64 | 197-370MB/s | 过 | 过 |

- **结论**：三档可靠性同档（校验+全字节匹配全过）→"能否更小"→ **锁 16**(带宽最省；旧值 32)。
- 旁证保留：真网络丢包/CDN 抖动下更大重叠的容错价值，D5 用户体感回归时如见拼接校验失败率上升则回调。

## D · ChunkTimeoutMs（慢端点 256KB/s 供应，1MiB 段 ×2rep)

| timeout | 结果 | 错误率 |
|---|---|---|
| 2000ms | **Timeout 失败**(2/2) | 100% ❌（超拐点） |
| 5000ms | 成功（avg 8154ms) | 0% ✅ |
| 15000ms | 成功（avg 8128ms) | 0% ✅ |

- **结论**：2000ms 在慢供应下 100% 失败（cliff 下沿）；5000 起全过；15000 无增益。**锁 5000**(bezzad 锚+实测拐点之上）。

## E · 元数据并发（**真 API**,storesearch 匿名，4 请求×2rep/档，共 24 请求）

| 并发 | avg 延迟 | ok | 错误率 | 增益 vs 1 |
|---|---|---|---|---|
| 1（串行） | 445.75ms | 8/8 | 0% | — |
| 2 | 414.63ms | 8/8 | 0% | **7.0%** |
| 4 | 416.62ms | 8/8 | 0% | **6.6%** |

- **结论**：24/24 全 200（Accept-Language 指纹头下无 429）；**最大增益 7.0% < 10% 阈值→不放大**；叠加 calibration_1 证据（429=指纹+累计天花 ~117/天级，高并发加速撞天花）→ **保持串行 1**（同 1.x;MaxConcurrentDownloads 同向保守 1)。

## Options 默认值裁决（旧值差异说明）

| 参数 | 旧值 | **新值** | 依据 |
|---|---|---|---|
| MaxChunkParallelism | 8 ⚠️ | **8(锁定）** | A 无可复现增益+DepotDownloader 锚 |
| MaxConnectionsPerServer | 8 ⚠️ | **8(锁定）** | B 无判别力+对齐 |
| OverlapBytes | 32 ⚠️ | **16** | C 三档全过→最小省带宽 |
| ChunkTimeoutMs | 5000 ⚠️ | **5000(锁定）** | D 拐点：2000=100% 错/5000=0% |
| 元数据并发（MaxConcurrentDownloads 同向） | 1 | **1(锁定）** | E 真API 增益 7.0%<10% |

落地：DownloadOptions 注释标[D4.8 已锁定]；HttpSegmentDownloader.OverlapBytes 常量 32→16;AppHost cdnClient 超时接 `Options.ChunkTimeoutMs/1000`。

## 会话内顺带修的真 bug（标定暴露的，已修+回归绿）

1. **in-half 分裂选 in-flight 段**→两 worker 写重叠区=内容交错损坏（SegmentPlanner 加在途集合拒分裂）
2. **HTTP 段写偏移错位**：fetch 恒带重叠前缀但 applyOverlap=false 时 dataOffset=0→把上一段尾部写进自己区（写偏移恒跳前缀）
3. **请求超时只作用于 header 阶段**：读流无超时=慢端点判别失真（CreateRequestScope 涵盖读流+Timeout 优雅失败映射）

## 局限（诚实标注）

- localhost 内存级：A/B/C 增益判据不可判别（rep 方差 4.5x);真 CDN 结论须 D5+ 复测。
- E 单次运行 24 请求（未触 429;指纹头已防）。单出口（香港 IDC) 结论，跨网络条件应复跑。
- 沙箱代理环境与用户真环境差异（fake-IP 出口）。

## qa-20 域评审联署（acceptance 条款过目）

- [x] calibration_2.md/csv/json 三件+旧值差异
- [x] MaxChunkParallelism/ChunkTimeoutMs/OverlapBytes/MaxConnectionsPerServer 锁定（Options/常量/AppHost 落地）
- [x] 元数据并发对真 API(E:24/24 200，增益 7.0%<10%)
- [x] 分段并发强制本地 Kestrel fixture 禁公网（A/B/C/D)
- [x] 增益≥10% 最大档为默认（无达标候选→保守保持）；错误率<2% 门槛（锁定档均 0%)
