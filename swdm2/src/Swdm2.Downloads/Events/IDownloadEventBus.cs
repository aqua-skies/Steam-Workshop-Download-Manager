using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Events;

/// <summary>
/// 下载事件总线契约（D3.2,spec §3.5):
/// - 发布=原始字节采样（provider 侧），总线侧聚合 EMA/ETA 成不可变快照后**节流投递**给订阅者；
/// - 节流语义：每任务窗口 (<see cref="ProgressThrottleMs"/>) 内至多一次投递；
///   窗口内最新样本保留（尾帧不丢，Timer 刷新=不积压）；
/// - 订阅者异常不杀总线（隔离投递）。
/// </summary>
public interface IDownloadEventBus : IAsyncDisposable
{
    /// <summary>上报进度（原始字节；总线聚合成快照并节流投递）。</summary>
    Task ReportProgressAsync(DownloadTaskId taskId, ulong bytesReceived, ulong? totalBytes,
        DownloadState? state = null, IReadOnlyList<int>? segments = null, string? message = null,
        CancellationToken ct = default);

    /// <summary>订阅节流后的事件流；返回取消订阅句柄。</summary>
    IDisposable Subscribe(Func<ProgressSnapshot, Task> handler);

    /// <summary>任务最新快照（UI 一次性查询/重渲染兜底）。</summary>
    ProgressSnapshot? GetLatest(DownloadTaskId taskId);
}
