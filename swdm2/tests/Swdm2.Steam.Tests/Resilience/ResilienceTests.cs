using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Resilience;

/// <summary>
/// 假钟（D2.4 真实输入验收的基础设施）：逻辑时间推进，真实毫秒不流逝。
/// </summary>
public sealed class FakeTimeProvider : ITimeProvider
{
    private DateTime _utcNow = new DateTime(2026, 10, 2, 12, 0, 0, DateTimeKind.Utc);
    private readonly List<DateTime> _fireTimes = new();
    public DateTime UtcNow => _utcNow;
    public IReadOnlyList<DateTime> FireTimes => _fireTimes;

    /// <summary>DelayAsync=推进逻辑时间并记录放行时刻（供并发间隔断言）。</summary>
    public Task DelayAsync(TimeSpan delay, CancellationToken ct = default)
    {
        if (delay > TimeSpan.Zero)
        {
            _utcNow = _utcNow.Add(delay);
            _fireTimes.Add(_utcNow);
        }
        return Task.CompletedTask;
    }

    /// <summary>手动推进（熔断冷却测试用）。</summary>
    public void Advance(TimeSpan delta) => _utcNow = _utcNow.Add(delta);

    /// <summary>记录当前时刻为放行时刻（无等待的放行）。</summary>
    public void RecordFire() => _fireTimes.Add(_utcNow);
}

/// <summary>
/// D2.4 节流器验收：同 bucket 串行+最小间隔强制；跨 bucket 不互阻；假钟断言。
/// </summary>
[Trait("Category", "Resilience")]
public sealed class ThrottlerTests
{
    [Fact]
    public async Task Same_Bucket_Sequence_Enforces_Min_Interval()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time, new Dictionary<string, TimeSpan>
        {
            ["api"] = TimeSpan.FromMilliseconds(100),
        });

        var fireTimes = new List<DateTime>();
        for (var i = 0; i < 3; i++)
        {
            await throttler.AcquireAsync("api");
            fireTimes.Add(time.UtcNow);
        }

        // 每次请求间隔 ≥ 100ms（假钟逻辑时间）
        Assert.True(fireTimes[1] - fireTimes[0] >= TimeSpan.FromMilliseconds(100));
        Assert.True(fireTimes[2] - fireTimes[1] >= TimeSpan.FromMilliseconds(100));
    }

    /// <summary>验收判据：并发同 bucket——第二次放行距第一次 ≥ 间隔（全程锁串行）。</summary>
    [Fact]
    public async Task Concurrent_Same_Bucket_Second_Fire_After_Interval()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time, new Dictionary<string, TimeSpan>
        {
            ["api"] = TimeSpan.FromMilliseconds(6000),
        });

        var releaseFirst = new TaskCompletionSource();
        var firstStarted = new TaskCompletionSource();
        var secondFireTime = new TaskCompletionSource<DateTime>();

        var first = Task.Run(async () =>
        {
            await throttler.AcquireAsync("api");
            time.RecordFire();
            firstStarted.SetResult();
            await releaseFirst.Task; // 模拟请求处理期（全程锁不释放？锁在 acquire 返回时已释放）
        });
        var second = Task.Run(async () =>
        {
            await firstStarted.Task;
            await throttler.AcquireAsync("api");
            secondFireTime.SetResult(time.UtcNow);
        });

        await firstStarted.Task;
        await Task.Delay(50); // 让 second 进入锁等待
        releaseFirst.SetResult();
        await Task.WhenAll(first, second);

        var secondTime = await secondFireTime.Task;
        // 第二次放行时间与第一次（recorded）差 ≥ 6000ms
        Assert.True(secondTime - time.FireTimes[0] >= TimeSpan.FromMilliseconds(6000),
            $"interval={secondTime - time.FireTimes[0]} expected >= 6000ms");
    }

    [Fact]
    public async Task Different_Buckets_Do_Not_Block_Each_Other()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time, new Dictionary<string, TimeSpan>
        {
            ["api"] = TimeSpan.FromMilliseconds(60000),
            ["store"] = TimeSpan.FromMilliseconds(5),
        });

        await throttler.AcquireAsync("api"); // 占住 api 的逻辑间隔
        // 不同 bucket 立即放行（不等 api 的 60s)
        var sw = System.Diagnostics.Stopwatch.StartNew();
        await throttler.AcquireAsync("store");
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(2), "跨 bucket 不应阻塞");
    }

    [Fact]
    public async Task Unknown_Bucket_Zero_Interval_Immediate()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time);
        await throttler.AcquireAsync("unknown");
        await throttler.AcquireAsync("unknown");
        Assert.Empty(time.FireTimes); // 零间隔=无延迟推进
    }

    /// <summary>默认间隔表与 SteamOptions 槽位一致（1.x 实证起点，C7 标注）。</summary>
    [Fact]
    public void Default_Intervals_Match_Documented_Starts()
    {
        Assert.Equal(TimeSpan.FromSeconds(6), Throttler.DefaultIntervals[ThrottleBuckets.CommunityDetail]);
        Assert.Equal(TimeSpan.FromSeconds(2), Throttler.DefaultIntervals[ThrottleBuckets.CommunityBrowse]);
        Assert.Equal(TimeSpan.FromMilliseconds(100), Throttler.DefaultIntervals[ThrottleBuckets.Api]);
    }
}

/// <summary>
/// D2.4 熔断器验收：阈值→开→冷却→半开→（成功→关/失败→开）完整序列。
/// </summary>
[Trait("Category", "Resilience")]
public sealed class CircuitBreakerTests
{
    [Fact]
    public void Consecutive_Failures_Open_At_Threshold()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 3, cooldownMs: 60000);

        Assert.False(breaker.IsOpen("api"));
        breaker.RecordFailure("api");
        Assert.False(breaker.IsOpen("api"));
        breaker.RecordFailure("api");
        Assert.False(breaker.IsOpen("api"));
        breaker.RecordFailure("api"); // 第 3 次=阈值
        Assert.True(breaker.IsOpen("api"));
        Assert.Equal(CircuitBreaker.Phase.Open, breaker.GetPhase("api"));
    }

    [Fact]
    public void Success_Resets_Failure_Count()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 3, cooldownMs: 60000);

        breaker.RecordFailure("api");
        breaker.RecordFailure("api");
        breaker.RecordSuccess("api");
        Assert.Equal(0, breaker.GetFailureCount("api"));
        breaker.RecordFailure("api"); // 从 0 重新计
        Assert.Equal(1, breaker.GetFailureCount("api"));
        Assert.False(breaker.IsOpen("api"));
    }

    /// <summary>验收判据：开态→冷却届满→半开放行一次试探（IsOpen 返回 false)。</summary>
    [Fact]
    public void Cooldown_Elapses_HalfOpen_Allows_One_Trial()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 2, cooldownMs: 60000);

        breaker.RecordFailure("api");
        breaker.RecordFailure("api"); // 开
        Assert.True(breaker.IsOpen("api"));

        time.Advance(TimeSpan.FromSeconds(59));
        Assert.True(breaker.IsOpen("api")); // 冷却未满仍开

        time.Advance(TimeSpan.FromSeconds(2)); // 61s
        Assert.False(breaker.IsOpen("api")); // 半开放行
        Assert.Equal(CircuitBreaker.Phase.HalfOpen, breaker.GetPhase("api"));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void HalfOpen_Outcome_Resolves_State(bool trialSucceeds)
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 2, cooldownMs: 60000);

        breaker.RecordFailure("api");
        breaker.RecordFailure("api");
        time.Advance(TimeSpan.FromSeconds(61));
        Assert.False(breaker.IsOpen("api")); // 进入半开

        if (trialSucceeds)
        {
            breaker.RecordSuccess("api");
            Assert.Equal(CircuitBreaker.Phase.Closed, breaker.GetPhase("api"));
            Assert.Equal(0, breaker.GetFailureCount("api"));
        }
        else
        {
            breaker.RecordFailure("api"); // 试探失败→重新开
            Assert.Equal(CircuitBreaker.Phase.Open, breaker.GetPhase("api"));
            Assert.True(breaker.IsOpen("api"));
        }
    }

    /// <summary>半开试探失败后冷却重计（再问 IsOpen 必须真开满新冷却）。</summary>
    [Fact]
    public void HalfOpen_Failure_Restarts_Cooldown()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 2, cooldownMs: 60000);

        breaker.RecordFailure("api");
        breaker.RecordFailure("api");
        time.Advance(TimeSpan.FromSeconds(61));
        Assert.False(breaker.IsOpen("api")); // 半开
        breaker.RecordFailure("api"); // 重开

        time.Advance(TimeSpan.FromSeconds(30));
        Assert.True(breaker.IsOpen("api")); // 新冷却未满
        time.Advance(TimeSpan.FromSeconds(31));
        Assert.False(breaker.IsOpen("api")); // 61s 后重新半开
    }
}

/// <summary>
/// ResiliencePipeline + D2.3 客户端集成验收：开态 Fail(CircuitOpen) 不发请求；
/// 节流在请求前 acquire;请求结果计入熔断。
/// </summary>
[Trait("Category", "Resilience")]
public sealed class ResiliencePipelineTests
{
    [Fact]
    public async Task Open_Breaker_Fails_Without_Calling_Action()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 2, cooldownMs: 60000);
        breaker.RecordFailure("api");
        breaker.RecordFailure("api"); // 开
        var called = 0;

        var result = await ResiliencePipeline.ExecuteAsync<string?>(
            "api", throttler: null, breaker,
            _ => { called++; return Task.FromResult(Result<string?, SteamError>.Ok("x")); });

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.CircuitOpen, result.Error);
        Assert.Equal(0, called); // 未调动作=未发请求
    }

    [Fact]
    public async Task Throttler_Acquired_Before_Action()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time, new Dictionary<string, TimeSpan>
        {
            ["api"] = TimeSpan.FromMilliseconds(500),
        });
        var order = new List<string>();

        var r1 = await ResiliencePipeline.ExecuteAsync("api", throttler, breaker: null,
            _ => { order.Add("act1"); return Task.FromResult(Result<string?, SteamError>.Ok("1")); });
        var r2 = await ResiliencePipeline.ExecuteAsync("api", throttler, breaker: null,
            _ => { order.Add("act2"); return Task.FromResult(Result<string?, SteamError>.Ok("2")); });

        Assert.True(r1.IsOk && r2.IsOk);
        Assert.Equal(new[] { "act1", "act2" }, order.ToArray());
        // 第二次执行前假钟推进了 500ms（节流生效证据）
        Assert.Single(time.FireTimes);
        Assert.Equal(TimeSpan.FromMilliseconds(500), time.FireTimes[0] - new DateTime(2026, 10, 2, 12, 0, 0, DateTimeKind.Utc));
    }

    [Fact]
    public async Task Success_Records_Breaker_Success_Failure_Records_Failure()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 5, cooldownMs: 60000);

        await ResiliencePipeline.ExecuteAsync("api", null, breaker,
            _ => Task.FromResult(Result<string?, SteamError>.Ok("ok")));
        Assert.Equal(0, breaker.GetFailureCount("api"));

        await ResiliencePipeline.ExecuteAsync("api", null, breaker,
            _ => Task.FromResult(Result<string?, SteamError>.Fail(SteamError.RateLimited)));
        Assert.Equal(1, breaker.GetFailureCount("api"));
    }

    /// <summary>D2.3 客户端集成端到端：熔断开态 → GetDetails 直接 CircuitOpen 且 stub 收不到请求。</summary>
    [Fact]
    public async Task Client_Circuit_Open_Fails_Without_Http_Call()
    {
        var breaker = new CircuitBreaker(SystemTimeProvider.Instance, threshold: 3, cooldownMs: 60000);
        breaker.RecordFailure("api");
        breaker.RecordFailure("api");
        breaker.RecordFailure("api"); // 开

        using var stub = new ThrottlerStub(() => (System.Net.HttpStatusCode.OK, "{}"));
        var client = new SteamWebApiClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            breaker: breaker,
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.CircuitOpen, result.Error);
        Assert.Equal(0, stub.RequestCount); // 未发出 HTTP
    }

    /// <summary>D2.3 客户端集成端到端：连续 429 达阈值 → 熔断开→后续请求 CircuitOpen(端到端 1.x 429 学费闭环）。</summary>
    [Fact]
    public async Task Client_Repeated_429_Opens_Breaker_Then_CircuitOpen()
    {
        var time = new FakeTimeProvider();
        var breaker = new CircuitBreaker(time, threshold: 3, cooldownMs: 60000);
        using var stub = new ThrottlerStub(() => (System.Net.HttpStatusCode.TooManyRequests, "{}"));
        var client = new SteamWebApiClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            breaker: breaker,
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

        // 前三次 429 → 计入熔断（第 3 次响应后达阈值=开）
        for (var i = 0; i < 3; i++)
        {
            var r = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
            Assert.Equal(SteamError.RateLimited, r.Error);
        }
        Assert.True(breaker.IsOpen("api"));

        // 第 4 次：熔断开态 → CircuitOpen 且不再发请求
        var blocked = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.Equal(SteamError.CircuitOpen, blocked.Error);
        Assert.Equal(3, stub.RequestCount); // 只发过 3 次
    }

    /// <summary>客户端节流集成：第二次请求逻辑延迟 ≥ bucket 间隔（假钟记录）。</summary>
    [Fact]
    public async Task Client_Throttler_Second_Call_Logically_Delayed()
    {
        var time = new FakeTimeProvider();
        var throttler = new Throttler(time, new Dictionary<string, TimeSpan>
        {
            ["api"] = TimeSpan.FromMilliseconds(100),
        });
        using var stub = new ThrottlerStub(() => (System.Net.HttpStatusCode.OK, """
        {"response":{"result":1,"publishedfiledetails":[{"publishedfileid":"1","result":1,"creator_app_id":440,"title":"t"}]}}
        """));
        var client = new SteamWebApiClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            throttler: throttler,
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

        var r1 = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        var r2 = await client.GetPublishedFileDetailsAsync(new PublishedFileId(2));
        Assert.True(r1.IsOk && r2.IsOk);
        // 假钟在第二次 acquire 中推进 100ms = 节流强制证据
        Assert.Single(time.FireTimes);
    }

    /// <summary>给客户端集成测试用的最简 stub（固定状态+ JSON)。</summary>
    private sealed class ThrottlerStub : IDisposable
    {
        private readonly System.Net.Sockets.TcpListener _listener;
        private readonly Task _serveTask;
        private readonly System.Threading.CancellationTokenSource _cts = new();
        private readonly Func<(System.Net.HttpStatusCode, string)> _script;
        private int _requestCount;
        public string Url { get; }
        public int RequestCount => Volatile.Read(ref _requestCount);

        public ThrottlerStub(Func<(System.Net.HttpStatusCode, string)> script)
        {
            _script = script;
            _listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0);
            _listener.Start();
            Url = $"http://127.0.0.1:{((System.Net.IPEndPoint)_listener.LocalEndpoint).Port}/";
            _serveTask = Task.Run(ServeAsync);
        }

        private async Task ServeAsync()
        {
            while (!_cts.IsCancellationRequested)
            {
                System.Net.Sockets.TcpClient tcp;
                try { tcp = await _listener.AcceptTcpClientAsync(_cts.Token); }
                catch (OperationCanceledException) { break; }
                using (tcp)
                using (var stream = tcp.GetStream())
                {
                    var buf = new byte[8192];
                    var n = 0;
                    while (n < buf.Length)
                    {
                        var r = await stream.ReadAsync(buf.AsMemory(n), _cts.Token);
                        if (r == 0) break;
                        n += r;
                        if (System.Text.Encoding.ASCII.GetString(buf, 0, n).Contains("\r\n\r\n")) break;
                    }
                    Interlocked.Increment(ref _requestCount);
                    var (status, json) = _script();
                    var body = System.Text.Encoding.UTF8.GetBytes(json);
                    var code = (int)status;
                    var resp = $"HTTP/1.1 {code} {status}\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n";
                    await stream.WriteAsync(System.Text.Encoding.ASCII.GetBytes(resp), _cts.Token);
                    await stream.WriteAsync(body, _cts.Token);
                }
            }
        }
        public void Dispose()
        {
            _cts.Cancel();
            _listener.Stop();
            try { _serveTask.Wait(TimeSpan.FromSeconds(2)); } catch { }
            _cts.Dispose();
        }
    }
}
