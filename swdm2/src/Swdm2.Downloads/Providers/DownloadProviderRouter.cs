using System.Collections.Concurrent;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// provider 链路由器（D4.4,spec §3.2 D2 基线决策）:
/// - 主 provider(SteamKit CDN)失败→按错误类型路由：
///   回退类（Network/Timeout/Blocked/AuthRequired/CircuitOpen/InvalidChecksum/CorruptAsset)→自动回退 steamcmd；
///   直切类（AuthNeedAccount=AuthRequired 同义）同回退路径（steamcmd 账号路径职责在 steamcmd 侧）；
///   不路由类（InvalidConfiguration/NotFound/Cancelled/Deserialization/RateLimited?)→快速失败
///   （RateLimited 回退也会被节流=无意义浪费；蒸汽原则：不把已知会失败的事再试一遍）
/// - 切换=事件总线 message 注解（"provider 已切换：…")+ CurrentProvider 查询（UI 提示契约）
/// - Deliverable：注入故障 provider→自动回退 steamcmd 成功（见 Downloads.Tests）
/// </summary>
public sealed class DownloadProviderRouter : IDownloadProvider
{
    /// <summary>回退到 steamcmd 的错误类型表（spec D2：会话级失败→回退 steamcmd;Blocked/NeedAccount→直切账号路径）。</summary>
    private static readonly HashSet<SteamError> RouteToFallback = new()
    {
        SteamError.Network,
        SteamError.Timeout,
        SteamError.Blocked,
        SteamError.AuthRequired,
        SteamError.CircuitOpen,
        SteamError.InvalidChecksum,
        SteamError.CorruptAsset,
        // 实测增补：SteamKit CM 匿名登录可被节流（沙箱/共享出口观测到 RateLimited);
        // steamcmd 进程登录不经 CM=不同路径，spec D2「会话级失败→回退」语义。
        SteamError.RateLimited,
    };

    private readonly IDownloadProvider _primary;
    private readonly IDownloadProvider _fallback;
    private readonly IDownloadEventBus _bus;
    private readonly ConcurrentDictionary<DownloadTaskId, string> _currentProvider = new();

    /// <summary>当前生效 provider 名（UI "provider 已切换"提示查询；初始=主 provider 名）。</summary>
    public string CurrentProviderFor(DownloadTaskId taskId)
        => _currentProvider.GetOrAdd(taskId, _primary.GetType().Name);

    public DownloadProviderRouter(IDownloadProvider primary, IDownloadProvider fallback,
        IDownloadEventBus bus)
    {
        _primary = primary ?? throw new ArgumentNullException(nameof(primary));
        _fallback = fallback ?? throw new ArgumentNullException(nameof(fallback));
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
    }

    /// <summary>槽 hook 转发（qa-20 t27 ProcessSlotAcquirer 同模式：多 provider 槽扩展）。</summary>
    public Func<DownloadTask, CancellationToken, Task>? ProcessSlotAcquirer
    {
        get => (_primary is SteamCmdProvider scp ? scp.ProcessSlotAcquirer : null)
              ?? (_primary is SteamKitCdnProvider skp ? skp.ProcessSlotAcquirer : null);
        set
        {
            if (_primary is SteamCmdProvider scp) scp.ProcessSlotAcquirer = value;
            if (_fallback is SteamCmdProvider fsc) fsc.ProcessSlotAcquirer = value;
            if (_primary is SteamKitCdnProvider skp) skp.ProcessSlotAcquirer = value;
            if (_fallback is SteamKitCdnProvider fsk) fsk.ProcessSlotAcquirer = value;
        }
    }

    public async Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(entry);
        var taskId = entry.Task.Id;
        _currentProvider[taskId] = _primary.GetType().Name;

        var ok = await _primary.ExecuteAsync(entry, ct).ConfigureAwait(false);
        if (ok) return true;

        // 错误类型路由
        var reason = (_primary as IReportLastError)?.LastError;
        var providerError = (reason as DownloadProviderException)?.Error;
        var routeable = providerError is { } e && RouteToFallback.Contains(e);

        if (!routeable)
            return false; // 不路由类=快速失败（取消/配置错误/NotFound 等）

        // 链回退：UI 提示 provider 已切换（总线 message 注解；D5 UI 消费契约）
        _currentProvider[taskId] = _fallback.GetType().Name;
        await _bus.ReportProgressAsync(
            taskId, 0, null, state: null,
            message: $"provider 已切换：{_primary.GetType().Name}→{_fallback.GetType().Name}（原因：{providerError}）",
            ct: ct).ConfigureAwait(false);

        return await _fallback.ExecuteAsync(entry, ct).ConfigureAwait(false);
    }

    public Task PauseAsync(DownloadTaskId taskId)
        => _currentProvider.TryGetValue(taskId, out var name) && name == _fallback.GetType().Name
            ? _fallback.PauseAsync(taskId)
            : _primary.PauseAsync(taskId);

    public Task CancelAsync(DownloadTaskId taskId)
        => _currentProvider.TryGetValue(taskId, out var name) && name == _fallback.GetType().Name
            ? _fallback.CancelAsync(taskId)
            : _primary.CancelAsync(taskId);
}
