# SWDM 视觉设计令牌（Design Tokens）· v1.0

> 对标：PCL2（Plain Craft Launcher 2）皮肤质感 · DeepSeek Harness 皮肤质感 · Steam 社区页面
> 状态：1.4.2 起为 **QSS 2.0 基线**；文档与 `swdm/resources/qss/*.qss`、`swdm/gui/design_system.py` 一一对应。
> 范围声明：本轮只定义令牌 + QSS 骨架 + workshop 卡片试点，**不重排布局结构**。布局/导航形态属 2.0 重构议题（见 §9）。

---

## 1. 现状诊断

基于 `docs/screenshots/workshop.png`（offscreen 渲染 + modlens 读图）与 `swdm/gui/styles.py` 源码：

| 问题 | 现状 | 对标差距 |
|---|---|---|
| 卡片无高程 | mod 卡片是透明 QWidget，与页面背景无分离（`bg #1e1e22` ≈ 面板 `#23232a`，对比仅 ~5%亮度差） | PCL2：白卡(245/255) + 3px 阴影 0.07→0.4 悬停抬升 |
| 标签纯文本 | `[wiremod] [tool]` 是单色纯文本标签 | Steam：胶囊式 tag chip |
| 按钮无层级 | 主/次按钮均紫色块，缺深度（纯色无渐变/边框） | PCL2：3px 圆角 + 主题色 1px 边框 + 文字同色 |
| 强调色单一 | 只有蓝紫一个色系（链接、标签、选中全用同一紫/蓝） | Steam：链接蓝 `#66C0F4` 与操作紫分离 |
| 令牌散落 | 50+ 处内联 `setStyleSheet` 硬编码颜色，QSS 与代码双源 | PCL2：ColorBrush1/2/4 资源字典统一注入 |
| 无动效令牌 | 悬停/选中瞬切，无曲线/时长约定 | PCL2：90ms 颜色、150ms 高度 ExtraStrong 缓动 |

**根因总结**：1.x 主题是「能用的 VS Code 深色调」，没有令牌系统。2.0 的目标不是换皮，而是建立**单一事实来源**（Single Source of Truth）：文档 = QSS 文件 = Python TOKENS 三处一致。

---

## 2. 竞品调研（2026-10-01）

### 2.1 PCL2（Meloong-Git/PCL，WPF）

源：[`Controls/MyCard.vb`](https://github.com/Meloong-Git/PCL/blob/main/Plain%20Craft%20Launcher%202/Controls/MyCard.vb)、[`Controls/MyButton.xaml`](https://github.com/Meloong-Git/PCL/blob/main/Plain%20Craft%20Launcher%202/Controls/MyButton.xaml) 实读。

| 要素 | 实际值（源码实据） |
|---|---|
| 卡片背景 | `Color.FromArgb(245, 255, 255, 255)` —— 96% 不透明白（微透，层次柔和） |
| 卡片圆角 | `CornerRadius(5)` |
| 卡片阴影 | `MyDropShadow` ShadowRadius **3**，Margin `-3,-3,-3,-4`（底部多 1px，模拟自然光） |
| 阴影透明度 | 静止 **0.07** → 悬停 **0.4**（≈5.7 倍抬升，最强皮肤感签名） |
| 阴影颜色 | 主题色 `ColorObject1`（阴影不是黑色而是品牌色） |
| 卡片标题 | FontSize **13**，FontWeight **Bold**，Margin `15,12,0,0` |
| 折叠态高度 | 40px |
| 悬停颜色过渡 | **90ms**（`AaColor ... 90`） |
| 高度动画 | ≤800px：**150ms** `AniEaseOutFluent(ExtraStrong)`；>800px 分匀速段+减速段 |
| 退出动画 | scale −0.08 + opacity −1，**200ms** AniEaseIn/OutFluent |
| 箭头旋转 | **250ms** AniEaseOutFluent |
| 按钮 | 外层半透明底 + 内层 `CornerRadius=3`、1px **主题色边框**、文字 **= 边框色**（`Foreground=BorderBrush`）、FontSize 13、ScaleTransform 悬停缩放 |

**可迁移结论**：① 阴影用品牌色而非黑色；② 圆角分级（卡 5 / 钮 3）；③ 90ms 与 150ms 是 Microsoft Fluent 体感的实测甜点；④ 悬停抬升（idle 0.07 → hover 0.4）是「皮肤质感」的核心签名。

### 2.2 Steam 社区（store/community web）

| 要素 | 实际值 |
|---|---|
| 页面底色 | 深色 `#1b1b1b` 系（Store `#171a21`），**比内容面板深一档**，卡片靠明度差浮起 |
| 内容面板 | `#2a2a2a` / `#232323` |
| 主文本 | `#c7d5e0`；次要 `#8f98a0`（≈6:1 对比） |
| 链接 | Steam 蓝 `#66C0F4`（与操作按钮的紫/绿完全分离的语义色） |
| 订阅按钮 | 绿色渐变（`#75b022`→`#5c9e2b`）——「成功/拥有」语义 |
| 卡片圆角 | **3px**（小而利落，PCL2 的卡 5px 的另一半流派） |
| 区块标题 | 大写 + 字母间距，视觉锚点清晰 |
| workshop 卡片 | 缩略图 3px 圆角 + 标题/作者/订阅数三行信息层级 |

**可迁移结论**：① 链接色与操作色分离；② 圆角 3px 用于小元素（chip/缩略图/小按钮）；③ 深一档画布是暗色卡片浮起的最省力手段（比阴影更适配 Qt——QSS 不支持 box-shadow）。

### 2.3 关键技术约束（Qt/QSS）

**QSS 不支持 `transition`/动画与 `box-shadow`。** 因此：

- **高程**：用「画布深一档 + 1px 描边 + 表面明度阶梯」模拟（Steam 路线），对话框如需真实阴影走 `QGraphicsDropShadowEffect`（2.0 议题）。
- **动效**：令牌只做约定（时长/曲线），实现层为 Python 侧 `QPropertyAnimation`/`QVariantAnimation`（`design_system.py` 导出 `MOTION` 供自绘控件取用）。
- **CSS 变量**：QSS 不支持变量 → 令牌落地为「每主题一份 QSS 文件」+「Python TOKENS 字典」双副本，靠本文档做单一事实源约束（后续可加测试断言三者一致，见 §8）。

---

## 3. 色板（Color Palette）

### 3.1 暗色（dark）

**表面阶梯（Surface Steps）** —— 明度递进，模拟 z 轴：

| Token | 值 | 用途 |
|---|---|---|
| `surface.canvas` | `#16161C` | 窗口/页面画布（比 1.x `#1e1e22` 更深，卡片浮起的前提） |
| `surface.card` | `#1E1E24` | 卡片、面板主体（含旧 `bg_panel` 语义） |
| `surface.card_hover` | `#25252D` | 卡片/行悬停 |
| `surface.input` | `#26262E` | 输入框、下拉、菜单、tooltip（含旧 `bg_input` 语义） |
| `surface.raised` | `#2B2B34` | 弹出层/对话框 |
| `surface.selected` | `#32285E` | 选中态（强调色 24% 不透明观感） |

**描边（Strokes）**：

| Token | 值 | 用途 |
|---|---|---|
| `stroke.hairline` | `#2B2B33` | 卡片/面板分隔线 |
| `stroke.card` | `#2E2E37` | 卡片描边（悬停时 → `stroke.hover`） |
| `stroke.input` | `#3A3A45` | 输入框描边 |
| `stroke.hover` | `#4A4A57` | 交互描边悬停 |
| `stroke.focus` | = `accent.500` | 聚焦描边 |

**文本（Text）**：

| Token | 值 | 对画布对比 | 用途 |
|---|---|---|---|
| `text.primary` | `#E8EAF0` | 14.5:1 | 主文本、标题 |
| `text.secondary` | `#9AA3AF` | 7.0:1 | 元信息、说明（含旧 `text_dim` 语义） |
| `text.tertiary` | `#6E757F` | 3.9:1 | 占位、禁用辅助 |
| `text.disabled` | `#5A6068` | — | 禁用 |
| `text.on_accent` | `#FFFFFF` | 4.5:1 on accent | 强调色上的文本 |

**强调与语义（Accent / Semantic）**：

| Token | 值 | 用途 |
|---|---|---|
| `accent.400` | `#8F74FF` | 悬停 |
| `accent.500` | `#7C5CFF` | 主强调（品牌延续 1.x 蓝紫） |
| `accent.600` | `#6A48F0` | 按下 |
| `link.default` | `#66C0F4` | 链接、标签、可点文本（Steam 蓝，与操作紫分离） |
| `link.hover` | `#8CD4FF` | 链接悬停 |
| `success.500` | `#43B581` | 成功/已完成/「已在库」 |
| `danger.500` | `#F04747` | 错误/删除 |
| `warning.500` | `#FAA61A` | 警告/限流提示 |

### 3.2 浅色（light）

| 分类 | Token | 值 | 备注 |
|---|---|---|---|
| 表面 | `surface.canvas` | `#F2F3F6` | 比 1.x `#f6f7f9` 略深 → 白卡浮起 |
| 表面 | `surface.card` | `#FFFFFF` | PCL2 的「白卡」 |
| 表面 | `surface.card_hover` | `#F7F8FA` | |
| 表面 | `surface.input` | `#FFFFFF` | |
| 表面 | `surface.raised` | `#FFFFFF` | 弹层 |
| 表面 | `surface.selected` | `#E7E0FB` | |
| 描边 | `stroke.hairline` | `#DDE1E6` | |
| 描边 | `stroke.card` | `#E3E6EB` | |
| 描边 | `stroke.input` | `#C8CCD2` | |
| 描边 | `stroke.hover` | `#B6BCC5` | |
| 文本 | `text.primary` | `#23272E` | |
| 文本 | `text.secondary` | `#5A6169` | |
| 文本 | `text.tertiary` | `#8A919A` | |
| 强调 | `accent.400/500/600` | `#7D5CFF` / `#6D4AFF` / `#5B3CE0` | |
| 链接 | `link.default` / `link.hover` | `#1F7EB8` / `#1463A0` | 深化至 ≥4.5:1（`#66C0F4` 在白底仅 2.4:1，不可用于正文链接） |
| 语义 | success/danger/warning | `#2F9E6B` / `#D63C3C` / `#C77E00` | |

> **无障碍基线**：正文至少 4.5:1；大字（≥15px 600）与图标 3:1。accent.500 上的白字达 4.6:1（dark）✓。

---

## 4. 高程与阴影（Elevation）

Qt/QSS 无 box-shadow，采用「明度阶梯 + 描边」的 Steam 式高程；PCL2 式品牌色阴影列为 2.0 实现项（`QGraphicsDropShadowEffect`）。

| 层级 | dark | light | 手段 |
|---|---|---|---|
| z0 画布 | `#16161C` | `#F2F3F6` | 最深/最暗底 |
| z1 卡片 | `#1E1E24` + `stroke.card` 1px | `#FFFFFF` + `stroke.card` 1px | +1 明度阶 + 1px 描边 |
| z2 悬停 | `#25252D` + `stroke.hover` | `#F7F8FA` + `stroke.hover` | 再 +1 阶 |
| z3 输入/弹层 | `#26262E` + `stroke.input` | `#FFFFFF` + `stroke.input` | +2 阶 |
| z4 对话框 | `#2B2B34` + 2px `stroke.input` | `#FFFFFF` + 2px `stroke.hover` | 最浮（2.0 加真实阴影） |

**规则**：任何浮层必须与下层至少有 1 个明度阶 + 描边双重分离；等亮无描边的两块区域 = 设计缺陷。

---

## 5. 圆角（Radius）

| Token | 值 | 用途 | 出处 |
|---|---|---|---|
| `radius.xs` | `3px` | tag chip、缩略图、小图标按钮、Steam 式小元素 | Steam |
| `radius.sm` | `5px` | 紧凑卡片、列表 item | PCL2（`CornerRadius(5)`） |
| `radius.md` | `6px` | 按钮、输入框、下拉 item、进度条 | 综合收敛 |
| `radius.lg` | `8px` | 卡片容器、对话框、菜单、tab pane | 延续 1.x |
| `radius.pill` | `999px` | 胶囊 chip、筛选标签、开关 | Steam |

**规则**：一族元素只用一个档位；跨档位必须对应明确的层级关系（元素越小圆角越小）。

---

## 6. 间距（Spacing）—— 4pt 栅格

`space.1 … space.8` = `4 / 8 / 12 / 16 / 20 / 24 / 32` px。

| 场景 | 值 | 说明 |
|---|---|---|
| 组件内紧凑间距（图标↔文字） | `4` | |
| 卡片内边距（2.0 目标） | `12` | 1.x 为 8（试点不改几何，仅令牌约定，见 §8 迁移） |
| 卡片之间 | `8` | `list_layout.setSpacing(8)` |
| 区块（section）内边距 | `16` | |
| 区块之间 | `16~24` | |
| 对话框内边距 | `24` | |

对齐原则：一律 4 的倍数；禁止 3/5/7 等散值（历史内联样式除外，迁移时统一）。

---

## 7. 字号与动效

### 7.1 字号（Type Scale，QSS px）

| Token | 值 | 字重 | 行高 | 用途 |
|---|---|---|---|---|
| `text.caption` | `10px` | 400 | 1.4 | 极次要标注（试点 tag 用 11） |
| `text.body_sm` | `11px` | 400 | 1.45 | 卡片元信息、提示 |
| `text.body` | `12px` | 400 | 1.5 | 正文默认 |
| `text.title_sm` | `13px` | 600 | 1.35 | 卡片标题（PCL2 同 13） |
| `text.title` | `15px` | 600 | 1.3 | 区块/空态标题 |
| `text.title_lg` | `18px` | 600 | 1.25 | 对话框标题 |
| `text.hero` | `22px` | 700 | 1.2 | 里程碑/空态大标题 |

字体族：`"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif`（Windows 中英文双覆盖，雅黑 UI 数字与西文更整齐）。

### 7.2 动效（Motion）

| Token | 时长 | 曲线 | 场景 | PCL2 对应 |
|---|---|---|---|---|
| `motion.color` | `90ms` | linear | 悬停颜色过渡 | `AaColor ... 90` ✓ |
| `motion.fast` | `150ms` | `ease-fluent-out` | 高度/缩放/进入 | 150ms ExtraStrong ✓ |
| `motion.base` | `200ms` | `ease-fluent-out` | 淡入淡出/退出 | 200ms AniEase ✓ |
| `motion.slow` | `250ms` | `ease-fluent-out` | 旋转/大位移 | 250ms 旋转 ✓ |
| `motion.spring` | `300ms` | `ease-spring` | 撤销/收藏等强调反馈 | 2.0 新增 |

曲线定义（CSS cubic-bezier ↔ Qt easingCurve）：

| Token | cubic-bezier | QEasingCurve |
|---|---|---|
| `ease-fluent-out` | `cubic-bezier(0.22, 1, 0.36, 1)` | `OutQuint` |
| `ease-fluent-in` | `cubic-bezier(0.64, 0, 0.35, 1)` | `InQuint` |
| `ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | `OutBack` |

**QSS 限制提示**：QSS 无 `transition`，以上令牌在 QSS 中**仅作取值约定**（悬停态颜色差值即令牌差值），动画能力由 Python 侧 `MOTION` 常量 + `QPropertyAnimation` 实现（`design_system.py` 已导出，供自绘控件/2.0 动效使用）。

---

## 8. 落地与迁移

### 8.1 单一事实来源结构

```
docs/design/design_tokens.md      ← 本文档（规范）
swdm/resources/qss/dark.qss       ← dark 2.0 overlay（令牌的 QSS 副本）
swdm/resources/qss/light.qss      ← light 2.0 overlay
swdm/gui/design_system.py         ← TOKENS / MOTION 字典 + design_qss() 装配
   ├─ design_qss(theme) = 旧 qss + 2.0 overlay（叠加层，级联后者胜出）
   └─ 旧 styles.qss()/DARK_QSS/LIGHT_QSS 完全保留（兼容回退）
```

**兼容策略（「保留旧 qss 兼容」）**：
- `swdm.gui.styles.qss(theme)` 签名与返回值**不变**（仍返回 1.x QSS），现有 50+ 处内联样式与回归测试（`test_qss_p1_p5`：`qss('nonsense')==DARK_QSS` 等）零破坏。
- 新入口 `design_system.design_qss(theme)` = `qss(theme)` + 主题 overlay；资源文件缺失/读取异常时自动降级为纯旧 QSS（不崩溃）。
- 开关：`config.general.ui_style`，`modern`（默认，2.0） / `classic`（1.x 纯旧 QSS，回退通道）。`MainWindow._apply_theme` 与 `_on_system_theme_changed` 统一走该开关。
- 打包：`swdm.spec` 增 `swdm/resources/qss/*.qss` → datas（loader 经 `resource_path` 解析，开发/PyInstaller 双态可用）。

### 8.2 试点：workshop 卡片（`ModCardWidget`）

只动样式，不动结构/几何（内边距仍 8、缩略图仍 96×96、按钮仍 92 宽）：

| 元素 | 1.x | 2.0 试点 |
|---|---|---|
| 卡片容器 | 透明无描边 | `objectName=swdmCard` → `surface.card` + `stroke.card` 1px + `radius.lg`，悬停 `surface.card_hover` + `stroke.hover`（`WA_Hover` 开启） |
| 标题 | 内联 `font-weight:600;font-size:13px;color:#e8ecf2` | 移除内联 → `#cardTitle` QSS 规则（同一取值，单一来源） |
| 元信息 | 内联 `color:#8a909a;font-size:11px` | 移除内联 → `#cardMeta` |
| 标签 | 内联 `color:#5f8fd0;font-size:10px` | 移除内联 → `#cardTags`，改用 `link.default`（Steam 蓝分离语义）+ `11px` |
| 缩略图 | 内联 `background:#262b32;border-radius:4px` | 移除内联 → `#cardThumb`，`radius.xs` 3px（Steam） |
| 按钮组 | 无变化（容器描边内自然成组） | 同（QSS overlay 已分级圆角 6px） |

**为什么移除内联样式**：Qt 中 widget 内联 `setStyleSheet` 优先级**高于**全局 QSS，是令牌系统生效的最大障碍。试点验证「对象名 + 全局 QSS」的可行性，为 2.0 全量迁移内联样式铺路。

**两个 Qt 渲染坑（试点实测，2.0 迁移必读）**：

1. **普通 QWidget 不绘制 QSS 背景**：QSS 规则匹配后会把解析色写进 widget 的 palette，但若该 widget 未设 `WA_StyledBackground` / `autoFillBackground`，paintEvent 根本不画背景——规则「看似没生效」。`ModCardWidget` 必须设 `WA_StyledBackground`（style 走 PE_Widget 绘制 bg + 1px 描边 + 8px 圆角）；仅设 autoFill 会画实色矩形（无圆角/描边）。QLabel/QFrame 等内置控件自带 StyledBackground，只有自定义 QWidget 需要补。
2. **QScrollArea 视口/内容件的 autoFillBackground 亮灰**：视口与内容件 `autoFillBackground=True`、palette 沿用 QApplication 亮色默认（`#efefef`），在深色主题上画整块浅灰（1.4.1 遗留，深色列表区背景实为浅灰，无读图工具时不可见）。QSS 层排除两条路：`#qt_scrollarea_viewport` 规则不匹配内容件；`QScrollArea { background: transparent }` 把视口解析成实色黑。正确做法是代码侧 `design_system.prepare_scroll_area(scroll)` 关闭两层 autofill，已应用于 workshop / 标签栏 / 详情弹窗 / 设置页四处滚动区。

**验证工具**：`tools/verify_design_shots.py` —— 读图工具本机不稳定（sharp/modlens 时好时坏），改用**令牌色像素断言**：结构周期（canvas→描边→卡片→描边→间隙）、各令牌色存在性、`#EFEFEF` 残留为 0。`python tools/verify_design_shots.py`（dark，读 README 截图）/ `--light`（现场渲染，不污染截图）。dark + light 两模式 13+6 项断言全 PASS。

### 8.3 迁移路线（内联样式 → 令牌）

1. **1.4.2（本轮）**：workshop 卡片试点；overlay 层覆盖 tabs/buttons/inputs/scrollbars/cards 的全局观感。
2. **1.5**：library/downloads/settings 卡片同法迁移；`detail_dialog` 内联样式迁移；dialog 加 `QGraphicsDropShadowEffect`（brand-color 阴影，PCL2 式）。
3. **2.0**：tag chip 胶囊化（需 chip 为独立 QFrame，属结构改动）；全文 `setStyleSheet` 清零。

---

## 9. 后续路线建议（供讨论组裁决）

### 议题 A：导航形态 —— 顶 Tab → 侧栏

**现状**：`QTabWidget` 顶部 4~5 个 tab（工坊/下载/模组库/设置/更多），信息少时尚可，tab 数增长后标题被挤压、无法容纳图标+文字双行。

| 方案 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| **左侧栏导航**（PCL2 / DSH 皮肤质感） | 可折叠、图标+文字、扩展性强、皮肤质感最浓 | 内容宽度 −48~200px | **推荐**（2.0 旗舰改动） |
| 顶 tab 保留 + 图标点缀 | 改动最小 | 扩展性天花板仍在 | 备选（保守） |
| 顶栏 + 下拉菜单收纳 | 简洁 | 增加一次点击 | 不推荐 |

**建议**：先做可折叠侧栏（默认展开 180px，折叠为 56px 图标条），保留顶 tab 作为「经典」偏好项。需 2.0 重构窗口期实施（本轮不动）。

### 议题 B：密度

1.x 控件偏紧凑（卡片内边距 8px）。2.0 建议引入 `density` 令牌：`compact`（8px，现状）/ `comfortable`（12px，PCL2 同级）。卡片内边距 12、区块内边距 16 属 comfortable，作为 2.0 默认，compact 作偏好项。

### 议题 C：强调色策略

- 保留蓝紫 `accent.500 #7C5CFF`（1.x 品牌延续，且 Steam 紫 workshop 氛围一致）。
- 链接/标签统一改用 Steam 蓝 `#66C0F4`（深色）/ `#1F7EB8`（浅色），与本应用紫**分离语义**（Steam 社区同款逻辑：可点≠操作）。
- 未来皮肤系统：`accent.500` 改为用户可换（PCL2 主题色机制），令牌结构已支持（只需替换一个值族）。

### 议题 D：真实阴影 vs 描边高程

2.0 对对话框/悬浮卡片引入 `QGraphicsDropShadowEffect`（blur 12~16, color accent@30%, offset 4~6），追平 PCL2 皮肤质感。列表卡片维持描边高程（滚动性能 + Steam 路线）。

### 议题 E：动效落地

QSS 无动画 → 自绘控件的悬停抬升/按下缩放需 Python 侧 `QPropertyAnimation`（`design_system.MOTION` 已就绪）。优先级：卡片悬停抬升（PCL2 签名）> tab 切换 > 弹窗入场。**注意**：m1 已证实「运行中 QThread 被 GC → SIGSEGV」，动画实现须避开同一对象的强引用陷阱（animation 持有 parent）。

### 议题 F：2.0 技术形态（终极议题）

用户已列入「换语言/架构」2.0 终极议题。若走 Qt Quick（QML）路线，本套令牌可直接翻译为 `qtquickcontrols2.conf` 主题；若继续 QtWidgets，则按本套「对象名 + overlay QSS + TOKENS 字典」推进。**两者共用本文档**，令牌层先行可消除技术路线对设计的影响。

### 裁决清单（讨论组需明确）

1. 默认 `ui_style` 保持 `modern` 还是退回 `classic`（1.4.2 交付口径）。
2. 侧栏导航是否进 2.0（建议：是，含可折叠）。
3. density 默认 compact / comfortable。
4. 链接色是否切 Steam 蓝（建议：是，含浅色对比度修正）。
5. 对话框真实阴影是否进 1.5（建议：是，配合 PCL2 质感目标）。

---

## 10. 令牌速查（QSS 映射）

| 令牌 | dark | light | QSS 落点 |
|---|---|---|---|
| canvas | `#16161C` | `#F2F3F6` | `QMainWindow, QWidget#central` |
| card | `#1E1E24` / `stroke #2E2E37` | `#FFFFFF` / `#E3E6EB` | `QWidget#swdmCard` |
| card hover | `#25252D` / `#4A4A57` | `#F7F8FA` / `#B6BCC5` | `QWidget#swdmCard:hover` |
| accent | `#7C5CFF` / `#8F74FF` / `#6A48F0` | `#6D4AFF` / `#7D5CFF` / `#5B3CE0` | `QPushButton` / `::tab:selected` / focus |
| link | `#66C0F4` | `#1F7EB8` | `#cardTags`、链接 label |
| radius | xs 3 / sm 5 / md 6 / lg 8 | 同 | chip·thumb 3 / item 5 / btn·input 6 / card·menu 8 |
| 标题 | 13px/600 `#E8EAF0` | 13px/600 `#23272E` | `QLabel#cardTitle` |
| 元信息 | 11px `#9AA3AF` | 11px `#5A6169` | `QLabel#cardMeta` |
| 标签 | 11px `#66C0F4` | 11px `#1F7EB8` | `QLabel#cardTags` |
| 缩略图 | bg `#26262E`，radius 3 | bg `#EDEFF2`，radius 3 | `QLabel#cardThumb` |

**相关文件**：`swdm/gui/design_system.py`（TOKENS 字典）、`swdm/resources/qss/dark.qss`、`swdm/resources/qss/light.qss`、`swdm/gui/styles.py`（旧 qss 保留）、`swdm/gui/workshop_tab.py: ModCardWidget`（试点）。
