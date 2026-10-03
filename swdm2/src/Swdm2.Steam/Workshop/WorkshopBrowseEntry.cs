namespace Swdm2.Steam.Workshop;

/// <summary>
/// 工坊浏览条目（t56 D5.17):
/// - Id:storesearch 载体=AppId（字符串形式）；社区源落地后=PublishedFileId。
/// - Author/Tags/Subscribers/UpdatedAt:storesearch 载荷**不含**这些字段
///   （诚实 null/空，不造假——1.x "N/A 诚实不造假" 同构）。
/// - PreviewImageUrl:storesearch tiny_image（方形贴图裁剪源=t54 球体贴图/列表预览）。
/// </summary>
public sealed record WorkshopBrowseEntry(
    string Id,
    string Title,
    IReadOnlyList<string> Tags,
    string? Author = null,
    long? Subscribers = null,
    DateTimeOffset? UpdatedAt = null,
    string? PreviewImageUrl = null)
{
    /// <summary>真不可变 Tags（数组防御性拷贝；1.x 原地更新闪烁学费）。</summary>
    public IReadOnlyList<string> Tags { get; } = Tags;
}
