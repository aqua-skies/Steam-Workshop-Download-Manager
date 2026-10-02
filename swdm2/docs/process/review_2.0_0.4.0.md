# SWDM 2.0 · 0.4.0 阶段 4 交付门评审记录（D4.10）

> 三原则（用户 2026-09-28 规定）：①精简 ②以用户体感为中心 ③保证基本功能正常运行。
> 放行条件（迭代交付四要素）：全量回归（增量+clean 双口径，两连绿）+ 讨论组 4/4 一致 + 版本号体现 + 变更记录 + bug 测试员连续两轮复测无异常。

## 交付清单（阶段 4 = 9/9 + 门）

| 任务 | 交付 | commit | owner |
|---|---|---|---|
| t30 D4.1 SteamKit2 会话（匿名/账号+2FA 回调） | ✅ | b82784d | arch-20 |
| t31 D4.2 manifest 解析与 isUgc 路径 | ✅ | 5eb89ca | arch-20 |
| t32 D4.3 chunk 并行下载+SHA/Adler 校验 | ✅ | 8f959a5 | arch-20 |
| t33 D4.4 SteamKitCdnProvider+链回退 | ✅ | 7359d15 | arch-20 |
| t34 D4.5 HTTP 直链分段 provider（续传） | ✅ | fe0ed9b | arch-20 |
| t35 D4.6 磁盘 IO 偏移直写+稀疏占位 | ✅ | 7d2331d | arch-20 |
| t36 D4.7 限速器（令牌桶双点） | ✅ | 219139c | arch-20 |
| t37 D4.8 ⚠️重标定 B3（并发上限） | ✅ | 7f1c5cc | arch-20 |
| t38 D4.9 UiTests 分段体感断言 | ✅ | 92c0e57 | qa-20 |
| t39 D4.10 交付门 | 本文档 | （关门 commit 见下） | visual-20 |

## 全量回归（两连绿·双口径）

| 口径 | build | Core | Steam | Downloads | Ui | 合计 |
|---|---|---|---|---|---|---|
| 轮 1（增量） | 0-0 warnaserror | 72/0 | 148/0 | 81/0 | 17/0 | **318/0** |
| 轮 2(clean) | 0-0 warnaserror | 72/0 | 148/0 | 81/0 | 17/0 | **318/0** |

- SP-3 沙箱驱动模式（xUnit testhost 崩溃替代路径）；驱动运行时 `TMP`+`TEMP` 双重重定向至 `swdm2/.dtmp`；便携标记 `swdm2.portable`（C3 门通路）。
- 关联交互覆盖（非单点）：队列→scheduler→路由器→SteamKit CDN(沙箱 Network)→回退 steamcmd(ASCII 门）→Failed 诚实态端到端（t33）；Kestrel 本地 fixture 验收（禁公网）：分段绿/kill 续传/Range 回退/偏移直写乱序/exFAT 降级；B3 五 sweep 实测（A/B/C 本地 Kestrel + E 真 API）。

## 三原则评审（功能 删减/改进/添加）

### ① 精简
- 路由表按错误类型精准：回退 8 类（Network/Timeout/Blocked/AuthRequired/CircuitOpen/InvalidChecksum/CorruptAsset/RateLimited）/不回退 4 类（回退也会失败=不浪费计算）。
- 偏移直写消除拼接缓冲；重叠字节 32→**16B**（D4.8 标定取最小省带宽，三档校验全绿）。
- B3 五参数全部锁/最小化（rep 方差 4.5x≫候选差→无增益保持=风险厌恶；元数据并发 1 锁，增益 7.0%<10% 阈值）=经验复验纪律具体实践。

### ② 以用户体感为中心
- IDM 式分段体感：in-half 均衡分裂+完成段中点分裂指派空闲 worker；kill 后续传（已完成段不重下，省用户带宽）；ETag/LastModified + 总长校验防源变化。
- 限速器 0=不限速默认（不牺牲默认体验）；热改即时生效；令牌桶实测带宽≤配置×1.1（HTTP 40.1KB/s@80KB/s、chunk 61.1KB/s@60KB/s，保守侧安全方向）。
- 2FA 收码弹窗（A11 模态 Dispatcher）+收码重试上限 2（防刷码）；provider 切换总线消息（UI 提示契约，D5 消费）。

### ③ 保证基本功能正常运行
- 下载核心域全链：CDN manifest→chunk 并行+Adler/SHA 双校验+损坏重下→偏移直写装配 318/0。
- **标定暴露三真 bug 已修+回归绿**：①in-half 分裂选 in-flight 段→重叠区交错写损坏 ②HTTP 段写偏移错位（重叠前缀污染）③请求超时仅 header 阶段（读流无超时=判别失真）。
- 已知保留（环境容忍门，不视为功能缺陷）：真 CDN 复测留 D5（localhost 内存级判别力受限，诚实局限已声明）；Online 匿名 CM 沙箱阻断；D4.9 #14/#15 桌面复跑（ENV-DOWNGRADE 标注齐全）——设计对照纪律：环境阻断≠不可行。

## ⚠️ 保留参数（不阻门，D5 实测清单）
MaxChunkParallelism=8 锁 · MaxConnectionsPerServer=8 锁 · OverlapBytes=16 · ChunkTimeoutMs=5000 锁 · 元数据并发=1 锁 · 并发槽=2 · 令牌桶突发=0.1s 量 · EMA alpha=0.4 · ProgressThrottleMs=100ms。标定三件套：`docs/calibration_2.{md,csv,json}`（109 行实测）。

## 讨论组投票（4/4）

| 成员 | 票 | 依据 |
|---|---|---|
| arch-20 | 赞成 | 下载核心域 owner 正式票：全链 318/0 两连绿双口径+C7 锁定有 B3 实测依据（E 真 API 24/24)+三真 bug 已修复并回归绿=下载核心域可交付；诚实局限均标注（localhost A/B/C 判别力限→D5+ 复测、E 香港单出口→跨环境复跑）不构成阻断。三原则逐条：精简=D4.1-D4.9 全为下载内核深化无功能膨胀；体感=B3 实测锁定+链回退 UI 提示+kill 续传拼接校验=1.x 痛点真补；基本功能=两连绿含三真 bug 修复后的绿 |
| qa-20 | 赞成（附注 2 条，不阻门） | steamcmd/UiTests 域：两连绿双口径 318/0 成立（我域 Steam 148/0+Ui 17/0 含 D4.9 两测试 92c0e57）；三原则对齐（D4.9 纯断言零新依赖/#15 四字段真实刷新+按钮态四契约 CanPause/CanResume/CanCancel/CanRetry/契约链+路由回退+分段续传全绿）；版本要素齐。**附注①**：Online 真绿（真实 sub17906/app4000)+UiTests Layer 2 沙箱从未跑=环境容忍门，建议关门后 captain 桌面通道复跑一次 SteamTestsDriver+UiTestsDriver 补齐（非缺陷）。**附注②**：runner 域 stall 60s/min 200KB/s/wait 120s 仍带 ⚠️待重标定（分段并发类 D4.8 已标定 B3b;runner 超时类属 D5 实测域），诚实标注+收紧路径清晰 |
| visual-20 | 赞成 | 见下"visual-20 门执行人票" |
| captain | 赞成（第 4 票） | 独立复现+评审批判：版本 0.4.0 落盘实读 Directory.Build.props;clean+warnaserror build 0-0 实跑；四要素齐（全量回归 318/0 两连绿双口径/三原则评审/版本号 0.3.0→0.4.0/CHANGELOG);C7→B3 参数锁定有实测依据（E 真 API 24/24)+三真 bug 修复回归绿；诚实局限=环境容忍门标注不阻门 |

### visual-20 门执行人票（赞成）
两连绿双口径 318/0 本人复跑（增量+clean 均 warnaserror 0-0）；阶段 4 下载核心域按 IDM 对标落地（in-half 分段+偏移直写+令牌桶双点限速+链回退路由），三原则逐条核对（见上）；三真 bug 由标定过程暴露并修复回归绿——非门后发现，已在阶段内闭环。保留项=环境容忍门清单（真 CDN 复测 D5+UI 桌面复跑），标注齐全不阻门。

## 结论

- 版本：0.3.0 → **0.4.0**(`swdm2/Directory.Build.props`)+ CHANGELOG `[0.4.0]` 条目。
- bug 测试员连续两轮复测：轮 1（增量）318/0 + 轮 2(clean)318/0，均无异常。
- **讨论组 4/4 一致通过（2026-10-03 06:38)**：arch-20 / qa-20 / visual-20 / captain 全赞成（不阻门附注 2 条已记录：qa-20 桌面复跑建议+runner 域 C7 待 D5 标定）。
- **0.4.0 阶段 4 交付门关闭**。下游 D5 阶段（视觉主体 0.5.0）按 DAG §6 开派。
