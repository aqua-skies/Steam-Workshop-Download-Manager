namespace Swdm2.Steam.Workshop;

/// <summary>
/// 工坊浏览查询（t56 D5.17;契约与 t44 App 域 WorkshopBrowsePageViewModel 对齐：
/// filter/search/tag/author/sort/page 全量字段——端点只支持 term 时，其余字段
/// 的处理/降级由实现诚实标注）。
/// </summary>
/// <param name="SearchText">搜索词（storesearch term)。空=InvalidConfiguration 直拒。</param>
/// <param name="Tag">标签筛选（storesearch 不支持=诚实透传，社区源 D5.x 才生效）。</param>
/// <param name="Author">作者筛选（同上）。</param>
/// <param name="SortKey">排序键。</param>
/// <param name="SortDescending">降序。</param>
/// <param name="Page">页号（1 基）。</param>
/// <param name="PageSize">每页大小（0=全部）。</param>
public sealed record WorkshopBrowseQuery(
    string? SearchText = null,
    string? Tag = null,
    string? Author = null,
    WorkshopBrowseSortKey SortKey = WorkshopBrowseSortKey.Title,
    bool SortDescending = false,
    int Page = 1,
    int PageSize = 100)
{
    /// <summary>缓存键指纹（查询全字段 → 缓存按查询隔离）。</summary>
    public string CacheKey =>
        $"wb|t={SearchText ?? string.Empty}|tag={Tag ?? string.Empty}|au={Author ?? string.Empty}" +
        $"|sk={SortKey}|d={SortDescending}|p={Math.Max(1, Page)}|ps={PageSize}";
}

/// <summary>排序键（镜像 App 域 BrowseSortKey 语义）。</summary>
public enum WorkshopBrowseSortKey
{
    /// <summary>标题（storesearch 唯一客户端可排键）。</summary>
    Title = 0,
    /// <summary>订阅数（社区源字段；storesearch 缺=排序无效化提示见实现）。</summary>
    Subscribers = 1,
    /// <summary>更新时间（同上）。</summary>
    UpdatedAt = 2,
}
