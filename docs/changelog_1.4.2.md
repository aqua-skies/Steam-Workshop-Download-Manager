# SWDM 1.4.2 变更记录

> **English summary**: 1.4.2 is the interaction-layer iteration. Five user-reported bugs in the game-search bar are fixed at the root cause and verified by real QTest key simulation (17/17): crash on wrong-name Enter, "game not found" after selecting a suggestion, Backspace deleting only one character, Chinese↔English game-name matching (饥荒 ↔ Don't Starve), and missing feedback on every operation. Behind those: a new suggestion engine (QCompleter replacing combo clear/rebuild), an offline alias table with name normalization, immediate "searching" status, a design-token QSS system (light/dark) piloted on workshop cards, three crash classes fixed (QThread lifecycle, cross-thread signal guards, cross-thread direct-connection lambda slots), a double-click installer launcher (workspace-sandbox workaround), and the 2.0 rewrite preparation (18-module architecture contracts + 4-route feasibility matrix + PCL2 visual-language study + successor hand-on docs). Version markers synchronized to 1.4.2; installer rebuilt.

> 任务：t1-t8（swdm-142 团队，域 owner 制）· 2026-10-01 → 2026-10-02
> 前置：用户 2026-10-01 19:59 授权的 1.4.2 交互层 bug 清单（5 条）
> 评审文档：`docs/process/review_142.md`（三原则评审 + 交付投票）
> 上版记录：`docs/changelog_1.4.1.md`

---

## 一、版本概要

1.4.2 主线是**用户交互层的五个 bug 与反馈缺失**，全部修复均以**真实按键模拟**验证（`tests/test_user_interaction.py` 17/17 ALL PASS）——不再用 API 层 86+111 项"看似 PASS 却漏掉 4 个用户 bug"的老路：

- 输错游戏名回车不再闪退（崩溃根因见 §五）；
- 选中联想出的游戏名后正确识别（"找不到游戏"消失）；
- Backspace 每按一次删一个字符（含中文输入法上下文，新增 I2b 场景）；
- 中文/英文游戏名智能适配（"饥荒" ↔ "Don't Starve"，离线别名表 + 归一化匹配）；
- 每一样操作都有即时反馈（搜索/翻页/回车同步进入"搜索中…"态，≤150ms）。

同时交付**稳定性根因修复**（三处崩溃类）、**UI 设计令牌系统 v1.0**、**安装启动器**与**2.0 重构准备四件套**。

---

## 二、m2 游戏搜索联想重做（t2，captain 域接管）

**旧实现的 bug 结构**：联想候选通过 `game_combo.clear() + addItem + showPopup()` 重建——输入途中销毁 popup 内部构件，打断后续按键序列（用户报告"Backspace 只能删一个字符"的机制），并有构件竞态风险。

**新实现**（`swdm/gui/workshop_tab.py`）：

- 联想改用 `QCompleter` + `QStandardItemModel`：模型**原地更新**，不清空、不重建、不动焦点；候选项 `UserRole` 存 appid，点击/回车高亮项即切游戏。
- combo 的下拉列表保持完整游戏表不变（联想与游戏选择职责分离）。
- 无本地匹配时显式收起联想弹窗，避免残留候选与输入不符。

**验证场景**（真实 QTest 按键，非 API 调用）：I1 打字即时出联想 popup、I1 选中切游戏并解析 AppID、I2 popup 打开态连按 3 次 Backspace 逐字删除、**I2b 中文输入后连按 Backspace 逐字删除（用户真实 IME 场景，新增）**、I3b popup 打开态 Return 存活。

---

## 三、m2 中英文游戏名适配（t2）

- `swdm/core/games.py` 新增 `GAME_ALIASES`（55 条离线别名：饥荒/环世界/方舟/泰拉瑞亚/星露谷/文明/上古卷轴/群星/七日杀等热门游戏的中文名 + 常见简称）与 `normalize_name()`（NFKC 全角→半角 + 小写 + 仅保留字母数字：`"Don't Starve"` → `dontstarve`、`"求生之路 2"` → `求生之路2`）。
- 接入四处匹配逻辑：`_current_appid` / `_local_game_matches` / `_best_guess_appid` / `_match_score`。
- 语义：storesearch（`l=schinese`）是权威中文源，别名表是**离线/熔断兜底**（零网络、零延迟命中）。
- 顺带修两个**数据 bug**：`294100` = RimWorld（原误标 100% Orange Juice，已补真实 288470）；`219740` = Don't Starve（原误标 Project Cars）——这是 1.4.2 调试期"幽灵 100% Orange Juice"的直接来源。

---

## 四、m2 即时反馈（t2）

- `_refresh_list`（翻页/搜索/切游戏的统一入口）**同步**设置状态栏"搜索中…"、页码与上一页禁用态，不等 350ms 去抖与网络回包（用户反馈"每一样操作都要有反馈"的直接落实）。
- `_on_game_enter` 在联想未到达时立即"正在搜索游戏，稍候…"。
- 验证：I5 mod 搜索回车后 150ms 内状态栏已有可见变化。

---

## 五、三处崩溃类根因修复（t1 + t2）

| # | 崩溃现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | 搜索途中 SIGSEGV（exit -1073740791 + `QThread: Destroyed while thread is still running`） | `self._worker = _SearchWorker(...)` 中途被覆盖 → 旧线程仍在 run() 即被 GC 析构 | 模块级保活池 `_BG_THREADS` + `_register_bg_thread` + atexit 有界等待（requestInterruption + wait(2000)）；12 次重叠搜索 + 退出时 1 个在途 worker 实测 0 崩溃 |
| 2 | 图片回调 `RuntimeError: Internal C++ object already deleted` | 跨线程信号 emit 到已析构部件 | emit 前接收端存活守卫（`workers.py` PreviewImageWorker、`detail_dialog.py` 图片回调） |
| 3 | **跨线程裸 lambda 直连 → 槽在工作线程改 GUI**（隐蔽，C++ 断言抓不到） | PySide6 对 `signal.connect(lambda ...)` 走 **DirectConnection**，槽在发射线程执行并修改 status_label/completer 模型 | 四处改绑定方法（AutoConnection → 队列到主线程）：`_on_search_ready`、`items_ready`×2、详情弹窗 conflicts/deps/failed；`detail_dialog` 新增 `set_conflicts_raw` / `set_dependencies_raw` / `clear_comments` / `clear_dependencies` 桥接槽 |

**这三类全部是 Qt 互操作层的"意外复杂度"，不是语言层问题**——换任何栈都有等价物。修复模式已沉淀为 `docs/architecture/system_contracts.md` §3 的"Qt 线程规矩七组"，作为 2.0/换栈的迁移说明书。

另修：`_on_game_enter` 双重路由去重（一次回车被 combo 事件过滤器与 lineEdit 双发 → 500ms 同文本吸收，避免双倍搜索与状态抖动）。

---

## 六、m1 "找不到游戏"解析修复（t1）

- `_current_appid` 现按"Name  (appid)"**全格式**解析（两侧都按 `(` 拆分），选中联想项后不再误报"找不到游戏"。
- 兜底链：下拉项 itemData → 纯数字 AppID → 下拉项名匹配 → 最近联想缓存 → 内置表 → 别名表。

---

## 七、m4 UI 设计令牌系统 v1.0（t4，ui-designer/visual-owner 线）

- `docs/design/design_tokens.md`：色板/层级/圆角/间距/字号/动效（light+dark），PCL2 实测值 + Steam 社区调研。
- `swdm/resources/qss/{dark,light}.qss` overlay 层 + `swdm/gui/design_system.py`（TOKENS 字典 + `design_qss` 装配 + `prepare_scroll_area` 滚动区透明化）；workshop 卡片试点（ModCardWidget `swdmCard` + WA_Hover + WA_StyledBackground）。
- 兼容旧 `styles.qss()` 签名/返回不变（`test_qss_p1_p5` 37/37 PASS）；开关 `general.ui_style` modern/classic，默认 modern。
- 顺带修 1.4.1 遗留视觉 bug：QScrollArea 视口 autoFillBackground 亮灰压深色底（四处）+ QMenuBar 无规则。
- 验证：`tools/verify_design_shots.py` dark 13 项 + light 6 项像素断言 ALL PASS；README 4 截图 + 手册 5 截图重建（offscreen 字体修复后无豆腐块）。

---

## 八、安装启动器（installer 路径，1.4.2 随附）

- `installer/launch-setup.bat` + `installer/Output/安装-SWDM.bat`：双击安装器 → 选最新 SWDM-Setup-\*.exe → 优雅 taskkill SWDM → 拷贝到 %TEMP% ASCII 路径 → `start /wait` → 清理。
- 根因：本机工作区镜像路径沙箱内未知 exe 无法写 %TEMP%/AppData（Inno 引导器 error 5）——拷贝到 ASCII 临时路径后消失（对照实验确认与 agent 上下文无关）。

---

## 九、2.0 重构准备四件套（t3 + t7 + t5 + 报告）

- `docs/architecture/system_contracts.md`（54KB）：18 个 core 模块契约（职责+公共 API+线程模型+不变量，每条标注源码定位）、完整下载状态转移图、Qt 线程规矩七组、本质（10 项）vs 意外（9 项）复杂度清单、五段数据流序列图。
- `docs/architecture/rewrite_feasibility.md`（19KB）：四路线 × 五维度加权矩阵（PySide6 深度重构 4.13 > WPF 3.85 > Tauri 3.35 = Qt C++ 3.35）+ 敏感度检查 + 五阶段路线图 + 风险登记/回退点。
- `docs/design/visual_language_study.md`（24.5KB）：PCL2 仓库源码实读（MyCard/MyDropShadow/MyButton/MyListItem/MyLoading/MyHint/PageSetupUI），12 行「WPF 机制→PySide6 路径→复现度→硬上限」映射表 + 四路线美观评分。
- `docs/architecture/rewrite_2.0_master_report.md`：captain 编制的用户终裁版总报告（结论先行 + 理论基础 + 现实经验证据 + 分阶段计划 + 风险回退 + 四个开放问题）。
- `docs/process/`（t5）：继任者三件套（`dev_test_maintenance.md` 迭代八阶段+10 条环境陷阱解药、`user_interaction_scenarios.md` 15 用户场景+覆盖矩阵+7 项人工补测、`team_organization.md` 组织规矩 1-5 与理论依据）。

---

## 十、t9 下载域 1.4.1 遗留修复（F4/F2/F3，arch-owner）

独立复测（t6/t10）以 28 项纯 QTest 用户剧本新抓三个 1.4.1 遗留 bug（git show 81e956a 逐项核验非 1.4.2 回归），F4 破坏已交付卖点功能、F3 是卖点死路径，纳入本轮：

| # | 严重度 | 现象 | 根因 | 修复 |
|---|---|---|---|---|
| F1 | blocker（t6 抓到） | 生产路径工坊列表 0 卡片 | m2 把 `items_ready` 从闭包 lambda 改绑定方法直连，但真实 BrowseWorker 信号是 1 参 `Signal(list)`，2 参槽位 TypeError；桩用 2 参掩盖 | 真实信号升级 `Signal(list, int)` 携带 generation（`workers.py`），真实/桩契约统一 |
| F4 | high | 取消后行内「重试」：重试实际成功但行停「已取消」 | `_retire_cancelled`/`_exec_job` 收尾块按 `job.id` 判 `_active` 归属，取消后行内重试生成**同 id 新对象**，旧 worker 收尾把新任务踢出 `_active` 并登记旧任务 CANCELLED，重试 SUCCESS 被吞 | `_active` 归属判定一律改对象同一性（`is job`）（downloader.py 三处） |
| F2 | medium | 暂停期间排队任务仍被派发 | `_run_loop` 暂停检查只在并发等待前查一次，等并发槽位期间按下「全部暂停」后 popleft 不复查 `_paused` | 派发前最后一步补 `_paused` 复查（回到外层等待 resume 唤醒） |
| F3 | low | 勾选下载后无即时占位行（卖点死路径） | `svc.downloads_tab` 从未注入，`add_pending_batch` 抛 AttributeError 被 except 吞 | `MainWindow._build` 一行接线 `svc.downloads_tab = self.downloads_tab` |
| S7d 附加 | medium | 批量「重试失败」在 provider 链 fallback 收尾瞬态窗口内点击返回 0（job 短暂不在 _done，扫到空集） | 同上：链式回退中间态的竞态（1.4.1 遗留同类） | `retry_all_failed` 加 2s 有界等待收口，瞬态结束后照常重试 |

验证：`tests/_probe_dl_semantics.py`（3 场景确定性探针，纯 Python 线程，无 GUI/GIL 干扰）+ `tests/test_retest_round1_142.py`（28 项 QTest 用户剧本，含取消→行内重试终态成功）。

**方法论学知（进 docs/process/）**：并发类 bug 用纯 Python 探针复现比 GUI 可靠；GUI 测试中 `app.processEvents()` 持 GIL 会饿死下载线程，等待须 `time.sleep` 释放；**桩的信号元数必须与真实契约一致**，否则全绿测试掩盖生产 bug（本次 F1 正是如此被 17/17 掩盖，新增 `tests/test_browse_render.py` 真实 worker 冒烟守卫补上盲区）。

---

## 十一、陈旧测试更新与新增守卫

- `tests/test_browse_render.py`（**新增**）：真实 BrowseWorker + 桩 API → 卡片数 > 0、stderr 无 TypeError（F1 回归守卫，cards=2 ALL PASS）。
- `tests/test_retest_round1_142.py`（**新增**，qa-owner）：28 项纯 QTest 用户剧本（换游戏→联想→回车→mod 搜索→翻页→勾选→暂停/重试→取消/行内重试）。
- 更新到新契约（QCompleter 建议 model 取代 combo clear+addItem、数据修正后 "RimWorld" 取代错误的 "100% Orange Juice" 期望、版本绑定 1.4.2）：`test_game_search_fix`、`test_rettest_139`、`test_rettest_140`、`test_rettest_141`、`test_t45_retest`、`test_v136`、`test_gui`（`list_widget` → `_cards()`）、`test_gui_sweep`（F3 修复后 `_download_item` 现在真的建立占位行——补残留行清理恢复空表前提）。
- 手册扉页版本 1.4.2 + dist 重建（`tools/build_manual.py`：HTML 566KB、PDF 1.66MB、版本绑定 check 全绿）。

---

## 十二、测试与验证总结

- `tests/test_user_interaction.py`：17 项真实按键断言 ALL PASS。
- `tests/test_browse_render.py`：真实 worker 冒烟 ALL PASS。
- `tests/_probe_dl_semantics.py` + `tests/test_retest_round1_142.py`：F4/F2/F3 修复验证。
- 全量回归 `tests/run_all.ps1`：对照 1.4.1 基线零新增失败（版本绑定项需在 1.4.2 安装包构建后通过；teardown 退出码 -1073740791 为环境噪声，以 RESULT 行为准）。
- 独立复测两轮（qa-owner，t10）+ 讨论组三原则评审（t11）见 `docs/process/review_142.md`。

---

## 十三、涉及文件

- 产品代码：`swdm/gui/workshop_tab.py`、`swdm/gui/detail_dialog.py`、`swdm/gui/workers.py`、`swdm/gui/design_system.py`（新）、`swdm/gui/main_window.py`、`swdm/gui/services.py`、`swdm/core/games.py`、`swdm/core/paths.py`、`swdm/core/downloader.py`、`swdm/resources/qss/{dark,light}.qss`（新）、`swdm.spec`
- 测试/工具：`tests/test_user_interaction.py`、`tests/test_browse_render.py`（新）、`tests/test_retest_round1_142.py`（新）、`tests/test_game_search_fix.py`、`tests/test_rettest_*.py`、`tests/test_t45_retest.py`、`tests/test_v136.py`、`tests/test_gui.py`、`tools/verify_design_shots.py`（新）
- 安装器：`installer/swdm.iss`、`installer/launch-setup.bat`、`installer/Output/`
- 文档：`docs/architecture/*`（5 新含总报告）、`docs/design/*`（2 新）、`docs/process/*`（5 新含 review_142.md）、`docs/changelog_1.4.2.md`（本文件）、`docs/manual/SWDM用户手册.md` + dist 重建、README/手册截图重建

---

## 十四、已知限制（不阻塞）

1. 读图工具本机不可用（sharp ERR_DLOPEN_FAILED / Gemini key 无效）→ GUI 视觉以几何量化 + 像素断言 `tools/verify_design_shots.py` 兜底。
2. offscreen 截图成图需人工目检。
3. 托盘态/真实剪贴板交互 5 条人工清单（`docs/clipboard_watch_notes.md`）offscreen 不可验证。
4. 真 Steam 网络在本机 fake-IP 代理环境受限，网络层验证以桩 + 受限样本为准；`test_gui` 为真实网络冒烟，依赖代理在线。
