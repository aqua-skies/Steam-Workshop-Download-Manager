# 竞品精读：Streamline Workshop Downloader — 三大 UX 机制

> 调研日期：2026-09-30
> 仓库：https://github.com/dane-9/Streamline-Workshop-Downloader
> 精读版本：commit `cb79b2ad`（2026-08-13）
> 调研性质：**只读调研**，未修改任何 SWDM 代码；本文为 docs/research/ 下新文件。
> 技术栈对照：Streamline = Python 后端（`web_backend.py` 4768 行 + `downloader.py`）+ pywebview 前端（`Files/webui/`：`app.js` 8474 行未压缩 + `styles.css` 4359 行 + `index.html` 228 行）。SWDM = Python 3.12 + PySide6 原生控件。

---

## 0. 总体结论（先看可迁移性）

| 机制 | Streamline 实现 | SWDM 现状 | 迁移可行性 | 工作量 |
|---|---|---|---|---|
| ① Command Palette (Ctrl+K) | 纯前端动作注册表 + 分段过滤 + 键盘导航 | 无（仅有 F1 手册快捷键） | **高** — 逻辑与框架无关，PySide6 原生可复刻 | 中（≈2-3 天） |
| ② 虚拟滚动队列 | 前端窗口化渲染 + 后端分页 API + 行级缓存 | `QTableWidget.insertRow()` 全量渲染 | **高** — Qt 有更原生的方案（`QAbstractItemModel` + `QTableView` 自带虚拟化） | 中（≈3-5 天） |
| ③ 日志分组 + 状态徽章 | 操作（operation）聚合 + 状态机推导 + 定向 delta 更新 | Python logging 控制台输出，无结构化日志 UI | **中高** — 数据流可照搬，渲染需对接 Qt 信号 | 中（≈3-4 天） |

**关键洞察**：Streamline 的三个机制本质都是"**把 UI 状态从全量重建改为增量更新 + 把计算推到数据层**"。SWDM 的 `downloads_tab.py` 目前是 `_update_row()` 每次重写 `QTableWidgetItem` 全字段（L167），队列变大或更新频繁时会成为瓶颈——这正好是三个机制要解决的同一类问题。

---

## ① Command Palette（Ctrl+K）

### 关键文件

| 文件 | 行号 | 内容 |
|---|---|---|
| `Files/webui/index.html` | L191-213 | 面板 DOM 骨架（overlay > card > filters/input/list） |
| `Files/webui/app.js` | L1933-2177 | **动作注册表** `getSharedCommands()` |
| `Files/webui/app.js` | L2183-2212 | 命令执行 `runCommandById()` / `bindCommandToButton()` |
| `Files/webui/app.js` | L2214-2609 | 分段（section）体系 + 过滤器持久化 |
| `Files/webui/app.js` | L2642-2711 | 列表渲染 + 选中 + 执行 |
| `Files/webui/app.js` | L2787-2914 | 开/关面板 + 键盘事件接线 `wireCommandPalette()` |
| `Files/webui/app.js` | L4901-5003 | **全局快捷键** `wireGlobalShortcuts()`（Ctrl+K / 双击 Shift） |
| `Files/webui/styles.css` | L1874-2052 | 面板样式（居中卡片 560px、z-index 105、列表 max-height 52vh） |

### 实现机制

**动作注册表**（数据驱动的命令清单，每次打开时动态重建）：

```js
// app.js L1933 — 每次打开面板时重新求值，因此 label 可以反映当前状态
function getSharedCommands() {
  const config = { ...state.settingsDefaults, ...(state.config || {}) };
  const showSearch = config.show_searchbar !== false;
  // ...
  return [
    { id: "open_settings", label: "Open Settings", hint: "Controls",
      keywords: "settings preferences options",
      run: async () => { await openSettingsEditor(); } },
    // label 动态化：同一命令根据状态显示不同文案
    { id: "start_or_cancel_download",
      label: state.isDownloading ? "Cancel Download" : "Start Download",
      hint: "Queue", keywords: "download start cancel",
      run: () => startDownloadBtn.click() },          // 复用已有按钮逻辑
    { id: "toggle_search_bar",
      label: showSearch ? "Hide Search Bar" : "Show Search Bar",
      hint: "Appearance", keywords: "search bar visibility",
      run: async () => { await applySettingsPatch({...}); } },
    // ... 共约 20 条命令
  ];
}
```

命令结构五元组：`id`（唯一键，按钮绑定也用它）/ `label`（显示文案，可随状态翻转）/ `hint`（分段标签 + 右侧灰色标注）/ `keywords`（搜索扩展词）/ `run`（异步执行体，失败自动 `addLog(..., "bad")`）。

**搜索过滤**（L2586-2620，两阶段）：

1. **分段 Scope 过滤**：当前页签（如 "Queue"）先把候选缩减到该分段；页签为 "All" 时用 `commandPaletteAllTypeFilters`（用户可配置"All 页签下显示哪些类型"）。
2. **多词模糊匹配**：查询拆空格、全小写，`haystack = label + hint + keywords + 分段名`，**每个词都要命中**（AND 语义）。无评分排序——按注册顺序展示，足够简单也足够快（命令规模 ~20 条，O(n·m) 无需索引）。

**分段（section）体系**（L2214-2281）：分段来自命令的 `hint` 字段（`Controls/Queue/Appearance/Tools/Help`），经 `normalizeCommandPaletteSectionKey()` 归一化（小写+非字母数字转下划线）。有少量隐式归类规则：`hint === "Current"`（主题类）归入 `appearance`，`queue` 分段同时出现在 `controls`。页签栏（tabs）可由用户在过滤器菜单里增删，选择通过 `update_settings` API **持久化到后端 config.json**（`command_palette_filters` / `command_palette_all_type_filters` 两个字段）。

**键盘导航**（两级，L2831-2851 + L4901-5003）：

- 面板内：`input` 的 keydown — `ArrowDown/Up` → `setCommandPaletteSelection(±1)`（clamp 到 `[0, len-1]`，只切 `.active` class，不重渲染）；`Enter` → `executeCommandPaletteAction()`；`Escape` → 关闭。
- 全局：`document` keydown — `Ctrl/Cmd+K` 开关面板（开则再按关闭且**不恢复焦点**）；双击 Shift（360ms 窗口内两次 keyup，且无修饰键）开关面板。此外面板打开时，即使焦点不在输入框，方向键/回车/字母键也被全局处理器拦截并**转发**到输入框（`applyCommandPaletteInputKey()` 用 `setRangeText` 模拟按键再派发 `input` 事件）——保证任何键击都进入搜索框。

**打开/关闭流程**（L2787-2809）：打开时记住 `document.activeElement`（焦点恢复用）→ 关闭所有其他弹窗 → 重建动作表 → 同步过滤器配置 → 清空输入 → 显示 overlay → `renderCommandPaletteList()` → 抢焦点（`focusCommandPaletteInput()` 用 rAF + 最多 8 次 16ms 重试的焦点争夺，对抗 WebView 的焦点抢占）。关闭时清空所有状态、从 DOM 移除列表、把焦点还回去。

**入口可用性**：除 Ctrl+K 外，标题栏有一个 chevron 下拉按钮（`commands-split-menu`）提供 "Command Palette" 菜单项——键盘用户和鼠标用户都照顾到。

### 数据结构

```js
let commandPaletteActions = [];      // 当前命令注册表（打开时重建）
let commandPaletteResults = [];      // 过滤后的结果
let commandPaletteSelectedIndex = 0; // 选中下标
let commandPaletteLastFocusedElement = null;  // 焦点恢复
let commandPaletteSectionFilter = "all";      // 当前分段
let commandPaletteAvailableSections = [];     // 动态计算的全部分段
let commandPaletteVisibleFilters = [];        // 用户启用的页签
let commandPaletteAllTypeFilters = [];        // All 页签下启用的类型
```

### 渲染策略

**全量重渲染 + DOM 复用为零**：每次输入变化就 `commandPaletteList.innerHTML = ""` 后用 `document.createElement` 重建所有结果项（`renderCommandPaletteList()` L2642）。每项是 `<button>` 内含 `label` span + `hint` span，`mouseenter` 同步选中（不滚动），`click` 执行。列表容器 `max-height: min(52vh, 430px)` + `overflow: auto` 滚动。

**为什么全量重建也可接受**：结果集 ≤ 命令总数（~20 条），每项 DOM 节点 ~3 个，重建成本 < 1ms。这是**小列表场景下"简单胜于聪明"的恰当取舍**——滚动定位用 `scrollIntoView({block: "nearest"})` 而非手动计算。空结果显示 "No commands found."。

### 可迁移到 PySide6 的方案草图

```
swdm/gui/command_palette.py  （新文件，约 350-450 行）
├── @dataclass Command:
│     id: str; label: str; section: str; keywords: str; run: Callable[[], None]
├── CommandRegistry:
│     ├── register(cmd)  — 静态注册 + 各 tab/服务自注册
│     ├── build() -> list[Command]  — 动态求值（label 可随状态翻转）
│     └── by_id(cid)
├── CommandPaletteDialog(QDialog):
│     ├── 顶部：QLineEdit（搜索） + 分段 tab 条（QHBoxLayout of QPushButton）
│     ├── 中部：QListWidget / 自绘 QListView（结果列表）
│     ├── 底部：Esc 提示 label
│     ├── keyPressEvent 转发：任意字母键注入搜索框（QKeyEvent 转字符串 append）
│     ├── 上/下/Enter/Esc 导航
│     └── focusOutEvent / 关闭时焦点归还 lastFocusedWidget
└── 接线：
      main_window.py: QShortcut(QKeySequence("Ctrl+K"), self)
      → palette = CommandPaletteDialog(registry, parent=self); palette.exec()
      双击 Shift：keyPressEvent 记录上次 Shift release 时间戳，360ms 内二次触发
```

命令清单建议（对齐 SWDM 现有功能，**不新增功能本体**）：打开设置页 / 切换标签页（工坊/下载/库） / 开始或取消下载 / 清除已完成 / 打开下载目录 / 导入导出 mod 包 / 切换主题 / 检查库更新 / 用户手册 / 关于。其中"开始/取消下载""清除已完成"等复用现有按钮的 `.click()` 等价方法，与 Streamline 的 `run: () => startDownloadBtn.click()` 同策略——**命令层不重复实现业务逻辑**。

**迁移注意点**（Qt 特有）：
- 对话框用 `QDialog` 模态 + `setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)`，居中于父窗口上方（`move()` 到父窗口顶部 1/4 处，模仿 64px top padding）。
- QListWidget 自带键盘导航（`QAbstractItemView` 的 `Up/Down/Enter`），只需 `installEventFilter` 处理 Escape 和字母键转发，**比 Streamline 的手动实现更省代码**。
- 分段页签持久化对应 SWDM 的 `core/config.py` 读写（config 落地两行）。
- 测试：`tests/test_command_palette.py` — 注册表完整性、过滤 AND 语义、状态翻转 label、执行回调、Ctrl+K 快捷键（`QTest.keyClick`）。

**工作量估计**：**2-3 天**（其中半天处理焦点/快捷键细节，半天写测试）。风险低：纯新增模块，不动现有逻辑。

---

## ② 虚拟滚动队列（数千 mod 不卡）

### 关键文件

| 文件 | 行号 | 内容 |
|---|---|---|
| `Files/webui/app.js` | L110-113 | 常量：行高 20px / overscan 14 行 / fetch 缓冲 80 行 / 单页上限 1200 |
| `Files/webui/app.js` | L130-145 | 虚拟化状态机（窗口、页缓存、查询键） |
| `Files/webui/app.js` | L4256-4380 | `getVirtualQueryPayload/Key` + `ensureBackendWindowLoaded()`（异步分页） |
| `Files/webui/app.js` | L4382-4426 | `patchStableQueueViewport()`（原地更新快路径） |
| `Files/webui/app.js` | L4428-4497 | **`renderQueueViewport()` 核心渲染** |
| `Files/webui/app.js` | L4521-4542 | 滚动事件接线 `wireQueueVirtualization()` |
| `Files/webui/app.js` | L3825 / 4101 / 4245 | 行工厂 / 行更新 / 行缓存裁剪 |
| `web_backend.py` | L901-992 | **后端分页 API `get_queue_page()`** + 查询缓存 |

### 实现机制

**双模式**：`virtualBackendEnabled = state.apiAvailable`。API 可用时走"后端分页"（队列真相在后端，前端只持有当前页）；API 不可用时降级为"前端全量"（`virtualItems = getSortedQueue(getFilteredQueue())`）。这个降级路径是亮点——离线/无桥接时功能不丢失。

**固定行高窗口化**（`renderQueueViewport()` L4428）：

```js
const rowHeight = QUEUE_ROW_HEIGHT;                       // 20px 固定
const rowsInView = Math.ceil(viewportHeight / rowHeight);
let startIndex = Math.floor(scrollTop / rowHeight) - VIRTUAL_OVERSCAN_ROWS;  // 上 overscan 14 行
let endIndex   = Math.min(total, startIndex + rowsInView + VIRTUAL_OVERSCAN_ROWS * 2);
```

DOM 里只保留 `[startIndex, endIndex)` 的行，前后各塞一个**垫片行**（`createSpacerRow()`）：`height = startIndex * 20px` / `(total - endIndex) * 20px`。垫片撑出真实滚动条高度，使滚动条 thumb 与数据量一致。整批行装入 `DocumentFragment` 后 `queueBody.replaceChildren(fragment)`（一次性替换，只触发一次 reflow）。

**滚动节流**：scroll 事件 → `virtualScrollQueued` 标志 + `requestAnimationFrame` 合并（每帧最多渲染一次，56fps 以下不堆积）。

**后端分页**（`ensureBackendWindowLoaded()` L4296）：视口所需窗口前后各扩 80 行（`VIRTUAL_FETCH_BUFFER_ROWS`）去后端取，`limit = clamp(80, 视口+160, 1200)`。**竞态防护**：每次 fetch 自增 `virtualBackendFetchId`，响应回来时若 id 不匹配则丢弃（快速滚动时的旧请求作废）。**覆盖检查**：若现有页 `[pageStart, pageEnd)` 已覆盖所需窗口则跳过请求。查询（filter/search/sort）变化时以查询键（六元组 `\x1f` 连接的字符串）判等，变化即重置窗口。

**后端查询缓存**（`web_backend.py` L933-982，`get_queue_page()`）：过滤/搜索/排序结果**整组缓存**，键为六元组 + 队列 revision 号；任何队列变更（`_emit_event("queue")` → `_queue_revision += 1`）让缓存整体失效。分页只做 `[offset:offset+limit]` 切片 + `dict(mod)` 浅拷贝。单页硬上限 2000（`limit = max(1, min(2000, limit))`），前端再 clamp 到 1200。返回 `{success, offset, limit, total, items, stats, regex_error}`——**stats 随页返回**，前端不必为拿计数再全量拉取。

**行级缓存**：`state.rowCache: Map<modId, HTMLTableRowElement>`——行 DOM 按 modId 复用，滚回来时 `createQueueRow()` 只执行一次。`pruneRowCacheToVisible()` 在每次渲染后裁掉不可见的条目（同时从 DOM 移除），控制缓存增长。

**更新快路径**（`patchStableQueueViewport()` L4382）：强制刷新时，若窗口未变且渲染的行序与期望行序（按 modId 逐一比对）完全一致，则**不重建 DOM**，只对每行调 `updateQueueRow()` 原地改文本 + 调两个垫片高度。这把"队列状态刷新"从 O(n) DOM 重建降为 O(n) 文本赋值——`updateQueueRow()` 内部还有 **signature 短路**（L4120：`row._signature` 八元组相等则跳过全部单元格重写）。

**拖拽排序的窗口保护**（L4443-4449）：拖拽重排期间强制扩展窗口覆盖 `[lastVirtualStart, lastVirtualEnd]`——否则自动滚动会把被拖块裁出视口导致渲染崩溃。这是虚拟化+交互相结合时的典型坑，Streamline 显式处理了。

### 数据结构

```js
let virtualItems = [];            // 降级模式的全量数据
let virtualBackendPageStart/End;  // 当前页窗口 [start, end)
let virtualBackendPageItems = []; // 当前页数据（normalizeQueueItem 规范化后）
let virtualBackendTotal = 0;      // 后端报告的总数（滚动条高度来源）
let virtualBackendQueryKey = "";  // 六元组查询键
let virtualBackendFetchId = 0;    // 竞态防护计数器
let lastVirtualStart/End = -1;    // 上次渲染窗口（变化检测）
// 行规范化（L2968）：预计算搜索用小写字段，分离展示值与匹配值
```

后端侧：`self.download_queue`（真相）+ `self._queue_query_cache`（视图缓存）+ `self._queue_revision`（失效号）+ `self.events`（变更通知）。

### 渲染策略

**核心数字**：10000 条队列、视口 600px → 实际渲染 30 + 28 overscan = **58 行 DOM**，垫片 2 行。滚动时每帧至多一次 fragment 替换。行高必须是**常量 20px**（写进 CSS 变量 `--queue-row-height`）——这是窗口计算 O(1) 的前提；变高行需改为二分前缀和（Streamline 未做，不需要）。

**状态徽章宽度动画**（`animateQueueStatusChange()` L3939）：状态变 Downloading/Downloaded 时记录 badge 变化前宽度，用 Web Animations API 做宽度补间，避免文字变化导致布局跳动。同类连续动画用 500ms 内的序列计数器区分。`prefers-reduced-motion` 下全部跳过。

### 与 SWDM 的对照

SWDM `downloads_tab.py` 现状：`QTableWidget(0, len(HEADERS))` + 每任务 `insertRow()` + `_update_row()` 全字段重写。QTableWidget **本身就是虚拟化的**（Qt 的 item view 只绘制可视区域），所以"卡"不在渲染而在**数据通路**：每个状态更新走信号 → `_update_row` 重写 N 个 `QTableWidgetItem`。因此 SWDM 要借鉴的不是"虚拟滚动"（白送），而是**增量更新协议 + 行 signature 短路 + 后端分页**。

### 可迁移到 PySide6 的方案草图

分两层，可选第一层先行：

**层 1（低成本，收益直接）——增量状态更新协议**：
```
现状：engine 状态变化 → 信号携带 job → downloads_tab._update_row(job) 全字段重写
改进：
1. DownloadJob 增加 _signature（status/retry/provider/failure_detail 等八元组 join）
2. _update_row 内先比 signature，相等则 return（对齐 updateQueueRow L4120）
3. 状态徽章单元格只在 status 变化时 setItem/setText，并触发一次样式刷新
   （QSS 里对 "Downloading" 状态列加 pulse 动画 / 彩色背景，对齐 is-active::before）
```

**层 2（队列规模真正变大时，如"下载整个工坊"功能）——分页 + 必要时 QTableView**：
```
若引入"队列整个工坊"（Streamline 有此功能）导致队列过万：
1. 数据层：QueueStore 提供 page(filter, search, sort, offset, limit)
   — 模仿 web_backend.get_queue_page：view 缓存 + revision 失效 + stats 随页返回
   — SWDM 侧直接在内存做（同进程无需 RPC），dict 浅拷贝出页
2. 视图层：QTableWidget 换 QTableView + QAbstractTableModel
   — data() 按 index 即时取 humanities，rowCount = total
   — 滚动条天然准确（Qt 按 rowCount 计算），无需垫片行
   — 搜索/过滤变化 → beginResetModel() + 重新分页
3. 懒加载元数据：队列先入 mod_id/url，详情（标题/预览图）滚入可视区再异步富化
   — Streamline 的 item_metadata_deferred 动作就是这个思想
```

**迁移注意点**：
- Qt 的虚拟化要求 `rowCount` 准确但**不要求所有行有数据**——`data()` 被调用时才需要返回值，这与 Streamline 的按需 `getVirtualItemAt()` 同构。
- SWDM 已有的"分类/搜索/排序"三件套可以直接映射到查询六元组。
- 测试：1 万行假数据滚动帧时（QElapsedTimer 测 data() 调用频率）、signature 短路命中率、窗口边界（滚到末尾 total-1）、过滤切换时 revision 失效。

**工作量估计**：层 1 = **1-1.5 天**（含测试）；层 2 = **3-5 天**（含 QTableView 迁移与全部回归）。层 2 建议与"集合/整页批量下载"功能捆绑排期，单独排性价比低（QTableWidget 在数千行内不构成瓶颈）。

---

## ③ 日志分组 + 状态徽章的数据流与渲染

### 关键文件

| 文件 | 行号 | 内容 |
|---|---|---|
| `web_backend.py` | L401-451 | 事件总线 `_emit_event` / `poll_events` / 节流刷新 |
| `web_backend.py` | L453-490 | `_next_operation_id()`（`prefix-ms-seq`）+ `log()`（携带 operation/action/context） |
| `Files/webui/app.js` | L99-106 | 时间线状态：top items / 分组 Map / 计数 / 上限 2000 |
| `Files/webui/app.js` | L441-645 | 操作标签/摘要/状态机推导 (`formatOperationSummary`, `deriveOperationState`) |
| `Files/webui/app.js` | L700-788 | 裁剪 (`pruneLogTimeline`) / **分组插入 (`addEntryToGroupedTimeline`)** |
| `Files/webui/app.js` | L837-1007 | 渲染调度 + 列表 DOM 工厂 + `renderLogTimeline()` |
| `Files/webui/app.js` | L1018-1041 | `addLog()` 入口（滚动锚点决策） |
| `Files/webui/app.js` | L7907-7981 | **`applyQueueStatusEvent()` 队列徽章定向更新** |
| `Files/webui/app.js` | L8069-8107 | 轮询循环 `pollEvents()`（250ms） |
| `Files/webui/styles.css` | L3653-3729 | 状态徽章六态样式（pulse 动画） |
| `Files/webui/styles.css` | L4025-4212 | 日志行/分组/子行/tone 徽章样式 |

### 实现机制

#### A. 数据流：事件总线（后端 → 前端）

```
后端任意线程                          前端
────────────────                     ──────────────
self.log(msg, tone, source,          setInterval 250ms → pollEvents()
   action, context,                      → callApi("poll_events", lastEventId)
   operation_id)                          → handleEvent(event) 逐条
   → _emit_event("log", payload)             type=="log"      → addLog(...)
   → events.append({id,type,                 type=="queue"    → scheduleQueueRefresh(true)
     payload,timestamp})                     type=="queue_status" → applyQueueStatusEvent(payload)
                                             type=="download" → 状态机 + 按钮文案
   type=="settings" → 全量重应用配置
事件数组超 3000 → 裁到 1500（保尾部）
poll_events(last_id) → [evt for evt if id > last_id]
```

**队列刷新节流**（`_emit_queue_refresh_throttled` L416）：`queue` 事件触发前端整表重渲染，昂贵——因此后端设最小发射间隔（`_queue_emit_interval_sec`），间隔内的请求由一个 daemon `threading.Timer` 延迟到间隔末尾补发。即"高频队列变更 → 合并为低频刷新"。`queue_revision` 在此自增，用于让视图缓存失效。

#### B. 日志分组：操作（operation）聚合

每条结构化日志可带 `operation_id`（后端生成：`queue-build-1735651200000-7` 格式，前缀可读 + ms 时间戳 + 序列号）。前端按 operation_id 聚合：

- **无 operation_id** → 独立单行（`kind: "single"`）。
- **有 operation_id** → 进分组（`kind: "group"`）。`context.parent_operation_id` 支持子操作归并到父操作（`logOperationParents` Map）。
- **进度条目折叠**：`download_progress` / `queue_build_progress` / `pages_fetched` 三类条目在分组内**原地更新**（id 固定为 `progress:{opId}:{kind}`）——同一个进度只占一个条目位置，不会刷屏。这是"数千行下载日志"不淹没用户的关键。
- 分组总是置顶（`moveGroupTopItemToFront`），最新活动在最上面。`queue-build` 前缀的分组会被重打标签为 "Queue Build"。

#### C. 分组状态徽章：状态机推导

`deriveOperationState(currentState, entry)`（L556）——逐条条目滚动推导分组的聚合状态，优先级：

```
1. context 显式声明（operation_state: canceled/error/warn/done/run）— 最高优先
2. 当前已是 canceled/error → 粘性保持（终态不可逆）
3. tone=warn → warn；warn 粘性
4. action 含 cancel → canceled
5. tone=bad → error；tone=good → done
6. 默认保持当前 / run
```

状态 → 徽章：`run → RUN(蓝)` / `done → DONE(绿)` / `error → ERROR(红)` / `warn → WARN(橙)` / `canceled → STOP(黄)`。分组行显示：`▸/▾` 展开标记 + 时间 + **状态徽章** + "操作标签: 最后一刻摘要" + `N logs` 计数。点击展开/折叠子条目（子行缩进 16px、淡化）。

**摘要文案机**（`formatOperationSummary` L467）：按条目的 `action` 映射成人话，例如 `download_progress → "12/50 processed · 10 downloaded · 2 failed"`、`pages_fetched → "3/8 pages fetched, 1 failed"`、`queue_input_failed + reason → 对应中文级诊断`。context 里带计数（added/skipped/finished/total/completed/failed）。

#### D. 队列状态徽章：定向 delta 更新（不重渲染整表）

`queue_status` 事件只带一个 mod 的变化（`{mod_id, status, retry_count, max_retries, failure_detail, previous_status?, invalidate_queue_view?}`）。前端 `applyQueueStatusEvent()`：

1. 在 `state.queue` 和当前分页数据里**定位该 item** 并就地改字段（O(n) 查找，n = 页内条数）。
2. 若 `invalidate_queue_view` 为真（增删/重排等结构变更）才走整表刷新；否则 → `renderQueueViewport(true)` 走 **patchStableQueueViewport 快路径**（DOM 不重建，只改行内文本）。
3. 触发徽章宽度补间动画。

**徽章设计**（CSS L3653-3729）：药丸形（`border-radius: 999px`，10px 字号），六色语义：`is-neutral/muted`（灰，排队/取消）/ `is-active`（蓝 + **CSS pulse 脉冲点** 1.15s 循环，下载中）/ `is-success`（绿）/ `is-warning`（橙，重试）/ `is-danger`（红，失败且**可点击**——role=button、tabindex=0、点击弹出 failure_detail 详情对话框）。失败徽章因此是**进入错误诊断的入口**，不只是装饰。

#### E. 日志时间线渲染策略

- **合并渲染调度**：`scheduleLogTimelineRender()` 用 rAF 合并；`preserveScroll` 标志在一次合并窗口内 OR 累积。
- **滚动锚点**：渲染前若用户不在底部（`scrollTop > 2`），捕获第一个可见行（`data-log-key`）与其偏移，渲染后按 key 找回该行并补偿 scrollTop——**用户阅读历史时新日志不会拽走滚动位置**；在底部则自然跟随。
- **总量上限**：`MAX_LOG_TIMELINE_ENTRIES = 2000`，超限从最旧 top item 逐条淘汰；分组整体清空时级联删除父子映射。分组淘汰逐条 shift 并 `recomputeLogGroup()` 重推状态（保持分组状态与条目一致）。
- **分类过滤器**：按 `source`（system/ui/download/clipboard…）过滤，配置持久化。
- 双击单行 → `showFullLogMessageDialog()`（完整消息弹窗，防截断）。

### 数据结构

```js
// 日志时间线（三表结构）
let logTopItems = [];                 // 顶层序列（single | group 引用），新 → 旧
let logGroupsByOperation = new Map(); // operationId -> group
let logOperationParents = new Map();  // childOpId -> parentOpId
let logEntrySeq = 0;                  // 条目自增 id
let logTimelineEntryCount = 0;        // 总数（淘汰依据）

// group 结构
{ operationId, prefix, label, source, entries: [], expanded: false,
  state: "run"|"done"|"error"|"warn"|"canceled", lastMessage, updatedAt }

// entry 结构（addLog L1025）
{ id, message, tone: "info"|"good"|"bad"|"warn", timestampMs,
  source, action, operationId, context }
```

### 可迁移到 PySide6 的方案草图

SWDM 现状：`swdm/core/logger.py` → Python logging → 控制台/文件；`downloads_tab.on_engine_log(line)` 只 debug 打印。没有面向用户的结构化日志 UI。

**方案：操作日志面板（可作为 1.4.x 新增的"活动"面板，或并入调试页）**

```
swdm/core/activity.py（新）：
├── @dataclass LogEntry:
│     id, message, tone, source, action, operation_id, context(dict), ts
├── @dataclass OpGroup:
│     op_id, prefix, label, entries[], expanded, state, updated_at
├── ActivityLog（QOBJECT，单例，线程安全 like web_backend 的 events_lock）：
│     ├── log(msg, tone, source, action, context, op_id)
│     ├── operation_id(prefix) -> "queue-build-{ms}-{seq}"
│     ├── add_entry_to_grouped_timeline(entry)  — 直接移植 L726-788 逻辑
│     │     含 progress 条目折叠（download_progress 原地更新）
│     ├── derive_op_state(cur, entry) — 移植 L556 状态机
│     ├── prune_to(2000)  — 移植 L700
│     └── signal entry_added(LogEntry) / group_updated(OpGroup)
│         （替代 Streamline 的 250ms 轮询——Qt 信号天然推送，比轮询更优）

swdm/gui/activity_panel.py（新）：
├── QListView + 自定义 QAbstractListModel（或 QTextBrowser + 富文本）
│     model.data() 按 top_items 渲染：group 行 → 折叠箭头+徽章+摘要+计数
│     展开时插入子条目（beginInsertRows）
├── 滚动锚点：QScrollBar.value() != maximum() → 保持 firstVisibleRowIndex
├── 分类过滤 QComboBox（all/system/ui/download）
└── 双击 → 详情对话框（复用 detail_dialog 的样式）

动作埋点（对齐 SWDM 已有的操作流）：
├── 入队流程：op_id=queue-input-*，action=queue_input_started/accepted/failed
├── 整页/集合扫描：op_id=queue-build-*，action=pages_fetched("3/8 pages")
├── 下载批次：op_id=download-*，action=download_progress("10/50 processed")
└── SWDM 的 failure_reason.py 可以作为 context.reason 输入摘要文案

状态徽章（复用①层1的 signature 更新）：
├── downloads_tab 状态列改用 QLabel + QSS 动态类（setStyleSheet per state）
├── QSS: 六色药丸 + 下载中 pulse（QPropertyAnimation on opacity 或 GIFless 双圆点）
└── 失败徽章 setCursor(PointingHand) + mousePressEvent → failure_detail 弹窗
    （对齐 is-danger[role=button] 的可点击诊断入口）
```

**迁移注意点**：
- **不必轮询**：Streamline 轮询是因为跨进程桥接；SWDM 同进程，`QtCore.Signal` 直接推送，实时性更好且省掉定时器。
- **线程安全**：`web_backend` 用 `events_lock` 保护事件数组；SWDM 的 ActivityLog 信号发射必须通过 `QtCore.QMetaObject.invokeMethod` 或队列连接（SWDM 已有 `gui/workers.py` 的跨线程模式可复用，downloads_tab L117 注释明确"跨线程操作 QTableWidget 会冻结"）。
- **与既有日志的关系**：Python logging（文件/控制台）保留给开发；ActivityLog 面板面向用户，两者并行——Streamline 也是 `web_backend.log()` 与自身 stdout 日志分离。
- **摘要文案本地化**：`formatOperationSummary` 的 action→文案表在 SWDM 应放 `swdm/core/failure_reason.py` 同类位置，支持中文（Streamline 只有英文）。
- 测试：分组聚合（同 op_id N 条 → 1 分组 N 子条）、进度折叠（10 条 download_progress → 1 条目）、状态机终态粘性（error 后不回退）、滚动锚点保留、2000 上限淘汰、分类过滤。

**工作量估计**：**3-4 天**（ActivityLog 核心 1.5 天 + 面板渲染 1.5 天 + 埋点改造 0.5-1 天 + 测试）。依赖少，可与①并行开发。

---

## 附录 A：三机制的公共基础设施（可一并借鉴）

1. **事件总线的 revision 失效模式**：`_queue_revision` 单调整数 + 视图缓存键校验（`web_backend.py` L935-947）——SWDM 的 `api_cache.py` 已有类似思想（见记忆：命中前必须深拷贝），可推广到队列视图缓存。
2. **rAF/节流五连**：滚动渲染（rAF 合并）、队列刷新（后端 Timer 节流）、日志渲染（rAF 合并）、搜索输入（`SEARCH_RENDER_DEBOUNCE_MS = 180`）、双击 Shift（360ms 窗口）——Qt 侧对应 `QTimer.singleShot` + `QElapsedTimer`，模式直接搬。
3. **竞态守卫 fetchId 模式**：异步分页请求的 token 校验（L4320/L4336）——Qt 侧 `QThreadPool` + 自增 token，取消旧结果。
4. **垫片行思路**：固定行高 + 前后垫片是 DOM 方案；Qt 的 item view 天然不需要，但**概念上对应** QAbstractItemModel 的 rowCount 准确性。

## 附录 B：精读引用清单（行号均为精读版本 cb79b2ad）

- 命令注册表：`app.js:1933-2177`；过滤：`app.js:2586-2620`；导航/接线：`app.js:2642-2914`；全局快捷键：`app.js:4901-5003`；DOM：`index.html:191-213`；样式：`styles.css:1874-2052`
- 虚拟滚动常量：`app.js:110-113`；核心渲染：`app.js:4428-4497`；分页窗口：`app.js:4296-4380`；快路径：`app.js:4382-4426`；滚动接线：`app.js:4521-4542`；行缓存裁剪：`app.js:4245-4254`；后端分页：`web_backend.py:901-992`
- 日志分组：`app.js:441-788`；渲染：`app.js:837-1041`；状态机：`app.js:556-645`；队列徽章更新：`app.js:7907-7981`；事件分发：`app.js:7983-8067`；轮询：`app.js:8069-8107`；后端事件总线：`web_backend.py:401-490`
