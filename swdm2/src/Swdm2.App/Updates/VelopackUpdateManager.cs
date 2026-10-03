using System.IO;
using Velopack;

namespace Swdm2.App.Updates;

/// <summary>
/// Velopack 生产实现（D6.3;t58 契约：artifacts feed file:// 实测通道）。
/// - feed=本地路径或 URL(UpdateManager urlOrPath 双通道；file:///localhost 均受理）
/// - IsInstalled/CurrentVersion=UpdateManager 自带（VelopackApp 无静态成员）
/// - 下载=DownloadUpdatesAsync(UpdateInfo,Action&lt;int&gt;)（delta fallback full)
/// - Apply=ApplyUpdatesAndRestart(asset)（即刻退出+升级+重启；VelopackApp.Run 消费）
/// docs.velopack.io/reference/cs/Velopack/UpdateManager（1.2 API 实测对齐）
/// </summary>
public sealed class VelopackUpdateManager : IUpdateManager
{
    private readonly UpdateManager _inner;

    /// <summary>覆盖安装（非 Velopack 通道）=IsInstalled false(t58 诚实降级②)。</summary>
    public bool IsVelopackInstalled => _inner.IsInstalled;

    /// <summary>当前安装版本（3 段化：Velopack 内部补 4 段 0.5.0.0,断言比较漂移）。</summary>
    public Version? CurrentVersion => _inner.CurrentVersion is { } v ? Trim(v.Version) : null;

    /// <param name="releasesFeedUrlOrPath">releases feed(file:// 本地或 http(s) 远端）。</param>
    /// <param name="locator">定位器注入（测试=TestVelopackLocator 模拟安装；null=默认实机定位）。</param>
    public VelopackUpdateManager(string releasesFeedUrlOrPath, Velopack.Locators.IVelopackLocator? locator = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(releasesFeedUrlOrPath);
        _inner = new UpdateManager(releasesFeedUrlOrPath, null, locator);
    }

    public async Task<UpdateInfo?> CheckForUpdatesAsync(CancellationToken ct = default)
    {
        if (!IsVelopackInstalled) return null; // 覆盖安装=诚实无升级路径
        var info = await _inner.CheckForUpdatesAsync().WaitAsync(ct).ConfigureAwait(false);
        if (info?.TargetFullRelease is not { } asset) return null;
        return new UpdateInfo(
            TargetVersion: Trim(asset.Version.Version), // 3 段化同上
            PackageSizeBytes: asset.Size,
            Notes: null);
    }

    /// <summary>Version 3 段化（0.5.0.0→0.5.0;等值比较稳定）。</summary>
    private static Version Trim(Version v) => new Version(v.Major, v.Minor, v.Build);

    public async Task DownloadUpdatesAsync(UpdateInfo info,
        IProgress<int>? progress = null, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(info);
        var raw = await _inner.CheckForUpdatesAsync().WaitAsync(ct).ConfigureAwait(false);
        if (raw?.TargetFullRelease is null)
            throw new InvalidOperationException($"feed 无 {info.TargetVersion} 可下载包");
        Action<int>? p = progress is null ? null : new Action<int>(progress.Report);
        await _inner.DownloadUpdatesAsync(raw, p, ct).ConfigureAwait(false);
    }

    public Task ApplyUpdatesAsync(UpdateInfo info, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(info);
        return Task.Run(async () =>
        {
            var raw = await _inner.CheckForUpdatesAsync().WaitAsync(ct).ConfigureAwait(false);
            if (raw?.TargetFullRelease is null)
                throw new InvalidOperationException($"feed 无 {info.TargetVersion} 可应用包");
            _inner.ApplyUpdatesAndRestart(raw.TargetFullRelease); // 退出+升级+重启
        }, ct);
    }
}
