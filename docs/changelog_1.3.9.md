# SWDM 1.3.9 变更记录

发布日期：2026-09-28　版本号：1.3.8 → 1.3.9（`swdm/core/paths.py:9` APP_VERSION、`installer/swdm.iss:14` SWDMVersion 同步）

本轮主题：修复用户报告的 12 项 bug（五路并行 t11-t15）+ t16 讨论组决议并入 8 项小改 + 竞态修复。全部改动均带回归测试，1.3.9 新增约 111 项测试。

---

## 一、用户报告的 12 项 bug 修复

### U1. 托盘无法直接退出，必须先唤起程序再关闭 — t11
- 根因：`main_window.py` `_real_quit()` 用 `self.close()` 转发"退出"意图，但 `QWidget.close()` 对**不可见窗口直接返回 true 且不发送 QCloseEvent**（Qt 行为：`!isVisible()` 时跳过 closeEvent）。窗口最小化到托盘后处于隐藏态，`closeEvent` 的真正退出逻辑从未被调用，进程残留后台——与用户描述完全吻合。
- `swdm/gui/main_window.py`：
  - 新增 `_do_real_quit()` 公共方法：停止下载管理器 + 保存配置 + 释放 AppMutex + `QCoreApplication.quit()`，供 `_real_quit` 与 `closeEvent` 真正退出分支共用，避免重复逻辑
  - `_real_quit()` 改为置 `_force_quit=True` 后直接调 `_do_real_quit()`，不再依赖 `close()` 转发——隐藏窗口也能立即退出
  - `closeEvent` 真正退出分支改为调 `_do_real_quit()` + `super().closeEvent(event)`；拦截分支（可见+托盘可见 → `hide()` 最小化）保持不变，F4 不回归；`aboutToQuit` 兜底释放保留
- 测试：`tests/test_uninstall_fix.py` 扩展至 22 项——新增 `_QuitRecorder` 替身拦截 `QCoreApplication.quit()`（避免测试进程真退出）；改造用例 4；新增 7a/7b/7c（模拟 `_build_tray` 菜单接线：可见态触发退出、**隐藏态触发退出**——t11 核心场景、「显示主窗口」恢复可见）

### U2. 游戏框输入未识别，只能下拉选 — t12
- 根因：`_on_game_enter` 的 `_current_appid()` 解析链全部要求名称**精确相等**，联想未返回时 `_last_search_pairs` 为空即判未识别。
- `swdm/gui/workshop_tab.py`：`_current_appid()` 多层回退（精确匹配 → 纯数字 → 下拉项名称匹配 → 联想缓存 → 内置游戏表），新增 `_match_score()`/`_best_guess_appid()` 模糊回退；输入与下拉项文本不一致时绝不误用旧 itemData
- 测试：`tests/test_139_merge.py` 等 38 项新测试覆盖

### U3. 搜索联想下拉混乱 — t12
- 本地即时匹配层（零延迟出候选）+ 模糊评分排序；下拉弹出时机统一；联想结果带 DLC 启发式过滤
- 测试：t12 的 38 项新测试

### U4. 搜索回车疑似无效 — t12
- 回车确认走 `_on_game_enter`，配合 U2 的多层回退解析，输入游戏名/AppID 均可识别

### U5. 标签筛选不准 — t12
- 根因：服务端 `requiredtags` 只是近似匹配。改法：客户端按所选标签做**精确过滤**，并给出可见性提示"已按所选标签精确过滤掉 N 个不匹配的物品"（t16 议题 E-① 一次性解决"过滤完全静默"问题）
- 与 B① 提示柔化统一为一套大白话措辞

### U6. 切换游戏后标签不自动刷新（旧标签仍过滤新游戏列表）— t13
- 根因：`tag_bar.set_tags()` 的"切换游戏后保留选中"逻辑会重选同名标签，且 `_on_game_changed` 从不清标签选中与过滤参数
- `swdm/gui/workshop_tab.py`：`_on_game_changed` 开头 `tag_bar.clear_selection()` + `tag_edit.setText("")`（同游戏手动刷新的保留逻辑不动）

### U7. 下载卡 99% 不动 — t14
- 根因：`DownloadJob.percent` 的 `min(99, ...)` 硬封顶 + CDN 路径 total 与实际字节不一致时永远到不了 100。改法：完成判定以字节数为准，`bytes >= total` 直返 100

### U8. 速度显示 0 → 突跳 2-300MB/s — t14
- 根因：`ProgressSmoother` 的 EMA 在 UI 定时器与工作线程上报频率不匹配时给出假速度；`min_interval=0.1` 的 emit 节流合并了采样
- `swdm/core/downloader.py`：改最近 N 秲**滚动窗口 + 时间戳**采样（`deque`），速度 = 窗口内字节增量 / 时间增量；`ProgressSmoother` 节流只合并 emit 不合并样本

### U9. 设置页首行挤压 — t13
- offscreen 几何量化定位：分组标题按钮与首个 QGroupBox 仅 6px、目录表首行行高无保底。三处定向加固：`CollapsibleSection` 内容上边距 6→10、账号分组表单显式 spacing/margins、目录表 `defaultSectionSize=30` / `minSectionSize=24`

### U10. 下载页与库页删除不互通 — t13
- 双向信号：`DownloadsTab.library_changed` + `_remove_row` 对已入库成功任务弹"同时从 mod 库移除（含文件）？"；`LibraryTab.records_removed` 两个删除动作后 emit；`main_window.py` 接线（`library_changed → _on_library_changed` 无参槽，`records_removed → remove_rows_for`）。G4 选中恢复不回归

### U11. mod 库不按游戏分类（只显示裸 AppID 数字）— t14
- 根因（t16 议题 C-① 定位）：appid 过滤下拉早已存在（`library_tab.py:72-75`），缺口只在**展示层用裸 appid 数字**（"4000" 而非 "Garry's Mod"）。改法：过滤下拉与库行文本统一用 `games.game_name()` 渲染，无需新增列/分组结构（保守实现，符合精简原则）

### U12. 详情页加载慢 — t15
- 量化基线（4 真实夹具放大到 ~220KB）：全链路解析合计仅 **4.5ms/页**——**解析不是瓶颈**；真瓶颈是 `/sharedfiles/` 的 3s 端点节流把连续点击串行化，且 400ms 悬停预取会抢占槽位，用户点击排在预取后面空等 3s
- `swdm/core/steam_api.py` `_endpoint_throttle(path, priority)`：priority=True 绕过端点等待；低优先级改 0.25s 分片睡眠，期间检测 `_priority_pending` 则立即让槽返回 False；`_community_get` 计数器进出清零（finally + `max(0,n-1)` 防泄漏）
- 用户点击（`DetailPageWorker`、`get_dependencies`）传 priority=True；预取 worker 保持低优先级；`workshop_tab._do_prefetch_detail` 有用户请求在飞时直接跳过预取
- 感知层（既有，无需改）：弹窗 show() 先于 worker、简介先填、依赖/评论/图片加载占位、预览图独立 QThread
- 测试：`tests/test_detail_perf.py`（新增，17 项）

---

## 二、t16 讨论组决议并入项（8 项）

讨论组五方（installer-fixer 组织 + search-fixer / core-tester / gui-tester / recorder）逐条评审 A-E 议题，详见 `docs/feature_review_1.3.9.md`。本版落地：

| 编号 | 项 | 落点 |
|---|---|---|
| A-P3 | `on_throttle_signal` 被覆盖（1.3.8 遗留） | `steamcmd_engine.py:144` 单回调改 `list`；`downloader.py:119` 改 `append` 订阅（约 3 行，有真实触发路径：多 manager 共享 engine） |
| A-P1 防御 | 取消后不登记 `_done` 廉价防御（P1 本身留 1.3.10） | `downloader.py` cancel 路径守卫（t14 已带） |
| B① | 搜索提示文案柔化 | `steam_api.py:810` `SEARCH_LOW_HIT_HINT` 去黑话："Steam 搜索只匹配标题；想精确搜索作者，可在设置页填写 Steam API Key"，与 t12 标签过滤提示统一一套措辞 |
| B② | 设置页"打开数据目录"按钮 | `settings_tab.py:247` `open_data_btn` + `:537` `_open_data_dir`（`QDesktopServices.openUrl`，零风险；与 U10 删除互通呼应） |
| B③ | 库页导出当前筛选结果 | `library_tab.py:153` `_current_filter()` + `:362/371` `_export_list` 导出与列表显示一致的结果集 |
| C① | mod 库按游戏分类 | t14 的 `game_name()` 渲染（见 U11） |
| E② | 下载完成托盘通知 | `main_window.py:216` `_notify_download_finished`（复用 1.3.7 F4 托盘链路，零新依赖） |
| E③ | steamcmd 报 SUCCESS 但 bytes=0 校验 | `downloader.py:504-512`：SUCCESS + `bytes_done<=0` 改判 FAILED 走重试路径（<15 行，t6 复测观察到的瞬时现象闭环） |

测试：`tests/test_139_merge.py`（新增，28 项，覆盖 M1-M7 并入项）

---

## 三、竞态修复（core-tester，t17 打包前并入）

`swdm/core/downloader.py:250-271 / 563-576`：
- 真因：`cancel()` 与 `_exec_job` 收尾路径竞态——worker 置 SUCCESS/FAILED 后、移出 `_active` 前，`stop() → cancel_all() → cancel()` 把终态覆盖成 CANCELLED，造成"下载成功却显示已取消"与 `_done` 重复登记 / finished 双发（test_throttle 7a/7b/7c2 偶现 flake 的真因）
- 修法：`cancel()` 对已终态（SUCCESS/FAILED）job 提前返回；`_exec_job` 仅在本路径完成登记时 fire finished
- 测试：`tests/test_throttle.py` 新增 7g/7h 确定性竞态回归（hook 在置态后注入 cancel，验证未修补代码 FAIL / 修补后 PASS）；15 轮采样 0 失败（修前 5/8）

test_v136 固件修复（gui-tester）：check#2 联想输入在 `game_combo` 残留文本 "g" 致 `_current_appid()` 返回空、`_do_refresh_list` 提前返回——属测试固件跨 check 状态污染，check#4 前重置游戏选择修复。

---

## 四、版本号与打包

- `swdm/core/paths.py:9` `APP_VERSION = "1.3.9"`；`installer/swdm.iss:14` `SWDMVersion = "1.3.9"`（OutputBaseFilename、VersionInfo 同步）
- 打包链：`pyinstaller swdm.spec --noconfirm`（成功，330 文件）→ 复制 `dist\SWDM` 到 `build\dist` → ISCC（Inno Setup 6.7.3，33.1s）→ **`installer\Output\SWDM-Setup-1.3.9.exe`（42.67 MB）**
- 冒烟：`build\dist\SWDM\SWDM.exe` 稳定运行 6 秒未退出；安装包 FileVersion / ProductVersion 均为 1.3.9

---

## 五、全量回归统计

`tests/run_all.ps1` 串行执行（`QT_QPA_PLATFORM=offscreen` + `PYTHONUTF8=1`，结果文件重定向读取）。**终态：56 脚本 54 PASS / 2 FAIL / 0 NORESULT**（t17 时点 53 脚本 51 PASS，t18/t19 新增 3 个复测脚本后为终态）

- 复测脚本（t18/t19 新增，全部 PASS）：`test_rettest_139`（t18，42 项用户视角）、`test_t19_retest` + `test_t19_retest2`（t19，28+12 项核心视角）
- 既有非回归（与 1.3.8 基线逐项一致，非代码回归）：
  - `test_legacy_format` — 真实 mod 字节数漂移（夹具需与字节数解耦，1.3.10 待办）
  - `test_page_parser` — 旧标签夹具（需用真实 Wayback 快照重写，1.3.10 待办）
- `test_actions_api`：1.3.8 基线的实网 429 本次跑通 PASS（0 NORESULT）
- `test_throttle`：竞态修复后全 PASS（含新增 7g/7h 守卫）
- `test_v136`：固件修复后全 PASS
- `test_bulk_games`：本次全 PASS（前次失败为实网偶发）
- 1.3.9 新增测试约 111 项：t11 22 项（扩展）、t12 38 项、t13 19 项、t14 40 项、t15 17 项、t16 并入项 28 项
- GUI 测试 offscreen 全量通过：`test_gui_sweep`、`test_all_buttons`、`test_cross_features`、`test_batch3`（F4 托盔回归）

---

## 六、t20 交付评审（讨论组终审）

评审时间：2026-09-29 · 主持：search-fixer（t12 修复作者 + t16 并入项实施者）· 五方：captain / installer-fixer / gui-tester / core-tester / recorder

评审原则：精简、以用户体感为中心、保证基本功能正常运行。评审对象：1.3.9 打包终态（`installer\Output\SWDM-Setup-1.3.9.exe` 42.67MB，版本号双端 1.3.9）。

### 6.1 U1-U12 逐条过审（修复 → 测试 → 判定）

| # | 用户 bug | 修复 | 复测覆盖 | 判定 |
|---|---|---|---|---|
| U1 | 托盘无法直接退出 | t11 `_do_real_quit()`（Qt 对隐藏窗口 close() 不发 closeEvent 的根因，最小修复） | t11 22 项 + t18 U1 + 关联5 | ✅ 无过度设计 |
| U2 | 搜索联想下拉混乱 | t12 `currentIndex -1` + 匹配度排序（精确>开头>包含） | t12 38 项 + t18 U2 | ✅ |
| U3 | 游戏框输入未识别 | t12 editable combo 陈旧 itemData 根因 + 五层回退链 | t12 + t18 U3 | ✅ |
| U4 | 搜索回车无效 | t12（实测已具备，未误改；补待选机制） | t12 + t18 U4 | ✅ |
| U5 | 标签筛选不准 | t12 客户端精确交集 + 服务端近似兜底提示 | t12 + t18 U5 + 关联6 | ✅ |
| U6 | 切游戏标签不刷新 | t13 两行修复（clear_selection + setText） | t13 19 项 + t18 U6 | ✅ |
| U7 | 下载卡 99% | t14 一行判定（bytes>=total 直返 100%） | t14 40 项 + t18 U7 + t19 | ✅ |
| U8 | 速度突跳 | t14 deque 滚动窗口（未重写采样链） | t14 + t18 U8 + t19 独立验证 | ✅ |
| U9 | 设置页首行挤压 | t13 三处间距加固（量化定位） | t13 + t18 U9 | ✅ |
| U10 | 删除/移除不互通 | t13 双向信号（两信号+两槽，未动数据层） | t13 + t18 U10 + 关联7 | ✅ |
| U11 | 库不按游戏分类 | t14 展示层 `game_name()` 渲染（降维，不加分组树） | t14 + t18 U11 + t19 | ✅ 无过度设计 |
| U12 | 详情页加载慢 | t15 量化基线推翻预设（解析 4.5ms/页非瓶颈），只改端点节流优先级礼让 | t15 17 项 + t18 U12 + t19 | ✅ 本版最克制一处 |

**五方一致结论**：12 项全部根因修复 + 测试闭环（约 111 项新检查全 PASS），无一例为修 bug 引入新抽象。

### 6.2 t16 决议执行情况

| 决议 | 执行 | 核实 |
|---|---|---|
| A-P3 on_throttle_signal 订阅化 | ✅ 已收 | `steamcmd_engine.py:144` list + `downloader.py:119` append，t19 独立验证订阅不覆盖语义 |
| A-P1 廉价防御（取消不登记 _done） | ✅ 已收 | cancel 路径守卫；后续竞态修复（core-tester，15 轮 0 失败 + 7g/7h 守卫）覆盖更强语义 |
| B① 搜索提示柔化 | ✅ 已收 | SEARCH_LOW_HIT_HINT 去黑话、两处措辞统一 |
| B② 打开数据目录按钮 | ✅ 已收 | `settings_tab.py` open_data_btn |
| B③ 导出当前筛选结果 | ✅ 已收 | `library_tab.py` `_current_filter()`，t18 关联8 实测只导命中项 |
| C① 库按游戏分类 | ✅ 已收 | game_name 渲染（行内 + 下拉），保守实现 |
| E② 下载完成托盘通知 | ✅ 已收 | 复用 F4 链路，双守卫 |
| E③ steamcmd bytes=0 校验 | ✅ 已收 | <15 行，t19 对照验证 |
| A-P1 主修复 / B④ / C② / D / E④ | ⏸ 延后 | 全部显式登记第七节 1.3.10 待修清单，无遗忘风险 |

**D 间隔项专项说明**：讨论组结论倾向降到 0.6-0.8s，captain 并入清单未列；t12 本地即时匹配层已消除联想体感瓶颈（t18 U2 实证），且 storesearch 匿名接口无速率保障、本机出口 IP 已被限过——五方复评认为保守不降是正解而非遗漏。

### 6.3 提问回答

**Q：是否有"该加没加、影响基本功能"的项？**
A：**没有。** 两轮复测 + 全量回归未发现基本功能缺口。两点已登记的非基本功能项：t15 移交的 stop/retry 竞态（偶发 flaky，非用户场景稳定触发，t22 兜底）；`services.py:78` 未传 api 致 CDN 几乎必然回退 steamcmd（架构层，t21 provider 抽象层顺带修复，steamcmd 通道本身工作正常）。

**Q：既有非回归失败如何处理？**
A：`test_legacy_format`（真实 mod 字节数漂移）+ `test_page_parser`（旧标签夹具，Wayback 实证推翻）自 1.3.8 起逐项一致，均非功能缺陷，登记第七节 1.3.10 待办（P4/P5）。

### 6.4 五方投票表

| 投票人 | 立场 | 投票 | 保留意见 |
|---|---|---|---|
| search-fixer（主持） | t12 作者 + t16 并入项实施者 | **同意交付** | 无 |
| captain | 团队负责人 | **同意交付** | 无（12 项修复链路逐条核实、四要素齐备） |
| installer-fixer | U1 修复 + t17 打包执行者 | **同意交付** | 无（D 间隔保守不降为正确取舍） |
| gui-tester | t18 第一轮复测执行者 | **同意交付** | 无（已回填第五节回归终态数字，追溯性已补齐） |
| core-tester | t19 第二轮复测执行者 | **同意交付** | 无 |
| recorder | 工程记录员 | **同意交付** | 无（提示 t19 verdict 字段不可变，已以 acceptanceResults 6/6 passed 等价记录） |

**投票结果：6/6 同意交付，零反对。**

### 6.5 交付闸门结论

用户规定的两个交付条件均已满足：

1. **讨论组一致认为可交付** —— t16 功能评审五方逐条表态 + t20 交付评审 6/6 同意、零反对 ✓
2. **bug 测试员连续两轮复测均无异常** —— t18（GUI/用户视角 42+16 项）+ t19（核心视角 40 项）ALL PASS；两轮全量回归均 56 脚本 54 PASS / 2 既有非回归（与 1.3.8 基线逐项一致）/ 0 NORESULT，零新增失败 ✓

迭代四要素齐备：全量回归 ✓、讨论组评审 ✓、版本号双端 1.3.9 + changelog 可追溯 ✓、连续两轮复测无异常 ✓。

> **闸门结论：1.3.9 交付评审通过，SWDM 1.3.9 正式交付。**
> 安装包：`installer\Output\SWDM-Setup-1.3.9.exe`（42.67 MB）。t21（provider 抽象层）/ t22（1.3.10 遗留项）随之解锁。

---

## 七、待修清单（1.3.10 / t22，无遗忘风险）

- **A-P1**：cancel 微秒并发窗口（`downloader.py:392-393`），正确修复需 pending-cancel 集合 + 派发前检查（>15 行，涉状态机核心路径）
- **B④**：调试 Tab 默认隐藏（`show_debug_panel` 配置已存在，需同步 `win.debug_tab` 相关测试）
- **C②**：下载页暂停/继续合并为单按钮（留 polish 批，`_sync_batch_buttons` 状态同步 + 按钮测试需重跑）
- **D**：`GameSearchClient` 1.2s 间隔 → 0.6-0.8s + `_Throttle` 熔断退避
- **P4**：`test_page_parser` 夹具用真实 Wayback 快照重写
- **P5**：`test_legacy_format` 字节数解耦
- polish：作者作品列表页、导出筛选结果的进一步打磨
- 1.4.0 规划：provider 抽象层（t21，详见 `docs/provider_adaptation.md`）

---

*1.3.9 交付闸门：讨论组一致通过（t16 功能评审 + t20 交付评审 6/6 同意、零反对）+ bug 测试员连续两轮复测无异常（t18 GUI 视角 58 项 / t19 核心视角 40 项，全量回归 56 脚本 54 PASS 零新增失败）——两项均已满足，t20 评审放行，1.3.9 正式交付（2026-09-29）。*
