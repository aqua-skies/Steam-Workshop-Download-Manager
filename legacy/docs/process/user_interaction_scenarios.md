# SWDM 用户侧交互场景剧本（继任者接手文档）

> 面向：继任者 AI 与独立复测员。目标：**每条场景 = 操作步骤 + 期望反馈 + 自动化覆盖 + 没覆盖就要人工补**。
> 维护人：process-doc（swdm-142 t5）· 2026-10-01
> 约定：`test_user_interaction.py` 头部公约——直调 `setText` / 方法 = API 测试；`QTest.keyClicks` / `keyClick` / `QInputMethodEvent` 才算用户交互测试。本文件场景与之一一对应。
> 姊妹篇：`docs/process/dev_test_maintenance.md`（流程与环境陷阱）· `docs/process/team_organization.md`（组织规矩）
> 状态基线：1.4.1 已交付；1.4.2 修复中（t1 硬崩溃 / t2 交互反馈 / t3 中英文适配 / t4 视觉系统）。标 **[1.4.2]** 的期望反馈依赖在修项落地后的行为。

---

## 〇、怎么用这份文档

1. **自动化能跑的**：按 §各场景的「自动化覆盖」列直接 `python tests\<文件>.py`（必须 `$env:PYTHONUTF8="1"; $env:QT_QPA_PLATFORM="offscreen"`，字体陷阱见 dev_test §四.1）。判定看 stdout `RESULT:` 行。
2. **自动化覆盖不到的**：查 §十二「人工补测清单」，逐条在真实桌面执行并记录（复测文档范例：`docs/clipboard_watch_notes.md`）。
3. **新增场景**：照抄 `test_user_interaction.py` 头部套式（dev_test §3.1），网络全桩、场景自闭合，脚本式 `check()` + `RESULT:`。

---

## 一、游戏名输入与联想下拉（工坊页顶部游戏框）

**GUI 锚点**：`swdm/gui/workshop_tab.py` `game_combo`（:388，editable + NoInsert；`currentIndexChanged → _on_game_changed`）· `_do_game_search` / `_fill_search_results` / `_on_search_ready` · `_current_appid()` 解析链（下拉项文本 → `_last_search_pairs` → 内置表，选中后 lineEdit 变 `Name  (appid)` 全格式）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 点击游戏框，逐字输入 "garry" | 每输入一个字符都有即时反应；本地内置表匹配立即出候选（无需等待网络）**[1.4.2 输入阶段即时反馈]** |
| 2. 继续输入 / 停顿 | 弹出联想 popup，候选按匹配度排序，**第一项始终是最佳匹配**；本地与网络结果都弹下拉（行为一致） |
| 3. 输入框文本与 popup 选中状态同步 | lineEdit 文本 = 用户输入；选中某项后 lineEdit 变为 `Name  (appid)` 全格式，且 `_current_appid()` 解析成功（两侧都按 `(` split 后比较） |
| 4. 键盘上下键 + 回车选中 | 走 combo 选中路径，不崩；列表刷新请求触发（AppID 已解析） |
| 5. 状态栏 | **不出现**「请先选择或输入游戏 AppID」 |

**自动化覆盖**：
- `tests/test_user_interaction.py` **I1**（真按键 `QTest.keyClicks`：打字即时出联想 popup / 选中后全格式 / `_current_appid` 解析成功 / 状态栏无未识别提示 / 触发列表刷新）
- `tests/test_game_search.py`（可编辑下拉、本地匹配、防抖、在途取消——隔离构造不触发网络）
- `tests/test_game_search_fix.py` **U1/U2**（U1 回退链：联想最佳匹配 / 本地匹配 / 结果到达自动选第一项 / 纯数字 AppID；U2 下拉 currentText 与 lineEdit 一致、候选项按匹配度排序）

**1.4.2 关联修复**：`_do_game_search` QThread 生命周期硬崩（t1，SIGSEGV 复现指纹 = 退出码 -1073740791 + `QThread: Destroyed while thread still running`——`self._search_worker` 覆盖旧引用致运行中 QThread 被 GC）。

---

## 二、中文 / 英文游戏名适配

| 步骤 | 期望反馈 |
|---|---|
| 1. 用输入法键入中文 "饥荒" | 文本落入输入框（`QInputMethodEvent` 路径），联想出候选 |
| 2. 选中或回车 | 解析到 Don't Starve 系列 AppID（别名表：中文俗称 ↔ 英文原名 ↔ AppID） |
| 3. 输入英文 "dont starve"（无撇号） | 同样解析到 AppID |
| 4. 翻译名 / 缩写 / 大小写变体 | 统一匹配层命中（别名表 + 容错）**[1.4.2 游戏搜索域 t2]** |

**自动化覆盖**：
- `tests/test_user_interaction.py` **I4**（中文键入落到输入框；"饥荒" 解析到 Don't Starve 系列 AppID；"dont starve" 解析到 AppID；解析后触发列表刷新）

**1.4.2 关联修复**：中英别名表 + 统一匹配已并入**游戏搜索域任务 t2（ux-fixer 端到端）**——bug 归属制：搜索 popup 的一切交互行为归域 owner 一人守（见 `team_organization.md` §一 规矩 1）。

---

## 三、错误游戏名回车（不崩 + 明确反馈）

| 步骤 | 期望反馈 |
|---|---|
| 1. 输入一个不存在的游戏名，如 "zzzNotExist" | 不硬崩（进程存活）；有明确反馈（"未找到该游戏" 类提示或联想空态），不是无声失败 |
| 2. popup 打开态按回车 | 走 combo 选中路径，不崩（若有候选选第一项；无候选给提示） |
| 3. 网络慢 / 熔断时回车 | 降级走本地回退链（U1 链：联想最佳匹配 → 本地匹配 → 纯数字 AppID），最终无解析时提示而非转圈不动 |

**自动化覆盖**：`tests/test_user_interaction.py` **I3 / I3b**（错误游戏名回车进程存活——走到断言后即未硬崩；无结果时给出明确反馈；popup 打开态 Return 进程存活）。

**1.4.2 关联修复**：t1（`_current_appid` 全格式解析 + QThread 存续守卫）；t2（输入阶段即时反馈）。

---

## 四、退格删除字符（popup 打开态）

| 步骤 | 期望反馈 |
|---|---|
| 1. 输入 "garrymod" 使 popup 打开 | popup 弹出 |
| 2. 连按 3 次 Backspace | **每次只删一个字符**（`clear()+popup` 竞争不再吞输入），输入框剩 "garr"，输入框仍可继续编辑不卡死 |
| 3. 继续输入 | 联想候选随文本更新 |

**自动化覆盖**：`tests/test_user_interaction.py` **I2**（popup 打开态连按 3 次 Backspace 每次都删一个字符；删除后输入框非卡死）。

---

## 五、mod 搜索与回车（搜索框）

**GUI 锚点**：`workshop_tab.py:452` `search_edit`（placeholder「搜索 mod 关键词或作者名（回车）…」；`returnPressed → _refresh_list`）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 选好游戏后，在 mod 搜索框输入关键词 | 输入阶段即有可见反馈（ LoadingOverlay 或状态条进入"搜索中"态）**[1.4.2]** |
| 2. 按回车 | 触发列表刷新（`_refresh_list` 真被调用），150ms 内有可见反馈 |
| 3. 低命中率（搜作者名） | 回退链：标题命中率 < 0.3 时按作者过滤（`apply_browse_search_fallback`），双 0 命中返回空列表 + 明确空态文案"未找到该作者的 mod"，状态栏提示"Steam 搜索仅匹配标题…" |
| 4. 翻页 / 改词 | 代际请求丢弃旧结果（`_search_by_gen`），不串页 |

**自动化覆盖**：
- `tests/test_user_interaction.py` **I5**（mod 搜索回车后 150ms 内有可见反馈）
- `tests/test_search_fix.py`（S1/S2 搜索回退 26 项：标题命中率 / 作者过滤 / 状态栏提示 / 双 0 命中空态）
- `tests/test_game_search_fix.py` **U3**（returnPressed 已接线且 `_refresh_list` 实际被触发）

---

## 六、翻页与滚动（工坊列表）

**GUI 锚点**：`prev_btn`（:511，第 1 页禁用）· `next_btn`（:524）· `list_scroll`（:493，SmoothScrollBar）· `_page`（:294）· 预取（`_on_items_ready` 后调度下一页预取，只暖 ApiCache、从不渲染、不覆盖当前页）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 第 1 页加载完成 | 「← 上一页」禁用；页码标签正确 |
| 2. 点「下一页 →」 | 立即看到页码变化（同步路径，不等网络回包）；新页 30 条卡片、滚动条归零、滚动范围重建 |
| 3. 滚动 | 平滑滚动条（SmoothScrollBar），无跳动 |
| 4. 翻页后勾选状态 | 勾选集合清空（不跨页残留） |
| 5. 到最后一页 | 空列表时 `page > 1` 显示"已到最后一页，没有更多物品"；下一页预取熔断冷却期跳过不空转 |
| 6. 回上一页 | 卡片为旧 id，可再滚动，缩略图回填不报错 |

**自动化覆盖**：
- `tests/test_page_switch.py`（页 A/B 卡片数、滚动归零、范围重建、回页 A 旧 id、缩略图回填、翻页勾选清空）
- `tests/test_scroll_repage.py`（滚动 + 翻页联动）
- `tests/test_t34_nextpage_prefetch.py`（25 项：只在本页满 30 条时预取 / 熔断冷却跳过 / 用户点击与依赖下载在飞时礼让 / 代际两次校验旧预取丢弃 / 预取只暖缓存从不渲染）

---

## 七、勾选与批量下载

**GUI 锚点**：卡片 `check_box` · `_checked_ids`（:304）· `dl_selected_btn`（:536 → `_download_selected`）· `_check_all` · `_update_dl_button`。

| 步骤 | 期望反馈 |
|---|---|
| 1. 勾选一张卡片 | `_checked_ids` 含该 id；按钮文本变「⬇ 下载勾选 (1)」；勾选不误触详情 |
| 2. 点「全选」 | 3 项全选，卡片 `isChecked` 同步；再点全部取消 |
| 3. 点「⬇ 下载勾选 (n)」 | 加入下载队列（含依赖解析），切到下载页；**入队后勾选集合清空、按钮复位无 (n)** **[1.4.2 U4]** |
| 4. 单卡下载按钮 / 卡片详情按钮 | 单卡下载不经勾选路径；整卡点击不打开详情 |
| 5. 重新填充列表 | 勾选清空，卡片为全新实例 |

**自动化覆盖**：
- `tests/test_checkboxes.py`（卡片数 / 初始无勾选 / 勾选集合 / 按钮文本更新 / 全选反选 / 重新填充清空 / 整卡点击不打开详情 / 勾选不误触详情 / 设置页无压扁控件）
- U4（入队后清空）为 1.4.2 计划项：`plan_1.4.2_impl.md` §U4，落地后 `test_checkboxes.py` 加断言"点「下载勾选」后 `_checked_ids` 为空且按钮文本无 (n)"

---

## 八、标签过滤（标签栏）

**GUI 锚点**：`workshop_tab.py:487` `tag_bar`（`selection_changed → _on_tag_selection_changed`）· 切换游戏时 `_on_game_changed → _fetch_tags` 同步刷新标签栏（内容 / 选中状态 / 列表过滤三者同步）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 游戏加载后 | 标签栏显示标签 chips（过滤无关导航标签、去重保序、计数 `(1,234)` 显示、0 计数不显示括号） |
| 2. 勾选标签 | `selected()` 含该标签；触发 selection_changed；已选行显示带叉 chip |
| 3. 点叉删除标签 | 从 `selected()` 移除，对应 chip 取消勾选 |
| 4. 服务端近似匹配不准时 | 客户端交集精确过滤（`U4` 客户端二次处理）+ 状态栏提示"标签过滤为服务端近似匹配" |
| 5. 切换游戏 | 标签栏内容、选中状态、列表过滤三者同步刷新（旧选中残留 = bug 指纹） |
| 6. loading / 空列表 / 拉取失败 | 表头三态分清（1.4.2 U10：加载中 / 无标签 / 拉取失败含重试入口）**[P2]** |

**自动化覆盖**：
- `tests/test_tag_bar.py`（标签解析过滤 / 去重保序 / 计数显示 / 选中集合 / 带叉 chip / 多选累积 / set_selected 去重 / 点叉删除 / 清空选择 / 重填保留选中 / loading 态表头 / 空列表禁用）
- `tests/test_game_search_fix.py` **U4**（标签精确过滤：服务端 requiredtags 近似匹配 → 客户端交集过滤 + 提示）
- `tests/test_quick_search.py`（详情页标签 / 作者依赖标题点击 → 跳转筛选页搜索）
- 实网标签拉取：`tests/test_tags.py`（`run_all.ps1` skip 基线——真实 Steam 标签页结构，环境漂移时单跑定性）

---

## 九、详情页

**GUI 锚点**：`swdm/gui/detail_dialog.py`（「🔄 刷新」强制 bypass 缓存重建 worker）· `detail_cache.py`（TTL 24h + `time_updated` 双失效，命中深拷贝，损坏容忍按 miss）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 点卡片「详情」按钮 | 弹出详情页；整卡点击不打开详情 |
| 2. 再次进入同一物品 | 命中磁盘缓存零网络请求（回退不重新加载） |
| 3. 点「🔄 刷新」 | 清内存条目 + `force_refresh=True` 重建 |
| 4. 评论区 | 默认折叠（1.4.2 U12：悬停提示 + 手册 E10 补写折叠说明） |
| 5. 依赖 / 作者 / 标签 chip | 依赖标题搜索、作者搜索、依赖行独立下载、社区链接可用（手册 E10 的 7 点交互） |

**自动化覆盖**：`tests/test_detail_dialog.py`（弹窗交互）· `tests/test_t33_detail_cache.py`（33 项：双失效 / 深拷贝 / 损坏容忍 / 手动刷新 bypass）· `tests/test_detail_perf.py`（解析耗时 + 缓存命中）。
**人工**：详情页视觉布局（本机读图工具失效，几何量化兜底）。

---

## 十、下载与进度反馈（下载页）

**GUI 锚点**：`downloads_tab.py` 按钮（:62-65）· `_clear_done`（:289）· `_retry_failed` · 进度条终态色（success/failed，unpolish/polish 重绘）· `ProgressSmoother` 滚动窗口速度。

| 步骤 | 期望反馈 |
|---|---|
| 1. 入队一个 mod | 下载页出现该物品行；状态从排队 → 下载中 |
| 2. 观察速度 | 滚动窗口速度平滑（突发合并，不突跳 2-300MB/s）；长停顿后窗口正确反映真实速率；窗口外样本被丢弃 |
| 3. 卡 99% 判定 | 完成判定以字节数为准（`percent` 100 由字节闭环，不封顶 99%） |
| 4. 暂停 / 继续 | 「⏸ 全部暂停 ⇄ ▶ 全部继续」单按钮切文案；暂停态排队行文案追加「（已暂停）」**[1.4.2 U6]** |
| 5. 取消 | cancel 立即生效（微秒竞态已闭环：A-P1 16 项）；取消发到正确 provider **[1.4.2 P0-2]** |
| 6. 失败 | 终态红色 + 可读失败原因（C2 八类：DISK_FULL / RATE_LIMITED / NETWORK / LOGIN_FAILED / ITEM_GONE / ACCOUNT_NEEDED / EMPTY_SUCCESS / GENERIC，误报红线：通用 I/O 串绝不映射"需正版账号"） |
| 7. 点「↻ 重试失败」 | 重试失败任务，不因按钮自身 bug 崩（G3 已修） |
| 8. 点「清除已完成」 | 只清成功行 + 二次确认（默认"否"），失败/已取消行保留给「↻ 重试失败」**[1.4.2 U2]** |
| 9. 空队列 | 空态引导「前往工坊浏览」（B6） |

**自动化覆盖**：
- `tests/test_download_stats.py`（t14 回归：滚动窗口速度 / 突跳 / 卡 99% / 库 appid 维度）
- `tests/test_ap1_cancel_race.py`（16 项 3 场景确定性回归：cancel 抢注 / 入链前取消 / 标记清理后重试）
- `tests/test_download_fixes.py` · `tests/test_failure_reason.py`（42 项含 5 项误报红线）· `tests/test_t44_retest_gui.py`
- 空态 / 按钮布局：`tests/test_gui_sweep.py`（98 项 5 Tab 全覆盖，含 G2 从底往上删行 / G3 状态栏引用修复）

---

## 十一、mod 库管理（库页）

**GUI 锚点**：`library_tab.py` `import_btn`（:149「⬆ 导入已有目录」）· `export_btn`（:154「⬇ 导出列表」）· `import_list_btn`（:159）· `check_updates_btn`（U3 三态按钮）· 右键菜单（:486）· 库页空态（:284-344）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 下载完成 | 自动登记入库；刷新后选中行不丢失（G4：重建前记 `_selected_ids()`，重建后按 UserRole 恢复） |
| 2. 按游戏分类 | 库记录带 appid 维度；库页分组 / 筛选按游戏生效（t14 库分类） |
| 3. 折叠分组 | 切换不崩；展开分组标题按钮与首个内容控件间距 ≥ 8px（防挤压，量化断言） |
| 4. 导出列表 | 导出**当前筛选结果**（B③，与列表显示一致），JSON 数组；导出完成弹窗显示条数与路径 |
| 5. 导入列表 | 非数组 JSON（字典）不崩（G5 守卫 + 明确错误提示）；导入完成弹窗显示成功数，1.4.2 U8 起同时显示跳过数 **[P1]** |
| 6. 导入已有目录 | 询问目标游戏 AppID；导入完成提示 |
| 7. 点「🔍 检查更新」 | daemon 线程执行不卡 UI；进度「检查中 x/y」实时；按钮三态（启动 / 进度 / 取消）**[1.4.2 U3]**；更新项标红（🔄 前缀 + 红色）→ 询问是否入队 → 同意后入队并清标红 |
| 8. 检查更新中再点按钮 | 变「⏹ 取消检查」，批间（50 条/批）粒度中止，已有部分结果如实标红不吞 **[1.4.2 U3]** |
| 9. 空库 / 筛选无结果 | 空态引导（「前往工坊浏览」/「清除筛选条件」） |

**自动化覆盖**：
- `tests/test_gui_sweep.py`（模组库页节：导入非数组 JSON 不崩 / 导出 JSON 数组 / 折叠分组切换不崩 + 间距量化；G4 选中恢复）
- `tests/test_t37_lib_updates.py`（34 项：核心 15 + GUI 19，500 条分 10 批进度单调递增 + cancel 中止）
- `tests/test_a6_check_updates_thread.py`（A6 修复后：按钮点击 → daemon worker → 完成回调的**真实线程路径** 8 项——原 `QMetaObject.invokeMethod(Q_ARG(list,...))` 在本机 PySide6 无 QMetaType，完成回调从未触发，按钮永久卡"检查中"）
- 账号通道：`tests/test_account_provider.py`（72 项：默认链不含 / 日志导出无凭据 / 熔断解耦 / Guard 流程）

---

## 十二、剪贴板入队与批量粘贴

| 步骤 | 期望反馈 |
|---|---|
| 1. 复制工坊链接（浏览器 / 其他程序） | 自动解析、补全、加入下载队列；状态栏提示 5 秒「已从剪贴板加入下载队列：…」 |
| 2. 重复复制同一链接 | 去重（基于 `snapshot()` 的 queued/active/done 三组），不二次入队 |
| 3. 复制非工坊文本 | 零成本跳过（无弹窗、无日志记录原文） |
| 4. 批量粘贴（多个链接 token） | 按 token 解析、去重、跳过无效值 |
| 5. 设置页关闭开关后再复制 | 无任何反应；重新开启后即时恢复、无需重启 |

**自动化覆盖**：`tests/test_b3_clipboard.py`（34 项：默认开启与连接 / 解析入队 / 状态栏提示 / 重复触发去重 / 非工坊文本静默跳过 / 无原文缓存 / 失败静默 / 开关解绑 / 处理器二次配置 no-op / 重启重连 / 三组判重 / 设置页读写即时生效 / 批量粘贴 token 去重 / 搜索冷却改词作废）。
**offscreen 不可验证（`QClipboard.dataChanged` 不产生事件）——以下 5 条必须人工在真机确认**，清单见 `docs/clipboard_watch_notes.md`：浏览器复制链接 / 最小化到托盘时复制 / 复制非工坊内容 / 复制集合链接 / 关闭开关后复制。

---

## 十三、设置页

**GUI 锚点**：`settings_tab.py`（通道动态下拉按注册表生成 + tooltip「所选通道不可用时自动沿链回退，SteamCMD 永远兜底」；主题「跟随系统」读 `colorScheme()`；缓存 / 剪贴板 / 账号 / 调试 Tab 开关）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 切换主题 | 深色 / 浅色 / 跟随系统即时生效（系统配色切换即时换肤，不要求重启） |
| 2. 改通道 | 下拉写 config；不可用时沿链回退（SteamCMD 永远兜底） |
| 3. 通道未配置 | 显示「（未配置，链内自动跳过）」 |
| 4. 匿名态点「测试登录」 | 现场造独立引擎测完即弃，不与并发下载互污染（**[1.4.2 P0-3]**：原直接复用共享引擎会覆盖 `_proc` / 解除挂起的取消） |
| 5. 改「最大并发下载」并保存 | 立即生效（调低立即钳到新上限，调高逐级回升）**[1.4.2 P0-4]** |
| 6. 保存按钮 | 1.4.2 U7 起常驻吸底（当前在长滚动页最底部，易漏保存）**[P1]** |
| 7. 账号分组 | 常驻隐私明示「账号仅本地存储、仅本人使用」；登录态自动加入链位于匿名兜底之前 |
| 8. 显示调试面板开关 | 默认隐藏（config `debug_tab` 默认 False + `main_window` 条件 addTab）；重启后生效 |

**自动化覆盖**：`tests/test_gui_sweep.py`（设置页节：无压扁控件几何断言）· `tests/test_all_buttons.py`（全按钮点击，含「添加游戏目录」端到端——QInputDialog 桩签名 `(parent,title,label,items,...)` 取 `a[3]` 的历史教训）· `tests/test_account_provider.py` · `tests/test_providers.py`（89 项通道链）· `tests/test_throttle.py`（节流 / 并发）。

---

## 十四、托盘

**GUI 锚点**：`main_window.py` `_build_tray`（:139；**offscreen / 无桌面环境时 `isSystemTrayAvailable()` 为 False 直接跳过，`self._tray = None`**）· `act_show`（「显示主窗口」:154）· `act_quit`（「退出」:157 → `_real_quit` → `_do_real_quit` :175）· `_on_tray_activated`（单击或双击恢复 :237-240）· closeEvent 三分判定（可见+托盘可见 → hide() 最小化；`_force_quit` 或不可见 → 真正退出——卸载场景的 WM_CLOSE 必为卸载程序所发）· AppMutex `SWDM_SingleInstance_Mutex`（与 `installer/swdm.iss` 的 `AppMutex=` 同名）。

| 步骤 | 期望反馈 |
|---|---|
| 1. 可见窗口点 X | 最小化到托盘（不退出），托盘提示 |
| 2. 托盘菜单「显示主窗口」/ 单击或双击托盘图标 | 恢复窗口可见 |
| 3. 托盘菜单「退出」 | 隐藏态也能立即退出（`_real_quit` 不依赖 close() 转发，直接 `_do_real_quit`：停止下载管理器 + 保存配置 + 释放 AppMutex + `QCoreApplication.quit()`） |
| 4. 卸载程序关闭进程 | AppMutex 命中 → CloseApplications / AppMutex 双机制确保卸载不残留进程 |

**自动化覆盖**：`tests/test_uninstall_fix.py`（22 项：可见窗口 closeEvent 拦截 / 隐藏窗口放行 / `_force_quit` / `_real_quit` 真实路径 / 无托盘环境直接退出 / AppMutex 创建与释放 / 模拟 `_build_tray` 菜单接线 7a-7c 含**隐藏态触发退出**核心场景）· `tests/test_cross_features.py`（closeEvent 三分判定 + 卸载放行分支，offscreen 无托盘时注入假托盘）· `tests/test_batch3.py`（F4 托盔回归）。
**人工**：真实托盘的气泡通知、托盘态下复制链接入队、双击恢复——offscreen 不可验证，见 §十二与 `clipboard_watch_notes.md`。

---

## 十五、帮助入口（F1 用户手册）

| 步骤 | 期望反馈 |
|---|---|
| 1. 按 F1 或「帮助(&H) > 用户手册(&M)」 | `QDesktopServices.openUrl()` 打开随包 HTML；HTML 缺失回退 PDF |
| 2. 随包路径 | `build\dist\SWDM\_internal\manual\`（PyInstaller 数据目录），MD5 与 `docs/manual/dist/` 一致 |
| 3. 手册内容 | 九章节；界面状态与代码冻结后版本核对（含调试 Tab 默认隐藏、暂停/继续合并按钮、通道下拉与账号入口） |

**自动化覆盖**：`tests/test_manual.py`（源文件存在 / 版本绑定 / 图片存在 / 目录锚点 / HTML+PDF 产物 / 帮助入口）· `tests/test_t44_retest_gui.py`（帮助入口断言）。

---

## 十六、覆盖矩阵（场景 × 测试文件）

| # | 场景 | 自动化测试 | 覆盖度 | 无覆盖 = 人工补 |
|---|---|---|---|---|
| 1 | 游戏输入 / 联想 | test_user_interaction.py I1 · test_game_search.py · test_game_search_fix.py U1/U2 | 真按键 + 回退链全覆盖 | — |
| 2 | 中英文名适配 | test_user_interaction.py I4 | 基础覆盖 | **别名表扩充后需补用例（t3 落地后）** |
| 3 | 错误名回车不崩 | test_user_interaction.py I3/I3b | 全覆盖 | — |
| 4 | 退格 | test_user_interaction.py I2 | 全覆盖 | — |
| 5 | mod 搜索回车 | test_user_interaction.py I5 · test_search_fix.py · test_game_search_fix.py U3 | 全覆盖 | — |
| 6 | 翻页 / 滚动 | test_page_switch.py · test_scroll_repage.py · test_t34_nextpage_prefetch.py | 全覆盖 | — |
| 7 | 勾选批量下载 | test_checkboxes.py | 覆盖（U4 入队清空待加） | — |
| 8 | 标签过滤 | test_tag_bar.py · test_game_search_fix.py U4 · test_quick_search.py | UI 全覆盖 | **实网标签结构（test_tags.py 在 skip 基线，环境漂移时单跑定性）** |
| 9 | 详情页 | test_detail_dialog.py · test_t33_detail_cache.py · test_detail_perf.py | 逻辑全覆盖 | **视觉布局（几何量化兜底 + 人工目检）** |
| 10 | 下载 / 进度 / 速度 | test_download_stats.py · test_ap1_cancel_race.py · test_download_fixes.py · test_failure_reason.py · test_gui_sweep.py | 全覆盖 | — |
| 11 | 库管理 / 导入导出 | test_gui_sweep.py · test_t37_lib_updates.py · test_a6_check_updates_thread.py | 全覆盖 | **legacy 格式导入实网（test_legacy_format 在 skip 基线）** |
| 12 | 剪贴板 | test_b3_clipboard.py（34 项） | 逻辑全覆盖 | **真机 5 条：见 §十二 + clipboard_watch_notes.md** |
| 13 | 设置页 | test_gui_sweep.py · test_all_buttons.py · test_account_provider.py · test_providers.py · test_throttle.py | 全覆盖 | **主题"跟随系统"真实桌面配色切换** |
| 14 | 托盘 | test_uninstall_fix.py · test_cross_features.py · test_batch3.py | 逻辑 + 假托盘注入 | **真实托盘：气泡 / 托盘态复制 / 双击恢复** |
| 15 | 帮助 F1 | test_manual.py · test_t44_retest_gui.py | 全覆盖 | — |

---

## 十七、人工补测清单（汇总，交付前逐条过）

> **规则：没有自动化覆盖的场景 = 必须人工补。** 复测员（qa-indept）在两轮复测中逐条执行并记录到 `docs/retest_round*.md`。

1. **真实桌面剪贴板 5 条**（`docs/clipboard_watch_notes.md`）：浏览器复制链接入队 / 托盘态复制 / 复制非工坊内容 / 复制集合链接 / 关闭开关后复制。
2. **真实托盘 3 条**：最小化到托盘不退出；托盘「显示主窗口」/双击恢复；托盘「退出」隐藏态立即退出（进程在任务管理器消失）。
3. **offscreen 截图人工目检**：README 4 张 + 手册 5 张（本机读图工具全失效，自动化只验证"生成不崩溃 + 尺寸非空"）。
4. **真机 exe 冒烟**：`build\dist\SWDM\SWDM.exe` 复制到 `%TEMP%` ASCII 路径运行（沙箱陷阱见 dev_test §四.4），窗口标题版本号正确 + 8-10 秒稳定存活。
5. **实网场景**：storesearch 联想真实返回 / browse 列表真实分页 / 标签页实网结构 / legacy 导入（skip 基线脚本在网卡可用时单跑，PASS=环境确认，FAIL=逐项定性）。
6. **安装与卸载真机**：双击 `installer\Output\安装-SWDM.bat`（自动 taskkill → 拷 `%TEMP%` → 安装）；卸载走 CloseApplications + AppMutex 不残留进程；卸载数据目录复选框行为（三重安全校验：路径以 `\SWDM` 结尾 + 含特征文件 + 安装目录含源码时跳过）。
7. **GUI 视觉**：所有布局用几何量化（`mapTo` 相对坐标 + 显式间距断言）替代截图比对；无法量化的视觉改动提 ui-designer 评审。

---

## 十八、新增场景测试的写法（3 分钟上手）

**先读规矩**（`team_organization.md` §一 规矩 2.3）：**用户可见功能必须同时交付 QTest 真按键交互测试——API 层断言不算数**（1.4.1 的 86+111 项复测全是 API 层、用户上手撞 4 个交互 bug 的直接教训）。

```python
# 1. 头部套式照抄 test_user_interaction.py（见 dev_test_maintenance.md §3.1）
# 2. 网络全桩：在 MainWindow 构造前注入
#    from swdm.core import game_search as gs_mod
#    gs_mod.GameSearchClient = _FakeSearchClient      # 联想
#    swdm.gui.workshop_tab.BrowseWorker = _FakeBrowseWorker   # 列表
# 3. 真按键才叫交互测试：
#    QTest.keyClicks(ed, "garry")      # 逐字输入
#    QTest.keyClick(ed, Qt.Key.Key_Backspace)   # 退格
#    QInputMethodEvent(...)            # 输入法中文
# 4. 弹窗桩在断言内部捕获状态（模拟 QMessageBox 非真实阻塞，dev_test §四.9）
# 5. 结尾：
#    print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
#    sys.exit(0 if ok else 1)
```

判定以 `RESULT:` 行为准；Qt 退出码 -1073740791 为既有环境噪声（dev_test §四.3），**仅当 RESULT 行缺失且死在断言前才算真崩**。

---

## 十九、互链

- 流程与环境陷阱：`docs/process/dev_test_maintenance.md`
- 组织规矩：`docs/process/team_organization.md`
- 历史用户 bug 与复测：`docs/qa_report.md` · `docs/retest_round*.md` · `docs/clipboard_watch_notes.md`
- 1.4.2 在修项与期望行为来源：`docs/plan_1.4.2_draft.md` · `docs/research/plan_1.4.2_impl.md`
