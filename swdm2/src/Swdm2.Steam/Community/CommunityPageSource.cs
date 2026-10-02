using System.Net;
using Swdm2.Core.Caching;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Connectivity;

namespace Swdm2.Steam.Community;

/// <summary>
/// 社区页面 HTTP 源（D2.5）：
/// - 可达门（S4）：Community 端点未验证可达（Unknown/Blocked/Unreachable）→ Fail(Network) **0 请求**；
/// - 节流：browse→community-detail/browse bucket（D2.4 ThrottleBuckets）+熔断器（连续失败保护）；
/// - 缓存：D1.6 IAsyncCache（出口深拷贝——1.x api_cache 污染学费的 C# 断言化）；
/// - 指纹头：经 D2.1 IHttpClientFactory 携带 Accept-Language 承重头（1.x 429 学费）。
/// </summary>
public sealed class CommunityPageSource : ICommunitySource
{
    private readonly IHttpClientFactory _factory;
    private readonly IConnectivityState? _connectivity;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;
    private readonly IAsyncCache<string, IReadOnlyList<WorkshopItem>>? _browseCache;
    private readonly IAsyncCache<string, WorkshopItem>? _detailCache;
    private readonly ProxyMode _proxyMode;

    /// <summary>⚠️[参数待重标定] 社区列表缓存 TTL（起点 10min；D2.6 无覆盖——元数据变更低频）。</summary>
    public static readonly TimeSpan DefaultBrowseTtl = TimeSpan.FromMinutes(10);

    /// <summary>⚠️[参数待重标定] 社区详情缓存 TTL（起点 30min）。</summary>
    public static readonly TimeSpan DefaultDetailTtl = TimeSpan.FromMinutes(30);

    public CommunityPageSource(IHttpClientFactory factory,
        IConnectivityState? connectivity = null,
        ProxyMode proxyMode = ProxyMode.SystemProxy,
        IThrottler? throttler = null,
        ICircuitBreaker? breaker = null,
        IAsyncCache<string, IReadOnlyList<WorkshopItem>>? browseCache = null,
        IAsyncCache<string, WorkshopItem>? detailCache = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _connectivity = connectivity;
        _proxyMode = proxyMode;
        _throttler = throttler;
        _breaker = breaker;
        _browseCache = browseCache;
        _detailCache = detailCache;
    }

    public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> BrowseAsync(AppId appId, CancellationToken ct = default)
    {
        var cacheKey = $"community:browse:{appId.Value}";
        if (_browseCache is null)
            return FetchBrowseAsync(appId, ct);

        return CachedAsync(_browseCache, cacheKey, token => FetchBrowseAsync(appId, token), DefaultBrowseTtl, ct);
    }

    public Task<Result<WorkshopItem, SteamError>> EnrichDetailAsync(PublishedFileId id, CancellationToken ct = default)
    {
        var cacheKey = $"community:detail:{id.Value}";
        if (_detailCache is null)
            return FetchDetailAsync(id, ct);

        return CachedAsync(_detailCache, cacheKey, token => FetchDetailAsync(id, token), DefaultDetailTtl, ct);
    }

    /// <summary>
    /// 缓存衔接：Result 与缓存工厂（裸值语义）的边界转换——失败以 <see cref="CommunityFetchException"/>
    /// 携带错误码抛出（D1.6 契约：工厂异常传播且**不缓存失败结果**），边界再还原为 Result.Fail。
    /// </summary>
    private static async Task<Result<TValue, SteamError>> CachedAsync<TValue>(
        IAsyncCache<string, TValue> cache, string key,
        Func<CancellationToken, Task<Result<TValue, SteamError>>> fetch, TimeSpan ttl, CancellationToken ct)
        where TValue : class
    {
        try
        {
            var value = await cache.GetOrAddAsync(key,
                async token =>
                {
                    var r = await fetch(token).ConfigureAwait(false);
                    if (!r.IsOk)
                        throw new CommunityFetchException(r.Error ?? SteamError.None);
                    return r.Value!;
                }, ttl, ct).ConfigureAwait(false);
            return value is null
                ? Result<TValue, SteamError>.Fail(SteamError.Network)
                : Result<TValue, SteamError>.Ok(value);
        }
        catch (CommunityFetchException ex)
        {
            return Result<TValue, SteamError>.Fail(ex.Error);
        }
    }

    private sealed class CommunityFetchException(SteamError error) : Exception("community fetch failed")
    {
        public SteamError Error { get; } = error;
    }

    private async Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> FetchBrowseAsync(AppId appId, CancellationToken ct)
    {
        if (!IsCommunityReachable())
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Network);

        var url = $"https://steamcommunity.com/workshop/browse/?appid={appId.Value}&l=schinese";
        var htmlResult = await GetHtmlAsync(url, ThrottleBuckets.CommunityBrowse, ct).ConfigureAwait(false);
        if (!htmlResult.IsOk)
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(htmlResult.Error ?? SteamError.None);

        var parsed = CommunityHtmlParser.ParseBrowse(htmlResult.Value!, appId);
        if (parsed.Count == 0)
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Deserialization);

        var items = parsed.Select(p => new WorkshopItem(p.Id, appId, p.Title) { PreviewUrl = p.PreviewUrl }).ToArray();
        return Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(items);
    }

    private async Task<Result<WorkshopItem, SteamError>> FetchDetailAsync(PublishedFileId id, CancellationToken ct)
    {
        if (!IsCommunityReachable())
            return Result<WorkshopItem, SteamError>.Fail(SteamError.Network);

        var url = $"https://steamcommunity.com/sharedfiles/filedetails/?id={id.Value}&l=schinese";
        var htmlResult = await GetHtmlAsync(url, ThrottleBuckets.CommunityDetail, ct).ConfigureAwait(false);
        if (!htmlResult.IsOk)
            return Result<WorkshopItem, SteamError>.Fail(htmlResult.Error ?? SteamError.None);

        var html = htmlResult.Value!;
        var title = CommunityHtmlParser.TryParseTitle(html);
        var appId = CommunityHtmlParser.TryParseAppId(html);
        if (string.IsNullOrWhiteSpace(title) || appId is null)
            return Result<WorkshopItem, SteamError>.Fail(SteamError.Deserialization);

        var item = new WorkshopItem(id, appId, title)
        {
            Creator = CommunityHtmlParser.TryParseCreator(html),
            PreviewUrl = CommunityHtmlParser.TryParsePreview(html),
        };
        return Result<WorkshopItem, SteamError>.Ok(item);
    }

    /// <summary>门（S4）：仅 Direct/ViaProxy 已验证可达时放行；Unknown 亦拦截（未探测不调用）。</summary>
    private bool IsCommunityReachable()
    {
        if (_connectivity is null) return true; // 未注入状态=不做门（测试/离线 fixture 路径）
        if (!_connectivity.Current.TryGetValue(EndpointKind.Community, out var status))
            return false;
        var reach = status.Reach;
        return reach == Reachability.Direct || reach == Reachability.ViaProxy;
    }

    private async Task<Result<string, SteamError>> GetHtmlAsync(string url, string bucket, CancellationToken ct)
    {
        var pipelineResult = await ResiliencePipeline.ExecuteAsync(
            bucket, _throttler, _breaker,
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

        return pipelineResult;
    }
}
