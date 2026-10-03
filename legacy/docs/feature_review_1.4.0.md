# SWDM 1.4.0 功能评审讨论组

> 评审时间：2026-09-29 · 主持：installer-fixer
> 五方逐一表态：search-fixer / core-tester / gui-tester / recorder（+ captain 列席）
> 评审对象：t21 provider 抽象层 + GGNetwork 试点 + t22 1.3.10 遗留项 7/7
> 三原则：**精简 / 以用户体感为中心 / 保证基本功能正常运行**

**评审材料**：`docs/provider_architecture_1.4.0.md`（core-tester 架构说明）· `research/provider_adaptation.md`（适配设计）· `research/provider_research.md`（实测调研）· t21/t22 任务 output · 回归基线 59 脚本（52 PASS / 7 FAIL = 5 实网代理不稳 + 2 既有非回归 / 0 NORESULT，零新增失败；test_providers 74 项 ALL PASS）

---

## 一、议题 A：provider 抽象层是否过度设计

### 结论表

| 子项 | 结论 | 票数 | 依据 |
|---|---|---|---|
| ABC + ProviderRegistry + `_Circuit` 熔断 | **收（须打包前接上生产调用）** | 3/3 | 真实复用（http_download 续传/取消、_session 复用、is_configured 默认实现，三个 provider 都继承）；链构造是回退逻辑本身；熔断器是 1.3.7 O5 `_Throttle` 思路延伸。**重要更正（core-tester 诚实披露 + 主持人一手核实）**：`ProviderRegistry.record_failure/record_success`（registry.py:136/141）**当前无生产调用方**——downloader.py 链循环从不调用（downloader.py:137/702/714 的 record_failure 属 `_backoff`，与 provider registry 无关），熔断器只读不写、永不 trip，是 inert 的。A1 辩护中"避免坏通道每任务白等超时"的收益未兑现。**必须打包前接上（清理第 7 项）或按精简原则删除——讨论组决议：接上**（ggnetwork 这类第三方代理正是熔断器目标场景；inert 熔断器比没有更糟：维护负担 + 假装有能力） |
| 60s 探测缓存 + `probe_results` 参数 | **删** | 1/3 主张删（主持人核实支持） | 核实事实：build_chain 不探测；UI 唯一调用 `settings_tab.py:402 list_channels(probe_results=False)`；`probe_results=True` 路径**零生产调用方**是死路径（约 40 行）。删除产品行为零变化 |
| `_download_via_cdn` 死方法 | **删** | 1/3 主张删（主持人核实支持） | 核实事实：downloader.py:442 定义，链改造后 swdm 内零调用方 |
| `cdn_downloader.py` 兼容门面 | **延后 1.4.1 移除** | 主持人折中裁决 | 当前只被死方法 + 3 个测试文件引用；门面让 test_cdn / test_core_sweep 零改动、1.3.9 基线直接复用（迁移期标准做法，search-fixer + recorder 判"加分"）；打包前动 3 个测试 import 链收益不抵风险；顶部加"1.4.1 移除，新代码请用 swdm.core.providers.cdn"注释防新代码引用 |
| `ProviderKind.EXTERNAL` 占位 | **删** | 2/1 | base.py:29 定义，全仓库零引用确认死代码；YAGNI——真做 SWD 时加回成本为零；recorder 主张"留"为 2:1 少数 |
| SWD（steamworkshop.download）兜底 | **延后（不做 1.4.0）** | 2/3 | 调研结论低增量价值（返回同一官方 CDN URL，本程序 CDN 通道自己能 resolve）；HTTP-only、无 API、半废弃、社区口碑差；匿名场景已被 ggnetwork 覆盖 |

**主持人核实**：EXTERNAL 零引用、`_download_via_cdn` 零调用方、`probe_results=True` 零生产调用方、`ProviderRegistry.record_failure/record_success` 零生产调用方（熔断器 inert）——四处死代码/未接线主张全部一手核实属实，core-tester 证据链可靠。

### A 方逐条表态

**search-fixer**：A 收（未过度设计）——"ABC + registry + _Circuit + 60s 探测缓存逐条对上设计文档要求，registry 249 行、provider 各件都很薄，没有为想象中的需求加层；令牌桶/熔断/探测缓存都是匿名第三方接口的必需件"。门面**加分**（旧测试零改动，降低交付风险）。EXTERNAL **删**（零引用死代码）。

**core-tester**（t21 作者）：A1 收 ABC + Registry + _Circuit（真实复用，非包装层）；probe 缓存**删**（已核实死路径）。A2 删 `_download_via_cdn` 死方法；门面 1.4.0 内清掉（后接受主持人延后 1.4.1 折中）。A3 删 EXTERNAL；SWD 移出路线图。**评审中诚实更正**：A1 辩护称"熔断器避免坏通道每任务白等超时"，但核实 `ProviderRegistry.record_failure/record_success` 零生产调用方，熔断器 inert、永不 trip——收益未兑现。据此认领第 7 项（接生产调用方，约 6 行），并指出若不做则 _Circuit 应按精简原则删除（"inert 熔断器比没有更糟：维护负担 + 假装有能力"）。讨论组采纳"接上"路线。

**recorder**：A 全收——"最小必要集：链构造需要 registry，熔断是 1.3.7 O5 _Throttle 熔断器的既有思路延伸，探测缓存避免每次构造链打网络；没有为未来 provider 预埋的复杂机制"。门面**加分**（迁移期标准做法，负债仅双份入口）。EXTERNAL **留**（明确钩子、零启用成本）——2:1 少数。

---

## 二、议题 B：GGNetwork 试点是否达预期

### 结论表

| 子项 | 结论 | 票数 | 依据 |
|---|---|---|---|
| 令牌桶 20/min + 突发 3 | **收（保持默认）** | 3/3 | 关键澄清（core-tester）：**令牌桶只限 resolve 的 POST（每物品 1 次），不限 CDN 传输——下载速度不受影响**。GGNetwork 是第三方代理（服务端用自有 Steam 账号代下），受 ToS §5.2.2「excessive server load」明文约束，被封是封整个 SWDM 用户群；~30 req/min 那条是 Rust steam-user 对 Valve 自家接口的值，对代理取低于 Valve 的自律值正确；且 `rate_limit_per_minute` 用户可改 |
| resolve 后立即下载（不缓存 URL） | **收（已正确实现）** | 2/2 | ggnetwork.py:143-156 resolve() 返回 url 后当帧即调 http_download——与调研结论（"链接 will expire soon，拿到立即下载"）一致 |
| queue.position 排队守卫 | **收（缺口，≤5 行小修）** | 主持人核实 + core-tester 认领 | 核实事实：resolve() 完全没读 queue 字段（ggnetwork.py:118-124 只取 url）。设计文档规定排队时轮询或回退；当前安全边界是 url 为空→回退，但服务端排队中若返回 url 会下到不完整内容。落点：url 提取前判 `queue.position>0` 返 ""（干净回退，不轮询——轮询占工作线程 + 令牌桶配额） |
| zip 解压 + GMAD 弱校验 | **收（阈值合理）** | 3/3 | GMAD 魔数兜住格式正确性；>1% 差异**升级为回退触发**（见下） |
| >1% 尺寸差异：⚠ 只提示 vs 回退触发 | **升级为回退触发** | 主持人裁决（技术澄清后） | core-tester 主张改：`should_fallback` 只看 FAILED，⚠ 在 SUCCESS 消息里不触发回退 → 坏包误报成功入库。search-fixer 顾虑"声明 size 是未压缩 .gma 字节数，zip 转存必然有差异"——**技术澄清**：`_verify_content` 比的是**解压后 .gma 的实际字节数** vs `item.file_size`（Steam 声明的原始 .gma 字节数），zip 转存不影响比较，>1% 差异确实是坏包信号，误伤面很小。误报时回退 steamcmd 拿到新版本结果仍正确。回退走链内语义、不消耗 auto_retry。recorder 补充建议：⚠/回退消息同时落库（事后可见）——回退后 FAILED 消息自然带差异信息入库，统一满足 |
| 匿名降级路径完整性 | **收（到位）** | 3/3 | build_chain 对未配置 key 通道 log.info 后跳过、不报错；cdn `requires_key=False` → is_configured 恒 True，匿名时 resolve 拿不到 file_url → FAILED + `_FALLBACK_HINT`（提示登录）。一处体感小瑕疵（延后）：preferred=cdn 的匿名用户每次下载先尝试失败再回退，可在 resolve 前查登录态直接跳过 |

### B 方逐条表态

**search-fixer**：B1 收（20/min 对第三方代理正确取向，用户可调）；B2 已正确实现（resolve 后当帧下载，不缓存 URL）；B2b queue 守卫**缺口需小修**（触及"保证基本功能正常运行"，不该延后）；B3 收（>1% 只⚠不回退是对的——声明 size 是未压缩 .gma 字节数，硬失败误伤；GMAD 魔数已够；建议⚠消息补"可能是转存压缩包"解释）。

**core-tester**：B1 收（关键澄清：令牌桶只限 resolve POST 不限 CDN 传输，批量 10 项约 30s 解析等待可接受）；B2 部分收——GMAD + zip 解压够用，但 >1% 差异只⚠不回退是风险点，主张升级为回退触发（误报场景下回退 steamcmd 拿新版本结果仍正确）；B3 收（路径完整，preferred=cdn 匿名等待优化延后）。

**recorder**：B 收（20/min 正确：ToS §5.2.2 + 本机出口曾被限 + 社区安全值 ~30 req/min，下载是长连接突发 3 够用）；zip+GMAD 够稳健，⚠ 不落库是体感缺口（建议落库标记"曾触发体积告警"）。

**gui-tester**（27 项离线实测 ALL PASS，tests/_t23_review.py：B1×6 / B2×5 / B3×6 / B4×6 / C×4）：B1 收——下载页单按钮「⏸ 全部暂停」⇄「▶ 全部继续」纯文案切换，mgr.paused 正确复位，重试失败/清除已完成仍独立，4 操作语义不重叠无歧义。B2 收——默认无调试 Tab，debug_tab 实例始终创建（win.debug_tab 可用），设置开关「显示调试面板（重启后生效）」默认关、勾选后 config 正确写入；**t18 复测未使用调试 Tab（走日志与源码路径），隐藏对排错无影响**；开关在杂项区好找，"重启后生效"文案诚实。B3 收——**体感关键在本地即时层**：输入"gar"本地联想即时出候选完全不等待 0.7s，0.7s 只影响首次网络新词；对比 1.3.9 的 1.2s 首现快 0.5s 方向正确；冷却 15s 期间下拉退回纯本地候选可接受（小建议非阻塞：冷却结束自动重发一次待选词）。B4 收——下拉按注册表动态生成可读显示名、默认选中有效通道、切换写入 config；**tooltip 是关键加分项**（"所选通道不可用时自动沿链回退，SteamCMD 永远兜底"）——这正是普通用户理解"通道"所需的最小解释；默认即 steamcmd 开箱即用。

---

## 三、议题 C：steamcmd 链尾兜底与 1.3.9 一致性

### 结论：收，逐字节一致（3/3）

证据链（core-tester，recorder 确认逻辑自洽）：默认 channel=steamcmd → 链=[steamcmd]（terminal 不追加 cdn/ggnetwork）；`_run_provider` 对 steamcmd 走原 `_run_steamcmd`（`_engine_lock` 串行路径未动一行）；test_engine_concurrency + test_throttle + test_139_merge 全 PASS。`services.py:78` 的 api 修复只在链含 cdn 时生效，默认通道下零可观测差异。

匿名用户 UI 无退化（search-fixer）：`list_channels(probe_results=False)` 只反映配置态、不因网络抖动抖动选项；tooltip 明确告知"匿名会话下 CDN 直链不可用" + "SteamCMD 永远兜底"。一处 UI 延后建议（recorder）：下拉显示"未配置"状态而非隐藏，否则用户不知道自己少了一个可选项（1.4.1）。

---

## 四、议题 D：t22 遗留项收口质量

### 结论：四项全部收干净（2/2 当事人 + 交叉验证）

| 项 | 结论 | 证据 |
|---|---|---|
| A-P1 cancel 微秒窗口 | **收干净**（正式状态机修复） | cancel() 的 `add(_cancelling)+set+pop+登记` 与 worker 终态判定块全程同一把 `_lock` 串行；入链前早退；自动重试判定+入队同锁原子。两个临界区严格串行 → 目标窗口（终态被覆盖 / _done 重复登记）已关闭。`test_ap1_cancel_race.py` 16 项三个确定性场景（cancel 抢注成功 / 入链前取消 / 标记清理后同 id 重试成功）+ test_throttle 7a/7g/7h 保持 PASS。残留窗口只剩 engine.cancel() 与引擎进程写自己的竞争（引擎层契约，超出 A-P1 范围） |
| B④ 调试 Tab 默认隐藏 | **收干净** | config 默认 False + main_window 条件 addTab（debug_tab 实例始终创建，win.debug_tab 测试耦合保住）+ 设置开关。test_gui_sweep 118 项 / test_gui_offline 同步改默认 4 Tab 后全 PASS |
| C② 暂停/继续合并 | **收干净** | `_toggle_pause_all` 单按钮，`_sync_batch_buttons` 切文案且恒启用（无任务时不再灰按钮） |
| D 搜索间隔 0.7s + 熔断退避 | **收干净** | 0.7s（落在 t16 投票的 0.6-0.8s 区间）+ 连续 3 次失败或 ConnectionError 冷却 15s（成功清零），复用 O5 _Throttle 思路 |

**高质量信号**（recorder）：t21/t22 在同一份 `_exec_job` 上交叉验证——core-tester 移除链循环顶部冗余 stop 判定 + steamcmd stop_event 拦截（因 A-P1 早退已覆盖取消场景），两人对同代码达成一致才动刀。

---

## 五、议题 E：1.4.0 是否可交付

### 结论：收（可交付），附 7 项打包前必做清理 + 闸门安排（3/3）

**无"该加未加影响基本功能"的项**（3/3 一致）：默认通道仍是 steamcmd，匿名/CDN/GGNetwork 全部是链上增量，默认路径行为与 1.3.9 等价（回归零新增失败佐证）。无体感退步。**一处例外**：`_Circuit` 熔断器 inert（见议题 A 更正）——不致命（熔断器不工作 = 退化为无熔断，链仍正确），但属"承诺了没有的能力"，打包前必须接上或删除，讨论组决议接上。

**范围可控无蔓延**（recorder）：1.4.0 = t21 新增 providers/ 包（侵入点集中：downloader.py 链构造 / services.py:78 / config+settings）+ t22 六项（全部是 1.3.9 t16 登记的延后项，零新增范围）。边界清晰（架构文档第 7 节自陈待办）。

### 打包前必做清理（core-tester 全部认领，每项 ≤ 20 行，完成后重跑 test_providers + 五套核心回归 + run_all）

| # | 项 | 落点 | 认领 |
|---|---|---|---|
| 1 | 删 `_download_via_cdn` 死方法 | downloader.py:442 | core-tester |
| 2 | 删 probe 缓存 / probe() + `list_channels` 的 `probe_results` 参数 + 同步改 test_providers | registry.py / settings_tab.py:402 | core-tester |
| 3 | 删 `ProviderKind.EXTERNAL` 占位；架构文档第 7 节同步（SWD 移出路线图） | base.py:29 / docs | core-tester |
| 4 | ggnetwork >1% 尺寸差异 → FAILED 走链内回退（不消耗 auto_retry）；消息写明回退原因「内容大小与 Steam 声明不符（可能下载不完整），已回退 SteamCMD 重下」 | ggnetwork.py `_verify_content` | core-tester |
| 5 | ggnetwork queue.position>0 守卫（干净回退，不轮询） | ggnetwork.py resolve() | core-tester |
| 6 | cdn_downloader.py 顶部加"1.4.1 移除"注释 | cdn_downloader.py | core-tester |
| 7 | **给熔断器接生产调用方**（core-tester 诚实披露后新增）：`_run_channel_chain` 循环里 SUCCESS → `record_success(name)`、FAILED/CANCELLED → `record_failure(name)`，约 6 行。让尺寸差异 FAILED 自动计入 ggnetwork 熔断（反复坏包 → 60s 冷却跳过该通道）。行为校验点：匿名 preferred=cdn 时前 3 个任务 resolve 失败 → 熔断 60s → 后续任务直接走 steamcmd；`list_channels(probe_results=False)` 不查熔断，UI 下拉无可见困惑 | downloader.py `_run_channel_chain` + test_providers 补"链失败计入熔断"用例 | core-tester |

### 实网冒烟裁决（主持人）

**GGNetwork 从未做过实网端到端验证**（core-tester + search-fixer 双方诚实披露；本机代理 DNS/超时不稳，只验证了离线 mock 路径；5 个实网 FAIL 全是环境问题）。匿名通道是 1.4.0 核心卖点，架构文档自陈"匿名接口需实测确认 20/min 自律值"。

裁决：**t24 打包前优先尝试实网冒烟（resolve 一个小 mod 真下下来）；本机代理不稳做不到则 ggnetwork display_name 加"实验性"后缀 + settings tooltip 强化提示；默认仍 enabled（默认通道 steamcmd，用户不主动选不到该通道）**。两条路都安全且不过度。core-tester 同意。changelog 须标注"匿名通道经离线 mock 验证，实网未经长时验证"（若适用）。

### 交付闸门安排（recorder 提出，实际流水线已对齐）

用户规则要求 **bug 测试员连续两轮复测均无异常**。任务流水线已对齐 1.3.9 的 t18/t19 双轮结构（recorder 初查时只过滤了 t21–t25 误报缺失，经主持人查任务板双源确认）：

**t23 讨论组（本任务）→ t24 打包（installer-fixer，依赖 t23）→ t25 复测第一轮（GUI/用户视角，gui-tester，依赖 t24）+ t26 复测第二轮（核心视角，core-tester，依赖 t24）→ t27 交付评审（search-fixer，依赖 t23/t24/t25/t26）。**

交付闸门 = t23 讨论组一致 + t25/t26 双轮无异常 + t27 交付评审通过。**t26 无需补建，已在流水线上。**

### 回归口径提醒（recorder）

两次 run_all 分布不同（52 PASS / 7 FAIL vs 46 PASS / 4 FAIL / 9 NORESULT），反映实网测试在本机环境不稳定（超时在 FAIL/NORESULT 间漂移）。**t24 以"零新增失败 + 既有非回归逐项核对"为准**（1.3.9 口径），不追绝对 PASS 数。既有非回归两项：test_legacy_format（mock 字节数漂移）、test_page_parser（旧标签夹具）。

---

## 六、五方表态汇总

| 成员 | A 抽象层 | B GGNetwork | C 一致性 | D t22 | E 可交付 |
|---|---|---|---|---|---|
| search-fixer | 收；门面加分；EXTERNAL 删 | B1 收 / B2 已实现 / B2b 小修 / B3 收 | 收 | 四项全收干净 | 收（附 B2b 小修 + 实网冒烟或默认禁用） |
| core-tester | 收；probe 缓存删 / 死方法删 / EXTERNAL 删；门面延后；**更正：熔断器 inert（record_failure/success 零生产调用方），认领第 7 项接上** | B1 收（只限 resolve 不限传输）/ B2 回退触发 / B3 收 | 收（逐字节一致） | 收（两临界区严格串行） | 收（认领 7 项清理 + 诚实披露零实网） |
| gui-tester | 收（27 项离线实测 ALL PASS）；门面加分；EXTERNAL 删；**熔断器 inert 独立实测确认**（C④ build_chain 跳过熔断通道但永不 trip，支持二选一） | B1 收（无歧义）/ B2 收（排错路径不断）/ B3 收（本地即时层兜底）/ B4 收（tooltip 关键加分） | 收（实测一致） | 收（同 core-tester 16 项判定） | 收（t25 收尾要求：GGNetwork 真下载冒烟 + 通道切换端到端用例） |
| recorder | 全收；门面加分；EXTERNAL 留（少数） | 收（⚠ 落库建议） | 收（逻辑自洽） | 收（交叉验证信号好） | 收（t26 双轮确认已在流水线 + 回归口径） |
| installer-fixer（主持） | 收；probe/死方法/EXTERNAL 删 + 熔断器 inert 已核实（四处死代码主张全部一手确认）；门面延后 1.4.1 | 收；B2b 小修 + >1% 回退触发（技术澄清后裁决） | 收 | 收 | 收（7 项清理 + 实网冒烟裁决 + t26 闸门） |

---

## 七、本版收 / 延后 / 删决议总表

**收（本版落地/保留）**：provider 抽象层（ABC + Registry + _Circuit 熔断 **+ 打包前接生产调用方**）· GGNetwork 试点（令牌桶 20/min + 突发 3 + zip 解压 + GMAD 校验 + queue 守卫 + >1% 回退触发）· services.py:78 修复 · 设置页通道动态列表 · A-P1 cancel 窗口正式修复 · B④ 调试 Tab 隐藏 · C② 暂停/继续合并 · D 搜索间隔 0.7s + 熔断退避 · bytes=0 校验 · steamcmd 链尾兜底

**延后 1.4.1+**：cdn_downloader.py 门面移除（含 3 测试 import 迁移）· list_channels 显示"未配置"状态 · preferred=cdn 匿名跳过优化 · ⚠ 消息落库增强 · ggnetwork 探测动态化（当前固定物品 id 2537024972）

**删（本版清理）**：`_download_via_cdn` 死方法 · probe 60s 探测缓存 + `probe_results` 参数 · `ProviderKind.EXTERNAL` 占位

**不做**：SWD（steamworkshop.download）兜底（低增量价值，移出路线图）· steamwebapi / Nether（调研已排除）

---

*结论同步 captain 与 t24 打包（installer-fixer）。t24 执行：7 项清理落定后改版本号 1.3.9→1.4.0（paths.py:9 + swdm.iss:14）+ changelog + PyInstaller/ISCC 打包 + 冒烟，随后 t25/t26 双轮复测。*
