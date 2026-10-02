using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Community;

/// <summary>
/// 社区页面回退源（D2.5）：Web API 不可用/字段缺失时的补充元数据通道。
/// 仅在 Community 端点**已验证可达**（D2.2 IConnectivityState 为 Direct/ViaProxy）时调用；
/// Unknown/Blocked/Unreachable 直接 Fail(Network) 且 0 请求发出（S4 不可达不调用）。
/// 1.x 学费：社区页 429 指纹头由 D2.1 工厂携带（Accept-Language 承重头）。
/// </summary>
public interface ICommunitySource
{
    /// <summary>浏览某游戏的工坊物品列表（按页抓取 HTML 解析）。</summary>
    Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> BrowseAsync(AppId appId, CancellationToken ct = default);

    /// <summary>详情富化（标题/作者/预览图——API 缺失字段的回退填充）。</summary>
    Task<Result<WorkshopItem, SteamError>> EnrichDetailAsync(PublishedFileId id, CancellationToken ct = default);
}
