using Microsoft.Extensions.Configuration;
using Swdm2.App.Configuration;
using Swdm2.App.ViewModels;
using Swdm2.Core.Logging;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;

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

        _bus = bus;
        _queue = queue;
        _scheduler = scheduler;
        _shell = new MainShellViewModel(paths, queue, provider, scheduler, bus);
    }

    /// <summary>进程退出释放（队列/总线异步 Dispose）。</summary>
    public static async Task StopAsync()
    {
        if (_scheduler is not null) await _scheduler.DisposeAsync().ConfigureAwait(false);
        if (_queue is not null) await _queue.DisposeAsync().ConfigureAwait(false);
        if (_bus is not null) await _bus.DisposeAsync().ConfigureAwait(false);
        _shell?.Dispose();
    }
}
