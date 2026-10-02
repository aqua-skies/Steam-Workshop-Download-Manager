using Swdm2.Core.Domain;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;
using Xunit;

namespace Swdm2.Downloads.Tests.Events;

/// <summary>
/// D3.2 事件总线与进度聚合验收（arch-20 细化：1ms 级高频采样实测）：
/// - 高频回调不击穿节流（1ms 源 × 50ms 窗 → 投递数远少于样本数，首帧即达）
/// - 尾帧不丢（源停止后 pending 必达，Timer 刷新）
/// - 事件负载不可变（record+防御性拷贝）
/// - EMA/ETA 聚合正确（含诚实降级 null)
/// </summary>
[Trait("Category", "Downloads")]
public sealed class EventBusTests
{
    private static DownloadTaskId NewId() => new DownloadTaskId(Guid.NewGuid());

    // ---------- 节流 ----------

    /// <summary>验收判据：1ms 级高频源（Windows Task.Delay 实际分辨率 ~10-15ms，动态上界）不击穿节流 + 尾帧必达。</summary>
    [Fact]
    public async Task HighFrequency_Source_Does_Not_Break_Through_Throttle()
    {
        var delivered = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 50);
        var unsub = bus.Subscribe(s => { lock (delivered) delivered.Add(s); return Task.CompletedTask; });

        var id = NewId();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        for (var i = 1; i <= 100; i++)
        {
            await bus.ReportProgressAsync(id, (ulong)(i * 10_000), 1_000_000, DownloadState.Downloading);
            await Task.Delay(1); // 1ms 级高频源（实际分辨率受限→按实测耗时动态算上界）
        }
        sw.Stop();
        await Task.Delay(150); // 等尾帧 Timer 刷新
        unsub.Dispose();

        var deliveredCount = delivered.Count;
        var bound = (int)Math.Ceiling(sw.Elapsed.TotalMilliseconds / 50.0) + 2; // 上界=窗口数+Timer 容差
        Assert.True(deliveredCount <= bound, $"投递数 {deliveredCount} 击穿节流（实际耗时 {sw.ElapsedMilliseconds}ms/窗口 50ms，上界 {bound}）");
        Assert.True(deliveredCount >= 2, "至少应有多次投递");
        Assert.Equal(10_000UL, delivered[0].BytesReceived); // 首样本即达
        Assert.Equal(1_000_000UL, delivered[^1].BytesReceived); // 尾帧必达（Timer 刷新）
    }

    /// <summary>验收判据：紧致 burst（无延迟 500 样本）——投递数 ≤3（首帧+尾帧+容差），节流窗内只有最新 pending。</summary>
    [Fact]
    public async Task Tight_Burst_Throttled_To_First_And_Tail()
    {
        var delivered = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 50);
        var unsub = bus.Subscribe(s => { lock (delivered) delivered.Add(s); return Task.CompletedTask; });

        var id = NewId();
        const int n = 500;
        for (var i = 1; i <= n; i++)
        {
            await bus.ReportProgressAsync(id, (ulong)(i * 1_000), (ulong)(n * 1_000), DownloadState.Downloading);
        }
        await Task.Delay(120); // Timer 刷新尾帧
        unsub.Dispose();

        Assert.True(delivered.Count <= 3, $"紧致 burst 投递数 {delivered.Count} 应 ≤3（首帧+尾帧+容差）");
        Assert.Equal(1_000UL, delivered[0].BytesReceived);
        Assert.Equal((ulong)(n * 1_000), delivered[^1].BytesReceived);
    }

    /// <summary>验收判据：尾帧不丢——burst 后停发，最后一个样本必投递。</summary>
    [Fact]
    public async Task Tail_Frame_Not_Lost_After_Burst_Stops()
    {
        var delivered = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 50);
        var unsub = bus.Subscribe(s => { lock (delivered) delivered.Add(s); return Task.CompletedTask; });

        var id = NewId();
        for (var i = 1; i <= 50; i++)
        {
            await bus.ReportProgressAsync(id, (ulong)(i * 100), 5_000, DownloadState.Downloading);
        }
        await Task.Delay(120); // 停止后 Timer 刷新

        unsub.Dispose();
        Assert.NotEmpty(delivered);
        Assert.Equal(5_000UL, delivered[^1].BytesReceived); // 最终字节值已投递
    }

    /// <summary>验收判据：多任务独立节流窗（互不压制）。</summary>
    [Fact]
    public async Task Multiple_Tasks_Have_Independent_Throttle_Windows()
    {
        var counts = new System.Collections.Concurrent.ConcurrentDictionary<DownloadTaskId, int>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 50);
        var unsub = bus.Subscribe(s =>
        {
            counts.AddOrUpdate(s.TaskId, 1, (_, v) => v + 1);
            return Task.CompletedTask;
        });

        var idA = NewId();
        var idB = NewId();
        for (var i = 1; i <= 40; i++)
        {
            await bus.ReportProgressAsync(idA, (ulong)i, 100);
            await bus.ReportProgressAsync(idB, (ulong)i, 100);
        }
        await Task.Delay(120);
        unsub.Dispose();

        Assert.Equal(2, counts.Count);
        Assert.True(counts[idA] >= 1 && counts[idA] <= 4, $"A 投递数异常 {counts[idA]}");
        Assert.True(counts[idB] >= 1 && counts[idB] <= 4, $"B 投递数异常 {counts[idB]}");
    }

    /// <summary>订阅者异常不杀总线（隔离投递）。</summary>
    [Fact]
    public async Task Subscriber_Exception_Does_Not_Kill_Bus()
    {
        var ok = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        bus.Subscribe(s => Task.FromException(new InvalidOperationException("boom")));
        var unsub2 = bus.Subscribe(s => { lock (ok) ok.Add(s); return Task.CompletedTask; });

        await bus.ReportProgressAsync(NewId(), 100, 1000);
        unsub2.Dispose();
        await Task.Delay(30);

        Assert.NotEmpty(ok); // 第二订阅者仍收到（第一者抛异常被隔离）
    }

    // ---------- 事件负载不可变 ----------

    [Fact]
    public async Task Snapshot_Is_Immutable_And_Defensively_Copied()
    {
        var delivered = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var unsub = bus.Subscribe(s => { lock (delivered) delivered.Add(s); return Task.CompletedTask; });

        var sourceSegments = new List<int> { 1, 2, 3 };
        var id = NewId();
        await bus.ReportProgressAsync(id, 500, 1000, segments: sourceSegments);
        unsub.Dispose();
        await Task.Delay(20);

        sourceSegments.Add(99); // 外部突变不得污染快照（防御性拷贝）
        Assert.Equal(new[] { 1, 2, 3 }, delivered[0].Segments!.ToArray());
        Assert.Equal(500UL, delivered[0].BytesReceived);
    }

    [Fact]
    public void Snapshot_Structural_Equality()
    {
        var id = NewId();
        var a = new ProgressSnapshot(id, DownloadState.Downloading, 100, 1000, 50.0, TimeSpan.FromSeconds(18), 4, "m");
        var b = new ProgressSnapshot(id, DownloadState.Downloading, 100, 1000, 50.0, TimeSpan.FromSeconds(18), 4, "m");
        Assert.Equal(a, b);
        Assert.NotEqual(a, b with { BytesReceived = 200 });
    }

    // ---------- EMA / ETA 聚合 ----------

    [Fact]
    public void Tracker_Computes_Ema_Speed_And_Eta()
    {
        var tracker = new ProgressTracker(NewId());
        var t0 = new DateTime(2026, 10, 3, 0, 0, 0, DateTimeKind.Utc);
        var t1 = t0.AddSeconds(1);

        var s1 = tracker.Sample(1_000, 4_000, DownloadState.Downloading, sampleUtc: t0);
        Assert.Equal(0.0, s1.SpeedBytesPerSec); // 首样本无速率
        Assert.Null(s1.Eta);

        var s2 = tracker.Sample(3_000, 4_000, DownloadState.Downloading, sampleUtc: t1);
        Assert.True(s2.SpeedBytesPerSec > 0);
        // 瞬时速率 2000B/s（1s 内 +2000B)→ EMA=2000;ETA=(4000-3000)/2000=0.5s
        Assert.Equal(2000.0, s2.SpeedBytesPerSec, 1e-6);
        Assert.NotNull(s2.Eta);
        Assert.Equal(TimeSpan.FromSeconds(0.5), s2.Eta!.Value);
    }

    /// <summary>EMA 平滑：速率跳变后 EMA 介于新旧之间（不抖动 UI)。</summary>
    [Fact]
    public void Tracker_Ema_Smooths_Rate_Jump()
    {
        var tracker = new ProgressTracker(NewId());
        var t0 = new DateTime(2026, 10, 3, 0, 0, 0, DateTimeKind.Utc);
        tracker.Sample(0, 100_000, DownloadState.Downloading, sampleUtc: t0);
        var s1 = tracker.Sample(10_000, 100_000, DownloadState.Downloading, sampleUtc: t0.AddSeconds(1)); // 10KB/s
        var prevEma = s1.SpeedBytesPerSec;
        var s2 = tracker.Sample(20_000, 100_000, DownloadState.Downloading, sampleUtc: t0.AddSeconds(2)); // 10KB/s 瞬时
        Assert.Equal(prevEma, s2.SpeedBytesPerSec, 1e-6); // 瞬时未变 → EMA 不变

        var s3 = tracker.Sample(100_000, 100_000, DownloadState.Downloading, sampleUtc: t0.AddSeconds(3)); // 80KB/s 跳变
        Assert.True(s3.SpeedBytesPerSec > s2.SpeedBytesPerSec);
        // EMA(=0.4*80k+0.6*10k=38k) 介于旧值（10k)与瞬时（80k)之间——平滑不抖动
        Assert.True(s3.SpeedBytesPerSec > s2.SpeedBytesPerSec && s3.SpeedBytesPerSec < 80_000.0);
    }

    /// <summary>ETA 诚实降级：TotalBytes 未知/速度=0 → null。</summary>
    [Fact]
    public void Tracker_Eta_Null_When_Preconditions_Missing()
    {
        var tracker = new ProgressTracker(NewId());
        var t0 = new DateTime(2026, 10, 3, 0, 0, 0, DateTimeKind.Utc);
        var s1 = tracker.Sample(500, null, DownloadState.Downloading, sampleUtc: t0);
        Assert.Null(s1.Eta); // 总量未知

        var s2 = tracker.Sample(500, 1_000, DownloadState.Downloading, sampleUtc: t0.AddSeconds(1)); // 无增量 → 速度 0
        Assert.Null(s2.Eta); // 速度=0
    }

    [Fact]
    public async Task GetLatest_Returns_Last_Sample()
    {
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var id = NewId();
        await bus.ReportProgressAsync(id, 100, 1000);
        await bus.ReportProgressAsync(id, 500, 1000);
        Assert.Equal(500UL, bus.GetLatest(id)!.BytesReceived);
    }

    [Fact]
    public void Bus_Construct_Invalid_Throttle_Throws()
        => Assert.Throws<ArgumentOutOfRangeException>(() => new DownloadEventBus(progressThrottleMs: 0));
}
