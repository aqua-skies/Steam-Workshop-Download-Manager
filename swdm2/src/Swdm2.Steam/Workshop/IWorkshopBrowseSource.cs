using Swdm2.Core.Results;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 工坊浏览数据源契约（t56 D5.17;t44 App 域 VM 的真实数据源注入点）。
/// App 域 WorkshopBrowsePageViewModel 合成样本（SampleData)与本实现
/// **按同一接口可切换注入**（依赖反转；沙箱/UI 测试走合成样本，
/// 生产走 <see cref="StoreSearchWorkshopBrowseSource"/>）。
/// 失败语义=Result&lt;T,SteamError&gt;.Fail（同 D2.3 客户端族，不抛异常污染 UI)。
/// </summary>
public interface IWorkshopBrowseSource
{
    /// <summary>
    /// 按查询取浏览条目页。
    /// </summary>
    /// <param name="query">查询（search/tag/author/sort/page 全量）。</param>
    /// <param name="ct">取消令牌。</param>
    /// <returns>成功=条目列表（深拷贝出口=缓存污染防护 C5);失败=SteamError。</returns>
    Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> FetchAsync(
        WorkshopBrowseQuery query, CancellationToken ct = default);
}
