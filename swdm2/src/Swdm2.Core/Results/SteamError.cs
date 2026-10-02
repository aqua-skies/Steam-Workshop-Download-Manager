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

    /// <summary>配置无效（D2.1 起：自定义代理 URL 缺失/格式非法、Options 数值越界等启动期可校验错误）。</summary>
    InvalidConfiguration,

    /// <summary>steamcmd 部署链产物损坏（D3.3）：zip 损坏/解压失败/exe 缺失。损坏 zip 重下后仍失败归此（1.x 幂等重下经验）。</summary>
    CorruptAsset,

    /// <summary>steamcmd 版本校验失败（D3.3):probe 退出码非法（不在 {0,7})或 banner 版本串不可解析。实测 banner=版本唯一来源。</summary>
    VersionCheck,

    /// <summary>chunk 完整性校验失败（D4.3):SHA/Adler 校验不过或数据为空；重下耗尽后归此（损坏重下上限保护）。</summary>
    InvalidChecksum,
}
