using System.Diagnostics;

namespace Swdm2.Downloads.Limiter;

/// <summary>
/// 令牌桶限速器（D4.7,spec §3.3 ISpeedLimiter + 基线决策 D-series):
/// - 双点消费：chunk 调度点（SteamKitCdnProvider chunk 消费）+ HTTP 读流点（HttpSegmentDownloader 段读取）
/// - 0=不限速（用户体感默认不限；设置层热改 UpdateRate)
/// - 突发容量=1 秒量（带宽复利快速起步，随后节流到配置；IDM 令牌桶同型）
/// 单调补令牌（Stopwatch 插值），无锁等待=Task.Delay。
/// </summary>
public interface ISpeedLimiter
{
    /// <summary>当前速率（字节/秒；0=不限速）。</summary>
    long BytesPerSecond { get; }

    /// <summary>消费字节数（阻塞到令牌足够；不限速=立即返回）。</summary>
    Task WaitAsync(int bytes, CancellationToken ct = default);

    /// <summary>热改速率（0=不限速；UI 设置层即时生效）。</summary>
    void UpdateRate(long bytesPerSecond);
}

public sealed class TokenBucketSpeedLimiter : ISpeedLimiter
{
    private readonly object _gate = new();
    private double _tokens;
    private long _bytesPerSecond;
    private readonly Stopwatch _clock = Stopwatch.StartNew();

    public long BytesPerSecond
    {
        get { lock (_gate) return _bytesPerSecond; }
    }

    /// <summary>⚠️[参数待重标定] 突发上限=0.1 秒量（IDM 风格爬坡起步；acceptance 带宽容差 1.1×内收敛，D4.8 校准）。</summary>
    private const double BurstSeconds = 0.1;

    public TokenBucketSpeedLimiter(long bytesPerSecond = 0)
    {
        _bytesPerSecond =(bytesPerSecond < 0) ? 0 : bytesPerSecond;
        _tokens = CapacityFor(_bytesPerSecond);
    }

    public async Task WaitAsync(int bytes, CancellationToken ct = default)
    {
        if (bytes <= 0) return;
        while (true)
        {
            double deficitMs;
            lock (_gate)
            {
                if (_bytesPerSecond <= 0) return; // 不限速
                Refill();
                if (_tokens >= bytes)
                {
                    _tokens -= bytes;
                    return;
                }
                // 大请求（> 突发容量）：余额记账（负账=借用 R-A），精确等待 (R-A)/rate 后补平
                // 不做部分取票串行等待（二次方超时缺陷）
                _tokens -= bytes; // 借用：余额可能为负
                deficitMs = -_tokens / (double)_bytesPerSecond * 1000.0;
            }
            if (deficitMs <= 0) return;
            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(Math.Max(1, deficitMs)), ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            return; // 等待结束=借用已补平（ refill 后 ≥0)
        }
    }

    public void UpdateRate(long bytesPerSecond)
    {
        lock (_gate)
        {
            var rate = bytesPerSecond < 0 ? 0 : bytesPerSecond;
            Refill();
            _bytesPerSecond = rate;
            // 热改不透支：令牌钳到新容量
            _tokens = Math.Min(_tokens, CapacityFor(rate));
        }
    }

    private void Refill()
    {
        var now = _clock.Elapsed.TotalSeconds;
        var capacity = CapacityFor(_bytesPerSecond);
        // 时钟单调：每次调用推进，简单换算（精确补到 now)
        var prev = _lastRefillSeconds;
        _lastRefillSeconds = now;
        if (now > prev && _bytesPerSecond > 0)
        {
            _tokens = Math.Min(capacity, _tokens + (now - prev) * _bytesPerSecond);
        }
    }

    private double _lastRefillSeconds;
    private static double CapacityFor(long rate) => rate <= 0 ? double.MaxValue : rate * BurstSeconds;
}
