# SWDM 1.4.0 变更记录

> 打包任务：t24（installer-fixer，attempt f41422d2）· 2026-09-29
> 前置：t21 provider 抽象层（core-tester）+ t22 1.3.10 遗留项（search-fixer）+ t23 讨论组评审（installer-fixer 主持）+ t28 评审决议执行（core-tester）
> 评审文档：`docs/feature_review_1.4.0.md`（五方零反对，verdict=pass）

---

## 一、版本概要

1.4.0 是架构迭代版本：在 1.3.9 双通道（steamcmd + CDN）基础上引入**可扩展的下载 provider 抽象层**，新增**匿名第三方通道 GGNetwork 试点**，并收掉 1.3.9 t16 登记的全部 1.3.10 遗留项。默认通道仍为 steamcmd，默认路径行为与 1.3.9 逐字节一致——所有新通道都是链上增量，用户不主动切换感知不到变化。

**核心收益**：匿名用户从此有多通道回退能力（GGNetwork → CDN 失败 → steamcmd 兜底），且单通道故障时熔断器自动冷却跳过，不必每个任务白等一次超时。

---

## 二、provider 抽象层（t21，core-tester）

新增 `swdm/core/providers/` 六件套：

| 模块 | 职责 |
|---|---|
| `base.py` | ABC `DownloadProvider`（probe / download / cancel / resolve / should_fallback / is_configured 六方法）+ `ProviderMeta` + `ProviderKind` + `http_download`（Range 断点续传 / stop_event 取消 / 429 上报） |
| `registry.py` | `ProviderRegistry` 单例：`build_chain` 链构造 / `_Circuit` 熔断器（连续 3 次失败 → 60s 冷却 → half-open 探活）/ `list_channels`（配置态通道列表供 UI） |
| `cdn.py` | CDN 直链通道（平迁自 `cdn_downloader.py`，需登录态 resolve file_url） |
| `steamcmd.py` | steamcmd 通道，`terminal=True` 链尾兜底，`should_fallback()=False` |
| `ggnetwork.py` | 匿名第三方通道试点（见第三节） |

**链式回退语义**（`downloader.py` `_run_channel_chain`）：用户首选通道 → 其他启用通道按优先级 → steamcmd 链尾。跳过禁用 / 未配置 / 熔断冷却的通道；**一次链 = 一次尝试**（链内回退不消耗 auto_retry，只有整链失败才计入自动重试）；`should_fallback()` 结构化判定（替代 1.3.9 的消息含"回退"字符串判定）。

**侵入点集中**：
- `downloader.py`：链构造 + 状态机汇合（通道执行结果统一汇成 `DownloadResult`，后续重试/退避/入库与通道无关）
- `services.py:78`：`DownloadManager` 构造补 `api` 参数——**1.3.9 遗留缺陷**：CDN 通道因缺 api 无法完成 file_url 解析，几乎总是失败回退；本版修复
- `config.py`：`download.channel` + `download.providers.{name}.{enabled,...}` 三层嵌套合并
- `gui/settings_tab.py`：通道动态下拉（按注册表生成，tooltip 说明"所选通道不可用时自动沿链回退，SteamCMD 永远兜底"）

**兼容门面**：`cdn_downloader.py` 保留为兼容层（旧测试零改动，1.3.9 回归基线直接复用），顶部标注"1.4.1 移除，新代码请用 `swdm.core.providers.cdn`"。

**验证**：`tests/test_providers.py` 74 项 ALL PASS（t28 后扩至 84 项）。

---

## 三、GGNetwork 匿名通道试点（t21 + t28）

**调研结论**（`research/provider_research.md`）：GGNetwork（`api.ggntw.com`）是唯一匿名可用的第三方工坊代理——POST `steam.request` 传工坊物品 URL，返回官方 CDN 直链，无需 key。同批调研排除 steamwebapi.com（经济类 API 无工坊端点）、Nether（闭源账号爬虫合规风险）、steamworkshop.download（HTTP-only、无 API、半废弃、低增量价值——返回同一官方 CDN URL，本程序 CDN 通道自己就能 resolve）。

**实现**（`ggnetwork.py`）：
- **令牌桶限流**：20 req/min + 突发 3（自律值，低于社区对 Valve 自家接口的 ~30 req/min 参考——GGNetwork 是第三方代理，受 ToS §5.2.2「excessive server load」约束，被封影响整个用户群）。**关键：令牌桶只限 resolve 的 POST（每物品 1 次），不限 CDN 传输——下载速度不受影响**。`rate_limit_per_minute` 用户可调
- **resolve 后立即下载**：URL 当帧即调 `http_download`，不缓存（调研结论：链接会过期，不能长期缓存）
- **queue 排队守卫**（t28 补齐）：响应 `queue.position>0` 时返回空串干净回退 steamcmd，不轮询（轮询占工作线程 + 令牌桶配额）
- **zip 解压**：转存压缩包解压到 `content/<appid>/<itemid>`
- **GMAD 弱校验**：魔数校验格式正确性；尺寸差异 >1% 判坏包（t28 升级）：`_verify_content` 比的是**解压后 .gma 实际字节数** vs Steam 声明的原始 .gma 字节数（zip 转存不进入比较），>1% → FAILED 链内回退（不消耗 auto_retry），消息「内容大小与 Steam 声明不符（可能下载不完整），已回退 SteamCMD 重下」，并清坏包残留
- **429 处理**：经 `on_throttle_signal` 上报退避

**诚实披露**：GGNetwork **从未做过实网端到端验证**（本机代理 DNS/超时不稳，仅验证离线 mock 路径）。默认通道=steamcmd 使其不影响默认路径，用户不主动选择不到该通道。t23 讨论组裁决：t24 打包前优先尝试实网冒烟；做不到则标"实验性"后缀（t25 复测时 gui-tester 会做真下载冒烟）。

---

## 四、1.3.10 遗留项（t22，search-fixer）7/7

全部是 1.3.9 t16 讨论组登记的延后项：

**A-P1 cancel 微秒窗口 · 正式修复**（`downloader.py`）——1.3.9 只做了"取消后不再登记 _done"廉价防御，本版做正式状态机修复：
- 新增 `_cancelling` 集合；`cancel()` 在同一把锁内先 `add(_cancelling)` 再 `_stop.set()`——保证 worker 观察到 `_stop` 时 pending 标记已在位
- `_exec_job` 入链前早退：`_throttle_wait` 后若 `_stop` 已置位直接 `_retire_cancelled` 收尾
- 终态判定块与 `cancel()` 的 add+set+pop+登记全程同一把锁串行：cancel 先行→取消胜出（不导入库/不自动重试/终态不被覆盖回成功）；worker 先行→真实结果保留
- 自动重试的判定与重新入队并入同一锁块（cancel 无法插队复活已取消任务）；重试期间状态保持 RUNNING
- `retry()` 清除残留 pending 标记；新增 `_retire_cancelled()` 保证单次登记
- 验证：`tests/test_ap1_cancel_race.py` 16 项 3 场景确定性回归（cancel 抢注成功 / 入链前取消 / 标记清理后同 id 重试成功）

**B④ 调试 Tab 默认隐藏**：config 默认 False + `main_window` 条件 addTab（`debug_tab` 实例始终创建，保住测试耦合）+ 设置页开关"显示调试面板（重启后生效）"。默认 4 Tab，需排错时开关打开。

**C② 暂停/继续合并单按钮**：`_toggle_pause_all` 一个按钮切文案（⏸ 全部暂停 ⇄ ▶ 全部继续），`_sync_batch_buttons` 恒启用（无任务时不再灰按钮）；重试失败 / 清除已完成仍独立。

**D 搜索间隔 0.7s + 熔断退避**（`game_search.py`）：间隔 1.2s → 0.7s（落在 t16 投票的 0.6-0.8s 区间）；连续 3 次失败或 ConnectionError → 冷却 15s（成功清零）。体感关键在本地即时层：已输入词的联想即时出候选，0.7s 只影响首次网络新词。

**E③ bytes=0 校验**：steamcmd 成功但 0 字节 → 改判失败（防假成功入库）。

**stop/retry 竞态（7g/7h）**：cancel 不覆盖 SUCCESS/FAILED 终态。

**test_v136 固件修复**。

验证：`tests/test_t22_1310.py` 27 项 + `test_ap1_cancel_race.py` 16 项。

---

## 五、t23 讨论组评审决议

五方（installer-fixer 主持 + search-fixer / core-tester / gui-tester / recorder）逐条评审 A-E 议题，零反对通过交付。完整记录见 `docs/feature_review_1.4.0.md`（149 行）。

**收**：provider 抽象层（含熔断器接生产调用方）· GGNetwork 试点（令牌桶 20/min + queue 守卫 + >1% 回退触发）· services.py:78 修复 · 设置页通道动态列表 · A-P1 正式修复 · B④/C②/D/E③ 全部

**删**（3 处死代码）：`_download_via_cdn` 死方法（链改造后零调用方）· registry 60s 探测缓存 + `list_channels(probe_results)` 参数（`probe_results=True` 零生产调用方）· `ProviderKind.EXTERNAL` 占位（零引用，SWD 移出路线图）

**延后 1.4.1+**：cdn_downloader.py 门面移除（含 3 测试 import 迁移）· list_channels 显示"未配置"状态 · preferred=cdn 匿名跳过优化 · ⚠ 消息落库增强 · ggnetwork 探测动态化 · 搜索冷却结束自动重发待选词

**不做**：SWD 兜底（低增量价值）· steamwebapi / Nether（调研排除）

**评审中发现并修复的一处缺陷**：`_Circuit` 熔断器的 `record_failure/record_success` 原本**零生产调用方**——熔断器只读不写、永不 trip，是 inert 的（core-tester 诚实披露，installer-fixer 一手 grep 核实）。讨论组决议**接上而非删除**（ggnetwork 这类第三方代理正是熔断器目标场景；inert 熔断器比没有更糟），由 t28 落地。

---

## 六、t28 评审决议执行（core-tester，7 项打包前清理）

1. 删 `downloader.py` 死方法 `_download_via_cdn`（grep 零残留）
2. 删 registry 60s 探测缓存 + `list_channels` 的 `probe_results` 参数；`settings_tab.py:402` 调用同步改 `list_channels()`
3. 删 `ProviderKind.EXTERNAL` 占位；`docs/provider_architecture_1.4.0.md` 第 7 节重写（SWD 移出路线图）+ 新增第 8 节清理记录
4. ggnetwork >1% 尺寸差异 → FAILED 链内回退：`_verify_content` 返回 `(note, size_bad)`；消息写明回退原因 + `_safe_remove` 清坏包残留
5. queue.position>0 守卫（resolve 内 position>0 返空串干净回退，不轮询）
6. `cdn_downloader.py` 顶部标注"1.4.1 移除，新代码用 `swdm.core.providers.cdn`"
7. **熔断器接生产调用方**：`_run_channel_chain` 内 SUCCESS → `record_success(name)`、FAILED → `record_failure(name)`；**CANCELLED 与 terminal 通道豁免**（terminal 豁免是关键边界——steamcmd 若被熔断会让链变空）

验证：`test_providers.py` **84 项 ALL PASS**（+10 新项：queue 守卫 2 / 坏包回退 4 / 熔断 4 场景）；五套核心回归全 PASS。

---

## 七、版本号与打包

- `swdm/core/paths.py:9` `APP_VERSION` 1.3.9 → 1.4.0
- `installer/swdm.iss:14` `SWDMVersion` 1.3.9 → 1.4.0
- PyInstaller `swdm.spec --noconfirm` exit 0（"Build complete!"）→ ISCC（`C:\Users\Lenovo\AppData\Local\Programs\Inno Setup 6\ISCC.exe`，不在 PATH，49.4s）exit 0 → **`installer\Output\SWDM-Setup-1.4.0.exe` 42.69 MB**
- 冒烟：`build\dist\SWDM\SWDM.exe` 稳定运行 8 秒未退出，窗口标题「Steam 工坊下载管理器 v1.4.0」——版本号已正确贯穿到 GUI 标题栏
- 打包前置验证：providers/ 全静态 import（无 `import_module` 动态导入），swdm.spec 无需改动即可收集新子包

---

## 八、回归统计

`run_all.ps1` 串行（QT_QPA_PLATFORM=offscreen + PYTHONUTF8=1，输出重定向 `tests/_run_all_1.4.0.log` 读 RESULT 行）：

**59 脚本 57 PASS / 2 FAIL / 0 NORESULT，零新增失败。**

2 FAIL 逐项核对（均为 1.3.8 起既有非回归，与基线逐项一致，非本版引入）：
- `test_legacy_format`：真实 mod 字节数漂移（mock 硬编码值与实际不符）
- `test_page_parser`：旧标签结构夹具（已被 Wayback 实证推翻）

对比 t28 时点（54 PASS / 5 FAIL）：本轮网络环境好转，`test_bulk_games` + `test_bundle_ctx` + `test_bundle_methods` 三项纯环境失败转 PASS——印证回归口径：实网测试在 FAIL/PASS 间漂移是环境问题，不是代码回归。`test_providers.py` 84 项（t28 扩展后）随 run_all 全 PASS。

**回归口径**（t23 讨论组确认，同 1.3.9）：以"**零新增失败 + 既有非回归逐项核对**"为准，不追绝对 PASS 数（实网测试在本机 FAIL/NORESULT 间漂移是环境问题）。既有非回归两项：`test_legacy_format`（mock 字节数漂移）、`test_page_parser`（旧标签夹具）。

---

## 九、t23 评审占位（t27 交付评审回填）

t27（讨论组交付评审，search-fixer 主持）将对本 changelog 逐条过审并回填本节：U 级 bug 逐条过审表 / t23 决议执行情况表 / 六方投票表 / 闸门结论。

---

## 十、后续待修清单（1.4.1+）

- cdn_downloader.py 门面移除（含 3 测试 import 迁移）
- `list_channels` 下拉显示"未配置"状态（当前只反映启用态，用户不知道自己少了一个可选项）
- preferred=cdn 匿名用户 resolve 前查登录态直接跳过（省掉每次先尝试失败再回退的等待）
- ⚠ / 回退消息落库（mod 库元数据标记"曾触发体积告警"，事后可见）
- ggnetwork 探测动态化（当前固定物品 id 2537024972）
- 搜索冷却结束自动重发一次待选词（gui-tester 非阻塞建议）
- GGNetwork 实网长时验证（本版仅离线 mock + 可能的打包前冒烟）
