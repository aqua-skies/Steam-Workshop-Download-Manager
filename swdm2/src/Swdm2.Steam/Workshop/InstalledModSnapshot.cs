using Swdm2.Core.Domain;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 已安装 mod 快照（D6.2 更新检查入参；t59):
/// - ItemId:库扫描出的 PublishedFileId;
/// - LocalLastUpdatedUtc:本地安装时记录的物品远端时间戳（t51 库扫描
///   ModLibraryEntry.ItemLastUpdatedUtc / 下载完成落盘值）。**null=未知**
///   （首次安装未记录或旧版数据）→ 更新判定保守跳过（不报假更新）。
/// </summary>
public sealed record InstalledModSnapshot(PublishedFileId ItemId, DateTime? LocalLastUpdatedUtc = null);
