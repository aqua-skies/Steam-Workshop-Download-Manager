# SWDM 2.0 架构规格书（Architecture Specification）

> 版次：v1.0 · 2026-10-02 · 维护：arch-20（架构/稳定性域 owner）
> 依据：`swdm2/docs/design_baseline_2.0.md`（9 条锁定决策 + 保留资产清单）与 `docs/research2/` 五份报告（wpf_stack / wpf_ui_testing / idm_download_kernel / csharp_steam_workshop / pcl2_xaml_patterns）
> **文档地位：开发前置门（计划先行纪律）**——本文档 + t2 视觉规格 + t3 测试规格经 captain 认可、t5 讨论组终裁后，才允许开放开发任务（写产品代码）。研究、骨架与环境准备（含 t4 spike）不算开发。

---

## 0. 一句话架构

**SWDM 2.0 = .NET 8 (net8.0 / net8.0-windows) 五项目分层 + CommunityToolkit.Mvvm + WPF-UI 4.3.0 底座 + 自绘 PCL2 签名层 + MSDI/Serilog/Options + Generic Host 后台下载队列 + 双下载 provider（SteamKit2 CDN chunk 并行为主、steamcmd 封装兜底）+ Web API 元数据主源 + FlaUI 5.0.0 真实输入 UI 测试 + Velopack/GitHub Releases 分发。**

分层依赖链（单向、无环）：

```
Swdm2.UiTests  ──► Swdm2.App ──► Swdm2.Downloads ──► Swdm2.Steam ──► Swdm2.Core
      └────────────►(Core 只读断言辅助)
```

- `Swdm2.Core`：领域模型 / 配置 / 日志契约 / 路径 / 凭据 / 缓存 / 通用结果模型（net8.0，零外部依赖优先）
- `Swdm2.Steam`：Web API 客户端（主源）+ 社区页面回退 + 端点可达性探测 + 429/403 对策 + steamcmd 进程封装 + SteamKit2 CDN 客户端（net8.0）
- `Swdm2.Downloads`：双 provider 链 + 队列 / 状态机 / 分段续传 / 限速 / 事件总线（net8.0，引用 Steam）
- `Swdm2.App`：WPF MVVM（CommunityToolkit.Mvvm + WPF-UI 底座 + 自绘 Card + Generic Host 后台队列 + MSDI/Serilog/Options）（net8.0-windows）
- `Swdm2.UiTests`：FlaUI 5.0.0 UIA3 + xUnit + Xunit.StaFact，进程外启动被测 exe（net8.0-windows）

> **骨架现状与差异**：当前 `swdm2/` 骨架五项目已 build 绿，引用为 App→{Core,Steam,Downloads}、Steam→Core、Downloads→Core、UiTests→{Core,App}。**本规格要求补一条 Downloads→Steam 引用**（下载 provider 链需消费 Steam 域的 steamcmd 封装与 SteamKit CDN 客户端），属骨架接线，列入 D0.2 任务。

---

## 1. 对照基线：9 条锁定决策 → 架构元素映射

| 基线决策 # | 决策内容 | 本规格落点 |
|---|---|---|
| 1 | .NET 8 SDK（8.0.425） | 全项目 TFM：Core/Steam/Downloads = net8.0；App/UiTests = net8.0-windows；`< RollForward>` 不启用（锁 SDK 小版本，避免滑向 net10 行为差异） |
| 2 | 五项目骨架，域边界即类库边界 | §2-§6 模块契约；域 owner 直映：arch-20=Core/Downloads/架构稳定性、visual-20=App 自绘层与主题、qa-20=UiTests 与复测、captain=集成/构建/交付 |
| 3 | FlaUI 5.0.0UIA3 + xUnit + StaFact，进程外 `Application.Launch`，AutomationId 选择器，显式等待，Screen Object，失败截图 | §3.5 UiTests 契约 + §7 DAG 各阶段验证命令；AutomationId 命名规范 `<视图>_<控件>_<语义>` 写入 App 契约（§3.4） |
| 4 | 中文输入 ValuePattern Enter 为主 + Unicode 键事件/Ctrl+V；IME 拼音不做 | UiTests 输入三路径表（§3.5）；被测控件必须支持 ValuePattern（WPF TextBox 原生支持） |
| 5 | 视觉校验：被测进程内 Windows.Media.Ocr（中文）+ 像素 diff 补盲区；modlens 二次校验 | UiTests 视觉断言分层（§3.5）；静态区域像素 diff + 动态区域感知哈希容差 |
| 6 | CI：本机交互会话运行（FlaUI #168 Session 0 无桌面） | 验证命令一律本机 `dotnet test`（交互会话）；CI 方案 = 自托管 runner + 自动登录（D6.x，发布前落地） |
| 7 | 域 owner 线（arch/visual/qa + captain 集成） | DAG 任务归属列；bug 归属制（域 owner 修自己的域） |
| 8 | 下载域双 provider：SteamKit `CDNClientPool` 为主（chunk 级并行默认 8、chunk 自带 SHA 校验、isUgc 支持 Workshop）；steamcmd 兜底（quirk 保留）；HTTP 直链用分段+`.download` 尾部元数据续传；磁盘 IO 单文件偏移直写 + NTFS 稀疏占位（不支持则 SetLength 降级） | §3.3 Downloads 契约（provider 链、状态机、分段、限速、事件总线）+ §3.2 Steam 契约（steamcmd 封装、SteamKit CDN 客户端） |
| 9 | WPF 栈：CommunityToolkit.Mvvm 8.4.x + WPF-UI 4.3.0 底座 + 自绘 Card/Hint + Generic Host BackgroundService 队列（异常 worker 内全包 catch）+ MSDI + Serilog 4.4 + Options + Velopack 1.2.161；7 条致命坑转代码规范 | §3.4 App 契约（MVVM 规范、坑清单代码化）；wpf_stack §6 的 P1-P7 全部进 §4 学费清单与 §3.4 不变量 |

**基线 §三保留资产（学费）→ §4 学费清单逐条移植**（含"参数待重标定"标注 ⚠️）。

**基线 §四功能范围**：对等项（游戏选择/浏览/详情/下载/库/设置/匿名）与增强项（PCL2 视觉、IDM 体感、部分接入 Steam 官方）在 DAG 阶段 5-6 全覆盖；下载体感因双 provider 升级为真功能（steamcmd 路径分段数诚实降级 N/A）。

---

## 2. 分层与模块契约总则

### 2.1 依赖规则（编译期强制）

1. 依赖单向：Core ← Steam ← Downloads ← App；UiTests → App（+Core）。**禁止**任何反向引用、禁止 App 被 Core/Steam/Downloads 引用。
2. 禁止跨层"贴心"反向调用：Steam/Downloads 需要 UI 反馈时走事件/回调抽象（定义在自己层内，由 App 实现）。
3. NuGet 包边界：SteamKit2 3.4.0、Polly（可选，见 3.2.6）、HtmlAgilityPack/AngleSharp 限 Steam 项目；CommunityToolkit.Mvvm/WPF-UI/Velopack 限 App 项目；xUnit/FlaUI 限 UiTests 项目；Core 零 NuGet 依赖（仅 BCL）。
4. 命名空间 = 项目名：`Swdm2.Core.*`、`Swdm2.Steam.*`、`Swdm2.Downloads.*`、`Swdm2.App.*`、`Swdm2.UiTests.*`。

### 2.2 通用设计契约（全层）

- **异步全链路**：所有 IO/进程/网络 API 只有 `Async` 后缀形式；禁止 `.Result`/`.Wait()`（wpf_stack P1 死锁）；库内部 `ConfigureAwait(false)`。
- **取消传播**：公开方法一律接受 `CancellationToken`；窗口级 `CancellationTokenSource` 在 OnClosing 时 Cancel。
- **结果模型**：跨层方法返回 `Result<T, SteamError>` / `Result<T, DownloadError>`（判别式联合），禁止用异常做控制流；异常只用于真正意外的失败。错误分类与 1.x 一致（RateLimited/Blocked(403)/NotFound/AuthRequired/Network/CircuitOpen/Timeout）。
- **日志契约**：统一 `ILogger<T>`（Serilog 桥接）；结构化字段（`ItemId`、`AppId`、`Provider`、`ElapsedMs`）；**脱敏 sink 包装器**强制覆盖账号/密码/验证码（详见 §3.1.5）。
- **不可变优先**：领域模型用 `record`/`immutable`；可变缓存出口必须深拷贝（1.x `api_cache` 污染事故，见 §4）。
- **参数集中管理**：所有可调参数（节流间隔、退避、并发、超时、刷新节流）一律走 `IOptionsMonitor<T>` 强类型选项，代码中不出现魔数；凡从 1.x 或开源项目移植的数值，一律在选项注释中标注 ⚠️**参数待重标定**（经验复验纪律），并登记到 §8 重标定任务清单。
- **命名约定**：类型名 PascalCase；UiTests AutomationId 见 §3.5.3。

---

## 3. 模块契约（公共 API / 线程模型 / 不变量）

---

### 3.1 Swdm2.Core（领域模型 / 配置 / 日志契约 / 路径 / 凭据）

**职责**：2.0 的领域语言。零外部依赖，纯 BCL。

#### 3.1.1 公共 API（摘要）

```csharp
namespace Swdm2.Core.Domain
    // 领域模型（全部 record，不可变）
    public sealed record AppId(int Value);                    // 与 WorkshopItem 元数据中的游戏
    public sealed record PublishedFileId(ulong Value);        // 工坊物品 id（ulong，与 Steam API 一致）
    public sealed record UgcId(ulong Value);                  // 与 PublishedFileId 不同（DepotDownloader #713 教训，UI 必须区分提示）
    public sealed record WorkshopItem(PublishedFileId Id, AppId AppId, string Title, string? Description,
                                      ulong? FileSize, string? PreviewUrl, string? Creator,
                                      IReadOnlyList<PublishedFileId> Dependencies, ...);
    public sealed record GameInfo(AppId Id, string Name, string[] Aliases, AppId? DsAppIdFallback); // DS AppID 回退（WorkshopDL 经验）
    public sealed record ModLibraryEntry(...);                // 本地库条目
    public sealed record DownloadTaskId(Guid Value);

namespace Swdm2.Core.Results
    public readonly struct Result<T, TErr> where TErr : Enum { bool IsOk; T? Value; TErr? Error; ... }
    public enum SteamError { None, RateLimited, Blocked, NotFound, AuthRequired, Network, Timeout, CircuitOpen, Cancelled, Deserialization }
    public enum DownloadError { None, ProviderFailed, InvalidChecksum, DiskSpace, RangeNotSupported, Cancelled, ... }

namespace Swdm2.Core.Paths
    public interface IPathService
        // 便携模式：root = exe 所在目录；安装模式：root = %APPDATA%\SWDM（Velopack 安装位置可迁移）
        string Root { get; }
        string SteamCmdDirectory { get; }                      // <Root>/steamcmd
        string WorkshopContent(AppId app)                      // <Root>/steamcmd/steamapps/workshop/content/<appid>（与 SCA/1.x 同构）
        string DownloadStaging(DownloadTaskId)                 // 未完成下载的暂存区（.download 尾部元数据文件）
        string LogDirectory { get; }                           // <Root>/logs
        string ConfigFile { get; }
        PathMode Mode { get; }                                 // Portable / Installed
    public enum PathMode { Portable, Installed }

namespace Swdm2.Core.Credentials
    public interface ICredentialStore                          // DPAPI 实现（ProtectedData.CurrentUser）
        Task<ReadOnlyMemory<char>?> GetPasswordAsync(string account, CancellationToken ct);
        Task SetPasswordAsync(string account, ReadOnlyMemory<char> password, CancellationToken ct);
        Task DeleteAsync(string account, CancellationToken ct);

namespace Swdm2.Core.Caching
    public interface IAsyncCache<TKey, TValue> where TValue : class
        Task<TValue?> GetOrAddAsync(TKey key, Func<CancellationToken, Task<TValue>> factory, TimeSpan ttl, CancellationToken ct);
        // ⚠️ 契约：命中返回前必须深拷贝（1.x api_cache 污染学费，enrich() 就地修改事故）

namespace Swdm2.Core.Options
    public sealed class SteamOptions      { ProxyMode Proxy; string? CustomProxyUrl; double[] ThrottleMs; int MaxConcurrentMetadataQueries; int BackoffInitialMs; int BackoffMaxMs; int CircuitThreshold; int CircuitCooldownMs; }
    public sealed class DownloadOptions   { int MaxConcurrentDownloads; int MaxChunkParallelism; long MaxSpeedBytesPerSecond; int ChunkTimeoutMs; int OverlapBytes; bool UseSparsePlaceholder; int MaxConnectionsPerServer; int ProgressThrottleMs; }
    public sealed class PathOptions       { PathMode ForceMode; string? CustomRoot; }
```

#### 3.1.2 线程模型

- 全部不可变或线程安全；无 UI 线程需求；`IPathService` 计算纯函数式（无锁）。
- `ICredentialStore` 异步、无锁（DPAPI 加解密在线程池线程）。
- 配置热更新：`IOptionsMonitor<T>.OnChange` 回调在线程池线程触发；订阅方禁止在回调里直接碰 UI（marshal 到 UI 线程）。
- `IAsyncCache` 内部用 `ConcurrentDictionary` + SemaphoreSlim 防击穿（single-flight）。

#### 3.1.3 不变量（含 1.x 学费移植）

| # | 不变量 | 来源/学费 |
|---|---|---|
| C1 | 领域模型 record 不可变；集合属性只读 | 1.x 联想模型原地更新教训（clear() 重建 → UI 闪烁/状态丢失） |
| C2 | 凭据：DPAPI(CurrentUser) 加密落盘；**明文不进日志、不进配置文件、不进异常消息** | 基线 §三；SCA CredentialStore（DPAPI）；1.x `_redact_secrets` |
| C3 | 便携模式 = exe 同级目录，可整目录迁移；安装模式 = %APPDATA%；`Root` 一经启动确定，运行期不可变 | 1.x 便携模式经验 |
| C4 | 版本号单一来源：构建时 `ThisAssembly.Version` 注入，程序/安装器/更新包同源 | 1.x 版本号双端同步纪律 |
| C5 | 缓存出口深拷贝；`record` 集合返回 `IReadOnlyList` | api_cache 污染学费（§4 教训 #4） |
| C6 | `PublishedFileId` 与 `UgcId` 是不同类型，禁止隐式互换 | DepotDownloader #713（换错 id 得 "A task was cancelled"） |
| C7 | ⚠️[参数待重标定] 所有 Options 数值默认值来自 1.x/开源项目，仅作起点；2.0 交付前必须由 §8 重标定任务实测后锁定 | 用户经验复验纪律 |

---

### 3.2 Swdm2.Steam（Web API 主源 + 社区页面回退 + 端点探测 + 429/403 对策 + steamcmd 进程封装 + SteamKit2 CDN 客户端）

**职责**：一切与 Steam 服务对话的能力。元数据、鉴权、内容传输的原语。

#### 3.2.1 公共 API（摘要）

```csharp
namespace Swdm2.Steam.Connectivity
    public enum EndpointKind { Api, Store, Community, Cdn }
    public sealed record EndpointStatus(EndpointKind Kind, Reachability Reach, LatencyMs);
    public enum Reachability { Unknown, Direct, ViaProxy, Blocked, Unreachable }
    public interface IEndpointProbe                     // 启动期三端点探测（api/store/community）
        Task<IReadOnlyDictionary<EndpointKind, EndpointStatus>> ProbeAsync(CancellationToken ct);
    public interface IConnectivityState                 // 状态栏数据源：直连/系统代理/自定义代理 + 各端点状态
        IReadOnlyDictionary<EndpointKind, EndpointStatus> Current { get; }
        event EventHandler<IReadOnlyDictionary<EndpointKind, EndpointStatus>>? Changed;

namespace Swdm2.Steam.Web
    public interface ISteamWebApiClient                 // 元数据主源（基线 §三复验：匿名可用且完整）
        Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(PublishedFileId id, CancellationToken ct);
        Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(IReadOnlyList<PublishedFileId> ids, CancellationToken ct);  // itemcount=N 批量（SO #56018823）
        Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(PublishedFileId collectionId, CancellationToken ct);
    public interface IStoreSearchClient                 // 游戏搜索：storesearch（匿名无 key）
        Task<Result<IReadOnlyList<GameInfo>, SteamError>> SearchAsync(string term, CancellationToken ct);
    public sealed class RequestFingerprints             // 429 指纹头（静态常量 + 应用扩展方法）
        public static readonly string UserAgent;        //   Chrome UA
        public static readonly string AcceptLanguage;   //   zh-CN,zh;q=0.9,en;q=0.8
        public const string XRequestedWith = "X-Requested-With";  // 双保险（1.x 实测两个都加）

namespace Swdm2.Steam.Community                         // 回退源：仅 Community 可达时使用
    public interface ICommunityScraper                  // browse 列表/依赖/评论等 API 未覆盖项 + 详情富化
        Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> BrowseAsync(AppId app, BrowseQuery query, CancellationToken ct);
        Task<Result<WorkshopItem, SteamError>> EnrichFromDetailPageAsync(WorkshopItem item, CancellationToken ct);

namespace Swdm2.Steam.Resilience
    public interface IThrottler                        // 端点差异化节流；锁覆盖 read-sleep-write 全程
        Task<IAsyncDisposable> AcquireAsync(EndpointKind kind, string pathPrefix, CancellationToken ct);
        // ⚠️[参数待重标定] 间隔：详情页 3s 或 6s（1.x 两处口径不一：基线 §三=3s / csharp_steam_workshop §3.3=6s——必须实测裁决）/ browse 2s / api 1-2s
    public interface ICircuitBreaker                    // 1.x circuit.py 语义移植
        bool IsOpen(EndpointKind kind);                 //   连续 3 次失败熔断 / 连接级失败立即熔断 / 冷却 15s / 半开重置 ⚠️[参数待重标定]

namespace Swdm2.Steam.SteamCmd
    public interface ISteamCmdDeployer                  // steamcmd.zip 下载 + 解压 + exe 存在校验（SCA/1.x steamcmd_deploy）
    public interface ISteamCmdRunner                    // 进程封装（批拼命令 + 正则解析 + 成功三元判定）
        Task<SteamCmdRunResult> RunAsync(IReadOnlyList<WorkshopDownloadRequest> items, SteamCmdLogin login, string installDir, IProgress<SteamCmdProgress> progress, CancellationToken ct);
    public sealed record SteamCmdLogin(string? Account, ReadOnlyMemory<char>? Password, string? GuardCode);
    public sealed record SteamCmdRunResult(IReadOnlyDictionary<PublishedFileId, ItemOutcome> Outcomes, string RawStdout);
    public enum ItemOutcome { SuccessVerified, SuccessZeroBytes, FailedNoOutput, Failed, NeedsGuardCode, RateLimited, InvalidCredentials }

namespace Swdm2.Steam.Cdn                               // SteamKit2 3.4.0（锁版本）
    public interface ISteamSessionManager              // 匿名/账号会话；2FA 码交互回调由 App 实现
        Task LoginAsync(SteamCmdLogin login, CancellationToken ct);
    public interface ISteamCdnClient                    // Workshop 内容传输原语（DepotDownloader isUgc 路径）
        Task<ManifestHandle> ResolveUgcManifestAsync(AppId app, PublishedFileId pubfile, CancellationToken ct);
        IAsyncEnumerable<ChunkResult> DownloadChunksAsync(ManifestHandle manifest, CancellationToken ct);  // chunk 自带 SHA 校验
```

#### 3.2.2 线程模型

- 网络全异步；`HttpClient` 由 App 层 `IHttpClientFactory` 注入（池化、`PooledConnectionLifetime` 托管 DNS 变化）。
- `IThrottler`：`SemaphoreSlim` + 按端点键的锁字典；**锁覆盖 read-sleep-write 全程**（1.x 教训：节流窗口内并发读会击穿间隔）。
- `ICircuitBreaker`：`lock` + `Interlocked` 计数（1.x circuit.py 的 C# 直译）。
- `ISteamCmdRunner`：进程专跑在线程池 Task；stdout/stderr 两个独立读取 Task（防重定向缓冲区死锁）；steamcmd 自身日志文件尾随读取 Task（200ms 轮询，SCA 经验：关键提示行可能只落磁盘日志）；**UI 线程禁止 `WaitForExit`**；看门狗：绝对超时 + 无输出超时（SCA：8 分钟绝对 / 60 秒无输出。
- `ISteamCdnClient`：chunk 级并发（`CDNClientPool` round-robin 加权），并发上限由 DownloadOptions 注入（⚠️[参数待重标定] 默认 8，对齐 DepotDownloader `-max-downloads`）。
- steamcmd 进程**串行化**：进程级 `SemaphoreSlim(1,1)`（1.x `_proc_lock` 教训：共享 `_proc` 被并发任务覆盖致 poll() 空指针——C# 侧用局部变量保存进程句柄 + 信号量双保险）。

#### 3.2.3 不变量（含 1.x 学费）

| # | 不变量 | 来源/学费 |
|---|---|---|
| S1 | 所有发往 steamcommunity 的请求必带指纹头四件套（UA + Accept-Language + X-Requested-With）；裸 UA = 必 429 | 1.x 34 次实测（§4 教训 #1） |
| S2 | 429 处理**不读 Retry-After**（响应从不带），一律客户端自退避；见 429 → 冷却（比普通熔断更长）⚠️[参数待重标定：1.x 30s 起/90s 封顶，问"能否更短"] | 1.x 实测（教训 #2） |
| S3 | 403 = IP/代理边缘层：快速失败抛 `Blocked`，用过期缓存兜底，**不重试** | 1.x（教训 #3） |
| S4 | 社区页面请求**仅在 Community 端点探测可达时发出**；不可达时走 Web API 降级路径，不静默失败（引导用户配代理） | 基线 §三 端点可达性矩阵 |
| S5 | **C# HttpClient 不读系统代理**：ProxyMode 三态（None/SystemCustom/CustomUrl）显式注入 `SocketsHttpHandler.Proxy` | 基线 §三；csharp_steam_workshop §6.3 |
| S6 | steamcmd 成功三元判定：输出行 Success + bytes>0 + 磁盘递归非空；失败 item 删除残留空目录（防下次"已存在即跳过"误判） | SCA sweep 校验（§4 教训 #6） |
| S7 | steamcmd 退出码**不可信**，结果一律以输出行为准；ExitCode 非零仅作 OtherFailure 兜底 | SCA SteamAuth（§4 教训 #6） |
| S8 | `+force_install_dir` 必须在所有下载命令**之前**；`+quit` 最后；批拼单进程时失败 item 不中断后续 item | 1.x steamcmd_engine 实测（§4 教训 #6） |
| S9 | steamcmd 输出在进入日志/UI 前过滤账号名/密码/验证码（`line.Replace(username, "***")`） | 1.x `_redact_secrets`（教训 #8） |
| S10 | TLS 陷阱：HandshakeFailure 优先设 `SslProtocols = Tls12\|Tls13` 而非关代理 | DepotDownloader #727 / 1.x 推送经验 |
| S11 | ⚠️[参数待重标定] 节流/退避/熔断/并发全部走 Options，不允许硬编码 | 经验复验纪律 |
| S12 | 元数据主源 = Web API `GetPublishedFileDetails`（匿名可用且完整，真实 id 3808352517 实测 result:1 + 全字段）；`GetFileSize` 端点**不存在**，禁止设计引用；`file_url` 字段 2017 年已移除（下载不走它） | 基线 §三 Web API 复验纠错 |

---

### 3.3 Swdm2.Downloads（双 provider 链 + 队列 / 状态机 / 分段续传 / 限速 / 事件总线）

**职责**：下载生命周期管理。引用 Steam（消费 steamcmd 封装与 SteamKit CDN 原语）。

#### 3.3.1 公共 API（摘要）

```csharp
namespace Swdm2.Downloads.Contracts
    public sealed record DownloadTask(DownloadTaskId Id, AppId App, PublishedFileId Item, string TargetDirectory, DownloadProviderKind? ForcedProvider, DownloadTaskPriority Priority);
    public enum DownloadProviderKind { SteamKitCdn, SteamCmd, HttpDirect }
    public enum DownloadTaskState { Queued, Preparing, Downloading, Paused, Verifying, Completed, Failed, Cancelled }
    public sealed record DownloadProgressSnapshot(DownloadTaskId Id, long TotalBytes, long DownloadedBytes, int ActiveSegments,
                                                  double CurrentSpeedBytesPerSec, double AverageSpeedBytesPerSec, TimeSpan? Eta, DownloadTaskState State);
    public interface IDownloadEventBus                        // 进度/状态事件流（UI 订阅）
        IObservable<DownloadEvent> Events { get; }            //   DownloadEvent = Progress/StateChange/SegmentChange/Completed/Failed
    public interface IDownloadQueue                          // 队列 API（UI 侧 + 调度器侧共用）
        DownloadTaskId Enqueue(DownloadTask task);           //   新任务自动进队列（IDM 语义）
        ValueTask PauseAsync(DownloadTaskId, CancellationToken ct);
        ValueTask ResumeAsync(DownloadTaskId, CancellationToken ct);
        ValueTask CancelAsync(DownloadTaskId, CancellationToken ct);
        ValueTask RetryAsync(DownloadTaskId, CancellationToken ct);
        ValueTask SetPriorityAsync(DownloadTaskId, DownloadTaskPriority ct);   // 用户点击 priority 绕过等待（1.x 节流纪律同款语义）
        IReadOnlyList<DownloadTaskSnapshot> Snapshot();

namespace Swdm2.Downloads.Providers
    public interface IDownloadProvider                       // provider 链单元
        DownloadProviderKind Kind { get; }
        bool CanHandle(DownloadTask task, ConnectivityStateSnapshot connectivity);   // 路由判据
        Task<ProviderExecutionResult> ExecuteAsync(DownloadTask task, DownloadContext ctx, IProgress<DownloadProgressSnapshot> progress, CancellationToken ct);

namespace Swdm2.Downloads.Segments                          // HTTP 直链场景（预览图/直链 CDN 资源）
    public interface ISegmentPlanner                        // IDM in-half division：初始 N 段；段完成→从最大未完成段中点分裂→指派空闲 worker（复用同一 HttpClient 连接池 = 连接复用）
    public interface IResumeStore                           // `.download` 尾部元数据（定长头 + 偏移指针）：chunk 表(start,end,done) + URL + ETag/Last-Modified + 来源页参数
    public interface ISparseFileAllocator                    // FSCTL_SET_SPARSE 占位；GetVolumeInformation 查 FILE_SUPPORTS_SPARSE_FILES，不支持降级 SetLength

namespace Swdm2.Downloads.Limiter
    public interface ISpeedLimiter                          // 令牌桶（chunk 调度层 + HTTP 层双点）：真限速（SteamKit 可控；steamcmd 场景为调度层诚实假象）
```

#### 3.3.2 线程模型

- **单写者状态机**：`DownloadQueueWorker : BackgroundService`（Generic Host，AddHostedService）持有状态机唯一写权；UI/其他线程只读 `Snapshot()` 快照。
- 队列底层 `System.Threading.Channels.Channel<T>`（多生产者：UI 入队、自动重试、更新检查；单消费者：worker）。
- **HostedService 异常 worker 内全包 catch**：任何异常 → 记日志 + 事件总线发 Failed 事件 + 错误横幅（Snackbar），**绝不允许冒泡到 Host**（默认 Host 会在 BackgroundService 抛异常时停止整个应用——对桌面应用毁灭性）。
- 进度聚合器：provider 频繁进度回调 → 线程安全聚合（EMA 当前速度 + 平均速度 + 剩余/当前）→ UI 订阅节流刷新（⚠️[参数待重标定] 500ms-1s；wpf_stack §4.1：避免每秒数百次 Dispatcher 调用造成 UI 饥饿）。
- steamcmd provider 执行时占用 Steam 域的进程级信号量（串行化跨 provider 共享）。
- 令牌桶限速器：`Interlocked` 无锁补令牌（ Stopwatch 计时）。

#### 3.3.3 不变量（含 IDM/1.x 学费）

| # | 不变量 | 来源/学费 |
|---|---|---|
| D1 | 状态机转移受限：合法转移表（Queued→Preparing→Downloading→{Paused↔Downloading}→Verifying→Completed/Failed/Cancelled；任何状态→Cancelled）；非法转移抛 `InvalidStateTransition`（可测） | 1.x provider 链与状态机经验 |
| D2 | provider 链回退顺序：**SteamKitCdn（主）→ SteamCmd（兜底）**；HttpDirect 用于直链资源；回退按错误类型路由（Blocked/NeedAccount → 直切 steamcmd 账号路径；会话级失败 → 回退 steamcmd） | 基线决策 8；1.x 链式回退（§4 教训 #10） |
| D3 | 队列并发：`MaxConcurrentDownloads` 由调度器级控制（IDM 语义：并发只归 Scheduler 管）；手动"立即下载"绕过队列 | IDM functions5 |
| D4 | 暂停的任务**不占并发槽**；取消的任务立即释放（含子进程 kill：先写 `quit\n` → terminate → 排空 stdout/stderr → wait 超时强杀，1.x 三段式收尾） | 1.x（教训 #6） |
| D5 | chunk 完整性：SteamKit chunk **SHA 必校验**（比 IDM 更强）；HTTP 分段用**重叠字节比对**（每段多请求 16-64B，续传起点回退比对）⚠️[参数待重标定] | DepotDownloader / IDM FAQ problems9 |
| D6 | Range 探测：下载前 HEAD/轻探测 `Accept-Ranges: bytes` + `Content-Length` + ETag/Last-Modified；服务器返回 200 而非 206 → **整段回退单流** | bezzad/Downloader issue #119 |
| D7 | 续传元数据随文件持久化（`.download` 尾部）；续传时先校验服务器仍支持 Range 且文件未变；失效链路（200-with-HTML/403）触发**重解析**（来源页参数随任务持久化），不直接报错 | SuperUser #657720（社区经验，标注为推断） |
| D8 | 磁盘 IO：单文件偏移直写（免拼接）为主；大文件可选 NTFS 稀疏占位（⚠️**不可逆**：稀疏标记只用于下载期文件，**禁止**对用户既有库文件操作）；拼接（A 策略）仅网络盘/AV 冲突回退 | idm_download_kernel §5 |
| D9 | steamcmd provider 场景的 IDM 体感**诚实降级**：速度=stdout 进度行解析或磁盘增长估算；无稳定速度时 ETA="未知"；分段数=N/A；限速=调度层（启动时机/并发控制） | idm §4.2 映射表（§4 教训 #6） |
| D10 | 完成产物路径在任务完成前**不可被库扫描认领**（暂存区 → 原子移动/重命名） | 1.x 0 字节假成功防御延伸 |
| D11 | ⚠️[参数待重标定] MaxChunkParallelism（起点 8=DepotDownloader 默认）、MaxConnectionsPerServer（起点 8）、ChunkTimeoutMs（起点 5s=bezzad）、OverlapBytes（起点 16-64）、MaxConcurrentDownloads（起点 1，问"能否更大"） | 经验复验纪律 |
| D12 | 事件总线事件**携带任务快照**（不可变），订阅方无需回查状态机 | 消除 1.x 共享可变状态竞态 |

---

### 3.4 Swdm2.App（WPF MVVM + WPF-UI 底座 + 自绘 Card + Generic Host）

**职责**：用户界面、窗口/页面/主题、MVVM 绑定、后台服务宿主、打包更新入口。

#### 3.4.1 架构分层

```
Swdm2.App
 ├─ Hosting/        App.xaml.cs：Host.CreateDefaultBuilder + ConfigureAppConfiguration +
 │                  ConfigureServices（Options/Serilog/视图/服务/HostedService）+ 三层异常捕获
 ├─ Ui/Controls/    自绘签名层：SwdmCard / Hint / SmoothScrollViewer / ModListItem / AniHelper（命名轨道）
 ├─ Ui/Themes/      Light.xaml / Dark.xaml / Accent.xaml / Common.xaml（MergedDictionaries 换字典切换）
 ├─ Ui/Pages/       PageBase + 容器替换导航 + 返回栈；主页/浏览/详情/下载/库/设置
 ├─ Ui/Dialogs/     Steam Guard 收码、错误横幅（Snackbar）
 ├─ ViewModels/     CommunityToolkit.Mvvm：[ObservableProperty] / [RelayCommand]
 └─ Services/       UI 侧适配器：PageNavigationService / ThemeService / ErrorReporter /
                    NotificationService（toast + 托盘）
```

#### 3.4.2 公共 API（摘要）

```csharp
namespace Swdm2.App.Hosting
    public sealed partial class App : Application            // Generic Host 接入（wpf_stack §3.2 骨架）
        // OnStartup: VelopackApp.Build().Run()（Main 最开头，自定义 Main）→ _host.StartAsync() → MainWindow.Show()
        // OnExit: _host.StopAsync() → _host.Dispose()
        // 三层捕获：DispatcherUnhandledException / AppDomain.CurrentDomain.UnhandledException / TaskScheduler.UnobservedTaskException
namespace Swdm2.App.Ui.Controls
    public class SwdmCard : ContentControl                   // PCL2 MyCard 三层结构 + 90ms 四路颜色 + 阴影 0.07→0.4
    public static class AniHelper                            // 命名轨道 Begin/Stop（同键先停旧的）+ StartColor
    public class SmoothScrollViewer : ScrollViewer           // PreviewMouseWheel 接管 + 300ms 缓动惯性滚动
    public abstract class PageBase : UserControl             // RunEnter/RunExit（stagger 25ms + 双段位移）
namespace Swdm2.App.Ui.Navigation
    public sealed class PageNavigationService                // Border 容器替换 + PageStack 返回栈（110ms 退出 → 30ms 进入）
```

#### 3.4.3 线程模型

- **UI 线程独占 UI 对象**；后台只碰线程安全服务/数据；`ObservableCollection` 仅在 UI 线程修改（创建也在 UI 线程），由绑定引擎自动 marshal。
- 必须直接操作控件时 `Dispatcher.InvokeAsync`（禁同步 `Invoke` 于可能被主线程等待的路径——wpf_stack P2 互等死锁）。
- 下载进度：后台线程 → 进度聚合器（线程安全）→ UI 线程定时批量刷新（⚠️[参数待重标定] 500ms-1s）。
- **async/await 三坑零容忍**：① UI 线程 `.Result`/`.Wait()` 禁止（CA2007 规则开启）；② `async void` 禁止（事件处理器例外但必须 try/catch 全包 + 记日志）；③ 窗口级 CTS：OnClosing Cancel，防 await 期间窗口已关闭。
- Generic Host：`OnStartup` 里 `StartAsync`、`OnExit` 里 `StopAsync`；`DownloadQueueWorker` 常驻。

#### 3.4.4 不变量（wpf_stack 7 坑 + PCL2 学费代码化）

| # | 不变量 | 来源 |
|---|---|---|
| A1 | 所有绑定数据源实现 INotifyPropertyChanged（`[ObservableProperty]` 自动满足）；长生命事件源（静态/单例下载事件）用 `WeakEventManager` 或关闭时显式退订 | wpf_stack P3 |
| A2 | 虚拟化列表：`VirtualizingPanel.IsVirtualizing="True"` + `Recycling` + `ScrollUnit="Pixel"`；**永远不把虚拟化列表包在 ScrollViewer 里**；分组开 `IsVirtualizingWhenGrouping` | wpf_stack P4；pcl2 §4.3 路线 A |
| A3 | 主题字典只合并一次（App.xaml 单点）；键名一律 `swdm-` 前缀防第三方冲突；主题切换 = MergedDictionaries 换字典（无闪烁） | wpf_stack P5 |
| A4 | Per-Monitor V2 DPI 感知（app.manifest）；`UseLayoutRounding` + `SnapsToDevicePixels`；文本 `TextOptions.TextFormattingMode="Display"` | wpf_stack P6 |
| A5 | 三层异常捕获常驻；`e.Handled=true` 仅限可恢复异常（栈溢出/OOM 让它崩） | wpf_stack P7 |
| A6 | MVVM 纯声明式：View 只做绑定/模板，ViewModel 不引用 `System.Windows.Controls`（除 `ICommand` 语义）；命令一律异步 + CancellationToken | wpf_stack §1.4（AI 生成可靠度） |
| A7 | **AutomationId 命名规范**（从第一个控件执行）：<`视图`>_<_控件`>_<_语义`>（如 `SearchPage_SearchBox_Input`）；x:Name 自动成为 AutomationId 亦可；FlaUI 测试只按 AutomationId 找元素 | wpf_ui_testing §7.1（≈80% 鲁棒性） |
| A8 | WPF-UI 锁版本 4.3.0；升级 = 全量回归门（456 开放 issue 的风险对冲）；主题真源 = 自建 Light/Dark/Accent 字典（不与 WPF-UI ApplicationThemeManager 并存，避免双主题状态）；WPF-UI 仅作窗口/控件基座 | 基线决策 9；pcl2 §8 弯路嫌疑标注 → 已由 t4 spike 实证（附录 SP-1：2 处 API 弯路 + A8b 反射实测规则） |
| A9 | 即时反馈：每个用户操作 ≤150ms 内有可见反馈（禁用态/进度条微动/动画起步）⚠️[参数待重标定：实测能否更短] | 1.x UI 教训（§4 教训 #9） |
| A10 | 搜索联想**原地更新**数据源，不 clear() 重建；中英别名/归一化在 Core 层 | 1.x（§4 教训 #9） |
| A11 | Steam Guard 收码弹窗用 `Dispatcher.Invoke` 切 UI 线程 ShowDialog + `TaskCompletionSource<string?>` 唤醒后台 await | SCA SteamAuth（§4 教训 #6） |
| A12 | 弹窗不打桩、不替换实现：MessageBox 该弹还弹，测试按 FlaUI #255 路径点掉 | 1.x 桩函数教训（§4 教训 #12） |

---

### 3.5 Swdm2.UiTests（FlaUI 5.0.0 真实输入 UI 测试）

**职责**：模拟真实用户鼠标点击与键盘输入的端到端验证。**不打桩、不直调 ViewModel、不经 API 层**（用户测试纪律）。

#### 3.5.1 技术契约

- FlaUI 5.0.0+ UIA3 + xUnit + `Xunit.StaFact`（`WpfFact`）。
- **进程外** `Application.Launch(被测 exe, "--test-mode")`：与用户双击 exe 完全一致（独立进程/Dispatcher/启动路径）。
- 选择器：**一律 AutomationId**；禁止显示文本、坐标、层级索引、ClassName。
- 等待：`Retry.While` / `Wait.Until` 显式超时；**禁止 `Thread.Sleep`**。
- 组织：Screen Object 模式（每个窗口/页面一个映射类）。
- 失败证据：`FlaUI.Capturing.Capture.Screen()/Element()` 截图落盘（`TestArtifacts/`）+ 被测进程 Serilog 日志。
- 串行：`[Collection]` + `DisableTestParallelization`；启动前杀残留进程（单实例互斥）。
- 分层：冒烟套件（5 条主旅程：启动→搜索→详情→下载→库）类级共享进程；关键流程（下载/搜索）方法级独立进程。
- 视觉校验（补充不替代）：Windows.Media.Ocr（中文）断言文本；静态区域像素 diff + 动态区域感知哈希容差。
- CI：本机交互会话 `dotnet test`（FlaUI #168）；发布前 D7 落地自托管 runner。

#### 3.5.2 中文输入三路径

| 路径 | 用法 | 定位 |
|---|---|---|
| ValuePattern `Enter("饥荒")` | 主路径（最稳，WPF TextBox 原生支持） | 语义级设值 |
| Unicode 键盘 `Keyboard.TypeText`（`KEYEVENTF_UNICODE`→WM_CHAR） | 真实输入事件、不经 IME | 备用 |
| 剪贴板 + 真实 `Ctrl+V` | 真实击键 + 中文可靠 | 备用 |
| **IME 拼音模拟** | **不做** | 禁止 |
| 按键触发类操作（回车搜索） | 必须真实键盘事件 `Keyboard.Type(VK_RETURN)` | 强制 |

#### 3.5.3 不变量

| # | 不变量 | 来源 |
|---|---|---|
| T1 | 被测元素必须有 AutomationId（A7）；新增可交互元素不带 id = 测试任务不通过 | wpf_ui_testing §7.1 |
| T2 | 弹窗断言按 FlaUI #255：MessageBox 是 Window，`FindFirstDescendant` 找按钮点击；**禁止打桩替换** | 基线决策 3；1.x 桩函数教训 |
| T3 | 窗口前置（`Focus()`/`SetForeground()`）后再输入；输入前 `Focus()` TextBox；窗口位置/大小显式设置（DPI/分辨率一致） | wpf_ui_testing §3.3 |
| T4 | 跨进程真实点击注意 #323（夺物理鼠标焦点）；无 ClickablePoint 时 InputSimulator 裸 SendInput 到 `PointToScreen()` 坐标 | wpf_ui_testing §1.4 |
| T5 | 测真不测纯逻辑：纯逻辑（别名归一化/字符串匹配）归 Core 单元测试；UI 层不重复断言（倒金字塔） | wpf_ui_testing §4.3 |
| T6 | 每次迭代完成后 **FlaUI 冒烟套件全量回归**（含新增功能与功能间关联交互） | 迭代交付四要素 |

---

## 4. 1.x 学费清单移植表（不变量来源）

> 全部条目源自基线 §三保留资产 + 五份报告的实测/源码结论。**参数类条目一律标 ⚠️[参数待重标定]**（用户经验复验纪律：移植到新栈/新环境必须实测重标定，先问"能否缩短/能否更小"再验证采纳）。

| # | 学费 | 移植落点 | 参数状态 |
|---|---|---|---|
| 1 | 429 指纹层：裸 Chrome UA 缺 Accept-Language 必 429；补 `Accept-Language` 或 `X-Requested-With` 任一即 200（34 次实测） | S1 / `RequestFingerprints` | 机制照搬（非参数） |
| 2 | 429 响应从不带 Retry-After（响应体 334KB）；Referer/Origin/匿名 cookie 全无效；Steam 客户端 UA 亦 200 | S2（不读 Retry-After，客户端自退避） | ⚠️ 退避时长待标定（1.x 30s 起/90s 封顶） |
| 3 | 403 = IP/代理边缘层：快速失败 + 过期缓存兜底，重试无用 | S3 / Result 错误模型 | 机制照搬 |
| 4 | 端点差异化节流：端点间间隔分档；锁覆盖 read-sleep-write 全程；priority 绕过等待 | `IThrottler` / D3 | ⚠️ 间隔待标定（1.x 口径不一：详情 3s vs 6s / browse 2s / api 1-2s——实测裁决） |
| 5 | api_cache 命中必深拷贝（可变对象 + 就地 enrich 污染事故） | C5 / `IAsyncCache` | 机制照搬 |
| 6 | steamcmd quirk 全套：无逐字节进度、0 字节假成功、退出码不可信、`+force_install_dir` 位置、stdin 关闭、批拼单进程、输出行正则、三段式收尾、串行化锁、看门狗、输出脱敏、Sweep 磁盘校验、失败删空目录、mod 更新不删除已删文件（时间戳 zip 备份方案） | S6-S9 / D4 / D9 / steamcmd wrapper | 机制照搬（正则表直接移植：`Success\. Downloaded item (\d+) to "([^"]+)" \((\d+) bytes\` 等） |
| 7 | 版本号双端同步（程序 + 安装器） | C4 + Velopack 包版本同源 | 机制照搬 |
| 8 | 凭据不落日志/不进配置（DPAPI） | C2 / `ICredentialStore` | 机制照搬（C# 侧重做：ProtectedData） |
| 9 | UI 层：联想原地更新（勿 clear() 重建）；每操作即时反馈 ≤150ms；中英别名/归一化搜索；隐式单例显式化 | A9 / A10 / Core 归一化 | ⚠️ 150ms 阈值待实测 |
| 10 | provider 链式回退（多 provider + 账号匿名双模式） | D2 | 链结构照搬 |
| 11 | Web API 复验纠错：GetPublishedFileDetails 匿名**可用且完整**（真实 id 3808352517）；GetFileSize 404 不存在；file_url 2017 移除 | S12 | 已复验（基线 captain 换源复核） |
| 12 | 桩函数不是真实阻塞：1.x QTest 用桩替换 QMessageBox 导致断言时序被桩改变，测出的是桩的行为 | A12 / T2 | 机制照搬（UIA 弹窗点击替代打桩） |
| 13 | WPF 七坑（Dispatcher 死锁 P1、跨线程互等 P2、绑定泄漏 P3、虚拟化失控 P4、MergedDictionaries P5、DPI P6、闪退 P7） | A1-A5 | 机制照搬（wpf_stack §6 全部有社区实证出处） |
| 14 | HostedService 异常会杀整个 Host：worker 内全包 catch | §3.3.2 | 机制照搬 |
| 15 | 端点可达性矩阵 + HttpClient 不读系统代理 | S4 / S5 | 机制照搬 |
| 16 | IDM 内核机制：动态分段 in-half division、连接复用、默认 8 连接 + 每主机例外表、重叠字节校验、状态随文件、链接失效重解析、速度/ETA 公式、调度器级并发 | §3.3 providers/segments | ⚠️ 连接数/重叠字节/超时/刷新节流待标定 |
| 17 | DepotDownloader/SteamKit：CDNClientPool round-robin 加权、chunk 并发默认 8、chunk SHA 校验、isUgc 路径、-pubfile/-ugc 区分 | §3.2 CDN / C6 | ⚠️ 并发上限待标定 |
| 18 | PCL2 列表不用 VSP：像素滚动 + 惰性实例化 + 卡片折叠 | A2 路线 A 裁决（下） | 数值待视觉规格标定 |

**arch-owner 裁决（pcl2_xaml_patterns §4.3 提交项）**：工坊浏览/下载列表/库管理三主场景采用**路线 A**（`VirtualizingStackPanel` Recycling + `ScrollUnit="Pixel"` + 模板），理由：数据量已知可上千、WPF 原生维护成本最低；惯性滚轮（SmoothScrollViewer 300ms 缓动）作为增量体验叠加；**路线 B**（PCL2 惰性实例化）不采用为架构基线，仅卡片折叠交互（独立于虚拟化）保留 PCL2 语序（折叠卡片展开时才实例化子控件）。此裁决同时满足性能与 FlaUI 可测性（虚拟化回收项仍暴露 UIA 树，惰性实例化的占位元素对 UIA 不友好）。

---

## 5. 跨模块契约要点

### 5.1 事件流

```
[Steam 域] 端点状态变更 ──► IConnectivityState.Changed ──► App 状态栏 VM
[Downloads 域] 下载事件 ──► IDownloadEventBus (IObservable) ──► App 下载页 VM（UI 线程节流订阅）
[App] 用户操作 ──► IDownloadQueue / ISteamWebApiClient（命令，异步 + CT）
```
- 跨层事件一律 `IObservable<T>`/`event` + 不可变事件负载；UI 订阅用 `WeakEventManager` 或 ViewModel Dispose 时退订（A1）。
- 错误横幅：域层 Result/Error → App `ErrorReporter` → Snackbar/对话框（用户可读文案 + 日志关联号）。

### 5.2 凭据流

```
UI 收码框 ──► SteamCmdLogin(ReadOnlyMemory<char>) ──► ICredentialStore（DPAPI 落盘）+ ISteamCmdRunner（内存用完即清）
日志/异常消息 ──► 脱敏 sink 包装器（强制覆盖账号/密码/验证码）
```

### 5.3 配置流

- `appsettings.json` + 用户设置（`PathOptions`/`SteamOptions.ProxyMode` 等）→ `IOptionsMonitor<T>`；变更回调 → 下载域/网络域热更新（并发数、限速、代理切换即时生效）。
- 代理切换：ProxyMode 变更 → `IConnectivityState` 重新探测 → 状态栏与端点可用性即时更新（不重启进程）。

### 5.4 版本与发布流

- 构建时版本注入（Directory.Build.props + ThisAssembly）→ 程序 Assembly + Velopack 包 + GitHub Release 三处同源（C4）。
- Velopack 1.2.161：`VelopackApp.Build().Run()` 在自定义 Main 最开头；`UpdateManager` 检查/下载/应用重启；`vpk pack` 生成安装+更新+增量包；GitHub Releases 托管（D6）。

---

## 6. 开发任务 DAG（终版 v2.3 · t5 讨论组定稿 + captain 认可）

> **变更日志（v1.0 → v2.0）**：
> - **阶段 0 压缩**：D0.1（WPF-UI 试装页）/ D0.3（FlaUI 冒烟链）的验证内容已由 **t4 spike 5/5 实证覆盖**（附录 SP），仅保留 D0.2 骨架接线；
> - **FlaUI 锁 5.0.0**（NuGet flatcontainer 三包实证最新；"6.0.0"系误读已撤回）；包清单按 t3 测试规格 §2.1；
> - **A7 修正 / A8b** 入各验收判据（AutomationId 只设可靠载体；WPF-UI API 首用前反射实测）；
> - **输入路径三规则**入 UiTests 契约（CJK→Enter；含空格/标点 ASCII→Ctrl+V；真实按键前先物理点击获焦点）；
> - **重标定任务采用 t3 §5 可执行基准**（D2.6=B1+B2 退避/节流曲线；D4.8=B3 并发上限）。
> - **v2.1（评审 patch · captain）**：①D6.3 未签名 SmartScreen 告知 = 首次运行内置 Hint 提示卡（用户可关闭且不再弹；留"取得代码签名证书即移除"活口；增量包不受体积约束，决策 10）；②**D7 循环条款**：终审（D7.3）产出修改项 → 回 D7.1 全量回归且**复测轮次归零重计**，直至"两轮干净复测 + 讨论组一致"同时成立才 D7.4（与 1.4.x 交付双条件一致）；③D3.7→D5.10 明确为**渐进式**（D3.7 先行下载主旅程冒烟，D5.10 扩为五主旅程）。
> - **v2.2（评审 patch · visual-20）**：①D5.1/2/11 acceptance 精确化（指向 t2 §2.1-2.7 组件验收判据小节+§5 数值对照表 22 行+§4 六清单；D5.11 补 modlens 读图二次校验）；②**D5.12 并入 D5.10**（A9 即时反馈计时断言挂 P0 真实旅程，产出仍入 calibration_2.md）；③**D5.3 WM_NCHITTEST 降级为 fallback 条款**（chrome 走 WPF-UI FluentWindow+TitleBar+WindowChrome ResizeBorderThickness=8；标题栏皮肤渐变+图标钮自绘保留）；④**D5.4-5.9 每页追加页面级 1 条 FlaUI 冒烟**（Smoke 层 = t3 §4.2 矩阵 P0 子集，把 D5.10 首次全量风险前移消化，SP-2 先点击获焦点顺序契约早暴露）。
> - **v2.3（评审 patch · qa-20）**：①D2.6/D4.8 acceptance 明确引用 t3 §5.5 输出格式（csv/md/json 三件+与旧值差异说明，arch 锁 Options 时有可核验落盘凭证）；②D4.8 inScope 补 `swdm2/tests/Swdm2.UiTests/Calibration/`（与 D2.6 口径统一）；③D4.1 acceptance 追加 Steam Guard 收码弹窗 FlaUI 断言（2FA 弹窗真实键盘输入验证码+模态阻塞断言，#23 场景不再悬空）；④D7.2/D6.4 **不合并**（D6.4=结构覆盖矩阵，D7.2=时间维度双轮稳定性=交付双条件的法定项），D7.2 第二轮直接复用 D6.4 矩阵执行表。t3 侧 M1/M5（输入三规则/A7 载体段/SP-3 双通道/§7.2 映射同步）qa-20 已自办 v1.1 补丁。
>
> **阶段 5 补充（P4）**：D5.4-D5.9 每页验收追加"页面级 1 条 FlaUI 冒烟通过"（冒烟内容=该页主交互，如联想命中/筛选生效/依赖渲染/队列入队/参数保存/代理切换）。

**规则**：每阶段 = 一次可交付迭代，交付时必须满足迭代四要素（全量回归 + 讨论组评审 + 版本号 + 变更记录）；阶段内任务并行/串行以依赖为准；本节经 t5 讨论组终裁 + captain 认可后即**开发任务开放清单**（计划先行纪律的放行门）。
**任务 ID**：D<阶段>.<序号>；**owner**：A=arch-20（Core/Downloads/架构）、V=visual-20（App 自绘/主题）、Q=qa-20（UiTests/复测）、C=captain（集成/构建/交付）。
**通用验证命令**（所有任务）：`dotnet build swdm2/Swdm2.sln -c Debug -warnaserror`（0 警告 0 错误，基线决策 2）+ 涉 UI 任务追加 `dotnet test swdm2/tests/Swdm2.UiTests`（普通交互桌面）或驱动模式（本沙箱内，见 SP-3）。

---

### 阶段 0 · 骨架接线（t4 spike 已实证基础上的唯一收尾任务）

> **已实证覆盖**（spike 冒烟 5/5，不重开任务）：D0.1 WPF-UI 4.3.0 试装页（FluentWindow/TitleBar/控件/自绘 Card + 主题三字典共存）；D0.3 FlaUI 5.0.0 进程外真实输入冒烟链（含截图/读图链路）。残留: 唯一接线任务。

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D0.2 (A/C) | 骨架接线补齐 | Downloads→Steam ProjectReference；产品 UiTests 引 t3 §2.1 包清单（FlaUI 5.0.0 + xunit + Xunit.StaFact）；App 侧空白窗口 + AutomationId（MainWindow）最小骨架 | build 0 警告 0 错误；UiTests 能 Application.Launch 产品 exe 并断言主窗口 | `dotnet build swdm2/Swdm2.sln -warnaserror` + UiTests 冒烟（SP-3 驱动模式或桌面 `dotnet test`） | swdm2/src/Swdm2.Downloads/Swdm2.Downloads.csproj, swdm2/tests/Swdm2.UiTests/*, swdm2/src/Swdm2.App/* |

---

### 阶段 1 · Core 域契约（可交付：领域语言 + 配置/路径/凭据/缓存基础设施 + 单元测试；版本 0.1.0）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D1.1 (A) | 领域模型与结果模型 | record 领域类型（WorkshopItem/Game/AppId/PublishedFileId/UgcId/DownloadTask…）+ Result<T,TErr> + 错误枚举 | 类型不可变；UgcId 与 PublishedFileId 不互换（编译期）；单测覆盖 | `dotnet test`（Core 单测） | swdm2/src/Swdm2.Core/Domain/, Results/ |
| D1.2 (A) | 路径服务 | IPathService：便携/安装双模式；WorkshopContent 布局；暂存区；日志目录 | 便携=exe 同级、安装=%APPDATA%；路径绝对化；切换模式测试绿 | `dotnet test` | swdm2/src/Swdm2.Core/Paths/ |
| D1.3 (A) | 配置与选项骨架 | appsettings.json + SteamOptions/DownloadOptions/PathOptions；IOptionsMonitor 订阅 | 强类型绑定；热更新回调触发测试绿 | `dotnet test` | swdm2/src/Swdm2.Core/Options/, swdm2/src/Swdm2.App/appsettings.json |
| D1.4 (A) | 凭据存储（DPAPI） | ICredentialStore：ProtectedData.CurrentUser；删除/读取/不存在分支 | 明文不落盘；日志不含明文（脱敏 sink D1.5 联合断言） | `dotnet test` | swdm2/src/Swdm2.Core/Credentials/ |
| D1.5 (A) | 日志契约与脱敏 sink | Serilog 接桥 + 脱敏 wrapping sink（账号/密码/验证码→***） | 注入敏感串→日志无明文 | `dotnet test` | swdm2/src/Swdm2.Core/Logging/, swdm2/src/Swdm2.App/ |
| D1.6 (A) | 缓存抽象 | IAsyncCache（single-flight + 深拷贝出口） | 命中后修改返回对象不影响缓存（1.x api_cache 学费断言） | `dotnet test` | swdm2/src/Swdm2.Core/Caching/ |
| D1.7 (C) | 阶段 1 交付门 | 全量回归 + 讨论组评审 + 版本 0.1.0 + 变更记录 | 四要素齐 | `dotnet test swdm2/Swdm2.sln` | docs/， CHANGELOG |

---

### 阶段 2 · Steam 域：探测/Web API/社区回退（可交付：元数据查询 + 状态栏真实可达性；版本 0.2.0）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D2.1 (A) | HttpClient 工厂与代理显式接管 | ProxyMode 三态注入 SocketsHttpHandler；指纹头四件套默认；MaxConnectionsPerServer 参数化 | 切换 ProxyMode 行为变化可测；请求头断言 | `dotnet test` | swdm2/src/Swdm2.Steam/Web/ |
| D2.2 (A) | 端点可达性探测 | IEndpointProbe：api/store/community 三端点轻探 + IConnectivityState 事件 | 探测三态+事件触发；双网络环境（fake-IP/直连）各记录一组 | `dotnet test` + 手工矩阵 | swdm2/src/Swdm2.Steam/Connectivity/ |
| D2.3 (A) | Web API 客户端 | GetPublishedFileDetails（含 batch）/ GetCollectionDetails / storesearch | 真实在线 id 3808352517 集成测试 result:1+字段非空（可 -skip 无网）；失败映射 SteamError | `dotnet test --filter Category=Online` | swdm2/src/Swdm2.Steam/Web/ |
| D2.4 (A) | 节流器与熔断器 | IThrottler（差异化间隔+全程锁）+ ICircuitBreaker（连续失败/连接级/冷却/半开） | 并发间隔符合配置；熔断开态抛 CircuitOpen；半开重置 | `dotnet test`（假钟） | swdm2/src/Swdm2.Steam/Resilience/ |
| D2.5 (A) | 社区页面回退 | Browse 列表 + 详情富化（仅 Community 可达时调用） | 离线 fixture 解析正确；不可达不调用（S4）；缓存命中深拷贝 | `dotnet test` | swdm2/src/Swdm2.Steam/Community/ |
| D2.6 (A/Q) | ⚠️重标定 B1+B2（t3 §5.1/§5.2 可执行骨架，输出按 t3 §5.5 格式 csv/md/json+旧值差异） | B1 429 退避曲线（候选 5-90s，三段法继承 1.x 脚本，档间冷却 120s，n≥3）；B2 端点最小安全间隔（裁决 1.x 详情 3s vs 6s 分歧，候选 0.5-8s×20 请求）；先问"能否更短/能否更小" | 基准报告 swdm2/docs/calibration_1.md（t3 §5.5 输出格式：csv/md/json 三件+与旧值差异说明）；Options 默认值按实测锁定或标注继续待定 | `dotnet test --filter Category=Calibration`（裸 HttpClient） | swdm2/docs/, swdm2/tests/（公共基准） |
| D2.7 (C) | 阶段 2 交付门 | 四要素（版本 0.2.0） | 同上 | 全量 | docs/， CHANGELOG |

---

### 阶段 3 · Downloads 域骨架 + steamcmd provider（可交付：真实下载一个匿名可用 mod，端到端；版本 0.3.0）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D3.1 (A) | 状态机与队列 | DownloadTask 状态机（转移表断言）+ IDownloadQueue + Channel 单消费者 worker + 调度器级并发 | 非法转移抛异常可测；入队自动进队列；并发槽配置控制 | `dotnet test` | swdm2/src/Swdm2.Downloads/Queue/ |
| D3.2 (A) | 事件总线与进度聚合 | IDownloadEventBus + EMA/平均速度/ETA + UI 节流刷新 | 高频回调不击穿节流；事件负载不可变 | `dotnet test` | swdm2/src/Swdm2.Downloads/Events/ |
| D3.3 (A) | steamcmd 部署 | ISteamCmdDeployer：zip 下载+解压+exe 校验 | 幂等；损坏 zip 重下 | `dotnet test`（离线 fixture） | swdm2/src/Swdm2.Steam/SteamCmd/ |
| D3.4 (A) | steamcmd runner | 批拼命令+1.x 正则表+成功三元判定+Sweep 校验+失败删空目录+stdin 关闭+三段式收尾+看门狗+输出脱敏 | 真实下载匿名 mod（sub 17906 内 app）成功且产物递归非空；0 字节假成功被拒；kill 后无僵尸进程 | `dotnet test --filter Category=Online` + 产物目录断言 | swdm2/src/Swdm2.Steam/SteamCmd/ |
| D3.5 (A) | SteamCmdProvider 接入链 | IDownloadProvider 实现：进程级信号量；进度=stdout 行+磁盘增长估算；分段数 N/A 诚实降级 | 队列驱动下载真实 mod 成功；暂停/取消杀进程干净 | `dotnet test --filter Category=Online` | swdm2/src/Swdm2.Downloads/Providers/ |
| D3.6 (A) | 串行化与句柄纪律 | 进程级 SemaphoreSlim + 局部变量保存进程句柄 | 并发两任务请求 steamcmd→第二个等待（不覆盖句柄、不 NRE） | `dotnet test`（双任务时序断言） | swdm2/src/Swdm2.Steam/SteamCmd/ |
| D3.7 (Q) | UiTests P0 冒烟：下载主旅程 | FlaUI 真实输入：入队→等待完成→断言状态与产物计数（弹窗 #255 路径） | FlaUI 绿；失败截图+读图校验 | UiTests（SP-3 驱动/桌面两通道） | swdm2/tests/Swdm2.UiTests/ |
| D3.8 (C) | 阶段 3 交付门 | 四要素（版本 0.3.0） | 同上 | 全量 | docs/， CHANGELOG |

---

### 阶段 4 · SteamKit CDN 主 provider + 分段续传 + 限速（可交付：真并行 IDM 体感；版本 0.4.0）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D4.1 (A) | SteamKit2 会话 | ISteamSessionManager：匿名/账号登录 + 2FA 回调链路（App 弹窗收码，A11） | 匿名会话建立；401 映射 AuthRequired；**Steam Guard 收码弹窗 FlaUI 断言**（2FA 弹窗真实键盘输入验证码+模态阻塞断言，#23 场景） | `dotnet test --filter Category=Online` | swdm2/src/Swdm2.Steam/Cdn/ |
| D4.2 (A) | manifest 解析与 isUgc 路径 | ResolveUgcManifestAsync（pubfile→PICS→manifest） | 真实 pubfile 解析出文件/chunk 列表；-pubfile/-ugc 区别在 UI 提示文案 | `dotnet test --filter Category=Online` | swdm2/src/Swdm2.Steam/Cdn/ |
| D4.3 (A) | chunk 并行下载 + SHA 校验 | DownloadChunksAsync + 并发上限注入 + chunk SHA 强校验 | 并行度按 Options 真实生效；损坏 chunk→InvalidChecksum 重下 | `dotnet test --filter Category=Online` | swdm2/src/Swdm2.Steam/Cdn/, swdm2/src/Swdm2.Downloads/Providers/ |
| D4.4 (A) | SteamKitCdnProvider + 链回退 | provider 链路由：SteamKit 主→steamcmd 兜底（按错误类型路由） | 注入故障 provider→自动回退 steamcmd 成功；UI 提示 provider 已切换 | `dotnet test`（注入故障） | swdm2/src/Swdm2.Downloads/Providers/ |
| D4.5 (A) | HTTP 直链分段 provider | in-half division 动态分段 + Range 探测 + 200-not-206 回退单流 + 重叠字节比对 + `.download` 尾部元数据续传 + 来源页参数持久化 | 本地 Kestrel fixture 分段下载绿；kill 后续传成功且拼接点校验过；不支持 Range 时回退 | `dotnet test`（本地 Kestrel fixture） | swdm2/src/Swdm2.Downloads/Segments/, Providers/ |
| D4.6 (A) | 磁盘 IO：偏移直写 + 稀疏占位 | ISparseFileAllocator（FSCTL_SET_SPARSE+容量检查降级+不可逆警告） | 偏移写入无拼接；exFAT 降级 SetLength；稀疏只用于下载期文件 | `dotnet test` | swdm2/src/Swdm2.Downloads/Disk/ |
| D4.7 (A) | 限速器 | 令牌桶（chunk 调度+HTTP 双点） | 限速后实测带宽≤配置×(1+10%) | `dotnet test` | swdm2/src/Swdm2.Downloads/Limiter/ |
| D4.8 (A/Q) | ⚠️重标定 B3（t3 §5.3） | 并发上限：元数据并发对真 API；分段并发强制本地 Kestrel fixture（禁公网）；增益≥10% 最大档为默认，错误率<2% 门槛；先问"能否更大/能否更小" | 基准报告 calibration_2.md（t3 §5.5 输出格式）；MaxChunkParallelism/ChunkTimeoutMs/OverlapBytes/MaxConnectionsPerServer 锁定 | `dotnet test --filter Category=Calibration` | swdm2/docs/, swdm2/tests/Swdm2.UiTests/Calibration/ |
| D4.9 (Q) | UiTests：分段体感断言 | 下载行分段数/速度/ETA 真实刷新；暂停/继续按钮态（状态机驱动） | FlaUI 真实点击绿 | UiTests | swdm2/tests/Swdm2.UiTests/ |
| D4.10 (C) | 阶段 4 交付门 | 四要素（版本 0.4.0） | 同上 | 全量 | docs/， CHANGELOG |

---

### 阶段 5 · App UI 主体：PCL2 视觉 + IDM 下载体感（可交付：完整可用的主界面；版本 0.5.0）

> 视觉数值/动画/令牌以 t2 `visual_system_2.0.md` 为准（行号级出处 + ⚠️[参数待重标定] 标记，D5.x 视觉验收联测锁定）；AutomationId 载体遵守 A7 修正（SP-2 可靠载体表）。

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D5.1 (V) | 主题系统 | Light/Dark/Accent/Common 四字典 + 单点合并（A3）+ swdm- 前缀 + Color/Brush 双资源律 | 切换"无闪烁"按 t2 §4 清单 6 可操作定义（切换前后截图除令牌映射外无变化 + 帧采样门）；换 Accent.xaml 即换皮；动画绑 Color 资源 | UiTests 截图断言（t2 §4 像素六清单） | swdm2/src/Swdm2.App/Ui/Themes/ |
| D5.2 (V) | 自绘控件层 | SwdmCard（三层+90ms 四路+阴影 0.07→0.4+150ms 高度+250ms 箭头+200ms 退出）/Hint/ModListItem/SmoothScrollViewer/AniHelper（命名轨道） | t2 §2.1-2.7 各组件**验收判据**小节逐条 + §5 数值对照表 22 行；A8b：WPF-UI API 用前反射实测 | 像素断言六清单（t2 §4）+ 组件验收判据 | swdm2/src/Swdm2.App/Ui/Controls/ |
| D5.3 (V) | 窗口 chrome 与导航 | chrome 走 WPF-UI FluentWindow+TitleBar + WindowChrome ResizeBorderThickness=8 覆盖缩放；**WM_NCHITTEST 降级为 fallback 条款**（若弃 WPF-UI TitleBar 时启用；标题栏皮肤渐变+图标钮始终自绘）；PageBase+容器替换+返回栈（110→30ms + stagger 25ms） | snap/DWM 阴影保留；返回栈语义测试；t2 §2.4 验收（条件化片段） | UiTests | swdm2/src/Swdm2.App/Ui/Pages/, Navigation/, Chrome/ |
| D5.4 (V) | 游戏选择页 | 联想搜索（原地更新+中英别名归一化）+即时反馈 | FlaUI 输入"饥荒"/"Don't Starve"双语命中；联想原地更新 | UiTests | swdm2/src/Swdm2.App/Ui/Pages/, ViewModels/ |
| D5.5 (V) | 工坊浏览页 | 分页/标签/排序/搜索/作者筛选 + 虚拟化路线 A（VSP Recycling+Pixel）+惯性滚轮 | 千项列表滚动流畅（帧计数）；A2 六不变量断言 | UiTests | swdm2/src/Swdm2.App/Ui/Pages/ |
| D5.6 (V) | mod 详情页 | 依赖/冲突/评论展示（Web API+社区回退渲染） | 依赖来自 API；社区字段缺失诚实降级显示 | UiTests | swdm2/src/Swdm2.App/Ui/Pages/ |
| D5.7 (V/A) | 下载页（IDM 体感） | 行级：文件名/大小/状态/ETA/速度/分段数/Q 列；按钮态随选中项；三档通知强度；类别树=游戏→目录 | 字段全部来自事件总线（steamcmd 场景分段数 N/A 诚实）；按钮态=状态机驱动 | UiTests | swdm2/src/Swdm2.App/Ui/Pages/Download/ |
| D5.8 (V) | 设置页 | 目录/账号（DPAPI 记住密码）/引擎参数（Options 全暴露+校验） | 参数变更热生效；密码不回显 | UiTests | swdm2/src/Swdm2.App/Ui/Pages/ |
| D5.9 (A) | 状态栏：端点可达性 | IConnectivityState→状态栏（直连/系统代理/自定义代理+三端点状态）；失败引导配代理 | 探测结果如实显示；切代理即时更新 | UiTests | swdm2/src/Swdm2.App/ |
| D5.10 (Q/V) | P0 冒烟 5 条主旅程（t3 §4.1）+ ⚠️即时反馈重标定（并入） | 启动→搜索→详情→下载→库 全量 FlaUI 真实输入（#255 弹窗路径+截图+OCR/像素校验）；A9 阈值 ≤150ms 实测=**计时断言挂 P0 真实旅程**（真实旅程比合成基准更贴用户体感），问"能否更短" | 全绿（输入三规则落实）；计时基准报告合入 calibration_2.md | UiTests（两通道）+ 计时断言 | swdm2/tests/Swdm2.UiTests/, swdm2/docs/ |
| D5.11 (V/C) | 视觉终检 + 交付门 | t2 §4 像素断言六清单（结构周期/令牌存在性/残留色 0/双主题/阴影抬升/无闪烁）逐项执行 + **modlens 读图二次校验**（SP-3 链路已实证）；四要素（版本 0.5.0） | 六清单+回归全绿；CHANGELOG | UiTests + 截图读图（含 modlens） | docs/ |

---

### 阶段 6 · 库管理 / 更新检查 / 打包发布（可交付：功能对等 1.x + 可安装更新；版本 0.6.0）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D6.1 (A) | mod 库管理 | 分类/导入导出/库扫描（原子认领 D10）；steamcmd 更新策略：时间戳 zip 备份后清除再下载（解决"不删已删文件"） | 备份/清除可回滚；库扫描不认领未完成任务产物 | `dotnet test` | swdm2/src/Swdm2.Downloads/Library（或 Core） |
| D6.2 (A) | mod 更新检查 | manifest/时间戳对比；标红+询问入队（弹窗真实阻塞，A12） | FlaUI：弹窗打开时标红态在弹窗内读取断言（1.x 桩函数学费的 C# 正解） | UiTests | 同上 + App |
| D6.3 (C) | Velopack 集成 | vpk pack + GitHub Releases；版本号同源（C4）；**未签名 SmartScreen 告知 = 首次运行内置 Hint 提示卡**（用户可关闭且不再弹；留"取得代码签名证书即移除"活口；增量包大小不受体积约束，决策 10） | 打包→安装→自动更新（~2s 无 UAC 重启）流程走通；首次启动提示卡出现一次并可关闭 | 手工 + `vpk pack` | swdm2/src/Swdm2.App/, installer 脚本 |
| D6.4 (Q) | 复测矩阵 | 双网络环境（fake-IP/直连）×匿名/账号×两 provider 全组合回归 | 矩阵结果记录；异常组合归档为已知限制 | 矩阵执行表 | docs/ |
| D6.5 (C) | 阶段 6 交付门 | 四要素（版本 0.6.0） | 同上 | 全量 | docs/， CHANGELOG |

---

### 阶段 7 · 发布冲刺（可交付：2.0.0 正式版）

| 任务 | subject | objective | acceptance | 验证命令 | inScope |
|---|---|---|---|---|---|
| D7.1 (Q) | 全量回归 | 所有功能+功能间关联交互（P0 主旅程+单元+集成+复测矩阵） | 全绿 | `dotnet test swdm2/Swdm2.sln`（全类别） | 全仓 |
| D7.2 (Q) | 双轮复测 | bug 复测员连续两轮复测无异常（第二轮直接复用 D6.4 矩阵执行表，不重设计） | 两轮报告 | 复测表 | docs/ |
| D7.3 (C) | 讨论组终审 | 删减/改进/添加评审（三原则：精简/用户体感/基本功能） | 一致通过纪要 | 评审会 | docs/ |
| D7.4 (C) | 发布 | 版本号 2.0.0+变更记录+Release+安装包 | 交付双条件（讨论组一致+双轮复测无异常） | `vpk pack` + GitHub Release | 全仓 |

**DAG 依赖图（关键路径 · v2.0，spike 已覆盖 D0.1/D0.3）**：
```
[t4 spike ✅ 已实证] ──► D0.2 ──► D1.1..D1.6 ──► D1.7
D1.* ──► D2.1 ──► D2.2 ──► D2.3 ──► D2.7                  （D2.4/D2.5 并行；D2.6=B1+B2 重标定）
D1.* ──► D3.1 ──► D3.2 ──► D3.5 ──► D3.8                  （D3.3/D3.4 可提前，D3.5 依赖 D3.4；D3.7 依赖 D3.5）
D3.5 ──► D4.1 ──► D4.2 ──► D4.3 ──► D4.4 ──► D4.10        （D4.5/D4.6/D4.7 并行；D4.8=B3 重标定；D4.4 依赖 D3.5）
D5.1/D5.2/D5.3 ──► D5.4..D5.9（每页含 1 条 Smoke）──► D5.10 ──► D5.11（D5.* 依赖 D2/D3 服务契约）
D5.11 ──► D6.1..D6.4 ──► D6.5 ──► D7.1 ──► D7.2 ──► D7.4
横切：D2.6/D4.8 = 重标定任务（经验复验纪律，t3 §5 基准）；D5.10（并入 A9 计时）= 即时反馈重标定
```

---

### 放行门（计划先行纪律的落地）

本 DAG 终版经 **t5 讨论组评审**（arch-20/visual-20/qa-20/captain 四方，三原则：精简/以用户体感为中心/保证基本功能正常运行）出具评审记录 `docs/process/review_2.0_plan.md`（含投票），**captain 认可后**即开放 D0-D7 开发任务。评审中提出的删减/改进以 patch 方式回写本节并标注版本（v2.1…）。
## 7. 纪律显式遵守（对用户四条硬纪律的落实）

1. **计划先行纪律**：本文档 = 开发前置门的一部分（架构契约/任务拆分/验收判据/验证方式四要素齐全）；t5 讨论组终裁 + captain 认可前，D1-D7 全部任务不开放；阶段 0 = t4 spike（骨架/环境准备豁免）。
2. **经验复验纪律**：§4 学费清单所有参数类条目标 ⚠️[参数待重标定]；DAG 显式排入重标定任务 D2.6（退避/节流）、D4.8（并发/超时/重叠字节）、D5.x 视觉标定（对接 t2/t3）；每处先问"能否缩短/能否更小"再实测采纳；参数集中走 Options，禁止硬编码，实测后锁定默认值并更新本规格。
3. **真实输入测试要求**：UiTests 契约（§3.5）= FlaUI 5.0.0 真实鼠标/键盘事件进程外驱动，AutomationId 选择器，显式等待，弹窗真实点击（#255 路径，禁打桩）；测试分层（单元=纯逻辑 / 集成=真实子系统 / UI=真实用户旅程）；CI 本机交互会话（#168）。
4. **迭代四要素**：每阶段交付门（D1.7/D2.7/…/D6.5/D7.4）强制：全量回归（含新增与关联交互）、讨论组评审（精简/用户体感/基本功能三原则）、版本号升级 + 可追溯变更记录、最终交付双条件（讨论组一致 + bug 复测员连续两轮无异常）。
5. **设计对照纪律**（基线 §五）：本规格每条结论对照基线 9 条决策（§1 表）；与基线冲突或超出的发现（列表路线 A 裁决、WPF-UI 主题真源二选一）已标注依据与复验状态（§8）；网络不稳导致的空结果一律不采信为"不可行"。

---

## 8. 对照基线结论（按 design_baseline_2.0.md §五 协议）

- **与基线一致的部分**：9 条锁定决策全部逐条映射（§1 表）；功能对等四组（游戏选择/浏览/详情/下载/库/设置/匿名）在 DAG 阶段 5-6 覆盖；增强项（PCL2 视觉、IDM 真体感、双 provider）与基线决策 8/9 一致。
- **与基线冲突/超出的发现**：
  - 裁决：**列表用虚拟化路线 A**（pcl2_xaml_patterns §4.3 提交项），超出基线当前未裁决项；裁决依据见 §4 末段（数据量 + FlaUI 可测性 + 维护成本）。
  - 裁决：**主题真源 = 自建字典**、WPF-UI 仅作控件基座（避免双主题状态），超出基线决策 9 的"底座"表述，与 pcl2 §8 的并存警告一致。
  - 补充：Downloads→Steam 引用补线（骨架现状差异，§0 末）。
- **弯路嫌疑（可能因网络不稳误读）**：WPF-UI 4.3.0 的 API 表面（FluentWindow/TitleBar/NavigationView 命名）取自 README 与稳定版惯例，未逐版核验 → **已由 t4 spike 复验并记录**（附录 SP-1：SymbolRegular 无 Regular 后缀、ui:Card 无 Header；实测手段=反射/包 XML 文档；A8b 契约化）。Web API 元数据主源结论经 captain 换源复验（真实 id 3808352517），采信。
- **采信/搁置/复验的决定**：
  - 采信：五份报告标注了出处的一手结论（34 次 429 实测、IDM 官方 FAQ、SteamKit/DepotDownloader 源码、PCL2 源码行号级数值、SCA 源码）。
  - 搁置：Nether/GGNetwork 第三方 provider（2.0 首版官方链路为主，符合精简原则）；PCL2 HSL 主题编辑器与镐子加载动画关键帧（低优先级债务）。
  - 已复验完成：D0.1/D0.3（t4 spike 5/5，附录 SP）；复验中：D2.6/D4.8（参数重标定，t3 §5 基准）+ D5.10 并入的 A9 即时反馈计时。
  - 参数分歧：1.x 节流口径不一（详情 3s vs 6s）→ 不采信任一旧值，D2.6 实测裁决（经验复验纪律的具体应用）。

---

## 9. 附录：关键参考速查

- 基线：`swdm2/docs/design_baseline_2.0.md`
- 研究：`docs/research2/wpf_stack.md`（栈选型 + 7 坑）、`wpf_ui_testing.md`（FlaUI 方案）、`idm_download_kernel.md`（IDM 内核 + C# 映射）、`csharp_steam_workshop.md`（steamcmd/SteamKit/Web API）、`pcl2_xaml_patterns.md`（可粘贴 XAML + 数值表）
- steamcmd 正则（1.x 移植，D3.4 直接引用）：
  - 成功：`Success\. Downloaded item (\d+) to "([^"]+)" \((\d+) bytes\)`
  - 失败：`ERROR! .*｜Failed to download item \d+.*｜Timeout .*｜Not Logged On.*`
  - 登录失败：`Login Failure｜Invalid Password｜Not Logged On｜[Rr]ate ?[Ll]imit`
  - Guard 提示：`THIS COMPUTER HAS NOT BEEN AUTHENTICATED｜CHECK YOUR EMAIL｜STEAM GUARD CODE:｜TWO-FACTOR AUTHENTICATION｜MOBILE AUTHENTICATOR`
- 请求头指纹（S1）：`User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 …` + `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8` + `X-Requested-With: XMLHttpRequest`（双保险）
- 端点清单：`api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/`（POST，匿名可用）·`/GetCollectionDetails/v1/`（POST）·`store.steampowered.com/api/storesearch/`（GET，匿名无 key）·~~GetFileSize~~（404 不存在，禁止引用）

---

> **门禁状态**：本文档 + t2 视觉规格 + t3 测试规格提交 captain；captain 对照基线 9 条核验一致性 → t5 讨论组终裁后开放 D0-D7 开发任务。

---

# 附录 SP · t4 基座实证 spike 补丁（2026-10-02，arch-20）

> 代码与证据：`swdm2/spike/SpikeWpf/`（被测试装页：WPF-UI 4.3.0 + 自绘 Card）+ `swdm2/spike/SpikeFlaUiTests/`（FlaUI 5.0.0 真实输入冒烟）+ `swdm2/spike/*/bin/.../spike_result.md`（5/5 PASS）+ `TestArtifacts/spike_tree.txt`（UIA 树 dump）+ `TestArtifacts/spike_screen_full.png`（读图链路证据）。spike 不进产品路径，结论补丁进本文。

## SP-1 · WPF-UI 4.3.0 在 net8.0-windows 可用性（Q1）✅ 有条件可用

- **包还原**：直连 api.nuget.org 200（2.1s）；`WPF-UI 4.3.0` restore 成功（冷启 42.8s），lib/net8.0-windows7.0，`Wpf.Ui.dll` 6.3MB；`xmlns="http://schemas.lepo.co/wpfui/2022/xaml"`（DLL 二进制扫描确认）。
- **初始化/主题**：`ui:ThemesDictionary Theme="Light"` + `ui:ControlsDictionary` + 自建 `swdm-` 前缀 ResourceDictionary 三者共存加载成功，build **0 警告 0 错误**，运行时 FluentWindow + TitleBar + Mica 背景正常（Windows 子系统）。
- **API 表面弯路（pcl2 §8 弯路嫌疑实锤）2 处**：
  1. `SymbolRegular` 枚举**无 Regular 后缀**：`"Apps24Regular"` 非法 → `XamlParseException → FormatException` **启动即崩溃**。正名 `Apps24`（反射 dump 9235 个枚举名佐证；4.3.0 包内同源核验 + captain main 分支源码核验）。⇒ 引擎规则：图标名一律以 `typeof(SymbolRegular).GetEnumNames()` 实测为准。
  2. `ui:Card` **无 `Header` 属性**（pcl2 §6.1 表假定存在；实际只有 `Footer`/`HasFooter`）⇒ 卡片标题自绘（本就是 PCL2 路线）。
- **结论 Q1**：可用，但 API 表面随版本漂移 → 契约 A8「锁版本 4.3.0 + 升级必过全量回归」不变，并**追加条目 A8b**：所有 WPF-UI API 名称首次使用前以反射/包内 XML 文档实测（图标/控件枚举类）。

## SP-2 · FlaUI 5.0.0 UIA3 可达性（Q2）✅ 高，有结构例外

实测 8/9 期望元素可达（唯一"缺失"为 Grid/ContentControl 容器本身——见下）：

| 元素类型 | 可达性 | 备注 |
|---|---|---|
| Window（AutomationId=MainWindow） | ✅ | 窗口级 id 完全暴露 |
| ui:Button / ui:TextBox(Edit) / ui:ListView(List) | ✅ | id + Name + ControlType 全 |
| 自绘 UserControl（SwdmCard） | ✅ type=Custom | **id 完全暴露，内容控件可达** |
| 自绘卡片内容 Button（SpikeCardButton） | ⚠️ | **无 ClickablePoint**（NoClickablePointException）→ 退到包围矩形中心点击（wpf_ui_testing §1.4 教训实证） |
| ui:TitleBar / ui:Card / Grid / ContentControl | ❌ | **UIA 树提升（hoisting）**：容器自身不在树中，其内容直接挂在窗口下；XAML 上设的 AutomationId 被"吞" |

- **契约 A7 修正（强制）**：AutomationId 只设在**可靠载体**上 = Window / 内容控件（Button·TextBox·ListBox·UserControl）/ WPF-UI 模板部件固定 id（如 `TitleBarMinimizeButton/MaximizeButton/CloseButton`）。**禁止**把测试锚点压在 `ui:TitleBar`、`ui:Card`、`Grid`、`ContentControl` 等 UIA 提升型容器上。
- **输入路径实测**：
  - ValuePattern `Enter("饥荒")` CJK 完美（断言值真进控件）✅
  - `Enter()` 对 ASCII **空格/撇号会被吞**（实测 `"Don't Starve"` → `"Don'tStarve"`）⇒ t3 输入规则补丁：CJK 走 Enter；含空格/标点的 ASCII 词走**剪贴板 Ctrl+V 真实路径**或用纯字母词。
  - 真实回车 `Keyboard.Press/Release(RETURN)` 能触发 TextBox 的 PreviewKeyDown 处理器（真实键盘事件生效），但需要先行**真实点击使窗口/控件获得焦点**（程序化 `Focus()`/`SetForeground()` 不可靠——Windows 前台锁定）⇒ 测试顺序契约：先物理点击 → 再注入按键。

## SP-3 · 截图 + 读图链路（Q3）✅ 完全可用

- `Capture.Element(list)` 138.7KB + `Capture.MainScreen()` 1443KB PNG 落盘成功；`read_image`（modlens 桥）**完整转写中文 UI**（搜索框 CaveStory、列表项、卡片文案、弹窗正文与"确定"按钮全可读；仅截断处标注 uncertain）。
- ⇒ 记忆中"读图工具本机全不可用"已**被 spike 推翻**（标 superseded）：视觉 bug 仲裁链（UIA 断言 → 截图 → OCR/像素 diff）对 WPF 进程成立，基线决策 5 落实。
- **xUnit 运行器基础设施发现（重要，输入 t3 执行方案）**：本机 harness 沙箱内 **`dotnet test` 的 testhost 启动即崩**（`SetParentProcessExitCallback` → `Win32Exception(5)` 拒绝跨进程句柄；Microsoft.NET.Test.Sdk 17.8/17.13 同崩，x64/AnyCPU 同崩）。spike 期间改用**控制台驱动反射执行同一批 [WpfFact] 方法**（`dotnet run`，真实输入链路完全一致；UseWPF=true 的 Exe 无控制台 → 输出落盘 `spike_result.md`）。⇒ 产品回归在普通交互桌面环境用 `dotnet test`（t3 契约不变），CI 环境需自托管 runner + 交互会话（基线决策 6）；本沙箱内临时回归用驱动模式。

## SP-4 · 裁决：混合策略（Q4）——WPF-UI 基座 + 签名级自绘（不全量基座、不全自建）

**与 t1 §3.4 裁决一致并双重加固**：
1. **窗口 chrome / 基础控件 = WPF-UI 4.3.0**（FluentWindow/TitleBar/Button/TextBox/ListView……实测可用且 UIA 友好）。
2. **签名级观感 = 自绘 UserControl**（SwdmCard/Hint/ListItem）：PCL2 三层结构 + 90ms 阴影动画实测渲染且 **UIA 天然暴露 id（Custom）**——比 WPF-UI Card 更可测（Card 不可达 + 无 Header）。
3. **依据的实证增量**：WPF-UI 的结构性控件（TitleBar/Card）API 和 UIA 表面都有版本漂移/提升现象 → 把"脸面 + 可测性敏感"的控件自绘，恰好自绘控件的 UIA 表现反而更可靠——**自绘不只为了脸，也为了测试纪律**。
4. 这与基线决策 9（WPF-UI 底座 + 自绘 Card）与 pcl2 §6 结论（模块 1/2/3/5 免写，4/6/7/8/9/10 自绘）完全对齐，spike 提供了实测支撑与 A7/A8 契约修正。

## SP-5 · 落账清单

- A7 修正（§3.4）：AutomationId 可靠载体表 + 顺序契约（先点击获得焦点再注入按键）→ 见 SP-2。
- A8 追加 A8b：WPF-UI API 名首次使用前反射实测（图标/枚举优先）。
- A9 不变（即时反馈阈值实测）；t2/t3 视觉与测试规格按本附录更新输入路径与载体规则。
- 基线决策 3 已由 captain 改 FlaUI 5.0.0（NuGet flatcontainer 三包实证：6.0.0 不存在）——本文 FlaUI 引用已同步全量改 5.0.0。
- D0.1/D0.3（阶段 0 spike 任务）实际已由 t4 完成其验证内容：WPF-UI 试装页面 + FlaUI 冒烟链 + 截图链路 + 结论回写。t5 DAG 定稿时阶段 0 可压缩为接线任务（D0.2 补 Downloads→Steam 引用 + 产品 UiTests 引入 FlaUI 5.0.0 包）。

---

> **门禁状态（更新）**：t1 规格（含本 spike 补丁）+ t2 视觉规格 + t3 测试规格 → captain 核验 → t5 讨论组终裁后开放 D0-D7。
