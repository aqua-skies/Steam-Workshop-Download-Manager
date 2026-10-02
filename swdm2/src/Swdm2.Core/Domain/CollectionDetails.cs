namespace Swdm2.Core.Domain;

/// <summary>
/// 工坊集合（含递归展开后的全部后代 id）。C1/C5：不可变 record，集合防御性拷贝。
/// </summary>
public sealed record CollectionDetails
{
    /// <summary>集合自身的物品 id。</summary>
    public PublishedFileId Id { get; init; }

    /// <summary>集合标题（取自集合自身的 details；GetCollectionDetails 端点本身不返回标题）。</summary>
    public string Title { get; init; } = string.Empty;

    /// <summary>递归展开后的全部后代物品 id（嵌套集合已展平；ReadOnlyList 防御性拷贝）。</summary>
    public IReadOnlyList<PublishedFileId> ChildIds { get; init; } = Array.Empty<PublishedFileId>();

    public CollectionDetails(PublishedFileId id, string title, IEnumerable<PublishedFileId>? childIds = null)
    {
        Id = id;
        Title = title;
        ChildIds = (childIds ?? Enumerable.Empty<PublishedFileId>()).ToArray();
    }

    public bool Equals(CollectionDetails? other)
        => other is not null && Id == other.Id && Title == other.Title && ChildIds.SequenceEqual(other.ChildIds);

    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(Id);
        hash.Add(Title);
        foreach (var child in ChildIds) hash.Add(child);
        return hash.ToHashCode();
    }
}
