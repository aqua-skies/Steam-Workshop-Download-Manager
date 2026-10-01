# PCL2 视觉语言研究 + 各技术栈美观实现路径

> 对象：Plain Craft Launcher 2（Meloong-Git/PCL，WPF/.NET，main 分支 2026-10-02 快照）
> 姊妹文档：`docs/design/design_tokens.md`（t4 设计令牌 v1.0，PCL2 实测值已沉淀进令牌）
> 用途：① 1.4.2 视觉试点选型；② 为 `docs/architecture/rewrite_feasibility.md`（t3 四路线评估）提供**美观轴**输入。
> 方法论：全部结论基于源码实读（`FormMain.xaml(.vb)` / `Application.xaml` / `Controls/MyCard.vb` / `MyDropShadow.vb` / `MyButton.xaml(.vb)` / `MyListItem.xaml(.vb)` / `MyLoading.xaml(.vb)` / `MyHint.xaml` / `PageSetupUI.xaml.vb`），无截图推断。读图工具本机不可用（sharp/modlens 均失效，见项目记忆），几何与数值全部取自控件源码。

---

## 0. 一句话结论

PCL2 的「皮肤质感」= **8 级主题色相阶梯 × 90ms 悬停颜色过渡 × 0.07→0.4 阴影抬升 × 矢量图标与主题色绑定 × 命名轨道动画系统**。其中 **约 70% 的观感**（色阶、描边、圆角、字号层级、提示条、滚动条、矢量图标）在 PySide6/QSS 可 1:1 复现；**约 30%**（悬停颜色过渡、阴影抬升、镐子摆动、壁纸模糊）WPF 由 DependencyProperty 动画 + 自绘 9-patch 阴影 + BlurEffect 实现，PySide6 侧必须退化为 `QPropertyAnimation` + 自绘 `paintEvent` + `QGraphicsBlurEffect`，性能与声明式优雅度有硬性上限（详见 §6）。

---

## 1. 色相情绪：主题色 8 级阶梯 + HSL 主题系统

### 1.1 默认主题（蔚蓝）实测值

`Application.xaml` 颜色表——同一色相按明度/饱和度切成 **8 级**（ColorBrush1 最深 → 8 最浅），这是 PCL2 色彩情绪的全部语法：

| 级 | 值 | 语义（从用法反推） |
|---|---|---|
| 1 | `#343d4a` | 去饱和深蓝灰——**正文文字**、按钮默认边框、菜单边框 |
| 2 | `#0b5bcb` | 深蓝——列表项**选中**的前景色、高亮按钮边框 |
| 3 | `#1370f3` | 纯蓝——**聚焦**（输入框边框）、悬停按钮边框、勾选竖条、滚动条拇指 |
| 4 | `#4890f5` | 中蓝——标题栏渐变端点、指向反馈色 |
| 5 | `#96c0f9` | 亮蓝——加载图标前景（ColorBrushBg0） |
| 6 | `#d5e6fd` | 淡蓝——悬停描边、按下列表背景 |
| 7 | `#e0eafd` | 极淡蓝——**悬停背景**（列表 RectBack、按钮背景） |
| 8 | `#eaf2fe` | 近白——彩色标题栏上的次级文字 |

外加中性灰阶 Gray1–8（`#404040`→`#f5f5f5`，次级文字 Gray2 `#737373` / 占位 Gray4 `#a6a6a6`）与语义色（RedLight `#ff4c4c`、RedBack `#80fbdddd`、HalfWhite `#55ffffff`、SemiTransparent `#01eaf2fe`——**1% alpha** 的底色，滚动条轨道/PCL2 全套控件底色就是这个近乎透明的主题色，是"整体偏蓝"而非死黑的来源）。

**色相情绪的核心**：界面 90% 面积是中性的白/灰，主题色只出现在**交互 affordance**（边框、聚焦、选中、悬停、标题栏渐变）上。冷蓝 + 大面积留白 = "干净、可控、启动器该有的样子"；情绪由**明度分级**而非色相数量承担。

### 1.2 主题系统：HSL 可调 + 解锁制

`PageSetupUI.xaml.vb`：主题 14 号为自定义，暴露 **Hue（0–360°）/ Sat（%）/ Light（±）/ Delta（±）** 四滑杆，拖动即 `ThemeRefresh()` 整表重算 ColorBrush1–8 并通过 `DynamicResource` 立即全局生效（无重启、无闪烁）。隐藏主题构成情感彩蛋：5 玄素黑（灰色电台解锁）、6 铁杆粉（使用 99 次解锁）、8 赞助 ¥23.33、9 反馈 Bug/PR、11 解密游戏、12/13 隐藏、另有玩笑主题"眼瞎白/真·滑稽彩"。`SliderLauncherBlur`/`SliderLauncherTransparent` 还可调**壁纸模糊像素**与**窗口不透明度**。

**对 SWDM 的可迁移结论**：令牌系统已经具备"换一个 `accent.500` 即换皮肤"的能力（design_tokens §3 议题 C）。1.4.2 不需要做 HSL 编辑器，但**令牌 → QSS overlay → TOKENS 字典**三副本的一致性测试（design_tokens §8.1）是主题系统的最低地基。

---

## 2. 卡片与列表视觉层级

### 2.1 MyCard（卡片）

层叠结构（`MyCard.vb` New()，自底向上）：

1. `MyDropShadow` —— Margin `-3,-3,-3,-(3+1)`（**底部多 1px 模拟自然光**），ShadowRadius 3，静止透明度 **0.07**，**阴影颜色绑定主题色 ColorObject1**（不是黑色！）
2. `Border` —— 背景 `Color.FromArgb(245,255,255,255)`（**96% 不透明白**，微透让层叠柔和），CornerRadius 5
3. `MainGrid` —— 标题 `FontSize=13 Bold`，Margin `15,12,0,0`，前套 ColorBrush1
4. 折叠态固定高 40px；右侧箭头 `Shapes.Path`（`M2,4 l-2,2...` 内置几何），旋转动画 250ms `AniEaseOutFluent(ExtraStrong)`

悬停（`MyCard_MouseEnter`，**全部 90ms**）：标题/箭头颜色 1→2，阴影颜色 ColorObject1→4，阴影透明度 0.07→**0.4**（≈5.7 倍抬升——PCL2"皮肤感"的第一签名）。退出动画 `AniDispose`：scale −0.08 + opacity −1，**200ms** In/OutFluent 组合 + 高度收回 150ms。

高度变化动画（`StartHeightAnimation`）是性能与质感平衡的教科书：≤800px 直接 150ms `AniEaseOutFluent(ExtraStrong)`；>800px **分匀速段 + 减速段**（展开 5000px/s×300ms 匀速 + 400ms 减速；超长收回强制 100ms 匀速 + 150ms 减速，避免长时间"等待动画结束"）。

### 2.2 MyListItem（列表项）——SWDM 最该抄的一层

- 行高 **42px**，5 列网格：[2px 勾选条][0~N 左 padding][4px+34px 图标][* 标题][右 padding]
- 标题默认 14px、`TextTrimming=CharacterEllipsis`；**副标题 Info 12px、透明度 0.6**（同一支笔淡墨写两行——信息层级靠字号 + 透明度，不靠第三种颜色）
- 悬停（`RefreshColor`）：`RectBack`（背景 ColorBrush7、边框 ColorBrush6、CornerRadius 6、**scale 0.8→1** 120ms `AniEaseOutFluent`）淡入；整行 scale 1→0.98（按下）；右侧按钮组（25×25 图标钮）**悬停才淡入**并撑开右 padding（`5 + 按钮数×25`）——低密度默认、按需展开
- 选中：前景 1→ColorBrush2，**左侧 5px 圆角竖条**（ColorBrush3）高度以 200ms `OutFluent` + 300ms `OutBack` 两段生长；radio 语义由控件树自动单选收敛
- 图标三通道：SVG path 矢量（`GeometryConverter`）/ 本地位图 / 网络图（`MyImage`，7 天缓存 + FallbackSource + LoadingSource 占位图）

**卡片 vs 列表的分工**：卡片 = 同质内容的**容器**（可折叠、有阴影、标题 13 bold）；列表项 = **可点选的行**（无阴影、靠 RectBack 悬停浮层 + 勾选竖条表达状态）。二者不混用阴影——阴影只给"浮起来的东西"。

### 2.3 提示条 / 菜单 / 滚动条 / 按钮

- `MyHint`：**左侧 3px 色条**（`BorderThickness 3,0,0,0`）+ 圆角 2 + 内边距 12,9 + 可选关闭钮——Material 式 alert 的极简版
- `ContextMenu`：白底 + 1px ColorBrush1 边 + 圆角 3 + `DropShadowEffect`（Opacity 0.4 / BlurRadius 4 / ShadowDepth 2，**真实阴影只给弹出层**）+ MenuItem 行高 26
- `MyScrollBar`：宽 **8px**，拇指圆角 3、margin 2，轨道 `ColorBrushSemiTransparent`（1% 主题色），翻页按钮透明但保留点击
- `MyButton`：双层（外层半透明底 + 内层 CornerRadius 3、1px **主题色边框**、**文字色 = 边框色**、FontSize 13）；状态机 Normal(1)/Highlight(2)/Red(RedLight+RedDark) 三档 × 悬停级（悬停进 ColorBrush3）；**按下 scale 0.955 / 80ms** `OutFluent(ExtraStrong)`，松手 300ms 回弹、离开 800ms 慢回（按下/松开/离开三种回弹速度不同——"按下去要脆、弹回来要慢"）

---

## 3. 加载态动画：MyLoading 的状态机

`MyLoading.xaml(.vb)`——一个 Minecraft 镐子矢量图（`PathPickaxe`，Stroke 而非 Fill）的三状态（Run/Stop/Error）循环：

- **摆动循环**（`AniLoop`）：−20° / **350ms + 250ms 延迟** `AniEaseInBack(Weak)`（蓄力后摆）→ +50° / 900ms `AniEaseOutFluent`（挥下）→ +25° / 900ms `AniEaseOutElastic(Weak)`（弹性回弹）；挥击点甩出两粒 3×5 碎片（左右各一，opacity 0→1→0 / 100ms+180ms，X±5 / Y−6 抛物线）
- **错误态**：前景色 → `ColorBrushRedLight` 300ms，X 形 `PathError` 100ms 淡入 + 400ms `AniEaseOutBack` 缩放进场；若镐子还没挥下则**等动画结束再播**（400ms 等待槽，`ErrorAnimationWaiting`）——状态切换不打断进行中的动作，过渡永远完整
- **文本反馈**：`"加载中 - 42%"`（ShowProgress 绑定 Loader 进度）；错误态文本**替换为异常信息**（`TextErrorInherit`，`Ex.GetDisplay(False)`）而非通用"加载失败"

**设计哲学**：加载图标本身有性格（游戏主题镐子）、进度量化（百分比）、失败可读（真实异常文本）。SWDM 已有 `LoadingSpinner`（QPainter 弧 + QPropertyAnimation）与 `LoadingOverlay`（半透明遮罩 + 一行文字，`swdm/gui/widgets.py`），缺的是**百分比文本与错误态文本替换**——正是 1.4.2「反馈缺失」主线要补的（见 §5 第 2 条）。

---

## 4. 信息密度与字体权衡（回应用户反馈"文字大小/信息量权衡"）

PCL2 的选择与理由（全部源码可查）：

| 层级 | 字号 | 字重 | 出处 |
|---|---|---|---|
| 列表项主标题 | **14** | 400 | `MyListItem.xaml.vb` FontSize 默认 14 |
| 全局正文 / 卡片标题 / 输入框 / 按钮 | **13** | 卡片标题 Bold | `Application.xaml` TextBlock 默认 13；`MyCard` 13 Bold |
| 卡片内次级文本 | 11 | 400 | `Custom.xaml` 教学："FontSize 11 即改为 11 号" |
| 列表副标题 Info | **12** + **opacity 0.6** | 400 | `MyListItem` LabInfo |
| 标题栏副页面名 / 弹窗 | 15 / 16 | 400 | `FormMain` LabTitleInner 15、`MyLoading` LabText 16 |

- **字号谱极窄（11–16）**，层级靠**字重（Bold）、透明度（0.6）、颜色级（Gray2 vs ColorBrush1）**三支笔，而不是靠再小一号字。**信息量不是靠"字小"换来的，是靠"行高与副标题"换来的**：42px 行内放 14+12 双行 ≈ 单行 11px 的信息量，但可读性高一个档位。
- **文字裁切一律 `CharacterEllipsis`**（全局 TextBlock 默认值）——宁可用省略号也不允许换行炸版；`TextTrimming` 在 SWDM 已有等价 `ElidedLabel`（`widgets.py:411`），但未全局铺开。
- 字体族 `"Resources/#PCL English, Microsoft YaHei UI"`——**自带 20KB 英文字体**（西文/数字字形统一）+ 雅黑 UI 回退，保证中英混排基线一致。`TextOptions.TextFormattingMode="Display"`（MyButton 文本）开 ClearType 优化。
- **密度可配置心智**：`SliderLauncherTransparent` 等四滑杆 + 功能隐藏（F12 强显）让用户自己调信息量，而非设计者替用户二选一。

**对 SWDM 的结论**：当前令牌（body 12 / title_sm 13 / body_sm 11）与 PCL2 谱系**完全对齐**，1.4.2 不应缩字。信息量诉求的正确解法是**双行列表项**（标题 13/600 + 元信息 11 secondary，行高 40–42 对齐 PCL2），而非把现有 12px 正文压成 10px。design_tokens §9 议题 B 的 `density` 令牌（compact 8 / comfortable 12）就是这条路的 2.0 形态。

---

## 5. 1.4.2 试点：三条最高性价比改进

前提：t4 已交付令牌 v1.0 + QSS overlay + workshop 卡片试点（`ModCardWidget`/`swdmCard`）。下列三条**均在已铺好的地基上增量**，QSS 为主、`widgets.py` 小幅修改、零结构改动。

### ① 悬停反馈阶梯推广到列表行 / 菜单 / 输入态（QSS-only）

PCL2 的 90ms 颜色过渡在 Qt 列表场景不划算（QSS 无 transition，逐行动画 + 自绘代价高）。最高性价比的静态等价：**悬停 = 明度 +1 阶 + 描边换色**（PCL2 RectBack 的终态），选中 = 强调色文本/左侧竖条。

- `QListWidget::item:hover` / `QMenu::item:hover` → `surface.card_hover` + `stroke.hover`（dark 已有令牌）
- 输入框三态对齐 PCL2 PasswordBox 触发器：默认 `stroke.input` → 悬停 `accent.400` → 聚焦 `accent.500`（QSS `:hover`/`:focus` 规则，无动画）
- 落点：`swdm/resources/qss/dark.qss` / `light.qss` overlay 新增规则；验证：`tools/verify_design_shots.py` 加断言
- 覆盖映射：§6 表第 3 行「悬停反馈」的静态降级版。代价 ≈ 0，观感收益 ≈ PCL2 皮肤感的第二签名

### ② LoadingOverlay 加进度百分比 + 错误态（widgets.py 小改）

PCL2 MyLoading 两个可以直接抄的点：**"加载中 - 42%" 文本** 与 **错误态变色 + 异常文本替换**（§3）。SWDM `LoadingOverlay` 现有 spinner + 一行静态文字。

- `LoadingOverlay.set_message(text, percent=None)`；percent 非空时追加 ` - {p}%`
- `LoadingOverlay.set_error(text)` → 文本转 `danger.500`，spinner 换成 ✕（或保留 spinner + 红色描边），文本显示真实失败原因（对齐 `failure_reason` 域已有产物）
- 与 1.4.2 主线 t2（游戏搜索联想的即时反馈）共用同一反馈语汇：搜索联想面板加载、列表刷新、下载队列空态全部走同一组件
- 覆盖映射：§6 表第 6 行「加载态动画」的功能等价（动画可以先不抄，文本反馈先抄）

### ③ 列表/卡片元信息层级规范化（双行 + 透明度语义）

回应"文字大小/信息量权衡"：把 workshop 卡片已令牌化的 `#cardTitle`(13/600) + `#cardMeta`(11, secondary) 推广到 library/downloads 列表行，行高 40–42 对齐 PCL2；元信息统一 `opacity 0.6` 语义（PCL2 LabInfo 同款，用 text.secondary 近似而非真调透明度）。**字号不动、行高微调**——信息量感知 +30%，可读性不降级。

- 落点：QSS `#rowTitle` / `#rowMeta` 规则 + 列表 item widget 设对象名；结构与 `ModCardWidget` 试点同法（`WA_StyledBackground` + 对象名）
- 覆盖映射：§4 字体权衡章节的 1.4.2 落点

**三条之外、不建议进 1.4.2 的**：tag chip 胶囊化（需 QFrame 结构改动，列 design_tokens §8.3 的 2.0）、真实品牌色阴影（`QGraphicsDropShadowEffect` 在滚动列表的性能债，2.0 议题 D）、镐子级动画（QPropertyAnimation 组合，2.0 议题 E）。

---

## 6. 美观轴：WPF 机制 → PySide6 路径 → 四路线评分（供 t3 引用）

**本节为 `rewrite_feasibility.md` 的美观轴输入。t3 的四条路线：① C# WPF（PCL2 同栈）② Tauri（Rust+Web）③ Qt6 C++ / Avalonia ④ 续用 PySide6 深度重构。**

### 6.1 逐机制的 WPF 实现 → PySide6 最近似路径

| # | 视觉效果 | WPF 实现机制（源码实据） | PySide6 最近似路径 | 复现度 | 硬性上限 / 注意 |
|---|---|---|---|---|---|
| 1 | **自定义窗口边框** | `WindowStyle=None + AllowsTransparency=True + Background={x:Null}`（`FormMain.xaml`）；根 Grid Margin 10 留透明阴影区；8 个 Resizer 矩形（线性/径向渐变填充，`MyResizer.vb` 挂钩）；`RectangleGeometry RadiusX/Y=6` 圆角剪裁边框；标题栏 48px 自绘（主题色渐变 + 图标钮） | `Qt.FramelessWindowHint` + `WA_TranslucentBackground` + 8 个边缘 size-grip QWidget（或 nativeEvent 处理 `WM_NCHITTEST`）+ QSS `border-radius` + 自绘标题栏 | **高**（形态）| 失去 DWM 系统阴影与 Snap Layouts；多 DPI 混接时 1px 边缘发虚；圆角+阴影需自绘 `paintEvent`（QSS 无 box-shadow） |
| 2 | **窗口入场动画** | `TransformRotate −4°` + `TranslateTransform Y=60`，600ms/500ms `AniEaseOutBack(Weak)`，透明度 250ms（`FormMain_Loaded`） | `QPropertyAnimation` 并行组动 windowOpacity + 自绘 rotation/pos（帧渲染成本高，多退化为滑入+淡入） | **中** | 无/LayoutTransform 等价物；旋转整窗在 Qt 需自绘帧缓存，实践中降级为位移+透明度 |
| 3 | **悬停反馈** | `MouseEnter/Leave` + `AaColor` 90ms（卡片/按钮）；`AaScaleTransform` 0.955 按下 80ms（`MyButton.xaml.vb`）；阴影 0.07→0.4（`MyCard.vb`） | enterEvent/leaveEvent + `QVariantAnimation` 插值 palette 颜色 + `QPropertyAnimation(b"scale"...)`（自绘控件需 Q_PROPERTY）；**QSS `:hover` 静态规则作零成本兜底** | **中高**（静态满分/动态要写）| QSS 伪态无法与动画联动；每个动画必须显式持有 parent（m1 学费：运行中对象被 GC → SIGSEGV，见 design_tokens §9.E）；DepProperty 式"任意属性可动画"不存在，只能动 Qt property |
| 4 | **动画过渡系统** | `AniStart/AniStop("轨道名 " & Uuid)` **命名轨道**动画管理（同键自动停旧的）；`AniControlEnabled` 计数器压制代码驱动变更产生的动画；`Aa*` 助手族（Color/Opacity/Scale/Rotate/Height/Width/X/Y/Double/Code）；缓动库 OutFluent(ExtraStrong/Strong/Middle/Weak)/InFluent/OutBack/InBack/OutElastic；`AniSpeed` 全局倍率 | `QPropertyAnimation` + `QParallelAnimationGroup`/`QSequentialAnimationGroup` + `QEasingCurve`（OutQuint≈OutFluent、OutBack、OutElastic、OutCircle≈CircleEase）；轨道管理需自建（dict + stop(key)） | **中**（全部可手写等价）| 无框架级"命名轨道""压制计数器"——每处自建易漏；QSS 子控件（::handle/::tab）无法动画，必须换自绘控件 |
| 5 | **真实品牌色阴影** | `MyDropShadow.vb`：自绘 9-patch（边 `LinearGradientBrush` + 角 `RadialGradientBrush`，6 级 alpha 渐变 0.74336/0.38053/0.12389/0.02654，源自 WPF Aero `SystemDropShadowChrome`）；阴影色绑主题色；`ContextMenu` 用内置 `DropShadowEffect`(0.4/4/2) | `QGraphicsDropShadowEffect`（blurRadius+color+offset）；或 9-patch 自绘 `paintEvent`（QLinearGradient/QRadialGradient 完全可写） | **中**（自绘可对齐 / 内置效果受限）| `QGraphicsEffect` 每控件仅一个且不可叠加；与 QSS 圆角裁切冲突（圆角阴影需圆角 source）；滚动列表大量用 = 性能债 → 列表行维持 Steam 式描边阶梯（design_tokens §4 决策） |
| 6 | **加载态动画** | 镐子 `Path` + `RotateTransform` 关键帧序列（350/900/900ms，InBack→OutFluent→OutElastic）+ 粒子对 + 错误态 X 缩放进场 + 等待槽 | `QPropertyAnimation(b"angle")`（SWDM `LoadingSpinner` 已有）+ `QSequentialAnimationGroup` 编排 + 粒子用并行小动画 | **高**（功能层）/ 中（性格层）| Qt 画刷/QPainterPath 可复刻矢量与缓动；"动画人格"（镐子主题）是内容设计问题不是技术问题 |
| 7 | **矢量图标** | `Shapes.Path Data="M...z"`（SVG path 字符串直接当内容）+ `Fill` 绑 `DynamicResource ColorBrush*`（换主题图标即时变色）；`MyIconButton/MyIconTextButton` Logo 属性即 path | QPainterPath 解析 SVG path + `QPainter` 自绘 / `QSvgRenderer` + 生成时替换 fill 重缓存 / iconfont | **中** | 无"SVG-path-as-property"声明式模型 → 主题切换需图标缓存失效重建；QSvgRenderer 不继承主题色，recolor 得自己替换 SVG 文本 |
| 8 | **模糊遮罩** | `BlurEffect`（壁纸模糊可调像素，`SliderLauncherBlur`）；模态层 `PanMsg` 透明叠加 | `QGraphicsBlurEffect`（**软件渲染**）；压暗遮罩 = 半透明 QWidget overlay | **低→中** | Qt 无 GPU 高斯模糊，全窗实时模糊在 resize/scroll 掉帧；Win11 亚克力/Mica 须 `DwmSetWindowAttribute` ctypes 直调；纯色压暗遮罩无上限 |
| 9 | **文字省略** | 全局 `TextTrimming=CharacterEllipsis`；`TextOptions.TextFormattingMode=Display` | `ElidedLabel`（`widgets.py:411` 已有，`QFontMetrics.elidedText`） | **高** | 需全局铺开（QLabel 默认不省略）；ClearType 级微调无等价 |
| 10 | **主题色注入** | `ResourceDictionary` + `DynamicResource` + HSL 重算 ColorBrush1–8，全树即时换色 | 令牌字典 → 重建 QSS 字符串 → `setStyleSheet` 重应用 + `QApplication.setPalette` | **高** | QSS 重解析是 O(表大小)，全窗瞬时切换（几十 ms）可接受；**QSS 无变量** → 三副本一致性只能靠测试（design_tokens §8.1） |
| 11 | **静态层：描边/圆角/渐变/字号/提示条/滚动条** | `ControlTemplate` 重写（`Application.xaml` 全部控件模板） | QSS（border/border-radius/qlineargradient/font/::subcontrol） | **高（1:1）** | QSS 选择器/伪态覆盖度 ≈ CSS 子集，复杂模板（如 ScrollViewer 结构置换）需 `QProxyStyle`/自绘控件补 |
| 12 | **半透明层叠** | `Color.FromArgb(245,...)` 96% 白 / `#55ffffff` / `#01eaf2fe`（1% 底色） | QSS `rgba()` | **高** | — |

### 6.2 四路线美观轴评分（1–5 + 理由，转 t3 统一维度表）

| 路线 | 美观上限 | 理由（机制级） |
|---|---|---|
| **① C# WPF** | **5.0** | 全部 12 项机制一一对应：DependencyProperty 动画、ControlTemplate/Trigger/Storyboard 声明式驱动、`MyDropShadow`/`MyCard`/`MyButton`/`MyLoading`/ModAnimation 可**直接移植**；PCL2 本身就是参考实现 |
| **② Tauri（Rust+Web）** | **4.5** | CSS `transition`/`transform`/`filter: backdrop-filter`/SVG/Canvas 原生且 GPU 加速——模糊、过渡、矢量全部无上限甚至更现代；扣 0.5：无边框窗口同样要自管 hit-test 与系统阴影，且跨平台 obliged 统一（Win11 mica 需插件） |
| **③ Qt6 C++ / Avalonia** | **Qt C++ 3.5 / Avalonia 4.5** | Qt C++：与 PySide6 **同一机制同一上限**（QSS/QPropertyAnimation/QGraphicsEffect 软件模糊），只是性能与 C++ 级控制更好；Avalonia：XAML + 动画系统与 WPF 同构（Direct2D/Skia 渲染），美观轴接近 WPF |
| **④ 续用 PySide6 深度重构** | **3.5** | 静态层（表 11/12 行）满分对齐——1.4.2 试点已证 QSS+令牌可拿到 PCL2 观感的主体；扣分项集中在动态层（悬停过渡/阴影抬升/模糊）需自绘且性能受限，主题切换靠重建 QSS（可用但有上限）。**但这是一条"70% 观感 / 20% 成本"的性价比路线**：§5 三条改进全部落在静态层 + 现有 `widgets.py` 原语 |

### 6.3 给 t3 的三句话结论

1. **美观不构成"必须换 WPF"的理由**：PCL2 的质感主体（色阶/描边/层级/字体谱）在 PySide6 已 1:1 落地（t4 令牌+试点），动态层差距是"工程量"而非"可能性"。
2. **若 2.0 真换栈，Tauri 在美观轴上是唯一不输 WPF 且分发更轻的选项**（4.5），代价在核心逻辑 Rust 重写与 AI 团队驾驭度（转 t3 的迁移成本/可维护性轴评估）。
3. **Avalonia 是"想留在 XAML 心智"的折中**（4.5），Qt6 C++ 在美观轴相对 PySide6 无质变（3.5）——若纯为美观选 Qt C++ 不成立，其收益在性能/分发轴。

---

## 7. 附：PCL2 数值速查（供令牌对齐复核）

| 项 | PCL2 实测 | SWDM 令牌（design_tokens.md） | 对齐 |
|---|---|---|---|
| 卡片背景 | `ARGB(245,255,255,255)` 96% 白 | light `surface.card #FFFFFF` | ✓（微透留 2.0） |
| 卡片圆角 / 折叠高 / 标题 | 5 / 40px / 13 Bold @ `15,12,0,0` | `radius.sm` 5 / `text.title_sm` 13/600 | ✓ |
| 阴影 | radius 3，alpha 0.07→0.4，**主题色**，底边 +1px | 2.0 议题 D（QGraphicsDropShadowEffect，blur 12–16 accent@30%） | 方向一致 |
| 颜色过渡 | **90ms** | `motion.color` 90ms | ✓ |
| 高度动画 | 150ms ExtraStrong（≤800px）/ 分段 | `motion.fast` 150ms OutQuint | ✓ |
| 退出动画 | 200ms scale −0.08 + opacity | `motion.base` 200ms | ✓ |
| 箭头/旋转 | 250ms | `motion.slow` 250ms | ✓ |
| 列表行高 / 标题 / 副标题 | 42 / 14 / 12@0.6 | 建议 §5③（40–42 / 13 / 11 secondary） | 谱系一致 |
| 按钮按下 | scale 0.955 / 80ms | 2.0 议题 E | 方向一致 |
| 滚动条 | 8px / 圆角 3 / 1% 底色 | QSS overlay 已覆盖 | ✓ |
| 提示条 | 左 3px 色条 + 圆角 2 + padding 12,9 | 2.0 MyHint 等价物 | 待 1.5+ |
| 字体 | PCL English + 雅黑 UI，11–16 谱 | 雅黑 UI + Segoe UI，10–22 谱 | ✓（SWDM 略宽，保留） |

**参考文件**（GitHub raw，main 分支）：
- `Plain Craft Launcher 2/Application.xaml`（颜色表/控件模板/滚动条/菜单）
- `Plain Craft Launcher 2/FormMain.xaml(.vb)`（无边框窗口/Resizer/圆角剪裁/标题栏/页面切换动画/HSL 主题）
- `Plain Craft Launcher 2/Controls/MyCard.vb`、`MyDropShadow.vb`、`MyButton.xaml(.vb)`、`MyListItem.xaml(.vb)`、`MyLoading.xaml(.vb)`、`MyHint.xaml`
- `Plain Craft Launcher 2/Pages/PageSetup/PageSetupUI.xaml.vb`（HSL 主题/壁纸模糊/功能隐藏）
- `Plain Craft Launcher 2/Resources/Custom.xaml`（主页自定义 DSL——ColorBrush1–8/ColorObject1/4 动态资源用法）
