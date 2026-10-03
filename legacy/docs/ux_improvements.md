# SWDM 1.3.7 — 竞品 UX 研究 + 可执行改进清单

> 产出角色：竞品研究（ux-researcher）
> 日期：2026-09-24
> 研究对象：Workshop 下载器 / mod 管理器 / SteamCMD GUI 包装器四类竞品
> 结合本程序：SWDM 1.3.5（PySide6，五标签页：工坊浏览 / 下载 / 模组库 / 设置 / 调试）
> 竞品底稿：`research/competitor_analysis.md`（功能层全景，本报告聚焦 **UX 层**：交互响应手感、视觉层级、操作步长、错误提示）

---

## 0. 竞品 UX 坐标（四类工具的交互范式）

| 类别 | 代表 | 交互范式核心 | SWDM 现状对比 |
|---|---|---|---|
| 网页下载器 | steamworkshopdownloader.io 系（已大批倒闭） | 粘贴链接即识别 → 元数据预览 → 一键下载；极短操作链 | ✅ 已有「导入 URL/合集」；❌ 无剪贴板自动识别、无下载前预览确认 |
| 图形化下载器 | **WorkshopDL**（单文件 exe） | 剪贴板 URL 自动识别；小文件 WebAPI / 大文件 SteamCMD 自动切换；首次启动自初始化 | ✅ 双通道已实现；❌ 无剪贴板监听、下载确认靠弹窗而非预览面板 |
| SteamCMD GUI | **SteamCMD_GUI2 / SCMD2 / Streamline / PyShopDL** | stdout 正则解析驱动进度条；失败自动重试（steamcmd 随机超时是公认刚需）；队列化管理 | ✅ 进度解析+自动重试已实现；❌ **失败行无手动「重试」按钮**、无队列排序 |
| 专业 mod 管理器 | **Vortex / Arma 3 Launcher** | 卡片化 mod 列表 + 缩略图；启用开关/加载顺序；冲突检测给「一键修复」按钮；Profile 切换；主题 | 部分：卡片化仅存在于未接入的 `widgets.ModCard`；库页仍是纯文本列表；无加载顺序/Profile |

**一句话结论**：SWDM 的**功能覆盖**已超过多数 SteamCMD GUI 竞品（依赖解析、冲突检测、标签过滤、SQLite 库均属稀有能力），但**视觉层级与操作步长**仍停在「命令行工具加了一层皮」的阶段——这是当前与 Vortex/WorkshopDL 体验差距最大、也是 1.3.7 最容易拿分的地方。

---

## 1. 现状审计：四个维度的问题清单

审计方式：通读 `swdm/gui/` 全部 11 个源文件 + `app.py`，逐页面核对信号连接与布局结构。

### 1.1 交互响应手感

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| R1 | **排序下拉切换后列表不刷新**——用户改了排序只能再手动点「搜索」才生效 | `workshop_tab.py:425-428` 创建 `sort_combo` 后**无任何 `currentIndexChanged.connect`** | 🔴 高（真实 bug） |
| R2 | **卡片无 hover 视觉反馈**，悬停只有 400ms 后的详情预取，画面毫无变化 | `ModCardWidget` 无 hover 样式（对比 `widgets.ModCard` 已备好 hover 边框却未被工坊页使用） | 🟠 中高 |
| R3 | **关键词搜索必须回车/点按钮**——标签栏变化即时刷新，关键词却要两步 | `workshop_tab.py:422` 仅连 `returnPressed`；`search_edit` 无 `textChanged` 防抖 | 🟠 中高 |
| R4 | **全屏加载遮罩遮挡整个列表区**，翻页期间无法看旧内容、无法操作；快速翻页时遮罩反复闪烁 | `LoadingOverlay` 盖住 `list_scroll` 全部（`workshop_tab.py:470`） | 🟠 中 |
| R5 | **下载完成无任何主动提示**——用户在别的标签页只能自己想起来去看 | 无 `QSystemTrayIcon`、无 `showMessage`、无窗口标题进度（grep 全库无系统托盘实现；README 的「系统托盘」为愿景） | 🟠 中高 |
| R6 | **无任何键盘快捷键** | grep `QShortcut|setShortcut` 全库 0 命中 | 🟡 中 |
| R7 | 详情弹窗预览图加载中只显示文字「图片加载中…」，无骨架占位 | `detail_dialog.py:669-675` | 🟢 低 |
| R8 | 主题切换需重启程序才完整应用（提示文案已写明，但体验断裂） | `settings_tab.py:417-419`；`main_window._apply_theme` 只在启动时执行 | 🟡 中 |

### 1.2 视觉层级

| # | 问题 | 证据 |
|---|---|---|
| V1 | **工坊列表是「无容器行」**：白板背景上一条条文本+按钮，没有卡片边界、没有分区，信息层级完全靠字号硬撑 | `ModCardWidget` 无 QFrame/背景/边框；已有的 `widgets.ModCard`（带 `CARD_BG`/圆角/hover 边框）被闲置 |
| V2 | **详情弹窗配色与主窗口不一致**：主窗口强调色 `#7c5cff`（蓝紫），弹窗按钮主色 `#2f6fd0`（纯蓝），按钮圆角 5px vs 8px | `detail_dialog.py:642-649` vs `styles.py:94-106` |
| V3 | **下载页「物品 ID」列对普通用户无意义却占位最宽**（`ResizeToContents`，10 位 ID ≈ 90px），真正重要的「标题」列反而被挤压 | `downloads_tab.py:64` |
| V4 | 模组库是**密集单行文本**：`✓ 标题 ★ [分类] — 42.3 MB · 4000 · 123456789`，缩略图只是 48px 小图标，无卡片化、无启用开关控件 | `library_tab.py:190-207` |
| V5 | 底部操作栏 6 个按钮全部 `secondary` 样式平铺，主操作（启用/禁用）与低频操作（导入/导出/刷新）视觉同级 | `library_tab.py:104-137` |
| V6 | 无任何**空态设计**：列表为空只有状态栏一行 11px 小字；下载队列为空时表格光秃秃 | `workshop_tab.py:860-865`；`downloads_tab` 无空态 |
| V7 | `tag_edit` 隐藏输入框（逗号分隔）与标签栏 chip 表达同一功能，两处 UI 并存，新人困惑 | `workshop_tab.py:430-433` + tag_bar |

### 1.3 操作步长

| # | 问题 | 现状步长 | 竞品步长 |
|---|---|---|---|
| S1 | **下载失败后重新下载** | 回工坊页 → 找到卡片 → 点下载（3+ 步，且卡片可能不在当前页） | 竞品一律在失败行提供「重试」按钮（1 步） |
| S2 | **批量取消** | 「取消全部」直接执行，**无确认对话框**（危险操作零防护） | Vortex/Arma3 对破坏性操作一律二次确认 |
| S3 | **修改 mod 目录** | 工坊页有「目录…」按钮（好），但模组库页改目录要去设置页表格选行 | — |
| S4 | **导入合集** | 「更多」菜单 → 粘贴对话框 → 手动解析 | WorkshopDL：剪贴板自动识别，打开程序即填入 |
| S5 | 翻页只有上一页/下一页，无页码、无总页数、无跳页 | 想回第 5 页只能连点 4 次 | 网页下载器普遍有页码 |
| S6 | 查看下载文件位置 | 模组库：右键 → 在资源管理器打开 | 下载页完成行也可直接给「打开目录」 |
| S7 | 队列内无排序/优先级调整，先下后下只能靠入队顺序 | — | Streamline 队列可拖拽管理 |

### 1.4 错误提示

| # | 问题 | 证据 |
|---|---|---|
| E1 | **下载失败只在「信息」列显示一行文本**，无操作引导（用户不知道还能重试） | `downloads_tab.py:140-172`，失败行操作列只是「移除」 |
| E2 | **「取消全部」无确认**（同 S2，错误提示维度即「危险操作无拦截」） | `downloads_tab.py:265-266` |
| E3 | 限流（429）错误信息已有明确等待建议（好，`workers.py:64-69`），但**不给出「自动等待后重试」的状态可见性**——用户只看到失败 | 遮罩/状态栏未区分「排队重试中」与「真失败」 |
| E4 | 模组库删除是**永久删除**，无软删除/回收站，误删无法恢复 | `library_tab.py:284-291` 直接 `delete(remove_files=True)` |
| E5 | 列表加载失败弹 `QMessageBox.critical`（模态打断流操作），且快速连续操作时 `_on_list_failed` 已做了 pending 优先处理（好），但**失败原因不区分网络/限流/游戏无工坊页** | `workshop_tab.py:795-802` |
| E6 | 全局异常弹窗 `QMessageBox.critical(None, ...)` 无父窗口，可能被主窗口遮挡 | `main_window.py:146-150` |
| E7 | 登录测试结果用内联富文本 span 硬编码颜色，浅色主题下可读性未验证 | `settings_tab.py:350-354` |

---

## 2. 改进清单（可直接执行）

> 每条含：**问题 → 竞品做法 → 具体改法 → 影响文件 → 验证**。优先级：P0 = 1.3.7 必做（小改动大收益/真 bug）；P1 = 拉开差距；P2 = 打磨。

### P0-1 修复排序下拉不刷新（真 bug）

- **问题**：切换「热门趋势/最新发布/…」后列表纹丝不动，用户以为排序坏了（R1）。
- **竞品做法**：所有浏览类工具的排序控件变更即刷新；Vortex 的排序下拉即时重排 mod 列表。
- **具体改法**：`workshop_tab.py` `_build()` 中，`self.sort_combo` 创建后补一行：
  ```python
  self.sort_combo.currentIndexChanged.connect(lambda _i: self._refresh_list())
  ```
  `_refresh_list()` 已含 350ms 去抖，连点多种排序只会发最后一次请求，不会触发 429。
- **影响文件**：`swdm/gui/workshop_tab.py`（约 425 行，1 行新增）
- **验证**：启动 GUI，切换排序，观察列表是否按新维度重排；`tests/test_gui.py` 截图对比顺序变化。

### P0-2 下载失败行加「重试」按钮

- **问题**：失败后只能回工坊页重找卡片重下，卡片若不在当前页几乎无法重试（S1/E1）。
- **竞品做法**：SteamCMD_GUI2/SCMD2 等包装器把「steamcmd 随机超时自动重试」做成刚需；失败行给显式 Retry 按钮；Vortex 下载失败给「重试 / 忽略」两个动作按钮。
- **具体改法**：
  1. `downloads_tab.py:_update_row()` 中，当 `job.status in (FAILED, CANCELLED)` 时，操作列按钮改为**两个**：「重试」「移除」：
     - 重试：调用 `self.mgr.enqueue(job.item, job.appid)`（`DownloadManager.enqueue` 已存在，`downloader.py:156`），新行出现后删除旧行；
     - 失败行的「信息」列文案补操作引导：`job.message` 后追加 `（可点「重试」重新下载）`。
  2. 若核心层方便，给 `DownloadManager` 加 `retry(job_id)` 方法（复用 `enqueue` + 迁移 `item`/`appid`），UI 直接调用更干净。
  3. 操作列宽度从 88px 提到 140px，容纳两按钮（列 Fixed 模式，`downloads_tab.py:73-74`）。
- **影响文件**：`swdm/gui/downloads_tab.py`；可选 `swdm/core/downloader.py`（加 `retry()`）
- **验证**：断网或填错 AppID 制造失败任务，点「重试」后新任务入队并恢复下载；`tests/test_smoke.py` 不受影响。

### P0-3 「取消全部」加确认对话框

- **问题**：危险操作零拦截，误点丢掉整个队列进度（S2/E2）。
- **竞品做法**：Vortex 卸载/移除 mod 一律 `QMessageBox.question` 二次确认；本程序「移除并删除文件」已有确认（`library_tab.py:285-288`），下载页应保持同样标准。
- **具体改法**：
  ```python
  def _cancel_all(self) -> None:
      if QMessageBox.question(
          self, "取消全部",
          f"将取消全部未完成的下载（进行中 {n} 个、排队 {m} 个），确定继续？",
          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
          QMessageBox.StandardButton.No,
      ) != QMessageBox.StandardButton.Yes:
          return
      self.mgr.cancel_all()
  ```
  从 `self.mgr.snapshot()` 取 active/queued 计数填入文案。
- **影响文件**：`swdm/gui/downloads_tab.py`（`_cancel_all`，约 265 行）
- **验证**：队列有任务时点「取消全部」，弹出确认；选 No 队列不变。

### P0-4 修复模组库刷新丢失过滤选择（真 bug）

- **问题**：`refresh()` 每次清空并重建「游戏/分类」下拉，**不恢复用户之前的选择**——用户选了「仅某游戏」，一点「启用选中」过滤就回到「全部游戏」（实测可复现）。
- **竞品做法**：Vortex 的过滤器在刷新后保持原选中（过滤控件是视图状态，不随数据重建）。
- **具体改法**：`library_tab.py:refresh()` 中，重建下拉前保存、重建后恢复：
  ```python
  prev_appid = self.appid_combo.currentData()
  prev_cat = self.category_combo.currentData()
  # ... clear + addItem ...
  for combo, prev in ((self.appid_combo, prev_appid), (self.category_combo, prev_cat)):
      idx = combo.findData(prev) if prev else 0
      combo.setCurrentIndex(idx if idx >= 0 else 0)
  ```
  注意：恢复必须在 `blockSignals` 保护内做，避免触发 `currentIndexChanged` 死循环。
- **影响文件**：`swdm/gui/library_tab.py`（约 146-163 行）
- **验证**：库页选某游戏 + 某分类 → 点启用/禁用/刷新 → 过滤保持不变，列表内容一致。

### P0-5 统一详情弹窗配色

- **问题**：弹窗是程序里唯一一个蓝色主题的窗口，视觉上像「另一个软件」（V2）。
- **竞品做法**：Vortex 弹窗/面板与主窗口共享同一套设计 token；本程序 `styles.py` 已有完整的 `DARK_COLORS/LIGHT_COLORS` 双主题常量。
- **具体改法**：删除 `detail_dialog.py:_apply_qss()` 的硬编码 QSS，改为从 `styles.qss(theme)` 取主样式 + 少量弹窗专属补充（如 `QDialog` 背景沿用 `bg`）。按钮主色改用 `DARK_COLORS["accent"]`（深色）/ `LIGHT_COLORS["accent"]`（浅色），圆角 8px 对齐主窗口。顺带修 E7（状态色用主题常量而非硬编码）。
- **影响文件**：`swdm/gui/detail_dialog.py`（`_apply_qss`）；只读引用 `swdm/gui/styles.py`
- **验证**：切换深/浅主题后打开详情弹窗，按钮颜色、圆角、背景与主窗口一致。

### P0-6 工坊卡片加 hover 反馈 + 已安装状态角标

- **问题**：鼠标划过卡片画面零反馈，下载进度只在按钮位置出现，已安装 mod 与未安装视觉无差别（R2/V1）。
- **竞品做法**：`widgets.ModCard` 已实现的标准做法（`CARD_BG` 底 + `CARD_BORDER` 边 + hover 亮边 + 「✓ 已安装 / 未安装」角标）；Vortex 同款。Steam 浏览页卡片 hover 有轻微抬升。
- **具体改法**：让 `ModCardWidget` 复用这套语言（不必整体换成 `ModCard`，改动太大）：
  ```python
  self.setObjectName("modCard")
  self.setStyleSheet(
      "QWidget#modCard { background:#25252c; border:1px solid #33333b; border-radius:8px; }"
      "QWidget#modCard:hover { border:1px solid #4d4d59; background:#2a2a31; }"
  )
  ```
  - 右侧按钮列顶部加一个 22px 状态角标（「未安装」灰 / 「✓ 已在库」绿，复用 `INSTALLED_BG/INSTALLED_FG` 常量），`mark_downloaded()` 同步更新角标。
  - 配色常量从 `widgets.py` 导入，避免再散落一份。
- **影响文件**：`swdm/gui/workshop_tab.py`（`ModCardWidget._build`）
- **验证**：划过卡片边框/背景变化；已下载的 mod 卡片显示绿色「已在库」角标。

### P0-7 关键词搜索即时化（防抖自动刷新）

- **问题**：标签栏改选即时刷新，关键词却必须回车，两种筛选控件行为不一致（R3）。
- **竞品做法**：Vortex 过滤框输入即过滤；网页下载器搜索框即时联想。本程序游戏名搜索已实现「本地即时 + 网络防抖」范式（`_on_search_text_edited`），照搬到 mod 搜索即可。
- **具体改法**：
  ```python
  self._kw_timer = QTimer(self)          # 复用 _refresh_timer 也可
  self._kw_timer.setSingleShot(True)
  self._kw_timer.setInterval(500)        # 输入停顿半秒后刷新，避免逐字请求
  self._kw_timer.timeout.connect(self._refresh_list)
  self.search_edit.textChanged.connect(self._kw_timer.start)
  ```
  保留 `returnPressed` 立即刷新（不等防抖）。`_refresh_list` 内的 350ms 去抖与限流保护已就位。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_build` row2）
- **验证**：连续输入 5 个字符，只发一次列表请求；结果正确返回。

### P0-8 加载遮罩改为非遮挡的「顶部加载条 + 局部微光」

- **问题**：翻页时整个列表被深色遮罩盖死、无法滚动查看旧内容，快速翻页遮罩闪烁（R4）。
- **竞品做法**：浏览器/网页下载器用顶部细进度条（Chrome/Lighthouse 样式）表示「后台加载中」但不挡内容；Streamline 的队列页加载用行内 skeleton。
- **具体改法**：
  - 列表区上方加一条 2-3px 的 `QProgressBar`（不确定模式，range 0,0），加载开始 `show()`、完成 `hide()`；
  - 状态栏文案保留（"正在加载工坊列表…" 已通过 `worker.progress` 驱动）；
  - `LoadingOverlay` 保留给「真正必须等待」的场景（如首次启动部署 steamcmd），列表刷新不再使用。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_build` / `_do_refresh_list` / `_populate` / `_on_list_failed`）；`swdm/gui/widgets.py` 可新增 `TopLoadingBar` 组件
- **验证**：翻页期间旧列表仍可见可滚动；顶部细条动画指示加载中；完成后消失。

### P0-9 下载完成通知 + 主窗口标题进度

- **问题**：下载完无人知晓，必须切到下载页才知道（R5）。
- **竞品做法**：浏览器下载完成弹系统通知；Arma3 Launcher 更新完成托盘气泡提示。
- **具体改法**：
  1. `main_window.py` 加 `QSystemTrayIcon`（顺带把 README 承诺的托盘落地），`_on_download_finished` 中：
     ```python
     self.tray.showMessage("SWDM", f"已下载完成：{job.item.title}", QIcon(...))
     ```
     仅在窗口非激活/最小化时弹出（避免打扰）。
  2. 主窗口标题追加全局进度：`SWDM v1.3.7 · 下载中 2/5 (45%)`，无任务时去掉后缀——这是用户切走后回来的最快状态锚点。
  3. 全部完成时标题回到「就绪」。
- **影响文件**：`swdm/gui/main_window.py`（`_on_download_finished`、`_refresh_status_bar`）；`swdm/gui/downloads_tab.py`（`_refresh_status` 可广播计数）
- **验证**：开始下载后标题出现进度；最小化窗口时完成有托盘通知。

### P0-10 键盘快捷键体系

- **问题**：纯鼠标操作，高频用户没有加速通道（R6）。
- **竞品做法**：Vortex/WorkshopDL 支持 `Ctrl+F` 聚焦搜索、`Esc` 关闭弹窗；这是桌面工具的肌肉记忆基线。
- **具体改法**（`main_window.py` 集中注册，作用于当前标签页）：
  | 快捷键 | 动作 |
  |---|---|
  | `Ctrl+F` | 聚焦当前页搜索框（工坊页/库页通用） |
  | `F5` / `Ctrl+R` | 刷新当前页（工坊列表 / 库列表） |
  | `Esc` | 关闭打开的详情弹窗（若存在） |
  | `Ctrl+1..5` | 切换五个标签页 |
  | `Ctrl+D` | 工坊页：聚焦游戏选择框 |
  | `Enter`（搜索框内已有） | 立即搜索 |
  实现方式：`QShortcut(QKeySequence("Ctrl+F"), self, ...)`，各标签页暴露 `focus_search()` / `refresh()` 方法（`refresh_login_ui` 同款模式）。
- **影响文件**：`swdm/gui/main_window.py`（注册）；各 tab 暴露的公共方法
- **验证**：逐个按键实测生效；`tests/test_gui.py` 可加自动化按键断言。

---

### P1-11 下载页表格视觉重排

- **问题**：物品 ID 喧宾夺主、状态无颜色、失败信息无声（V3/E1）。
- **竞品做法**：Streamline 队列表格：标题为主列、状态用彩色标签（进行中=蓝、完成=绿、失败=红）、操作列按钮化；ID 列默认隐藏或弱化为等宽小字。
- **具体改法**（`downloads_tab.py`）：
  1. 「物品 ID」列改 `Fixed` 且宽度收到 0 或直接 `setSectionHidden(0, True)`（保留供调试页，表格可见性比隐藏更好）；
  2. 「标题」列保持 Stretch 为主列；
  3. 状态列按状态上色：成功绿（`success` 常量）、失败红（`danger`）、下载中蓝（`accent`）、取消/排队灰（`text_dim`）——用 `QTableWidgetItem.setForeground(QColor(...))`；
  4. 「进度」列失败时进度条变红（`setStyleSheet` 覆盖 chunk 颜色）+ 信息列文案带「点重试」引导（接 P0-2）；
  5. 完成行右键菜单加「打开文件目录」（复用 `library_tab._open_folder_by_path`，S6）。
- **影响文件**：`swdm/gui/downloads_tab.py`（`_update_row` / `_build` 表头）
- **验证**：制造成功/失败/取消任务各一，截图确认颜色与按钮正确。

### P1-12 工坊列表卡片化（视觉层级跃升）

- **问题**：整页无视觉容器，信息密度高但层级扁平，长时间浏览疲劳（V1）。
- **竞品做法**：Vortex Mods 区卡片（缩略图 + 标题 + 标签 chips + 状态角标）；Steam 工坊网页本身也是卡片网格。**本程序 `widgets.ModCard` 已实现完整卡片（含代码生成占位图、标签 chips 数量溢出 +N、安装角标），但工坊页用的是另一套 `ModCardWidget`。**
- **具体改法**（两条路，选改动小的）：
  - **方案 A（推荐）**：`ModCardWidget` 接入 `widgets.ModCard` 的视觉层——套 `QFrame#modCard` 样式、标题用 `ElidedLabel`、标签由纯文本 `[tag]` 换成 chips（复用 `ModCard._add_chip`），右侧操作区保留下载/详情按钮不变。
  - **方案 B**：直接让工坊页使用 `ModCard` + 右侧操作列扩展，改动较大但消除两套卡片并行。
  - 无论哪条：行高从「内容自适应」统一为 `112px`，卡片间距 8px，已下载卡片整体加一层淡绿左边框（`border-left: 3px solid #43b581`）作为状态强化。
- **影响文件**：`swdm/gui/workshop_tab.py`（`ModCardWidget`）；`swdm/gui/widgets.py`（可能导出 chips 构造助手）
- **验证**：60 卡压力测试渲染时间不显著上升（基线 115ms / ~1.9ms/卡）；窄窗口下标题正确省略、chips 不溢出。

### P1-13 模组库列表卡片化 + 启用开关

- **问题**：库页是 90 年代风格的单行密集文本，缩略图被压成 48px 图标，启用状态用 `✓/✗` 字符，信息扫读效率低（V4）。
- **竞品做法**：Vortex Mods 区每行 = 缩略图（80px+）+ 标题/标签/大小 + 右侧**开关控件**（Switch）+ 状态色；Arma3 Launcher 同款勾选启用。
- **具体改法**（`library_tab.py`，分步可控）：
  1. 第一阶段（低成本）：`QListWidget` 换成 `setIconSize(QSize(72,72))` + `setSpacing`，文本行用富文本分两行（标题加粗一行、`作者 · 大小 · 游戏名` 灰色小字一行），启用状态用彩色 `●` 代替 `✓/✗`；
  2. 第二阶段：仿工坊页改 `QScrollArea + 自定义卡片`（与工坊页组件统一），右侧放 `QCheckBox` 风格的启用开关 + 收藏星标按钮；
  3. 底部操作栏整理主次：「启用选中 / 禁用选中」升为主按钮（默认样式），「导入/导出/刷新」收进「更多」菜单（与工坊页 `more_btn` 同模式，V5）。
- **影响文件**：`swdm/gui/library_tab.py`（`_populate` / `_build`）
- **验证**：库页截图对比；右键菜单与勾选操作全部保持可用。

### P1-14 空态与引导设计

- **问题**：所有空列表都只有一行小字，用户不知道「正常空」还是「出错了」（V6）。
- **竞品做法**：Vortex 空库有「去浏览 mod」引导按钮；网页下载器空输入框有示例占位文本。
- **具体改法**：列表区空时，在滚动区中央渲染空态组件（`widgets.py` 新增 `EmptyState(icon, title, hint, action_button)`）：
  | 场景 | 主标题 | 引导 |
  |---|---|---|
  | 工坊列表空 | 「没有匹配的 mod」 | 「试试更换排序、清空标签筛选，或检查网络」+ 按钮「清空筛选」 |
  | 游戏无工坊页 | 「该游戏暂无可抓取的工坊页」 | 「换一款游戏试试」+ 跳到游戏选择 |
  | 下载队列为空 | 「暂无下载任务」 | 「去工坊浏览挑选 mod」+ 按钮切到工坊页 |
  | 模组库为空 | 「还没有任何 mod」 | 「导入已有目录」或「去工坊下载」（两个按钮） |
- **影响文件**：`swdm/gui/widgets.py`（新组件）；三个 tab 的空判定处
- **验证**：清空筛选/断网制造各空态，截图确认文案与按钮可用。

### P1-15 分页强化

- **问题**：只能上一页/下一页，无法感知位置、无法跳页（S5）。
- **竞品做法**：网页下载器与 Steam 工坊页的页码导航（`1 2 … 7 [8] 9 … 20`）。
- **具体改法**（`workshop_tab.py` row3）：
  - `page_label` 从「第 N 页」升级为「第 N 页 · 本页 30 项 · 预估共 X 页」（`total` 从 `browse()` 返回值取，无值时降级显示「第 N 页」）；
  - 页码标签点击可编辑（`QLabel` → 可点击数字，或直接给「跳到第 N 页」小按钮）；低成本方案：在「下一页」后加一个「跳页…」按钮弹 `QInputDialog`。
  - 「上一页」在第 1 页已禁用（已做），补：下一页超出结果时禁用（本页 items < 30 时禁用下一页）。
- **影响文件**：`swdm/gui/workshop_tab.py`（row3 / `_populate` 末尾更新按钮状态）
- **验证**：翻到最后一页时「下一页」自动禁用；跳页对话框输入 3 跳到第 3 页。

### P1-16 详情弹窗多开管理

- **问题**：`self._detail_dialog` 只保留一个引用，开第二个弹窗时第一个失去引用（窗口仍在但代码不再管理）；非模态多开层级混乱。
- **竞品做法**：浏览器标签页式：每个详情独立窗口，任务栏可见；Vortex 的 mod 详情是侧滑面板（单实例复用）。
- **具体改法**（二选一）：
  - **A（低成本）**：改为 `set[]` 容器管理多个弹窗，关闭时移出集合；每次 `_open_detail` 复用已存在的同 id 弹窗（`activateWindow` + `raise_`），避免重复抓取（详情页缓存已有，但窗口复用更省内存）。
  - **B（更现代）**：改为右侧滑出式面板（`QFrame` 停靠在主窗口右侧），与列表并排可同时操作——契合「mod 选择页与详情页同时开启」的既有产品意图。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_open_detail`）；若选 B 需改 `main_window.py` 布局
- **验证**：连续打开 3 个详情弹窗，逐个关闭无崩溃；重复打开同一弹窗不重复请求。

### P1-17 导入 URL 增强（剪贴板识别）

- **问题**：导入要「更多」菜单 → 对话框 → 粘贴（S4）；用户复制了链接打开程序还要再粘贴一次。
- **竞品做法**：WorkshopDL 的招牌交互——**剪贴板 URL 自动识别**，打开程序即填入输入框，一键即可下载。
- **具体改法**：
  1. 工坊页启动时（`__init__` 末尾）读一次剪贴板，若为工坊链接（`resolve_any_url` 能解析出 item id），在状态栏提示「检测到剪贴板有工坊链接，点此导入」+ 一个临时小按钮（或 `more_menu` 顶部出现「📥 导入剪贴板中的链接」动作）；
  2. 导入对话框预填剪贴板内容（若为链接）；
  3. 对话框改 `QPlainTextEdit` 支持多行粘贴（现在 `QInputDialog.getText` 只能单行，多个链接要自己把换行替换成逗号——虽然代码已处理，但输入框本身不友好）。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_import_url`、`__init__`）
- **验证**：复制工坊链接后打开程序，出现导入提示；一次粘贴 5 个链接全部解析入队。

### P1-18 队列右键菜单与重排

- **问题**：队列只能整列取消，无法对单个任务「优先/延后/打开目录」（S7）。
- **竞品做法**：Streamline 的 queue/manage/download 三段式；下载器普遍支持右键「优先下载」。
- **具体改法**（`downloads_tab.py`）：表格加 `CustomContextMenu`，菜单项：
  - 进行中/排队：「优先下载（插队）」「取消」
  - 完成：「打开文件目录」「在模组库中定位」
  - 失败：「重试」（接 P0-2）
  - 「上移/下移」调整排队顺序（需 `DownloadManager` 暴露 `reorder(job_id, delta)`；无则先用「取消重下」近似，后续迭代）
- **影响文件**：`swdm/gui/downloads_tab.py`；可选 `swdm/core/downloader.py`
- **验证**：各状态行的右键菜单项正确显示且可用。

---

### P2-19 主题即时切换

- **问题**：切主题要重启（R8）。
- **具体改法**：`settings_tab._apply_all()` 中主题变化时，直接调 `main_window` 的 `_apply_theme()`（需通过 `settings_changed` 信号传一个 `theme_changed` 标志，或让 main_window 比较 config 前后值）。详情弹窗若已改用 `styles.qss(theme)`（P0-5），同步刷新已打开弹窗即可。
- **影响文件**：`swdm/gui/settings_tab.py`、`swdm/gui/main_window.py`、`swdm/gui/detail_dialog.py`
- **验证**：浅色主题下所有页面（含详情弹窗、标签 chips）即时变浅且无残留深色块。

### P2-20 软删除回收站

- **问题**：`移除并删除文件` 永久删除，误删无法恢复（E4）。
- **竞品做法**：竞品功能清单 P2-23「软删除/回收站：删除 mod 先进回收站，防误操作」；Vortex 卸载有保留文件选项。
- **具体改法**：`library.delete(..., remove_files=True)` 时改为移动到 `<数据目录>/trash/<appid>/<item_id>/`，模组库右键菜单加「回收站…」二级入口（恢复 / 彻底清空）；`ModLibrary` 加 `trash_list() / restore() / purge()`。
- **影响文件**：`swdm/core/mod_library.py`；`swdm/gui/library_tab.py`
- **验证**：删除后文件存在于 trash；恢复后库记录与文件一致。

### P2-21 错误提示分级与原因区分

- **问题**：加载失败一律 `QMessageBox.critical` 打断操作，且不区分原因（E3/E5）。
- **竞品做法**：Vortex 的通知系统分级（error/warning/info）且带「查看日志」动作；VS Code 的错误条带「重试」按钮。
- **具体改法**：
  - `_on_list_failed` 按原因分流：`RateLimitError` → 状态栏黄字「已触发限流，X 秒后自动重试」（若核心层已在退避重试，UI 应显示「排队重试中」而非失败）；网络异常 → 空态组件 + 「检查代理设置」按钮跳设置页；其余 → 错误条 + 「查看日志」按钮跳调试页。
  - 模态 `critical` 只用于「用户主动操作直接失败」（如保存设置失败），后台加载失败改用内联错误条。
  - 全局异常弹窗指定 parent 为活动窗口（修 E6）。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_on_list_failed`）；`swdm/gui/main_window.py`（异常钩子 parent）
- **验证**：断网/限流场景下的提示文案与引导按钮正确。

### P2-22 预览图骨架占位

- **问题**：加载中纯文字占位，图片加载完画面跳变（R7）。
- **具体改法**：详情页预览图占位改为与最终图同尺寸的渐变底 + 中心 spinner（复用 `LoadingSpinner`）；失败时显示占位图（复用 `ModCard._placeholder`）。
- **影响文件**：`swdm/gui/detail_dialog.py`（`_show_image_placeholder`）
- **验证**：打开详情弹窗，图片区无尺寸跳变。

### P2-23 设置页整理

- **问题**：`CollapsibleSection` 内再嵌套 `QGroupBox`，每个分组标题出现两次（如「Steam 账号（登录方式）」）；无「恢复默认」。
- **具体改法**：
  - 去掉内层 `QGroupBox`，`CollapsibleSection` 直接承载 `QFormLayout`（标题唯一）；
  - 底部「保存全部设置」旁加「恢复默认设置」（弹确认 → `config.reset()` → `_load_values()`）；
  - 分组顺序按使用频率排：账号 → SteamCMD → 库目录 → 网络 → 依赖 → 外观（现状基本符合，微调即可）。
- **影响文件**：`swdm/gui/settings_tab.py`；`swdm/core/config.py`（可能需 `reset()`）
- **验证**：每个分组标题只出现一次；恢复默认后表单值回到出厂状态。

### P2-24 游戏搜索联想面板增强

- **问题**：联想候选项是纯文本下拉，无图标、无收藏标记、无"最近玩过"。
- **竞品做法**：Steam 客户端的游戏选择器带封面图与最近使用置顶。
- **具体改法**（低成本）：`_fill_search_results` 的候选项文本追加收藏星标（`★ Name (appid)`）；下拉项 `setUserData` 携带 appid；最近选择的 5 个游戏在 combo 顶部以「🕘 最近」分组呈现（配置持久化 `recent_games`）。
- **影响文件**：`swdm/gui/workshop_tab.py`（`_fill_search_results` / `_load_games`）；`swdm/core/config.py`
- **验证**：输入"gmod"即时出现带星标的候选；切换过的游戏出现在最近分组。

---

## 3. 明确不做（避免过度设计）

| 想法 | 为什么不做 |
|---|---|
| 加载顺序 / Profile 系统 | 需要核心层支持 mod 启用语义与游戏挂载规则，属 1.4+ 功能级迭代，不在 UX 批次 |
| 自动更新（GitHub Release 自检） | 打包链已稳定，自更新风险高于收益，列入长期 |
| 插件化 / 社区清单市场 | 生态功能，与 UX 无关 |
| 重构为 MVVM / 引入 QML | 现有 QThread+信号桥接架构经 1.3.x 多轮回归验证，推倒重来风险不可控 |
| 卡片网格视图（Pinterest 风） | 工坊浏览是「快速比较+批量下载」场景，列表行信息密度更高；网格只做详情弹窗预览即可 |

---

## 4. 建议实施批次

| 批次 | 内容 | 预估改动 | 风险 |
|---|---|---|---|
| **批次 1（手感）** | P0-1 排序刷新、P0-2 失败重试、P0-3 取消确认、P0-4 库过滤保持、P0-7 搜索即时化 | 5 处定点修改，均 < 20 行 | 低（均有现成信号/方法可复用） |
| **批次 2（反馈）** | P0-6 卡片 hover、P0-8 加载条、P0-9 通知+标题进度、P0-10 快捷键 | 4 个中等改动 | 低-中（托盘与快捷键需全量回归） |
| **批次 3（视觉）** | P0-5 弹窗配色、P1-11 下载页重排、P1-12 工坊卡片化、P1-13 库页卡片化、P1-14 空态 | 视觉层重构，集中改 4 个文件 | 中（需 60 卡压力测试 + 截图回归） |
| **批次 4（步长）** | P1-15 分页、P1-16 弹窗管理、P1-17 剪贴板、P1-18 右键菜单 | 4 个独立功能 | 低-中 |
| **批次 5（打磨）** | P2-19 ~ P2-24 | 体验细节 | 低 |

**回归要求**：每个批次结束跑 `tests/test_smoke.py`（核心链路）+ `tests/test_gui.py`（GUI 自动化截图），并对修改过的页面做「全按钮实测」（1.3.5 建立的做法，曾借此发现设置页添加游戏崩溃）。

---

## 5. 与竞品差异化的 UX 结论

> SWDM 的功能稀有度（匿名下载 + 依赖树解析 + 冲突检测 + 标签过滤 + SQLite 库）已高于市面上绝大多数 SteamCMD GUI 竞品；**1.3.7 的 UX 目标不是加功能，而是让这些已有能力「被看见、被点到、被理解」**：
> - **被看见**：卡片化、状态角标、彩色状态、空态引导（P1-11/12/13/14）
> - **被点到**：失败重试、右键菜单、跳页、剪贴板导入（P0-2、P1-15/17/18）
> - **被理解**：分级错误提示、限流「重试中」可见性、危险操作确认（P0-3、P2-21）
>
> 对标公式：**浏览体验学 Steam 工坊网页 + Vortex（卡片/状态/空态），下载体验学 Streamline + 浏览器下载（队列/重试/通知），错误体验学 VS Code（分级 + 可操作按钮）**。

---

### 附录：本报告引用的代码证据定位

| 证据 | 位置 |
|---|---|
| 排序下拉无信号连接 | `swdm/gui/workshop_tab.py:425-428` |
| 搜索仅 returnPressed | `swdm/gui/workshop_tab.py:422` |
| 全屏加载遮罩 | `swdm/gui/workshop_tab.py:470`（`LoadingOverlay`） |
| 失败行无重试 / 取消全部无确认 | `swdm/gui/downloads_tab.py:173-192`、`265-266` |
| 物品 ID 列过宽 | `swdm/gui/downloads_tab.py:64` |
| 库页下拉重建丢选择 | `swdm/gui/library_tab.py:147-163` |
| 库页密集文本行 | `swdm/gui/library_tab.py:190-207` |
| 详情弹窗蓝色主题 | `swdm/gui/detail_dialog.py:633-657` |
| 卡片无 hover 样式 | `swdm/gui/workshop_tab.py:118-215`（对比 `widgets.ModCard:498-509`） |
| 无快捷键 / 无托盘 | grep `QShortcut|QSystemTrayIcon` 全库 0 命中 |
| 主题需重启 | `swdm/gui/settings_tab.py:417-419` |
| 竞品功能全景底稿 | `research/competitor_analysis.md` |
