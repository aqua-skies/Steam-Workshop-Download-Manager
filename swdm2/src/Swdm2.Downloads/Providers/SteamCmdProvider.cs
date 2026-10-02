using System.Collections.Concurrent;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// SteamCmd 下载 provider(D3.5 接入链）:
/// - 队列驱动：<see cref="ExecuteAsync"/> 签名对齐 D3.1 scheduler 执行器（装配=DownloadScheduler(queue, provider.ExecuteAsync))；
/// - 部署保障：D3.3 <see cref="ISteamCmdDeployer.EnsureAsync"/>（幂等；非 ASCII 路径环境约束门控在探针级）；
/// - 进程级下载：D3.4 <see cref="ISteamCmdRunner.DownloadAsync"/>（成功三元+Sweep+失败清空=原子性保证）；
/// - 进度桥接：runner 的 SteamCmdProgress(stdout 磁盘增长估算）→ <see cref="IDownloadEventBus"/> 总线（EMA/ETA/节流）；
///   分段数恒 null=诚实 N/A(steamcmd 单流下载，D3.5b UI 契约）；
/// - 暂停/取消：<see cref="PauseAsync"/>/<see cref="CancelAsync"/> 杀 linked CTS → runner 杀全树+清半成品；
/// - 熔断器接入（S4 同源机制）:bucket <see cref="CircuitBucket"/>;
///   Open 态直接失败不启进程（D2.3 Fast-Fail 语义）；
/// - ⚠️[参数待重标定] 进度估算偏差阈值 15%(arch-20 细化：内报警统计、超阈降级 N/A 诚实路径——
///   超阈=最终快照标注"偏差 X%"且 ETA 保持 null)。
/// </summary>
public sealed class SteamCmdProvider : IDownloadProvider
{
    /// <summary>熔断 bucket(S4 同源：downloads 走 Steam 域熔断机制）。</summary>
    public const string CircuitBucket = "steamcmd-download";

    /// <summary>⚠️[参数待重标定] EstimatedBytes vs BytesDone 偏差报警阈值（±15%;实测后收紧/放宽）。</summary>
    public const double DeviationThreshold = 0.15;

    private readonly ISteamCmdDeployer _deployer;
    private readonly ISteamCmdRunner _runner;
    private readonly IDownloadEventBus _bus;
    private readonly ICircuitBreaker _breaker;
    private readonly IConnectivityState? _connectivity;
    private readonly ConcurrentDictionary<DownloadTaskId, CancellationTokenSource> _active = new();

    public SteamCmdProvider(ISteamCmdDeployer deployer, ISteamCmdRunner runner,
        IDownloadEventBus bus, ICircuitBreaker breaker, IConnectivityState? connectivity = null)
    {
        _deployer = deployer ?? throw new ArgumentNullException(nameof(deployer));
        _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
        _breaker = breaker ?? throw new ArgumentNullException(nameof(breaker));
        _connectivity = connectivity;
    }

    public async Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(entry);
        var task = entry.Task;
        var taskId = task.Id;

        // 0) 路由门（D4.4 才做多 provider 链回退；本阶段仅 SteamCmd)
        if (task.Provider != DownloadProvider.SteamCmd)
        {
            await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                message: $"provider={task.Provider} 未接入（多 provider 路由 D4.4）", ct: ct).ConfigureAwait(false);
            return false;
        }

        // 1) 可达门（D2.2 IConnectivityState:全端 Unreachable→不启进程快失败；
        //    Blocked/Unknown 放行——内容层与元数据层限流独立，Steam CDN 不受社区页 403/429 影响）
        if (_connectivity is not null && IsNetworkDown(_connectivity.Current))
        {
            await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                message: "网络不可达：全部探测端点 Unreachable", ct: ct).ConfigureAwait(false);
            return false;
        }

        // 2) 熔断门（S4 同源；Open→不启进程直接失败）
        if (_breaker.IsOpen(CircuitBucket))
        {
            await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                message: "熔断器开态：跳过本次下载（连续失败冷却中）", ct: ct).ConfigureAwait(false);
            _breaker.RecordFailure(CircuitBucket);
            return false;
        }

        // 2) 部署保障（D3.3 幂等）
        var deployment = await _deployer.EnsureAsync(ct).ConfigureAwait(false);
        if (!deployment.IsOk)
        {
            await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                message: "steamcmd 部署不可用：" + deployment.Error, ct: ct).ConfigureAwait(false);
            _breaker.RecordFailure(CircuitBucket);
            return false;
        }

        // 3) 非 ASCII 安装目录门控（实测 2026-10-02:steamcmd.exe 从中文路径启动 Fatal exit=-2)
        if (!IsAscii(task.DestinationDirectory))
        {
            await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                message: "安装目录含非英文字符（steamcmd 不支持）：" + task.DestinationDirectory, ct: ct).ConfigureAwait(false);
            return false; // 环境约束而非下载失败——不计熔断
        }

        // 4) 组装请求（TotalHint 供 runner 估算；FileSize 缺失=0→总线 ETA 诚实 null)
        var totalHint = task.Item.FileSize ?? 0UL;
        var request = new SteamCmdRunRequest(
            ItemId: task.Item.Id,
            App: task.AppId,
            ExePath: deployment.Value!.ExePath,
            InstallDir: task.DestinationDirectory,
            TotalHintBytes: (long)totalHint,
            Validate: false);

        // D3.6 进程级信号量接入点（qa-20 补 WaitAsync 超时语义 t27;null=默认放行不阻断）
        if (ProcessSlotAcquirer is not null)
            await ProcessSlotAcquirer(task, ct).ConfigureAwait(false);

        // 5) linked CTS 注册（暂停/取消的进程级句柄）
        var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _active[taskId] = linked;

        var progress = new Progress<SteamCmdProgress>(p =>
        {
            // stdout 行磁盘增长估算 → 总线（EMA/ETA/节流在 D3.2 总线侧）
            _ = _bus.ReportProgressAsync(taskId, (ulong)Math.Max(0, p.BytesEstimated),
                totalHint > 0 ? totalHint : null,
                DownloadState.Downloading, segments: null, message: p.Message, ct: linked.Token);
        });

        try
        {
            var result = await _runner.DownloadAsync(request, progress, linked.Token).ConfigureAwait(false);
            _breaker.RecordSuccess(CircuitBucket);

            // 6) 结果映射 + 偏差监控（±15% 报警统计/超阈降级）
            if (result.IsOk)
            {
                var ok = result.Value!;
                var deviation = ok.BytesDone > 0 && ok.EstimatedBytes > 0
                    ? Math.Abs(ok.EstimatedBytes - ok.BytesDone) / (double)ok.BytesDone
                    : 0.0;
                var outOfTolerance = deviation > DeviationThreshold;
                await _bus.ReportProgressAsync(
                    taskId,
                    (ulong)Math.Max(0, ok.BytesDone),
                    totalHint > 0 ? totalHint : null,
                    DownloadState.Completed,
                    segments: null,
                    message: outOfTolerance
                        ? $"⚠进度估算偏差 {deviation:P0}（超 ±{DeviationThreshold:P0} 阈值，ETA 降级 N/A）"
                        : null,
                    ct: ct).ConfigureAwait(false);
                return true;
            }

            // 失败语义：entry 状态由 scheduler 转 Failed;此处只报总线。
            // 自撤销（Pause/Cancel API 杀的进程→runner Fail(Cancelled))不覆盖 Paused/Cancelled 快照——
            // 总线尾帧由 KillAsync 已报，防 Failed 覆盖尾帧。
            var killedByUs = !result.IsOk && result.Error == SteamError.Cancelled
                             && linked.Token.IsCancellationRequested;
            if (!killedByUs)
            {
                await _bus.ReportProgressAsync(taskId, 0, null, DownloadState.Failed,
                    message: $"下载失败：{result.Error}", ct: ct).ConfigureAwait(false);
                _breaker.RecordFailure(CircuitBucket);
            }
            return false;
        }
        catch (OperationCanceledException)
        {
            // 取消来源=Pause/Cancel API(scheduler 的 ct 由自己处理；此处=linked 已被 Pause/Cancel 撤销）
            return false; // scheduler 按 entry 当前态（Paused/Cancelled）保留
        }
        finally
        {
            _active.TryRemove(taskId, out var s);
            s?.Dispose();
        }
    }

    public Task PauseAsync(DownloadTaskId taskId)
        => KillAsync(taskId, DownloadState.Paused);

    public Task CancelAsync(DownloadTaskId taskId)
        => KillAsync(taskId, DownloadState.Cancelled);

    private async Task KillAsync(DownloadTaskId taskId, DownloadState target)
    {
        if (_active.TryRemove(taskId, out var linked))
        {
            linked.Cancel(); // runner 负责杀全树+清半成品（D3.4 契约）；linked 的 Dispose 由 ExecuteAsync finally 负责
        }
        // 状态转移走 D3.1 转移表（非法态抛异常=可测；entry 引用由上层 UI/调度器持有）
        // 总线最终快照（UI 尾帧：Paused/Cancelled 态）
        await _bus.ReportProgressAsync(taskId, 0, null, target,
            message: target == DownloadState.Paused ? "已暂停" : "已取消").ConfigureAwait(false);
    }

    /// <summary>非 ASCII 门控（实测 steamcmd Fatal exit=-2 前置检查）。</summary>
    internal static bool IsAscii(string path)
        => !string.IsNullOrEmpty(path) && path.All(c => c < 128);

    /// <summary>
    /// 可达门判定：全部已探测端点 Unreachable=true;未探测（Unknown/空）放行（不因未探测阻塞下载）。
    /// 设计对照（1.x 学费）：Blocked/Unknown 不判网络死亡——内容层（Steam CDN/steamcmd)
    /// 与元数据层（社区页 403/429)限流相互独立。
    /// </summary>
    internal static bool IsNetworkDown(IReadOnlyDictionary<EndpointKind, EndpointStatus> current)
    {
        if (current is null || current.Count == 0) return false;
        var probed = current.Values.Where(s => s.Reach != Reachability.Unknown).ToList();
        return probed.Count > 0 && probed.All(s => s.Reach == Reachability.Unreachable);
    }

    /// <summary>D3.6 进程级信号量接入点（t27 补 WaitAsync 超时语义；null=默认放行不阻断）。</summary>
    public Func<DownloadTask, CancellationToken, Task>? ProcessSlotAcquirer { get; set; }
}
