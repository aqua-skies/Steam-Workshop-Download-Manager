namespace Swdm2.Core.Options;

/// <summary>
/// 代理模式（三态，S2.2 端点探测的配置入口）。
/// </summary>
public enum ProxyMode
{
    /// <summary>直连（不使用系统代理与自定义代理）。</summary>
    Direct,

    /// <summary>系统代理（读取 Windows 系统代理设置，1.x 默认行为）。</summary>
    SystemProxy,

    /// <summary>自定义代理（用户填 URL，状态栏引导配代理的场景）。</summary>
    Custom,
}
