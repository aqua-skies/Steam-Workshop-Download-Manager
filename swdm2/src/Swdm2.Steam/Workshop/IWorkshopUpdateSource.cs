using Swdm2.Core.Results;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 工坊更新检查源契约（D6.2;t59;t51 库页消费）。
/// 复用 D5.6/t45 批量详情链（ISteamWebApiClient.GetPublishedFileDetailsBatchAsync):
/// 指纹头（工厂承重头 Accept-Language)+Api 节流桶+熔断；失败语义=Result Fail
/// 不抛异常污染 UI。合成/真实源可切换注入（依赖反转同 t56)。
/// 社区 HTML 回退：详情页链（CommunityPageSource,t45）负责；更新检查走 API
/// 单链（time_updated 字段足够），API 全失败=VM 错误态诚实降级（不造假候选）。
/// </summary>
public interface IWorkshopUpdateSource
{
    /// <summary>
    /// 批量检查已安装 mod 的远端更新。
    /// </summary>
    /// <param name="installed">库扫描出的已安装快照。</param>
    /// <param name="ct">取消令牌。</param>
    /// <returns>成功=更新候选列表（深拷贝出口语义；可为空）;失败=SteamError。</returns>
    Task<Result<IReadOnlyList<ModUpdateCandidate>, SteamError>> CheckUpdatesAsync(
        IReadOnlyList<InstalledModSnapshot> installed, CancellationToken ct = default);
}
