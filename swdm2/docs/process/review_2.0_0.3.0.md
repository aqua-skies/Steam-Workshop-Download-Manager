# SWDM 2.0 · 0.3.0 阶段 3 交付门评审记录（D3.8）

> 三原则（用户 2026-09-28 规定）：①精简 ②以用户体感为中心 ③保证基本功能正常运行。
> 放行条件（迭代交付四要素）：全量回归（增量+clean 双口径，两连绿）+ 讨论组 4/4 一致 + 版本号体现 + 变更记录 + bug 测试员连续两轮复测无异常。

## 交付清单（阶段 3 = 8/8）

| 任务 | 交付 | commit | owner |
|---|---|---|---|
| t21 D3.1 状态机与队列（含 ResumeAsync 补完） | ✅ | 696773c + 1afa33f | arch-20 |
| t22 D3.2 事件总线与进度聚合 | ✅ | 09fb329 | arch-20 |
| t23 D3.3 steamcmd 部署器 | ✅ | db86584 | qa-20 |
| t24 D3.4 steamcmd runner | ✅ | 621f6b2 | qa-20 |
| t25 D3.5 SteamCmdProvider 接入链 | ✅ | fe40fdd | arch-20 |
| t26 D3.5b App 最小可测 UI | ✅ | 526f9df | visual-20 |
| t27 D3.6 串行化与句柄纪律 | ✅ | 56798c3 | qa-20 |
| t28 D3.7 UiTests P0 下载主旅程 | ✅ | c927d74 | visual-20 |
| t29 D3.8 交付门 | 本文档 | （关门 commit 见下） | arch-20 |

## 全量回归（两连绿·双口径）

| 口径 | build | Core | Steam | Downloads | Ui | 合计 |
|---|---|---|---|---|---|---|
| 轮 1（增量） | 0-0 warnaserror | 72/0 | 103/0 | 53/0 | 9/0 | **237/0** |
| 轮 2(clean) | 0-0 warnaserror | 72/0 | 103/0 | 53/0 | 9/0 | **237/0** |

- SP-3 沙箱驱动模式（xUnit testhost 崩溃替代路径）；驱动运行时 `TMP`+`TEMP` 双重重定向至 `swdm2/.dtmp`。
- 关联交互覆盖（非单点）：队列↔provider↔总线装配联调（t25 Queue_Driven_Download_Completes）；runner stdout 磁盘增长估算→EMA/ETA/节流链路（t25 Progress_Bridge）；UI 状态机驱动按钮启用态（t26/t28 契约对齐 D3.1 七态）。

## 三原则评审（功能 删减/改进/添加）

### ① 精简
- 阶段 3 未引入冗余抽象：IDownloadProvider/IDownloadEventBus 均为单实现接口+测试 stub 隔离（无过度设计）。
- App 手写 MVVM 零新依赖（CommunityToolkit.Mvvm 切换明确留 D5，不为骨架引入包）。
### ② 以用户体感为中心
- 下载状态 PCL2 式即时反馈：进度节流 100ms（尾帧不丢=不卡尾）；ETA/分段数诚实 N/A 降级（不展示假数据）。
- 失败/暂停/取消语义完整：杀进程干净+无半成品（1.x 学费内置）；恢复按钮已点亮（ResumeAsync)。
### ③ 保证基本功能正常运行
- 队列驱动下载全链单测绿（装配=一行）；暂停/取消/重试/恢复五语义均有测试。
- 已知保留：沙箱环境约束下 Online 真实 mod 下载+UI #14 桌面复跑为环境容忍门清单（ENV-DOWNGRADE 标注齐全），不视为功能缺陷（设计对照纪律：环境阻断≠不可行）。

## ⚠️C7 待重标定参数（不阻门，D4/D5 实测清单）
并发槽=2 · EMA alpha=0.4 · ProgressThrottleMs=100ms · 进度偏差阈值 ±15% · api/store bucket 100ms/250ms。

## 讨论组投票（4/4）

| 成员 | 票 | 依据 |
|---|---|---|
| arch-20 | 赞成 | 两连绿双口径 237/0；下载域全链（队列↔provider↔runner↔总线↔UI)契约对齐无缺口；C7 参数全标注保留 |
| qa-20 | 赞成（附注 2 条，不阻门） | steamcmd 域实证锚定（banner 版本串/退出码{0,7}/非 ASCII 门探针级）；Steam 103/0 我域两连绿；三原则对齐（runner 零过度抽象/诚实 N/A/契约链偏差<10%)。**附注①**：Online 真实下载绿从未在沙箱跑过=弯路嫌疑标注，建议关门前桌面 ASCII %TEMP% 复跑一次 SteamTestsDriver 补环境证据（非缺陷）。**附注②**：C7 参数移植 1.x 未在 2.0 实测，D4 上线后先问"能否更短"再标定。 |
| visual-20 | 赞成（附工程卫生建议 1 条，不阻门） | App/UI 域第一手核验：clean+warnaserror 0-0 自复跑；四驱动 237/0 双口径两连绿自复跑；三原则对齐（零新 NuGet+保留 id 全套 A7 载体/100ms 尾帧不丢+诚实 N/A+五语义/真链装配沙箱如实 Failed 不造假）。**保留**：#14 完成弹窗桌面复跑清单+C7 标注齐。**建议**：`swdm2/TestArtifacts/` 测试截图工件加 .gitignore（7 个 Q10 失败截图 untracked 污染工作树）→ 关门提交已照办。 |
| captain | 赞成 | 独立复现+评审批判：build 0-0 warnaserror 双口径复跑；四要素齐（回归 237/0 两连绿/三原则评审/版本 0.3.0/CHANGELOG);环境容忍门走设计对照纪律不阻门；C7 清单保留 D4/D5 实测=经验复验纪律正确用法 |

## 结论

- 版本：0.2.0 → **0.3.0**(`swdm2/Directory.Build.props`)+ CHANGELOG `[0.3.0]` 条目。
- **讨论组 4/4 一致通过（2026-10-03 02:00)**：arch-20 / qa-20 / visual-20 / captain 全赞成（不阻门附注 3 条已记录）。
- bug 测试员连续两轮复测：轮 1（增量）237/0 + 轮 2(clean)237/0，均无异常。
- **0.3.0 阶段 3 交付门关闭**。下游 D4 阶段计划见 `docs/architecture/architecture_2.0.md` §6 DAG(D4.x)。
