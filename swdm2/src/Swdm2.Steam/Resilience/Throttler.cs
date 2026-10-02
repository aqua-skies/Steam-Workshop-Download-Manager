using System.Collections.Concurrent;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Resilience;

/// <summary>
/// 节流器契约（spec §3.3 / D2.4)：**同端点串行化 + 最小间隔强制**。
/// bucket=逻辑端点组（"community-detail"/"browse"/"api"/"store")，差异间隔见 <see cref="Throttler"/>。
/// </summary>
public interface IThrottler
{
    /// <summary>持锁等待直至该 bucket 允许下一次请求（全程持锁=同 bucket 串行）。</summary>
    Task AcquireAsync(string bucket, CancellationToken ct = default);
}

/// <summary>
/// 熔断器契约（spec §3.3 / D2.4):三态状态机 Closed→Open→HalfOpen→Closed。
/// 开态（含半开试探被占）调用方应**不发起请求**直接 Result.Fail(CircuitOpen)（与 D2.3 结果语义一致，不抛异常）。
/// </summary>
public interface ICircuitBreaker
{
    /// <summary>bucket 是否处于开态（冷却后首次询问会转会为半开并返回 false——允许一次试探）。</summary>
    bool IsOpen(string bucket);

    /// <summary>记录一次成功（重置计数器；半开成功→Closed)。</summary>
    void RecordSuccess(string bucket);

    /// <summary>记录一次失败（连续达阈值→Open;半开失败→重新计时冷却）。</summary>
    void RecordFailure(string bucket);
}

/// <summary>
/// 时间提供者（D2.4 假钟 seam):<see cref="UtcNow"/> 逻辑读数 + <see cref="DelayAsync"/> 异步等待。
/// 生产=系统真钟；测试=假钟（推进逻辑时间，真实毫秒不流逝——并发间隔断言的基础）。
/// </summary>
public interface ITimeProvider
{
    DateTime UtcNow { get; }
    Task DelayAsync(TimeSpan delay, CancellationToken ct = default);
}

/// <summary>系统真钟实现。</summary>
public sealed class SystemTimeProvider : ITimeProvider
{
    public static readonly SystemTimeProvider Instance = new();
    public DateTime UtcNow => DateTime.UtcNow;
    public Task DelayAsync(TimeSpan delay, CancellationToken ct = default) => Task.Delay(delay, ct);
}

/// <summary>节流 bucket 键（与 SteamOptions.ThrottleMs 槽位对齐 + D2.x 端点域）。</summary>
public static class ThrottleBuckets
{
    /// <summary>社区详情页（ThrottleMs[0]，**D2.6 实测 1000ms**:0.5s×20 零失败，天花板≈累计 117 请求由熔断器兜底）。</summary>
    public const string CommunityDetail = "community-detail";

    /// <summary>社区 browse 接口（ThrottleMs[1]，**D2.6 实测 1000ms**：与详情页同域同限流）。</summary>
    public const string CommunityBrowse = "browse";

    /// <summary>api.steampowered.com 元数据（D2.3 域；⚠️[参数待重标定] 100ms 起点——先问能否更小）。</summary>
    public const string Api = "api";

    /// <summary>store.steampowered.com 搜索（⚠️[参数待重标定] 250ms 起点）。</summary>
    public const string Store = "store";
}

/// <summary>
/// 节流器默认实现（D2.4):
/// - 每 bucket:SemaphoreSlim(1) **全程锁**（同 bucket 严格串行）+ 上次放行时间；
/// - 间隔 = now - lastFire &lt; interval 时 <see cref="ITimeProvider.DelayAsync"/> 等待（锁内等待=间隔强制）；
/// - 不同 bucket 互不阻塞（各自独立锁）。
/// </summary>
public sealed class Throttler : IThrottler
{
    private readonly ITimeProvider _time;
    private readonly ConcurrentDictionary<string, Bucket> _buckets = new();

    /// <summary>默认间隔（**D2.6 实测**：0.5s×20 连发零失败→间隔非瓶颈；累计请求天花板由熔断器兜底。详见 docs/calibration_1.md）。</summary>
    public static readonly IReadOnlyDictionary<string, TimeSpan> DefaultIntervals = new Dictionary<string, TimeSpan>
    {
        [ThrottleBuckets.CommunityDetail] = TimeSpan.FromSeconds(1),
        [ThrottleBuckets.CommunityBrowse] = TimeSpan.FromSeconds(1),
        [ThrottleBuckets.Api] = TimeSpan.FromMilliseconds(100),
        [ThrottleBuckets.Store] = TimeSpan.FromMilliseconds(250),
    };

    private readonly IReadOnlyDictionary<string, TimeSpan> _intervals;

    /// <param name="time">钟（测试注入假钟）。</param>
    /// <param name="intervals">bucket→间隔（null=默认；全部 ⚠️[参数待重标定] C7/D2.6 B2)。</param>
    public Throttler(ITimeProvider time, IReadOnlyDictionary<string, TimeSpan>? intervals = null)
    {
        ArgumentNullException.ThrowIfNull(time);
        _time = time;
        _intervals = intervals ?? DefaultIntervals;
    }

    public async Task AcquireAsync(string bucket, CancellationToken ct = default)
    {
        var entry = _buckets.GetOrAdd(bucket, b => new Bucket(GetInterval(b)));
        await entry.Semaphore.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var now = _time.UtcNow;
            var elapsed = now - entry.LastFire;
            if (elapsed < entry.Interval)
            {
                await _time.DelayAsync(entry.Interval - elapsed, ct).ConfigureAwait(false);
            }
            entry.LastFire = _time.UtcNow;
        }
        finally
        {
            entry.Semaphore.Release();
        }
    }

    private TimeSpan GetInterval(string bucket)
        => _intervals.TryGetValue(bucket, out var interval) ? interval : TimeSpan.Zero;

    private sealed class Bucket
    {
        public SemaphoreSlim Semaphore { get; } = new(1, 1);
        public DateTime LastFire { get; set; } = DateTime.MinValue;
        public TimeSpan Interval { get; }
        public Bucket(TimeSpan interval) => Interval = interval;
    }
}

/// <summary>
/// 熔断器默认实现（D2.4):连续失败计数（阈值 <see cref="SteamOptions.CircuitThreshold"/>=5 起点）+
/// 冷却（CircuitCooldownMs=60s 起点，全部 ⚠️[参数待重标定] C7/D2.6 B1）+ 半开单次试探。
/// 状态转移：Closed→(连续阈值失败)→Open→(冷却后 IsOpen 询问）→HalfOpen→（一次试探成功→Closed/失败→Open)。
/// </summary>
public sealed class CircuitBreaker : ICircuitBreaker
{
    private readonly ITimeProvider _time;
    private readonly int _threshold;
    private readonly TimeSpan _cooldown;
    private readonly ConcurrentDictionary<string, State> _states = new();

    public CircuitBreaker(ITimeProvider time, int? threshold = null, int? cooldownMs = null)
    {
        ArgumentNullException.ThrowIfNull(time);
        _time = time;
        _threshold = threshold ?? 5;
        _cooldown = TimeSpan.FromMilliseconds(cooldownMs ?? 60000);
    }

    public bool IsOpen(string bucket)
    {
        var state = _states.GetOrAdd(bucket, _ => new State());
        lock (state)
        {
            if (state.Phase == Phase.Open)
            {
                if (_time.UtcNow - state.LastFailureUtc >= _cooldown)
                {
                    state.Phase = Phase.HalfOpen; // 冷却届满：放一次试探
                    return false;
                }
                return true;
            }
            return false; // Closed / HalfOpen 均放行（HalfOpen=单次试探在途）
        }
    }

    public void RecordSuccess(string bucket)
    {
        var state = _states.GetOrAdd(bucket, _ => new State());
        lock (state)
        {
            state.Phase = Phase.Closed;
            state.ConsecutiveFailures = 0;
        }
    }

    public void RecordFailure(string bucket)
    {
        var state = _states.GetOrAdd(bucket, _ => new State());
        lock (state)
        {
            state.ConsecutiveFailures++;
            state.LastFailureUtc = _time.UtcNow;
            if (state.Phase == Phase.HalfOpen || state.ConsecutiveFailures >= _threshold)
            {
                state.Phase = Phase.Open; // 半开试探失败 → 重新冷却计时
            }
        }
    }

    /// <summary>测试观察：当前相位（不作为生产 API)。</summary>
    internal Phase GetPhase(string bucket)
        => _states.TryGetValue(bucket, out var s) ? s.Phase : Phase.Closed;

    internal int GetFailureCount(string bucket)
        => _states.TryGetValue(bucket, out var s) ? s.ConsecutiveFailures : 0;

    internal enum Phase { Closed, Open, HalfOpen }

    private sealed class State
    {
        public Phase Phase { get; set; } = Phase.Closed;
        public int ConsecutiveFailures { get; set; }
        public DateTime LastFailureUtc { get; set; } = DateTime.MinValue;
    }
}

/// <summary>把节流+熔断组合成单一门面（D2.3 客户端注入点；失败语义 Fail 而非抛异常）。</summary>
public static class ResiliencePipeline
{
    /// <summary>执行动作前 acquire 节流；开态直接 Fail(CircuitOpen) 不发请求；结果后记录熔断。</summary>
    public static async Task<Result<T, SteamError>> ExecuteAsync<T>(
        string bucket, IThrottler? throttler, ICircuitBreaker? breaker,
        Func<CancellationToken, Task<Result<T, SteamError>>> action, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(action);
        if (breaker is not null && breaker.IsOpen(bucket))
            return Result<T, SteamError>.Fail(SteamError.CircuitOpen);
        if (throttler is not null)
            await throttler.AcquireAsync(bucket, ct).ConfigureAwait(false);
        // acquire 后再问一次熔断（开态可能在排队期间被别的请求触发）
        if (breaker is not null && breaker.IsOpen(bucket))
            return Result<T, SteamError>.Fail(SteamError.CircuitOpen);
        var result = await action(ct).ConfigureAwait(false);
        if (breaker is not null)
        {
            if (result.IsOk) breaker.RecordSuccess(bucket);
            else breaker.RecordFailure(bucket);
        }
        return result;
    }
}
