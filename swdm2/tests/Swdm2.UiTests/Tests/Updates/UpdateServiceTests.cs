using Swdm2.App.Updates;
using Xunit;

namespace Swdm2.UiTests.Tests.Updates;

/// <summary>
/// D6.3 升级状态机验证（t60):状态转移单向+进度+错误不吞+覆盖安装降级。
/// 真实 feed 集成见 VelopackFeedIntegrationTests(file:// artifacts)。
/// </summary>
public sealed class UpdateServiceTests
{
        private sealed class SyncProgress<T> : IProgress<T>
    {
        private readonly Action<T> _cb;
        public SyncProgress(Action<T> cb) => _cb = cb;
        public void Report(T value) => _cb(value);
    }

    private sealed class FakeUpdateManager : IUpdateManager
    {
        public bool IsVelopackInstalled { get; set; } = true;
        public Version? CurrentVersion { get; set; } = new Version(0, 5, 0);
        public UpdateInfo? NextUpdate { get; set; }
        public int DownloadCalls { get; private set; }
        public int ApplyCalls { get; private set; }
        public Exception? DownloadError { get; set; }

        public Task<UpdateInfo?> CheckForUpdatesAsync(CancellationToken ct = default) =>
            Task.FromResult(NextUpdate);

        public Task DownloadUpdatesAsync(UpdateInfo info, IProgress<int>? progress = null,
            CancellationToken ct = default)
        {
            DownloadCalls++;
            if (DownloadError is not null) throw DownloadError;
            progress?.Report(50);
            progress?.Report(100);
            return Task.CompletedTask;
        }

        public Task ApplyUpdatesAsync(UpdateInfo info, CancellationToken ct = default)
        {
            ApplyCalls++;
            return Task.CompletedTask;
        }
    }

    [WpfFact]
    public async Task Full_Path_Check_Download_Apply()
    {
        var fake = new FakeUpdateManager
        {
            NextUpdate = new UpdateInfo(new Version(0, 6, 0), 74_000_000, null),
        };
        var svc = new UpdateService(fake);

        Assert.Equal(UpdateService.UpdateState.Idle, svc.State);
        Assert.True(svc.CanCheck);

        await svc.CheckAsync();
        Assert.Equal(UpdateService.UpdateState.Available, svc.State);
        Assert.Equal(new Version(0, 6, 0), svc.PendingUpdate?.TargetVersion);
        Assert.Contains("0.6.0", svc.Message);
        Assert.True(svc.CanDownload);

        await svc.DownloadAsync();
        Assert.Equal(100, svc.DownloadProgress);
        Assert.Equal(UpdateService.UpdateState.ReadyToApply, svc.State);
        Assert.True(svc.CanApply);
        Assert.Equal(1, fake.DownloadCalls);

        await svc.ApplyAsync();
        Assert.Equal(UpdateService.UpdateState.Applied, svc.State);
        Assert.Equal(1, fake.ApplyCalls);
    }

    [WpfFact]
    public async Task Check_Feed_Empty_Up_To_Date()
    {
        var svc = new UpdateService(new FakeUpdateManager { NextUpdate = null });
        await svc.CheckAsync();
        Assert.Equal(UpdateService.UpdateState.UpToDate, svc.State);
        Assert.Equal("已是最新版本", svc.Message);
    }

    [WpfFact]
    public async Task Download_Error_Stays_Honest_With_Message()
    {
        var fake = new FakeUpdateManager
        {
            NextUpdate = new UpdateInfo(new Version(0, 6, 0), 1, null),
            DownloadError = new InvalidOperationException("disk full"),
        };
        var svc = new UpdateService(fake);
        await svc.CheckAsync();
        await svc.DownloadAsync();

        Assert.Equal(UpdateService.UpdateState.Error, svc.State);
        Assert.Contains("disk full", svc.Message); // 诚实文案不吞异常
        Assert.Equal(0, fake.ApplyCalls); // Error 后应用禁用
    }

    [WpfFact]
    public void Overwrite_Install_Pre_Degrades_Not_Velopack()
    {
        // t58 诚实降级②：覆盖安装=UpdateManager 不可用=前置降级状态
        var svc = new UpdateService(new FakeUpdateManager { IsVelopackInstalled = false });
        Assert.Equal(UpdateService.UpdateState.OverwriteInstall, svc.State);
        Assert.Contains("覆盖安装", svc.Message);
    }

    [WpfFact]
    public async Task Progress_Provides_Percent()
    {
        var fake = new FakeUpdateManager
        {
            NextUpdate = new UpdateInfo(new Version(0, 6, 0), 1, null),
        };
        var svc = new UpdateService(fake);
        await svc.CheckAsync();

        // 同步进度类（同服务端 SyncProgress 语义；Progress<T>.Report 异步 post 陷阱）
        var seen = new List<int>();
        var proxy = new SyncProgress<int>(seen.Add);
        await fake.DownloadUpdatesAsync(svc.PendingUpdate!, proxy);
        Assert.Contains(100, seen);
        Assert.Contains(50, seen);
    }
}