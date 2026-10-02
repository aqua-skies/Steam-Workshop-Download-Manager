using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Connectivity;

namespace Swdm2.Steam.Web;

/// <summary>
/// Steam Web API 客户端契约（spec §3.2）：元数据主源（匿名可用且完整的 api.steampowered.com 端点）。
/// </summary>
public interface ISteamWebApiClient
{
    /// <summary>单个工坊物品详情（匿名 GetDetails v1,itemcount=1)。</summary>
    Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(PublishedFileId id, CancellationToken ct = default);

    /// <summary>批量物品详情（itemcount=N 批量封包，SO #56018823；itemids 一次请求多个）。</summary>
    Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
        IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default);

    /// <summary>集合详情（递归展开嵌套子集合为扁平后代列表）。</summary>
    Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(PublishedFileId collectionId, CancellationToken ct = default);
}

/// <summary>
/// storesearch 游戏搜索契约（spec §3.2）：匿名无 key,l=schinese&cc=CN,id 即 AppId（研究阶段实证）。
/// </summary>
public interface IStoreSearchClient
{
    /// <summary>按名称搜索游戏（结果为原始值；别名归一化属 D5 搜索服务域）。</summary>
    Task<Result<IReadOnlyList<GameInfo>, SteamError>> SearchGamesAsync(string term, CancellationToken ct = default);
}

/// <summary>与 <see cref="ISteamWebApiClient"/> 联用的可选可达性门（D2.2 契约）。</summary>
public interface IConnectivityGate
{
    /// <summary>Api 端点是否可达（Unreachable=true 时调用方应直接返回 Network 失败，不发出请求）。</summary>
    bool IsApiUnreachable { get; }
}
