using Velopack;

namespace Swdm2.App.Updates;

/// <summary>
/// 升级管理抽象（D6.3;t58 打包链已就位:artifacts feed+VelopackApp 钩子）。
/// 接口化=测试可注入桩；生产实现包 Velopack.UpdateManager(file:// feed)。
/// t58 诚实降级②：覆盖安装（非 Velopack 升级路径）= IsVelopackInstalled=false
/// 时 UpdateManager 不可用=UI 引导用 Setup/releases 而非自动升级。
/// </summary>
public interface IUpdateManager
{
    /// <summary>当前是否 Velopack 安装（非覆盖安装；决定自动升级路径可用性）。</summary>
    bool IsVelopackInstalled { get; }

    /// <summary>当前安装版本（未安装=null)。</summary>
    Version? CurrentVersion { get; }

    /// <summary>检查更新（读 releases feed;返回 null=已最新/不可用）。</summary>
    Task<UpdateInfo?> CheckForUpdatesAsync(CancellationToken ct = default);

    /// <summary>下载更新（进度回调 0-100;失败抛）。</summary>
    Task DownloadUpdatesAsync(UpdateInfo info, IProgress<int>? progress = null,
        CancellationToken ct = default);

    /// <summary>应用更新（写入待升级钩子，下次重启生效；Velopack 契约）。</summary>
    Task ApplyUpdatesAsync(UpdateInfo info, CancellationToken ct = default);
}

/// <summary>检查结果（feed 行级数据）。</summary>
public sealed record UpdateInfo(
    Version TargetVersion,
    long PackageSizeBytes,
    string? Notes);