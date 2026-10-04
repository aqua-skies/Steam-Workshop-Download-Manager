using System.Globalization;
using System.Net;
using System.Text.RegularExpressions;
using Swdm2.Core.Caching;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Community;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// 社区 HTML 工坊浏览源（D9.2/t68;真实工坊条目）。
/// GET https://steamcommunity.com/workshop/browse/?appid={appId}&amp;browsesort=totaluniquesubscribers&amp;p={page}
/// （匿名；本机实测 200+30 真实条目 id/标题/预览图）。
///
/// **为什么不是 storesearch 载体**（t56 的 StoreSearchWorkshopBrowseSource):
/// storesearch 返回**游戏级 AppId**(id=AppId 不是 PublishedFileId)=不能直接下载；
/// 用户"下载功能是摆设"根因=Browse 展示的是游戏列表 sample 而非可下载的工坊 mod。
/// 本源条目 Id=**真实 PublishedFileId**(sharedfiles/filedetails?id=...)=下载链可直接消费。
///
/// **1.x 学费防护四件套**（同 storesearch 源）：
/// 1. 指纹头=SteamHttpClientFactory 默认头（Accept-Language;1.x 429 学费）
/// 2. 节流桶=ThrottleBuckets.CommunityBrowse(t56 预留换桶点）
/// 3. 熔断=ICircuitBreaker(RateLimited/Network 计入）
/// 4. 缓存深拷贝出口（C5)
///
/// HTML 结构（2026-10 实测快照；混淆类名不稳定故用 href/img/alt 特征锚）：
/// &lt;a href="https://steamcommunity.com/sharedfiles/filedetails/?id={id}" class="..."&gt;
///   &lt;img src="{preview}" alt="{title}" .../&gt;
/// 旧版 &lt;div class="workshopItemTitle"&gt; 已被 React 化替换=正则取 img alt。
/// </summary>
public sealed class CommunityWorkshopBrowseSource : IWorkshopBrowseSource
{
    private const string CommunityBrowseEndpoint = "https://steamcommunity.com/workshop/browse/";

    /// <summary>作者名（页面条目块内"创作者：X"a 标签；t68 实测快照可解析）。</summary>
    private static readonly Regex AuthorPattern = new(
        @"创作者：([^<]{1,80})</a>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant,
        TimeSpan.FromSeconds(1));

    private readonly IHttpClientFactory _factory;
    private readonly IAsyncCache<string, WorkshopBrowsePage>? _cache;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;
    private readonly TimeSpan _timeout;
    private readonly Func<string, string> _endpointOverride;
    private readonly TimeSpan _cacheTtl; // ⚠️[参数待重标定] 60s 起点

    public CommunityWorkshopBrowseSource(IHttpClientFactory factory,
        IAsyncCache<string, WorkshopBrowsePage>? cache = null,
        IThrottler? throttler = null, ICircuitBreaker? breaker = null,
        TimeSpan? timeout = null, Func<string, string>? endpointOverride = null,
        TimeSpan? cacheTtl = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _cache = cache;
        _throttler = throttler;
        _breaker = breaker;
        _timeout = timeout ?? TimeSpan.FromSeconds(20);
        _endpointOverride = endpointOverride ?? (_ => CommunityBrowseEndpoint);
        _cacheTtl = cacheTtl ?? TimeSpan.FromSeconds(60);
    }

    public Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> FetchAsync(
        WorkshopBrowseQuery query, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (string.IsNullOrWhiteSpace(query.SearchText))
            return Task.FromResult(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
                .Fail(SteamError.InvalidConfiguration));

        if (_cache is null)
            return ResiliencePipeline.ExecuteAsync(ThrottleBuckets.CommunityBrowse, _throttler, _breaker,
                _ => CoreFetchAsync(query, ct), ct);
        return CachedFetchAsync(query, ct);
    }

    private async Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> CachedFetchAsync(
        WorkshopBrowseQuery query, CancellationToken ct)
    {
        var cached = _cache ?? throw new InvalidOperationException("cache path requires cache");
        var page = await cached.GetOrAddAsync(query.CacheKey,
            async token =>
            {
                var result = await ResiliencePipeline.ExecuteAsync(
                    ThrottleBuckets.CommunityBrowse, _throttler, _breaker, _ => CoreFetchAsync(query, token), token)
                    .ConfigureAwait(false);
                if (!result.IsOk)
                    throw new WorkshopSourceException(result.Error ?? SteamError.None);
                return new WorkshopBrowsePage(result.Value!);
            }, _cacheTtl, ct).ConfigureAwait(false);
        return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
            .Ok((page ?? throw new WorkshopSourceException(SteamError.None)).Entries);
    }

    /// <summary>不经缓存/弹性的核心请求体（HTTP+HTML 解析）。</summary>
    private async Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> CoreFetchAsync(
        WorkshopBrowseQuery query, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
                .Fail(clientResult.Error ?? SteamError.None);
        using var client = clientResult.Value!;
        client.Timeout = _timeout;

        // 搜索词=AppId（工坊浏览按游戏分类；文本搜索走 Steam 自身 query 参数）
        var queryStr = "appid=" + Uri.EscapeDataString(query.SearchText!.Trim())
            + "&browsesort=totaluniquesubscribers&sort=totaluniquesubscribers&actualsort=totaluniquesubscribers"
            + "&p=" + Math.Max(1, query.Page)
            + (query.PageSize > 0 ? "&numm=" + query.PageSize : "");
        var builder = new UriBuilder(new Uri(_endpointOverride(CommunityBrowseEndpoint))) { Query = queryStr };

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(_timeout);

        HttpResponseMessage response;
        try
        {
            response = await client.GetAsync(builder.Uri, cts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return Fail(SteamError.Timeout);
        }
        catch (OperationCanceledException)
        {
            return Fail(SteamError.Cancelled);
        }
        catch (HttpRequestException)
        {
            return Fail(SteamError.Network);
        }
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                return Fail(MapHttpStatus(response.StatusCode));
            try
            {
                var html = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                // AppId 来自查询词（SearchText=appid 字符串）
                var appId = int.TryParse(query.SearchText, System.Globalization.NumberStyles.Integer,
                    System.Globalization.CultureInfo.InvariantCulture, out var appVal) && appVal > 0
                    ? new AppId(appVal) : new AppId(0);
                var entries = ParseEntries(html, appId);
                return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Ok(entries);
            }
            catch
            {
                return Fail(SteamError.Deserialization);
            }
        }
    }

    /// <summary>HTML→条目解析（复用 CommunityHtmlParser.ParseBrowse=D2.5 稳定锚；作者=块内"创作者：X"增强）。</summary>
    public static IReadOnlyList<WorkshopBrowseEntry> ParseEntries(string html, AppId appId)
    {
        var items = CommunityHtmlParser.ParseBrowse(html, appId);
        var list = new List<WorkshopBrowseEntry>(items.Count);
        foreach (var item in items)
        {
            // 作者=同一条目块内"创作者：X"（ParseBrowse 不含作者=D2.5 未落该字段；
            // 以 id 字符串定位锚点窗口）
            string? author = null;
            var anchorIdx = html.IndexOf(
                item.Id.Value.ToString(System.Globalization.CultureInfo.InvariantCulture),
                System.StringComparison.Ordinal);
            if (anchorIdx >= 0)
            {
                var tailLen = Math.Min(2500, html.Length - anchorIdx);
                var am = AuthorPattern.Match(html, anchorIdx, tailLen);
                if (am.Success)
                    author = WebUtility.HtmlDecode(am.Groups[1].Value.Trim());
            }
            list.Add(new WorkshopBrowseEntry(
                Id: item.Id.Value.ToString(System.Globalization.CultureInfo.InvariantCulture),
                Title: string.IsNullOrWhiteSpace(item.Title) ? $"工坊物品 {item.Id.Value}" : item.Title,
                Author: author,
                Tags: Array.Empty<string>(),
                Subscribers: null,           // 订阅数无稳定文本锚=诚实 null（详情页补）
                UpdatedAt: null,
                PreviewImageUrl: string.IsNullOrEmpty(item.PreviewUrl) ? null : item.PreviewUrl));
        }
        return list;
    }

    private static Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError> Fail(SteamError err)
        => Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Fail(err);

    private static SteamError MapHttpStatus(HttpStatusCode status) => status switch
    {
        HttpStatusCode.TooManyRequests => SteamError.RateLimited,
        HttpStatusCode.Forbidden => SteamError.Blocked,
        HttpStatusCode.NotFound => SteamError.NotFound,
        _ => SteamError.Network,
    };

    private sealed class WorkshopSourceException(SteamError error) : Exception($"workshop source: {error}")
    {
        public SteamError Error { get; } = error;
    }
}
