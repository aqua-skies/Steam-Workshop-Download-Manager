using Microsoft.Extensions.Configuration;
using Swdm2.App.Configuration;
using Swdm2.App.Session;
using Swdm2.App.ViewModels;
using Swdm2.Core.Logging;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Cdn;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
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

    /// <summary>会话管理器（D4.1;#23 FlaUI 旅程与登录链入口）。</summary>
    public static SteamKitSessionManager Session
        => _session ?? throw new InvalidOperationException("AppHost 未启动（先调 Start()）。");

    public static MainShellViewModel Shell
        => _shell ?? throw new InvalidOperationException("AppHost 未启动（先调 Start()）。");

    public static void Start()
    {
        var config = SwdmConfiguration.LoadConfiguration();
        var steam = config.GetSection("Steam").Get<SteamOptions>() ?? new SteamOptions();
        var download = config.GetSection("Download").Get<DownloadOptions>() ?? new DownloadOptions();

        var paths = PathService.Detect();
        paths.EnsureDirectories();

        var redaction = new RegexRedactionPolicy();
        var httpFactory = new SteamHttpClientFactory(steam);
        var breaker = new CircuitBreaker(SystemTimeProvider.Instance,
            steam.CircuitThreshold, steam.CircuitCooldownMs);
        var deployer = new SteamCmdDeployer(paths, httpFactory, new SteamCmdProcessProbe(),
            breaker: breaker);
        var runner = new SteamCmdRunner(redaction);

        var bus = new DownloadEventBus(Math.Max(1, download.ProgressThrottleMs));
        var provider = new SteamCmdProvider(deployer, runner, bus, breaker);
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
        _shell = new MainShellViewModel(paths, queue, provider, scheduler, bus);

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
    }
}
