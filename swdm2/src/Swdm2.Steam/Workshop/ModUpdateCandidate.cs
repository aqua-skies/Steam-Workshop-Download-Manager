using Swdm2.Core.Domain;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 更新候选（D6.2;t59):远端时间戳新于本地安装记录条目。
/// **诚实判定**：仅 RemoteLastUpdatedUtc &gt; LocalLastUpdatedUtc 出候选；
/// 本地时间戳未知（null)=不报更新（1.x 假更新学费对照——宁可漏报不谎报）。
/// </summary>
/// <param name="RemoteItem">远端元数据快照（UI 入队复用，免二次请求）。</param>
public sealed record ModUpdateCandidate(
    PublishedFileId ItemId,
    WorkshopItem RemoteItem,
    DateTime RemoteLastUpdatedUtc,
    DateTime? LocalLastUpdatedUtc = null)
{
    /// <summary>可读差异（仅 UI 展示用；远端-本地时间差）。</summary>
    public TimeSpan Age => LocalLastUpdatedUtc.HasValue
        ? RemoteLastUpdatedUtc - LocalLastUpdatedUtc.Value
        : TimeSpan.Zero;
}
