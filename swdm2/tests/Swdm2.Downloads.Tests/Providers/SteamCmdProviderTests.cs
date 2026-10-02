using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;
using Xunit;

namespace Swdm2.Downloads.Tests.Providers;

/// <summary>
/// D3.5 SteamCmdProvider 接入链验收（真实输入=真实 Channel 队列+真实进程取消语义，
/// runner/deployer/breaker/connectivity 为受控 stub——与 qa-20 D3.4 runner 测试的隔离分层一致）:
/// - 队列驱动下载成功（scheduler↔provider↔bus 装配）
/// - 暂停/取消杀进程干净（runner ct 撤销+产物目录无半成品=原子性）
/// - 进度桥接 stdout 磁盘增长估算→总线（分段恒 null 诚实 N/A)
/// - 偏差 ±15% 超阈降级（报警统计）
/// - 前置门：可达门/熔断门/非 ASCII 门/路由门
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SteamCmdProviderTests
{
    // SP-3 重定向的 TEMP 在中文工作区路径下会被 provider 的 ASCII 门正确拦截（实测 steamcmd Fatal exit=-2 同因）;
    // 测试目录须真 ASCII → LocalApplicationData（C:\Users\Lenovo\AppData\Local,用户名 ASCII)。
    private static readonly string AsciiRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "swdm2-tests", "d35-" + Guid.NewGuid().ToString("N"));

    private static DownloadTask NewTask(string? destDir = null, DownloadProvider provider = DownloadProvider.SteamCmd,
        ulong? fileSize = 100_000)
    {
        var item = new WorkshopItem(new PublishedFileId(17906), new AppId(4000), "测试物品")
        {
            FileSize = fileSize
        };
        return new DownloadTask(new DownloadTaskId(Guid.NewGuid()), item, new AppId(4000),
            destDir ?? "C:\\swdm2-d35\\content") { Provider = provider };
    }

    private sealed class StubDeployer : ISteamCmdDeployer
    {
        public SteamCmdDeployment? Current { get; } =
            new("C:\\steamcmd\\steamcmd.exe", "1788292693", "sha-baseline", 774825, DateTimeOffset.UtcNow);

        public Task<Result<SteamCmdDeployment, SteamError>> EnsureAsync(CancellationToken ct = default)
            => Task.FromResult(Result<SteamCmdDeployment, SteamError>.Ok(Current!));
    }

    private sealed class StubRunner : ISteamCmdRunner
    {
        public List<SteamCmdRunRequest> Requests { get; } = new();
        public Func<SteamCmdRunRequest, IProgress<SteamCmdProgress>, CancellationToken, Task<Result<SteamCmdRunResult, SteamError>>>? Behavior { get; set; }

        public Task<Result<SteamCmdRunResult, SteamError>> DownloadAsync(SteamCmdRunRequest request,
            IProgress<SteamCmdProgress>? progress = null, CancellationToken ct = default,
            ISteamCmdLineObserver? observer = null)
        {
            lock (Requests) Requests.Add(request);
            return Behavior is null
                ? Task.FromResult(Result<SteamCmdRunResult, SteamError>.Ok(
                      new SteamCmdRunResult(SteamCmdOutcome.Success, Path.Combine(request.InstallDir, "content"), 90_000, 90_000, "ok", 1.0)))
                : Behavior(request, progress!, ct);
        }
    }

    private sealed class StubBreaker : ICircuitBreaker
    {
        public bool Open { get; set; }
        public int Failures { get; private set; }
        public int Successes { get; private set; }
        public bool IsOpen(string bucket) => Open;
        public void RecordSuccess(string bucket) => Successes++;
        public void RecordFailure(string bucket) => Failures++;
    }

    // SP-3 沙箱：驱动子进程对 AppData/系统目录写受限（UnauthorizedAccessException)，
    // 且重定向 TEMP 位于中文工作区路径（provider ASCII 门正确拦截——实现正确，是测试环境约束）。
    // 故半成品/原子性用进程内 FakeDownloadState 模拟杀进程语义；真磁盘原子性验证属 D3.4 runner 域（qa-20 已覆盖）。
    private sealed class FakeDownloadState
    {
        public bool HalfBaked { get; set; }
        public bool Cleaned { get; set; }
    }

    private static async Task<Result<SteamCmdRunResult, SteamError>> HalfThenCompleteBehavior(
        FakeDownloadState fake, SteamCmdRunRequest request, IProgress<SteamCmdProgress> progress, CancellationToken ct)
    {
        fake.HalfBaked = true; // "半成品文件已出现"
        progress.Report(new SteamCmdProgress(40, 40_000, "下载中"));

        try
        {
            await Task.Delay(3000, ct).ConfigureAwait(false); // 等待暂停/取消信号
        }
        catch (OperationCanceledException)
        {
            // 杀进程语义：清半成品（D3.4 契约=runner 负责失败/取消清空）
            fake.HalfBaked = false;
            fake.Cleaned = true;
            return Result<SteamCmdRunResult, SteamError>.Fail(SteamError.Cancelled);
        }

        progress.Report(new SteamCmdProgress(100, 90_000, "完成"));
        return Result<SteamCmdRunResult, SteamError>.Ok(
            new SteamCmdRunResult(SteamCmdOutcome.Success, Path.Combine(request.InstallDir, "content"), 90_000, 90_000, "ok", 1.0));
    }

    // ---------- 队列驱动下载成功 ----------

    /// <summary>验收判据：scheduler+provider+bus 装配，队列驱动下载真实完成（entry→Completed)。</summary>
    [Fact]
    public async Task Queue_Driven_Download_Completes()
    {
        var runDir = "C:\\swdm2-d35\\q1";
        var runner = new StubRunner();
        var breaker = new StubBreaker();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, breaker);

        await using var queue = new DownloadQueue();
        await using var scheduler = new DownloadScheduler(queue, provider.ExecuteAsync, maxConcurrent: 1);

        var task = NewTask(runDir);
        var entry = await queue.EnqueueAsync(task);

        var spin = SpinWaitFor(() => entry.State == DownloadState.Completed, TimeSpan.FromSeconds(5));
        Assert.True(spin, $"entry 终态={entry.State}");
        Assert.Single(runner.Requests);
        Assert.Equal(1, breaker.Successes);
        Assert.Equal(0, breaker.Failures);

        var latest = bus.GetLatest(task.Id)!;
        Assert.Equal(DownloadState.Completed, latest.State);
        Assert.Equal(90_000UL, latest.BytesReceived);
    }

    /// <summary>验收判据：进度=stdout 磁盘增长估算→总线快照；分段数恒 null（诚实 N/A)。</summary>
    [Fact]
    public async Task Progress_Bridge_Emits_Snapshots_With_Null_Segments()
    {
        var runner = new StubRunner();
        var fake = new FakeDownloadState();
        runner.Behavior = (req, p, ct) => HalfThenCompleteBehavior(fake, req, p, ct);
        var breaker = new StubBreaker();
        var snapshots = new List<ProgressSnapshot>();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var unsub = bus.Subscribe(s => { lock (snapshots) snapshots.Add(s); return Task.CompletedTask; });
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, breaker);

        await using var queue = new DownloadQueue();
        await using var scheduler = new DownloadScheduler(queue, provider.ExecuteAsync, maxConcurrent: 1);

        var task = NewTask("C:\\swdm2-d35\\q2");
        var entry = await queue.EnqueueAsync(task);

        Assert.True(SpinWaitFor(() => runner.Requests.Count == 1, TimeSpan.FromSeconds(5)));
        Assert.True(SpinWaitFor(() => snapshots.Any(s => s.BytesReceived == 40_000), TimeSpan.FromSeconds(5)));

        // 暂停测试前先等 runner 稳定在半成品阶段
        Assert.True(SpinWaitFor(() => entry.State == DownloadState.Downloading, TimeSpan.FromSeconds(2)));
        await provider.PauseAsync(task.Id);
        unsub.Dispose();

        var mid = snapshots.FirstOrDefault(s => s.BytesReceived == 40_000)!;
        Assert.NotNull(mid);
        Assert.Equal(DownloadState.Downloading, mid.State);
        Assert.Null(mid.Segments); // 诚实 N/A:steamcmd 单流无分段
        Assert.Equal("下载中", mid.Message); // stdout 行消息映射（D3.4→D3.2 桥接）
        Assert.NotNull(bus.GetLatest(task.Id));
    }

    // ---------- 暂停/取消杀进程干净（原子性） ----------

    /// <summary>验收判据：取消杀进程+产物目录无半成品（原子性）。</summary>
    [Fact]
    public async Task Cancel_Kills_Process_Without_Half_Baked_Residue()
    {
        var runner = new StubRunner();
        var fake = new FakeDownloadState();
        runner.Behavior = (req, p, ct) => HalfThenCompleteBehavior(fake, req, p, ct);
        var breaker = new StubBreaker();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, breaker);

        var entry = ManuallyStartedEntry(NewTask("C:\\swdm2-d35\\q3"), out var externalCts);
        var exec = provider.ExecuteAsync(entry, externalCts.Token);

        Assert.True(SpinWaitFor(() => runner.Requests.Count == 1, TimeSpan.FromSeconds(5)));
        Assert.True(SpinWaitFor(() => fake.HalfBaked, TimeSpan.FromSeconds(2))); // 半成品出现

        await provider.CancelAsync(entry.Task.Id);
        var ok = await exec; // runner 撤销 → Fail(Cancelled)

        Assert.False(ok);
        Assert.False(fake.HalfBaked); // 无半成品残留
        Assert.True(fake.Cleaned); // 杀进程+清理已执行（原子性）
        Assert.Equal(DownloadState.Cancelled, bus.GetLatest(entry.Task.Id)!.State);
        externalCts.Dispose();
    }

    /// <summary>验收判据：暂停杀进程+总线尾帧 Paused。</summary>
    [Fact]
    public async Task Pause_Reports_Paused_Tail_Snapshot()
    {
        var runner = new StubRunner();
        var fake = new FakeDownloadState();
        runner.Behavior = (req, p, ct) => HalfThenCompleteBehavior(fake, req, p, ct);
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker());

        var entry = ManuallyStartedEntry(NewTask("C:\\swdm2-d35\\q4"), out var externalCts);
        var exec = provider.ExecuteAsync(entry, externalCts.Token);
        Assert.True(SpinWaitFor(() => runner.Requests.Count == 1, TimeSpan.FromSeconds(5)));

        await provider.PauseAsync(entry.Task.Id);
        var ok = await exec;

        // runner 返回 Cancelled(Fail)→provider false;entry 态由调度器/调用方转（此处 OnPaused 语义验证总线）
        Assert.False(ok);
        Assert.Equal(DownloadState.Paused, bus.GetLatest(entry.Task.Id)!.State);
        Assert.False(fake.HalfBaked); // 暂停也清半成品（steamcmd 不可断点续传）
        Assert.True(fake.Cleaned);
        externalCts.Dispose();
    }

    // ---------- 前置门 ----------

    /// <summary>验收判据：熔断器开态不启进程快失败+计熔断失败。</summary>
    [Fact]
    public async Task Circuit_Open_Fails_Fast_Without_Process()
    {
        var runner = new StubRunner();
        var breaker = new StubBreaker { Open = true };
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, breaker);

        var entry = ManuallyStartedEntry(NewTask(), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.False(ok);
        Assert.Empty(runner.Requests); // 未启进程
        Assert.Equal(1, breaker.Failures);
        Assert.Contains("熔断", bus.GetLatest(entry.Task.Id)!.Message!);
    }

    /// <summary>验收判据：非 ASCII 安装目录门控（实测 Fatal exit=-2 前置）。</summary>
    [Fact]
    public async Task NonAscii_Install_Dir_Fails_Fast()
    {
        var runner = new StubRunner();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker());

        var entry = ManuallyStartedEntry(NewTask("C:\\下载目录\\content"), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.False(ok);
        Assert.Empty(runner.Requests);
        Assert.Contains("非英文", bus.GetLatest(entry.Task.Id)!.Message!);
    }

    /// <summary>验收判据：路由门（非 SteamCmd provider 未接入，D4.4 才做链回退）。</summary>
    [Fact]
    public async Task Non_SteamCmd_Route_Fails_Fast()
    {
        var runner = new StubRunner();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker());

        var entry = ManuallyStartedEntry(NewTask(provider: DownloadProvider.SteamKitCdn), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.False(ok);
        Assert.Empty(runner.Requests);
        Assert.Contains("未接入", bus.GetLatest(entry.Task.Id)!.Message!);
    }

    /// <summary>验收判据：可达门——全端 Unreachable 快失败（Blocked/Unknown 放行=内容层独立）。</summary>
    [Fact]
    public async Task All_Unreachable_Fails_Fast()
    {
        var runner = new StubRunner();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var connectivity = new StubConnectivity(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Unreachable, -1),
            [EndpointKind.Store] = new(EndpointKind.Store, Reachability.Unreachable, -1),
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.Unreachable, -1),
        });
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker(), connectivity);

        var entry = ManuallyStartedEntry(NewTask(), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.False(ok);
        Assert.Empty(runner.Requests);
        Assert.Contains("网络不可达", bus.GetLatest(entry.Task.Id)!.Message!);
    }

    /// <summary>可达门对照：Blocked 不判死亡（内容层≠元数据层）。</summary>
    [Fact]
    public async Task Blocked_Still_Proceeds()
    {
        var runner = new StubRunner();
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var connectivity = new StubConnectivity(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.Blocked, -1),
            [EndpointKind.Api] = new(EndpointKind.Api, Reachability.Direct, 30),
        });
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker(), connectivity);

        var entry = ManuallyStartedEntry(NewTask(), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.True(ok);
        Assert.Single(runner.Requests); // 放行
    }

    // ---------- 偏差 ±15% ----------

    /// <summary>验收判据：偏差超 ±15%→成功完成但消息标注降级（报警统计）。</summary>
    [Fact]
    public async Task Deviation_Out_Of_Tolerance_Reports_And_Degrades_Eta()
    {
        var runner = new StubRunner
        {
            Behavior = (req, p, ct) => Task.FromResult(Result<SteamCmdRunResult, SteamError>.Ok(
                new SteamCmdRunResult(SteamCmdOutcome.Success, "content", BytesDone: 1000, EstimatedBytes: 2500, "ok", 1.0))) // 150% 偏差
        };
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker());

        // FileSize=null：总量未知 → ETA 恒 null（诚实降级）
        var entry = ManuallyStartedEntry(NewTask(fileSize: null), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.True(ok);
        var latest = bus.GetLatest(entry.Task.Id)!;
        Assert.Equal(DownloadState.Completed, latest.State);
        Assert.Contains("偏差", latest.Message!);
        Assert.Contains("降级", latest.Message!);
        Assert.Null(latest.Eta); // ETA 降级 N/A
    }

    /// <summary>偏差在 ±15% 内=正常完成，无报警。</summary>
    [Fact]
    public async Task Deviation_Within_Tolerance_No_Alarm()
    {
        var runner = new StubRunner
        {
            Behavior = (req, p, ct) => Task.FromResult(Result<SteamCmdRunResult, SteamError>.Ok(
                new SteamCmdRunResult(SteamCmdOutcome.Success, "content", BytesDone: 1000, EstimatedBytes: 1050, "ok", 1.0))) // 5%
        };
        await using var bus = new DownloadEventBus(progressThrottleMs: 1);
        var provider = new SteamCmdProvider(new StubDeployer(), runner, bus, new StubBreaker());

        var entry = ManuallyStartedEntry(NewTask(fileSize: null), out var cts);
        var ok = await provider.ExecuteAsync(entry, cts.Token);
        cts.Dispose();

        Assert.True(ok);
        Assert.Null(bus.GetLatest(entry.Task.Id)!.Message);
    }

    // ---------- 工具 ----------

    private static DownloadTaskEntry ManuallyStartedEntry(DownloadTask task, out CancellationTokenSource cts)
    {
        cts = new CancellationTokenSource();
        var entry = new DownloadTaskEntry(task);
        entry.TransitionTo(DownloadState.Queued);
        entry.TransitionTo(DownloadState.Preparing);
        entry.TransitionTo(DownloadState.Downloading);
        return entry;
    }

    private static bool SpinWaitFor(Func<bool> predicate, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (predicate()) return true;
            Thread.Sleep(15);
        }
        return predicate();
    }

    private sealed class StubConnectivity : IConnectivityState
    {
        private readonly IReadOnlyDictionary<EndpointKind, EndpointStatus> _current;
        public StubConnectivity(IReadOnlyDictionary<EndpointKind, EndpointStatus> current) => _current = current;
        public IReadOnlyDictionary<EndpointKind, EndpointStatus> Current => _current;
        public event EventHandler<IReadOnlyDictionary<EndpointKind, EndpointStatus>>? Changed { add { } remove { } }
    }
}
