using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using Swdm2.Core.Caching;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Workshop;

/// <summary>
/// storesearch 载体的工坊浏览源（t56 D5.17;真实实现）：
/// GET https://store.steampowered.com/api/storesearch/?term=xxx&amp;l=schinese&amp;cc=CN
/// （匿名无 key——研究阶段实证）。
///
/// **1.x 学费防护四件套**：
/// 1. 指纹头=<see cref="SteamHttpClientFactory"/> 默认头（承重头 Accept-Language:
///    1.x 裸 Chrome UA 缺该头被 429,research 3/3 实证；此处随工厂注入）；
/// 2. 节流桶=<see cref="ThrottleBuckets.Store"/>(store 域 250ms 起点值;
///    ⚠️任务原文"browse 2s 档"=社区 browse HTML 端点实测值——本实现走 store 域
///    端点故用 Store 桶；社区 HTML 源落地时换 <see cref="ThrottleBuckets.CommunityBrowse"/>);
/// 3. 熔断=<see cref="ICircuitBreaker"/>（RateLimited/Network 计入，开态 Fail(CircuitOpen));
/// 4. 缓存深拷贝=<see cref="IAsyncCache{TKey,TValue}"/>（api_cache 污染学费的
///    C# 断言化：出口深拷贝，enrich 类就地修改回不了缓存）。
///
/// **诚实降级**（设计对照纪律标注）：storesearch 载荷仅含 id/name/tiny_image;
/// Author/Tags/Subscribers/UpdatedAt 为 null/空（不造假）；Tag/Author 端点
/// 不支持=接口字段保留待社区源 D5.x;客户端排序仅 Title 生效，其他 SortKey
/// 保持端点序（相关性）并在 <see cref="LastSortDegraded"/> 标记。
/// </summary>
public sealed class StoreSearchWorkshopBrowseSource : IWorkshopBrowseSource
{
    private const string StoreSearchEndpoint = "https://store.steampowered.com/api/storesearch/";

    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    private readonly IHttpClientFactory _factory;
    private readonly IAsyncCache<string, WorkshopBrowsePage>? _cache;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;
    private readonly TimeSpan _timeout;
    private readonly Func<string, string> _endpointOverride;
    private readonly TimeSpan _cacheTtl; // ⚠️[参数待重标定] 60s 起点（同域浏览更新频率）

    /// <summary>最近一次查询的排序是否被降级（诚实标注，非断言失败）。</summary>
    public WorkshopBrowseSortKey? LastSortDegraded { get; private set; }

    public StoreSearchWorkshopBrowseSource(IHttpClientFactory factory,
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
        _timeout = timeout ?? TimeSpan.FromSeconds(15);
        _endpointOverride = endpointOverride ?? (_ => StoreSearchEndpoint);
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
            return ResiliencePipeline.ExecuteAsync(ThrottleBuckets.Store, _throttler, _breaker,
                _ => CoreFetchAsync(query, ct), ct);

        // 缓存路径：未命中→弹性管道取页；命中=深拷贝出口（AsyncCache C5 契约）
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
                    ThrottleBuckets.Store, _throttler, _breaker, _ => CoreFetchAsync(query, token), token)
                    .ConfigureAwait(false);
                // 工厂异常/失败不缓存（AsyncCache 契约：不缓存失败结果）
                if (!result.IsOk)
                    throw new WorkshopSourceException(result.Error ?? SteamError.None);
                return new WorkshopBrowsePage(result.Value!);
            }, _cacheTtl, ct).ConfigureAwait(false);
        // GetOrAddAsync 契约：工厂成功=非 null（工厂失败抛异常传播）；防御显式空检查
        return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
            .Ok((page ?? throw new WorkshopSourceException(SteamError.None)).Entries);
    }

    /// <summary>不经缓存/弹性的核心请求体（直达 HTTP+解析）。</summary>
    private async Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> CoreFetchAsync(
        WorkshopBrowseQuery query, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
                .Fail(clientResult.Error ?? SteamError.None);
        using var client = clientResult.Value!;
        client.Timeout = _timeout;

        // 查询串构造同 StoreSearchClient（显式 EscapeDataString 更确定）
        var queryStr = "term=" + Uri.EscapeDataString(query.SearchText!.Trim()) + "&l=schinese&cc=CN";
        var builder = new UriBuilder(new Uri(_endpointOverride(StoreSearchEndpoint))) { Query = queryStr };

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
                var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                var payload = await JsonSerializer.DeserializeAsync<StoreSearchBrowseResponse>(stream, JsonOptions, ct)
                    .ConfigureAwait(false);
                var items = payload?.Items ?? new List<StoreSearchBrowseItem>();
                var entries = items
                    .Where(i => !string.IsNullOrEmpty(i.Id) && !string.IsNullOrEmpty(i.Name))
                    .Select(i => new WorkshopBrowseEntry(
                        Id: i.Id!,
                        Title: i.Name!,
                        Author: null,                 // storesearch 载荷缺乏=诚实 null
                        Tags: Array.Empty<string>(),  // 同上
                        Subscribers: null,
                        UpdatedAt: null,
                        PreviewImageUrl: string.IsNullOrEmpty(i.TinyImage) ? null : i.TinyImage))
                    .ToList();
                return Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>
                    .Ok(ApplySortAndPage(entries, query));
            }
            catch (JsonException)
            {
                return Fail(SteamError.Deserialization);
            }
        }
    }

    /// <summary>客户端排序+分页（端点不支持服务端分页；Title 之外的排序键=降级保持端点序）。</summary>
    private IReadOnlyList<WorkshopBrowseEntry> ApplySortAndPage(
        List<WorkshopBrowseEntry> entries, WorkshopBrowseQuery query)
    {
        LastSortDegraded = null;
        if (query.SortKey == WorkshopBrowseSortKey.Title)
        {
            var sorted = query.SortDescending
                ? entries.OrderByDescending(e => e.Title, StringComparer.OrdinalIgnoreCase).ToList()
                : entries.OrderBy(e => e.Title, StringComparer.OrdinalIgnoreCase).ToList();
            entries = sorted;
        }
        else
        {
            // 诚实降级：Subscribers/UpdatedAt 载荷缺失=排序无效化，保持相关性序
            LastSortDegraded = query.SortKey;
        }
        if (query.PageSize <= 0) return entries;
        var page = Math.Max(1, query.Page);
        return entries.Skip((page - 1) * query.PageSize).Take(query.PageSize).ToList();
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

    /// <summary>缓存失败不缓存的传播异常（Cache 工厂失败语义）。</summary>
    private sealed class WorkshopSourceException(SteamError error) : Exception($"workshop source: {error}")
    {
        public SteamError Error { get; } = error;
    }
}

/// <summary>缓存页载体（可深拷贝集合）。</summary>
public sealed record WorkshopBrowsePage(IReadOnlyList<WorkshopBrowseEntry> Entries);

/// <summary>storesearch 响应载荷（D2.3 同构）。</summary>
internal sealed class StoreSearchBrowseResponse
{
    [JsonPropertyName("total")]
    public int Total { get; set; }
    [JsonPropertyName("items")]
    public List<StoreSearchBrowseItem> Items { get; set; } = new();
}

internal sealed class StoreSearchBrowseItem
{
    [JsonPropertyName("type")]
    public string? Type { get; set; }
    [JsonPropertyName("id")]
    public string? Id { get; set; }
    [JsonPropertyName("name")]
    public string? Name { get; set; }
    [JsonPropertyName("tiny_image")]
    public string? TinyImage { get; set; }
}
