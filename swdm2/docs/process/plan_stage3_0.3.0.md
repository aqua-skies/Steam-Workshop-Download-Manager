# SWDM 2.0 阶段 3 规划（D3.1-D3.8 · 下载域核心）

> 状态：**4/4 评审通过（arch-20/qa-20/visual-20/captain 全赞成，建议全部并入），待用户确认开工**
> 来源：DAG v2.3 swdm2/docs/architecture_2.0.md §6 表 + 阶段 2 已验证事实
> 依赖链（DAG 硬约束）:D1.*(已完成）→D3.1→D3.2→D3.5→D3.5b→D3.7→D3.8;D3.3/D3.4 可提前；D3.5 依赖 D3.4;D3.7 依赖 D3.5b
> 版本：计划目标 0.3.0(D3.8 门）

## 阶段 2 已验证的衔接事实（非假设）

- Core 强类型 id/Result/SteamError 契约（72/0)
- IHttpClientFactory+指纹头（429 实测：累计天花板 ~117 请求=请求总量预算）
- 节流 1s+熔断器（5 连失败→Open→60s 冷却→半开）=D3.5 进程级调度的上层护栏
- 可达门模式（IConnectivityState 阻止不可达域发请求）=D3.5 前置条件同源
- SP-3 驱动测试通道（SteamTestsDriver 反射模式）+clean+warnaserror 口径

## 任务拆分与验收判据（每任务=方案+代码+验证+提交四件套）

### D3.1 (A) 状态机与队列 · src/Swdm2.Downloads/Queue/
- 契约：DownloadTask 状态机（枚举+转移表断言：待定→排队→下载中→（暂停/取消/失败）→完成，非法转移抛异常可测）;IDownloadQueue+Channel 单消费者；调度器级并发（参数 C7 起点同 D2.6 方法=实测重标定前保守 2)
- 验证：非法转移抛异常可测；入队自动进队列；并发槽配置控制
- 验证方式：Swdm2.Downloads.Tests（新建）+ DownloadsTestsDriver(SP-3 同模式）
- 执行者：arch-20（域 owner:Core/Resilience 同源状态机经验）

### D3.2 (A) 事件总线与进度聚合 · src/Swdm2.Downloads/Events/
- 契约：IDownloadEventBus;EMA/平均速度/ETA;UI 节流刷新（ProgressThrottleMs=100 ⚠️[C7 待实测]-arch-20 建议）
- 验收：高频回调不击穿节流；事件负载不可变（记录+防御性拷贝，同 Core D1.1 纪律）
- **补充验收（arch-20 细化）**:1ms 级高频事件源采样测试，确认 100ms 节流不丢尾帧/不积压；若实测不足则改参（经验复验纪律）
- 执行者：arch-20

### D3.3 (A) steamcmd 部署 · src/Swdm2.Steam/SteamCmd/
- 契约：ISteamCmdDeployer:zip 下载（走 D2.1 工厂+指纹头）+解压+exe 校验
- 验收（M1 qa-20 补强：Valve 无官方签名→哈希=自记录基线）:exe 存在+`+login anonymous +version` 退出码 0 且版本串可解析；首次部署后记指纹基线，二次下载比对防损坏/篡改（非完整性权威验证）；损坏 zip 触发重下（幂等，走 D2.4 熔断器+退避=已建好的护栏）
- 执行者：qa-20（D2.5 社区源+CalibBench 真实网络经验）

### D3.4 (A) steamcmd runner（1.x 正则全量移植+C# 重写）· src/Swdm2.Steam/SteamCmd/
- 契约：批拼命令；1.x 正则成功三元判定；Sweep 校验；失败清空目录；stdin 关闭；三段式收割看门狗；输出脱敏
- 验收（1.x 同尺度的线上回归）:真实下载匿名 mod(sub17906,app 4000) 成功且产物递归非空；**进度估算偏差（M2 qa-20 补强，可断言）:完成点估算字节 vs 实际产物字节 <10%(1.x 同法，C# 实现须复测对齐=经验复验具体化）**;kill 后无僵尸进程
- 验证方式：`Category=Online` 隔离（沙箱网络阻断时走 captain 代理直连复验，同 D2.3 模式）
- 执行者：qa-20(1.x steamcmd_runner.py 原作者经验移植）

### D3.5 (A) SteamCmdProvider 接入链 · src/Swdm2.Downloads/Providers/
- 契约：IDownloadProvider:进程级信号量；进度=stdout 行磁盘增长估算；分段数 N/A 诚实降级
- 验收：队列驱动下载真实 mod 成功；暂停/取消杀进程干净（产物目录无半成品=原子性）
- **进度偏差量化阈值（arch-20 细化，1.X 不可判→可判）**:估算与实际字节差 ±15% 内报警统计，超阈降级"分段数 N/A"诚实路径（不伪装精度）
- 执行者：arch-20（D3.1 队列+D3.5 provider 耦合最紧，同一 owner 减交接债）
- 前置门：D3.4 完成；可达门+熔断器接入（S4 同源）

### D3.5b (A) App 最小可测 UI(visual-20 执行前提·方案 A,captain 裁决采纳）· src/Swdm2.App/
- 契约：D3.7 需可点击 UI，而皮肤级 UI 在阶段 5——本任务补**最小可测骨架**：详情页下载按钮+下载页任务行/状态文本+完成弹窗；AutomationId 按 t3 §3.2 保留表（`ModDetailPage_DownloadButton`/`DownloadsPage_TaskList_Item__StateText` 等）
- 验收：可点击+状态文本可断言；**皮肤级观感留 D5,本阶段仅可测骨架**（不提前做视觉）
- 前置门：D3.5 完成（provider 就绪才有真状态可绑）
- 执行者：visual-20(App UI 域 owner,t2 视觉规格+读图链路经验）
- 方案 B（两段交付延 D5.6)否决理由：0.3.0 门内 D3.7 绿灯才能闭合"阶段 3=下载主旅程可跑通"的交付语义；与用户体感原则一致

### D3.6 (A) 串行化与句柄纪律
- 契约：进程级 SemaphoreSlim;局部变量保存进程句柄（防早释）；**WaitAsync(timeout) 超时语义（M4 qa-20 补强）：超时映射 SteamError 而非挂死 UI/队列**
- 验收：并发两任务请求 steamcmd→第二等待（不覆盖句柄、不 NRE);**等待超时不产生 NRE、不覆盖句柄**（1.x 句柄 bug 原地一并断言）
- 执行者：qa-20（1.x 该 bug 原作者，归属制）

### D3.7 (Q) UiTests P0 冒烟：下载主旅程 · tests/Swdm2.UiTests/
- 契约：FlaUI 真实输入（鼠标点击+键盘）：入队→冒等待→完成→断言状态与产物计数（弹窗 #255 路径）
- 验收：FlaUI 绿；失败截图+读图校验
- 验证方式：UiTestsDriver+桌面双通道（用户硬纪律：真实输入不造假）
- 执行者：visual-20(UiTests 实现域：t4 spike 读图链路+视觉规格 owner)
- **qa-20 域审条款（M3）：D3.7 完成后交 qa-20 按 t3 §4.2 #10-#14 场景映射、AutomationId 保留表、输入三规则、失败截图 Q10 审阅（UiTests 契约域 owner 职责落点，同 UiTestsDriver 审阅流程）**

### D3.8 (C) 阶段 3 交付门
- 四要素（版本 0.3.0):全量回归（新旧测试全跑+clean 口径）+讨论组三原则+版本号+CHANGELOG
- 执行者：captain 关门（同 0.1.0/0.2.0)

## 整体风险与处置（诚实标注）

1. **steamcmd 匿名下载限额**：1.x 同环境实测匿名下载大文件可行（429 学费在 metadata 层，content 层是 steamcmd 二进制协议）；若触发退出码 5/无网络=弯路嫌疑→换网络条件复验（设计对照纪律）
2. **进度估算精度**:stdout 行磁盘增长估算（1.x 同法）——C# 实现复测偏差对齐（经验复验：参数类须重测）
3. **成员退化预案**：长会话 stall 规律已三次确认——D3.x 每任务以"一段一段"粒度派发+认领后 60 秒无响应即 captain 接管（0.2.0 验证有效的 SOP)

## 验证矩阵（阶段 3 增量回归目标）

| 验证 | 目标 |
|---|---|
| build(clean+warnaserror) | 0-0 |
| CoreTestsDriver | 72/0 保持 |
| SteamTestsDriver | 78+D3.3/3.4/3.6 新增/0 |
| DownloadsTestsDriver（新） | D3.1/D3.2/D3.5 全绿 |
| UiTestsDriver | 5+D3.7/0 |

## 放行门

- [ ] 本计划评审（arch-20/qa-20/visual-20/captain 4/4 或 captain 单裁+成员异步确认）
- [ ] 用户确认开工（会话关机指令后下一次开工点）
