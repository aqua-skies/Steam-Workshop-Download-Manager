namespace Swdm2.Core.Domain;

/// <summary>下载提供者来源（provider 链路由提示用；D4.4 链回退时切换）。</summary>
public enum DownloadProvider
{
    /// <summary>SteamKit CDN 主 provider。</summary>
    SteamKitCdn,

    /// <summary>steamcmd 兜底 provider。</summary>
    SteamCmd,

    /// <summary>HTTP 直链分段 provider。</summary>
    HttpDirect,
}

/// <summary>
/// 下载任务（核心不可变快照）。状态机与可变进度在 Downloads 域（D3.1），
/// 本类型仅承载 UI/队列共享所需的领域数据（C1：不可变）。
/// </summary>
public sealed record DownloadTask
{
    /// <summary>任务 id（Guid 唯一）。</summary>
    public DownloadTaskId Id { get; init; }

    /// <summary>被下载的工坊物品。</summary>
    public WorkshopItem Item { get; init; }

    /// <summary>目标游戏 AppId（决定安装目录，D1.2 路径服务）。</summary>
    public AppId AppId { get; init; }

    /// <summary>安装目录（绝对路径；由 IPathService.WorkshopContent 派生）。</summary>
    public string DestinationDirectory { get; init; } = string.Empty;

    /// <summary>文件总字节数（计划值；未知时为 null，UI 诚实显示）。</summary>
    public ulong? TotalBytes { get; init; }

    /// <summary>入队时间（UTC）。</summary>
    public DateTime CreatedAtUtc { get; init; } = DateTime.UtcNow;

    /// <summary>实际使用的 provider（链回退后记录最终值，UI 提示"provider 已切换"）。</summary>
    public DownloadProvider Provider { get; init; } = DownloadProvider.SteamKitCdn;

    public DownloadTask(DownloadTaskId id, WorkshopItem item, AppId appId, string destinationDirectory)
    {
        Id = id;
        Item = item;
        AppId = appId;
        DestinationDirectory = destinationDirectory;
    }
}
