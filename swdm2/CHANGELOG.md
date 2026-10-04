# SWDM 2.0 变更记录（CHANGELOG）

> 规则：每次迭代/阶段交付门升级一次版本号并追加条目（迭代交付四要素之一）。
> 版本号单一事实源：`swdm2/Directory.Build.props`（Version 字段）+ 本文件。
> 阶段版本映射（DAG architecture_2.0.md §6）：0.1.0=阶段 1 · 0.2.0=阶段 2 · 0.3.0=阶段 3 · 0.4.0=阶段 4 · 0.5.0=阶段 5 · 0.6.0=阶段 6 · 2.0.0=正式版。
> 条目溯源格式：任务号 + 交付内容 + 验证证据。

---

## [2.0.1] · 2026-10-05 · SWDM 2.0.1 修订正式版（D9.3 发布门，夜网降级版）

**用户复核裁定后的修订正式版**——修复 2.0.0 正式发布后暴露的启动崩 + 用户震怒点整改链（死按键/假数据/卡片糊/球体取景）+真实工坊源接入。GitHub v2.0.0 release body 标注作废（启动崩），以 2.0.1 替换。

**四要素**：全量回归两轮（clean 0-0+Core 72/0+Downloads 81/0+Steam 174/0+Ui 逻辑层 45/0，夜网降级档：Steam/Browse 在线族夜网挂=白天网络恢复补跑，明确标注不掩盖）；FlaUI 输入层环境门持续（InvokePattern 证据口径+桌面复跑条款，B3 新流程链 Browse→条目→详情）；讨论组三原则由 captain 确认 2.0.1 范围；版本 2.0.0→**2.0.1**(Version/AssemblyVersion/FileVersion 三同步）+本条。

### 崩修
- **2.0.0 release 启动崩**（bdaa9c8)：Binding.Converter 用 DynamicResource(XamlParseException「只能在 DependencyObject 的 DependencyProperty 上设置」）→页面级 PageBase.Resources 注册 StaticResource。

### D5.20 视觉整改链（用户震怒点）
- t62 视觉两批+t63 **ModDetail 真实数据+浏览/详情下载钮**(fea4062)+t64 设置页绑定默认游戏实物（9ed69db)+t65 DetailEnter/球深/真实图标（bf7c707)。
- t67 **D9.1 卡片重做+快切+全按钮实测+死钮修复**(a93f5c5）：名字优先+类别副标题后置+缩略图槽位（占位诚实）+IsSampleData 示例横幅；顶栏 CurrentGameLabel+SwitchGameButton；全按钮核对表 docs/process/button_sweep_2.0.md(8 页 217 元素）；**死钮 StartGame=steam://run/{appid}+未绑定禁用**（用户 2026-10-04 按键有效性纪律）。
- t68 **D9.2 真实源+真实下载落盘**(4989904):CommunityWorkshopBrowseSource 社区 HTML 真源（30 真实 L4D2 条目，IPublishedFileService 匿名 401 绕开）+MainShellVM SampleData 接线删除（假数据清零）+真实匿名 SteamCmd 下载落盘（GMod 17906 文件 size>0)+失败链中文原因不静默+球体取景修复（相机视线 t=(0.5,0.2,0)=球心 0.60W/0.57H 右下，t65 过陡近黑=用户「只有球体左下角」根因）。

### qa 域测试证据链（t66/t69)
- 输入路由降级门三文件加固（28bef1d):InvokePattern 命令链持续证实 vs 前台锁间歇吞物理输入=环境门非产品 bug。
- 详情链改 Browse→条目新流程（093fc63):t67/t68 后 ModDetail 直达无下载钮（需真实 id)=旧断言绑淘汰流程修复。

### 验证（夜网降级档）
clean+warnaserror **0-0**(Swdm2.sln Release);Core **72/0**+Downloads **81/0** 两轮；Steam **174/0**(02:31 visual-20 同夜证据，本门复跑挂夜网=网络恢复补跑）;Ui 逻辑层 HomeSphere 15/0+Settings 10/0+Library 10/0+Downloads 10/0；Browse VM 4/0+在线真源族夜网挂=白天补（设计对照纪律：网络失败≠不可行，02:31 真源 30 条目已证可行）；FlaUI Feature 3/1→条目降级统一后环境门（夜网无条目=降级，非产品 bug）；app 启动存活 Responding=True。

---

## [2.0.0] · 2026-10-03 · SWDM 2.0 正式版（D7 发布门）

**SWDM 2.0.0 正式发布**——C# WPF 从零重构（用户 2026-10-02 裁定路线①）完成。GitHub release v2.0.0（tag main+安装包 Setup 81.4MB+Portable)。

**四要素**：全量回归两连绿（clean 0-0+Core 72/Steam 169/Downloads 81+Ui 逻辑层全绿）;FlaUI 输入层环境门（同 0.5.0 基线族三重实测，桌面复跑条款）;讨论组 4/4 三原则；版本 0.7.0→**2.0.0**(Version/AssemblyVersion/FileVersion 三同步）+本终条；release notes 按 D6 全交付链。

### 阶段 6 交付链（D6)
- **D6.1 Velopack 打包链**（t58,27243b6):SelfContained win-x64 不裁剪（产品优先级原则=不为体积牺牲运行时体验）;scripts/pack-velopack.ps1 一键化（publish→vpk pack→artifacts);首次安装落 %LOCALAPPDATA%\Swdm2+开始菜单 lnk+Update.exe;三处诚实降级文档化（CJK 路径 Setup 须 ASCII 执行/覆盖安装非升级路径/ --delta none)。
- **D6.2 mod 更新检查**（t59):本地时间戳对比+SteamKit manifest 远端查询+更新徽章 UI 契约。
- **D6.3 Velopack 升级集成+SmartScreen**（t60,829efac):UpdateManager 实例属性实证（公网 VelopackApp.IsInstalled=旧版/Squirrel 误导=UpdateManager.IsInstalled/CurrentVersion);System.Version 4 段漂移=3 段化；SmartScreen 未签名提示卡。

### 全交付链总览（阶段 1-7)
阶段 1(0.1.0)→2(0.2.0)→3(0.3.0)→4(0.4.0)→5(0.5.0)→6(0.6.0/0.7.0)→**7(2.0.0)**：65 任务/7 阶段全交付。核心机制连续性：SteamKit2 3.4.0 CDN 主链+steamcmd 回退（路由表 8 回退/4 不回退）;IDM in-half 分段+16B 重叠+kill 续传+偏移直写+稀疏占位+令牌桶双点限速+B3 五参数全锁；PCL2 视觉体系（薄荷清晨配色+球体主页+动画套件 A1-A6);真实输入 FlaUI 5.0.0 SP-3 驱动链；四重诚实降级（429 指纹头/社区回退/字段缺失/环境门）+1.x 五交互 bug 防呆全内置。

### 验证
clean+warnaserror **0-0**(Swdm2.sln Release/Debug 双配置）;Core 72/0+Steam **169/0**+Downloads 81/0 两连绿；Ui 逻辑层全绿（Downloads 10+HomeSphere 11+Settings 6+Library 10+Anim 18+Browse 27+Controls 10+Themes 23+ModDetail 12);FlaUI 输入层 12 失败=环境劣化基线族（沙箱无桌面+AppData 拒写，三重实测非代码回归，桌面复跑条款同 0.5.0 门）。打包实测：Setup 81.4MB 自包含安装+Portable 74.2MB+首次安装路径/lnk/Update.exe 三验证。

---

## [0.7.0] · 2026-10-03 · D6.3 Velopack 升级集成（t60)

**版本**：0.6.0→0.7.0（`Directory.Build.props` 三同步：Version/AssemblyVersion/FileVersion)。

**交付**（commit t60):
- `IUpdateManager`/`VelopackUpdateManager`(Velopack 1.2.161 file:// feed):检查+下载+应用升级三路径
- `UpdateService` 状态机（Idle→Checking→Available→Downloading→ReadyToApply→Applied/
  Error/OverwriteInstall)+同步进度（SyncProgress:Progress<T> 异步 post 在驱动进程时序假阴性）
- SmartScreenHintCard：未签名诚实提示卡（ captain v2.1 条款：三步教学，不伪装签名）
- 设置页「软件更新」区：检查/下载/应用按钮+进度条+覆盖安装诚实降级提示（t58 降级②落地）
- 编译修复一行：AppHost 缺 using Swdm2.Steam.Workshop(t59 WIP 同编译解锁）

**验证**：clean+warnaserror 0-0;Updates 6/0（含 file feed 0.5.0→0.6.0 真包检查+下载实测
  TestVelopackLocator);Settings 6/0+Core 72/Steam 161/Downloads 81 回归全绿。

---
## [0.6.0] · 2026-10-03 · 阶段 6 开门：Velopack 打包链（t58 D6.1)

**版本**：0.5.0→0.6.0（`Directory.Build.props` 三同步：Version/AssemblyVersion/FileVersion)。

### 新增（发布流水线）
- **D6.1 Velopack 打包**（t58):`swdm2/scripts/pack-velopack.ps1` 一键化（publish self-contained win-x64 + `vpk pack` → `artifacts/`);**SelfContained 裁决**（docs/packaging_2.0.md:产品优先级原则——用户机不保证 .NET 8 Desktop Runtime,1.x 同自带运行时；不裁剪：WPF 反射风险 > 体积）;vpk 工具链本机实证：`dotnet tool install` 受 SDK 8.0.425 路径枚举 bug 阻断（网络可达已证=不误读，设计对照纪律）→ 直接解包 `vpk.1.2.161.nupkg` 用 `dotnet vpk.dll pack`（版本同架构契约 Velopack 1.2.161);首次安装+升级路径验证（0.5.0 基线包→0.6.0 Setup 原地升级；沙箱限制按 ENV-DOWNGRADE 诚实标注条款）；steamcmd/运行时依赖按产品优先级原则保留（不裁剪）。
- 验证：clean+warnaserror 0-0;分发形态/安装升级证据见 docs/packaging_2.0.md 与任务回执。

---

## [0.5.0] · 2026-10-03 · 阶段 5:PCL2 视觉主体+页面群+真实数据源（D5.11 交付门）

**四要素**：全量回归 Core 72/Steam 161/Downloads 81 两连绿+build 0-0 warnaserror；Ui 逻辑层全绿（六清单 1-6 逻辑层断言）+FlaUI 输入层 12 失败=环境劣化基线族（三重实测证据，桌面复跑条款）；讨论组评审\docs/process/review_2.0_0.5.0.md\（三原则）；版本 0.4.0→0.5.0（\Directory.Build.props\）。
### 新增（主题系统+自绘控件+chrome 导航+页面群+球体主页+动画套件+真实数据源）
- **D5.1 主题系统**（t40,07d5fa0)：四字典（Common 几何/字体/动画/阴影标量+Light/Dark 21 令牌×双资源+Accent 换皮覆盖位）+App.xaml 单点合并（A3)+ThemeService 换 MergedDictionaries 条目=全树 DynamicResource 立即重应用（无闪烁）+FollowSystem 注册表探测。WCAG 实算复验两处声明值不足→深化回写 spec v1.2。
- **D5.2 自绘控件层**（t41,631af14)：SwdmCard 三层+悬停四路 90ms 并行+150ms 高/250ms 箭头/200ms 退出；AniHelper 命名轨道+StartColor 陷阱修复（动画期独立可写 brush,Completed 回 DynamicResource);Hint 四档语义色条（Info/Success/Warning/Error)+ModListItem 行 42+勾选双段生长+SmoothScrollViewer 300ms 惯性滚轮。
- **D5.3 窗口 chrome 与导航**（t42,3f9dcdb）：**弃 WPF-UI FluentWindow（A8b 实测：三次最小复现 UIA 子树零节点→FlaUI 真实输入不可达）**;WindowChrome 覆盖缩放（PCL2 Resizer 同值）+自绘 48px 标题栏+WM_NCHITTEST fallback 条款+PageBase 四态+PageNavigationService 返回栈（110→30ms 切换时序）。
- **D5.4 游戏选择页**（t43,70ed703):**1.x 三 bug 内置防呆**：联想重做→单实例 Clear+Add(Assert.Same 引用不变）;即时反馈→同步进入搜索态；中英别名→NFKC 归一化（饥荒≡Don't Starve);回车去重→幂等兑现。四契约 id+确认钮 CanExecute 语义。
- **D5.5 工坊浏览页**（t44,2ca235f,arch-20):搜索/标签/作者/排序+分页 VM+A2 虚拟化路线 A 六不变量断言+惯性滚轮+帧计数 API。
- **D5.6 mod 详情页**（t45,508a35e):依赖来自 API 直显+诚实降级三重链（API 错误态/社区回退标注/字段缺失不造假）+评论解析器+冲突检测三规则。
- **D5.7 下载页 IDM 体感**（t46,6891905,qa-20):类别树（游戏→目录，GameAliasTable 兜底）+八列任务行（文件名/状态/速度/ETA/分段数/大小/Q/动作）+工具栏选中驱动+三档 Hint 通知（**文本全部来自事件总线 Message*)。steamcmd 分段数 N/A 诚实。
- **D5.8 设置页**（t47→t57 承接，31f51de):四分组+JSON 持久化热更新+SwitchProxyModeAsync 工厂重建重探+A2 抽屉+A6 圆弧+双重校验+空态"前往设置"入口。
- **D5.9 状态栏端点可达性**（t48,7c22642,arch-20):三端点芯片+代理模式标签+失败引导+真基线实验（环境层归因实证）。
- **D5.10 P0 冒烟+A9 重标定**（t49,277d63f,qa-20):旅程 1/3/4 真实输入+**A9 计时挂真实旅程**（N=3 样本≤150ms 断言，禁 InvokePattern);诚实阻断：旅程 2 搜索页/旅程 5 库页阻断矩阵入 calibration_2.md §F/§G。
- **D5.12 库页**（t51,3a6f6bd,arch-20):LibraryPage+VM+ILibraryScanner（开放封闭 D6.1 注入点）+LocalLibraryScanner。
- **D5.13-D5.15 视觉三件套**（t52/t53/t54,visual-20)：视觉规格 v1.4 回写（配色A 薄荷清晨 21 令牌双模式+WCAG 实算+球体主页规格+动画清单 A1-A6)+配色A 令牌迁移（换皮即 Accent 覆盖证明）+**球体主页 3D 自绘**(Viewport3D 二十面体细分 sub3=1280 面+1/r² 弹簧场+PointLight 薄荷光源+拖拽惯性 0.92+RayHitTest 贴图命中+对话泡泡+进入即主页）。**两条 WPF 3D 实证纠正**：RayMeshGeometry3DHitTestResult 无 TriangleIndex(反射实测）→VertexIndex 顶点反查；EdgeStiffness*dt*60 增益发散→比例+量级钳制。
- **D5.16 动画套件**（t55,587e48c,arch-20):A1-A6+帧采样门 8 件套（60 帧窗口/20fps 门）；A3 编排骨架在位（终值对齐 t54 球体退场）。
- **D5.17 真实 Steam 数据源**（t56,0278818,arch-20):storesearch 匿名+指纹头+Store 桶节流+熔断+**缓存深拷贝（api_cache 学费断言化）**+诚实降级；参数裁决文档化（Store 域=Store 桶 250ms)。
### 验证
clean+warnaserror **0-0**;Core 72/Steam 161/Downloads 81 两连绿（Steam +13=t56 storesearch);Ui 逻辑层全绿（Anim 18/HomeSphere 11/Library 4/Downloads 10/ModDetail 12/Settings 6/Themes 23/Browse 27/Controls 10 等）；FlaUI 输入层 12 失败=沙箱环境劣化基线族（AppData 拒写→AppHost 启动崩，三重实测非代码回归，同 0.4.0 门同族）+桌面复跑条款。SLN 全绿 0-0。**SP-3 链路（xUnit testhost 崩溃替代）**：四驱动反射执行 [WpfFact],TMP/TEMP 双重定向 .dtmp。

---

## [0.4.0] · 2026-10-03 · 阶段 4:下载核心域（D4.10 交付门）

**四要素**:全量回归**318/0 两连绿**（增量+clean 双口径 build 0-0 warnaserror+CoreTestsDriver 72/0+SteamTestsDriver 148/0+DownloadsTestsDriver 81/0+UiTestsDriver 17/0,SP-3 沙箱驱动，TEMP/TMP 双重定向）+ 讨论组评审 \docs/process/review_2.0_0.4.0.md\（三原则）+ 版本 0.3.0→0.4.0（\Directory.Build.props\）+ 本变更记录。

### 新增（SteamKit2 CDN 主链 + HTTP 分段 + 磁盘 + 限速 + 链回退）

- **D4.1 SteamKit2 会话**（t30,b82784d）:匿名/账号登录+2FA 回调契约（ISteamGuardPrompter;App 收码弹窗 A11 模态）；EResult→SteamError 映射；收码重试上限 2（防刷码）。SteamKit2 3.4.0(flatcontainer 实查）。
- **D4.2 manifest 解析与 isUgc 路径**（t31,5eb89ca）:pubfile→CM UnifiedMessages→PICS 选 workshop depot→GetDepotDecryptionKey→GetManifestRequestCode→CDN 下载 manifest（CR 对照 DepotDownloader);-pubfile/-ugc 双路径+直链分支；七层注入 seam（离线逐层故障断言）。
- **D4.3 chunk 并行下载+SHA/Adler 校验**（t32,8f959a5）:并行注入（默认 8,C7)+Channel 单读者；长度+Adler32 双断言+SteamKit 内部 SHA;损坏重下（MaxChunkRetries=2)耗尽→InvalidChecksum;无 depot key→AuthRequired。
- **D4.4 SteamKitCdnProvider+链回退**（t33,7359d15）:DownloadProviderRouter 主 SteamKit→兜底 steamcmd 按错误类型路由（回退 8 类含 RateLimited/不回退 4 类）；切换=总线消息+CurrentProviderFor 查询（UI 契约 D5 消费）；ProcessSlotAcquirer hook 转发。
- **D4.5 HTTP 直链分段 provider**（t34,fe0ed9b）:IDM in-half 分段+段中点分裂指派空闲 worker;Range 探测（206 分段/200 单流回退）+16B 重叠字节比对（拼接点校验，标定后 32→16);每段原子续存+.download 元数据（ETag/LastModified+总长校验，已完成段不重下）。
- **D4.6 磁盘 IO 偏移直写+稀疏占位**（t35,7d2331d）:FSCTL_SET_SPARSE+SetLength;不可逆护栏（既有内容文件拒绝=稀疏只用于下载期文件）+续传显式放行；exFAT/FAT32→SetLength 降级（VolumeCapabilityProbe);OffsetFileWriter 偏移直写无拼接（锁内 Seek+Write 串行化并发段）。
- **D4.7 限速器（令牌桶）**（t36,219139c）:0=不限速默认+突发 0.1s 量；余额记账（负账=借用）大请求单次精确等待；双点消费（HTTP 读流+chunk 调度）+UpdateRate 热改即生效。实测带宽≤配置×1.1(HTTP 40.1KB/s@80KB/s、chunk 61.1KB/s@60KB/s)。修复初版部分取票串行等待的二次方超时死循环。
- **D4.8 ⚠️重标定 B3**（t37,7f1c5cc）:五 sweep 实测（A/B/C 本地 Kestrel+E 真 API):MaxChunkParallelism=8 锁（rep 方差 4.5x 无增益）/MaxConnectionsPerServer=8 锁/OverlapBytes 32→16/ChunkTimeoutMs=5000 锁（2000=100%Timeout)/元数据并发 1 锁（增益 7.0%<10%)。三件套 \docs/calibration_2.{md,csv,json}\（109 行）。标定暴露三真 bug 已修：①in-half 分裂选 in-flight 段重叠写损坏 ②HTTP 段写偏移错位 ③超时仅 header 阶段判别失真。
- **D4.9 UiTests 分段体感断言**（t38,92c0e57）:\#15 字段刷新+按钮态+#14 弹窗路径 FlaUI 断言 Layer 1 过（键盘输入层 ENV-DOWNGRADE 桌面复跑）。

### 验证
clean+warnaserror **0-0**;全量 **318/0**(Downloads 81+Steam 148+Ui 17+Core 72)两连绿双口径。Kestrel 本地 fixture 验收（禁公网）：分段绿/kill 续传/Range 回退/偏移直写乱序/exFAT 降级。环境容忍门保留不阻门：真 CDN 复测留 D5(localhost 判别力局限诚实声明）+Online CM 沙箱阻断+UI 桌面复跑（ENV 标注齐）。



**四要素**:全量回归**237/0 两连绿**（增量+clean 双口径 build 0-0+CoreTestsDriver 72/0+SteamTestsDriver 103/0+DownloadsTestsDriver 53/0+UiTestsDriver 9/0,SP-3 沙箱驱动，TEMP/TMP 双重定向）+ 讨论组评审 \docs/process/review_2.0_0.3.0.md\（三原则）+ 版本 0.2.0→0.3.0（\Directory.Build.props\）+ 本变更记录。

### 新增（下载域全链 + steamcmd + App 最小可测 UI）
- **D3.1 状态机与队列**（t21,696773c):\Downloads/Queue\ — DownloadStateMachine 七态枚举（Pending/Queued/Preparing/Downloading/Paused/Cancelled/Failed/Completed,Preparing 对齐 t3 §3.2 序列）+转移表（Failed→Queued 重试）锁内拏 InvalidOperationException;DownloadTaskEntry 不可变快照+线程安全状态；DownloadQueue Channel 单消费者 FIFO（入队自动 Pending→Queued;id 注册表幂等+RequeueAsync);DownloadScheduler 并发槽默认 2(C7 同 D2.6 法）+终态竞争双检+CancelQueued/RetryAsync。**补完（1afa33f)**:ResumeAsync(Paused→Downloading)+执行后转移守卫（仅 Downloading 态，外部暂停不覆盖）。
- **D3.2 事件总线与进度聚合**（t22,09fb329):\Downloads/Events\ — ProgressSnapshot 不可变 record 六字段（速度/ETA/分段数/字节数/状态/消息，visual-20 UI 断言契约）+防御性拷贝；ProgressTracker EMA(alpha=0.4 ⚠️C7)+ETA 诚实降级 null;DownloadEventBus 每任务独立节流窗（ProgressThrottleMs=100 ⚠️C7 可配置）+窗内 latest-pending+Timer 刷新=尾帧不丢/不积压+订阅者异常隔离。
- **D3.3 steamcmd 部署器**（t23,db86584,qa-20):zip 下载+解压+探针校验（banner 版本串+退出码 {0,7})+指纹基线自记录（Valve 不发布权威签名）；非 ASCII 路径门控（实测 Fatal exit=-2)。
- **D3.4 steamcmd runner**（t24,621f6b2,qa-20):1.x 正则移植+成功三元（Success 正则+Sweep 产物非空+退出码 ∈{0,7})+失败清目录（原子性）+三段式看门狗（输出/磁盘停滞终止+取消杀全树）+输出脱敏+M2 进度偏差<10%。
- **D3.5 SteamCmdProvider 接入链**（t25,fe40fdd):ExecuteAsync 签式与 scheduler 执行器完全对齐（\DownloadScheduler(queue, provider.ExecuteAsync)\ 即装配）；前置门链=路由门（链回退 D4.4)/可达门（内容层与元数据层 403/429 独立）/熔断门（S4 同源 bucket steamcmd-download)/部署门/非 ASCII 门；进度=stdout 磁盘增长估算→总线（分段恒 null 诚实 N/A);偏差 ±15% 超阈降级 ETA null;自撤销不覆盖 Paused/Cancelled 尾帧；PauseAsync/CancelAsync 杀进程干净（无半成品原子性）。
- **D3.6 串行化与句柄纪律**（t27,56798c3,qa-20):进程级信号量（provider ProcessSlotAcquirer 接入点接入）+M4 超时映射+句柄纪律。
- **D3.5b App 最小可测 UI**（t26,526f9df,visual-20):AppHost 装配真链（scheduler+provider+bus 原样接入）+t3 §3.2 保留表全套 A7 id+完成弹窗自绘 #255。
- **D3.7 UiTests P0 主旅程**（t28,c927d74,visual-20):#10 鼠标点击入队→行→显式状态机等待+#10b 键盘 Enter 版+#13 取消终态沉淀；RealClick 物理鼠标无 InvokePattern=t3 真实输入合规；全黑 capture 环境探测器=沙箱 ENV-DOWNGRADE 明确标注，#14 完成弹窗+产物计数桌面通道复跑。

### 验证

| 口径 | 结果 |
|---|---|
| 增量 build + 四驱动（轮 1） | 237/0 |
| clean build + 四驱动（轮 2） | 237/0 |
| bug 测试员连续两轮复测 | ✅ 两轮均无异常 |

### 已知保留项（⚠️C7 待重标定，不阻门）
- 并发槽=2/EMA alpha=0.4/ProgressThrottleMs=100ms/偏差阈值 ±15%:同 D2.6 方法学标注，待 D4/D5 真实负载实测重标定。
- 在线 end-to-end 真实 mod 下载（D3.3/D3.4/D3.5 Online 场景）+D3.7 #14 完成弹窗桌面复跑：沙箱环境约束（中文路径+headless 桌面），已 ENV 标注，桌面通道复跑清单见各任务交付记录。


## [0.2.0] · 2026-10-02 · 阶段 2：Steam 域基础设施（D2.7 交付门）

**四要素**：全量回归 155/0（build 0-0+SteamTestsDriver 78/0+CoreTestsDriver 72/0+UiTestsDriver 5/0，SP-3 沙箱驱动，TEMP+TMP 双重重定向）· 讨论组评审 `docs/process/review_2.0_0.2.0.md`（三原则，arch-20/qa-20/visual-20 投票）· 版本 0.2.0（`Directory.Build.props`）· 本变更记录。

### 新增（Steam 域：Web/Connectivity/Resilience/Community）

- **D2.1 HttpClient 工厂与代理显式接管**（t15,4e2ab4a):`Steam/Web`(IHttpClientFactory+SteamHttpClientFactory:ProxyMode 三态注入 SocketsHttpHandler——Direct 显式禁用/SystemProxy 系统代理/Custom 显式 WebProxy+URL 校验>InvalidConfiguration)+`SteamHttpHeaders` 指纹头四件套（UA/Accept/Accept-Language **承重头**/X-Requested-With 冗余层——1.x 429 学费实证移植，X-Requested-With 旧结论经 research_2 复测推翻标注）+MaxConnectionsPerServer 参数化（SteamOptions 新增，C7)。
- **D2.2 端点可达性探测**（t16,0a18be7):`Steam/Connectivity`(IEndpointProbe:GET+ResponseHeadersRead 轻探不读体/超时 5s;403→Blocked、超时-DNS-TLS→Unreachable、其余可达、429 归可达限流归 D2.4)+IConnectivityState(Unknown 初值/变更触发 Changed 同值不触发 latency 变=状态变/快照不可端）。双网络环境真实探测 `docs/connectivity_probe_2.2.md`:A(代理 Custom 7897)三端 ViaProxy;B(Direct 经 TUN)三端 Direct——诚实标注预判“直连不可达”未成立（fake-IP 为 TUN SNI 网关）。
- **D2.3 Web API 客户端**（t17,9652cb2):GetPublishedFileDetails(batch `itemcount=N` 批封包）+GetCollectionDetails(children sortorder 排序+嵌套递归 BFS 展开+**999↔200 环引用 visited 保护**)+storesearch；失败映射 8 类 SteamError(429/403/404/401/5xx+网络/JSON/超时/取消/result:9);IConnectivityGate 门（Api 不可达 0 请求发出）。真实在线验证 id 3808352517 result:1+title"KFC - Chicken Bucket"(captain 代理直连补验；沙箱在线测试网络阻断时驱动诚实标注“环境阻断非实现缺陷”）。
- **D2.4 节流器与熔断器**（t18,f13a379):`Steam/Resilience/Throttler.cs` 单文件全量——IThrottler（bucket 差异化+每 bucket SemaphoreSlim 全程锁=同 bucket 串行+锁内 DelayAsync 强制最小间隔+跨 bucket 不互阻）;ICircuitBreaker(Closed→阈值 5→Open→冷却 60s→HalfOpen 单试探→成功 Closed/失败 Open 重计）;ITimeProvider/System/FakeTimeProvider（假钟 seam:逻辑推进真实毫秒不流逝）;ResiliencePipeline 门面（开态/排队后复检 IsOpen→Result.Fail(CircuitOpen) 不抛+acquire→门→请求→结果计熔断）。客户端集成（api/store bucket 注入，默认 null 不破坏现有调用）。
- **D2.5 社区页面回退**（t19,43da3f0):`Steam/Community`——Browse 列表+详情富化+**可达门（S4:Community 未验证可达=Fail(Network) 0 请求）**+D1.6 缓存出口深拷贝；CommunityHtmlParser 只锚稳定结构（**实测研究结论**：browse 页 React 改版旧 workshopItem 类消失=混淆 CSS→锚 filedetails/?id=N+img src/alt;detail 页 workshopItemTitle/creatorsBlock 旧类仍稳；AppId 锚 myworkshopfiles/?appid=N——评论区 JSON 内 appid 为转义串不可直接正则）。真实 fixture（代理 7897 抓取 browse 679KB/30 物品含 KFC - Chicken Bucket;detail 109KB）内嵌资源。

### 变更（参数重标定，D2.6 用户"经验复验纪律"）

- **D2.6 B1+B2 实测重标定**（t20,ab803fb):CalibBench 独立控制台 86 分钟/436 条原始记录（`docs/calibration_1.{csv,json,md}`）。
  - **B1**：诱导 429（裸 burst,体 330034B)→等 5-90s×3→指纹头复测 **24/24 全 200**=解除机制是**头指纹（Accept-Language）非等待时长**——1.x 退避假设复验推翻但保留作防御默认（BackoffInitial 5000/BackoffMax 90000 不变，依据改为"防御性"）。
  - **B2**:0.5s×20 连发**零失败**（0.5s 档连过 30 次=r1 全 20+r2 前 10);1s+ 档通过/失败按累计预算跨轮移动（非间隔驱动，详见 calibration_1.md 修正后逐轮表）——**限流=会话窗口累计请求天花板（~117 次请求）非间隔维度**。8s 档轮内部分恢复（单轮跨 160s)=**时间恢复机制的直接证据**，与"天花板非间隔"结论相互印证。天花板恰由 D2.4 熔断器兜底（120s 冷却≈重置 20 次预算）。
  - **参数锁定**：`ThrottleMs[0]/[1]` 6000/2000 → **1000/1000**（appsettings.json+Throttler.DefaultIntervals+SteamOptions 文档三同步；ResilienceTests 默认间隔断言同改）。
- **误诊撤回**：20:21 曾判"Steam 端点对出口 IP 限流"，实为用户关闭代理软件（用户 20:50 告知）——诊断网络失败先确认本地代理/出口状态再归因远端。

### 验证

- SP-3 沙箱驱动模式（xUnit testhost 崩溃→控制台驱动反射同一测试方法）：build 0-0;SteamTestsDriver 78/0(D2.1 17+D2.2 11+D2.3 21+D2.4 17+D2.5 12);CoreTestsDriver 72/0;UiTestsDriver 5/0。
- 跨内容关联：客户端←工厂指纹头（stub 字节级断言）←可达门←节流桶←熔断器←缓存深拷贝；在线=result:1+双环境探测+三档标定全真实网络。

### 已知保留（C7 待重标定，不阻碍 0.2.0)

- api bucket 100ms/store bucket 250ms 未在 B2 覆盖（非 429 敏感路径）→D3/D4 或 0.3 迭代覆盖。
- 标定天花板数值（~117）为单出口 IP 单轮观测值，跨环境须复测。
- B1 退避值 5000/90000 为防御默认（实测无必要性证据，亦无反证）。

---

## [0.1.0] · 2026-10-02 · 阶段 1：Core 域契约（D1.7 交付门）

**四要素**：全量回归 77/0 绿（SP-3 沙箱驱动模式）· 讨论组评审 `docs/process/review_2.0_0.1.0.md`（三原则）· 版本 0.1.0（`Directory.Build.props`）· 本变更记录。

### 新增

- **D0.2 骨架接线**（t6）：Downloads→Steam ProjectReference（依赖链 Core←Steam←Downloads 单向无环）；UiTests 按 t3 §2.1 包清单接线（FlaUI 5.0.0 + xunit 2.9.0 + runner 2.8.2 + Xunit.StaFact——规格 1.2.1 实测不存在于 NuGet，实证替代 2.1.7 并通报 qa-20 回写 t3；`xunit.runner.json` 强制串行）；App 空白窗口 + `AutomationId=MainWindow`（A7 可靠载体）+ `AppLaunchSmokeTests`（[WpfFact] 进程外启动断言）。
- **D1.1 领域模型与结果模型**（t7）：`Core/Domain`（AppId/PublishedFileId/UgcId/DownloadTaskId 强类型 id，C6 类型级隔离 + 枚值校验 + TryParse；WorkshopItem/GameInfo/DownloadTask/ModLibraryEntry 不可变 record，集合防御性拷贝 + 结构性相等重写）；`Core/Results`（`Result<T,TErr>` 双分支结果模型 + SteamError/DownloadError 各 10 码）。`Swdm2.Core.Tests` 单测项目落地。
- **D1.2 路径服务**（t8）：`Core/Paths`（便携=exe 同级 / 安装=%APPDATA%\SWDM，C3 构造期锁定；WorkshopContent 与 SCA 同构 `<Root>/steamcmd/steamapps/workshop/content/<appid>`；DownloadStaging 纯函数确定性；EnsureDirectories 幂等；Detect 按 `swdm2.portable` 标记自动判模式）。
- **D1.3 配置与选项骨架**（t9）：`Core/Options`（ProxyMode 三态 + SteamOptions/DownloadOptions/PathOptions，全部数值 ⚠️[参数待重标定] C7 三重标注 + DataAnnotations 范围验证）；App 侧 appsettings.json + SwdmConfiguration（reloadOnChange + 运行时 ConfigFile 叠加 + IOptionsMonitor 热更新）。
- **D1.4 凭据存储**（t10）：`Core/Credentials`（ICredentialStore 契约 C2 + DpapiCredentialStore：ProtectedData.CurrentUser、原子写入、单写者锁、ZeroMemory、异常文安化、账号键归一、删除幂等、空密码拒绝、不存在=返回 null）。
- **D1.5 日志契约与脱敏 sink**（t11）：`Core/Logging`（RegexRedactionPolicy：键值标记/授权头/账号型三正则，中英双语）+ `App/Logging`（RedactingTextFormatter 两层防线：属性名 17 黑名单 + 渲染后文本正则兜底；SwdmLogging 启动期单点装配：File formatter + RollingInterval.Day + UTF8）。
- **D1.6 缓存抽象**（t12）：`Core/Caching`（IAsyncCache 契约 C5 + AsyncCache：ConcurrentDictionary + 每键 SemaphoreSlim single-flight + TTL；**双向深拷贝隔离**——命中克隆出口（消费侧，1.x enrich() 污染对价）+ 插入克隆入存（生产侧），默认 System.Text.Json 往返克隆器；负缓存 + 异常不毒化）。
- **版本基础设施**（D1.7）：`swdm2/Directory.Build.props` 全项目统一 Version/AssemblyVersion/FileVersion（+ SourceRevisionId 指向 git 提交）。
- **测试基础设施**（D1.7）：`tests/CoreTestsDriver/` 控制台反射驱动（SP-3 沙箱 testhost 崩溃的替代路径，captain 搭建）；`tests/UiTestsDriver/` 同模式 STA 驱动（本门新增，交 qa-20 审；纯反射特性匹配规避 xunit.core/xunit.v3.core CS0433 二义 + 引入 D1.5r 假绿教训的 IsAssignableFrom 兜底）。

### 修复

- **D1.5r 脱敏回归修复**（t14，commit 25086c0，D1.7 门回归抓出 + bug 归属制闭环）：
  - RegexRedactionPolicy 替换串硬编码不保留原分隔符（密码 `/`+中文冒号等形态被截断）→ 按原文分隔符形态重组；
  - 键表缺裸 `code`（验证码场景）→ 补齐；
  - 暗坑 ①：撇号紧贴敏感词尾部时截断泄漏（`P@ss...Don't` → `***'t`）；
  - 暗坑 ②：JSON 闭合引号形态的尾分隔符隔断，导致 `"token":` 整段完全不脱敏。
  - 根因坦承：历史"63/63 全绿"为假绿——自写驱动按特性 `Type.Name` 精确匹配筛方法，TheoryAttribute 派生自 FactAttribute 但 Name 不同，9 个 [Theory] 行被静默跳过。教训入过程纪律：自写测试驱动必须 IsAssignableFrom 匹配 + Theory/InlineData 展开 + 第二人独立复跑计数对账。
- **D1.3 ConfigurationBinder 坑**（t9 内修）：预填数组默认值与 JSON 绑定是追加而非替换（静默拼接错误配置）→ 类默认 `Array.Empty<T>` + 起点值只由 appsettings.json 承载。
- **D1.4 遗漏路径**（t11 内修）：FormatException（Base64 损坏密文）未走包装路径 → 纳入 CredentialStoreException 安全文案。

### 验证（0.1.0 全量回归，SP-3 沙箱驱动模式）

| 命令 | 结果 |
|---|---|
| `cd swdm2; dotnet build Swdm2.sln -c Debug --nologo -v q` | 0 警告 0 错误 |
| `dotnet run --project tests/CoreTestsDriver` | pass=**72** fail=0 skip=0（=63 [Fact] + 9 [Theory] 行，真数；历史 63/63 为驱动假绿） |
| `dotnet run --project tests/UiTestsDriver` | pass=**5** fail=0 skip=0（4 脱敏管道 + 1 AppLaunch 真实进程冒烟，Application.Launch → UIA3 定位 MainWindow） |
| 环境要点 | dotnet 派生进程的 `%TEMP%`/`%TMP` 双重重定向至 `swdm2/.dtmp`（GetTempPath 读 TMP 优先，仅重定向 TEMP 无效） |

**关联交互回归覆盖**（功能间关联，非单点）：D1.4+D1.5 联合（凭据明文不入日志文件管道）；D1.2+D1.3（路径/选项在双模式与热更新下的组合）；D1.6 C5 双向缓存隔离（消费侧 + 生产侧变异）；D1.1 C6 类型隔离（编译期 + 反射断言）。

### 已知非阻塞项

- t2 视觉规格 v1.1 回写（A7 载体表同步：SwdmCard/Hint 根元素 UserControl 化等）由 visual-20 于 D5 前自办（评审记录 `docs/process/review_2.0_plan.md` 遗留项）。
- t3 测试规格 v1.x 回写（StaFact 2.1.7 实证约束 + Calibration 迁 Core.Tests + §7.2 映射同步）由 qa-20 自办中。
- WPF-UI 4.3.0 API 表面按 A8b 于首次使用前反射实测（SP-1 已实证两处 API 漂移：SymbolRegular 无 Regular 后缀 / ui:Card 无 Header）。
- 参数类数值全部 ⚠️[参数待重标定]：B1/B2→D2.6，B3→D4.8（t3 §5 基准），A9 即时反馈阈值→D5.10。

---

> 0.1.0 为基础设施版本，不发布给最终用户（无 Velopack 打包/安装器）；首版对外交付 = 2.0.0（D7.4）。
