# SWDM 1.3.8 变更记录

发布日期：2026-09-28　版本号：1.3.7 → 1.3.8（`swdm/core/paths.py` APP_VERSION、`installer/swdm.iss` SWDMVersion 同步）

本轮主题：修复用户报告的两个 bug（搜索无关结果、卸载残留）+ 全量自测发现的 14 个小 bug 直接修复。全部改动均带回归测试。

---

## 一、用户报告 bug 修复

### S1. 搜索结果与输入无关（搜作者名跳出一堆无关 mod）— t1
- 根因：Steam 浏览页 `/workshop/browse/` 的 `searchtext` 只做**标题模糊匹配**，不匹配作者字段。参数本身生效（0 结果词返回 0），问题在 Steam 端语义。
- `swdm/core/steam_api.py` — `SteamAPI` 新增 3 个静态纯函数（无 Qt 依赖，可单测）：
  - `title_hit_rate(items, search_text)`：标题命中率（子串、大小写不敏感）
  - `filter_items_by_creator(items, search_text)`：按 `creator_name` / `creator`(steamid64) 过滤
  - `apply_browse_search_fallback(items, search_text, api_key_mode) -> (items, hint)`：API key 模式（QueryFiles 本身匹配作者）跳过；命中率 ≥ 30% 原样展示；低命中率原样展示 + 状态栏解释；**0 命中自动回退按作者过滤**（在 enrich 完成后执行，creator 字段已补全）；作者也 0 命中则返回**空列表 + 明确空态**"没找到标题或作者含「xxx」的 mod"（t9 议题 B 并入，避免把无关结果当作"搜索坏了/被限流"）
  - 常量 `TITLE_HIT_HINT_THRESHOLD = 0.3`、`SEARCH_LOW_HIT_HINT = "Steam 搜索仅匹配标题；作者搜索请使用详情页或 API key 模式"`
- `swdm/gui/workshop_tab.py` — `__init__` 新增 `_search_by_gen` 记录每代际请求的搜索词（`_do_refresh_list` 写入，避免回读用户可能已改动的输入框）；`_on_items_ready` 在 `_populate` 后按代际搜索词调用 fallback，命中提示追加到状态栏。**搜索框占位文字的"关键词或作者名"承诺未改，作者搜索能力已兑现**；过期代际丢弃逻辑保持不变。
- 测试：`tests/test_search_fix.py`（新增，26 项）— 高命中率不提示/不过滤、0 命中触发作者过滤（含 steamid64 命中）、双 0 命中返回空列表+明确空态（不含"限流"误导）、提示文字精确匹配、API key 模式跳过、空输入边界、GUI 集成（卡片数 + 状态栏 + 空态文案 + 过期代际丢弃）

### S2. 卸载程序无法退出后台（托盘）进程 — t2
- 根因：最小化到托盘后窗口被 `hide()`，Inno 卸载程序的 `CloseApplications=yes` 发送 WM_CLOSE 被当作"最小化到托盘"拦截，进程残留导致卸载不完全。
- `installer/swdm.iss` — `[Setup]` 段新增 `AppMutex=SWDM_SingleInstance_Mutex`（保留 `CloseApplications=yes`），安装/卸载程序据此检测运行中实例
- `swdm/gui/main_window.py` — 新增 `APP_MUTEX_NAME` 常量与 `_create_app_mutex` / `_release_app_mutex`（ctypes `kernel32.CreateMutexW`，`restype` 显式设 `c_void_p` 防 64 位句柄截断，无新依赖；`aboutToQuit` 兜底释放）；`closeEvent` 改三分判定——`_force_quit` 为真或**窗口不可见**时走真正退出（隐藏态收到的 WM_CLOSE 必为卸载程序所发），可见 + 托盘可见时仍 `hide()` 最小化（1.3.7 F4 托盘功能不回归）
- 测试：`tests/test_uninstall_fix.py`（新增，16 项）— 可见窗口拦截、隐藏窗口放行、`_force_quit`、托盘链路、无托盘环境、AppMutex 与 ISS 同名且 Windows 上创建/全局可见（ERROR_ALREADY_EXISTS）/退出后释放

---

## 二、GUI 全面自测修复（t3，6 个小 bug，均 <15 行）

| 编号 | 文件 | 要点 |
|---|---|---|
| G1 | `swdm/gui/workshop_tab.py` | ① "上一页"按钮构造后默认启用，第 1 页可点但无反应 → 初始 `setEnabled(False)`；② 页码标签与禁用态原只在网络回包后更新（350ms 去抖后才有反应）→ 移到 `_refresh_list` 同步路径；③ 空列表一律显示"没有匹配…或触发限流"，翻过最后一页时误导 → `page > 1` 时改显示"已到最后一页，没有更多物品" |
| G2 | `swdm/gui/downloads_tab.py` `_clear_done` | 按旧行号升序 `removeRow` 导致删错行、残留记录永久留在表里（3 行全完成时删掉了 C 留下 B）→ 改为 `sorted(done_rows, reverse=True)` 从底部往上删 |
| G3 | `swdm/gui/downloads_tab.py` `_retry_failed` | 引用不存在的 `self.status_bar` → AttributeError 崩溃（空队列时 `n==0` 短路，故此前从未暴露）→ 改用 `self.window().statusBar().showMessage(...)` + try/except 兜底 |
| G4 | `swdm/gui/library_tab.py` `refresh()` | `_populate` 内 `list_widget.clear()` 清掉选中行，每次启用/禁用/改分类/导入后必须重选 → 重建前记 `_selected_ids()`，重建后按 UserRole 恢复，currentRow 为空时设回第一行 |
| G5 | `swdm/gui/library_tab.py` `_import_list` | 选了非数组 JSON（如 `{"id": {...}}`）时 `for d in data` 遍历字典得字符串键，`d["item_id"]` 抛 TypeError 崩掉整个点击处理器 → `isinstance(data, list)` 守卫 + 明确错误提示 |
| G6 | `swdm/gui/workshop_tab.py:824` | t1 的代际搜索词字典只在 `_do_refresh_list` 初始化；绕过该路径的测试桩会 AttributeError → `getattr(self, "_search_by_gen", {}).get(gen, "")` 兜底 |

测试：`tests/test_gui_sweep.py`（新增，98 项，5 Tab 全覆盖）；`tests/run_all.ps1`（离线全量回归脚本）

---

## 三、核心逻辑全面自测修复（t4，6 个小 bug，均 <15 行）

| 编号 | 文件:行 | 要点 |
|---|---|---|
| C1 | `swdm/core/steam_api.py` 687-692 / 638-647 | `browse()` 首次抓取路径（经典卡片 + hub 内联）返回缓存内对象本身，`enrich()` 就地修改直接污染缓存，使命中路径的深拷贝保护失效 → 两条返回路径都改为 `copy.deepcopy` |
| C2 | `swdm/core/api_cache.py` 201-216 + `steam_api.py:638` | `make_cache_key` 缺 `numperpage` 维度，不同每页条数（30/10）共享同一缓存键会返回错误页大小的结果 → 新增可选参数（默认 30，向后兼容） |
| C3 | `swdm/core/steam_api.py` 236-240 / 296-312 | `_endpoint_throttle` 的 `_endpoint_last` 原为类级共享 dict 且 read-sleep-write 无锁：并发浏览线程读到同一个 last 后一起 sleep，实际请求间隔小于设定值（削弱 429 防护）→ 改为实例级 dict + 锁覆盖读-睡-写全程 |
| C4 | `swdm/core/downloader.py` 529-543 | ① `cancel()` 已把运行中的 job 移出 `_active` 并登记 `_done`，`_exec_job` 收尾时再 append 一次 → `_done` 重复行（clear_completed 计数虚高、retry_all_failed 夸大）→ 仅当 job 仍在 `_active` 时登记；② `library.log_job()` 原在 try 外，SQLite "database is locked" 异常会使工作线程死在 `_active` 未清理状态、调度循环永久挂起 → 包进 try/except |
| C5 | `swdm/core/mod_library.py` 182-190 | `upsert` 的 `ON CONFLICT` 不更新 `enabled`/`download_time`：重新下载后"按下载时间排序"不刷新、`enabled=True` 不落库 → 补上两列（category/notes/favorite 刻意保留用户元数据） |
| C6 | `swdm/core/throttle.py` 141-160 | `AdaptiveConcurrency` 无锁（兄弟类 `Backoff` 有），`_successes+=1` 是 read-modify-write，多线程并发丢计数、并发回升延迟 → `on_failure`/`on_success`/`reset` 全部加锁 |
| C7 | `swdm/core/mod_library.py` 154-158 | SQLite 连接默认 5s 锁超时，多实例共库并发写可能 "database is locked" → `sqlite3.connect(..., timeout=30.0)`（t9 议题 F1 并入；原 P2 已修复） |

测试：`tests/test_core_sweep.py`（新增，117 项）；`test_throttle.py` 约 6 分钟全量通过

---

## 四、版本号与打包（t5）

- `swdm/core/paths.py`：`APP_VERSION = "1.3.8"`
- `installer/swdm.iss`：`#define SWDMVersion "1.3.8"`（AppVersion / VersionInfoVersion / OutputBaseFilename 一并联动）
- 构建：PyInstaller `swdm.spec`（onedir / windowed）→ `build\dist\SWDM\`（137.7 MB）→ ISCC 编译 `installer/swdm.iss`
- 冒烟验证：`SWDM.exe` 启动后进程稳定运行 6 秒后正常关闭（含 t9 并入项后重新构建并复验）
- 安装包：**`installer\Output\SWDM-Setup-1.3.8.exe`，42.66 MB**

---

## 五、全量回归统计（t5）

离线全量回归（`tests/run_all.ps1`，跳过 16 个依赖外网/真实 steamcmd 的脚本）：**48 个脚本，45 PASS / 2 FAIL / 1 NORESULT**

t9 议题 B / F1 并入后复验（改动文件为 `steam_api.py` 回退空态、`workshop_tab.py` 空态状态栏、`mod_library.py` 连接超时）：`test_search_fix`（26/26）、`test_all_buttons`、`test_gui_sweep`（98 项）、`test_core_sweep`（117 项）、`test_batch1/2/3`、`test_v136` 全部 ALL PASS。

- FAIL `test_legacy_format`：唯一失败项是真实 mod 字节数漂移（app 8930 的 mod 现为 8049 字节，硬编码期望 18434），下载/入库/检索逻辑全部 PASS → 上游 mod 更新，非代码回归
- FAIL `test_page_parser`：合成夹具按**已被推翻的旧标签结构假设**（Wayback 三快照实证结论）→ 夹具待重写（见下方待办）
- NORESULT `test_actions_api`：直连真实 Steam 社区接口被 429 限流 → 属实网脚本，应并入 `run_all.ps1` 的 skip 列表
- 进程退出码 -1073740791（0xC0000409）为 Qt 在解释器关闭时拆卸仍运行线程（downloader/ImageLoader）导致的既有现象，修改前后一致；判定标准为 stdout `RESULT: ALL PASS`

---

## 六、剩余待修问题（建议 1.3.9）

| 编号 | 位置 | 问题 | 建议修法 |
|---|---|---|---|
| P1 | `swdm/core/downloader.py:392-393` `_run_loop` | `cancel()` 在 `popleft()` 与 `_active[job.id]=job` 之间的微秒窗口内既查不到 `_queue` 也查不到 `_active` → 取消静默无效、任务仍被执行（偶发，>15 行） | 引入 pending-cancel 集合或派发前检查 `job._stop` |
| P3 | `swdm/core/downloader.py:114` | `__init__` 无条件覆盖 `engine.on_throttle_signal`，两个 manager 共享同一 engine 时后者覆盖前者的节流回调 | 改为追加订阅（列表） |
| P4 | `tests/test_page_parser.py` | 合成夹具按已推翻的旧标签结构假设，3 项恒定 FAIL | 重写为基于真实 Wayback 快照的夹具 |
| P5 | `tests/test_legacy_format.py` | 硬编码字节数随上游 mod 更新漂移 | 改为只校验下载成功 + 入库结构，不固定字节数 |
| P6 | `tests/run_all.ps1` | `test_actions_api` 为实网脚本未在 skip 列表，离线回归报 NORESULT | 并入 `$skip` |

**t9 讨论组并入项**（详见 `docs/feature_review_1.3.8.md`）：议题 B「作者回退空态提示」与议题 F1「SQLite 锁超时」已在打包前并入 1.3.8（见上文 S1 空态分支与 C7），安装包已重新构建复验。

**功能评审结论**（t9 讨论组，详见 `docs/feature_review_1.3.8.md`）：搜索低命中率提示保留并统一措辞；议题 B「作者回退空态提示」+ 议题 F1「SQLite 锁超时」已并入本版（见 S1/C7）；hide_keywords/F7 保留；调试 Tab 默认隐藏、批量按钮精简方案、"按作者浏览"入口留 1.3.9；P1/P3 留 1.3.9；test_page_parser 夹具用真实 Wayback 快照重写；卸载数据目录清理经核实 ISS 已实现。

---

## 七、讨论组交付评审（t8）

**评审时间**：2026-09-28 · 主持：search-fixer · 五方逐一表态（captain / gui-tester / core-tester / installer-fixer / recorder）

**前置条件核实**：t6（GUI 视角第一轮复测）+ t7（核心视角第二轮复测）两轮均结论"无异常"——48 离线脚本 45 PASS / 2 FAIL（均非代码回归）/ 1 NORESULT（实网 429），三轮（t5 打包、t6、t7）结果逐项一致；`tests/test_cross_features.py` 26 项跨功能关联交互全 PASS。

### 逐条过审结论（三原则：精简 / 以用户体感为中心 / 保证基本功能正常运行）

| 改动 | 评审结论 | 要点 |
|---|---|---|
| t1 搜索二次处理 | ✅ 保留 | 用户报告 bug 之一的直接修复；根因在 Steam 端语义（browse 只匹配标题），客户端二次处理是唯一可行解；26 项测试覆盖含空态闭环 |
| t2 卸载 AppMutex + closeEvent 三分判定 | ✅ 保留 | 用户报告 bug 之二的直接修复；`isVisible()` 判据是区分"用户点 X"与"外部 WM_CLOSE"的最简可靠方案；aboutToQuit 兜底释放零风险保留 |
| t3 G1-G6（GUI 6 修） | ✅ 全部保留 | G2/G3/G5 为数据完整性/崩溃级硬伤，G1/G4 为体感修正，G6 一行防御性兜底；均 <15 行、低风险 |
| t4 C1-C6（核心 6 修） | ✅ 全部保留 | 均为正确性 bug，117 项测试托底；C3 留一行类级注释回退属无害残留，建议 1.3.9 清理 |
| t5 打包 + changelog | ✅ 保留 | 版本号双处同步、42.66MB 安装包冒烟通过、变更记录完整可追溯 |
| t9 并入 2 项 | ✅ 保留 | 空态是 t1 的体验闭环，C7 一行改动防 "database is locked" |

### 讨论组提问回答

1. **删减/简化**：**无**。16 项改动全部对应真实缺陷或用户报告 bug，无为改而改的项。
2. **t1 提示文字**：保留——只在命中率 <0.3 的"结果看起来无关"时出现，消除"搜索坏了"的误解，时机正确。但"API key 模式"对匿名用户偏黑话，**建议 1.3.9 柔化并统一两处提示为一套**（如"Steam 搜索只认标题，已按作者名帮你过滤；想精确搜作者，可在设置页填写 Steam API Key"），本版不阻塞。
3. **作者搜索需求**：**已兑现到匿名接口的极限**——占位文字"关键词或作者名"的承诺已兑现（0 命中回退过滤含 steamid64 命中 + 双 0 命中空态）；"查看该作者全部 mod"需 QueryFiles（API key）或详情页入口，属新增功能而非 bug 修复，留 1.3.9 单独评审。
4. **该加但没加**：两项小改（设置页"打开数据目录"按钮、库页导出当前筛选结果）建议留 1.3.9——1.3.8 保持当前范围收口，避免交付前临时加功能引入新风险；均不影响基本功能。另：t6 观察到 steamcmd 偶发报 SUCCESS 但 bytes=0（瞬时、两轮复测未复现），建议 1.3.9 在 `downloader.py:500-508` 成功分支加 `bytes_done==0 且 total_bytes>0` 校验。

### 最终投票

| 成员 | 投票 |
|---|---|
| captain | ✅ 可交付 |
| gui-tester | ✅ 可交付 |
| core-tester | ✅ 可交付 |
| installer-fixer | ✅ 可交付 |
| recorder | ✅ 可交付 |

**讨论组一致认为 1.3.8 可交付（5/5，零反对、零删减意见）。**

### 最终闸门结论

用户规定的两个交付条件均已满足：
1. **讨论组一致认为可交付** ✅（t9 功能评审 A-H 八议题四方逐条表态 + t8 交付评审 5/5 通过）
2. **bug 测试员连续两轮复测均无任何异常** ✅（t6 GUI 视角 + t7 核心视角，含 26 项跨功能关联交互）

**结论：1.3.8 可交付。** 交付物：`installer\Output\SWDM-Setup-1.3.8.exe`（42.66 MB）。

遗留问题（1.3.9 待办，已在第六章显式登记）：P1 cancel 微秒窗口、P3 on_throttle_signal 覆盖、P4 test_page_parser 夹具重写、P5 test_legacy_format 字节数解耦、P6 run_all skip 补 test_actions_api；polish 项：t1 提示文案柔化统一、C3 类级注释残留清理、steamcmd bytes=0 校验、设置页"打开数据目录"按钮、库页导出当前筛选结果。
