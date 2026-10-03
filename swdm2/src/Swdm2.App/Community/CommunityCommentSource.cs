using System.Net;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Web;

namespace Swdm2.App.Community;

/// <summary>
/// 社区详情页**评论**源（D5.6;D2.5 契约的 App 域消费侧补充）。
/// ICommunitySource.EnrichDetailAsync 只回 WorkshopItem 富化（不回 HTML)，
/// 评论区需同一详情页 HTML→本源独立拉取同一 URL:
/// - **共享 community-detail 节流桶**（ThrottleBuckets.CommunityDetail:与
///   CommunityPageSource.EnrichDetailAsync 同桶=1.x 学费"详情页节流"语义不变）
/// - 可达门（S4 直译：未验证可达=Direct/ViaProxy 时 0 请求）
/// - 熔断器（连续失败保护；D2.4)
/// - 指纹头：经 D2.1 IHttpClientFactory(Accept-Language 承重头=1.x 429 学费）
/// 评论解析失败 → 空列表（UI 诚实降级"解析失败/无评论"），不返回半假数据。
/// </summary>
public interface ICommentSource
{
    /// <summary>获取某工坊物品的评论区（空列表=解析无评论/失败；Result 失败=不可达/HTTP 错误）。</summary>
    Task<Result<IReadOnlyList<WorkshopComment>, SteamError>> GetCommentsAsync(
        PublishedFileId id, CancellationToken ct = default);
}

public sealed class CommunityCommentSource : ICommentSource
{
    private readonly IHttpClientFactory _factory;
    private readonly IConnectivityState? _connectivity;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;

    public CommunityCommentSource(IHttpClientFactory factory,
        IConnectivityState? connectivity = null,
        IThrottler? throttler = null,
        ICircuitBreaker? breaker = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _connectivity = connectivity;
        _throttler = throttler;
        _breaker = breaker;
    }

    /// <summary>获取某工坊物品的评论区（空列表=解析无评论/失败；Result 失败=不可达/HTTP 错误）。</summary>
    public async Task<Result<IReadOnlyList<WorkshopComment>, SteamError>> GetCommentsAsync(
        PublishedFileId id, CancellationToken ct = default)
    {
        if (!IsCommunityReachable())
            return Result<IReadOnlyList<WorkshopComment>, SteamError>.Fail(SteamError.Network);

        var url = $"https://steamcommunity.com/sharedfiles/filedetails/?id={id.Value}&l=schinese";
        var htmlResult = await ResiliencePipeline.ExecuteAsync(
            ThrottleBuckets.CommunityDetail, _throttler, _breaker,
            async token =>
            {
                var clientResult = _factory.CreateClient();
                if (!clientResult.IsOk)
                    return Result<string, SteamError>.Fail(clientResult.Error ?? SteamError.None);

                using var client = clientResult.Value!;
                using var response = await client.GetAsync(url, token).ConfigureAwait(false);
                if (response.StatusCode == HttpStatusCode.TooManyRequests)
                    return Result<string, SteamError>.Fail(SteamError.RateLimited);
                if (response.StatusCode == HttpStatusCode.Forbidden)
                    return Result<string, SteamError>.Fail(SteamError.Blocked);
                if (response.StatusCode == HttpStatusCode.NotFound)
                    return Result<string, SteamError>.Fail(SteamError.NotFound);
                if (!response.IsSuccessStatusCode)
                    return Result<string, SteamError>.Fail(SteamError.Network);

                var html = await response.Content.ReadAsStringAsync(token).ConfigureAwait(false);
                return Result<string, SteamError>.Ok(html);
            }, ct).ConfigureAwait(false);

        if (!htmlResult.IsOk)
            return Result<IReadOnlyList<WorkshopComment>, SteamError>.Fail(htmlResult.Error ?? SteamError.None);

        // 解析失败=空列表（诚实降级，非半假数据）
        var comments = CommunityCommentParser.ParseComments(htmlResult.Value);
        return Result<IReadOnlyList<WorkshopComment>, SteamError>.Ok(comments);
    }

    /// <summary>门（S4):仅 Direct/ViaProxy 放行；Unknown 亦拦截（未探测不调用）。</summary>
    private bool IsCommunityReachable()
    {
        if (_connectivity is null) return true; // 未注入=不做门（测试/离线 fixture 路径）
        if (!_connectivity.Current.TryGetValue(EndpointKind.Community, out var status))
            return false;
        var reach = status.Reach;
        return reach == Reachability.Direct || reach == Reachability.ViaProxy;
    }
}
