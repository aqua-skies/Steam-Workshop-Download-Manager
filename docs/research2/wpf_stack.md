# SWDM 2.0 · WPF 技术栈选型报告

> **代号**：SWDM 2.0（Steam Workshop mod 下载管理器，C# WPF 重写）
> **日期**：2026-10-02
> **对标产品**：PCL2（Plain Craft Launcher 2，扁平卡片 + 蓝色明度阶梯风格）+ Steam 社区 + IDM 下载体感
> **目标运行时**：.NET 8（已与 swdm2 解决方案骨架一致）

## 调研方法与数据可靠性声明

本报告所有定量数据（star 数、最近推送时间、NuGet 最新稳定版）均于 **2026-10-02** 通过 GitHub REST API 与 NuGet Registration API 直连核验（本机经代理 `127.0.0.1:7897`），并用 ddg / bing / exa 三引擎交叉检索社区真实反馈。

**已知检索限制（诚实声明）**：

1. 本机 fake-IP 网络环境下 `web_fetch` 对 github.com / learn.microsoft.com / docs.velopack.io 等域名 DNS 解析失败，正文细节取自搜索引擎返回的原文片段与 GitHub/NuGet API 的结构化字段，未逐页通读官方文档全文。
2. `CommunityToolkit/Mvvm` 的 GitHub API 查询从本机持续返回 404（其他 9 个仓库同一通道均正常），**该库的 star 数未能直接核验**；其活跃度以 NuGet 发版记录（8.4.2 / 2026-03-25）与微软官方文档所有权佐证。报告中凡未核验的数据点均显式标注。

---

## 1. MVVM 库对比：CommunityToolkit.Mvvm vs Prism vs ReactiveUI

### 1.1 数据表（GitHub API + NuGet API，2026-10-02 查询）

| 库 | GitHub Stars | 仓库最后推送 | NuGet 最新稳定版 | NuGet 发布时间 | 维护状态判定 |
|---|---|---|---|---|---|
| **CommunityToolkit.Mvvm** | 未能直连核验（API 404） | — | **8.4.2** | **2026-03-25** | 🟢 活跃，微软/.NET Foundation 维护 |
| **Prism** | 6,854 | 2026-10-01 | 9.0.537 | **2024-08-20** | 🟡 仓库有提交但**稳定版已近 2 年未更新** |
| **ReactiveUI** | 8,539 | 2026-10-01 | 25.1.1 | 2026-09-28 | 🟢 活跃 |

> 数据来源：[PrismLibrary/Prism](https://github.com/PrismLibrary/Prism)、[reactiveui/ReactiveUI](https://github.com/reactiveui/ReactiveUI)、[CommunityToolkit.Mvvm 官方文档](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/mvvm/)（[迁移自 MvvmLight 指南](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/mvvm/migratingfrommvvmlight)佐证其为 MvvmLight 官方继任者）

### 1.2 三者现状与社区定位

- **CommunityToolkit.Mvvm**：微软发布的轻量级 MVVM 库，前身为 Microsoft.Toolkit.Mvvm，是 MvvmLight 的官方继任者，"是许多 .NET 应用模板的默认轻量 MVVM 选择，也是多数团队与 ReactiveUI 对比时的基准"（[ReactiveUI 官方对比页](https://www.reactiveui.net/vs/community-toolkit-mvvm/)原文）。核心理念是 Roslyn 源代码生成器 + 零分配模式 + 平台无关（.NET Standard 2.0/2.1，[官方文档](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/mvvm/)）。
- **Prism**：成熟框架，聚焦导航、模块化、区域管理（region），自带容器抽象（默认 DryIoc，有 MSDI 适配器）（[ReactiveUI 官方对比](https://www.reactiveui.net/vs/prism/)）。功能最全但概念最重。NuGet 稳定版停在 2024-08 的 9.0.537，对一个快速迭代的项目是明确黄灯。
- **ReactiveUI**：Rx 响应式全家族（System.Reactive + DynamicData），自带路由。学习曲线最陡——需要完整掌握 Observable 调度器管线。

### 1.3 学习曲线与 AI 代码生成友好度（关键判据）

SWDM 2.0 在 AI 辅助编码（含 AI 研发团队）背景下，"LLM 能否可靠生成该库的代码"是和"人类学习曲线"同等重要的判据：

| 维度 | CommunityToolkit.Mvvm | Prism | ReactiveUI |
|---|---|---|---|
| 人类学习曲线 | 低：属性通知/命令/消息三件套，纯特性（attribute）标注 | 高：模块/区域/容器/EventAggregator 体系 | 最高：需先掌握 Rx（Observable、Scheduler、ObserveOn） |
| AI 生成可靠度 | 🟢 **最高**：`[ObservableProperty]`、`[RelayCommand]` 是"声明式 + 编译期生成"模式，生成结果可读、可静态验证；生成的就是普通 partial 类，AI 校对自己产物无障碍 | 🟡 中：样板代码多但结构固定（Prism 的 ViewModel 风格在网上训练语料极多） | 🔴 **低**：Rx 管线一处调度器错误（如忘了 `ObserveOnDispatcher`）即上线后偶发崩溃，且这类 bug 静态不可见；响应式链路的调试/审阅成本高 |
| 与 AI 结对开发体感 | 生成代码即最终代码，diff 可读 | 可接受 | 需要大量人工 review Rx 链 |

### 1.4 推荐：**CommunityToolkit.Mvvm 8.x**

**理由**：

1. **微软官方维护、发版稳定**（8.4.2 / 2026-03-25），无项目级人身风险。
2. **AI 友好度最高**（见 1.3），与 SWDM 2.0 的 AI 团队开发模式（域 owner + 多 agent 协作）天然契合。
3. **轻量**：不绑定容器、不绑架导航体系——DI 继续用 MSDI（见第 3 节），不会被框架锁死。
4. 缺省的导航/模块化能力，对单窗口 + 多页面的下载管理器**不是刚需**（PCL2 本身也是自绘页面切换而非框架级导航）。
5. 社区基准地位：众多新模板默认它（ReactiveUI 官方对比页原文佐证）。

**避坑提醒**：MVVM Toolkit 不提供模块化/导航——SWDM 2.0 需自行设计页面切换（ContentControl + DataTemplate 或自研导航器），这恰好也是 PCL2 的做法。

---

## 2. 控件库对比（对标 PCL2 扁平卡片 + 蓝色明度阶梯）

### 2.1 先看 PCL2 自己怎么做的（重要事实）

PCL2（[Meloong-Git/PCL](https://github.com/Meloong-Git/PCL)，7,359 stars，2026-09-28 仍在推送，**VB.NET + WPF**）的漂亮**不是任何第三方控件库的功劳**：源码里 `Controls/MyCard.vb`、`MyHint.vb` 等全部是**自绘用户控件**，社区版 [PCL-Community/PCL2-CE](https://github.com/PCL-Community/PCL2-CE) 还重构出了"基于 HSL 颜色转换的船新主题系统"（commit 9569965）与 MyHint 深色主题（commit 982e7b0）。

**结论先行**：PCL2 的外观 = 100% 自绘卡片控件 + HSL 主题系统。任何控件库都给不了你一模一样的 PCL2 脸。选型应选"**最省定制成本的基底**"，而不是"最像 PCL2 的库"。

### 2.2 数据表（GitHub API + NuGet API，2026-10-02 查询）

| 控件库 | Stars | 最后推送 | 开放 Issue | NuGet 最新稳定版 | .NET 8 兼容 | 维护判定 |
|---|---|---|---|---|---|---|
| WPF-UI (lepoco) | 9,677 | 2026-06-27 | **456** ⚠️ | 4.3.0 (2026-05-04) | 🟢 一等公民（net8.0 目标） | 🟡 活跃但 issue 积压严重 |
| HandyControl | 7,202 | 2026-08-11 | 329 | 3.5.1 (**2024-03-05**) ⚠️ | 🟡 主包近 2.5 年未发稳定版；有 .NET 8 交流案例（AFei19911012/HandyControlDemo 2024-09 提交 ".Net8 的测试案例"） | 🟡 主包停更，社区 fork（HandyControls 3.6.0）续命 |
| MaterialDesignInXaml | **16,270** | 2026-10-02 | 143 | 5.3.2 (2026-05-01) | 🟢 | 🟢 最活跃 |
| MahApps.Metro | 9,830 | 2026-10-01 | 19 | 2.4.11 (2025-09-13) | 🟢 | 🟢 稳定活跃 |

### 2.3 逐项评价（对标 PCL2 风格）

- **WPF-UI**（[lepoco/wpfui](https://github.com/lepoco/wpfui)，[官网](https://wpfui.lepo.co/)）：Fluent（Win11）路线——Mica/Acrylic 背景、圆角、暗色模式、导航框架、Snackbar/NumberBox 等新控件。**现代化扁平质感最接近 PCL2 的"干净"观感**，且对 .NET 8 是一等支持。⚠️ **456 个开放 issue** 是明确风险信号（是本批四个库里最高的，star/issue 比最差），采用前必须接受"遇到坑可能要自己提 PR"的现实。
- **HandyControl**：中文社区文档最好，控件种类多（含 Card 类组件）。但**主 NuGet 包 3.5.1 停在 2024-03**，GitHub 上 ".NET 8 是否支持" 的issue 与民间测试案例并存，属"能用但要赌"的状态；fork 包 HandyControls 3.6.0 目标 net5.0。性价比已经被 WPF-UI 反超。
- **MaterialDesignInXaml**：最活跃（star 最多、唯一 2026-10-02 当天仍有推送），控件齐全。**但 Material Design 的语言核心是 z 轴高程阴影与浮动按钮**，与 PCL2 的"扁平 + 明度阶梯"是**两个设计语言**，改皮成本反而高于 WPF-UI。
- **MahApps.Metro**：专注于窗口 chrome（Metro 风格标题栏）+ 主题，质量稳定（19 个开放 issue，star/issue 比全场最优）。但它**不是全控件库**，适合作为"窗口边框方案"与其他库组合，而非 PCL2 风格的主体。

### 2.4 推荐：**WPF-UI 作基底 + 自绘 Card 控件（PCL2 路线）**

**推荐方案与理由**：

1. **WPF-UI 4.3.x 作基底**：窗口/导航/基础控件的现代化底座（Fluent 扁平、暗色模式免费送），.NET 8 一等支持，活跃维护。
2. **PCL2 风格的核心元素自绘**：卡片（Card）、提示条（Hint）、下载进度条等，按 PCL2-CE 的 HSL 主题系统思路自建 `SwdmCard : ContentControl` + ControlTemplate——这是 PCL2 本身的做法，也是"看起来像 PCL2"的唯一正确路径。蓝色明度阶梯用一个主题资源键（如 `SwdmBlue.L1~L7`）在 HSL 空间生成。
3. **风险对冲**：456 个开放 issue 要求我们锁定具体版本（4.3.0）+ 在 CI 中加 UI 冒烟测试（FlaUI 方案见 `docs/research2/wpf_ui_testing.md`），升级版本必须过全量回归（符合用户规定的迭代交付流程）。
4. **备选**：若 WPF-UI 在实际集成中坑实在太深， fallback 到 MahApps.Metro（窗口 chrome）+ 纯自绘控件——MahApps 的 star/issue 比（9,830/19）是全场最健康的。

**定制成本量级（预估）**：WPF-UI 基底集成 1-2 人日；PCL2 风格自绘卡片套件 3-5 人日（含主题键体系）；后期持续打磨按视觉验收迭代。

---

## 3. DI / 日志 / 配置：MSDI + Serilog + Options 模式在 WPF 的落地

### 3.1 选型

| 组件 | 选择 | 版本（NuGet API 核验 2026-10-02） | 说明 |
|---|---|---|---|
| DI 容器 | **Microsoft.Extensions.DependencyInjection** | 随 .NET 8 运行时（Microsoft.Extensions.Hosting 10.0.12 为最新） | 官方容器，与 Generic Host 天然一体；Prism 的 DryIoc / ReactiveUI 的内置容器都不必引入 |
| 日志 | **Serilog** | 4.4.0 (2026-07-10) | 8,047 stars，结构化日志事实标准；活跃维护；`Serilog.Sinks.File` + `Serilog.Sinks.Console` + `Serilog.Sinks.Debug` 起步 |
| 配置 | **Microsoft.Extensions.Configuration + Options 模式** | 随框架 | appsettings.json + 强类型 `IOptions<T>` |

### 3.2 WPF 落地方式（骨架代码）

```csharp
// App.xaml.cs
public partial class App : Application
{
    private readonly IHost _host;

    public App()
    {
        _host = Host.CreateDefaultBuilder()
            .ConfigureAppConfiguration((ctx, cfg) =>
            {
                cfg.SetBasePath(AppContext.BaseDirectory);
                cfg.AddJsonFile("appsettings.json", optional: false, reloadOnChange: true);
            })
            .ConfigureServices((ctx, services) =>
            {
                // Options 模式：强类型配置
                services.Configure<SteamOptions>(ctx.Configuration.GetSection("Steam"));
                services.Configure<DownloadOptions>(ctx.Configuration.GetSection("Downloads"));

                // 日志：Serilog 接管 Microsoft.Extensions.Logging
                services.AddLogging(b => b.AddSerilog());

                // 视图与服务注册
                services.AddSingleton<MainWindow>();
                services.AddSingleton<IDownloadService, DownloadService>();     // 下载内核（SteamKit + steamcmd 兜底）
                services.AddHostedService<DownloadQueueWorker>();                // 后台队列服务（第 4 节）
            })
            .UseSerilog((ctx, cfg) => cfg
                .MinimumLevel.Information()
                .WriteTo.File(Path.Combine(AppContext.BaseDirectory, "logs", "swdm-.log"),
                              rollingInterval: RollingInterval.Day, retainedFileCountLimit: 14))
            .Build();
    }

    protected override async void OnStartup(StartupEventArgs e)
    {
        await _host.StartAsync();                          // 启动 HostedService
        _host.Services.GetRequiredService<MainWindow>().Show();
        base.OnStartup(e);
    }

    protected override async void OnExit(ExitEventArgs e)
    {
        await _host.StopAsync();                           // 优雅停止后台服务
        _host.Dispose();
        base.OnExit(e);
    }
}
```

要点：

- `Microsoft.Extensions.Hosting` 在 WPF 中**开箱不支持**，需如上手动接入（微软官方教程：[Use the .NET Generic Host in a WPF app](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/app-development/how-to-use-host-builder)——"WPF applications don't include Host Builder integration by default, but you can add it"）。
- 配置变更通知：对于"下载并发数变更即时生效"这类需求，用 `IOptionsMonitor<T>` 而非 `IOptions<T>`。
- Serilog 的 rolling 文件日志对 SWDM 尤为重要——下载失败排障依赖带时间戳的完整历史（1.x 经验：429/403 排查全靠日志）。

---

## 4. 线程模型：Dispatcher、async/await 坑、IHost + HostedService

### 4.1 Dispatcher 用法

- WPF **UI 线程独占 UI 对象**：任何后台线程要读写 UI 元素（包括 ObservableCollection 的绑定源）必须 marshal 回 UI 线程（[微软 Threading Model 文档](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/advanced/threading-model)）。
- 推荐做法：**后台线程只碰线程安全的服务/数据**，UI 更新通过 `ObservableCollection` + `CollectionChanged` 由绑定引擎自动 marshal（前提是集合在 UI 线程创建且仅 UI 线程改它）。需要直接操作控件时用 `Dispatcher.Invoke`（同步）或 `Dispatcher.InvokeAsync`（异步，推荐）；`BeginInvoke` 是老 API。
- **下载场景映射**：下载进度（后台 IO 线程）→ 进度聚合器（线程安全）→ UI 线程定时（~200ms）批量刷新，避免每秒数百次 Dispatcher 调用造成 UI 线程饥饿。

### 4.2 async/await 三个高频致命坑（社区实证见第 6 节 P1/P2）

1. **UI 线程上 `.Result` / `.Wait()` → 死锁**：SynchronizationContext 存在时，await 的续体要回 UI 线程，而 UI 线程正被 `.Result` 阻塞。解药：**全链路 async**，或必须同步阻塞时用 `Task.Run(...).Result` 把工作扔到线程池。
2. **`async void` 事件处理器抛异常无人接** → 变成未处理异常闪退。解药：事件处理器内 `try/catch` 包裹 + 统一日志上报告警。
3. **`async void` 生命周期失控**：await 期间窗口已关闭 → 操作已取消/对象已释放。解药：窗口级 `CancellationTokenSource`，OnClosing 时 Cancel。

### 4.3 后台服务：IHost + HostedService 在桌面应用

- [.NET Generic Host](https://learn.microsoft.com/en-us/dotnet/core/extensions/generic-host) 提供 DI + 配置 + 日志 + 生命周期管理的一体化底座；WPF 手动接入方式见 3.2。
- **SWDM 落地**：`DownloadQueueWorker : BackgroundService`（AddHostedService）在主机启动时常驻，内部用 `Channel<T>` 或 `BlockingCollection` 接下载任务，串行化 steamcmd 进程（1.x system_contracts 教训：steamcmd 必须串行化 + 多 provider 链式回退）。
- **注意**：HostedService 与 UI 生命周期解耦——`OnStartup` 里 `StartAsync`，`OnExit` 里 `StopAsync`（见 3.2）。`IHostApplicationLifetime` 可用于自定义启动/停止钩子（StackOverflow 有 .NET 8 WPF 下正确用法的[完整讨论](https://stackoverflow.com/questions/79219594/)）。
- 后台线程异常务必 `catch` 后记日志 + 转发到 UI 的错误横幅（Snackbar），**不要让异常冒到 Host 导致整个主机崩溃**（默认 Host 会在 BackgroundService 抛异常时停止整个应用——对桌面应用是毁灭性行为，需显式抑制：worker 内 try/catch 全包）。

---

## 5. 打包与自动更新：MSIX vs Inno Setup vs Squirrel.Windows vs Velopack

### 5.1 数据表（2026-10-02 核验）

| 方案 | 状态 | 自动更新 | 个人 GitHub 分发友好度 |
|---|---|---|---|
| **Velopack** | 🟢 **2,358 stars，2026-10-02 当天推送，1.2.161 (2026-09-29)** | ✅ 内置（增量 + 全量 + 迁移） | 🟢 **最佳**：GitHub Releases 免费托管 |
| Squirrel.Windows | 🔴 **7,982 stars 但"Contributors Needed"维护停摆**（README 明确写 "We are looking for help with maintaining this important project"，issue #1470）；最后推送 2024-07-24，423 个开放 issue，NuGet 2.0.1 停在 **2020-09-27** | ✅ 但年久失修 | 🟡 能用但社区已跑路 |
| MSIX | 🟢 微软在推 | ✅（应用商店） | 🔴 个人开发者痛点：签名证书（自签名不被信任）、沙箱权限限制、未签名时用户需手动开启旁加载 |
| Inno Setup | 🟢 稳定 | **❌ 无内置**（Reddit 社区原话：灵活易集成 CI/CD，"but unfortunately, it does not have any auto update mechanism"） | 🟡 安装包好做，更新全靠自研 |

### 5.2 Velopack 核心事实（GitHub README + 官方文档）

- **Rust 编写**的原生性能安装 + 自动更新框架，一条命令从编译产物生成**安装包 + 更新包 + 增量包 + 自更新便携包**（README 原文："Velopack takes your compiler output and generates an installer, updates, delta packages, and self-updating portable package in just one command"）。
- **分发零成本**：支持 "for free on GitHub/GitLab releases"（[官方分发文档](https://docs.velopack.io/distributing/overview)）——更新源就是一个 HTTP URL，GitHub Releases 直挂。
- **Squirrel 自动迁移**：README 明确支持从 Squirrel 无缝迁移（[迁移文档](https://docs.velopack.io/migrating/squirrel)）；且修复了 Squirrel 的目录切换缺陷（"Changing the path of the application like Squirrel does is very bad, it breaks a lot of things in Windows"）。
- **更新体验**：社区用户证言——"Updates apply and relaunch in ~2 seconds with no UAC prompts"（Velopack README testimonial）。
- **官方 WPF 样例**：[velopack/samples/CSharpWpf](https://github.com/velopack/velopack/tree/develop/samples/CSharpWpf)——正是本场景。

### 5.3 集成方式（官方文档要点）

```csharp
// Program.cs（WPF 需用自定义 Main 而非 App 自动启动）
VelopackApp.Build().Run();   // 必须在 Main 最开头，处理安装/更新钩子
var app = new App();         // 之后才进入 WPF App
app.Run();
```
更新检查：`UpdateManager` 的 `CheckForUpdatesAsync` / `DownloadUpdatesAsync` / `ApplyUpdatesAndRestart`（[官方 C# 指南](https://docs.velopack.io/getting-started/csharp)、[UpdateManager 参考](https://docs.velopack.io/reference/cs/Velopack/VelopackApp)）；打包用 `vpk` 命令行工具（`dotnet tool update -g vpk`，需要 dotnet 8+，[文档原文](https://github.com/velopack/velopack.docs/discussions/16)）。
CI：`dotnet publish` → `vpk pack`（指定版本号与发布目录）→ 上传 `.vpk` 产物到 GitHub Release。SWDM 已有 Inno Setup 经验，但 Velopack 的"一条龙"更省心。

### 5.4 推荐：**Velopack + GitHub Releases**

对 SWDM（个人开源、GitHub 分发）这是明显最优解：安装、增量更新、便携包、自动迁移全覆盖，更新服务器零成本。1.x 的 Inno Setup 安装器路线不在 2.0 推荐之列（除非 Velopack 集成出现不可逾越的具体障碍）。

**两根软钉子（诚实提示）**：
1. **代码签名**：未签名 exe 会触发 SmartScreen 警告。个人开发者无 EV 证书时，Velopack 文档建议的体验仍显著优于裸 Inno Setup（无 UAC 更新提示），但首次安装警告需在 README/手册中告知用户。证书预算：OV 证书约数百元/年（EV 更贵）。
2. Velopack 2,358 stars 属较新生态，中文社区资料少——遇坑需读英文官方文档（质量较高）或社区 Discord。

---

## 6. WPF 常见致命坑清单（社区真实案例 + 解药）

每条均附人类社区报告过的真实出处。

### P1. Dispatcher 死锁：UI 线程上 `.Result` / `.Wait()`

- **真实案例**：[StackOverflow 65603800](https://stackoverflow.com/questions/65603800/) —— "The deadlock occurs because the await is waiting for the UI thread to be free and the UI thread is blocked on the async method to complete"；微软代码分析规则 [CA2007](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2007) 明确 "result in a deadlock on the UI thread"。
- **业务场景**：下载管理器里"启动时同步等待配置加载完成"这类代码最容易踩。
- **解药**：全链路 async；库方法内部一律 `ConfigureAwait(false)`；万不得已要同步等待，用 `Task.Run(() => MethodAsync()).Result`（把续体留在线程池）。

### P2. 跨线程互等死锁：工作线程 Dispatcher.Invoke ↔ 主线程等结果

- **真实案例**：[StackOverflow 24211934](https://stackoverflow.com/questions/24211934/) —— 工作线程需要写日志到 UI 窗口而调 `Dispatcher.Invoke`，恰逢主线程在等该工作线程返回 → 互相 deadlock。
- **解药**：工作线程**永远不直接调 UI**——走日志服务（Serilog 直接写文件）或 `InvokeAsync`（非阻塞）；主线程绝不同步等待工作线程结果。

### P3. 绑定内存泄漏：绑定到非 INPC / 非 DependencyProperty 的对象

- **真实案例**：[StackOverflow 18542940](https://stackoverflow.com/questions/18542940/) "If you are not binding to a DependencyProperty or an object that implements INotifyPropertyChanged then the binding can leak memory"；[JetBrains dotMemory 官方博客](https://blog.jetbrains.com/dotnet/2014/09/04/fighting-common-wpf-memory-leaks-with-dotmemory/) 系统拆解了该模式；[微软弱事件文档](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/events/weak-event-patterns) 承认 "handlers attached to event sources won't be destroyed... lead to memory leaks"。
- **解药**：所有绑定数据源实现 `INotifyPropertyChanged`（MVVM Toolkit 的 `[ObservableProperty]` 自动满足）；事件订阅长生命源（如静态/单例下载事件）用 `WeakEventManager<TSource,TArgs>`（[Pete Brown 实战帖](http://10rem.net/blog/2012/02/01/event-handler-memory-leaks-unwiring-events-and-the-weakeventmanager-in-wpf-45)）或在关闭时显式退订。

### P4. 虚拟化失控：DataGrid/ListBox 海量数据卡死

- **真实案例**：
  - DataGrid 放进 ScrollViewer → 虚拟化被破坏（[SO 52221666](https://stackoverflow.com/questions/52221666/)："Using scroll viewer is disabling the virtualization"）。
  - 分组（Grouping）默认杀死虚拟化（[SO 4155424](https://stackoverflow.com/questions/4155424/)；[MahApps issue #3040](https://github.com/MahApps/MahApps.Metro/issues/3040) "DataGrid virtualization broken when grouping activated" 是控件库层面的同类真案）。
  - 100 万行 × 100 列滚动卡顿（[微软 Q&A 253711](https://learn.microsoft.com/en-us/answers/questions/253711/)）。
- **解药**：
  - `VirtualizingPanel.IsVirtualizing="True"` + `VirtualizingPanel.VirtualizationMode="Recycling"`；
  - 分组用 `VirtualizingPanel.IsVirtualizingWhenGrouping="True"`（.NET 4.5+）；
  - **永远不要把虚拟化列表包在 ScrollViewer 里**（要滚动布局就让内部列表自己滚）；
  - 超大集合（WPF 列表过万条）考虑数据虚拟化（IDataAware / 分页按需加载）；
  - 参[微软控件性能指南](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/advanced/optimizing-performance-controls)。
- **SWDM 相关**：mod 列表可能上千条——直接套用上述解药。

### P5. 资源字典合并（MergedDictionaries）性能与键冲突

- **真实案例**：
  - [leecampbell.com 经典文章](https://leecampbell.com/2010/05/13/mergeddictionaries-performance-problems-in-wpf/) "I consider this to be a huge problem in WPF"——MergedDictionaries 查找性能差；
  - ANTS profiler 实测 `ResourceDictionary.get_MergedDictionaries` 查找成为热点（[SO 6693320](https://stackoverflow.com/questions/6693320/)，~300 个字典）；
  - 50+ 个控件样式字典各自 merge 微软控件字典 → 启动延迟（[dotnet/wpf issue #6652](https://github.com/dotnet/wpf/issues/6652)）；
  - 同名资源键合并冲突解析顺序坑（[Alex Feinberg 解法文](https://alexfeinberg.wordpress.com/2015/04/17/solving-the-wpf-resource-key-collision/)）。
- **解药**：主题字典**只合并一次**（App.xaml 顶层或单点 ResourceDictionary）；用 ` consolidation`——自定义控件库内合并而非每个控件 merge 一遍；键名加前缀（`swdm-`）防第三方库冲突；启动慢用 `dotnet-trace` 验证资源查找耗时。

### P6. DPI 缩放：模糊与跨显示器错位

- **真实案例**：[SO 39217355](https://stackoverflow.com/questions/39217355/) "WPF Application Blurry on High DPI Screen on Windows 10"——开发者发现两个自己写的 WPF 应用在高分屏上都模糊；[Scott Hanselman 经典文章](https://www.hanselman.com/blog/wpf-and-text-blurriness-now-with-complete-clarity)；[CefSharp issue #2856](https://github.com/cefsharp/CefSharp/issues/2856) 系统缩放变化时内容模糊。
- **解药**：
  - app.manifest 声明 Per-Monitor V2 DPI 感知（[微软指南](https://learn.microsoft.com/en-us/windows/win32/hidpi/declaring-managed-apps-dpi-aware)）；.NET 8 的 WPF 模板默认已带；
  - `UseLayoutRounding="True"` + `SnapToDevicePixels="True"` 消除亚像素模糊（[微软 Layout Rounding 文档](https://learn.microsoft.com/en-us/archive/blogs/text/layout-rounding)）；
  - 文字模糊加 `TextOptions.TextFormattingMode="Display"`（[WPF 4.0 文本栈改进文档](https://learn.microsoft.com/en-us/archive/blogs/text/wpf-4-0-text-stack-improvements)）；
  - 自绘卡片边缘优先用整数像素的 Border，别用 0.5px 细线。

### P7. 闪退与未处理异常的三层捕获

- **真实案例**：[SO 793100](https://stackoverflow.com/questions/793100/) 与 [SO 1472498](https://stackoverflow.com/questions/1472498/) 社区共识——三层捕获：`Application.DispatcherUnhandledException`（UI 线程 dispatcher 异常，微软文档指出 "By default, WPF catches unhandled exceptions and notifies users"——即不处理就是系统级白框闪退）、`AppDomain.CurrentDomain.UnhandledException`（非 UI 线程/其他线程，通常无法恢复，只能记日志后退出）、`TaskScheduler.UnobservedTaskException`（被遗忘的 Task 异常，.NET 4.6+ 默认不杀进程但仍需监控）。
- **SWDM 解药（与 Serilog 联动）**：
```csharp
// App.xaml.cs 构造函数
DispatcherUnhandledException += (s, e) =>
{
    Log.Error(e.Exception, "UI 线程未处理异常");
    e.Handled = true;              // 阻止默认闪退，展示友好错误条
    ShowErrorBar(e.Exception);      // 但要防止"带病运行"：严重异常仍应提示重启
};
AppDomain.CurrentDomain.UnhandledException += (s, e) =>
    Log.Fatal(e.ExceptionObject as Exception, "非托管未处理异常，进程将退出");
TaskScheduler.UnobservedTaskException += (s, e) =>
{ Log.Error(e.Exception, "未观察的 Task 异常"); e.SetObserved(); };
```
- 注意 e.Handled = true 不能滥用：[SO 793100](https://stackoverflow.com/questions/793100/) 高票答案警告 "there'll be still exceptions which preclude a successful resuming of your application, like stack overflow, exhausted memory"——这些必须让它崩并保留崩溃转储。
- **与下载内核的联动**：下载 provider 链式回退（1.x system_contracts 教训）的每个 provider 异常都要在服务层 catch，绝不允许冒泡成未处理异常。

---

## 7. 总推荐（一句话版 + 表）

| 层面 | 推荐 | 一句话理由 |
|---|---|---|
| MVVM | **CommunityToolkit.Mvvm 8.4.x** | 微软官方、声明式源生成器、AI 生成可靠度最高 |
| 控件 | **WPF-UI 4.3 作底 + 自绘 Card/Hint（PCL2 路线）** | 现代扁平底座 + PCL2 本就是全自绘；WPF-UI issue 积压需版本锁定+回归把关 |
| DI/日志/配置 | **MSDI + Serilog 4.4 + Options 模式** | 官方三件套，Generic Host 一体化 |
| 线程 | **async/await 全链路 + BackgroundService 下载队列 + 线程安全服务** | 避开 P1/P2 死锁模式， steamcmd 串行化沿用 1.x 契约 |
| 打包更新 | **Velopack + GitHub Releases** | 一条命令全包，Squirrel 已停摆，MSIX 对个人开发者签名不友好 |
| 坑预防 | 第 6 节 7 条清单全部进入代码规范 + CI 静态检查（CA2007 等规则开启） | 每条都有社区实证，非纸上谈兵 |

**一句话总结**：SWDM 2.0 = .NET 8 + CommunityToolkit.Mvvm + WPF-UI(自绘皮) + MSDI/Serilog/Options + Generic Host 后台下载队列 + Velopack(GitHub Releases) 更新；第 6 节 7 个致命坑全部有社区实证解药，直接落成代码规范。

**执行衔接建议**：本报告结论与已落地的 `swdm2/docs/design_baseline_2.0.md`（.NET 8 骨架）方向一致；下一步可将本报告的 7 条坑清单转写为 swdm2 代码规范条目（docs/design/），并在骨架 App.xaml.cs 中先落地 Serilog + 三层异常捕获（P7）与 Generic Host（4.3 节）。
