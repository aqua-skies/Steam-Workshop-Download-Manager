using Microsoft.Extensions.Configuration;
using Swdm2.App.Community;
using Swdm2.App.Configuration;
using Swdm2.App.Connectivity;
using Swdm2.App.Navigation;
using Swdm2.App.Session;
using Swdm2.App.ViewModels;
using Swdm2.Core.Logging;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Limiter;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Cdn;
using Swdm2.Steam.Community;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
using Swdm2.Steam.Workshop;
using SteamKit2;

namespace Swdm2.App.Boot;

/// <summary>
/// App 装配根（D3.5b 最小可测骨架）：
/// 手工组装下载链（无 DI 容器依赖；D5 正式 UI 切 Generic Host + CommunityToolkit.Mvvm 时重构）：
/// PathService.Detect → SConfiguration → IHttpClientFactory/ICircuitBreaker（指纹头+熔断）
/// → SteamCmdDeployer/Runner → DownloadEventBus(ProgressThrottleMs) → SteamCmdProvider
/// → DownloadQueue + DownloadScheduler(queue, provider.ExecuteAsync) ——arch-20 留好的对齐装配点。
/// 启动=空转等入队；沙箱/不可达环境下下载会真实走 Failed（状态回显=可断言，不造假；t28 桌面绿灯）。
/// </summary>
public static class AppHost
{
    private static DownloadQueue? _queue;
    private static DownloadScheduler? _scheduler;
    private static DownloadEventBus? _bus;
    private static MainShellViewModel? _shell;
    private static SteamKitSessionManager? _session;
    private static PageNavigationService? _navigation;
private static ConnectivityStateService? _connectivity;

    /// <summary>会话管理器（D4.1;#23 FlaUI 旅程与登录链入口）。</summary>
    public static SteamKitSessionManager Session
        => _session ?? throw new InvalidOperationException("AppHost 未启动（先调 Start()）。");

    public static MainShellViewModel Shell
        => _shell ?? throw new InvalidOperationException("AppHost 未启动（先调 Start()）。");

    /// <summary>页面导航服务（D5.3:返回栈+110→30ms 切页时序；MainWindow 构造时 Attach 页面容器）。</summary>
    /// <summary>D5.9 连接状态服务（状态栏数据源+代理切换）。</summary>
    public static ConnectivityStateService Connectivity
        => _connectivity ?? throw new InvalidOperationException("AppHost 未启动（先调 Start())");

    public static PageNavigationService Navigation
        => _navigation ?? throw new InvalidOperationException("AppHost 未启动（先调 Start()）。");

    /// <summary>HTTP 工厂（D5.20c:设置页默认游戏搜索 storesearch 复用同指纹通道）。</summary>
    public static SteamHttpClientFactory HttpFactory
        => _httpFactory ?? throw new InvalidOperationException("AppHost 未启动（先调 Start())");
    private static SteamHttpClientFactory? _httpFactory;

    public static void Start()
    {
        var config = SwdmConfiguration.LoadConfiguration();
        var steam = config.GetSection("Steam").Get<SteamOptions>() ?? new SteamOptions();
        var download = config.GetSection("Download").Get<DownloadOptions>() ?? new DownloadOptions();

        var paths = PathService.Detect();
        paths.EnsureDirectories();

        var redaction = new RegexRedactionPolicy();
        var httpFactory = new SteamHttpClientFactory(steam);
        _httpFactory = httpFactory;
        // D5.9(状态栏端点可达性）：IConnectivityState 数据源+代理切换（S5 工厂快照语义→切代理重建）
        _connectivity = new ConnectivityStateService(steam);
        _ = Task.Run(async () => await _connectivity.RefreshAsync().ConfigureAwait(false)); // 启动后首探（异步不阻塞壳）
        var breaker = new CircuitBreaker(SystemTimeProvider.Instance,
            steam.CircuitThreshold, steam.CircuitCooldownMs);
        var deployer = new SteamCmdDeployer(paths, httpFactory, new SteamCmdProcessProbe(),
            breaker: breaker);
        var runner = new SteamCmdRunner(redaction);

        var bus = new DownloadEventBus(Math.Max(1, download.ProgressThrottleMs));
        // D4.7 限速器（令牌桶；0=不限速默认；chunk 调度+HTTP 双点消费）
        var limiter = new TokenBucketSpeedLimiter(download.MaxSpeedBytesPerSecond);
        // D4.4 provider 链路由：SteamKit CDN 主→steamcmd 兜底（按错误类型路由）
        var steamCmd = new SteamCmdProvider(deployer, runner, bus, breaker);
        var cdnSession = new SteamKitSessionManager(timeoutSeconds: 10); // 沙箱短超时：CM 阻断→Network 快回退链
        var cdnClient = new SteamKitCdnClient(cdnSession, timeoutSeconds: download.ChunkTimeoutMs / 1000, // D4.8 锁定：Options→chunk 超时
            chunkParallelism: download.MaxChunkParallelism);
        var cdnProvider = new SteamKitCdnProvider(cdnSession, cdnClient, bus, limiter: limiter);
        var provider = new DownloadProviderRouter(cdnProvider, steamCmd, bus);
        var queue = new DownloadQueue();
        var maxConcurrent = Math.Max(1, download.MaxConcurrentDownloads);
        var scheduler = new DownloadScheduler(queue, provider.ExecuteAsync, maxConcurrent);

        // D4.1:SteamKit 会话 + App 收码弹窗（A11)。SWDM2_TEST_2FA=1 环境容忍门=桩登录
        // （首次 AccountLogonDenied→弹窗收码→任意码 OK)，仅 #23 FlaUI 旅程触发；否则真链。
        var prompter = new WpfSteamGuardPrompter();
        var test2Fa = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("SWDM2_TEST_2FA"));
        _session = new SteamKitSessionManager(prompter,
            logOnOverride: test2Fa ? TestGuardLogOnStub : null);

        _bus = bus;
        _queue = queue;
        _scheduler = scheduler;
        _navigation = new PageNavigationService();

        // D5.6: 详情页元数据链（Web API 主源+D2.5 社区回退+评论源共享 community-detail
        // 节流桶；装配真实源后详情页 LoadDetailAsync 按需加载，失败=VM 错误态不造假）
        var apiClient = new SteamWebApiClient(httpFactory);
        var communitySource = new CommunityPageSource(httpFactory);
        var commentSource = new CommunityCommentSource(httpFactory);

        // D6.2(t59): 库页更新检查真实源=批量 GetPublishedFileDetails 链（指纹头+
        // Api 节流桶+熔断全在 apiClient 内）；角标/Hint 不阻塞主线程；入队询问才下载
        var updateSource = new WorkshopUpdateChecker(apiClient);

        _shell = new MainShellViewModel(paths, queue, provider, scheduler, bus,
            _connectivity, apiClient, communitySource, commentSource, updateSource);

        if (test2Fa)
        {
            // 后台触发账号登录 → 桩首次拒认证 → 弹窗（#23 真实输入断言入口）
            _ = Task.Run(async () => await _session.LoginAsync(
                new SteamSessionLogin("test2fa", "pw", null)).ConfigureAwait(false));
        }
    }

    /// <summary>#23 测试桩：首次 AccountLogonDenied（触发收码弹窗），收码后任意 5 位码 OK。</summary>
    private static async Task<(EResult Result, ulong SteamId)> TestGuardLogOnStub(
        SteamSessionLogin login, CancellationToken ct)
    {
        await Task.Delay(100, ct).ConfigureAwait(false); // 让主窗口先显示
        return string.IsNullOrEmpty(login.GuardCode)
            ? (EResult.AccountLogonDenied, 0UL)
            : (EResult.OK, 76561198000000042UL);
    }

    /// <summary>进程退出释放（队列/总线/会话异步 Dispose）。</summary>
    public static async Task StopAsync()
    {
        if (_scheduler is not null) await _scheduler.DisposeAsync().ConfigureAwait(false);
        if (_queue is not null) await _queue.DisposeAsync().ConfigureAwait(false);
        if (_bus is not null) await _bus.DisposeAsync().ConfigureAwait(false);
        _shell?.Dispose();
        _connectivity?.Dispose();
    }
}
