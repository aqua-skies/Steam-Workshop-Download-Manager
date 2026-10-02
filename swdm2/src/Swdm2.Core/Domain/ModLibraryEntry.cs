namespace Swdm2.Core.Domain;

/// <summary>本地库条目（扫描/导入产物）。C1/C5：不可变。</summary>
public sealed record ModLibraryEntry
{
    /// <summary>工坊物品 id（与下载任务同源）。</summary>
    public PublishedFileId ItemId { get; init; }

    /// <summary>所属游戏 AppId（决定库目录）。</summary>
    public AppId AppId { get; init; }

    /// <summary>物品标题。</summary>
    public string Title { get; init; } = string.Empty;

    /// <summary>安装路径（相对 Root，扫描得出）。</summary>
    public string RelativePath { get; init; } = string.Empty;

    /// <summary>安装时间（UTC，扫描时从文件时间取）。</summary>
    public DateTime InstalledAtUtc { get; init; }

    /// <summary>物品元数据声明的更新时间（可空；用于更新检查比对）。</summary>
    public DateTime? ItemLastUpdatedUtc { get; init; }

    /// <summary>磁盘占用字节数。</summary>
    public ulong? FileSize { get; init; }

    /// <summary>是否有可用更新（D6.2 更新检查判定后写入）。</summary>
    public bool HasUpdate { get; init; }

    public ModLibraryEntry(PublishedFileId itemId, AppId appId, string title, string relativePath)
    {
        ItemId = itemId;
        AppId = appId;
        Title = title;
        RelativePath = relativePath;
    }
}
