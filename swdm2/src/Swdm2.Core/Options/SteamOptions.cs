using System.ComponentModel.DataAnnotations;

namespace Swdm2.Core.Options;

/// <summary>
/// Steam 域可调参数。C7：**所有数值为 1.x/开源项目起点，交付前必须由重标定任务实测锁定**
/// （经验复验纪律：先问"能否缩短/能否更小/能否更大"再验证采纳）。
/// 重标定任务见 architecture_2.0.md §6：D2.6=B1 退避曲线 + B2 端点节流最小间隔。
/// </summary>
public sealed class SteamOptions
{
    /// <summary>⚠️[参数待重标定] 代理模式。默认 SystemProxy（1.x 行为：走系统代理配置）。</summary>
    public ProxyMode Proxy { get; set; } = ProxyMode.SystemProxy;

    /// <summary>自定义代理 URL（Proxy=Custom 时生效，如 http://127.0.0.1:7897）。</summary>
    [_url?]
    public string? CustomProxyUrl { get; set; }

    /// <summary>
    /// ⚠️[参数待重标定] 端点差异化节流（毫秒）：[0]=社区详情页（1.x=6000）、[1]=workshop/browse（1.x=2000）。
    /// 数组顺序由 Steam 域消费方约定（S11：节流参数不允许硬编码）。B2 重标定候选档 0.5s-8s。
    /// </summary>
    [Range(0, 120000)]
    public double[] ThrottleMs { get; set; } = { 6000, 2000 };

    /// <summary>⚠️[参数待重标定] 元数据并发上限。1.x 无显式上限概念，2.0 起点 2（B3 重标定）。</summary>
    [Range(1, 16)]
    public int MaxConcurrentMetadataQueries { get; set; } = 2;

    /// <summary>⚠️[参数待重标定] 429 退避初始毫秒。B1 候选档下界 5000ms（1.x 经验值）。</summary>
    [Range(100, 60000)]
    public int BackoffInitialMs { get; set; } = 5000;

    /// <summary>⚠️[参数待重标定] 429 退避上限毫秒。B1 候选档上界 90000ms（1.x 经验值）。</summary>
    [Range(1000, 600000)]
    public int BackoffMaxMs { get; set; } = 90000;

    /// <summary>⚠️[参数待重标定] 熔断器连续失败阈值。起点 5（1.x 经验值）。</summary>
    [Range(1, 50)]
    public int CircuitThreshold { get; set; } = 5;

    /// <summary>⚠️[参数待重标定] 熔断冷却毫秒（半开重试前）。起点 60000（1.x 经验值）。</summary>
    [Range(1000, 600000)]
    public int CircuitCooldownMs { get; set; } = 60000;
}
