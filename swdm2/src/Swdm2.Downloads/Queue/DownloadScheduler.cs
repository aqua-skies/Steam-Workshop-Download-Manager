using Swdm2.Core.Domain;

namespace Swdm2.Downloads.Queue;

/// <summary>
/// 下载调度器（D3.1):
/// - 单消费者读 <see cref="IDownloadQueue"/> + <see cref="SemaphoreSlim"/> 并发槽控制（⚠️[参数待重标定] C7 起点同 D2.6 方法=保守 2，实测重标定前不做激进值）；
/// - 出队→Queued→Downloading→执行→(Completed|Failed|Cancelled)，全部走状态机转移表；
/// - 终态条目跳过（取消发生在排队期时不再执行）；
/// - 暂停语义=D3.5 provider 职责（杀进程/挂起），本调度器只保证转移表入口（Paused→Downloading 由 ResumeAsync 触发再执行）。
/// 线程模型：单消费循环（Reader）+ 每任务一个执行 Task;ActiveCount 供 UI 与测试观察。
/// </summary>
public sealed class DownloadScheduler : IAsyncDisposable
{
    /// <summary>⚠️[参数待重标定] 调度器并发槽默认值（C7;1.x 单源串行 → 2 起点先问"能否更小/能否更大"再实测）。</summary>
    public const int DefaultMaxConcurrent = 2;

    private readonly IDownloadQueue _queue;
    private readonly SemaphoreSlim _slots;
    private readonly Func<DownloadTaskEntry, CancellationToken, Task<bool>> _executor;
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _loop;
    private int _activeCount;

    /// <summary>并发槽上限（构造时配置；"并发槽配置控制"验收点）。</summary>
    public int MaxConcurrent { get; }

    /// <summary>当前执行中数（观察值；测试断言并发上限）。</summary>
    public int ActiveCount => Volatile.Read(ref _activeCount);

    /// <param name="queue">队列（单消费者 Channel)。</param>
    /// <param name="executor">执行器：返回 true=成功→Completed;false 或异常→Failed;取消→Cancelled。状态转移由调度器统一完成（provider 只报结果）。</param>
    /// <param name="maxConcurrent">并发槽（默认 2,⚠️C7)。</param>
    public DownloadScheduler(IDownloadQueue queue,
        Func<DownloadTaskEntry, CancellationToken, Task<bool>> executor,
        int maxConcurrent = DefaultMaxConcurrent)
    {
        ArgumentNullException.ThrowIfNull(queue);
        ArgumentNullException.ThrowIfNull(executor);
        if (maxConcurrent < 1)
            throw new ArgumentOutOfRangeException(nameof(maxConcurrent), maxConcurrent, "并发槽必须 ≥1");
        _queue = queue;
        _executor = executor;
        MaxConcurrent = maxConcurrent;
        _slots = new SemaphoreSlim(maxConcurrent, maxConcurrent);
        _loop = Task.Run(() => RunAsync(_cts.Token));
    }

    /// <summary>取消队列中尚未执行的条目（排队期取消；执行期取消属 D3.5 provider)。</summary>
    public bool CancelQueued(DownloadTaskId id)
    {
        var entry = _queue.GetEntry(id);
        if (entry is null) return false;
        if (!entry.CanTransitionTo(DownloadState.Cancelled)) return false;
        entry.TransitionTo(DownloadState.Cancelled);
        return true;
    }

    /// <summary>重试失败任务（Failed→Queued；重排队列已有条目，保持状态连续）。</summary>
    public async ValueTask<bool> RetryAsync(DownloadTaskId id, CancellationToken ct = default)
    {
        var entry = _queue.GetEntry(id);
        if (entry is null || !entry.CanTransitionTo(DownloadState.Queued)) return false;
        await _queue.RequeueAsync(entry, ct).ConfigureAwait(false);
        return true;
    }

    public async Task RunAsync(CancellationToken ct)
    {
        try
        {
            await foreach (var entry in _queue.ReadAllAsync(ct).ConfigureAwait(false))
            {
                if (DownloadStateMachine.IsTerminal(entry.State))
                    continue; // 排队期被取消 → 跳过（终态不再执行）

                await _slots.WaitAsync(ct).ConfigureAwait(false);
                if (DownloadStateMachine.IsTerminal(entry.State))
                {
                    _slots.Release(); // 双重检查：取槽期间被取消
                    continue;
                }

                entry.TransitionTo(DownloadState.Preparing); // Queued→Preparing（获槽=准备阶段;t3 §3.2 序列）
                _ = RunEntryAsync(entry, _cts.Token);
            }
        }
        catch (OperationCanceledException) { /* 停止 */ }
    }

    private async Task RunEntryAsync(DownloadTaskEntry entry, CancellationToken ct)
    {
        Interlocked.Increment(ref _activeCount);
        try
        {
            entry.TransitionTo(DownloadState.Downloading); // Preparing→Downloading（provider 启动）
            try
            {
                var success = await _executor(entry, ct).ConfigureAwait(false);
                // 终态竞争防御：执行期间用户取消已切 Cancelled 则不再覆盖
                if (!DownloadStateMachine.IsTerminal(entry.State))
                    entry.TransitionTo(success ? DownloadState.Completed : DownloadState.Failed);
            }
            catch (OperationCanceledException)
            {
                if (!DownloadStateMachine.IsTerminal(entry.State))
                    entry.TransitionTo(DownloadState.Cancelled);
            }
            catch (Exception)
            {
                if (!DownloadStateMachine.IsTerminal(entry.State))
                    entry.TransitionTo(DownloadState.Failed);
            }
        }
        finally
        {
            Interlocked.Decrement(ref _activeCount);
            _slots.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        _cts.Cancel();
        await _loop.ConfigureAwait(false);
        _cts.Dispose();
        _slots.Dispose();
    }
}
