using System.Collections.Concurrent;
using System.Collections.ObjectModel;
using Swdm2.Core.Options;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Web;

namespace Swdm2.App.Connectivity;

/// <summary>
/// 连接状态控制器（D5.9):IConnectivityState(D2.2 状态栏数据源）的 App 落地 + 代理切换。
/// - 探测=EndpointProbe(D2.2 轻探，经 SteamHttpClientFactory=ProxyMode+指纹头继承）
/// - 切代理即时更新=S5:options 快照语义→**重建工厂**+重新探测（不热改实例）
/// - 失败引导=UI 层（状态栏 Hint + 配代理弹窗）
/// inScope(t48):swdm2/src/Swdm2.App/
/// </summary>
public interface IConnectivityController
{
    /// <summary>当前代理模式（与 SteamOptions 同源）。</summary>
    ProxyMode CurrentProxyMode { get; }

    /// <summary>自定义代理 URL(Custom 模式下生效）。</summary>
    string? CustomProxyUrl { get; }

    /// <summary>刷新探测（失败端点=Unreachable,不抛异常）。</summary>
    Task RefreshAsync(CancellationToken ct = default);

    /// <summary>切换代理模式（校验 Custom 需要 URL)+重建工厂+立即重探+事件。</summary>
    Task SwitchProxyModeAsync(ProxyMode mode, string? customProxyUrl, CancellationToken ct = default);

    /// <summary>代理模式切换事件（UI 即时更新契约）。</summary>
    event EventHandler? ProxyModeChanged;
}

public sealed class ConnectivityStateService : IConnectivityState, IConnectivityController, IDisposable
{
    private readonly SteamOptions _options;
    private IHttpClientFactory _factory; // S5:options 快照语义→切代理=重建
    private readonly TimeSpan _timeout;
    private readonly IReadOnlyDictionary<EndpointKind, string>? _endpointOverrides; // 测试注入
    private readonly SemaphoreSlim _gate = new(1, 1);
    private IReadOnlyDictionary<EndpointKind, EndpointStatus> _current;

    public ConnectivityStateService(SteamOptions options,
        IHttpClientFactory? factory = null,
        TimeSpan? timeout = null,
        IReadOnlyDictionary<EndpointKind, string>? endpointOverrides = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        _options = options;
        _factory = factory ?? new SteamHttpClientFactory(options);
        _timeout = timeout ?? EndpointProbe.DefaultTimeout;
        _endpointOverrides = endpointOverrides;
        _current = new ReadOnlyDictionary<EndpointKind, EndpointStatus>(
            new Dictionary<EndpointKind, EndpointStatus>
            {
                { EndpointKind.Api, new EndpointStatus(EndpointKind.Api, Reachability.Unknown, -1) },
                { EndpointKind.Store, new EndpointStatus(EndpointKind.Store, Reachability.Unknown, -1) },
                { EndpointKind.Community, new EndpointStatus(EndpointKind.Community, Reachability.Unknown, -1) },
            });
    }

    /// <summary>IConnectivityState(D2.2):当前快照（初始=全 Unknown)。</summary>
    public IReadOnlyDictionary<EndpointKind, EndpointStatus> Current => _current;

    /// <summary>IConnectivityState:任一端点**变更**时触发（同值快照重复不触发）。</summary>
    public event EventHandler<IReadOnlyDictionary<EndpointKind, EndpointStatus>>? Changed;

    public ProxyMode CurrentProxyMode => _options.Proxy;
    public string? CustomProxyUrl => _options.CustomProxyUrl;
    public event EventHandler? ProxyModeChanged;

    public async Task RefreshAsync(CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var probe = new EndpointProbe(_factory, _options.Proxy, _timeout, _endpointOverrides);
            var snapshot = await probe.ProbeAsync(ct).ConfigureAwait(false);
            if (!SameSnapshot(_current, snapshot))
            {
                _current = snapshot;
                Changed?.Invoke(this, snapshot);
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task SwitchProxyModeAsync(ProxyMode mode, string? customProxyUrl, CancellationToken ct = default)
    {
        if (mode == ProxyMode.Custom && string.IsNullOrWhiteSpace(customProxyUrl))
            throw new ArgumentException("Custom 模式需要 CustomProxyUrl(D5.9 校验）", nameof(customProxyUrl));

        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // S5:工厂为 options 快照语义 → 切代理=重建工厂（而非热改实例）
            _options.Proxy = mode;
            _options.CustomProxyUrl = string.IsNullOrWhiteSpace(customProxyUrl) ? null : customProxyUrl;
            _factory = new SteamHttpClientFactory(_options);
        }
        finally
        {
            _gate.Release();
        }

        await RefreshAsync(ct).ConfigureAwait(false); // 即时更新（新工厂+新探测）
        ProxyModeChanged?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>同值快照比对（排序无关：按键比对 Kind/Reach/LatencyMs)。</summary>
    private static bool SameSnapshot(
        IReadOnlyDictionary<EndpointKind, EndpointStatus> a,
        IReadOnlyDictionary<EndpointKind, EndpointStatus> b)
    {
        if (a.Count != b.Count) return false;
        foreach (var kv in a)
        {
            if (!b.TryGetValue(kv.Key, out var other)) return false;
            if (kv.Value.Reach != other.Reach || kv.Value.LatencyMs != other.LatencyMs) return false;
        }
        return true;
    }

    public void Dispose() => _gate.Dispose();
}
