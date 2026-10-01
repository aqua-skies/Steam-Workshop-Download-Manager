# SWDM 2.0 重构路线可行性评估（rewrite_feasibility）

> 版次：2.0-pre · 2026-10 · 输入底料：[system_contracts.md](system_contracts.md)（core 域契约与学费清单）
> 决策人：讨论组 + 用户。本文档**给出推荐与路线图，不替用户定**。
> 评估方：AI agent 团队（swdm-142）· 代码事实基准：1.4.1 / 1.4.2-m1

---

## 0. 评估背景与约束（先立靶）

1. **现状**：Python 3.12 + PySide6 单体桌面应用；core 层已无 GUI 依赖（§system_contracts §0）；GUI 层 `workshop_tab.py` 1761 行巨型类、50+ 处内联样式；交付链 PyInstaller（45.5MB exe）→ Inno Setup 安装器，无自动更新。
2. **视觉标杆**：PCL2（Plain Craft Launcher 2，WPF）——`docs/design/design_tokens.md` 已实测其参数（白卡 245/255 + 3px 阴影 0.07→0.4 悬停抬升、3-5px 圆角、90ms 颜色 / 150ms 高度缓动、ColorBrush1/2/4 资源字典统一注入）。
3. **团队属性**：AI agent 团队，全项目经验在 Python/PySide6（1.3.0→1.4.1 七个迭代、87+ 回归套件、契约级教训见 system_contracts §1）。**驾驭度权重应高于"理论最优栈"**——这是本评估的第一约束。
4. **待迁移资产**（按可移植性排序）：
   - **经验资产（不可移植，需重新发现）**：429 请求头指纹研究（34 次实测）、403 分层对策、steamcmd 输出行为（无逐字节进度/0 字节假成功/downloads 临时目录）、GGNetwork 响应形状、受限 App 名单、WinSock 10053 连接熔断规律。
   - **架构资产（可直接平移设计）**：provider 链 + terminal 语义 + 熔断、downloader 状态机与 `_cancelling` 竞态收口、双失效缓存、SQLite 并发策略、退避/抖动/并发自适应/进度平滑算法、失败原因保守归类。
   - **实现资产（语言相关）**：全部解析器正则、SQLite schema、steamcmd 编排——逻辑可翻译，代码不可直接复用。
5. **性能数据声明**：本文档的冷启动/内存数值为**量级估计**（业界公开基准 + 同类工具经验值），本机未做跨栈实测；用户若有疑义，2.0 立项前可做最小原型实测（见 §6 阶段 0）。

---

## 1. 四路线 × 五维度评分矩阵（1-5，5 最优）

| 维度（权重） | ① C# WPF | ② Tauri（Rust+Web） | ③ Qt6 C++ | ④ PySide6 深度重构 |
|---|---|---|---|---|
| 美观上限（0.20） | **5** | **5** | 4 | 3.5 |
| 效率（0.15） | **5** | 5 | **5** | 2 |
| 迁移成本（0.25，5=成本最低） | 2 | 1 | 2 | **5** |
| 分发与更新（0.15） | 4 | **5** | 3 | 4 |
| AI 团队可维护性（0.25） | 4 | 3 | 3 | **5** |
| **加权总分** | **3.85** | **3.35** | **3.35** | **4.13** |

> 权重理由：迁移成本与 AI 可维护性各 0.25——本项目最大风险不是"选错了栈"而是"重写中途烂尾"；美观上限 0.20——PCL2 级视觉是明确目标但不是唯一目标；效率 0.15——桌面下载工具对 1-2s 冷启动可容忍；分发 0.15——现有 Inno 链已可用，自动更新是增益。

---

## 2. 逐路线分析

### ① C# WPF（PCL2 同栈）

**美观上限 5 —— 机制级论证**
- 控件模板（`ControlTemplate` / `DataTemplate`）+ 样式/资源字典（PCL2 的 `ColorBrush1/2/4` 实证）：主题色一键全局替换、令牌系统原生支持。
- 动画系统（`Storyboard` / `DoubleAnimation` / `EasingFunction`）：悬停抬升、颜色 90ms、高度 150ms ExtraStrong 缓动——PCL2 实测值全部是其默认能力。
- 无边框窗口：`WindowChrome` + `ResizeMode=CanResizeWithGrip`；圆角/阴影（`DropShadowEffect`）原生。
- 矢量图标：`<Path>` / Geometry 资源，任意 DPI 缩放。
- **结论**：PCL2 视觉是 WPF 的"默认上限之内"，不需要黑魔法。

**效率 5**
- 冷启动 < 300ms（.NET 8+ AOT 或 Native AOT 更快）；常驻内存 60-120MB（WPF 桌面应用典型值，含运行时）。
- 并发模型：`async/await` + `HttpClient`——无 GIL，下载并发与 UI 完全解耦；steamcmd 串行化用 `SemaphoreSlim(1)` 即可。

**迁移成本 2 —— 核心逻辑重写量 ~90%**
- 可平移设计：provider 链、状态机、熔断、双失效缓存、退避算法（架构层照抄 system_contracts）。
- **必须重写**：全部 Python 代码。429 指纹研究可移植（就是 HTTP 头规则 + 语义文档，`HttpClient.DefaultRequestHeaders` 加 `Accept-Language` 即可）；正则解析器（`Regex` 语义足够，但需逐条回归对比真实页 fixtures）；SQLite（→ EF Core 或 Dapper + 相同 schema）；steamcmd 编排（`Process` 对称于 `subprocess`，输出解析逻辑翻译）；keyring（→ Windows Credential Manager / DPAPI）。
- **不可移植的隐性成本**：87+ 回归套件作废，需重建 C# 测试体系；契约文档（system_contracts）是唯一的迁移说明书——这正是它第一优先级的原因。

**分发与更新 4**
- 单文件/单目录发布 + MSIX 或 Inno/Velopack；**Velopack / Squirrel.AutoUpdate 成熟**（增量差分更新链现成）。
- 依赖：.NET Runtime（可 self-contained AOT，约 60-150MB 安装包；比当前 45.5MB 大）。

**AI 团队可维护性 4**
- C# + WPF 生态成熟、文档充分、AI 驾驶度高（XAML 声明式 UI 尤其适合 AI 生成）。
- 风险：**团队全部 PySide6 经验对此路线零复用**；XAML 数据绑定/MVVM 心智模型与当前信号槽架构差异大；无渐进路径——C# 与 Python 不能共享进程（除非 C# 壳调 Python core 的双进程怪路，不推荐）。
- 回退点：**一次性梭哈**。开始后回退 = 沉没成本全部损失。

### ② Tauri（Rust 内核 + Web 前端）

**美观上限 5**
- Web 前端 = CSS/动画/SVG 的完整能力：`backdrop-filter`、`transition`、`@keyframes`、SVG 矢量、无缝换肤——**美居家数上限最高的方案**，远超 PCL2：任何 web 设计规范都可以直接抄。
- 无边框窗口（`decorations: false` + 自定义标题栏）官方支持。
- 阴影：Windows 11 自带圆角+阴影；`Shadow` API 或 CSS `box-shadow` 在 webview 内部成立。

**效率 5**
- 冷启动 ~0.5-1s（webview 首次加载）；常驻内存 30-80MB（Rust 内核 + 系统 webview 复用）。
- 并发模型：Rust `tokio` async 生态——最优；steamcmd 子进程编排（`tokio::process`）+ 串行信号量。
- 注意：WebView2 是系统组件依赖（Windows 10+ 自带，但 Edge 版本碎片化）。

**迁移成本 1 —— 核心逻辑重写量 ~100%**
- **这是唯一一条连"思维方式"都要换的路线**：Python 动态类型 → Rust 所有权/借用检查器。所有权与跨线程共享（`Arc<Mutex>` / channel）与当前"锁 + 回调"模型映射代价高。
- 全部解析器正则、steamcmd 编排、SQLite（→ `rusqlite`）、HTTP（→ `reqwest`）重写；429 指纹研究本身可移植（header 规则）。
- 87+ 回归套件作废且重建最难（Rust 测试 + 前端测试两套）。
- **AI 团队可维护性风险最高**：编译器严格意味着 AI 迭代速度慢（每次修正都要过 borrow checker）；团队零 Rust 经验；Rust 陷阱（unsafe 调 FFI、async 复杂签名、Windows 工具链）会吃掉大量轮次。

**分发与更新 5**
- bundle msi/nsis + **Tauri Updater 内建**（签名差分更新，官方一等公民）——四路线中最完善。
- 包体小（~10-30MB）。

**回退点 1**：全量重写，零渐进。Rust 内核与 Python 内核不能逐步替换。

### ③ Qt6 C++（或 Avalonia/XAML 系）

**美观上限 4**
- QSS 上限已知（`docs/design/design_tokens.md` 实证）：**QSS 无 `box-shadow`**，需 `QGraphicsDropShadowEffect`（对话框/悬浮卡可用，列表卡片有滚动性能代价）；动画需 `QPropertyAnimation`（Python 侧同款问题在 C++ 同样存在，自绘控件的悬停抬升需手工实现）。
- 但 **QML 是另一条路**：Qt Quick 的动画/粒子/着色器上限远超 PCL2（ShaderEffect 可做任何视觉效果）。QML + C++ 混合可达 5，代价是两套心智模型 + QML 调试困难。
- Avalonia（跨平台 XAML，WPF 精神继承者）：美观机制与 WPF 几乎同级（5），但社区比 WPF 小、Windows 单平台优势不明显。

**效率 5**
- 原生 C++：冷启动 < 200ms、内存 < 50MB——四路线最优档。
- 并发：`QThreadPool` / `std::thread` + Qt 信号槽跨线程（`Qt::QueuedConnection`）——语义与当前 PySide6 一致，**这是唯一"GUI 代码可机械翻译"的路线**（信号槽、布局、QSS 几乎 1:1）。

**迁移成本 2**
- GUI 层可翻译（PySide6 → Qt6 C++ 的信号槽/QWidget 语义同构）；但 core 逻辑全重写（Python → C++）。
- 构建链复杂：msvc + CMake + windeployqt + 静态链接（或动态分发带 DLL 群）；PyInstaller→Inno 经验全部作废。
- 429 研究可移植；正则（QRegularExpression/`std::regex`）需逐条回归。
- **AI 可维护性 3**：C++ 内存管理风险（与 Rust 不同，编译器不挡错误，bug 更隐蔽）；构建错误对 AI 不友好（链接错误、ABI、部署缺失 DLL）；团队零 C++ 经验。
- 回退点：可拆成"core 重写 + GUI 翻译"两步，但第一步仍是全量重写。

**分发与更新 3**
- Inno/WiX + windeployqt 可用，但**无成熟自动更新**（QtIFW 或自建差分，均非开箱即用）。

### ④ 续用 PySide6 但按契约深度重构

**美观上限 3.5**
- QSS 上限是硬约束（无 box-shadow、无 CSS transition）：当前 `docs/design/design_tokens.md` 的令牌路线——「明度阶梯 + 描边」的 Steam 式高程 + `QPropertyAnimation` 悬停抬升 + `QGraphicsDropShadowEffect`（对话框）——**可达"接近 PCL2"的质感**（令牌文档 §2.1 逐项对比已给出差距与对策）。
- 缺的最后一公里：QSS 无颜色过渡（悬停瞬切，需 Python 侧 `QVariantAnimation` 手工插值）、列表卡片阴影受限。
- 变量：**QML 混合架构**（关键页面换 QQuickWidget）可把上限拉到 4.5+，代价是引入 §③ 的 QML 心智成本；2.0 可选做或不做。
- 已落地的 1.4.2 设计令牌系统（dark/light QSS + `design_system.TOKENS`）证明该路线"已在路上"。

**效率 2**
- 冷启动 1-2s（PySide6 + 解释器初始化，量级估计）；常驻内存 150-300MB（Python 运行时 + Qt + 混合）。
- 并发模型：GIL + QThread——**对网络/子进程 IO 型负载影响很小**（下载即 IO；steamcmd 是外部进程；正则/JSON 解析短暂持 GIL 可接受），但 UI 线程被 Python 字节码占用时的动画帧率上限低于编译型栈。
- 结论：对"工坊下载管理器"这类非实时、非高吞吐场景，2 分里包含的妥协可接受；若用户体感"启动慢"，可用 lazy import + 启动闪屏治标。

**迁移成本 5**
- **不是重写，是重构**。阶段一（core 解耦）大部分前置条件其实已满足：core 已不导入 Qt；剩余工作是消除隐式单例 + 事件总线化 + 契约测试显式化（system_contracts §6）。
- 阶段二（GUI 层重写）：workshop_tab 拆分、联想模型化、代际管理器统一、令牌全量落地——全部在现有 87+ 回归套件护栏内迭代，**每一步可验证、可回退**。
- 429 研究、provider 链、状态机、解析器**零重写**。

**分发与更新 4**
- 沿用 PyInstaller + Inno（45.5MB 现状，包体可通过排除二进制依赖优化）；自动更新可加（Squirrel.Windows / 自建差分包，均有 Python 生态实现），不是阻塞项。

**AI 团队可维护性 5**
- 全部团队经验在此；Python 动态语言对 AI 迭代最友好；**回退点最密**：每个阶段都是可发布的 1.5/2.0 版本，任何时候停手都不亏损。

---

## 3. 决策矩阵（敏感度检查）

把"美观上限"权重提到 0.35（用户如果把 PCL2 级视觉列为第一优先）：

| | 美观 0.35 | 迁移 0.20 | AI 维护 0.20 | 效率 0.10 | 分发 0.15 | 总分 |
|---|---|---|---|---|---|---|
| WPF | 1.75 | 0.40 | 0.80 | 0.50 | 0.60 | **4.05** |
| PySide6 重构 | 1.23 | 1.00 | 1.00 | 0.20 | 0.60 | **4.03** |
| Tauri | 1.75 | 0.20 | 0.60 | 0.50 | 0.75 | **3.80** |

**解读**：即便把美观权重顶到 0.35，WPF 与 PySide6 深度重构仍打平（4.05 vs 4.03）——因为 PySide6 路线的"低成本迁移"（1.00）在低权重下依然净胜。WPF 只在"美观 = 绝对唯一目标 + 不惜重写"时才是优选。**Tauri 在任何权重下都不占优**：它的两项 5 分（美观/效率/更新）都被两项致命短板（迁移 1、AI 维护 3）压住。

把"效率"权重提到 0.35（性能优先场景）：Qt C++ / WPF 上升，PySide6 降到 ~3.8——但 SWDM 不是性能敏感场景（§2④效率论证），此权重不成立。

---

## 4. 推荐路线

**推荐：路线 ④（续用 PySide6 按契约深度重构）作为 2.0 默认路线**，理由：
1. 加权总分第一（4.13），且在美观权重翻倍的敏感度检查下仍不输（4.03 vs WPF 4.05）。
2. **所有路线的共同前置都是"core 解耦 + 契约测试"**——阶段一无论最后选哪条都在做同一件事；而阶段一完成后，路线 ④ 只需继续，换栈则需从头翻译。先做 ④ 的阶段一，等于"给自己留了换栈的选项，但不提前下注"。
3. 团队经验复利（用户规矩：域 owner 跨迭代稳定）——PySide6 域知识已进入 system_contracts 的每一条学费，弃之是最大浪费。
4. 唯一具备**渐进回退点**的路线：1.5（core 解耦）→ 2.0（GUI 重构）每步独立可交付、可回归、可停止。

**不推荐 Tauri**：在任何权重组合下不占优，且 Rust+AI 迭代速度 + 零经验 + 全量重写三重风险叠加。

**保留换栈期权**：若 2.0 完成后用户对 QSS/QML 混合架构的美观上限仍不满意（或需要 <300ms 冷启动），届时启动 WPF 移植——契约文档 + 契约测试体系就是移植说明书。**这是阶段一最重要的战略价值：它把"换栈"从一次性赌博变成有说明书的工程。**

---

## 5. 分阶段迁移路线图

> 原则：每个阶段结束 = 一次可交付的版本（全量回归 + 讨论组评审 + 版本号，遵守迭代四要素）。

### 阶段 0：契约固化（可并入 1.5 中后期，~3-5 人日）
- 把 system_contracts §1 每条不变量落成显式契约测试（当前回归套件覆盖大半，补缺口：节流锁覆盖并发场景、terminal 语义、_cancelling 竞态时序、双失效缓存、SQLite 30s 锁、深拷贝断言）。
- core 无 Qt 化可验证判据：在无 PySide6 环境跑 core 测试全绿。
- 产出：`docs/architecture/` 成为新成员/新栈的统一入口。

### 阶段 1：core 层解耦（2.0 阶段一，~5-8 人日）
- 隐式单例 → 显式注入：`Services` 容器升级为构造注入 + 生命周期管理；`get_config()/get_api_cache()/get_registry()/get_detail_cache()` 收口为容器内对象（保留临时兼容层）。
- 回调 → 事件总线：`DownloadManager.on_started/progress/finished/queue_changed` 统一为 append 订阅的事件总线（core 发事件、GUI 订阅），边界唯一化；同时清理 `DownloadEventBridge.attach` 的赋值式订阅。
- job 状态机显式化：引入 `PENDING` 状态吸收 `_pending_refresh`/`_pending_search_term` 隐式标志位；QUEUED/PENDING 命名统一。
- workers 层收口：`_ImageTask` 自建 SteamAPI 逃逸点改正（经 Services 取实例）；后台任务管理器（保活池 + 代际 + 取消一体）从 workshop_tab 提升为 gui 层公共组件。
- 判据：core 包零 Qt 导入（静态检查）；契约测试全绿；GUI 行为零回归（87+ 套件 + 1.4.2 新增套件）。

### 阶段 2：GUI 层按令牌重写（2.0 阶段二，~10-15 人日）
- workshop_tab 拆分：游戏选择器组件（联想模型化——`QStandardItemModel`/`QCompleter` 增量更新替代 clear() 重建）/ 列表容器 / 卡片组件 / 预取管理器 / 代际管理器（去抖+代际+在途一站式）。
- 设计令牌全量落地：`docs/design/design_tokens.md` 路线图（1.4.2 已完成卡片试点与 QSS 骨架）→ 1.5 清单（library/downloads/settings 卡片迁移、对话框阴影）→ 2.0 清单（左侧栏导航旗舰改动、density 令牌、动效令牌落地为 `QPropertyAnimation`/`QVariantAnimation` 封装）。
- 判据：像素级设计验证延续 `tools/verify_design_shots.py` 断言链；每组件独立契约测试。

### 阶段 3：期权评估（2.0 完成后，按需）
- 美观/效率仍不达预期 → WPF 移植立项：以 system_contracts + 契约测试为说明书，C# 端逐模块翻译 + fixtures 对比回归（解析器先行，provider 链与状态机次之，UI 最后）。
- 美观达标但启动慢 → lazy import + 启动闪屏 + 冷启动实测（< 可接受线即收）。
- 均 OK → 保持 PySide6，进入功能迭代节奏（用户需求调研里 Valve 2026-01-08 工坊版本控制是差异化窗口，功能优先级可能高于换栈）。

---

## 6. 风险登记与回退点（按路线）

| 路线 | 主要风险 | 触发信号 | 回退动作 |
|---|---|---|---|
| ④ PySide6 重构 | 拆分引入行为回归；代际管理器迁移期出现结果错乱 | 任何轮次回归红 | 阶段内 git 层面可逐 commit 回退；每阶段独立可发布，最差停在 1.5 |
| ① WPF | 烂尾（重写周期 > 预期 2 倍）；429 经验在新 HTTP 栈上失效 | 阶段性原型无法复现关键行为（如详情页 200 率） | 立项前先做 2-3 日最小原型（全部核心端点 + steamcmd 编排冒烟），原型失败即放弃 |
| ② Tauri | borrow checker 迭代慢；webview 碎片化 | 连续多轮卡在同一模块 | 阶段 0 原型（Rust 端点 + 一个下载链路）失败即放弃 |
| ③ Qt C++ | 构建链/部署问题吃掉轮次 | windeployqt 链路跑不通 | 同上，先冒烟构建链 |

**所有路线的公共前置：阶段 0 + 阶段 1。** 这也是本文档把推荐写成"④ 为默认、换栈为期权"的结构性原因。

---

## 7. 结论（供讨论组与用户裁决的一段话）

2.0 的本质决策不是"选哪个技术栈"，而是"先把 core 层从 GUI 与隐式单例中彻底解放出来并用契约测试锁死"。这件事（阶段 0+1）无论未来选哪条路线都必须做，且做完之后换栈成本会从"凭运气重写"降为"按说明书翻译"。推荐：**2.0 走 PySide6 深度重构（阶段 1 解耦 + 阶段 2 令牌化 GUI），保留 WPF 期权；Tauri 与 Qt C++ 在当前团队结构与项目场景下不推荐。** 请讨论组按三原则（精简 / 以用户体感为中心 / 保证基本功能正常运行）评审，由用户终裁。
