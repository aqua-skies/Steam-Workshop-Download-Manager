namespace Swdm2.Steam.Connectivity;

/// <summary>端点种类（spec §3.2）。D2.2 探测 Api/Store/Community 三端点；Cdn 为 D3 下载域预留（本阶段不探测）。</summary>
public enum EndpointKind
{
    /// <summary>api.steampowered.com（元数据主源，匿名 GET/HEAD 可达）。</summary>
    Api,

    /// <summary>store.steampowered.com（storesearch 匿名接口，无 key）。</summary>
    Store,

    /// <summary>steamcommunity.com（社区页/工坊浏览回退源）。</summary>
    Community,

    /// <summary>CDN（下载分片源；D3 下载域接入时纳入探测）。</summary>
    Cdn,
}

/// <summary>
/// 可达性三态（spec §3.2）。Unknown=未探测；Direct=直连可达；ViaProxy=经代理可达；
/// Blocked=403/区域封锁（IP/边缘层，S2.2 探测结论）；Unreachable=网络层失败（DNS/TCP/TLS/超时）。
/// </summary>
public enum Reachability
{
    Unknown,
    Direct,
    ViaProxy,
    Blocked,
    Unreachable,
}

/// <summary>
/// 单端点探测结果（不可变 record）。LatencyMs=-1 表示未探测/失败（不计时）。
/// </summary>
/// <param name="Kind">端点。</param>
/// <param name="Reach">可达性判定。</param>
/// <param name="LatencyMs">响应头到达耗时（毫秒；未探测/超时/失败=-1）。</param>
public sealed record EndpointStatus(EndpointKind Kind, Reachability Reach, int LatencyMs);
