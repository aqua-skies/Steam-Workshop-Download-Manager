using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Connectivity;

/// <summary>
/// 端点探测契约（D2.2）：api/store/community 三端点**轻探**（GET + ResponseHeadersRead 不读体）。
/// 经 D2.1 的 <see cref="IHttpClientFactory"/> 注入（ProxyMode 生效 + 指纹头四件套）。
/// </summary>
public interface IEndpointProbe
{
    /// <summary>并行探测全部已配置端点；失败端点返回 Unreachable（不抛异常）。</summary>
    Task<IReadOnlyDictionary<EndpointKind, EndpointStatus>> ProbeAsync(CancellationToken ct = default);
}

/// <summary>
/// 连接状态契约（D2.2）：状态栏数据源——当前各端点状态 + 变更事件。
/// 事件回调在线程池线程触发（UI 订阅方须 marshal 到 UI 线程，同 D1.3 热更新回调纪律）。
/// </summary>
public interface IConnectivityState
{
    /// <summary>当前快照（不可变快照语义，调用方可缓存）。</summary>
    IReadOnlyDictionary<EndpointKind, EndpointStatus> Current { get; }

    /// <summary>任一端点状态**变更**时触发（同值重复应用不触发）。</summary>
    event EventHandler<IReadOnlyDictionary<EndpointKind, EndpointStatus>>? Changed;
}
