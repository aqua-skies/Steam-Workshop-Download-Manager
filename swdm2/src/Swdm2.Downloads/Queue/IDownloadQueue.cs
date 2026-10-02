using Swdm2.Core.Domain;

namespace Swdm2.Downloads.Queue;

/// <summary>
/// 下载队列契约（D3.1):Channel 单消费者 FIFO。
/// 入队=自动 Pending→Queued（"入队自动进队列"验收点）；终态任务不被调度器消费（取消的条目跳过）。
/// </summary>
public interface IDownloadQueue : IAsyncDisposable
{
    /// <summary>入队（自动转 Queued)；返回队列条目（状态机载体）。同一 task id 已注册（重复入队/终态重入）抛 InvalidOperationException。</summary>
    ValueTask<DownloadTaskEntry> EnqueueAsync(DownloadTask task, CancellationToken ct = default);

    /// <summary>重排队列已有条目（重试路径：Failed→Queued；同一条目保持状态连续性，不新建）。</summary>
    ValueTask RequeueAsync(DownloadTaskEntry entry, CancellationToken ct = default);

    /// <summary>同步尝试出队（单消费者；空返回 false)。</summary>
    bool TryDequeue(out DownloadTaskEntry? entry);

    /// <summary>读全部（单消费者流；调度器用）。</summary>
    IAsyncEnumerable<DownloadTaskEntry> ReadAllAsync(CancellationToken ct = default);

    /// <summary>当前队列内未消费条目数（近似，用于 UI 计数）。</summary>
    int PendingCount { get; }

    /// <summary>按 id 查找条目（取消/暂停 API 的入口）。</summary>
    DownloadTaskEntry? GetEntry(DownloadTaskId id);
}
