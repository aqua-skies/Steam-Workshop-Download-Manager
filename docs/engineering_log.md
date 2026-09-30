# SWDM 1.3.8 工程日志

> 团队：AgentTeams swdm-138（SWDM 1.3.8 bug 修复与全面自测）
> 记录员：recorder（任务 t10）
> 组织方式：成员 → 日期 → 条目；每条含时间、成员、任务编号、改动/思考要点、文件与行号、结论或遗留问题。
> 目的：用户 2026-09-28 规定——所有成员对这项工程的思考、想法、改动都要落盘，方便任何人读取追溯。

---

## 成员：search-fixer（搜索 bug 修复专家）

### 2026-09-28

#### 条目 1｜t1｜修复搜索结果与输入无关的问题｜15:23
- **任务**：t1「修复搜索结果与输入无关」——用户报告 bug 之一。已完成，verdict=pass。
- **根因思考**：Steam `/workshop/browse/` 的 searchtext 只做标题模糊匹配，不匹配作者字段——搜作者名时 30 个结果里几乎全是标题相近的无关 mod。browse 参数本身生效（0 结果词返回 0），问题在 Steam 端语义，故在客户端做二次处理。
- **改动**：
  1. `swdm/core/steam_api.py` — SteamAPI 新增 3 个静态纯函数（无 Qt 依赖，可单元测试）：
     - `title_hit_rate(items, search_text)`：标题命中率（子串、大小写不敏感）
     - `filter_items_by_creator(items, search_text)`：按 creator_name / creator(steamid64) 过滤
     - `apply_browse_search_fallback(items, search_text, api_key_mode) -> (items, hint)`：API key 模式（QueryFiles 自带作者匹配）跳过；命中率≥0.3 原样展示；低命中率原样展示+状态栏提示；0 命中回退按作者过滤（enrich 后 creator 已可用），作者也 0 命中则原样展示+提示。
     - 常量 `TITLE_HIT_HINT_THRESHOLD=0.3`、`SEARCH_LOW_HIT_HINT="Steam 搜索仅匹配标题；作者搜索请使用详情页或 API key 模式"`
  2. `swdm/gui/workshop_tab.py` — `__init__` 新增 `_search_by_gen` 记录每代际请求的搜索词（`_do_refresh_list` 写入，避免回读用户可能已改动的 search_edit）；`_on_items_ready` 在 `_populate` 后按代际搜索词调用 fallback，命中提示追加到状态栏。占位文字承诺未改动；过期代际丢弃逻辑保持不变。
  3. `tests/test_search_fix.py` — 新增脚本式测试（PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen、import 前设 APPDATA 临时目录，mock WorkshopItem 列表，零网络依赖），22 项。
- **验证**：test_search_fix.py ALL PASS（22/22）；test_batch1.py、test_v136.py 回归 ALL PASS。
- **遗留/约定**：三个脚本进程退出码非 0（-1073740791/1）是 Qt 在解释器关闭时拆卸仍运行线程（downloader/ImageLoader）的既有环境崩溃，**判定标准为 stdout RESULT 行**，修改前后一致。
- **结论**：搜索无关结果问题已修复并自测通过。search-fixer 随后转去 t5（打包收尾）。

#### 条目 2｜t9｜讨论组意见（search-fixer 逐条回复 A–H）｜约 16:30
- **任务**：t9 并行讨论组（installer-fixer 组织），只评审不改代码。
- **要点**：
  - A 搜索低命中率提示：**保留**，措辞可略柔化但不要删——这条提示正是用户报告 bug 的"解药"。建议缩短为「Steam 搜索仅匹配标题；按作者搜索请用详情页或 API key 模式」。
  - B 作者回退空态：**该补**。0 命中且回退过滤后仍为空时应明确提示「未找到该作者的 mod」，<10 行小改，建议纳入 1.3.8（search-fixer 可接）。
  - C F7 hide_keywords：**保留**，对重度用户有实际价值；建议 1.3.9 在卡片右键菜单加"屏蔽此类标题"快捷入口。
  - D 调试 Tab：建议加 config 开关 `debug_tab_visible` 默认 false + 设置页复选框；但涉及主窗口构建逻辑，**1.3.8 不动，留 1.3.9**。
  - E 下载页 5 个批量按钮：**保留**，对应真实下载管理场景，每个都有独立语义，合并进"更多"菜单反而增加点击成本。
  - F 3 个待修中大 bug：**全部留 1.3.9**。三者都不触碰"基本功能正常运行"底线，1.3.8 核心价值是兑现用户报告的两个 bug + 14 个自测小修，先发布。
  - G test_page_parser 旧夹具：**重写**为基于真实 Wayback 快照的夹具，否则永远 FAIL 稀释回归信号；重写前可先标记 skip。
  - H 该加没加：① 作者搜索的正解是"查看该作者全部 mod"（作者作品列表页），建议 1.3.9 在详情页加入口；② 卸载侧可补"卸载完成后打开反馈/告别页"，优先级低。
- **结论**：意见已提交 installer-fixer 汇总。

#### 条目 3｜t5｜汇总验证、全量回归、打包 1.3.8、写变更记录｜17:20 完成
- **任务**：t5（deps: t1,t2,t3,t4）——汇总验证、全量回归、打包 1.3.8、写变更记录。
- **版本号同步**：`swdm/core/paths.py` APP_VERSION + `installer/swdm.iss` SWDMVersion 同步 1.3.7→1.3.8（AppVersion / VersionInfoVersion / OutputBaseFilename 一并联动）。
- **构建**：PyInstaller `swdm.spec`（onedir / windowed）→ `build\dist\SWDM\`（137.7MB，退出码 0）→ ISCC 编译 `installer/swdm.iss` 成功 → **`installer\Output\SWDM-Setup-1.3.8.exe`，42.65MB**；冒烟验证 SWDM.exe 稳定运行 6 秒后正常关闭。
- **全量离线回归**（`tests/run_all.ps1`，跳过 16 个依赖外网/真实 steamcmd 的脚本）：48 脚本 **45 PASS / 2 FAIL / 1 NORESULT**。
  - FAIL `test_legacy_format`：真实 mod 字节数漂移（app 8930 的 mod 现为 8049 字节，硬编码期望 18434）→ 上游 mod 更新，非代码回归。
  - FAIL `test_page_parser`：合成夹具按已被推翻的旧标签结构假设 → 夹具待重写。
  - NORESULT `test_actions_api`：直连真实 Steam 社区接口被 429 限流 → 属实网脚本，应并入 skip 列表。
- **多任务同文件冲突检查**：t1+t3 在 `workshop_tab.py`、t1+t4 在 `steam_api.py` 无重叠，通过。
- **变更记录**：`docs/changelog_1.3.8.md`（91 行）——S1/S2 用户 bug + G1-G6 GUI bug + C1-C6 核心 bug + 版本号/打包 + 回归统计 + P1-P6 待修（建议 1.3.9）。
- **B/F1 并入结果**：✅ **已并入并重新打包**（search-fixer 17:45 回信，此前 17:26 记录的"未能并入"已过期，以此为准）。
  - 议题 B（作者回退空态）：`steam_api.apply_browse_search_fallback` 双 0 命中现返回空列表 + 空态文案；`workshop_tab` 空列表时状态栏直接展示该空态（不追加"可能限流"）。`tests/test_search_fix.py` 扩到 **26 项全 PASS**。
  - 议题 F1（SQLite 锁超时）：`mod_library._conn()` 改为 `sqlite3.connect(..., timeout=30.0)`——changelog 第三章新增 **C7** 条目，第六章 P2 已移出待修表。
  - 安装包重新构建：**`installer\Output\SWDM-Setup-1.3.8.exe`，42.66MB**（含两项），冒烟通过。
  - 复验回归：`test_search_fix`（26/26）、`test_all_buttons`、`test_gui_sweep`（98 项）、`test_core_sweep`（117 项）、`test_batch1/2/3`、`test_v136` 全部 ALL PASS。
  - `docs/changelog_1.3.8.md` 已同步更新（S1 补空态分支、第三章加 C7、第六章移除 P2 并加"t9 讨论组并入项"说明）。
- **状态**：t5 已 completed（verdict=pass），t6/t7 已解锁并进入 in_progress。

---

## 成员：installer-fixer（安装包与进程清理专家）

### 2026-09-28

#### 条目 1｜t2｜修复卸载程序无法退出后台（托盘）进程｜15:27
- **任务**：t2「修复卸载程序无法退出后台（托盘）进程」——用户报告 bug 之二。已完成，verdict=pass。
- **改动**：
  1. `installer/swdm.iss` — `[Setup]` 段紧邻 `CloseApplications=yes` 新增 `AppMutex=SWDM_SingleInstance_Mutex`（保留 CloseApplications=yes）。
  2. `swdm/gui/main_window.py` — 新增 `APP_MUTEX_NAME` 常量；`__init__` 初始化 `self._force_quit`/`self._app_mutex` 并调用 `_create_app_mutex()`；新增 `_create_app_mutex`/`_release_app_mutex`（ctypes WinDLL kernel32.CreateMutexW，restype 显式设 c_void_p 防 64 位句柄截断，无新依赖；aboutToQuit 兜底释放）；`closeEvent` 改三分判定——`_force_quit` 为真或窗口不可见时走真正退出（隐藏态收到的 WM_CLOSE 必为 Inno 卸载程序所发），可见+托盘可见时仍 hide() 最小化（F4 不回归）。
  3. `tests/test_uninstall_fix.py` — 新增脚本式测试，16 项断言：可见窗口 closeEvent 被拦截(hide+托盘提示)、隐藏窗口 closeEvent 放行真正退出、_force_quit 直接退出、_real_quit 托盘链路、无托盘环境直接退出、AppMutex 与 ISS 同名且 Windows 上创建/全局可见(ERROR_ALREADY_EXISTS)/退出后释放。
- **验证**：test_uninstall_fix.py ALL PASS (16/16)；test_batch3.py（F4 托盘回归断言）ALL PASS；13 测试 sweep 12 个 ALL PASS，唯一失败的 test_gui_sweep 5 项经 stub 验证为既有问题（与本次改动路径无关）。
- **遗留**：ISS 中 SWDMVersion 仍为 1.3.7，打包 1.3.8 前需同步（已交 t5 处理）。
- **结论**：卸载残留（进程占用）修复完成并自测通过。

#### 条目 2｜t9｜组织并行讨论组｜进行中（16:20 起）
- **任务**：t9 并行讨论组——功能删减/改进/添加可行性评审。installer-fixer 为组织者。
- **动作**：已向 core-tester、gui-tester、search-fixer 各发讨论邀请（议题 A–H 八条，三原则：精简、以用户体感为中心、保证基本功能正常运行）。
- **已收齐三方意见**（search-fixer / core-tester / gui-tester 逐条 A–H 回复，详见各成员条目）。
- **核实结论**（议题 H 卸载数据目录）：installer-fixer 通读 `installer/swdm.iss` 全文确认**已实现**——`CurUninstallStepChanged` 在 `usPostUninstall` 阶段（1）始终删除程序部署的 steamcmd 子目录；（2）按"保留用户数据"复选框（卸载前弹窗同步、进度页可改主意）决定是否删除整个 `%APPDATA%\SWDM`，且带三重安全校验（必须以 `\SWDM` 结尾、必须含 config.json / library.db / logs\swdm.log 之一特征文件、安装目录含源码时整体跳过）。core-tester 的关切已被覆盖，无需新增。
- **产出**：汇总写入 `docs/feature_review_1.3.8.md`（134 行，含结论速览表 + A-H 逐条四方意见 + 组织者补充意见）。
- **结论速览**：A 搜索提示保留但缩短去黑话并统一两处措辞（1.3.8）；B 作者回退空态补提示纳入 1.3.8（search-fixer 在 t5 打包前并入）；C hide_keywords 保留；D 调试 Tab 默认隐藏方案一致但建议留 1.3.9（涉及 `win.debug_tab` 测试同步）；E 批量按钮精简留 1.3.9（倾向合并互斥的暂停/继续单按钮）；F SQLite 锁超时建议 1.3.8 收、on_throttle_signal 倾向本版收、cancel 窗口留 1.3.9；G test_page_parser 旧夹具用真实 Wayback 快照重写不删；H 卸载数据目录清理已核实实现，建议 1.3.8 小改"打开数据目录"按钮 + 导出当前筛选结果。
- **状态**：t9 已完成（verdict=pass）。本文档供 t8 交付评审引用，最终取舍由 t8 结合 bug 复测结果决定。

---

## 成员：gui-tester（GUI 功能测试专家）

### 2026-09-28

#### 条目 1｜t3｜GUI 全面自测：6 个 GUI bug 修复｜16:43
- **任务**：t3「以用户视角扫遍所有功能找 bug」。已完成。
- **新增测试**：`tests/test_gui_sweep.py`（98 项，5 Tab 全覆盖，ALL PASS）；`tests/run_all.ps1`（离线全量回归脚本，跳过网络脚本）。
- **已修 bug（全部 <15 行、不涉及核心逻辑）**：
  1. **G1 工坊页"上一页"初始态 + 翻页状态同步滞后** — `swdm/gui/workshop_tab.py`
     - `_build`（prev_btn 创建处，约 485 行）：构造后 prev_btn 默认启用，第 1 页可点但 `_prev_page` 有守卫 → 点了无反应。修：`self.prev_btn.setEnabled(False)`。
     - `_refresh_list`/`_do_refresh_list`（约 772-790 行）：页码标签与上一页禁用态原只在 `_do_refresh_list` 更新（需过 350ms 去抖 + 网络回包后才反应）。修：移到 `_refresh_list` 同步路径，点翻页立刻看到页码变化。
     - `_populate`（约 909-917 行）：空列表时一律显示"没有匹配…或触发限流"，翻过最后一页时误导。修：`page > 1` 时改显示"已到最后一页，没有更多物品（试试回到上一页）"。
  2. **G2 下载页"清除已完成"按旧行号升序删行 → 残留记录** — `swdm/gui/downloads_tab.py` `_clear_done`（约 285-300 行）
     - 3 行全完成时：removeRow(0) 后 B/C 上移，再 removeRow(1) 删掉 C 留下 B，removeRow(2) 越界无效。修：`sorted(done_rows, reverse=True)` 从底部往上删。
  3. **G3 下载页"↻ 重试失败"有失败任务时必崩** — `swdm/gui/downloads_tab.py` `_retry_failed`（约 319-322 行）
     - `self.status_bar.showMessage(...)` 引用了 DownloadsTab 不存在的属性 → AttributeError。空队列时 `n == 0` 短路返回，所以全按钮测试从未发现。修：改用 `self.window().statusBar().showMessage(...)` + try/except 兜底。
  4. **G4 模组库页刷新后选中行丢失** — `swdm/gui/library_tab.py` `refresh()`（约 150 行）
     - `_populate` 内 `list_widget.clear()` 清掉选择。修：重建前记 `_selected_ids()`，重建后按 UserRole 恢复选中，currentRow 为空时设回第一行。
  5. **G5 模组库"导入列表"对非数组 JSON 崩溃** — `swdm/gui/library_tab.py` `_import_list`
     - 用户选了 `{"id": {...}}` 形式 JSON 时，`for d in data` 遍历字典得字符串键，`d["item_id"]` 抛 TypeError。修：`isinstance(data, list)` 守卫 + 明确错误提示。
  6. **G6 `_on_items_ready` 读 `_search_by_gen` 无属性兜底** — `swdm/gui/workshop_tab.py:824`
     - t1 的代际搜索词字典只在 `_do_refresh_list` 初始化；绕过该路径的子类/测试桩会 AttributeError。修：`getattr(self, "_search_by_gen", {}).get(gen, "")`。
- **测试桩 bug（非 app bug）**：`QInputDialog.getItem` 签名是 `(parent, title, label, items, ...)`，`tests/test_all_buttons.py` 与新 sweep 的桩取 `a[2]`（label 文本），导致"添加游戏目录"拿到的"返回值"是标题文字、name→appid 匹配必然失败后静默返回——这条路径此前从未被真正覆盖。已改 `a[3]`，`_add_game_dir` 现在端到端被覆盖。
- **未发现 GUI 大 bug。**
- **既有失败（与本次 GUI 改动无关，供 captain 参考）**：
  - `tests/test_legacy_format.py` 1 项：真实 mod 被作者更新导致硬编码字节数漂移（t4 已确认）。
  - `tests/test_page_parser.py` 3 项：合成 HTML 夹具按已被 Wayback 实证推翻的旧标签结构假设，需重写该单测夹具（属 core 范围）。
  - `tests/test_throttle.py` 偶发失败（"失败后自动重试成功"时序敏感，3 次运行 2 PASS 1 FAIL）。
- **回归**：test_gui_sweep 98/98 ALL PASS；离线全量 48 脚本 45 PASS / 2 既有失败 / 1 个无 RESULT 行的旧探索脚本；重点回归（test_all_buttons、test_v136、test_batch1/2/3、test_gui_fixes、test_gui_offline、test_v134_gui、test_detail_dialog、test_search_fix、test_uninstall_fix、test_core_sweep、test_checkboxes、test_tag_bar、test_quick_search、test_multi_game、test_scroll_repage、test_toolbar_layout）全 PASS。

#### 条目 2｜t9｜讨论组意见（gui-tester 逐条回复 A–H）｜约 16:40
- **要点**：
  - A 低命中率提示：**改进措辞不删**。"API key 模式"对普通用户是黑话，建议改为"Steam 搜索只认标题，已按作者名帮你过滤；想精确搜作者，可在设置页填写 Steam API Key"——动作指向具体入口；两处提示措辞不统一，建议合并一套。
  - B 作者回退空态：**添加，建议纳入 1.3.8**。查 `apply_browse_search_fallback`（`steam_api.py:828-835`）：0 命中且回退过滤后仍为空时返回 (items, SEARCH_LOW_HIT_HINT)，列表非空但展示无关结果；空列表文案"没有匹配的物品…或触发限流"两种情况都让用户误以为"搜索坏了/被限流了"。建议回退为空时返回空列表 + 明确空态。与 G1 空态分支联动改最干净。
  - C hide_keywords：**保留**。用户报告 bug 之一就是"搜索结果无关/噪音多"，这功能直接降低浏览噪音。入口在设置页"高级"区够用。小改进：工坊页状态栏在有过滤词时标注"已隐藏 N 个标题含屏蔽词的 mod"，让沉默过滤可见。
  - D 调试 Tab：**改进：默认隐藏 + 设置页开关**。config 里已有 `logging.show_debug_panel` 字段但没被用。注意多处测试直接访问 `win.debug_tab`，隐藏需同步改测试。
  - E 批量按钮：**改进：合并暂停/继续为一个状态按钮**（pause_all/resume_all 互斥启用，`_sync_batch_buttons` 已驱动该状态）。其余三个各有独立语义、低频，保留。
  - F 3 个待修 bug：**纳入 1.3.8**（与另两位意见不同）。SQLite 锁超时：下载线程写库+用户同时浏览/导入库是常见交互，触发就是"database is locked"，改动小；on_throttle_signal 覆盖：一行修，属正确性 bug；cancel 微秒窗口：若时间紧可留 1.3.9，但前两条建议这版收。
  - G test_page_parser：**重写不要删**。parse_available_tags 是生产路径必须有回归保护，从 tests/fixtures 真实浏览页快照抽一段真实侧栏片段替换合成 HTML 即可。
  - H 该加没加：① **设置页"打开数据目录"按钮**——用户报告"卸载残留"本质是数据目录散落用户看不见，t2 修了互斥量但用户仍需一键定位残留文件；② **库页"导出列表"应导出当前筛选结果**——`_export_list` 导出全部记录而非当前过滤视图，与按钮位置预期不符；③ 工坊页"下一页"在最后一页仍可点（匿名 browse 拿不到总数，保持现状+提示可接受）。①②都是小改，建议纳入 1.3.8。
- **结论**：纯讨论回复，未改任何代码。

---

## 成员：core-tester（核心逻辑测试专家）

### 2026-09-28

#### 条目 1｜t4｜核心逻辑全面自测：6 个核心 bug 修复 + 3 个待修｜16:13
- **任务**：t4「核心逻辑全面自测：线程安全、缓存、状态机、错误处理」。已完成。
- **已修 bug（均 <15 行，含文件:行号）**：
  1. `swdm/core/steam_api.py:687-692`（及 638-647）— `browse()` 未命中路径返回缓存内对象本身。命中路径有 copy.deepcopy，但首次抓取（经典卡片 + hub 内联两条路径）返回的是缓存里的同一批对象，`BrowseWorker.enrich()` 就地修改直接污染缓存，使命中路径的深拷贝保护失效。两条返回路径都改为深拷贝。
  2. `swdm/core/api_cache.py:201-216` + `steam_api.py:638` — `make_cache_key` 缺 numperpage 维度，不同每页条数（30/10）共享同一缓存键，会返回错误页大小的结果。新增可选参数（默认 30，向后兼容）。
  3. `swdm/core/steam_api.py:236-240/296-312` — `_endpoint_throttle` 的 `_endpoint_last` 原为类级共享 dict，且 read-sleep-write 无锁：并发浏览线程读到同一个 last 后一起 sleep，实际请求间隔小于设定值（削弱 429 防护）。改为实例级 dict + 锁覆盖读-睡-写全程（保留全局速率限制语义）。
  4. `swdm/core/downloader.py:529-543` — ①`cancel()` 已把运行中的 job 移出 `_active` 并登记 `_done`，`_exec_job` 收尾时再 append 一次 → `_done` 出现重复行（完成列表重复、clear_completed 计数虚高、retry_all_failed 重试数被夸大）。改为仅当 job 仍在 `_active` 时登记。②`library.log_job()` 原在 try 外，SQLite "database is locked" 等异常会使工作线程死在 `_active` 未清理的状态，调度循环 `while len(_active)>=current` 永久挂起、整个队列假死。包进 try/except。
  5. `swdm/core/mod_library.py:182-190` — `upsert` 的 ON CONFLICT 不更新 enabled/download_time：重新下载后"按下载时间排序"不刷新、`_register_to_library` 显式设置的 enabled=True 不落库。补上这两列；category/notes/favorite 刻意保留（用户元数据）。
  6. `swdm/core/throttle.py:141-160` — `AdaptiveConcurrency` 无锁（兄弟类 Backoff 有），`_successes+=1` 是 read-modify-write，多线程并发会丢计数、并发回升延迟。on_failure/on_success/reset 全部加锁。
- **待修 bug（中大，未改，建议修法）**：
  - A. `downloader.py:392-393`（_run_loop）— `cancel()` 在 `popleft()` 与 `_active[job.id]=job` 之间的微秒窗口内既查不到 `_queue` 也查不到 `_active` → 取消静默无效、任务仍被执行。建议：引入 pending-cancel 集合或派发前检查 `job._stop`（>15 行，建议留 1.3.9）。
  - B. `mod_library.py:154-157` — 多个 ModLibrary 实例共用同一 DB 文件、每次调用新建连接、SQLite 默认 5s 锁超时，并发写可能 "database is locked"。建议：连接 timeout 抬到 30s 或共享单例连接。
  - C. `downloader.py:114` — `__init__` 无条件覆盖 `engine.on_throttle_signal`，两个 manager 共享同一 engine 时后者覆盖前者的节流回调。建议改为追加订阅（列表）。
- **新增测试**：`tests/test_core_sweep.py`（117 项检查）ALL PASS exit=0。
- **回归**：test_throttle.py（约 6 分钟）ALL PASS exit=0（首跑 1 项失败经隔离复现 + threading.excepthook 验证为机器并发负载导致的时限 flaky，非代码回归；**建议 t5 全量回归串行执行避免误报**）；test_api_cache / test_engine_concurrency / test_batch1/2/3 / test_search_fix / test_uninstall_fix / test_cdn / test_download_fixes / test_engine_autodeploy / test_dep_recording / test_game_dirs / test_deps_parser / test_v136 全部 ALL PASS（15/16）；test_legacy_format.py 1 项失败为既有问题（真实 mod 3804862053 被作者更新，现 8049 字节 vs 硬编码期望 18434）。
- **变更文件**：`swdm/core/{steam_api,api_cache,downloader,mod_library,throttle}.py` + `tests/test_core_sweep.py`。

#### 条目 2｜t9｜讨论组意见（core-tester 逐条回复 A–H）｜约 16:37
- **要点**：
  - A 低命中率提示：**保留但缩短**。"API key 模式"对匿名默认用户无意义，建议精简为"Steam 搜索只匹配标题；按作者找请打开物品详情页。"
  - B 作者回退空态：**改进（补空态提示）**。补一行"未找到标题或作者含「X」的 mod"，消除"搜索坏了"的误解。
  - C hide_keywords：**保留**。降噪对常逛工坊的用户实用，默认空串不侵入；低频配置项不需要更显眼入口。
  - D 调试 Tab：**改进：默认折叠**。排障很有用（本项目重度依赖日志自证），不能删；默认展开增加普通用户噪音。
  - E 批量按钮：**改进：收纳**。五个操作对应五个不同状态，删任何一个都会丢能力。建议保留"暂停/继续 + 取消全部"为主按钮，"重试失败/清除已完成"收进"批量操作"菜单。
  - F 3 个待修 bug：**B 纳入 1.3.8，A/C 留 1.3.9**。B（SQLite 锁超时）单行改动、能防止队列假死，性价比高；A（cancel 微秒窗口）触发概率极低且无数据风险；C（on_throttle_signal 覆盖）只在共享 engine 时触发，app 只有一个 manager。
  - G test_page_parser：**删除过时断言，保留仍有效的**。基于"浏览页有 requiredtags 链接/tagFilter 容器"的断言测的是已被 Wayback 证据推翻的结构（从未存在），那是"错误假设固化"而非回归保护。
  - H 该确认的缺口：**卸载残留的数据目录**。t2 修的是"进程占用导致卸载被忽略"，但用户说"卸载残留"也可能指 %APPDATA%/SWDM 下的库 DB、图片缓存、日志、steamcmd 工作区在卸载后仍保留。请确认 `installer/swdm.iss` 是否清理了这些目录；若没有，建议 ISS 里加卸载时删除 AppData 数据目录（或至少提供选项）——这才是"卸载干净"体感的另一半。
- **结论**：意见已提交 installer-fixer 汇总。
- **小更正**（core-tester 17:33 回信 recorder）：他在 t9 讨论中的原建议就是「B（SQLite 锁超时）纳入 1.3.8」（单行改动、防队列假死、性价比高），与最终决定一致，无分歧；A（cancel 微秒窗口）和 C（on_throttle_signal 覆盖）确认仍留 1.3.9。
- **实现要点**（core-tester 补充，供 t5 参考）：`sqlite3.connect(..., timeout=30)` 加在 `mod_library.py` 的 `_conn()` 里即可，其余 upsert/search 路径无需改动；`tests/test_core_sweep.py` 未直接覆盖该超时（默认 5s 在单实例下不触发），并入后跑一遍 test_core_sweep + test_throttle 回归即可。

---

## 成员：recorder（工程记录员与信息中枢）

### 2026-09-28

#### 条目 1｜t10｜工程日志初始化｜16:51
- **任务**：t10 工程记录员职责载体。
- **动作**：创建 `docs/engineering_log.md`；从 agent_teams_status / team.json 收集 t1–t4 完成产出；用 memory_read 读今日日志与项目笔记补充细节；收录 t9 讨论组三方意见（A–H 八议题）。
- **结论**：日志建立，按"成员 → 日期 → 条目"组织，每条可关联任务编号与成员会话。持续追加至团队解散。

#### 条目 2｜t10｜协调 t9 结论 B/F1 并入 t5（captain 指令）｜17:26
- **背景**：captain 指示 t9 结论里两项建议在 t5 打包前并入 1.3.8，但 t5 已在进行中，存在时序冲突，由 recorder 中继协调。
- **动作 A**：向 search-fixer（t5 负责人）转达——议题 B「作者回退空态提示」（`steam_api.py:828-835`，0 命中且回退过滤后仍为空时返回无关结果，建议返回空列表 + 明确空态，与 t3 G1 空态分支联动）与议题 F1「SQLite 锁超时」（`mod_library.py:154-157`，连接 timeout 抬到 30s）；若尚未打包则先并入，若已在打包后期无法并入则记录到 `docs/feature_review_1.3.8.md` 的"1.3.9 遗留"并告知 captain。
- **动作 B**：向 core-tester 转达 F1 决定（讨论组建议 1.3.8 收），请其后续配合实现/复核。
- **core-tester 回信**（17:33）：小更正——他原建议就是「B 纳入 1.3.8」，与最终决定一致无分歧；A/C 确认留 1.3.9；补充实现要点 `sqlite3.connect(..., timeout=30)` 加在 `_conn()` 即可，并入后跑 test_core_sweep + test_throttle 回归。
- **结果（已更新）**：search-fixer 收到转达后在打包前完成了并入并重新构建（详见 search-fixer 条目 3），**B/F1 均已并入 1.3.8**，此前"未能并入"的记录已过期。

---

## 成员：gui-tester / core-tester｜t6 / t7 双轮复测｜18:20–18:29 完成

- **t6（gui-tester，第一轮复测，GUI 视角）**：结论 **无异常**。核对 1.3.8 打包终态（`installer\Output\SWDM-Setup-1.3.8.exe` 42.66MB，版本号双处同步，含 t9 并入项）；离线 48 脚本 45 PASS / 2 既有失败（test_page_parser 旧夹具、test_legacy_format 字节数漂移，均非代码回归）/ 1 NORESULT（test_actions_api 实网 429）；新增 `tests/test_cross_features.py` 26 项 ALL PASS，覆盖四类跨功能关联（搜索+标签叠加含作者回退、翻页+排序联动、下载中切 Tab 任务行不丢、closeEvent 三分判定——offscreen 无托盘时注入假托盘验证 F4 拦截与卸载放行分支）。
- **t6 瞬时观察（非代码回归）**：test_legacy_format 首跑 app 1250 被 steamcmd 报 SUCCESS 但 bytes=0 且未入库，重跑得完整 68552188 字节；根因定位 `steamcmd_engine.py:371-375` 仅按 steamcmd 成功行正则置 SUCCESS、不校验字节数或文件存在性，建议 1.3.9 在 `downloader.py:500-508` 成功分支对 bytes_done==0 且 total_bytes>0 加内容目录非空校验。
- **t7（core-tester，第二轮复测，核心逻辑独立视角）**：结论 **无异常**，与 t6 基线逐项一致。
- **结论**：两轮视角互补（GUI + 核心），用户交付闸门的测试侧条件（"bug 测试员连续两轮复测均无异常"）已满足，剩余 t8 讨论组交付评审。

---

## 任务流水线总览（2026-09-28）

| 任务 | 成员 | 状态 | 要点 |
|------|------|------|------|
| t1 | search-fixer | ✅ completed/pass | 搜索回退（标题命中率/作者过滤/状态栏提示），22 项测试 PASS |
| t2 | installer-fixer | ✅ completed/pass | 卸载互斥 AppMutex + closeEvent 三分判定，16 项测试 PASS |
| t3 | gui-tester | ✅ completed | GUI 自测 98 项 PASS，修 6 个 GUI 小 bug，无大 bug |
| t4 | core-tester | ✅ completed | 核心自测 117 项 PASS，修 6 个核心小 bug，记录 3 个待修中大 bug |
| t5 | search-fixer | ✅ completed/pass | 版本号同步 1.3.8、PyInstaller+ISCC 构建成功、安装包 42.66MB（含 t9 并入项）、离线回归 45/2/1、changelog 完成 |
| t6 | gui-tester | ✅ completed | 第一轮复测无异常：48 脚本 45 PASS + 新增 test_cross_features 26 项跨功能关联全 PASS |
| t7 | core-tester | ✅ completed | 第二轮复测无异常（核心视角），与 t6 基线一致 |
| t8 | search-fixer | 🔄 in_progress | 讨论组交付评审：逐条过审 + 总投票，结论写入 changelog "讨论组评审"小节 |
| t9 | installer-fixer | ✅ completed/pass | 并行讨论组：A-H 八议题四方意见汇总入 docs/feature_review_1.3.8.md |
| t10 | recorder | 🔄 in_progress | 工程记录员：记录/传递/安排（本日志） |

### 全局遗留事项
1. ~~`installer/swdm.iss` 的 SWDMVersion 仍为 1.3.7~~ → ✅ t5 已同步为 1.3.8（paths.py APP_VERSION 一并联动）。
2. ~~t9 议题 B「作者回退空态」与 F1「SQLite 锁超时」未能并入 1.3.8~~ → ✅ **已并入并重新构建**（B：fallback 双 0 命中返回空列表+空态文案；F1：`mod_library._conn()` timeout 30s，changelog 记为 C7，P2 已移出待修）。安装包 42.66MB，复验 test_search_fix(26)/gui_sweep(98)/core_sweep(117)/batch1-3/v136 全 ALL PASS。
3. `tests/test_legacy_format.py` 1 项失败：真实 mod 被作者更新（字节数漂移 18434→8049→7816，漂移值本身在变证明是上游 churn）——changelog P5，建议改为只校验下载成功 + 入库结构，不固定字节数。
4. `tests/test_page_parser.py` 3 项失败：合成夹具按已被 Wayback 推翻的旧标签结构（t9 议题 G，三方一致认为应重写而非删除）——changelog P4。
5. `tests/test_throttle.py` 偶发时序失败：机器并发负载导致的 flaky，回归已串行执行避免误报。
6. `tests/run_all.ps1` 未跳过实网脚本 test_actions_api（429 限流致 NORESULT）——changelog P6，应并入 `$skip` 列表。
7. t9 议题 D（调试 Tab 默认隐藏）/ E（批量按钮精简）/ H 的两个小改（"打开数据目录"按钮、导出当前筛选结果）建议留 1.3.9。
8. t4 待修 P1（cancel 微秒窗口，`downloader.py:392-393`）与 P3（on_throttle_signal 覆盖，`downloader.py:114`）留 1.3.9（t9 议题 F 定论）。
9. **t6 新发现的建议项（非本版 bug）**：`steamcmd_engine.py:371-375` 仅按成功行正则置 SUCCESS、不校验字节数或文件存在性；建议 1.3.9 在 `downloader.py:500-508` 成功分支对 bytes_done==0 且 total_bytes>0 加内容目录非空校验（瞬时出现一次，重跑即恢复）。

---

# SWDM 1.3.9 迭代（用户报告 12 个新 bug）

> 启动时间：2026-09-28 19:32。1.3.8 已交付（讨论组五方一致"可交付" + 连续两轮复测无异常，安装包 42.66MB）。
> 用户报告 12 项：托盘无法直接退出、游戏框输入未识别、搜索联想下拉混乱、搜索回车疑似无效、标签筛选不准、切换游戏标签不自动刷新、下载卡 99% 速度 0、速度显示 0→突跳 2-300MB/s、设置页首行挤压、下载页/库页删除不互通、库不按游戏分类、详情页加载慢。

## t11｜installer-fixer｜修复托盘退出：隐藏窗口 close() 不触发 closeEvent｜✅ 已完成
- **根因（captain 已定位）**：`swdm/gui/main_window.py:135-137` `_real_quit()`：
  ```python
  def _real_quit(self):
      self._force_quit = True
      self.close()
  ```
  窗口处于隐藏态（在托盘里）时，`QWidget.close()` 对不可见窗口直接返回 true 且**不发送 QCloseEvent**（Qt 行为：QWindow::close 在 !isVisible() 时跳过 closeEvent）。`_force_quit` 虽置位，但 closeEvent 的真正退出逻辑（释放 AppMutex + qApp.quit()）从未被调用，进程继续在后台运行。只有用户先"显示主窗口"再关闭时 close() 才触发 closeEvent——与用户描述完全吻合。
- **修复方向**：`_real_quit` 不依赖 close() 转发，直接执行真正退出：释放 AppMutex（复用 `_release_app_mutex`）+ `QApplication.quit()`；把 closeEvent 里 `_force_quit` 分支的退出逻辑抽成 `_do_real_quit()` 公共方法供两处调用。aboutToQuit 兜底释放保留。
- **验收**：托盘"退出"点击后进程立即结束（无需先显示窗口）；窗口可见态点 X 仍最小化到托盘（F4 不回归）；`_force_quit` 或 `isVisible()=False` 时 closeEvent 仍真正退出（卸载场景不回归）；扩展 `tests/test_uninstall_fix.py` 增加托盘退出用例（模拟 `_tray` contextMenu 的 act_quit triggered → 断言 qApp.aboutToQuit 或进程退出标志）。
- **回归范围**：test_uninstall_fix / test_batch3(F4) / test_cross_features。

### t11 完成记录｜19:46
- **状态**：✅ completed（attempt b31de48c），自测通过。
- **改动**：
  1. `swdm/gui/main_window.py`：
     - 新增 `_do_real_quit()` 公共方法：停止下载管理器 + 保存配置 + 释放 AppMutex + `QCoreApplication.quit()`，供 `_real_quit` 与 closeEvent 真正退出分支共用，避免重复。
     - `_real_quit()` 改为置 `_force_quit=True` 后直接调 `_do_real_quit()`，不再依赖 close() 转发——隐藏窗口也能立即退出。
     - closeEvent 真正退出分支改为调 `_do_real_quit()` + `super().closeEvent(event)`；拦截分支（可见+托盘可见 → hide() 最小化）保持不变，F4 不回归。aboutToQuit 兜底释放保留。
  2. `tests/test_uninstall_fix.py`：新增 `_QuitRecorder` 替身拦截 `QCoreApplication.quit()`（避免测试进程真退出），改造用例 4（`_real_quit` 直接调 quit() 且释放互斥量，不再断言窗口被 close），新增用例 7a/7b/7c（模拟 `_build_tray` 菜单接线：可见态触发退出、**隐藏态触发退出——t11 核心场景**、「显示主窗口」恢复可见）。
- **测试结果**：test_uninstall_fix.py **22/22 ALL PASS**（16→22，新增 6 项）；test_batch3（F4 托盔回归）、test_cross_features、test_gui_sweep、test_all_buttons 全部 ALL PASS。（进程退出码 -1073740791 为既有 Qt 线程拆卸崩溃，判据为 stdout RESULT: ALL PASS。）
- **结论**：托盘退出修复完成，U1 用户 bug 闭环。t11 是 1.3.9 第一个完成的修复任务。

## t12｜search-fixer｜搜索体验修复：游戏输入识别、联想下拉、回车、标签精确过滤｜in_progress
用户报告 4 个搜索相关问题：
1. **输入其他游戏时一直显示未识别，只有从下拉列表选取才能识别**。
   - 根因方向：`swdm/gui/workshop_tab.py:565-578` `_on_game_enter()` 回车时调 `_current_appid()`，其解析链（下拉项文本 → `_last_search_pairs` → 内置表）全部要求名称**精确相等**（lower 后 ==）。网络联想未返回时（本机代理到 store.steampowered.com 慢/熔断，GameSearchClient 有 1.2s 最低间隔 + 8s 超时），`_last_search_pairs` 为空且内置表无该游戏 → 返回 "" → 提示"未识别该游戏"。
   - 修复方向：精确匹配失败时 (a) 联想结果已到取最佳匹配项；(b) 无联想结果触发搜索、结果到了自动选中第一项（回车语义=确认第一个候选）；(c) 兜底支持直接输入纯数字 AppID。
2. **搜索联想下拉逻辑混乱、手感差**。审计 `_on_search_text_edited` / `_do_game_search` / `_fill_search_results` / `_on_search_ready`（581-681 行）：`_fill_search_results` 里 clear()+addItem 使 combo 内部 currentIndex 变 0（blockSignals 只挡信号不挡状态），ed.setText 恢复文本后 currentText 与 lineEdit 文本不一致；本地结果（is_local=True）不弹下拉、网络结果才弹，体感不一致；去重/合并顺序可能把用户正输入的精确匹配排到后面。修复方向：下拉弹出时机一致、候选第一项始终是最佳匹配、输入文本与选中状态同步。
3. **搜索栏没有回车快捷键**。先实测：`workshop_tab.py:428` `search_edit.returnPressed` 已连接 `_refresh_list`，placeholder 也写了"（回车）"。若实测回车无效则修（可能 `_refresh_list` 内有前置条件吞掉信号，或焦点被 tag_edit 抢占）；**若实际有效则记录为"已具备"，向 captain 汇报以免误改**。
4. **选取标签时总是搜到一些没有这个标签的 mod**。
   - 根因方向：`/workshop/browse/` 的 requiredtags 参数服务端只做近似匹配（或"或"语义），不是精确包含。参考 t1 做法（客户端二次处理）：browse 返回的 WorkshopItem 若带 tags 字段，按用户选中的标签做客户端精确过滤（交集判定）；若服务端结果不含 tags 则在状态栏提示"标签过滤为服务端近似匹配"。与 t13（标签栏自动刷新）联动，注意 tag_bar 选中状态与 tag_edit 文本一致性。
- **测试要求**：每小项配测试（`tests/test_search_fix.py` 扩展或新建 `tests/test_game_search_fix.py`）。回归 test_search_fix 等。

## t13｜gui-tester｜GUI 修复：切换游戏标签自动刷新、设置页首行挤压、删除/移除互通｜in_progress
用户报告 3 个 GUI 问题：
1. **切换游戏时标签拉取没有自动切换，需手动切换**。审计 `workshop_tab.py:683-690` `_on_game_changed()`——它确实调了 `_fetch_tags()`，但标签栏没跟着切换。可能原因：(a) `_fetch_tags` 拉到新标签后没先清空 tag_bar 旧选中项（旧游戏选中标签残留，列表仍按旧标签过滤）；(b) `_fetch_tags` 节流/缓存导致仍返回旧游戏标签；(c) editable combo 输入游戏名时 currentIndexChanged 不触发（与 t12 联动）。需确保切换游戏后标签栏内容、选中状态、列表过滤三者同步刷新。
2. **设置页面展开行第一行与下方方框挤压**。审计 `swdm/gui/settings_tab.py` 目录表/分组表布局：可能是表头 section 与首行 spacing/margins 为 0、QTableWidget 首行行高+表头重叠、或分组容器 QVBoxLayout spacing 未设。对比 1.3.6 `_ElidedLabel` 手感批次做法定位实际挤压源。用 offscreen 截图或量化几何（表头 bottom 与首行 top 间距）验证。
3. **下载页和 mod 库页面的删除/移除操作没有互通显示**。审计 downloads_tab 删除入口与 library_tab 移除入口，补双向联动：删除已入库 mod 时同时移除库记录（反之亦然），并触发双方 refresh。注意 t3 G4 的选中行恢复不回归。
- **测试要求**：每项配测试（`test_gui_sweep.py` 扩展）。回归 test_gui_sweep / test_all_buttons / test_cross_features。

## t14｜core-tester｜核心修复：下载速度采样（卡 99%/速度突跳）、mod 库按游戏分类｜in_progress
用户报告 3 个下载/库核心问题：
1. **下载时容易卡在 99% 且显示下载速度为 0**。
2. **下载状态拉取有问题：经常速度一直为 0，过一段时间突然显示 2-300MB/s**。
   - 根因方向（两者同源——速度采样统计）：审计 `swdm/core/downloader.py` 进度上报与 `downloads_tab` 速度显示。若速度 = (bytes_now-bytes_last)/dt，但采样定时器间隔与实际上报频率不匹配（UI 定时器 500ms 读一次但工作线程 1s 才报一次），dt 内增量为 0 → 显示 0；或进度回调在子线程通过信号发到主线程时被 Qt 合并/丢弃（AutoConnection 对高频信号会合并，QueuedConnection 排队积压），一次 tick 累积多秒增量 → 突然显示 200-300MB/s 假速度；卡 99% 可能是最后一块完成回调丢失（同原因），或 CDN 断点续传的 total_bytes 与实际下载字节数不一致导致百分比封顶 99%。
   - 修复方向：速度用滚动窗口（最近 N 秒增量/真实经过时间）而非瞬时 tick；进度信号用 QueuedConnection 且每次携带时间戳，UI 侧按时间戳计算速率；完成判定以文件字节数/校验为准而非百分比。可参考 t4 已修的 C4（_done 重复登记）避免重复计数污染。
3. **不同游戏的 mod 在 mod 库管理里没有分类**。审计 `swdm/core/mod_library.py` schema 与 `library_tab.py` 展示：给库表加 game_appid 维度（若 schema 已有 appid 列则用上），库页面增加"按游戏分组"或游戏列/筛选。注意 upsert 写入时要带 appid（t4 C5 的 upsert 修复不回归）。
- **测试要求**：每项配测试（`test_core_sweep.py` 扩展或新建 `tests/test_download_stats.py`）。回归 test_core_sweep / test_download_fixes / test_cdn。

## t15｜gui-tester｜mod 详情页加载性能优化｜pending（t13 完成后启动）
- **用户报告**：加载 mod 详情页速度过慢。
- **背景**：工坊卡片点击后弹出详情页，需拉取 steamcommunity.com `/sharedfiles/` 详情页解析（本机走 fake-IP 代理，详情页 ~110KB，`_community_get` 已加 Accept-Language 防 429）。
- **排查与优化方向**（按性价比排序）：定位详情页加载入口（workshop_tab 卡片点击 → 详情 worker），量化慢在哪（网络请求 / HTML 解析 / 图片加载阻塞 UI）；详情缓存（1.3.7 O4 上限 100）命中路径是否真快、未命中时是否阻塞 UI 线程；详情页图片懒加载（先出文字，图片异步）；HTML 解析若用 BeautifulSoup 全文档解析，改用目标片段提取（正则定位关键 div）；详情拉取与卡片 enrich 的请求节流（`/sharedfiles/` 6s 基准）排队时按用户点击优先级插队；详情页先显示骨架/加载进度条避免界面假死。注意 429 熔断器（O5 _Throttle）不要因高频请求被反复触发。
- **测试要求**：先用 offscreen 量化基线（单次详情解析耗时），优化后对比；配测试（`test_core_sweep.py` 扩展或新建 `tests/test_detail_perf.py`，mock 响应测解析耗时 + 缓存命中）。

## t16｜installer-fixer｜并行讨论组：1.3.9 功能删减/改进/添加可行性评审｜pending
- 并行于 t11-t15（不要等修复完成），方式同 1.3.8 的 t9：向 search-fixer、core-tester、gui-tester、recorder 发讨论邀请。
- **议题 A-E**：
  - A. 1.3.8 遗留 P1（`downloader.py:392-393` cancel 微秒并发窗口）与 P3（`downloader.py:114` on_throttle_signal 覆盖）是否纳入本版（core-tester 曾倾向本版收 P3，评估改动风险）。
  - B. t9 已建议留 1.3.9 的功能项是否落地：t1 提示文案柔化（去"API key 模式"黑话并统一两处提示为一套）、设置页"打开数据目录"按钮、库页导出当前筛选结果、调试 Tab 默认隐藏（`show_debug_panel` 配置已存在）。
  - C. 新报告 bug 引出的功能取舍：mod 库按游戏分类（t14）会新增游戏列/分组，是否与"精简"冲突？下载页 5 个批量按钮（t9 建议合并暂停/继续为单按钮）本版是否动？
  - D. GameSearchClient 的 1.2s 最低请求间隔（防 storesearch 熔断）与"联想手感差"的权衡：能否降到更小间隔或改用指数退避？
  - E. 是否有"该加但没加"的功能（结合本次用户反馈的 12 项，尤其标签筛选、游戏切换、速度显示）。
- **产出**：汇总写入 `docs/feature_review_1.3.9.md`，每条含议题、各方意见、结论、理由。只讨论和写文档，不改代码。

## t17｜search-fixer｜汇总验证、全量回归、打包 1.3.9、写变更记录｜pending（依赖 t11-t15）
- **冲突检查**：t11-t15 改动的共享文件无互相覆盖（重点 `workshop_tab.py`：t12 游戏输入/标签过滤 vs t13 切换标签刷新；`downloads_tab.py`：t13 删除互通 vs t14 速度显示；`main_window.py`：t11 托盘退出独占）。
- **并入 1.3.8 遗留**：评估并纳入 t16 讨论组结论中决定本版做的项（至少 P3 on_throttle_signal 覆盖、t1 提示文案柔化；P1 cancel 窗口视 t16 结论）。
- **全量回归**：`tests/run_all.ps1` 串行执行（避免并发 flaky，t4/t5 踩过），既有失败需与 1.3.8 基线逐项一致。
- **版本号**：`swdm/core/paths.py` APP_VERSION 1.3.8→1.3.9；`installer/swdm.iss` SWDMVersion 1.3.9。
- **打包**：PyInstaller `swdm.spec --noconfirm` → 复制 dist\SWDM 到 build\dist → ISCC 编译 → `installer\Output\SWDM-Setup-1.3.9.exe`，冒烟验证稳定运行 6 秒。**必须设 QT_QPA_PLATFORM=offscreen**，否则 GUI 测试假失败（t5 踩过坑）。
- **变更记录**：`docs/changelog_1.3.9.md`，用户报告 12 项逐条编号（U1-U12）+ 对应修复任务 + 测试覆盖 + 版本号/打包 + 回归统计 + 待修清单 + t16 讨论组评审小节占位（t20 回填）。

## t18｜gui-tester｜bug 复测第一轮：用户视角验证 12 项修复｜pending（依赖 t17）
- 对 1.3.9 打包终态做全量复测，重点从用户操作视角验证 12 项是否真正修复（不只看单元测试）：托盘退出、游戏框识别（中文/英文/纯 AppID）、联想下拉顺手度、回车生效、标签精确过滤、切换游戏标签自动切换、卡 99%/速度平滑、设置页首行挤压、删除互通、库按游戏分类、详情页加载速度。
- 全量离线回归与 1.3.8 基线对比零新增失败；`test_cross_features.py` 扩展覆盖本轮新行为（托盘退出、标签过滤、删除互通）。

## t19｜core-tester｜bug 复测第二轮：核心逻辑独立复测｜pending（依赖 t17）
- 重点：下载速度采样正确性（滚动窗口、时间戳、完成判定以字节数为准，用 mock 流量化验证）；mod 库按游戏分类的 schema 与查询正确性（appid 落库、分组查询）；详情页优化不破坏解析正确性（mock 详情页 HTML 验证字段提取齐全）；并入的 1.3.8 遗留项（P3 on_throttle_signal 订阅化等）真正修复且不回归；全量回归与 1.3.8 基线逐项一致。

## t20｜search-fixer｜讨论组交付评审：一致通过后方可交付 1.3.9｜pending（依赖 t16-t19）
- 前置核实：t18 + t19 连续两轮无异常后，组织全体成员（captain、gui-tester、core-tester、installer-fixer、recorder）按三原则逐条过审并投票：12 项 bug 逐条确认修复且无过度设计；t16 讨论组结论执行情况；是否有该加没加影响基本功能的项；总投票 1.3.9 是否可交付（5/5 一致 + 零反对）。
- **产出**：汇总写入 `docs/changelog_1.3.9.md` "讨论组评审"小节（逐条过审表+提问回答+投票表+闸门结论），置 completed 并输出最终闸门结论。收齐 captain 最后一票后汇总。

## 1.3.9 任务流水线

| 任务 | 成员 | 状态 | 要点 |
|------|------|------|------|
| t11 | installer-fixer | ✅ completed | 托盘退出：`_do_real_quit()` 公共方法 + qApp.quit()，test_uninstall_fix 22/22 |
| t12 | search-fixer | 🔄 in_progress | 搜索 4 修：游戏输入识别/联想下拉同步/回车实测/标签客户端精确过滤 |
| t13 | gui-tester | 🔄 in_progress | GUI 3 修：切换游戏标签刷新/设置页首行挤压/删除互通 |
| t14 | core-tester | 🔄 in_progress | 核心 3 修：速度采样滚动窗口（卡 99%/突跳）/mod 库按游戏分类 |
| t15 | gui-tester | ⏳ pending | 详情页加载优化（t13 后启动） |
| t16 | installer-fixer | ⏳ pending | 并行讨论组 A-E 议题 → docs/feature_review_1.3.9.md |
| t17 | search-fixer | ⏳ pending | 回归+打包 1.3.9+changelog（依赖 t11-t15） |
| t18 | gui-tester | ⏳ pending | 复测第一轮：用户视角验证 12 项（依赖 t17） |
| t19 | core-tester | ⏳ pending | 复测第二轮：核心逻辑独立复测（依赖 t17） |
| t20 | search-fixer | ⏳ pending | 交付评审：5/5 一致 + 零反对（依赖 t16-t19） |

## 1.3.9 跨任务依赖与联动注意（供 t17 冲突检查参考）
- `swdm/gui/workshop_tab.py`：t12（游戏输入识别/联想下拉/标签过滤，`_on_game_enter`/`_fill_search_results`/581-681 行附近）与 t13（切换游戏标签自动刷新，`_on_game_changed`/`_fetch_tags` 683-690 行附近）共用——任务描述已互相点名（t12 第 4 点提"与 u3 联动"，t13 第 1 点提"与 u2 联动"），双方需注意 tag_bar 选中状态与 tag_edit 文本一致性。
- `swdm/gui/downloads_tab.py`：t13（删除互通）与 t14（速度显示）共用。
- `swdm/gui/main_window.py`：t11 独占（`_real_quit`/`_do_real_quit`/closeEvent）。
- 1.3.8 遗留待并入（t17 阶段）：P1（`downloader.py:392-393` cancel 微秒窗口）、P3（`downloader.py:114` on_throttle_signal 覆盖）、t1 提示文案柔化——视 t16 结论。

---

## 成员：recorder｜1.3.9 讨论组与协调记录

### t16 讨论组意见（recorder 逐条回复 A–E）｜19:50

**A. 1.3.8 遗留 P1 / P3 是否纳入 1.3.9**
- **P3（on_throttle_signal 覆盖，`downloader.py:114`）：建议纳入**。一行改的正确性债（改追加订阅），1.3.8 讨论组已倾向本版收，t17 任务描述也点名"至少 P3"，继续拖没有收益。
- **P1（cancel 微秒窗口，`downloader.py:392-393`）：建议留 1.3.10**。>15 行改动，触发概率极低且无数据风险（1.3.8 讨论组 2/3 主张留后版）；1.3.9 已有 12 个用户 bug 要修，排期不应再扩。建议 t14 修速度采样时顺手加廉价防御：取消后不再登记 `_done`。

**B. t9 建议留 1.3.9 的功能项是否本版落地**
- **① t1 搜索提示文案柔化：建议落地**（改进）。三方一致认为"API key 模式"是黑话、两处提示措辞不统一；纯文案改动零风险，与本版 t12 搜索体验修复天然一并做。
- **② 设置页"打开数据目录"按钮：建议落地**（小改）。与本次"卸载残留/库分类"主题直接呼应（用户需要看见自己的数据在哪）。
- **③ 库页导出当前筛选结果：建议落地**（小改）。按钮位置（过滤工具栏旁）与行为（导出全部）不符，属轻量体验修正。
- **④ 调试 Tab 默认隐藏：建议留 1.3.10**。涉及主窗口构建逻辑 + 多处测试同步（`win.debug_tab` 引用），回归风险偏高；本版已有 t13 改 settings_tab 布局，不宜再叠主窗口改动。`show_debug_panel` 配置已存在，1.3.10 接上即可。

**C. 新 bug 引出的功能取舍**
- **① mod 库按游戏分类（t14）与"精简"冲突？——不冲突，建议做**。用户本轮明确报告"不同游戏的 mod 没有分类"，这是基本功能可用性问题（找不着自己的 mod），优先级高于精简原则。精简指"不堆砌无用功能"，给库加游戏列/分组是让现有数据可辨识，属必要索引。建议实现保守：加游戏列 + 筛选下拉即可，不做复杂分组树。
- **② 下载页 5 个批量按钮本版是否动？——不动**。1.3.8 讨论组曾倾向合并暂停/继续单按钮，但本版 12 个 bug 已占满排期，且按钮布局已被 test_all_buttons 覆盖，改动会牵动 `_sync_batch_buttons` 状态同步与测试。留 1.3.10。

**D. GameSearchClient 1.2s 间隔 vs 联想手感**
- **建议：降间隔 + 指数退避组合，而非二选一**。1.2s 是防 storesearch 熔断（非官方 Storefront API 限流比官方 API 更狠），但联想手感需要 ~300-400ms 响应。建议：首次请求允许较短间隔（如 350ms），触发 429 后指数退避（1.3.7 O5 `_Throttle` 熔断器可复用）；同时 t12 的"输入文本与选中状态同步"修好后，即使联想稍慢用户也能先回车确认。注意与 1.3.6 已有的搜索防抖（350ms）保持节奏一致。

**E. 该加但没加的功能（结合本次 12 项反馈）**
1. **标签筛选后的"已过滤"可见性**：t12 做标签精确过滤后，用户不知道结果被过滤了多少，建议状态栏标注"已按标签过滤：N 个结果"（与 1.3.8 讨论组 hide_keywords 的"已隐藏 N 个"同类设计）。
2. **下载完成的通知/提示**：用户反馈"卡 99%"，除了 t14 的采样修复，建议下载真正完成时托盘通知 + 状态栏明确提示（1.3.7 F4 托盘通知已存在，接上即可）——直接缓解"不知道下载好没好"的焦虑。
3. **steamcmd 成功但 bytes=0 的校验**（t6 复测时发现的瞬时问题）：`steamcmd_engine.py:371-375` 仅按成功行正则置 SUCCESS，建议本版顺手在 `downloader.py:500-508` 成功分支对 bytes_done==0 且 total_bytes>0 加内容目录非空校验。这是"保证基本功能正常运行"的闭环，改动小。
4. 不建议本版加新功能（如作者作品列表页）——排期已满，留 1.3.10。

**结论**：意见已提交 installer-fixer 汇总（`docs/feature_review_1.3.9.md`），供 t20 交付评审引用。

---

## t12–t16 完成记录（补录）｜21:00–21:45

### t12｜search-fixer｜搜索体验 4 修｜✅ completed/pass
- **测试**：新建 `tests/test_game_search_fix.py` **38/38 ALL PASS**（U1 游戏输入识别 10 + U2 联想下拉 9 + U3 回车/标签同步 3 + U4 标签精确过滤 16）；回归 test_search_fix(26)、test_gui_sweep(98)、test_cross_features(26)、test_all_buttons(34) 全部 ALL PASS。
- **结论**：4 个搜索问题全部修复（具体实现细节由 search-fixer 自报，测试数字如上）。U2/U3/U4 用户 bug 闭环。

### t13｜gui-tester｜GUI 3 修｜✅ completed/pass
- **bug1（u6 切游戏标签不自动切换）**：根因是 `tag_bar.set_tags()` 的"切换游戏后保留选中"逻辑会重选同名标签，且 `_on_game_changed` 从不清 tag 选中与 tag_edit 过滤参数 → 新游戏列表仍按旧标签过滤。修：`_on_game_changed` 开头 `tag_bar.clear_selection()` + `tag_edit.setText("")`（set_tags 的同游戏手动刷新保留逻辑不动）。
- **bug2（u9 设置页首行挤压）**：offscreen 几何量化结论——全部 QFormLayout 行间距 ≥6px 健康，最贴合描述的是分组标题按钮与首个 QGroupBox 仅 6px + 目录表首行行高无保底。三处定向加固：`CollapsibleSection` 内容上边距 6→10、账号分组表单显式 spacing/margins、目录表 `defaultSectionSize=30` / `minSectionSize=24`。
- **bug3（u10 删除/移除不互通）**：双向信号——`DownloadsTab.library_changed` + `_remove_row` 对已入库成功任务弹「同时从 mod 库移除（含文件）？」；`LibraryTab.records_removed` 两个删除动作后 emit；main_window 接线（`library_changed`→无参槽 `_on_library_changed`，`records_removed`→`remove_rows_for`）。G4 选中恢复不回归（refresh 走 `_restore_combo`）。
- **测试**：test_gui_sweep **116 项 ALL PASS**（含 u6 4 / u9 3 / u10 10 项新检查）、test_all_buttons、test_cross_features 全部 ALL PASS。
- **并行冲突处理**：core-tester 先前看到的 3 FAIL（`library_changed` 误连需参槽 `_on_download_finished` 致 TypeError + u9 -470px）已修，最终文件态已同步给 core-tester。
- **结论**：3 个 GUI bug 全部修复，19 项新测试。u6/u9/u10 用户 bug 闭环。

### t14｜core-tester｜核心 3 修｜✅ completed
- **速度采样**：`throttle.py` `ProgressSmoother` 重构为 deque 滚动窗口（默认 3s），窗口内真实增量/真实经过时间；合并 tick 12MB/s 而非旧 EMA 的 ~20000MB/s、长停顿归 0、窗口外样本淘汰、`_MAX_SAMPLES=64` 封顶。
- **卡 99%**：`downloader.py` `DownloadJob.percent`：`bytes_done>=total_bytes` 直返 100，即使完成回调被 Qt 合并/延迟也不卡 99%。
- **库按游戏分类**：`library_tab.py` 下拉与行文本显示 `game_name`（Garry's Mod / Left 4 Dead 2），未知游戏回退 'AppID N'；`mod_library` appid 列/upsert/search(sort=appid) 既有维度验证不回归（t4 C5 upsert 保留）。
- **测试**：新建 `tests/test_download_stats.py` **40 项 ALL PASS**（速度采样 17 + 卡99% 5 + 库分类 18）；回归 test_core_sweep / test_download_fixes / test_cdn / test_throttle / test_batch1-3 / test_cross_features / test_all_buttons 全部 ALL PASS。test_gui_sweep 当时 3 FAIL 为 t13 并行半成品（非 t14 文件），后由 t13 修复同步。
- **结论**：3 个核心问题全部修复。u7/u8/u11 用户 bug 闭环。

### t15｜gui-tester｜详情页加载性能优化｜✅ completed/pass
- **量化基线推翻任务预设**：4 真实夹具放大到 ~220KB，全链路解析合计仅 **4.5ms/页**（description 0.3-0.4ms、comments 0.9-1.5ms、deps 0.0-0.2ms）。**解析不是瓶颈**；真实瓶颈是 `/sharedfiles/` 的 3s 端点节流把连续点击串行化，且 400ms 悬停预取会抢占槽位，导致用户点击排在预取后面空等 3s。
- **优化（用户点击永远优先于投机请求）**：
  - `steam_api.py` `_endpoint_throttle(path, priority)`：priority=True 绕过端点等待；低优先级改 0.25s 分片睡眠，期间检测 `_priority_pending` 则立即让槽返回 False。`_community_get` 计数器进出清零（finally + max(0,n-1) 防泄漏），被礼让时返回空串由预取静默处理。
  - `DetailPageWorker`（用户点击）与 `get_dependencies`（用户下载）传 priority=True；预取 worker 保持低优先级。
  - `workshop_tab` `_do_prefetch_detail`：有用户请求在飞时直接跳过预取。
- **感知层（既有，无需改）**：弹窗 show() 先于 worker（非模态）、简介先填 item.description、依赖/评论/图片均显示加载占位、预览图独立 QThread。骨架屏已完备。
- **附带修复**：`test_throttle.py` 4 处仍用 P3 之前的可调用对象赋值（`on_throttle_signal = lambda`），引擎迭代抛 TypeError 致 8 项失败；改为 `.append()` + `in` 语义后降至 2/5 偶现 flake，定位为 `downloader.py:375-379` `stop()`→`cancel_all()` 与 531-541 自动重试再入队竞态，已带证据移交 core-tester（非本任务引入，后入 t22）。
- **测试**：新建 `tests/test_detail_perf.py` **17 项 ALL PASS**（4 夹具解析性能上限 60ms、缓存命中"调网络即抛错"验证、假时钟下 6 项优先级礼让语义、4 项 GUI 冒烟含 DetailPageWorker 传 priority=True）；回归 11 套全 ALL PASS。
- **结论**：u12 用户 bug 闭环（体感层面：连续点击不再串行空等 3s）。

### t16｜installer-fixer｜并行讨论组 A-E｜✅ completed/pass
五方（installer-fixer 组织 + search-fixer/core-tester/gui-tester/recorder）逐条评审，汇总写入 `docs/feature_review_1.3.9.md`。结论摘要：
- **A-P3（on_throttle_signal 覆盖）：本版收（5/5）**——引擎侧单回调改 list 遍历约 3 行，append 订阅，有真实触发路径。
- **A-P1（cancel 微秒窗口）：留 1.3.10（5/5）**——>15 行涉状态机核心；本版改收"取消后不再登记 _done"廉价防御（t14 顺手带）。
- **B-① 搜索提示文案柔化：本版收（5/5）**——去黑话 + 与 t12 新提示统一为一套措辞。
- **B-② 设置页"打开数据目录"按钮：本版收（5/5）**——零风险，与 u10 删除互通呼应。
- **B-③ 库页导出当前筛选结果：本版收（5/5）**。
- **B-④ 调试 Tab 默认隐藏：倾向留 1.3.10（4/5）**——`win.debug_tab` 测试耦合 + 与复测节奏冲突。
- **C-① 库按游戏分类：本版收（5/5）**——保守实现：core-tester 定位到 appid 过滤下拉早已存在，缺口只是展示层显示裸数字，用 `games.game_name()` 渲染即可，不新增分组树（与 recorder 意见一致）。
- **C-② 下载页 5 批量按钮：本版不动（5/5）**——留 1.3.10 polish 批。
- **D GameSearchClient 间隔：降到 0.6-0.8s + 复用 O5 `_Throttle` 熔断退避（3/4 支持降间隔，core-tester 主张只加本地即时层；取保守值不直接 350ms——storesearch 匿名接口无速率保障、本机出口 IP 已被限过）**。
- **E-① 标签过滤可见性：t12 已实现，议题关闭**；**E-② 下载完成托盘通知本版收**（复用 F4 链路）；**E-③ steamcmd bytes=0 校验本版收**（`downloader.py:500-508`，<15 行）；**E-④ 不加新大功能（5/5）**——作者作品列表页等留 1.3.10。
- **结论**：文档供 t20 交付评审引用，最终取舍由 t20 结合 t17/t18 复测结果决定。本任务只写文档，未改任何代码。

---

## t17–t19 完成记录 + t20 投票（补录）｜23:45–01:07

### t17｜search-fixer｜汇总打包 1.3.9｜✅ completed/pass
- PyInstaller 330 文件 + ISCC 编译成功，FileVersion/ProductVersion 均 1.3.9，冒烟 6 秒稳定。
- 安装包 `installer\Output\SWDM-Setup-1.3.9.exe` **42.67MB**；`docs/changelog_1.3.9.md` 12.3KB。
- **t16 决议 8 项已全部并入**：A-P3 订阅化、A-P1 廉价防御、B①文案柔化、B②打开数据目录、B③导出筛选结果、C①库分类、E②下载完成通知、E③ bytes=0 校验。
- 结论：打包成功，t18/t19 依赖满足。

### t18｜gui-tester｜复测第一轮（GUI/用户视角）｜✅ completed/pass
- 新建 `tests/test_rettest_139.py` **42 项 ALL PASS**——U1-U12 用户操作视角：托盘隐藏态直退 + mutex 释放、输入联想、三种游戏输入（中文/英文/纯 AppID）、回车待选链路、标签精确过滤端到端、切游戏清标签、卡 99%、突发摊平、设置页间距行高、删除互通双向、库游戏名分类、详情页缓存 + 优先级。
- `test_cross_features.py` 扩展 **16 项 ALL PASS**（关联 5-8）。
- `run_all.ps1` 全量回归 **56 脚本 54 PASS / 2 既有非回归**（test_legacy_format 字节数漂移、test_page_parser 旧夹具，同 1.3.8 基线零新增失败）/ 0 NORESULT。
- 结论落 `docs/retest_round1_gui_1.3.9.md`。判定 **pass**。

### t19｜core-tester｜复测第二轮（核心视角）｜✅ completed
- **40 项独立检查全 PASS**，结论落 `docs/retest_round2_core_1.3.9.md`。
- 复测脚本首轮 4 FAIL 均为固件问题非产品缺陷（已修）：`ProgressSmoother.feed()` 签名是 `feed(bytes_done, total, now=)` 返回 dict 快照（旧假设为 `(now, bytes)` 位置参数返回标量速度）；`parse_creator_name` 锚点为 `class="creatorName"`（非 friendBlock）；`parse_required_items` 需匹配新结构。
- 与 t18 共同构成交付闸门双轮复测。**注**：任务状态 completed 但 verdict 字段为空（非 pass），结论本身为"无异常"——recorder 在 t20 投票中已提醒主持方注意此凭据完整性。

### t20｜search-fixer｜交付评审｜✅ completed/pass — **1.3.9 正式交付**
- **五方投票 6/6 同意交付、零反对**（search-fixer 主持 + captain + installer-fixer + gui-tester + core-tester + recorder）。
- 评审记录写入 `docs/changelog_1.3.9.md` 第六节：6.1 U1-U12 逐条过审表 / 6.2 t16 执行情况表 / 6.3 提问回答 / 6.4 五方投票表 / 6.5 闸门结论。
- **两处凭据收口**：第五节回归统计回填终态（56 脚本 54 PASS / 2 既有非回归 / 0 NORESULT，t17 时点 53/51 已注明）；t19 verdict 字段终态不可变，core-tester 追加 acceptanceResults 6/6 passed 作等价 PASS 记录。
- **交付条件核对**：① 讨论组一致（t16 五方 + t20 6/6 零反对）✓ ② bug 测试员连续两轮复测无异常（t18 GUI 58 项 + t19 核心 40 项，两轮全量回归零新增失败）✓ ③ 版本号双端 1.3.9 + changelog 可追溯 ✓ ④ 全量回归两轮 ✓。
- **结论**：**1.3.9 正式交付**，安装包 `installer\Output\SWDM-Setup-1.3.9.exe` 42.67MB。t21（provider 抽象层）/ t22（1.3.10 遗留项）随之解锁。

---

## 1.3.9 交付总结

| 维度 | 结果 |
|------|------|
| 用户报告 bug | U1-U12 共 12 项，全部根因修复 + 测试闭环 |
| 讨论组并入 | t16 决议 8 项已收（A-P3 / A-P1 防御 / B①②③ / C① / E②③） |
| 延后 1.3.10 | 5 项（A-P1 主修复 / B④调试 Tab / C②批量按钮 / D 间隔微调 / E④新功能）+ t15 移交 stop/retry 竞态，全部登记 t22 |
| 新增测试 | 约 111 项新检查（t11 +6 / t12 38 / t13 +18 / t14 40 / t15 17），全部 ALL PASS |
| 双轮复测 | t18 GUI 视角 58 项 + t19 核心视角 40 项，两轮全量回归零新增失败 |
| 交付闸门 | 讨论组一致（t16 + t20 6/6 零反对）+ bug 测试员连续两轮复测无异常 —— 用户四要素全部满足 |
| 交付物 | `installer\Output\SWDM-Setup-1.3.9.exe` 42.67MB，版本号双端 1.3.9，冒烟 6 秒稳定 |
**recorder 投票：同意交付** ✅（四项逐条同意）
1. **U1-U12 逐条修复且无过度设计——同意**。12 项全部根因 + 修复 + 测试闭环（约 111 项新检查全 PASS）。无过度设计佐证：t15 用量化基线推翻任务预设（解析 4.5ms/页非瓶颈），优化只落在端点节流优先级礼让；t14 库分类只渲染 `game_name()` 不加分组树，最小可行实现。
2. **t16 决议执行符合——同意**。该收 8 项已在 t17 打包中体现；该延后项（A-P1 主修复 / B④调试 Tab / C②批量按钮 / D 间隔微调 / E④新功能）全部显式登记 t22，无遗忘风险。
3. **该加没加、影响基本功能的项——无**。t15 移交的 stop/retry 竞态属偶发 flaky（非用户场景稳定触发），已登记 t22；`services.py:78` 未传 api 致 CDN 几乎必然回退 steamcmd 的缺陷 1.3.9 即存在，t21 provider 抽象层会顺带修复，不影响本版基本功能。
4. **1.3.9 可交付——同意**。12 bug 全修 + 五方决议执行到位 + 双轮复测零新增失败 + 版本号双处同步 + changelog 可追溯 + 安装包冒烟通过，用户四要素闸门全部满足。

---

## 1.3.9 流水线表更新（t11–t16 完成）

| 任务 | 成员 | 状态 | 要点 |
|------|------|------|------|
| t11 | installer-fixer | ✅ completed | 托盘退出：`_do_real_quit()` 公共方法 + qApp.quit()，test_uninstall_fix 22/22 |
| t12 | search-fixer | ✅ completed/pass | 搜索 4 修：游戏输入识别/联想下拉/回车/标签精确过滤，test_game_search_fix 38/38 |
| t13 | gui-tester | ✅ completed/pass | GUI 3 修：切游戏标签清选中/设置页首行间距加固/删除双向信号联动，gui_sweep 116 项 |
| t14 | core-tester | ✅ completed | 核心 3 修：ProgressSmoother 滚动窗口/percent 字节判定/库 game_name 展示，test_download_stats 40/40 |
| t15 | gui-tester | ✅ completed/pass | 详情页性能：量化基线 4.5ms/页非瓶颈，优化落在端点节流优先级礼让，test_detail_perf 17/17 |
| t16 | installer-fixer | ✅ completed/pass | 讨论组 A-E 五方结论入 docs/feature_review_1.3.9.md，8 项决议待 t17 并入 |
| t17 | search-fixer | ✅ completed/pass | 打包 1.3.9：PyInstaller 330 文件 + ISCC，版本号双处 1.3.9，冒烟 6 秒稳定，安装包 42.67MB，t16 决议 8 项已并入 |
| t18 | gui-tester | ✅ completed/pass | 复测第一轮无异常：GUI/用户视角 42+16 项 ALL PASS，56 脚本 54 PASS / 2 既有非回归 |
| t19 | core-tester | ✅ completed | 复测第二轮无异常：核心视角 40 项 ALL PASS，与 t18 基线一致（verdict 字段为空，结论为无异常） |
| t20 | search-fixer | ✅ completed/pass | 交付评审 6/6 同意零反对，**1.3.9 正式交付**，闸门结论入 changelog 第六节 |

### 1.3.9 测试新增汇总（供 t18/t19 复测基线参考）
- `tests/test_game_search_fix.py`（t12）：38 项
- `tests/test_uninstall_fix.py`（t11）：16→22 项（+6 托盘退出用例）
- `tests/test_gui_sweep.py`（t13）：98→116 项（+18：u6 4 / u9 3 / u10 10 + 原有扩充）
- `tests/test_download_stats.py`（t14）：40 项
- `tests/test_detail_perf.py`（t15）：17 项
- 合计 1.3.9 新增约 111 项检查，全部 ALL PASS。

---

# SWDM 1.4.0 规划启动（与 1.3.9 并行，不阻塞打包）

> 启动时间：2026-09-28 22:00。用户要求自行接入 4 个下载 provider（steamwebAPI、GGNetwork、Nether、SWD）并迭代 1.4.0。

## 研究阶段（两个后台 subagent 并行）
- **a106b536**：联网调研 4 个 provider 的 API/认证/匿名可用性/速率限制 → `research/provider_research.md`。
- **fb41fe76**：读 SWDM 现有下载链路代码输出适配设计 → `research/provider_adaptation.md`。
- **现有架构线索**：`config.py:38` 通道配置、`settings_tab.py:146-151` channel_combo 下拉（steamcmd/cdn 两项硬编码）、`downloader.py:71/420-476` DownloadManager + CDN 通道 + 自动回退、`steamcmd_engine.py:109` 引擎、`cdn_downloader.py` 直链通道。
- **后续**：报告出来后按匿名可用性 + 接入成本建各 provider 实现任务（依赖 t21），再建 1.4.0 打包/双轮复测/交付评审流水线。

### a106b536 provider 实测调研完成（`research/provider_research.md`）
- **GGNetwork**：**唯一试点匿名可用**的第三方 provider。
- **steamwebapi.com**：**排除**——经济类 API（价格/商店数据），无工坊下载端点。
- **Nether**：**排除**——闭源账号爬虫，合规风险。
- **steamworkshop.download**：**低优先级，默认禁用兜底**。
- 结论：1.4.0 provider 实现任务将以 GGNetwork 为首发，其余视匿名可用性 + 接入成本决定。

### fb41fe76 适配设计完成｜22:23（`research/provider_adaptation.md`）
- **读码结论**：通道选择集中在 `downloader.py:476-494` `_exec_job`（`if channel=="cdn"` 二选一），入库链路对通道零感知（统一落地 `content/<appid>/<itemid>`）；进度协议已统一（`on_progress(pct, done, msg)` → ProgressSmoother）。
- **15 处硬编码清单**，含最脆的 `downloader.py:490` 用消息含"回退"二字判回退。
- **设计**：`swdm/core/providers/` 包（base ABC `DownloadProvider` + registry 链式回退，回退不消耗 auto_retry）；`cdn_downloader` 平迁为 `providers/cdn.py` 保留兼容门面；`steamcmd_engine` 不动，由 `providers/steamcmd.py` 包装。
- **发现的现存缺陷**：`services.py:78` 构造 `DownloadManager` 未传 api，CDN 通道几乎必然回退 steamcmd（此缺陷在 1.3.9 即存在，t21 实施时会顺带修复）。
- **最大风险**：第三方 provider 若返回压缩包而非原始 .gma，需先解压再按布局落地；建议 provider 声明 `supported_appids` 避免依赖链卡死。

## t21｜core-tester｜provider 抽象层 + GGNetwork 试点｜🔄 in_progress（t20 完成后已解锁）
- **范围（captain 2026-09-29 澄清）**：t21 **已包含 GGNetwork 试点实现**——`providers/ggnetwork.py` 与 providers/ 包架构、cdn 平迁、`services.py:78` 修复、config/settings 通道动态列表**一体交付**，不需要"t21 就绪后再建 provider 实现任务"。
- 输入：fb41fe76 的 `research/provider_adaptation.md` + a106b536 的 `research/provider_research.md`（GGNetwork 为唯一匿名可用试点）。
- 顺带修复现存缺陷：`services.py:78` 构造 `DownloadManager` 未传 api 致 CDN 几乎必然回退 steamcmd。

## t22｜search-fixer｜1.3.10 遗留项｜🔄 in_progress（独立推进）
- cancel 微秒窗口（`downloader.py:392-393`，需 pending-cancel 集合，>15 行涉状态机核心）
- 调试 Tab 默认隐藏（`win.debug_tab` 测试耦合）
- 批量按钮合并（暂停/继续单按钮，`_sync_batch_buttons`）
- GameSearch 间隔（t16 决议降到 0.6-0.8s + 熔断退避）
- steamcmd bytes=0 校验（`downloader.py:500-508`，<15 行——t16 决议 1.3.9 收，t17 已并入；若实际未并入则 t22 兜底）
- t15 移交的 stop/retry 竞态（`downloader.py:375-379` stop()→cancel_all() 与 531-541 自动重试再入队竞态）

## 1.4.0 流水线（t20 完成后已解锁）

| 任务 | 成员 | 状态 | 要点 |
|------|------|------|------|
| t21 | core-tester | ✅ completed | provider 抽象层+GGNetwork 试点：providers/ 六件套，test_providers 74 项 ALL PASS，run_all 59 脚本零新增失败 |
| t22 | search-fixer | ✅ completed | 1.3.10 遗留 7/7 收齐：A-P1 cancel 窗口正式修复 + 调试 Tab/批量按钮/间隔/竞态，43 项新测试 |
| t23 | installer-fixer | 🔄 in_progress | 讨论组评审进行中：search-fixer/core-tester/recorder 三方已表态，待 gui-tester |
| t24 | installer-fixer | ⏳ pending | 汇总验证、全量回归、打包 1.4.0（paths.py:9 + swdm.iss:14）、写变更记录 |
| t25 | gui-tester | ⏳ pending | bug 复测第一轮：用户视角验证 1.4.0 新增与回归（依赖 t24） |
| t26 | core-tester | ⏳ pending | bug 复测第二轮：核心视角独立复测（依赖 t24） |
| t27 | search-fixer | ⏳ pending | 交付评审：六方一致 + 零反对（依赖 t23+t24+t25+t26） |

## 依赖关系与人员安排说明（captain 2026-09-29 澄清）
- **t21 已包含 GGNetwork 试点实现**（`providers/ggnetwork.py` 与包架构/cdn 平迁/services.py:78 修复/通道动态列表一体交付）——不需要 t21 就绪后再建 provider 实现任务。
- **installer-fixer / gui-tester 保持空闲待命**：下一任务是 t23（讨论组，依赖 t21+t22）和 t25（复测，依赖 t24 打包）。t21 provider 接口未定前让它们提前写复测脚手架会返工，**不安排预备任务**。
- **t22 由 search-fixer 独立推进**。

### captain 澄清：t26/t27 早已存在（recorder 更正）｜10:45
- recorder 此前查询 team.json 时只过滤了 t21–t25，**漏读 t26/t27**，误报"流水线只有一轮复测、需补建 t26"。向 captain 确认后更正：**t26/t27 在建 1.4.0 流水线时已按 1.3.9 的 t18/t19 结构创建**。
- **完整五任务闸门（与 1.3.9 完全对齐）**：t23 讨论组一致 + t24 打包 + **t25（gui-tester，GUI/用户视角）+ t26（core-tester，核心视角）连续两轮复测无异常** + **t27（search-fixer，六方一致 + 零反对，依赖 t23+t24+t25+t26）**。
- recorder 的"连续两轮"要求**本就已被流水线满足**，无需补建；工程日志流水线表已补全 t26/t27 两行。

---

## t21 / t22 完成记录（补录）｜1.4.0 实施期

### t21｜core-tester｜provider 抽象层 + GGNetwork 试点｜✅ completed
- **providers/ 六件套**：`base.py`（ABC `DownloadProvider` + `ProviderMeta` + 通用件 `http_download` Range 续传/stop_event 轮询取消/429 上报 + `_session` 复用 SteamAPI session）、`registry.py`（`ProviderRegistry` 单例：注册 / `build_chain` 链构造 / 60s 探测缓存 / `_Circuit` 熔断 3 次失败冷却 60s 半开重熔 / `list_channels` UI 下拉）、`cdn.py`（自 `cdn_downloader.py` 平迁）、`steamcmd.py`（`terminal=True` 链终结者）、`ggnetwork.py`（匿名 PROXY 试点）。
- **downloader.py 链式回退**：terminal 语义、回退不消耗 auto_retry、`should_fallback()` 结构化判定（替代 1.3.9 的"消息含'回退'"字符串判定，`downloader.py:490` 硬编码消除）。
- **顺带修复**：`services.py:78` 补 `api=api`（CDN 通道几乎必然回退 steamcmd 的 1.3.9 缺陷）；config 通道化（`download.providers` 三层嵌套 `_merge`）；settings_tab `channel_combo` 由 `registry.list_channels()` 动态生成。
- **架构文档**：`docs/provider_architecture_1.4.0.md`（78 行），含通道清单（cdn priority 10 / ggnetwork 20 / steamcmd 100 链尾）、GGNetwork 要点（令牌桶 20/min+突发 3、zip 解压取 .gma、GMAD 弱校验 >1% 带 ⚠ 不回退）、关键设计决策（steamcmd 永远链尾且 terminal；默认通道=steamcmd 时链只有一条，行为与 1.3.9 一致）、1.4.0 后待办（EXTERNAL 占位 / steamworkshop.download 兜底未实现 / ggnetwork 探测固定 id 2537024972 / 端到端实网验证未做）。
- **测试**：`tests/test_providers.py` **74 项 ALL PASS**；全量 run_all 59 脚本 52 PASS / 7 FAIL（5 实网 DNS/超时环境失败已单独复现确认：`cdn.fastly.steamstatic.com getaddrinfo failed`、`steamcommunity.com connect timeout`；2 既有非回归 legacy_format/page_parser），**零新增失败**。
- **与 t22 交叉验证**：移除链循环顶部冗余 stop 判定与 steamcmd stop_event 拦截——A-P1 的 `_exec_job` 入口早退已覆盖取消场景，两人对同代码达成一致才动刀。
- **版本号**：1.4.0 留 t24 统一改（`paths.py:9` + `swdm.iss:14`）。
- **打包前置已验证**：providers/ 全静态 import（`registry.py:235-247` + `downloader.py:524`），无 `import_module` 动态导入，swdm.spec 无需改动即可收集新子包。

### t22｜search-fixer｜1.3.10 遗留项｜✅ completed（7/7）
- **A-P1 cancel 微秒窗口正式修复**（基于 t21 落地后的 `_exec_job` 结构）：
  - `downloader.py:108` 新增 `_cancelling` 集合；`cancel()` 在同一把锁内先 `add(_cancelling)` 再 `_stop.set()`（:272-274）——保证 worker 观察到 `_stop` 时 pending 标记已在
  - `_exec_job` 入链前早退：`_throttle_wait` 后若 `_stop` 已置位直接 `_retire_cancelled` 收尾，不进通道链（:594-599）
  - 终态判定块（:664-698）与 `cancel()` 的 add+set+pop+登记全程互斥串行：cancel 先行→取消胜出（不导入库/不自动重试/终态不被覆盖回成功）；worker 先行→真实结果保留（7g/7h 语义不变）
  - 自动重试的判定与重新入队并入同一锁块（cancel 无法插队复活已取消任务）；重试期间状态保持 RUNNING（7a 轮询语义，修复了初版误置 FAILED 致轮询方提前收队的回归）；失败退避在重试前记录
  - `retry()` 清除残留 pending 标记（:373）；新增 `_retire_cancelled()` 保证单次登记
- **其余 6 项**：B④ 调试 Tab 默认隐藏（config 默认 False + 条件 addTab + 设置开关，`debug_tab` 实例始终创建）；C② 暂停/继续合并单按钮（`_toggle_pause_all`）；D 间隔 0.7s + 熔断退避（连续 3 次失败或 ConnectionError 冷却 15s）；bytes=0 校验核对已落地；stop/retry 竞态由 core-tester 收掉（7g/7h）；test_v136 固件已修。
- **测试**：新增 `tests/test_ap1_cancel_race.py` **16 项**（3 场景确定性回归：cancel 抢注成功、入链前取消、标记清理后同 id 重试成功）+ `tests/test_t22_1310.py` **27 项**；回归 test_throttle（含 7a/7g/7h）、test_139_merge、test_download_fixes、test_core_sweep、test_download_stats、test_batch1-3、test_gui_sweep(118)、test_gui_offline、test_gui_fixes、test_cross_features、test_all_buttons、test_providers(74)、test_v136、test_uninstall_fix、test_engine_concurrency 全 ALL PASS。
- **全量回归**：59 脚本 46 PASS / 4 FAIL / 9 NORESULT，**0 新增失败**（4 FAIL = test_bulk_games + test_multi_game 本机代理出口 ConnectTimeout 纯环境 + legacy_format + page_parser 既有非回归；9 NORESULT = 8 实网超时 + 旧冒烟脚本本无 RESULT 行）。core-tester 独立 run_all 交叉确认结论一致。

---

## t23 讨论组评审记录（进行中）｜installer-fixer 主持

评审材料：`docs/provider_architecture_1.4.0.md` · `research/provider_research.md` · t22 改动清单 · 回归基线 59 脚本 52 PASS / 7 FAIL（5 实网代理不稳 + 2 既有非回归）/ 0 NORESULT，零新增失败

### search-fixer 表态｜10:29
- **A**：provider 抽象层**收**（未过度设计）；**EXTERNAL 占位删**（`base.py:29` 零引用死代码）
- **B1**：令牌桶 20/min **收**（~30/min 是 Valve 自家接口值，第三方代理应更保守，且可配置）
- **B2**：resolve 后立即下载已正确实现（`ggnetwork.py:143-156`）
- **B2b**：**queue.position 轮询是缺口**——`resolve()` 未读 queue 字段，建议 ≤5 行小修（position>0 直接返回空串干净回退 steamcmd，不轮询）
- **B3**：弱校验 1% 阈值**收**（zip 转存必然有 size 差异，硬失败误伤）
- **C**：匿名降级**收**（build_chain 跳过 + settings tooltip 到位）
- **D**：t22 四项全收干净并附证据
- **E**：**收（可交付）**，附两条收尾要求：B2b 小修 + GGNetwork 端到端真下载冒烟（本机代理超时从未实测，否则通道应默认禁用）；SWD 兜底延后不做（调研低增量价值）

### recorder 表态｜10:35
- **A**：抽象层**收**（ABC+registry+_Circuit+探测缓存是链式回退最小必要集，熔断是 1.3.7 O5 思路延伸）；**兼容门面保留是加分**（旧测试零改动、回归基线可比，1.4.1 可删）；**EXTERNAL 占位：留**（与 search-fixer 分歧——理由是 steamworkshop.download 调研已定低优先级兜底，占位是明确钩子零启用成本，建议 changelog 标注"占位未实现"即可）
- **B1**：20/min+突发 3 **不过保守，正确**（GGNetwork ToS §5.2.2 禁 excessive load；本机出口 IP 曾被限；社区安全速率 ~30 req/min，匿名第三方取 20 留余量）
- **B3**：弱校验**够稳健，但 ⚠ 只提示不落库是体感缺口**——建议 ⚠ 同时落库（mod 库元数据标记"曾触发体积告警"），事后可见，否则用户关弹窗信息就丢
- **C**：**收**，`is_configured()=False` 跳过 + steamcmd 链尾 terminal 是与 1.3.9 一致的关键正确性证明；建议 `list_channels()` 显示"未配置"状态而非隐藏（1.4.1）
- **D**：**全收**，A-P1 的取消令牌有序化（同锁 add 后 set + 入链前早退 + 终态块互斥）语义完备；t21/t22 交叉验证是高质量协作信号
- **E1**：**范围可控，无蔓延**——1.4.0 = t21 新增包（侵入点集中）+ t22 六项（全部 1.3.9 t16 登记的延后项，零新增）；三处克制证据写在架构文档第 7 节待办里
- **E2**：**无影响基本功能的该加未加**；两处体感提醒：① **GGNetwork 实网验证未完成**（匿名通道是 1.4.0 核心卖点，架构文档自陈需实测确认 20/min，5 个实网 FAIL 均为本机代理环境非产品缺陷，但端到端真实匿名下载从未跑通）——强烈建议 t25 复测含一次 GGNetwork 实网真下载，否则 changelog 须标注"匿名通道经离线 mock 验证，实网未经长时验证"；② ⚠ 不落库
- **E3**：**1.4.0 全部收，可交付**；延后 EXTERNAL / SWD 兜底 / 探测动态化（1.4.1+）；**删：无**
- **闸门安排**：目前流水线只见 t25 一轮复测，用户规则要求 **bug 测试员连续两轮复测**——建议 captain 补建 t26 复测第二轮（core 视角，对齐 1.3.9 的 t18/t19 结构）
- **回归口径提醒**：installer-fixer 基线 52 PASS/7 FAIL/0 NORESULT 与 t22 自跑 46 PASS/4 FAIL/9 NORESULT 分布不同——实网测试在本机环境不稳定（超时在 FAIL/NORESULT 间漂移）；建议 t24 以"零新增失败 + 既有非回归逐项核对"为准，不追绝对 PASS 数（1.3.9 口径）

### core-tester 表态｜10:31
- **A**：provider 架构**收**（ABC/Registry/`_Circuit` 真实复用），但建议**删三处死代码**：registry probe 缓存路径（UI 只调 `probe_results=False`，`build_chain` 不探测）、`downloader.py:442` `_download_via_cdn`（链改造后无调用方）、`ProviderKind.EXTERNAL` 占位（SWD 未实现）；`cdn_downloader.py` 门面建议测试迁移到 `providers.cdn` 后一并删除
- **B1**：令牌桶 20/min **收**——只限 resolve 的 POST 不限 CDN 传输，下载速度不受影响
- **B3**：**>1% 尺寸差异应从 ⚠ 升级为回退触发**——`should_fallback` 只看 FAILED，⚠ 在 SUCCESS 消息里不回退，坏包会误报成功
- **C**：匿名降级路径完整（cdn `is_configured` 恒 True → resolve FAILED + `_FALLBACK_HINT`）；默认通道与 1.3.9 逐字节一致（terminal 链尾 + `_run_steamcmd` 未动）
- **D**：A-P1 **收**（两临界区全程持 `_lock` 严格串行）
- **E**：**收，可交付**，零新增失败无体感退步；认领 5 项打包前小清理；诚实披露 ggnetwork 零实网端到端验证，建议 t24 打包前实网冒烟或 UI 标"实验性"

### 三方分歧裁决（installer-fixer 主持）｜10:40
- **EXTERNAL 占位：删**（search-fixer + core-tester 主张删 2:1，recorder 的"留"为少数；YAGNI 论证"真做时加回成本为零"成立，changelog 记录"占位按讨论组决议移除"）
- **⚠ 升级为回退触发 + 消息落库**（core-tester 的回退方案 + recorder 的落库建议统一：回退后 FAILED 消息自然带差异信息入库，事后可见）
- **门面 + `_download_via_cdn`**：`_download_via_cdn` 死方法删；门面文件倾向延后 1.4.1（等 core-tester 确认）
- **t26 第二轮复测**：recorder 提醒被采纳——写入 feature_review 决议表：t24 打包 + t25（GUI/用户视角）+ t26（核心视角）双轮无异常 + t23 讨论组一致 = 交付闸门；installer-fixer 将同步 captain 补建 t26
- **回归口径**：同意 recorder 建议——t24 以"零新增失败 + 既有非回归逐项核对"为准

**待收**：gui-tester 表态；收齐后出 `docs/feature_review_1.4.0.md`。

---

### t27 交付评审通过 + 1.4.0 正式交付｜2026-09-29 14:56 · recorder 记录

- t27（search-fixer 主持，attempt ff9b7f51）六方投票 **6/6 同意交付、零反对**：闸门四条件全部满足（t23+t27 讨论组一致 / t25 GUI 55 项 + t26 核心 45 项双轮复测无异常 / 版本号双端 1.4.0 + changelog 十节可追溯 / 两轮 run_all 61 脚本 59 PASS 零新增）。changelog 第九节回填完成。
- recorder 投票依据（以工程日志 + git 记录逐项核实）：三原则复核全同意（精简：t28 删 3 处死代码+门面延后 1.4.1；体感：默认通道 steamcmd 与 1.3.9 等价；基本功能：A-P1 正式修复+零新增失败）。
- 收尾提醒（已记入）：c172188（t25 产出）交付前需 captain 推送，使远程 main 与交付凭据一致。

### t30 源码注释与 docstring 中英文适配（1.4.1 首项）｜2026-09-29 · recorder 执行

- **范围**：`swdm/` 全部 40 个 `.py` 模块级 docstring 英化（英文为主 + 关键业务术语中文括注，如 `Steam Workshop (工坊)`、`前置依赖`、`链尾兜底`）；补齐 30 处缺失的公共 API docstring；`docs/git_workflow.md` 第五节扩写为完整注释语言规范（语言分工表 + docstring 内容要求 + t30 落地范围）；`docs/provider_architecture_1.4.0.md`、`docs/打包说明.md`、`docs/changelog_1.4.0.md`、`docs/project_structure.md` 补英文摘要段；README 双语补 1.4.1 路线小节。
- **原则执行**：只改注释/docstring/文档，**未改任何可执行逻辑**；依赖 `git diff --stat` 与 compileall 双重确认。
- **验证**：关键回归 test_providers / test_download_fixes / test_core_sweep / test_gui_sweep / test_throttle / test_all_buttons / test_cross_features 全部 ALL PASS；直跑 pwsh 时需带 `PYTHONUTF8=1`，否则 ⚠/✓ 字符在 GBK 控制台 print 假崩（显示层问题，非代码缺陷）。
- **诚实记录**：deps_parser.py docstring 替换时出现过一次重复头残留（edit 工具尾部空白匹配失败），用临时 python 脚本按行切除并 ast.parse 校验修复，脚本用后即删。

---

## 1.4.1 迭代记录（t29–t42）｜2026-09-29 → 2026-09-30

> 组织方式同前：每条含任务编号/成员/改动要点/文件/结论。t30 已在上节记录，此处不重复。
> 1.4.1 十功能项 t32–t41 全部完成并逐项收口；t42 手册为代码冻结后收尾项；打包闸门 t43–t46 在 2026-09-30 代码冻结期执行。

### t29｜git 仓库维护 + 项目文档基建｜2026-09-29 · recorder

- **改动**：`docs/git_workflow.md`（提交规范：类型/范围/摘要/必填 tXX 编号；main 单线；推送分工；.gitignore 维护；中英文适配政策）；`docs/project_structure.md`（全 40 个 `.py` 逐文件职责索引，读源码 grep class/def 签名后写，含迭代溯源 t1–t28）；`README.en.md` + `README.md` 双语互链，中文版对齐 1.4.0（补 providers/ 架构树与多通道链章节）。
- **结论**：三交付物本地提交 commit 6e88510（待 captain 推送）。无逻辑改动。

### t31｜并行讨论组：1.4.1 功能删减/改进/添加可行性评审｜2026-09-29 · installer-fixer 主持（attempt 7a68a501）

- **任务**：12 项候选清单评审，五方逐条裁决，零原则性反对。
- **结论**：**纳入 10 项**（A1 用户手册 / A2 QSS / A3 README 改进后 / B1 详情磁盘缓存 P0 / B2 预取下一页 P0 / B3 剪贴板入队 P0 含 B5 并入 / C1 库更新检查 / C2 失败原因枚举 / C3 私人账户 provider / C5 GGNetwork 补测**最先**）；**延后 1.4.2 三项**（A4 图标 / C4 集合下载 / S5 缩略图缓存）；**砍 0 项**。时序：C5 最先（结论驱动去留 + 反影响 C2/C4）→ B1/B2/B3+A2+C1+C3 并行 → A1（代码冻结后）+ C2 收尾 → A3 随时。
- **产出**：`docs/feature_review_1.4.1.md`（8 节）。两处计划外提问裁决：B5 并入 B3；S5 延后并要求 plan 补写理由；1.4.0 changelog 遗留 5 项折叠为技术债（见 t36/t40 收口）。

### t32｜C5 GGNetwork 真下载补测 + 后端登录态探测｜2026-09-29 · search-fixer（attempt 2 e8701a76）

- **改动**：`swdm/core/providers/ggnetwork.py` resolve() url 优先语义（position>0 且无 url 才回退；原守卫与实测语义相反——成功响应都同时带 position=1 与有效 url）+ api 返回的 url 是 HTML 落地页，须改写为 cdn.ggntw.com；探测物品轮换（原固定 id 2537024972 已被 Steam 删除，换可轮换探测）。
- **结论**：**推翻 1.4.0「本机做不了」前提**——api/cdn.ggntw.com 本机直连可用（不受 steamcommunity fake-IP/SNI 阻断），该判断只适用于 steamcommunity。live E2E 通过（160250458 → 20685180 字节 .gma，GMAD 校验，delta=0）。后端对公开内容匿名开放，风险维持 🟡 不上调（受限 App 样本 0）。两个严重 bug 使该通道自 1.4.0 起从未实际生效（默认链不经过，用户无感知）。
- **产出**：`docs/ggnetwork_retest_1.4.1.md`。

### t33｜B1 详情页磁盘缓存（TTL + time_updated 双失效）｜2026-09-29 · core-tester（attempt 2 b3936bbd，前次产出已并入树 + 本轮验证收口）

- **改动**：`swdm/core/detail_cache.py`（新建：get/put/invalidate，命中 `copy.deepcopy(html)` 延伸深拷贝保护到磁盘层，`os.replace` 原子写，JSON 非法/缺字段/文件缺失全当 miss 并清理）；`swdm/gui/settings_tab.py` 开关 + QSpinBox TTL（0–720 小时，0=关闭该层）+ 「🧹 立即清除全部详情缓存」；config `network.detail_cache_enabled`(True) / `detail_cache_ttl_hours`(24)；time_updated 不一致立即判 miss 并物理删除；详情弹窗「🔄 刷新」→ `_refresh_detail` 清内存条目 + force_refresh=True 重建 worker（手动刷新 bypass）。
- **测试**：`tests/test_t33_detail_cache.py` 33 项 ALL PASS（四硬约束逐条：深拷贝/双失效可配/损坏容忍/手动 bypass）。
- **结论**：全量 64 脚本 62 PASS / 2 FAIL（bulk_games 实网 + legacy_format 既有 flake），零代码回归；测试侧修正 test_core_sweep `_bare_api()` 补 CircuitBreaker 与 test_rettest_140 C3b 改公开 API（t34 委托后的迁移）。

### t34｜B2 预取下一页入 _page_cache｜2026-09-29 · core-tester（attempt 2）

- **改动**：`swdm/core/circuit.py`（新建 CircuitBreaker：连续 3 次失败或 `requests.ConnectionError` → 冷却 15s，record_success 只重置 streak 忠实 t22 语义，线程安全）；`swdm/core/game_search.py` 与 `swdm/core/steam_api.py` 熔断逻辑委托 CircuitBreaker（browse 挂独立 _browse_breaker，语义不变）；`swdm/gui/workshop_tab.py` `_schedule_prefetch_next_page`（800ms 单次 QTimer + daemon `threading.Thread` 直调 `api.browse(page+1)` 只暖缓存从不渲染；守卫链：去重 → _priority_pending>0 礼让 → 熔断冷却跳过 → appid 空 → 代际再校验 → ApiCache 已有 key 跳过；缓存键与 browse() 内部完全一致）。
- **关键修复**：首发 BrowseWorker(QThread) 版本导致 test_gui_sweep 在 run_all 内进程挂死（非守护 QThread + fake-IP 代理黑洞网络请求阻塞解释器退出）→ 改 daemon 线程根治且更精简。
- **测试**：`tests/test_t34_nextpage_prefetch.py` 25 项 ALL PASS；全量（合并 t34+t35+t41 终态树）**64 脚本 64 PASS / 0 FAIL / 0 NORESULT 历史首次**。

### t35｜B3 剪贴板监听入队 + B5 批量粘贴导入｜2026-09-29 · gui-tester（attempt 3）

- **改动**：`swdm/gui/main_window.py` `_start_clipboard_watch`（config `general.clipboard_watch` 默认开；复制工坊物品链接或纯物品 ID 自动解析入队，只在内容匹配时解析、不记录/缓存剪贴板内容）；`swdm/gui/workshop_tab.py` **⋯ 更多** 菜单「🔗 批量粘贴导入…」（B5 批量链接/ID 一次入队）；搜索冷却自动重发（t16 登记的技术债并入：连续快速搜索时自动合并稍后重发）。
- **测试**：`tests/test_b3_clipboard.py` ALL PASS。与 t34/t41 合并树回归 64/64。

### t36｜A2 QSS 界面美化 P1–P5 + B6 空状态引导 + 技术债 ①②｜2026-09-29 · gui-tester（attempt 2 b99117e8）

- **改动**：`swdm/gui/styles.py` 与各 Tab——P1 滚动条（handle 描边 + pressed 态，dark/light 双主题纵横双向）；P2 表头（min-height 24px + hover/pressed + 右分隔线，只动 QHeaderView::section）；P3 进度条（`[status="done"]` 绿 / `[status="failed"]` 红，downloads_tab 终态 setProperty + unpolish/polish 重绘）；P4 跟随系统（`qss("auto")` 走 `QGuiApplication.styleHints().colorScheme`，MainWindow._watch_system_theme 标志位增减连接避免 disconnect RuntimeWarning，设置页下拉加「跟随系统」，**主题切换不再要求重启**）；P5/B6 空态（库空→「前往工坊浏览」、有库筛选空→「清除筛选条件」、下载空队列→「前往工坊浏览」，navigate_requested→MainWindow._goto_workshop_tab）。
- **技术债**：① registry.list_channels 经 _credential_state 返回 NO_KEY 时设置页标签「（未配置，链内自动跳过）」；② `test_page_parser` 夹具改 requiredtags[] 表单控件形态 + `test_legacy_format` 网络感知重写（live 对 API file_size 硬断言 / 离线 SKIP）。
- **测试**：`tests/test_qss_p1_p5.py`（新，36 项）+ gui_sweep/gui_offline/all_buttons/cross_features/rettest_140(55)/t22_1310(27)/providers(84)/page_parser/legacy_format 全 ALL PASS；**run_all.ps1 63/63 PASS 零失败（历史首次）**；compileall exit 0。

### t37｜C1 mod 库更新检查（time_updated 比对，手动按钮版）｜2026-09-29/30 · core-tester（attempt 3 收口）

- **改动**：`swdm/core/steam_api.py:446` `check_updates(records, progress, cancel)`（批量比对 time_updated，**50 条/批**，每批前 `_endpoint_throttle("/ISteamRemoteStorage/", priority=False)`；经 `get_file_details→_api_post` **直连不经 api_cache**（比对的永远是 Steam 当前值）；单批异常当该批判未知跳过不传播不误标；无快照 tu=0 跳过）；`steam_api.py:307-316` `_ENDPOINT_INTERVALS` 新增 `"/ISteamRemoteStorage/": 3.0`；`swdm/gui/library_tab.py` 「🔍 检查更新」按钮 → daemon 线程（防 UI 卡死 + 防重入）→ progress 经 QMetaObject.invokeMethod 回 GUI 线程实时改按钮文本「🔍 检查中 x/y」→ `_populate` 标红（🔄 前缀 + 红色，灰色不覆盖标红）→ QMessageBox 询问「现在加入下载队列？」→ 同意后从库记录重建 WorkshopItem 走 `svc.downloader.enqueue` 标准队列（**downloader.py 零改动**）→ 入队后清标红。
- **四硬约束**：bypass api_cache / 大库进度反馈（500 条分 10 批 U6/U6b/U6c + cancel 中止 U7）/ 首版只标红+一键入队（V3/V4/V5/V9）/ 批 50 + 批复用端点基准（U3/U6）。
- **测试**：`tests/test_t37_lib_updates.py` 34 项 ALL PASS（U 核心 15 + V GUI 19）。全量 66 脚本 62 PASS / 4 FAIL 全实网环境（零代码回归）。
- **后续**（captain 2026-09-30 16:33 裁决）：UX 审计发现 A6——`library_tab.py:398-401` `Q_ARG(list)` 完成回调失效致 C1 端到端卡死（Q_ARG 对裸 list 类型不工作，int 正常）——并入 t43 打包前修复；U3 检查更新取消死代码（按钮禁用 + `_check_cancel` 恒 False）入 1.4.2 修复池。t44 复测须覆盖真实线程路径（daemon worker → `_on_check_updates_done` 完整回调，t37 测试盲区：原先直调收尾绕过）。

### t38｜C3 私人账户 provider（steamcmd +login）｜2026-09-29 · search-fixer（attempt 3 ac30a39d）

- **架构**：`swdm/core/providers/account_steamcmd.py`（新建：display_name「SteamCMD（私人账号·自己有权内容）」，**默认链不含**——build_chain 断言保证；匿名态/会话级失活时与「未配置凭据」同等待遇被跳过）。共享/兜底引擎**恒匿名** + 账号专属引擎（services.refresh_engine 不再下发凭据；账号路径经 `_run_steamcmd(engine=专属引擎)` 共用串行锁，两 steamcmd 进程永不并发）；settings `_login_engine_factory` 测试登录现场造带凭据引擎测完即弃。
- **四风控**：①凭据本地存储等级明示（keyring 优先 + 本地混淆回退；不进日志/不进导出包/不上传任何服务器，匿名模式零收集）；②登录失败且疑似 Steam Guard 时弹验证码入口并提示「仅需一次」（本机验证成功后 steamcmd 缓存 sentry）；③账号问题不阻塞兜底下载（共享引擎恒匿名，结构上不可能阻塞）；④会话级失活（账号 provider 失败后与未配置同等待遇）。
- **产出**：`docs/c3_account_provider_1.4.1.md`。设置页「Steam 账号（登录方式）」切手动登录即出现该通道。

### t39｜A3 README 截图 + badge 墙 + 能力清单 + 已知限制｜2026-09-29 · installer-fixer（attempt 91d476a3）

- **改动**：badge 墙 7 枚 shields.io 静态 SVG（双语 README 同步）；`tools/make_readme_shots.py` 固定夹具数据 offscreen 渲染 4 张 1280x800 PNG（workshop/downloads/library/settings），脚本 RESULT: ALL PASS；「功能速览」能力清单四分组共 18 条（双语同步）；已知限制 4→5 条（补受限 App 需自有账号的诚实披露 + 1.4.2 排期）。未改任何业务代码。
- **诚实披露**：成图需人工目检（本机读图工具不可用——sharp ERR_DLOPEN_FAILED / modlens key invalid），已在 README 注明，延后 1.4.1 交付前由用户目检。

### t40｜技术债：cdn_downloader.py 门面移除｜2026-09-29 · installer-fixer（attempt 2 e46df9a6）

- **改动**：`swdm/core/cdn_downloader.py` 门面文件删除（生产代码零引用）；3 个测试迁 CDNProvider 直连 API——`tests/test_cdn.py`（download_file→http_download、download_item_cdn→download、resolve_file_url→resolve）、`tests/test_core_sweep.py` 第 5 节（206 续传/200 重写/403/匿名空直链 5 项）、`tests/test_providers.py` 第 11 节（test_compat_facade→test_cdn_provider_direct）。三者 RESULT 全 PASS。

### t41｜C2 item 级失败原因枚举 + 受限物品提示登录｜2026-09-29 · search-fixer（attempt 2）

- **改动**：`swdm/core/failure_reason.py`（新建，纯函数）：8 桶分类——DISK_FULL / EMPTY_SUCCESS（E③ 报 SUCCESS 但 0 字节）/ RATE_LIMITED / NETWORK / LOGIN_FAILED（凭据，与所有权区分）/ ITEM_GONE / ACCOUNT_NEEDED（仅两条正向信号支持）/ GENERIC（**兜底红线**：不区分权限/网络/限流）。判定顺序保证 steamcmd 通用 I/O 串（`ERROR! I/O Operation Failed` / `Failed to download item` / `Not Logged In` 除外）不误判为 ACCOUNT_NEEDED（误报教训：#13474 论证 steamcmd I/O 失败确实不区分原因）；`render_failure` 渲染用户可读文案（登录引导但不承诺因果）。downloader 终态路径调用 classify_failure/render_failure 填 job.message（下载页「信息」列）。
- **产出**：`docs/c2_failure_reason_1.4.1.md`。

### t42｜A1 用户手册（代码冻结后写）｜2026-09-30 · scribe（attempt 8 d7f1ead4-0b9b-4974-9e09-3dcb9b3bbf91）

- **任务**：界面状态随实现漂移，文档骗人比没有更伤——故代码冻结后写。
- **交付物（五）**：
  1. `docs/manual/SWDM用户手册.md`（27KB）——九章中文（0 扉页版本+日期+许可证 / 1 快速上手 5 步 / 2 核心概念（AppID vs publishedfileid、provider 链与回退、匿名与私人账号、mod 包、依赖、冲突）/ 3 工坊浏览 / 4 下载队列 / 5 模组库 / 6 设置 / 7 调试 / 8 故障排查 FAQ（429/403、steamcmd 失败、缺依赖、解包失败、中文路径）/ 9 帮我们改进），任务导向编号步骤，**界面状态以冻结后实测为准**（调试 Tab 开关重启生效、暂停/继续合并单按钮、通道下拉动态生成+可用性标注、C3 设置页登录方式切换、C2 八桶文案逐条对 `failure_reason.render_failure` 原文核对）；扉页 **版本 1.4.1** 绑定声明 + 与 `../changelog_1.4.1.md` 互链。
  2. `docs/manual/images/manual-*.png` ×5——固定夹具 offscreen 截图（`tools/make_manual_shots.py`：工坊搜索+标签 / 详情弹窗含依赖+冲突+评论 / 下载队列进行中+排队+C2 失败行 / 库页 C1 标红 / 设置页全展开），RESULT: ALL PASS。
  3. `tools/build_manual.py`——markdown 3.11 → 单文件 HTML（CSS 内联 + 5 图 base64 内嵌）+ 无头 Edge 打印 PDF；锚点解析/图片内嵌/扉页版本声明三重校验 RESULT: ALL PASS。坑：python-markdown 默认 slugify 经 NFKD+ascii encode **丢弃全部中文**，不能用于 CJK 锚点——改自定义 unicode 保留 slug 与手写目录链接同规则。
  4. dist 产物：`docs/manual/dist/SWDM-用户手册.html`（137373B）+ `.pdf`（1338193B）。
  5. `tests/test_manual.py`（入 run_all）：11 项断言 + 1 项 SKIP 全 PASS（源文件/扉页版本==APP_VERSION/5 图存在/目录锚点/HTML 文档头+内嵌 5 图/PDF 非空）；**帮助入口检查在 `main_window.py` 出现「用户手册」字样（packager 接线后）自动转硬断言**。
- **诚实披露**：读图工具本机不可用，5 截图仅验证生成不崩溃+尺寸非零，**交付前需人工目检**（同 t39 口径）。
- **验证**：make_manual_shots 5/5 PASS；build_manual ALL PASS（两轮）；test_manual ALL PASS（两轮）；compileall swdm+tests+tools exit 0。run_all 全量在 test_bulk_games 实网挂起（既有代理失效环境问题）后终止，全套件验证属 t43 闸门。

---

## 成员换血事件（路由失效）｜2026-09-30 15:51 · scribe 记录

- **事件**：会话模型从 atria-asi 切到 duanyan/Atria-Dawn-Preview 后，AgentTeams 5 名成员仍挂在失效的 atria-asi 路由，t42/t43 连续失败报 `no adapter registered for provider atria-asi`（重试无效，确认路由级故障）。
- **处置**：移除全部 5 名旧成员（installer-fixer / recorder / search-fixer / gui-tester / core-tester，**名称不可复用**），以新名称重新添加 5 名（**packager**（安装包与进程清理专家）/ **scribe**（工程记录员与信息中枢）/ **fixer**（搜索与下载链修复）/ **gui-checker**（GUI 功能测试）/ **core-checker**（核心逻辑测试）），秉承 captain 当前 duanyan 路由（duanyan 不支持 reasoning_effort=max，添加时须省略）。
- **角色错配修正**：新成员自动从池中认领任务导致角色错配（认领与角色不符），用 fixer 做中转三步交换回正确归属。
- **工程启示**（已落项目记忆）：①换模型路由后 AgentTeams 成员路由不会自动更新，需**移除+重新添加**（名称需更换）；②`add_member` 自动认领池中任务可能与角色错配，需手动交换；③闸门链重派：t42 手册→scribe（第 8 次尝试）、t43 打包 1.4.1→packager（第 7 次）、t44 GUI 复测→gui-checker、t45 核心复测→core-checker、t46 六方评审→fixer；t44/t45 等 t43，t46 等 t44+t45。间歇性后台 subagent 失败消息是旧成员会话死亡回响，无影响。

---

## 打包闸门期事件（只读审计 + 裁决）｜2026-09-30 16:12–16:33 · scribe 记录

- captain 并行调度铺开（1.4.1 代码冻结期，全部只读/文档/调研，不污染交付）：scribe 认领 t47（本条）+ 3 个只读审计 subagent 并行：核心静态审计、UX+手册一致性核对、竞品新一轮调研（用户级规则要求的定期调研，服务 1.4.2 规划）。
- **UX 一致性审计结论**：手册 E11 发布阻塞（三处链接 `docs/changelog_1.4.1.md` 不存在，**packager 创建 changelog 即解**）；UX 候选 13 条（P0×4：工坊页中央空态 / 清除已完成实清失败行 / 检查更新不可取消 / 勾选入队不清空）；U3=t37 契约「可取消」在 UI 层是死代码（`library_tab.py:174/382` `_check_cancel` 恒 False、按钮禁用），已并入 t44 必检与 t46 评审议程。
- **核心审计**：`docs/core_audit_1.4.2.md` —— P0×4（`throttle.py:86` 退避等级无 clamp，`2.0**1024` 溢出击穿工作线程→队列死锁，夜间挂机+死网可达；`downloader.py:305` cancel() 杀错引擎，账号通道子进程不被中断；steamcmd_engine 测试登录绕过 `_engine_lock` 与下载竞态；AdaptiveConcurrency._max 构造时固化致并发配置永不生效）+ P1×3 + P2×9 + P3×13，修复集约 1–1.5 人日建议 1.4.2；**确认无误报保护项**（A-P1 竞态闭环 / 深拷贝三路径 / 零除 guards / 路径穿越防御 / 凭据四风控，不得误改）。
- **运营教训**：AgentTeams 运行态 edit_plan 会因历史任务 assignee 指向已移除成员而整体校验失败（`task t1 assignee not an active member`），此时改用持久消息向成员追加任务范围；已建 t48（scribe，deps t47）修手册勘误+重构建。
- **captain 裁决 16:33**：① A6（`library_tab.py:398-401` `Q_ARG(list)` 完成回调失效，致 C1 端到端卡死）**修在 1.4.1 打包前**，并入 packager 的 t43 范围（参照 1.3.8 t9 议题并入打包先例）；理由：C1 是 1.4.1 十主功能之一，端到端失效违反「保证基本功能正常运行」。② U3 与「最大并发下载配置静默失败」→ 1.4.2 修复池（core_audit P0-4 / ux_audit U3 已收）；理由：两者核心契约层工作正常，属 UI 可达性/配置传播增强。③ t44 复测要求：三项结论正式写入 `docs/retest_round1_gui_1.4.1.md`；A6 修复后必须覆盖真实线程路径；`tests/test_t44_retest_gui.py` A6 组与 `test_qarg_list_repro.py` 需在修复落地后同步改为断言修复后行为（当前断言 buggy 行为，修复会 FAIL）。

---

## 1.4.1 交付文档索引｜2026-09-30 · scribe 整理

| 文档 | 产出任务/成员 | 位置与说明 |
|---|---|---|
| 1.4.1 变更记录 | t43 packager | `docs/changelog_1.4.1.md`（打包闸门产出；覆盖 t32 C5 / t33 B1 / t34 B2 / t35 B3+B5 / t36 A2+B6 / t37 C1 / t38 C3 / t39 A3 / t40 技术债 / t41 C2 / t42 手册，每条带任务编号与文件） |
| 用户手册 | t42 scribe | `docs/manual/SWDM用户手册.md`（单一事实源）+ `docs/manual/images/`（5 截图）+ `docs/manual/dist/`（构建产物 SWDM-用户手册.html/.pdf） |
| 功能评审记录 | t31 installer-fixer | `docs/feature_review_1.4.1.md`（8 节，12 项裁决） |
| C5 补测报告 | t32 search-fixer | `docs/ggnetwork_retest_1.4.1.md` |
| C2 失败枚举设计 | t41 search-fixer | `docs/c2_failure_reason_1.4.1.md` |
| C3 私人账户设计 | t38 search-fixer | `docs/c3_account_provider_1.4.1.md` |
| 复测报告（GUI 第一轮） | t44 gui-checker | `docs/retest_round1_gui_1.4.1.md`（**产出后由 t44 成员补入本索引**） |
| 复测报告（核心第二轮） | t45 core-checker | `docs/retest_round2_core_1.4.1.md`（**产出后由 t45 成员补入本索引**） |
| 核心审计（1.4.2 输入） | captain 只读审计 | `docs/core_audit_1.4.2.md` |
| 竞品调研（1.4.2 输入） | captain 只读审计 | 见 captain 调度记录（服务 1.4.2 规划） |

> 历史版本文档索引延续：1.3.8/1.3.9/1.4.0 各 changelog + 复测报告 + feature_review 同目录，本日志既有段落可追溯。

---

## 1.4.1 交付闸门链（t43–t46）全记录｜2026-09-30 · scribe 收口（captain 指令）

> **1.4.1 正式交付**（t46 六方评审 6/6 同意、零反对，闸门通过）：`installer\Output\SWDM-Setup-1.4.1.exe` 45.5MB（47756369B），版本号双端 1.4.1，tag v1.4.1 由 captain 同步提交。

### t43｜打包 1.4.1 + A6 修复 + 帮助菜单接线 + 手册随包｜2026-09-30 · captain 接管

- **背景**：packager 连续尝试未收口，captain 直接接管打包任务（参照 1.3.8 t5/t17 先例：打包终态由最具上下文者执行）。
- **A6 修复（并入打包前，1.4.1 范围内）**：`swdm/gui/library_tab.py` 新增 `updates_checked = Signal(list)`——**用 Qt Signal(list) 替代 `Q_ARG(list)` 的 invokeMethod 投递**（bare list 在 PySide6 无 QMetaType，`QMetaObject.invokeMethod` 抛 RuntimeError，致 t37 C1「检查更新」完成回调永不触发、端到端卡死；同文件 `records_removed = Signal(list)` 同类模式已在 t13 验证可行）。修复后 C1 链路 daemon worker → `updates_checked` → `_on_check_updates_done` 全通（t44 复测覆盖真实线程路径，堵住 t37 测试盲区——原测试直调收尾绕过回调）。
- **帮助菜单接线（A1/t42 收尾）**：`swdm/gui/main_window.py` 新增菜单栏「帮助(&H)」→「用户手册(&M)」（`self.manual_action`，打开随包单文件 HTML，缺 HTML 时回退 PDF，均无才报错）。**t42 设计的自启断言生效**：`tests/test_manual.py` 探测 `main_window.py` 含「用户手册」字样后，帮助入口检查由 SKIP 转为硬断言（动作存在 + 目标文件存在）。
- **版本 bump + 手册随包**：版本号双端 1.4.1（`paths.py` APP_VERSION + `swdm.iss` SWDMVersion，AppVersion/VersionInfoVersion/OutputBaseFilename 联动）；PyInstaller 打入 `docs/manual/dist/` 两文件至 `build\dist\SWDM\_internal\manual\`（HTML + PDF），MD5 与 dist 一致（`ABB3462D736BB7FA046D93FCA589A32A`，t48 勘误已并入终态，scribe 独立复验）。
- **打包**：PyInstaller → ISCC → `installer\Output\SWDM-Setup-1.4.1.exe` 45.5MB；全量回归 88 脚本 87 PASS / 1 FAIL（实网环境性）。
- **changelog**：`docs/changelog_1.4.1.md` 十六节落盘（t32-t42 全部功能 + 技术债 + A6 + §十四汇总验证与全量回归 + §十五已知限制与下一步 + §十六评审记录），手册三处互链自通。

### t44｜bug 复测第一轮：用户视角验证 1.4.1｜gui-checker

- 56 + 30 项检查 ALL PASS（`tests/test_t44_retest_gui.py`，含 A6 修复后真实线程路径复测）；exe 冒烟运行 10 秒存活、标题栏 v1.4.1。
- 特征化确认两项 1.4.2 候选属实（非阻塞，captain 16:33 裁决归 1.4.2 修复池）：**U3**「检查更新取消」UI 层死代码（`library_tab.py` 按钮禁用 + `_check_cancel` 恒 False）；**P0-4** 最大并发下载配置静默失败（`AdaptiveConcurrency._max` 构造时固化）。
- 结论落 `docs/retest_round1_gui_1.4.1.md`。

### t45｜bug 复测第二轮：核心逻辑独立复测｜core-checker（attempt 8d9b412a）

- **111 项独立检查 ALL PASS**（`tests/test_t45_retest.py`）+ **skip 基线全量回归 69/69**（零新增失败）+ 已知 flake（`test_bulk_games`/`test_multi_game`/`test_page_content` 实网、`test_legacy_format` mock 漂移）单跑确认环境性。
- **三项测试基础设施修复**（使 69/69 稳定可复现）：
  1. **run_all.ps1 编码脚阱**：UTF-8 无 BOM 脚本在旧版 PowerShell 下中文字符被 GBK 误解，污染紧邻的 `$skip` 赋值行——**注释行被吞进 `$skip` 数组、skip 列表静默失效**（实网脚本被全数纳入回归）。修复：脚本头部明确编码声明并隔离注释与赋值（现 `$skip` 含 `test_bulk_games`/`test_multi_game`/`test_page_content` 等 21 项）；
  2. **sys.path 补行**：脚本式测试在仓库根外运行时找不到包，统一补 `sys.path.insert`；
  3. **`os._exit(0)` 规避 teardown 崩溃**：Windows 下 Qt 线程拆卸偶发 `-1073740791` 硬崩溃会丢失 stdout RESULT 行（t3 起已知的判定标准问题）——关键判定路径在 Qt 拆卸前以 `os._exit(0)` 显式退出保住 RESULT 行（t42 条目记录的 flush=True 是同一问题的另一层防御）。
- 结论落 `docs/retest_round2_core_1.4.1.md`。

### t46｜六方交付评审：一致通过 1.4.1｜fixer 主持（attempt 40372c6c）

- **六方投票 6/6 同意、零反对**：fixer（主持）+ captain + packager + scribe + gui-checker + core-checker。scribe 投票依据（独立核验、非引用主持方数据）：随包手册 MD5 = dist MD5、版本号双端 1.4.1、changelog 互链可达；四要素逐项满足。
- **三项补充议程裁决**：
  1. **U3 + P0-4 归 1.4.2 修复池**：t44 特征化确认属实但核心契约层工作正常，属 UI 可达性/配置传播增强；changelog §15 已记录、t49 草案已收 P0 → 1.4.1 按现状交付；
  2. **三份 1.4.2 输入报告分发确认完成**（core_audit / ux_audit / 竞品+用户需求，见下索引）；
  3. **手册勘误 MD5 验证并入**：t48 的 16 条勘误经随包 HTML MD5 比对确认在打包终态（scribe 独立复验一致）。
- **诚实披露（非阻塞）**：GGNetwork 受限 App 样本未取得（风险维持 🟡）；offscreen 不验托盘态/真实剪贴板（t42 人工清单 5 条）；5 张截图需交付用户前人工目检（读图工具不可用）；U3/P0-4 入 1.4.2。
- 评审记录写入 `docs/changelog_1.4.1.md` 第十六节（§十四回填三组回归统计：t43 88/87/1、t44 89/87/2、t45 69/0/0 零新增）。

### 1.4.2 规划输入索引（本轮用户新指令的四份调研）｜2026-09-30 · scribe 登记

| 文档 | 位置 | 性质与用途 |
|---|---|---|
| 1.4.2「建议纳入池」实现预研 | `docs/research/plan_1.4.2_impl.md` | 方案预研（技术方案与工作量细化，不写代码）；对接 t49 草案（含 U3/P0-4 + 功能评审延后项 A4/C4/S5） |
| 竞品精读：sefrawe/Steam-Workshop-Mod-Assistant-Management-Tool | `docs/research/sefrawe_backup_verify.md` | 竞品实现逻辑与备份校验机制精读（Python 3.12+PySide6、steamcmd 单源架构） |
| 竞品精读：Streamline Workshop Downloader 三大 UX 机制 | `docs/research/streamline_ux.md` | UX 机制对标（用户级规则：主动定期竞品调研） |
| SWDM 用户真实需求调研 | `docs/research/user_needs.md` | 竞品 GitHub Issues 只读抓取 + 中文社区检索（B站/贴吧/CSDN/搜狐/迅游/游戏媒体）+ Steam/Valve 官方动态；数据截至 2026-09-30 |

> 与既有 1.4.2 输入合流：`docs/core_audit_1.4.2.md`（核心静态审计 P0×4 等）、`docs/ux_audit_1.4.2.md`（UX 审计 U1–U13 + 手册勘误 E1–E16）、`docs/feature_review_1.4.1.md`（延后三项裁决）。1.4.2 规划按三原则（精简 / 用户体感 / 基本功能）评审去留。
