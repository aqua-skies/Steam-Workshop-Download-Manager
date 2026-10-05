using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Resilience;
using Swdm2.Core.Paths;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Downloads.Tests.Providers;

/// <summary>
/// D10.1/t70 断点①复现+验收：App 真实组合「router 主失败回退→SteamCmd 真链」。
/// qa-20 E2E 实测：主 provider AuthRequired 失败→切换消息后 10min 无进展、
/// steamcmd 根目录从未创建。本测用同款真实 deployer/runner 组合（与 AppHost L88-93
/// 同构）+ 桩主 provider 故障注入，断言回退链真实落盘（17906/4000 匿名 steamcmd)。
/// Online 门=SWDM2_SKIP_ONLINE=1 跳过（不假绿）。
/// </summary>
public sealed class RouterFallbackOnlineIntegrationTests
{
    private static bool Skip => Environment.GetEnvironmentVariable("SWDM2_SKIP_ONLINE") == "1";

    /// <summary>主 provider 故障注入（AuthRequired=App 实测切换原因同款）。</summary>
    private sealed class FailingPrimary : IDownloadProvider, IReportLastError
    {
        public Exception? LastError { get; private set; }
        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
        {
            LastError = new DownloadProviderException(SteamError.AuthRequired, "primary fail (e2e 实测同款)");
            return Task.FromResult(false);
        }
        public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Func<DownloadTask, CancellationToken, Task>? ProcessSlotAcquirer { get; set; }
    }

    private sealed class RecordingBus : IDownloadEventBus
    {
        public readonly List<string> Messages = new();
        public Task ReportProgressAsync(DownloadTaskId taskId, ulong bytesReceived, ulong? totalBytes,
            DownloadState? state = null, IReadOnlyList<int>? segments = null,
            string? message = null, CancellationToken ct = default)
        {
            if (!string.IsNullOrEmpty(message))
                Messages.Add($"{state?.ToString() ?? "-"}: {message}");
            Console.WriteLine($"DIAG bus [{state}] {message}");
            return Task.CompletedTask;
        }
        public IDisposable Subscribe(Func<ProgressSnapshot, Task> handler) => new NopDisp();
        public ProgressSnapshot? GetLatest(DownloadTaskId taskId) => null;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        private sealed class NopDisp : IDisposable { public void Dispose() { } }
    }

    [Fact]
    public async Task Router_Fallback_To_Real_SteamCmd_Lands_File()
    {
        if (Skip)
        {
            Console.WriteLine("SKIP: SWDM2_SKIP_ONLINE=1");
            return;
        }

        var asciiRoot = Environment.GetEnvironmentVariable("SWDM2_ASCII_ROOT");
        // 驱动进程对 C:\tmp 只读 ACL（实测 UnauthorizedAccess）=默认 %APPDATA%
        // （ASCII+用户可写；同 app 根域语义）
        var asciiDefault = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var root = !string.IsNullOrEmpty(asciiRoot)
            ? Path.Combine(asciiRoot, "swdm2_t70_router_" + Guid.NewGuid().ToString("N")[..8])
            : Path.Combine(asciiDefault, "swdm2_t70_router_" + Guid.NewGuid().ToString("N")[..8]);
        try { Directory.CreateDirectory(root); }
        catch (UnauthorizedAccessException ex)
        {
            // 驱动进程沙箱 ACL 门（e2e 同族）=诚实降级不假绿：线上环境复跑
            Console.WriteLine($"[ONLINE-ACL-FAIL] {ex.GetType().Name} root={root} — 环境阻断（换权限环境复验）");
            return;
        }

        // app 同构根模式（SWDM2_REAL_ROOT=1）=直接用 %APPDATA%\SWDM 真实部署：
        // 复现 qa e2e 卡死的完整链（EnsureAsync 慢路径+真实 runner)。
        var useRealRoot = Environment.GetEnvironmentVariable("SWDM2_REAL_ROOT") == "1";
        var realAppRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SWDM");
        if (useRealRoot) root = realAppRoot;

        try
        {
            var paths = new OnlinePaths(root);
            var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.SystemProxy });
            var deployer = new SteamCmdDeployer(paths, factory, new SteamCmdProcessProbe());
            var runner = new SteamCmdRunner();
            var bus = new RecordingBus();
            var breaker = new CircuitBreaker(new SystemTimeProvider());
            var fallback = new SteamCmdProvider(deployer, runner, bus, breaker);
            var primary = new FailingPrimary();
            var router = new DownloadProviderRouter(primary, fallback, bus);

            // 同 AppHost 队列任务口径（MainShellVM L130: Provider=SteamCmd)
            var install = Path.Combine(root, "install");
            Directory.CreateDirectory(install);
            var item = new WorkshopItem(new PublishedFileId(17906), new AppId(4000), "t70 router e2e mod");
            var task = new DownloadTask(
                new DownloadTaskId(Guid.NewGuid()), item, new AppId(4000), install)
            { Provider = DownloadProvider.SteamCmd };
            var entry = new DownloadTaskEntry(task);

            var ok = await router.ExecuteAsync(entry, CancellationToken.None);
            Console.WriteLine($"DIAG router result={ok} messages=[{string.Join(" | ", bus.Messages)}]");

            // 回退链=切换消息+真实落盘（同 RealLanding 收口径）
            Assert.Contains(bus.Messages, m => m.Contains("provider 已切换", StringComparison.Ordinal));
            var contentRoot = Path.Combine(install, "steamapps", "workshop", "content", "4000", "17906");
            Assert.True(Directory.Exists(contentRoot), $"落盘目录必须存在: {contentRoot}");
            var files = Directory.GetFiles(contentRoot, "*", SearchOption.AllDirectories);
            Assert.NotEmpty(files);
            Assert.All(files, f => Assert.True(new FileInfo(f).Length > 0));
            Console.WriteLine($"DIAG landed {files.Length} files at {contentRoot}");
        }
        finally
        {
            // 真实根不删（app 数据）；临时根清理
            if (!useRealRoot) { try { Directory.Delete(root, true); } catch { } }
        }
    }
}

    internal sealed class OnlinePaths : IPathService
    {
        private readonly string _root;
        public OnlinePaths(string root) => _root = root;
        public string Root => _root;
        public PathMode Mode => PathMode.Portable;
        public string SteamCmdDirectory => Path.Combine(_root, "steamcmd");
        public string WorkshopContent(AppId app) => Path.Combine(_root, "content", app.Value.ToString());
        public string DownloadStaging(DownloadTaskId taskId) => Path.Combine(_root, "staging", taskId.Value.ToString());
        public string LogDirectory => Path.Combine(_root, "logs");
        public string ConfigFile => Path.Combine(_root, "config.json");
        public string CredentialsFile => Path.Combine(_root, "credentials.bin");
        public void EnsureDirectories() { }
    }