# SWDM 1.4.2 竞品调研报告（2026-09-30，只读调研）

调研方式：GitHub Search/Repo API + README 抓取（只读 GET，未触碰工作区任何文件）。
"近半年活跃"判据：2026-03-30 之后有 push。star/提交数据截至 2026-09-30 查询时。

---

## ① 新玩家或老工具的新动态

### A. 活跃新玩家（近半年有实质更新）

**1. sefrawe/Steam-Workshop-Mod-Assistant-Management-Tool — 最直接的同赛道中文竞品（强烈关注）**
- 仓库：https://github.com/sefrawe/Steam-Workshop-Mod-Assistant-Management-Tool
- star=1，2026-09-07 创建（仅 3 周大），2026-09-30 今天仍在提交（近一周每天多次 commit）。MIT，中文界面。
- 技术栈与 SWDM 几乎一致：Python 3.12 + PySide6 + steamcmd + SQLite(WAL) + PyInstaller；终端用 pywinpty(ConPTY)；备份用 robocopy(/MT 多线程)。
- 核心功能：SQLite 账本登记 mod 编号/状态/版本/更新历史/备注；批量更新检测（远端更新时间 vs steamcmd acf 本地时间，分桶展示）；内置 ConPTY steamcmd 终端（**下载命令由用户复制粘贴到终端亲自执行，软件"绝不代替你执行下载"**）；更新前 robocopy 自动备份（按 mod 保留份数+全局容量上限+钉住豁免）+ 一键恢复（恢复前强制先备份当前版）；账实核验（"账上有/盘上有/版本一致"三差集报告，异常条目一键生成修复命令）；软删除（可恢复）；多游戏档案（RimWorld/CK3/任意工坊游戏独立账本切换）；junction 目录连接双向拓扑识别；换机迁移七步引导；清单分享（含备注/标签/特别关注，导出/一键并入）；深色主题三态；QtCharts 统计图表+高级筛选；失效 mod 处置（远端失效自动归档/关联替换）；绿色便携免安装。
- README（3964 字节）维护：截图嵌入正文（主界面/日常更新/备份/统计页）+ 技术栈表格 + **显式"设计原则"一节**（单源架构：steamcmd 目录为唯一数据源、acf 只读永不修改；不代替用户判断；绿色软件；界面自文档化；不内置 steamcmd）+ FAQ（杀软报毒/账号需求/数据位置/与 Steam 客户端订阅冲突）+ 使用须知（steamcmd 单点登录会顶号、同 mod 勿两边同时管理）。

**2. dane-9/Streamline-Workshop-Downloader — 最高 star 的活跃下载器（147★）**
- 仓库：https://github.com/dane-9/Streamline-Workshop-Downloader
- star=147，JavaScript（pywebview），LGPL-3.0，2024-10 创建，2026-08-13 提交并发布 v2.2.0（含 Windows/Linux 自动化 release 构建）。
- 功能亮点（多处于 SWDM 之上）：虚拟滚动队列（数千 mod 不卡、marquee 框选、批量操作、拖拽重排、拖拽导入、状态过滤、动画状态徽章）；**Command Palette（Ctrl+K / 双击 Shift，搜索式启动全部动作）**；交互式 SteamCMD 终端（应用内输 Steam Guard 码、密码可见输入且不保存）；实时日志总览（可折叠操作分组 + RUN/DONE/WARN/ERROR/STOP 颜色徽章 + 分类过滤）；多 Steam 账号管理（头像自动拉取、拖拽排序）；单 mod/整个集合/**整个游戏的工坊抓取（上限 50,010 个）**；SteamCMD 与 SteamWebAPI **多 provider 同时下载且可不同 AppID**；自动下载初始化 SteamCMD；AppID 列表用 Botasaurus 从 SteamDB 自动抓取更新；mod 自动检测归属游戏；剪贴板 URL 检测自动入队；队列导入导出；可配置批次大小；无边框自定义窗口。
- README（5997 字节）：banner+GUI 截图、for-the-badge 徽章矩阵（Release/ReleaseDate/Downloads/Stars）、**功能表格（Feature|Description，细则用 `<sub>` 小字）**、按平台分节的安装说明；README 与版本 bump 同日更新。

**3. Apricityx/WorkshopAndroidDownloader（WorkshopOnAndroid）— 移动端新玩家（134★）**
- 仓库：https://github.com/Apricityx/WorkshopAndroidDownloader
- star=134，Kotlin + Jetpack Compose，Apache-2.0，2026-03-12 创建，2026-08-28 推送（v1.1.10-hotfix5，密集 hotfix 节奏）。
- 定位：Android 端工坊下载器。预置热门工坊游戏+搜索+AppID 加游戏库；抓 Steam Community 页面浏览（搜索/分页/详情）；公开条目匿名下载，可选 Steam 协议登录（自研 `:steam-protocol` 模块管 CM 连接/认证/内容服务器发现/CDN 授权，`:workshop-core` 管 manifest/chunk/校验/解压/组装）；ADB Gradle 任务跳过 UI 直接触发下载拉日志。
- README（6343 字节）范式：徽章矩阵 + 锚点目录导航 + GitHub 告警框（`>[!IMPORTANT]` 澄清登录态绑定策略、`>[!NOTE]` 模块架构）+ **明确的"当前限制"一节（不支持 Collection 下载、二维码登录）**。

**4. someonenameguy/Workshop-Controller — 并行下载 + localhost Web UI（技术参考价值最高）**
- 仓库：https://github.com/someonenameguy/Workshop-Controller
- star≈1，Python 3.10+ FastAPI + 暗色 localhost Web UI，MIT，2026-09-08 活跃，33 tests。
- 核心差异：**并行 SteamCMD 下载（1–8 worker，默认 3，每个 worker 跑独立 staging 环境以完全规避 `appworkshop_<appid>.acf` 文件锁冲突与缓存竞争**——正是串行架构要回避的痛点）；多游戏多文件夹 profiles（RimWorld/Stellaris/Cities Skylines/PZ/GMod/DST，顶栏下拉即时切换）；"Mod Folder Healer & Refactorer"（mod 文件夹修复/重构）；Steam 风格标签过滤搜索；首次启动自动从 Valve CDN 检测/下载解压 SteamCMD；元数据+高清缩略图本地 JSON 缓存；自动更新扫描；零依赖打包（前端自包含、无 Node/NPM 构建步骤）。
- 注意：其近期 commit 在修并行带来的 worker 目录清理与 0 字节 mod 问题——并行方案自身仍在填坑。

**5. 其他活跃小工具（垂直/轻量方向）**
- chadlrnsn/workshop-downloader（1★，Wails Go+Svelte 5，2026-06-14）：EN/RU 双语 README 分节；Steam Guard Email+Mobile 2FA 的 UI 交互提示；**Sentry/SSFN token 持久登录**；steamcmd 自动依赖下载解压配置；队列重试。
- n1rm/norm-wallpaper-engine-downloader（3★，**PySide6 同栈**，2026-09-11）：Wallpaper Engine 垂直场景；无账号（hardcoded community access）；自动检测游戏安装路径；霓虹主题动画；EN/TR 双语。下载引擎用 DepotDownloaderMod（.NET）而非 steamcmd——替代引擎路线。
- c-creatorofficial/steam-workshop-downloader（0★，Python 单文件 CLI，2026-09-25）：GMod/SFM 垂直；零安装自举（自动 pip 装 rich/requests/bs4/Pillow）；**智能检测 mod 描述里的站外托管链接（Google Drive/Mega/Mediafire）**；.gma LZMA 自动解压+gmad.exe 解包；创作者主页爬取批量下载；HTTP 流式直下+自动断点续传+必要时回退 SteamCMD；预览图画廊抓取转 jpg。

### B. 老工具停滞/归档动态（确认竞品真空期）
- NethercraftMC5608/NetherWorkshopDownloader（110★）：**最后 push 2025-06-23（超一年），最新 release 2024-06**——曾经的最强竞品已实质性停滞。
- fidget77/WorkshopDL（46★）：push 2023-09（3 年）。Geam/steam_workshop_downloader（52★）：push 2021。notSeilce/SteamWorkshopDownloader（22★）：push 2025-02（19 个月）。jannes-io（10★）：2022。
- Husko（84★）：确认 archived（后端停止，与此前归档结论一致）。cappig（18★）：archived 2023。
- 结论：**近半年活跃且成规模的同赛道竞品只有 Streamline（海外）与 sefrawe（中文，极新）；SWDM 处于"老工具集体停滞、新玩家刚起势"的窗口期**，1.4.2 是巩固差异化的大好时机。

---

## ② 对 SWDM 的可迁移建议（按推荐度排序，每条含四维评估）

**S1. 更新前自动备份 + 一键恢复（来源：sefrawe）** ★强烈推荐
- 技术：subprocess 调 `robocopy /MT /XJ` 多线程复制旧版；按 mod 配保留份数 + 全局容量上限。
- 架构兼容：高——在现有下载管线中，对"库中已存在的同名 mod 更新"插入备份前置步骤，纯旁路增量，不动 provider 链/串行调度。
- 工作量：中（备份管理 UI + 份数/容量配置 + 恢复流程 + 测试）。
- 三原则：精简✓（单个"更新前备份"开关）；体感✓✓✓（mod 更新翻车是核心痛点，恢复=安心感）；基本✓（默认开，失败不阻断下载主流程）。
- 建议落地：1.4.2 作为 C 类功能首个候选。

**S2. 账实核验报告（来源：sefrawe）** ★推荐
- 技术：解析 steamcmd 产物 acf 文件，与 SWDM 现有库数据做"账上有/盘上有/版本一致"三差集。
- 架构兼容：高——复用现有库管理数据，只读核验+报告，不动下载层。注意：**不要新造第二套账本**，直接用 SWDM 现有库做差集（sefrawe 是 SQLite 账本路线，SWDM 库管理已等价）。
- 工作量：中低。三原则：精简✓（一个"核验"动作）；体感✓✓（消除"到底下没下成功"的信任焦虑）；基本✓。

**S3. 日志按操作分组 + 状态徽章（来源：Streamline）** ★推荐（低成本快赢）
- 技术：现有日志/控制台输出改造为可折叠操作分组 + RUN/DONE/WARN/ERROR/STOP 颜色徽章 + 分类过滤。
- 架构兼容：高——纯 GUI 层（SWDM 已有 QSS 美化基础）。工作量：低-中。
- 三原则：精简✓；体感✓✓（失败排查效率大幅提升）；基本✓。

**S4. Command Palette（Ctrl+K）（来源：Streamline）** 推荐
- 技术：PySide6 实现（快捷键唤出 + QLineEdit 搜索 + 动作注册表 + 键盘导航）。
- 架构兼容：高——一个聚合入口，复用现有菜单/动作。工作量：中。
- 三原则：精简✓（不新增功能只聚合入口）；体感✓✓（进阶用户效率翻倍）；基本✓（不影响现有交互）。建议 1.4.2 或 1.5。

**S5. README 维护方式对齐（来源：三者共同范式）** ★推荐（文档侧，1.4.1 手册基建的自然延续）
- 技术可行：高（纯文档）。工作量：低。
- 具体迁移点：① 加 GitHub 告警框 `>[!IMPORTANT]/[!NOTE]`（Apricityx 范式）；② 功能表格化 Feature|Description（Streamline 范式）；③ **新增"当前限制"一节，诚实披露 SWDM 已知限制**（SWDM 记忆里本就维护着已知限制清单，直接落入 README，Apricityx 范式最受用户信任）；④ FAQ 覆盖杀软误报/账号需求/数据位置/与 Steam 客户端订阅关系（sefrawe 范式）；⑤ for-the-badge 徽章矩阵 + 随版本 bump 同日更新 README（Streamline 的维护纪律）。
- 三原则：精简✓；体感✓（专业度/信任感）；基本✓。

**S6. 整游戏工坊批量抓取（"全部入队"）（来源：Streamline，上限 50,010）** 可选
- 架构兼容：中——SWDM 浏览/分页能力已具备，加"全选入队"自动化；与现有"批量粘贴"互补（URL 维度 ↔ 整库维度）。工作量：低-中。
- 三原则：精简✓（一个按钮）；体感✓（服主/整库备份场景）；基本✓。风险：大批量入队撞 Steam 限流（SWDM 已有节流/熔断基建，可控）。中优先级。

**S7. 描述内站外托管链接检测 + 预览图画廊（来源：c-creatorofficial）** 可选（小功能）
- 详情缓存已有，增量解析描述中 Drive/Mega/Mediafire 链接 + 全分辨率预览图。技术可行：高（复用详情缓存）。工作量：低。三原则：精简✓（详情页增量信息）；体感✓（mod 作者常把真更新放外部）；基本✓。低优先级。

**S8. 并行 SteamCMD 下载（worker 池 + 隔离 staging）（来源：Workshop-Controller）** ⚠️ 建议不去 / 长期观察
- 技术：可行（1–8 worker，每 worker 独立 staging 规避 acf 文件锁）。
- 架构兼容：**低**——SWDM 的串行化是有意设计（避免 acf 锁与 steamcmd session 冲突）；并行需引入 worker 池、staging 隔离、并发清理、同账号多实例互相顶号风险。
- 工作量：大。三原则：精简**✗**（显著抬升复杂度，违背"精简"）；体感✓（仅大批量用户有感）；基本✗（新增失败模式，Workshop-Controller 自己 2026-09-08 还在修 worker 目录清理与 0 字节 mod 的坑）。
- 结论：1.4.2 不做；可作为 1.6+ 长期方向持续观察竞品填坑进度。轻量替代：元数据抓取并行（SWDM 已实现）保留，下载层维持串行。

**S9. DepotDownloader 作为 provider 链一环（来源：n1rm）** ⚠️ 不建议
- 引入 .NET 运行时依赖 + 无账号硬编码社区 access 属于灰区，与 SWDM 多 provider 链式回退架构虽兼容但工作量/风险比收益差。记录为差异点即可。

---

## ③ 与 SWDM 现有能力的差异点（对照矩阵）

SWDM 现有能力基线：匿名浏览/搜索/排序/标签、steamcmd 串行下载+多 provider 链回退、库管理按游戏分类、依赖自动下载、冲突检测、详情磁盘缓存、剪贴板自动入队、批量粘贴、库更新检查、私人账号 provider、QSS 美化。

| 能力维度 | SWDM | Streamline | sefrawe | Workshop-Controller | 其他 |
|---|---|---|---|---|---|
| 下载引擎 | **多 provider 链式回退（独有）** | SteamCMD+SteamWebAPI 双源 | steamcmd 单源（用户手粘命令执行） | 并行 steamcmd worker+staging | n1rm: DepotDownloader；c-creator: HTTP 直下回退 steamcmd |
| 下载调度 | 串行化（稳定优先） | 批次大小可配置 | 批次排队+失败清单重跑 | **1–8 并行 worker** | nirm: 队列 |
| 备份/恢复 | ✗ 无 | ✗ 无 | **✓ robocopy 多线程+份数上限+一键恢复** | ✗ | — |
| 账实核验 | ✗（有冲突检测，不同维度） | ✗ | **✓ acf 三差集+一键修复命令** | ✗ | — |
| 更新检查 | ✓ 库更新检查 | ✓ 自动更新扫描 | ✓ 远端 vs 本地时间分桶（等价机制） | ✓ 自动更新扫描 | — |
| 依赖/冲突 | **✓ 依赖自动下载+冲突检测（独有）** | ✗ | ✗（仅 junction 拓扑识别） | Mod Folder Healer（修复维度另类） | — |
| 剪贴板/批量入队 | ✓ 剪贴板自动入队+批量粘贴 | ✓ 剪贴板检测+拖拽导入+**整库抓取(50k)** | 清单分享导出/并入 | Steam 风格标签过滤批量 | c-creator: 创作者主页爬取批量 |
| 队列/清单导入导出 | ✓ mod 包导入导出 | ✓ 队列导入导出 | ✓ 清单分享（含备注/标签） | 多游戏 profiles 切换 | — |
| 账号 | ✓ 私人账号 provider | ✓ 多账号管理（头像/拖拽排序） | 需登录拥有该游戏的账号 | 多 profiles | chadlrnsn: **SSFN/Sentry 持久登录+2FA UI** |
| 浏览 | ✓ 匿名浏览/搜索/排序/标签（完整） | 整库抓取 | 不做浏览（纯管理） | localhost Web UI 浏览 | Apricityx: Community 页面抓取浏览（移动端） |
| 缓存 | ✓ 详情磁盘缓存 | 元数据/缩略图 JSON 缓存 | SQLite 账本（全部状态） | 高清缩略图+元数据缓存 | c-creator: **描述站外链接检测+预览画廊** |
| UI | PySide6+QSS | 虚拟滚动队列+Command Palette+日志徽章 | ConPTY 内置终端+QtCharts 统计+深色三态 | 暗色 Web Dashboard | n1rm: 霓虹主题（同 PySide6） |
| 平台 | Windows（Inno Setup 安装包） | Win/Linux（便携+AppImage） | Windows 绿色免安装 | 跨平台 | Apricityx: **Android（唯一移动端）** |

**关键定位差异**：sefrawe 的哲学与 SWDM 相反——它"绝不代替用户执行下载"（命令手粘到终端），强调账实一致/可控可回滚；SWDM 走全自动批量省心路线。SWDM 应坚持自动路线（这是体感优势），但**吸收其"可回滚、可核验"的信任层能力（S1/S2）**——这是 SWDM 相对 sefrawe 唯二的功能缺口，也是最容易做出差异化的方向。相对 Streamline，SWDM 缺 Command Palette/整库抓取/日志分组徽章，但**有依赖自动下载+冲突检测+多 provider 回退这三张独有牌**，是老工具停滞期内应强化宣传的卖点（S5 的 README 改造可承载这一点）。

---
调研边界声明：仅做公开 GitHub API/README 只读调研，未修改工作区任何文件（遵守代码冻结约束）；未对竞品源码做精读（如需实现 S1/S2/S3，建议后续派源码精读 subagent 补充 robocopy 参数细节与 acf 解析字段细节）。
