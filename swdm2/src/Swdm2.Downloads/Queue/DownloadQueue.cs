using System.Collections.Concurrent;
using System.Threading.Channels;
using Swdm2.Core.Domain;

namespace Swdm2.Downloads.Queue;

/// <summary>
/// 下载队列默认实现（D3.1):
/// - <see cref="System.Threading.Channels"/> 单消费者（Reader 串行出队，Writer 多生产者安全——UI 线程/批导入多源入队）；
/// - 入队即 Pending→Queued（转移表校验：非 Pending 入队抛非法转移）；
/// - id→条目注册表供取消/暂停查询（ConcurrentDictionary)。
/// </summary>
public sealed class DownloadQueue : IDownloadQueue
{
    private readonly Channel<DownloadTaskEntry> _channel = Channel.CreateUnbounded<DownloadTaskEntry>(
        new UnboundedChannelOptions { SingleReader = true, SingleWriter = false });

    private readonly ConcurrentDictionary<DownloadTaskId, DownloadTaskEntry> _entries = new();

    public int PendingCount
    {
        get
        {
            // 近似计数：注册表中非终态条目（含队列等待+执行中，供 UI 粗计）
            return _entries.Values.Count(e => !DownloadStateMachine.IsTerminal(e.State));
        }
    }

    public async ValueTask<DownloadTaskEntry> EnqueueAsync(DownloadTask task, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(task);
        // 注册表幂等：重复入队或终态任务重新入队均拒（重试走 RequeueAsync 保持状态连续）
        if (_entries.ContainsKey(task.Id))
            throw new InvalidOperationException($"任务已存在于队列注册表，禁止重复/终态重入：task id={task.Id}");
        var entry = new DownloadTaskEntry(task);
        entry.TransitionTo(DownloadState.Queued); // 入队自动进队列（Pending→Queued，非法态抛异常可测）
        _entries[task.Id] = entry;
        await _channel.Writer.WriteAsync(entry, ct).ConfigureAwait(false);
        return entry;
    }

    public async ValueTask RequeueAsync(DownloadTaskEntry entry, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(entry);
        entry.TransitionTo(DownloadState.Queued); // Failed→Queued（非法态抛异常可测）
        await _channel.Writer.WriteAsync(entry, ct).ConfigureAwait(false);
    }

    public bool TryDequeue(out DownloadTaskEntry? entry)
        => _channel.Reader.TryRead(out entry);

    public IAsyncEnumerable<DownloadTaskEntry> ReadAllAsync(CancellationToken ct = default)
        => _channel.Reader.ReadAllAsync(ct);

    public DownloadTaskEntry? GetEntry(DownloadTaskId id)
        => _entries.TryGetValue(id, out var entry) ? entry : null;

    public ValueTask DisposeAsync()
    {
        _channel.Writer.TryComplete();
        _entries.Clear();
        return ValueTask.CompletedTask;
    }
}
