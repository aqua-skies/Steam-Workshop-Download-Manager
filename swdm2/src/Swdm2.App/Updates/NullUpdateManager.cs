namespace Swdm2.App.Updates;

/// <summary>
/// 降级实现（D6.3):Velopack 上下文不可用（VelopackApp.Run 未执行/驱动进程/
/// feed 路径不可达）时安全替代——IsVelopackInstalled=false → UpdateService
/// 走 OverwriteInstall 诚实降级②(t58 契约），不抛 ctor 异常破坏页面装配。
/// </summary>
public sealed class NullUpdateManager : IUpdateManager
{
    public bool IsVelopackInstalled => false;
    public Version? CurrentVersion => null;

    public Task<UpdateInfo?> CheckForUpdatesAsync(CancellationToken ct = default) =>
        Task.FromResult<UpdateInfo?>(null);

    public Task DownloadUpdatesAsync(UpdateInfo info, IProgress<int>? progress = null,
        CancellationToken ct = default) =>
        throw new InvalidOperationException("升级通道不可用（覆盖安装）");

    public Task ApplyUpdatesAsync(UpdateInfo info, CancellationToken ct = default) =>
        throw new InvalidOperationException("升级通道不可用（覆盖安装）");
}
