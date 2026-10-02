using System.ComponentModel.DataAnnotations;

namespace Swdm2.Core.Options;

/// <summary>
/// 下载域可调参数。C7：**所有数值为 1.x/DepotDownloader/bezzad 起点，交付前必须由重标定任务实测锁定**。
/// 重标定任务：D4.8=B3 并发上限（分段并发锁本地 Kestrel fixture，禁公网；增益≥10% 最大档为默认，错误率&lt;2% 门槛）。
/// 不变量 D11：全部不允许硬编码，一律经 Options 注入。
/// </summary>
public sealed class DownloadOptions
{
    /// <summary>⚠️[参数待重标定] 最大并发下载数。1.x=1（串行）；B3 先问"能否更大"再实测。</summary>
    [Range(1, 8)]
    public int MaxConcurrentDownloads { get; set; } = 1;

    /// <summary>⚠️[参数待重标定] 分段并行度。DepotDownloader 默认 8。</summary>
    [Range(1, 32)]
    public int MaxChunkParallelism { get; set; } = 8;

    /// <summary>⚠️[参数待重标定] 全局限速字节/秒（0=不限速）。</summary>
    [Range(0, long.MaxValue)]
    public long MaxSpeedBytesPerSecond { get; set; } = 0;

    /// <summary>⚠️[参数待重标定] 分段超时毫秒。bezzad 分段实现默认 5000。</summary>
    [Range(500, 120000)]
    public int ChunkTimeoutMs { get; set; } = 5000;

    /// <summary>⚠️[参数待重标定] 重叠字节数（分段边界校验）。1.x/研究区间 16-64，取中 32。</summary>
    [Range(0, 4096)]
    public int OverlapBytes { get; set; } = 32;

    /// <summary>稀疏占位文件（exFAT/NTFS 差异，D4.6 有降级路径与不可逆警告）。</summary>
    public bool UseSparsePlaceholder { get; set; } = true;

    /// <summary>⚠️[参数待重标定] 单服务器最大连接数。起点 8。</summary>
    [Range(1, 32)]
    public int MaxConnectionsPerServer { get; set; } = 8;

    /// <summary>⚠️[参数待重标定] 进度刷新节流毫秒（UI 体感阈值 ≤150ms，A9/D5.10 计时重标定）。</summary>
    [Range(16, 1000)]
    public int ProgressThrottleMs { get; set; } = 100;
}
