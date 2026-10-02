using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// 下载执行器契约（D3.5):<see cref="ExecuteAsync"/> 签名与 D3.1 <see cref="DownloadScheduler"/> 注入的
/// <c>Func&lt;DownloadTaskEntry, CancellationToken, Task&lt;bool&gt;&gt;</c> 完全对齐——队列驱动的统一插口。
/// 暂停/取消=provider 职责（D3.1 设计：状态转移表入口；杀进程+原子清理由 provider→runner 落地）。
/// </summary>
public interface IDownloadProvider
{
    /// <summary>
    /// 执行下载（队列驱动；scheduler 在 Queued→Preparing→Downloading 后调用）。
    /// 返回 true=成功；false 或异常=失败（scheduler 转 Failed/Cancelled)。
    /// 进度经 <see cref="IDownloadEventBus"/> 上报（EMA/ETA/节流在总线侧，D3.2)。
    /// </summary>
    Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct);

    /// <summary>暂停（杀进程+清理半成品；entry→Paused;1.x 学费：半成品残留=重下幂等破坏）。</summary>
    Task PauseAsync(DownloadTaskId taskId);

    /// <summary>取消（杀进程树+清理半成品；entry→Cancelled)。</summary>
    Task CancelAsync(DownloadTaskId taskId);
}
