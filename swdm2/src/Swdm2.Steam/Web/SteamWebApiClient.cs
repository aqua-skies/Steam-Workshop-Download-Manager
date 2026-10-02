using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Resilience;

namespace Swdm2.Steam.Web;

/// <summary>
/// Steam Web API 客户端默认实现（D2.3）：
/// - GET/POST 经 <see cref="IHttpClientFactory"/>（D2.1：ProxyMode + 指纹头四件套）；
/// - 可达性门（<see cref="IConnectivityGate"/>):Api 端点 Unreachable 时直接返回 Network 失败，不发出请求（S4 尊重不可达，避免无谓重放）；
/// - 失败映射 <see cref="SteamError"/>（HTTP 429→RateLimited、403→Blocked、404→NotFound、401→AuthRequired、
///   超时→Timeout、网络层→Network、JSON 解析→Deserialization、取消→Cancelled、业务 result!=1→NotFound),
///   **绝不以业务异常形式抛出**（D1.1 结果模型纪律）。
/// </summary>
public sealed class SteamWebApiClient : ISteamWebApiClient
{
    private const string DetailsEndpoint = "https://api.steampowered.com/IPublishedFileService/GetDetails/v1/";
    private const string CollectionEndpoint = "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    private readonly IHttpClientFactory _factory;
    private readonly IConnectivityGate? _gate;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;
    private readonly TimeSpan _timeout;
    private readonly Func<string, string> _endpointOverride;

    /// <param name="factory">D2.1 工厂。</param>
    /// <param name="gate">可选可达性门（null=不设防，直接请求）。</param>
    /// <param name="throttler">可选节流器（D2.4;bucket=<see cref="ThrottleBuckets.Api"/>)。</param>
    /// <param name="breaker">可选熔断器（D2.4;失败计入熔断，开态直接 Fail(CircuitOpen))。</param>
    /// <param name="timeout">单请求超时（默认 15s;⚠️[参数待重标定] D2.4 节流/熔断接管后由其统一）。</param>
    /// <param name="endpointOverride">测试注入：入参=真实端点 URL，出参=生效 URL（保留路径以区分端点；生产 null=真实端点）。</param>
    public SteamWebApiClient(IHttpClientFactory factory, IConnectivityGate? gate = null,
                             IThrottler? throttler = null, ICircuitBreaker? breaker = null,
                             TimeSpan? timeout = null, Func<string, string>? endpointOverride = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _gate = gate;
        _throttler = throttler;
        _breaker = breaker;
        _timeout = timeout ?? TimeSpan.FromSeconds(15);
        _endpointOverride = endpointOverride ?? (_ => DetailsEndpoint);
    }

    public async Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(PublishedFileId id, CancellationToken ct = default)
    {
        var batch = await GetPublishedFileDetailsBatchAsync(new[] { id }, ct).ConfigureAwait(false);
        if (!batch.IsOk)
            return Result<WorkshopItem, SteamError>.Fail(batch.Error ?? SteamError.None);
        var item = batch.Value!.SingleOrDefault();
        return item is null
            ? Result<WorkshopItem, SteamError>.Fail(SteamError.NotFound)
            : Result<WorkshopItem, SteamError>.Ok(item);
    }

    public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
        IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default)
    {
        if (ids.Count == 0)
            return Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(Array.Empty<WorkshopItem>()));
        if (_gate?.IsApiUnreachable == true)
            return Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Network));
        // D2.4 集成：节流 acquire → 熔断门 → 请求 → 结果计熔断（bucket=api)
        return ResiliencePipeline.ExecuteAsync(ThrottleBuckets.Api, _throttler, _breaker,
            _ => CoreFetchDetailsBatchAsync(ids, ct), ct);
    }

    /// <summary>不经弹性管道的核心请求体（由 <see cref="GetPublishedFileDetailsBatchAsync"/> 包装执行）。</summary>
    private async Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> CoreFetchDetailsBatchAsync(
        IReadOnlyList<PublishedFileId> ids, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(clientResult.Error ?? SteamError.None);
        using var client = clientResult.Value!;
        client.Timeout = _timeout;

        var form = new List<KeyValuePair<string, string>> { new("itemcount", ids.Count.ToString(CultureInfo.InvariantCulture)) };
        for (var i = 0; i < ids.Count; i++)
            form.Add(new($"publishedfileids[{i}]", ids[i].Value.ToString(CultureInfo.InvariantCulture)));

        using var content = new FormUrlEncodedContent(form);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(_timeout);

        HttpResponseMessage response;
        try
        {
            response = await client.PostAsync(new Uri(_endpointOverride(DetailsEndpoint)), content, cts.Token)
                                   .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Timeout);
        }
        catch (OperationCanceledException)
        {
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Cancelled);
        }
        catch (HttpRequestException)
        {
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Network);
        }
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(MapHttpStatus(response.StatusCode));

            DetailsResponse? payload;
            try
            {
                var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                payload = await JsonSerializer.DeserializeAsync<DetailsResponse>(stream, JsonOptions, ct)
                                     .ConfigureAwait(false);
            }
            catch (JsonException)
            {
                return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Deserialization);
            }

            if (payload?.Response?.PublishedFileDetails is null or { Count: 0 })
                return Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.NotFound);

            var items = payload.Response.PublishedFileDetails
                .Where(d => d.Result == 1)
                .Select(MapToWorkshopItem)
                .Where(i => i is not null)
                .Cast<WorkshopItem>()
                .ToList();
            return Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(items);
        }
    }

    public async Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(
        PublishedFileId collectionId, CancellationToken ct = default)
    {
        if (_gate?.IsApiUnreachable == true)
            return Result<CollectionDetails, SteamError>.Fail(SteamError.Network);

        // 1) 集合标题（GetCollectionDetails 端点不返回标题，用 GetDetails batch 取自身元数据）
        var self = await GetPublishedFileDetailsAsync(collectionId, ct).ConfigureAwait(false);
        if (!self.IsOk)
            return Result<CollectionDetails, SteamError>.Fail(self.Error ?? SteamError.None);

        // BFS 递归展开：filetype=0 的子项为嵌套集合，入队下一层（深度≤6 + visited 防环——
        // 1.x 学费：Steam 集合互相引用成环导致死循环）
        var visited = new HashSet<PublishedFileId> { collectionId };
        var allChildren = new List<PublishedFileId>();
        var collectionFrontier = new Queue<PublishedFileId>();
        collectionFrontier.Enqueue(collectionId);

        for (var depth = 0; collectionFrontier.Count > 0 && depth < 6; depth++)
        {
            var levelCount = collectionFrontier.Count;
            for (var i = 0; i < levelCount; i++)
            {
                var current = collectionFrontier.Dequeue();
                var children = await FetchCollectionChildrenAsync(current, ct).ConfigureAwait(false); // 内部已含节流/熔断包装
                if (!children.IsOk)
                    continue; // 嵌套子集合不可达不致整体失败（S4：不可达不调用/失败容忍）
                foreach (var entry in children.Value!)
                {
                    if (visited.Add(entry.Id))
                    {
                        allChildren.Add(entry.Id);
                        if (entry.FileType == 0) collectionFrontier.Enqueue(entry.Id); // 0=Collection
                    }
                }
            }
        }
        return Result<CollectionDetails, SteamError>.Ok(
            new CollectionDetails(collectionId, self.Value!.Title, allChildren));
    }

    /// <summary>取集合直系子项（单级；filetype=0 的子项为嵌套集合）。</summary>
    private async Task<Result<IReadOnlyList<CollectionChildEntry>, SteamError>> FetchCollectionChildrenAsync(
        PublishedFileId collectionId, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(clientResult.Error ?? SteamError.None);
        using var client = clientResult.Value!;
        client.Timeout = _timeout;

        var form = new List<KeyValuePair<string, string>>
        {
            new("collectioncount", "1"),
            new("publishedfileids[0]", collectionId.Value.ToString(CultureInfo.InvariantCulture)),
        };
        using var content = new FormUrlEncodedContent(form);
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(_timeout);

        HttpResponseMessage response;
        try
        {
            response = await client.PostAsync(new Uri(_endpointOverride(CollectionEndpoint)), content, cts.Token)
                                   .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(SteamError.Timeout);
        }
        catch (HttpRequestException)
        {
            return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(SteamError.Network);
        }
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(MapHttpStatus(response.StatusCode));
            try
            {
                var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                var payload = await JsonSerializer.DeserializeAsync<CollectionResponse>(stream, JsonOptions, ct)
                                      .ConfigureAwait(false);
                var children = payload?.Response?.Collections?.FirstOrDefault()?.Children;
                if (children is null or { Count: 0 })
                    return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(SteamError.NotFound);
                return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Ok(
                    children.OrderBy(c => c.SortOrder)
                            .Select(c => new CollectionChildEntry(
                                new PublishedFileId(ulong.Parse(c.PublishedFileId!, CultureInfo.InvariantCulture)),
                                c.FileType))
                            .ToList());
            }
            catch (JsonException)
            {
                return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(SteamError.Deserialization);
            }
            catch (FormatException)
            {
                return Result<IReadOnlyList<CollectionChildEntry>, SteamError>.Fail(SteamError.Deserialization);
            }
        }
    }

    private static WorkshopItem? MapToWorkshopItem(FileDetail d)
    {
        if (!ulong.TryParse(d.PublishedFileId, CultureInfo.InvariantCulture, out var id))
            return null;
        return new WorkshopItem(
            id: new PublishedFileId(id),
            appId: d.CreatorAppId.HasValue ? new AppId(d.CreatorAppId.Value) : new AppId(0),
            title: d.Title ?? string.Empty)
        {
            Description = d.Description,
            FileSize = d.FileSize,
            PreviewUrl = d.PreviewUrl,
            Creator = d.Creator,
            LastUpdatedUtc = d.TimeUpdated.HasValue
                ? DateTimeOffset.FromUnixTimeSeconds(d.TimeUpdated.Value).UtcDateTime
                : null,
        };
    }

    private static SteamError MapHttpStatus(HttpStatusCode status)
        => status switch
        {
            HttpStatusCode.TooManyRequests => SteamError.RateLimited,
            HttpStatusCode.Forbidden => SteamError.Blocked,
            HttpStatusCode.NotFound => SteamError.NotFound,
            HttpStatusCode.Unauthorized => SteamError.AuthRequired,
            _ => SteamError.Network,
        };

    // ---- Steam API 响应 DTO ----

    private sealed record DetailsResponse
    {
        [JsonPropertyName("response")]
        public DetailsInner? Response { get; init; }
    }

    private sealed record DetailsInner
    {
        [JsonPropertyName("result")]
        public int Result { get; init; }

        [JsonPropertyName("publishedfiledetails")]
        public List<FileDetail>? PublishedFileDetails { get; init; }
    }

    private sealed record FileDetail
    {
        [JsonPropertyName("publishedfileid")]
        public string? PublishedFileId { get; init; }

        [JsonPropertyName("result")]
        public int Result { get; init; } = 1;

        [JsonPropertyName("creator")]
        public string? Creator { get; init; }

        [JsonPropertyName("creator_app_id")]
        public int? CreatorAppId { get; init; }

        [JsonPropertyName("title")]
        public string? Title { get; init; }

        [JsonPropertyName("description")]
        public string? Description { get; init; }

        [JsonPropertyName("file_size")]
        public ulong? FileSize { get; init; }

        [JsonPropertyName("preview_url")]
        public string? PreviewUrl { get; init; }

        [JsonPropertyName("time_updated")]
        public long? TimeUpdated { get; init; }
    }

    private sealed record CollectionResponse
    {
        [JsonPropertyName("response")]
        public CollectionInner? Response { get; init; }
    }

    private sealed record CollectionInner
    {
        [JsonPropertyName("collections")]
        public List<CollectionEntry>? Collections { get; init; }
    }

    private sealed record CollectionEntry
    {
        [JsonPropertyName("publishedfileid")]
        public string? PublishedFileId { get; init; }

        [JsonPropertyName("children")]
        public List<CollectionChild>? Children { get; init; }
    }

    private sealed record CollectionChild
    {
        [JsonPropertyName("publishedfileid")]
        public string? PublishedFileId { get; init; }

        [JsonPropertyName("sortorder")]
        public int SortOrder { get; init; }

        [JsonPropertyName("filetype")]
        public int FileType { get; init; }
    }

    /// <summary>把 <see cref="IConnectivityState"/>（D2.2）适配为 <see cref="IConnectivityGate"/>。</summary>
    public sealed class StateConnectivityGate : IConnectivityGate
    {
        private readonly IConnectivityState _state;
        public StateConnectivityGate(IConnectivityState state)
        {
            ArgumentNullException.ThrowIfNull(state);
            _state = state;
        }
        public bool IsApiUnreachable
            => _state.Current.TryGetValue(EndpointKind.Api, out var s) && s.Reach == Reachability.Unreachable;
    }

    /// <summary>集合子项（id + filetype;0=Collection，GetCollectionDetails 端点语义）。</summary>
    private sealed record CollectionChildEntry(PublishedFileId Id, int FileType);
}

