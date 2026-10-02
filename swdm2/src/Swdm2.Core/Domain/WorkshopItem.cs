namespace Swdm2.Core.Domain;

/// <summary>
/// 工坊物品（元数据快照）。C1/C5：record 不可变，集合属性只读且创建时防御性拷贝。
/// 1.x 学费：联想模型原地更新（clear+重建）导致 UI 闪烁/状态丢失——2.0 元数据一律换值不换位。
/// </summary>
public sealed record WorkshopItem
{
    /// <summary>工坊物品 id（C6：与 UgcId 类型隔离）。</summary>
    public PublishedFileId Id { get; init; }

    /// <summary>所属游戏 AppId。</summary>
    public AppId AppId { get; init; }

    /// <summary>物品标题（UI 主文本）。</summary>
    public string Title { get; init; } = string.Empty;

    /// <summary>物品描述（可空）。</summary>
    public string? Description { get; init; }

    /// <summary>文件总字节数（可空：来源未提供时）。</summary>
    public ulong? FileSize { get; init; }

    /// <summary>预览图 URL（可空）。</summary>
    public string? PreviewUrl { get; init; }

    /// <summary>作者名（可空）。</summary>
    public string? Creator { get; init; }

    /// <summary>前置依赖（只读；构造时防御性拷贝，C5）。</summary>
    public IReadOnlyList<PublishedFileId> Dependencies { get; init; } = Array.Empty<PublishedFileId>();

    /// <summary>物品最近更新时间（UTC，可空）。</summary>
    public DateTime? LastUpdatedUtc { get; init; }

    /// <summary>主构造：依赖列表创建时防御性拷贝（外部 List 的突变不污染本实例，C1/C5）。</summary>
    public WorkshopItem(PublishedFileId id, AppId appId, string title,
        IEnumerable<PublishedFileId>? dependencies = null)
    {
        Id = id;
        AppId = appId;
        Title = title;
        Dependencies = (dependencies ?? Enumerable.Empty<PublishedFileId>()).ToArray();
    }

    /// <summary>
    /// 结构性相等：集合成员逐元素比较（C5 缓存语义——缓存深拷贝出的副本必须与原值相等，
    /// 默认引用比较会让"同一物品的两个快照"不相等，破坏缓存命中判定）。
    /// </summary>
    public bool Equals(WorkshopItem? other)
    {
        if (other is null) return false;
        return Id == other.Id
            && AppId == other.AppId
            && Title == other.Title
            && Description == other.Description
            && FileSize == other.FileSize
            && PreviewUrl == other.PreviewUrl
            && Creator == other.Creator
            && LastUpdatedUtc == other.LastUpdatedUtc
            && Dependencies.SequenceEqual(other.Dependencies);
    }

    /// <summary>与 <see cref="Equals(WorkshopItem)"/> 一致的结构性哈希（依赖按元素计入）。</summary>
    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(Id);
        hash.Add(AppId);
        hash.Add(Title);
        hash.Add(Description);
        hash.Add(FileSize);
        hash.Add(PreviewUrl);
        hash.Add(Creator);
        hash.Add(LastUpdatedUtc);
        foreach (var dependency in Dependencies)
            hash.Add(dependency);
        return hash.ToHashCode();
    }
}
