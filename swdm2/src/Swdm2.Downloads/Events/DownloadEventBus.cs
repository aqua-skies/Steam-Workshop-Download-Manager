using System.Collections.Concurrent;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Events;

/// <summary>
/// 事件总线默认实现（D3.2):
/// - 每任务 <see cref="ProgressTracker"/>(EMA/ETA 聚合）+ 独立节流窗；
/// - 节流：now-lastDelivery ≥ 窗口 → 即时投递；否则存 latestPending（尾帧保留）；
/// - <see cref="Timer"/>（周期=窗口）刷新 pending 到期者 → 尾帧不丢/不积压（源停发时最后样本必达）；
/// - 投递异常隔离（单订阅者抛异常不影响其他与总线存活）;
/// - ⚠️[参数待重标定] ProgressThrottleMs=100 起点同 D2.6 方法（实测重标定前保守，1ms 高频采样测试验证）。
/// 线程模型：发布方多线程（provider/调度器/Timer）安全；投递为异步顺序投递（窗口序保证）。
/// </summary>
public sealed class DownloadEventBus : IDownloadEventBus
{
    /// <summary>⚠️[参数待重标定] UI 刷新节流窗（C7;实测见 D3.2 高频采样测试）。</summary>
    public const int DefaultProgressThrottleMs = 100;

    private readonly TimeSpan _throttle;
    private readonly ConcurrentDictionary<DownloadTaskId, ProgressTracker> _trackers = new();
    private readonly ConcurrentDictionary<DownloadTaskId, DateTime> _lastDelivery = new();
    private readonly ConcurrentDictionary<DownloadTaskId, ProgressSnapshot> _pending = new();
    private readonly ConcurrentDictionary<DownloadTaskId, ProgressSnapshot> _latest = new();
    private readonly List<Func<ProgressSnapshot, Task>> _handlers = new();
    private readonly object _handlerGate = new();
    private readonly Timer _flushTimer;

    /// <param name="progressThrottleMs">节流窗（默认 100ms，⚠️C7)。</param>
    public DownloadEventBus(int? progressThrottleMs = null)
    {
        var ms = progressThrottleMs ?? DefaultProgressThrottleMs;
        if (ms < 1) throw new ArgumentOutOfRangeException(nameof(progressThrottleMs), ms, "节流窗必须 ≥1ms");
        _throttle = TimeSpan.FromMilliseconds(ms);
        _flushTimer = new Timer(_ => FlushPending(), null, _throttle, _throttle);
    }

    public Task ReportProgressAsync(DownloadTaskId taskId, ulong bytesReceived, ulong? totalBytes,
        DownloadState? state = null, IReadOnlyList<int>? segments = null, string? message = null,
        CancellationToken ct = default)
    {
        var tracker = _trackers.GetOrAdd(taskId, id => new ProgressTracker(id));
        var snapshot = tracker.Sample(bytesReceived, totalBytes, state, segments, message);
        _latest[taskId] = snapshot;

        var now = DateTime.UtcNow;
        var lastDelivery = _lastDelivery.GetOrAdd(taskId, _ => DateTime.MinValue);
        if (now - lastDelivery >= _throttle)
        {
            _lastDelivery[taskId] = now;
            _pending.TryRemove(taskId, out _);
            return DispatchAsync(snapshot);
        }

        _pending[taskId] = snapshot; // 尾帧保留：窗内最新样本
        return Task.CompletedTask;
    }

    public IDisposable Subscribe(Func<ProgressSnapshot, Task> handler)
    {
        ArgumentNullException.ThrowIfNull(handler);
        lock (_handlerGate) _handlers.Add(handler);
        return new Unsubscriber(() => { lock (_handlerGate) _handlers.Remove(handler); });
    }

    public ProgressSnapshot? GetLatest(DownloadTaskId taskId)
        => _latest.TryGetValue(taskId, out var snapshot) ? snapshot : null;

    /// <summary>Timer 回调：刷新到期 pending（尾帧必达 + 不积压）。</summary>
    private void FlushPending()
    {
        var now = DateTime.UtcNow;
        foreach (var kv in _pending)
        {
            if (!_lastDelivery.TryGetValue(kv.Key, out var last) || now - last >= _throttle)
            {
                if (_pending.TryRemove(kv.Key, out var snapshot))
                {
                    _lastDelivery[kv.Key] = now;
                    _ = DispatchAsync(snapshot);
                }
            }
        }
    }

    private async Task DispatchAsync(ProgressSnapshot snapshot)
    {
        List<Func<ProgressSnapshot, Task>> handlersCopy;
        lock (_handlerGate) handlersCopy = _handlers.ToList();
        foreach (var handler in handlersCopy)
        {
            try { await handler(snapshot).ConfigureAwait(false); }
            catch { /* 订阅者异常隔离：不杀总线 */ }
        }
    }

    public ValueTask DisposeAsync()
    {
        _flushTimer.Dispose();
        return ValueTask.CompletedTask;
    }

    private sealed class Unsubscriber : IDisposable
    {
        private readonly Action _unsubscribe;
        public Unsubscriber(Action unsubscribe) => _unsubscribe = unsubscribe;
        public void Dispose() => _unsubscribe();
    }
}
