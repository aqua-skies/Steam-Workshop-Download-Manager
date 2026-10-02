using Swdm2.Core.Domain;

namespace Swdm2.Downloads.Queue;

/// <summary>
/// 下载任务状态机（D3.1，spec §3.4 七态）。
/// 转移表：待定→排队→下载中→（暂停/取消/失败）→完成。
/// 终态（Completed/Cancelled/Failed/... 详见 <see cref="DownloadStateMachine"/>）不可再转移。
/// </summary>
public enum DownloadState
{
    /// <summary>待定（刚创建，尚未入队；UI 本地草稿）。</summary>
    Pending,

    /// <summary>排队（在队列中等待调度）。</summary>
    Queued,

    /// <summary>准备中（已获并发槽，provider 启动前资源准备；t3 §3.2 状态序列 Queued→Preparing→Downloading)。</summary>
    Preparing,

    /// <summary>下载中（provider 执行中）。</summary>
    Downloading,

    /// <summary>暂停（用户/调度器挂起；可恢复回 Downloading)。</summary>
    Paused,

    /// <summary>取消（终态）。</summary>
    Cancelled,

    /// <summary>失败（终态；可重试回 Queued——1.x 学费：失败任务不可原地直接重下）。</summary>
    Failed,

    /// <summary>完成（终态）。</summary>
    Completed,
}

/// <summary>
/// 状态机转移表（不变量，D3.1):
/// - Pending → Queued / Cancelled
/// - Queued → Downloading / Cancelled
/// - Downloading → Paused / Completed / Failed / Cancelled
/// - Paused → Downloading / Cancelled
/// - Failed → Queued（重试）
/// - Completed / Cancelled = 终态，无出边
/// 非法转移抛 <see cref="InvalidOperationException"/>（可测）。
/// </summary>
public static class DownloadStateMachine
{
    /// <summary>合法转移表（key=当前态，value=可转移目标集合；缺 key=终态）。</summary>
    public static readonly IReadOnlyDictionary<DownloadState, IReadOnlySet<DownloadState>> Transitions =
        new Dictionary<DownloadState, IReadOnlySet<DownloadState>>
        {
            [DownloadState.Pending] = new HashSet<DownloadState> { DownloadState.Queued, DownloadState.Cancelled },
            [DownloadState.Queued] = new HashSet<DownloadState> { DownloadState.Preparing, DownloadState.Cancelled },
            [DownloadState.Preparing] = new HashSet<DownloadState> { DownloadState.Downloading, DownloadState.Cancelled },
            [DownloadState.Downloading] = new HashSet<DownloadState>
            {
                DownloadState.Paused, DownloadState.Completed, DownloadState.Failed, DownloadState.Cancelled,
            },
            [DownloadState.Paused] = new HashSet<DownloadState> { DownloadState.Downloading, DownloadState.Cancelled },
            [DownloadState.Failed] = new HashSet<DownloadState> { DownloadState.Queued },
        };

    /// <summary>是否终态（Completed/Cancelled)。</summary>
    public static bool IsTerminal(DownloadState state)
        => state is DownloadState.Completed or DownloadState.Cancelled;

    /// <summary>判定转移合法性（不改状态，供调度器/测试查询）。</summary>
    public static bool CanTransition(DownloadState from, DownloadState to)
    {
        if (!Transitions.TryGetValue(from, out var allowed)) return false;
        return allowed.Contains(to);
    }

    /// <summary>转移；非法抛 <see cref="InvalidOperationException"/>（含 from/to 便于定位）。</summary>
    public static void EnsureCanTransition(DownloadState from, DownloadState to)
    {
        if (!CanTransition(from, to))
            throw new InvalidOperationException(
                $"非法状态转移：{from} → {to}（合法目标：{(Transitions.TryGetValue(from, out var a) ? string.Join("/", a) : "无（终态）")}）");
    }
}

/// <summary>
/// 队列中的任务条目（DownloadTask 不可变快照 + 线程安全可变状态）。
/// 状态变更经 <see cref="TransitionTo"/> 走转移表（锁内校验）。</summary>
public sealed class DownloadTaskEntry
{
    private readonly object _gate = new();
    private DownloadState _state = DownloadState.Pending;

    /// <summary>任务不可变快照（C1)。</summary>
    public DownloadTask Task { get; }

    /// <summary>当前状态（快照读，无需锁也能读到一致值；写必须经 TransitionTo)。</summary>
    public DownloadState State
    {
        get { lock (_gate) return _state; }
    }

    public DownloadTaskEntry(DownloadTask task)
    {
        ArgumentNullException.ThrowIfNull(task);
        Task = task;
    }

    /// <summary>转移（锁内走转移表）；非法抛异常；返回新状态便于断言。</summary>
    public DownloadState TransitionTo(DownloadState target)
    {
        lock (_gate)
        {
            DownloadStateMachine.EnsureCanTransition(_state, target);
            _state = target;
            return target;
        }
    }

    /// <summary>安全性查询（调度器判断可否取消/暂停/重试）。</summary>
    public bool CanTransitionTo(DownloadState target)
    {
        lock (_gate) return DownloadStateMachine.CanTransition(_state, target);
    }
}
