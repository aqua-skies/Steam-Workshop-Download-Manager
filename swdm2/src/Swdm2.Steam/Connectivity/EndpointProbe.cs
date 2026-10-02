using System.Collections.ObjectModel;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using Swdm2.Core.Options;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Connectivity;

/// <summary>
/// 端点探测器默认实现（D2.2）：
/// - GET + <see cref="HttpCompletionOption.ResponseHeadersRead"/>（只取响应头，不下载体——轻探）；
/// - 短超时（默认 5s，⚠️[参数待重标定]：探测超时非退避参数，D2.6 标定任务旁证）；
/// - 经 <see cref="IHttpClientFactory"/>（D2.1）继承 ProxyMode 与指纹头四件套；
/// - 2xx/3xx/4xx（除 403）→ 可达（Direct/ViaProxy 按 ProxyMode 判定）；403 → Blocked（S2.2 探测结论：
///   403 是 IP/边缘层封锁）；网络层异常（DNS/TCP/TLS/超时）→ Unreachable。
///   429 → **仍判定可达**（服务端有应答即可达；限流是节流器/熔断器语义，见 D2.4）。
/// </summary>
public sealed class EndpointProbe : IEndpointProbe
{
    /// <summary>默认探测端点 URL（Cdn 不在本阶段探测范围，见 <see cref="EndpointKind.Cdn"/> 注释）。</summary>
    public static readonly IReadOnlyDictionary<EndpointKind, string> DefaultEndpoints =
        new Dictionary<EndpointKind, string>
        {
            [EndpointKind.Api] = "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/",
            [EndpointKind.Store] = "https://store.steampowered.com/api/storesearch/?term=swdm&l=schinese&cc=CN",
            [EndpointKind.Community] = "https://steamcommunity.com/",
        };

    /// <summary>⚠️[参数待重标定] 探测超时（D2.2 轻探用；D2.6 标定旁证）。</summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(5);

    private readonly IHttpClientFactory _factory;
    private readonly ProxyMode _proxyMode;
    private readonly TimeSpan _timeout;
    private readonly IReadOnlyDictionary<EndpointKind, string> _endpoints;

    /// <param name="factory">D2.1 HttpClient 工厂（ProxyMode/指纹头从此继承）。</param>
    /// <param name="proxyMode">ProxyMode 快照——用于 Direct/ViaProxy 判定（状态分类，与工厂的注入同源）。</param>
    /// <param name="timeout">单端点探测超时（默认 5s）。</param>
    /// <param name="endpointOverrides">测试注入端点 URL（生产为 null=DefaultEndpoints）。</param>
    public EndpointProbe(IHttpClientFactory factory, ProxyMode proxyMode,
                         TimeSpan? timeout = null,
                         IReadOnlyDictionary<EndpointKind, string>? endpointOverrides = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _proxyMode = proxyMode;
        _timeout = timeout ?? DefaultTimeout;
        _endpoints = endpointOverrides ?? DefaultEndpoints;
    }

    public async Task<IReadOnlyDictionary<EndpointKind, EndpointStatus>> ProbeAsync(CancellationToken ct = default)
    {
        var tasks = _endpoints
            .Select(kv => ProbeEndpointAsync(kv.Key, kv.Value, ct))
            .ToArray();
        var statuses = await Task.WhenAll(tasks).ConfigureAwait(false);
        return statuses.ToDictionary(s => s.Kind);
    }

    private async Task<EndpointStatus> ProbeEndpointAsync(EndpointKind kind, string url, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return new EndpointStatus(kind, Reachability.Unreachable, -1);

        using var client = clientResult.Value!;
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
        linked.CancelAfter(_timeout);

        var sw = Stopwatch.StartNew();
        try
        {
            using var response = await client
                .GetAsync(url, HttpCompletionOption.ResponseHeadersRead, linked.Token)
                .ConfigureAwait(false);
            sw.Stop();
            var reach = response.StatusCode == HttpStatusCode.Forbidden
                ? Reachability.Blocked
                : (_proxyMode == ProxyMode.Direct ? Reachability.Direct : Reachability.ViaProxy);
            return new EndpointStatus(kind, reach, (int)sw.ElapsedMilliseconds);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            sw.Stop();
            return new EndpointStatus(kind, Reachability.Unreachable, -1); // 超时
        }
        catch (HttpRequestException)
        {
            sw.Stop();
            return new EndpointStatus(kind, Reachability.Unreachable, -1); // DNS/TCP/TLS 层
        }
    }
}

/// <summary>
/// 连接状态默认实现（D2.2）：快照存储 + 同值不触发的 <see cref="IConnectivityState.Changed"/> 事件。
/// 线程模型：多生产者（探测/事件回调）安全；事件在线程池线程同步触发。
/// </summary>
public sealed class ConnectivityState : IConnectivityState
{
    private readonly ConcurrentDictionary<EndpointKind, EndpointStatus> _status = new();

    /// <summary>初始快照：全部端点 Unknown（LatencyMs=-1）。</summary>
    public ConnectivityState()
    {
        foreach (var kind in Enum.GetValues<EndpointKind>())
            _status[kind] = new EndpointStatus(kind, Reachability.Unknown, -1);
    }

    public IReadOnlyDictionary<EndpointKind, EndpointStatus> Current
        => new ReadOnlyDictionary<EndpointKind, EndpointStatus>(
            new Dictionary<EndpointKind, EndpointStatus>(_status));

    public event EventHandler<IReadOnlyDictionary<EndpointKind, EndpointStatus>>? Changed;

    /// <summary>应用探测快照：逐端点比较，仅**任一值变化**才触发 Changed。返回应用后的当前快照。</summary>
    public IReadOnlyDictionary<EndpointKind, EndpointStatus> Apply(IReadOnlyDictionary<EndpointKind, EndpointStatus> snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var changed = false;
        foreach (var kv in snapshot)
        {
            if (_status.TryGetValue(kv.Key, out var existing))
            {
                if (!existing.Equals(kv.Value))
                {
                    _status[kv.Key] = kv.Value;
                    changed = true;
                }
            }
            else
            {
                _status[kv.Key] = kv.Value;
                changed = true;
            }
        }

        var view = Current;
        if (changed)
            Changed?.Invoke(this, view);
        return view;
    }

    /// <summary>探测并应用（一次性组合；调用方也可分步：probe→Apply）。</summary>
    public async Task<IReadOnlyDictionary<EndpointKind, EndpointStatus>> UpdateFromProbeAsync(
        IEndpointProbe probe, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(probe);
        var snapshot = await probe.ProbeAsync(ct).ConfigureAwait(false);
        return Apply(snapshot);
    }
}
