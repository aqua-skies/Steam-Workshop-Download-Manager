namespace Swdm2.Core.Results;

/// <summary>
/// Steam 域错误码。S2.4 熔断器开态为独立码（CircuitOpen）而非 Network，
/// UI 据此区分"网络不通"与"主动熔断保护中"两种文案。
/// </summary>
public enum SteamError
{
    /// <summary>无错误（预留给默认值/反序列化兜底；业务禁止用它表示成功，成功走 Result.Ok）。</summary>
    None,

    /// <summary>429 限流（退避策略触发，D2.4/D2.6）。</summary>
    RateLimited,

    /// <summary>403 或区域封锁（fake-IP/敏感地区，S2.2 探测结论）。</summary>
    Blocked,

    /// <summary>404 资源不存在（物品被删/私有化）。</summary>
    NotFound,

    /// <summary>401 需要登录或 2FA 收码（D4.1 弹窗交互链路）。</summary>
    AuthRequired,

    /// <summary>网络层不可达（DNS/TCP 失败，代理配置问题引导）。</summary>
    Network,

    /// <summary>超时（响应未在超时窗内返回）。</summary>
    Timeout,

    /// <summary>熔断器开启中（S2.4；冷却后半开重试）。</summary>
    CircuitOpen,

    /// <summary>用户取消。</summary>
    Cancelled,

    /// <summary>响应解析失败（结构变更/HTML 改版）。</summary>
    Deserialization,
}
