using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 真实更新检查器（D6.2;t59):库扫描快照→分块批量 GetPublishedFileDetails
/// （IPublishedFileService/GetDetails v1;复用 t45 链：指纹头+Api 节流桶+熔断，
/// 全在 <see cref="ISteamWebApiClient"/> 内）→时间戳对比→候选列表。
/// **参数裁决（⚠️[参数待重标定]，经验复验纪律）**:BatchSize=50 起点值
/// （单 POST itemcount=50；1.x 单请求上限未实测→保守分块；后续按真实接口
/// 响应/429 行为重标定）。对比规则=远端 time_updated 严格新于本地，本地
/// 未知=不报（诚实，1.x 假更新学费同族）。
/// </summary>
public sealed class WorkshopUpdateChecker : IWorkshopUpdateSource
{
    private readonly ISteamWebApiClient _api;
    private readonly int _batchSize;

    /// <param name="api">t45 批量详情客户端（弹性链在其内）。</param>
    /// <param name="batchSize">单次批量大小（默认 50;≤0=不分块）。</param>
    public WorkshopUpdateChecker(ISteamWebApiClient api, int batchSize = 50)
    {
        ArgumentNullException.ThrowIfNull(api);
        _api = api;
        _batchSize = batchSize <= 0 ? int.MaxValue : batchSize;
    }

    public async Task<Result<IReadOnlyList<ModUpdateCandidate>, SteamError>> CheckUpdatesAsync(
        IReadOnlyList<InstalledModSnapshot> installed, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(installed);
        if (installed.Count == 0)
            return Result<IReadOnlyList<ModUpdateCandidate>, SteamError>.Ok(Array.Empty<ModUpdateCandidate>());

        var candidates = new List<ModUpdateCandidate>();
        for (var skip = 0; skip < installed.Count; skip += _batchSize)
        {
            var chunk = installed.Skip(skip).Take(_batchSize).ToList();
            var ids = chunk.Select(s => s.ItemId).ToList();
            var batch = await _api.GetPublishedFileDetailsBatchAsync(ids, ct).ConfigureAwait(false);
            if (!batch.IsOk)
                return Result<IReadOnlyList<ModUpdateCandidate>, SteamError>.Fail(batch.Error ?? SteamError.None);

            // 远端时间戳严格新于本地=候选；本地基线未知=无法判定=不报（诚实，
            // 1.x 假更新学费同族；VM 侧 InstalledAtUtc 兜底保证库路径基线非空）
            var byId = chunk.ToDictionary(s => s.ItemId.Value);
            foreach (var remote in batch.Value!)
            {
                if (!byId.TryGetValue(remote.Id.Value, out var local))
                    continue;
                if (!remote.LastUpdatedUtc.HasValue)
                    continue; // 远端无时间戳=无法判定
                if (!local.LocalLastUpdatedUtc.HasValue)
                    continue; // 本地基线未知=无法判定=不报假更新
                if (remote.LastUpdatedUtc.Value <= local.LocalLastUpdatedUtc.Value)
                    continue; // 本地新于或等于远端=无更新
                candidates.Add(new ModUpdateCandidate(
                    ItemId: remote.Id,
                    RemoteItem: remote,
                    RemoteLastUpdatedUtc: remote.LastUpdatedUtc.Value,
                    LocalLastUpdatedUtc: local.LocalLastUpdatedUtc));
            }
        }
        return Result<IReadOnlyList<ModUpdateCandidate>, SteamError>.Ok(candidates);
    }
}
