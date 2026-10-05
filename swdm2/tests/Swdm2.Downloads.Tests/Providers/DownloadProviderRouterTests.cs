using System.Collections.Concurrent;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Downloads.Tests.Providers;

/// <summary>
/// D4.4 provider 链路由验收（spec D2 基线决策）:
/// - 注入故障 provider(Network/Timeout/AuthRequired/Blocked/InvalidChecksum)→自动回退 steamcmd 成功
/// - 主成功不回退；不路由类（Cancelled/InvalidConfiguration/NotFound）→快速失败
/// - 切换提示：总线 message "provider 已切换"+CurrentProviderFor 查询（UI 契约）
/// - 真 SteamKitCdnProvider 沙箱链回退（CM 阻断→Network→回退）
/// </summary>
[Trait("Category", "Downloads")]
public sealed class DownloadProviderRouterTests
{
    private static DownloadTaskEntry Entry()
        => new(new DownloadTask(
            new DownloadTaskId(Guid.NewGuid()),
            new WorkshopItem(new PublishedFileId(3808352517), new AppId(4000), "kfc"),
            new AppId(4000),
            Path.Combine(Path.GetTempPath(), "swdm-d44-" + Guid.NewGuid().ToString("N")))
        { Provider = DownloadProvider.SteamKitCdn });

    private sealed class StubProvider : IDownloadProvider, IReportLastError
    {
        private readonly SteamError? _failWith;
        public Exception? LastError { get; private set; }
        public int Invocations { get; private set; }

        public StubProvider(SteamError? failWith = null) => _failWith = failWith;

        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
        {
            Invocations++;
            if (_failWith is { } err)
            {
                LastError = new DownloadProviderException(err, $"stub fail={err}");
                return Task.FromResult(false);
            }
            LastError = null;
            return Task.FromResult(true);
        }

        public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
    }

    private sealed class RecordingBus : IDownloadEventBus
    {
        public ConcurrentQueue<string> Messages { get; } = new();

        public Task ReportProgressAsync(DownloadTaskId taskId, ulong bytesReceived, ulong? totalBytes,
            DownloadState? state = null, IReadOnlyList<int>? segments = null, string? message = null,
            CancellationToken ct = default)
        {
            if (!string.IsNullOrEmpty(message)) Messages.Enqueue(message);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<ProgressSnapshot, Task> handler) => new NoopDisposable();
        public ProgressSnapshot? GetLatest(DownloadTaskId taskId) => null;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;

        private sealed class NoopDisposable : IDisposable
        {
            public void Dispose() { }
        }
    }

    /// <summary>注入故障 provider(Network)→自动回退 steamcmd 成功+切换提示。</summary>
    [Theory]
    [InlineData(SteamError.Network)]
    [InlineData(SteamError.Timeout)]
    [InlineData(SteamError.AuthRequired)]
    [InlineData(SteamError.Blocked)]
    [InlineData(SteamError.InvalidChecksum)]
    [InlineData(SteamError.RateLimited)]
    public async Task Failing_Primary_Routes_To_SteamCmd_Fallback(SteamError error)
    {
        var primary = new StubProvider(error);
        var fallback = new StubProvider();
        var bus = new RecordingBus();
        var router = new DownloadProviderRouter(primary, fallback, bus);
        var entry = Entry();

        var ok = await router.ExecuteAsync(entry, CancellationToken.None);

        Assert.True(ok);
        Assert.Equal(1, fallback.Invocations);
        Assert.Equal(nameof(StubProvider), router.CurrentProviderFor(entry.Task.Id));
        var msg = Assert.Single(bus.Messages);
        Assert.Contains("provider 已切换", msg);
        Assert.Contains(error.ToString(), msg);
    }

    /// <summary>主 provider 成功→不回退（fallback 零调用）。</summary>
    [Fact]
    public async Task Successful_Primary_Does_Not_Fall_Back()
    {
        var primary = new StubProvider();
        var fallback = new StubProvider();
        var router = new DownloadProviderRouter(primary, fallback, new RecordingBus());

        var ok = await router.ExecuteAsync(Entry(), CancellationToken.None);

        Assert.True(ok);
        Assert.Equal(0, fallback.Invocations);
    }

    /// <summary>不路由类（Cancelled/InvalidConfiguration/NotFound/RateLimited)→快速失败，不回退。</summary>
    [Theory]
    [InlineData(SteamError.Cancelled)]
    [InlineData(SteamError.InvalidConfiguration)]
    [InlineData(SteamError.NotFound)]
    public async Task NonRouteable_Errors_Fail_Fast_Without_Fallback(SteamError error)
    {
        var primary = new StubProvider(error);
        var fallback = new StubProvider();
        var router = new DownloadProviderRouter(primary, fallback, new RecordingBus());

        var ok = await router.ExecuteAsync(Entry(), CancellationToken.None);

        Assert.False(ok);
        Assert.Equal(0, fallback.Invocations);
    }

    /// <summary>真链：SteamKitCdnProvider 沙箱 CM 阻断→Network 类→回退 steamcmd 桩成功（端到端链回退）。</summary>
    [Fact]
    [Trait("Category", "Integration")]
    public async Task Real_SteamKit_Primary_Sandbox_Failure_Routes_To_Fallback()
    {
        var session = new SteamKitSessionManager(timeoutSeconds: 3); // 沙箱短超时（环境容忍门）
        var cdn = new SteamKitCdnClient(session, timeoutSeconds: 3);
        var primary = new SteamKitCdnProvider(session, cdn, new RecordingBus());
        var fallback = new StubProvider();
        var bus = new RecordingBus();
        var router = new DownloadProviderRouter(primary, fallback, bus);
        var entry = Entry();

        var ok = await router.ExecuteAsync(entry, CancellationToken.None);

        // 沙箱：CM 阻断→primary Network 失败→回退成功；桌面网络通时 primary 成功（ok 由 primary）
        Assert.True(ok, "回退/主链必须其一成功");
        Assert.True(fallback.Invocations <= 1);
        if (fallback.Invocations == 1)
        {
            Assert.Contains("provider 已切换", Assert.Single(bus.Messages));
        }
    }

    /// <summary>D10.1/t70 断点①：回退 provider 抛逃逸异常=显式 Failed 消息，
    /// 禁止静默卡死（qa e2e provider 切换后 10min 冻结根因）。</summary>
    private sealed class ThrowingProvider : IDownloadProvider
    {
        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
            => throw new UnauthorizedAccessException("模拟 ACL 拒绝（e2e 沙箱实测同族）");
        public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
    }

    [Fact]
    public async Task Fallback_Escaping_Exception_Reports_Failure_Not_Silent_Stall()
    {
        var primary = new StubProvider(SteamError.AuthRequired);
        var fallback = new ThrowingProvider();
        var bus = new RecordingBus();
        var router = new DownloadProviderRouter(primary, fallback, bus);
        var entry = Entry();

        var ok = await router.ExecuteAsync(entry, CancellationToken.None);

        Assert.False(ok);
        Assert.Contains(bus.Messages, m => m.Contains("provider 已切换", StringComparison.Ordinal));
        Assert.Contains(bus.Messages, m => m.Contains("provider 回退执行异常", StringComparison.Ordinal));
        Assert.Contains(bus.Messages, m => m.Contains("UnauthorizedAccessException", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Primary_Escaping_Exception_Reports_Failure_Not_Silent_Stall()
    {
        var primary = new ThrowingProvider();
        var fallback = new StubProvider();
        var bus = new RecordingBus();
        var router = new DownloadProviderRouter(primary, fallback, bus);

        var ok = await router.ExecuteAsync(Entry(), CancellationToken.None);

        Assert.False(ok);
        Assert.Contains(bus.Messages, m => m.Contains("provider 执行异常", StringComparison.Ordinal));
        Assert.Equal(0, fallback.Invocations);
    }
}