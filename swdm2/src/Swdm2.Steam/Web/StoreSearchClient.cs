using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Web;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;

namespace Swdm2.Steam.Web;

/// <summary>
/// storesearch 客户端（D2.3):GET https://store.steampowered.com/api/storesearch/?term=amp;l=schinese&amp;cc=CN
/// （匿名无 key,id 即 AppId——研究阶段实证）。失败映射同 <see cref="SteamWebApiClient"/>。
/// </summary>
public sealed class StoreSearchClient : IStoreSearchClient
{
    private const string StoreSearchEndpoint = "https://store.steampowered.com/api/storesearch/";

    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    private readonly IHttpClientFactory _factory;
    private readonly IConnectivityGate? _gate;
    private readonly IThrottler? _throttler;
    private readonly ICircuitBreaker? _breaker;
    private readonly TimeSpan _timeout;
    private readonly Func<string, string> _endpointOverride;

    /// <param name="factory">D2.1 工厂。</param>
    /// <param name="gate">可选可达性门。</param>
    /// <param name="throttler">可选节流器（D2.4;bucket=<see cref="ThrottleBuckets.Store"/>)。</param>
    /// <param name="breaker">可选熔断器（D2.4;失败计入熔断，开态 Fail(CircuitOpen))。</param>
    /// <param name="timeout">单请求超时。</param>
    /// <param name="endpointOverride">测试注入：入参=真实端点 URL，出参=生效 URL。</param>
    public StoreSearchClient(IHttpClientFactory factory, IConnectivityGate? gate = null,
                             IThrottler? throttler = null, ICircuitBreaker? breaker = null,
                             TimeSpan? timeout = null, Func<string, string>? endpointOverride = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _gate = gate;
        _throttler = throttler;
        _breaker = breaker;
        _timeout = timeout ?? TimeSpan.FromSeconds(15);
        _endpointOverride = endpointOverride ?? (_ => StoreSearchEndpoint);
    }

    public Task<Result<IReadOnlyList<GameInfo>, SteamError>> SearchGamesAsync(string term, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(term))
            return Task.FromResult(Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.InvalidConfiguration));

        if (_gate?.IsApiUnreachable == true) // 可达性门同 Web API（Store 端点统一门）
            return Task.FromResult(Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Network));

        // D2.4 集成：节流 acquire → 熔断门 → 请求 → 结果计熔断（bucket=store)
        return ResiliencePipeline.ExecuteAsync(ThrottleBuckets.Store, _throttler, _breaker,
            _ => CoreSearchGamesAsync(term, ct), ct);
    }

    /// <summary>不经弹性管道的核心请求体（由 <see cref="SearchGamesAsync"/> 包装执行）。</summary>
    private async Task<Result<IReadOnlyList<GameInfo>, SteamError>> CoreSearchGamesAsync(string term, CancellationToken ct)
    {
        var clientResult = _factory.CreateClient();
        if (!clientResult.IsOk)
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(clientResult.Error ?? SteamError.None);
        using var client = clientResult.Value!;
        client.Timeout = _timeout;

        // 手工构造查询串（HttpUtility.ParseQueryString 编码歧义多，显式 Uri.EscapeDataString 更确定）
        var query = "term=" + Uri.EscapeDataString(term.Trim()) + "&l=schinese&cc=CN";
        var builder = new UriBuilder(new Uri(_endpointOverride(StoreSearchEndpoint)))
        {
            Query = query,
        };

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(_timeout);

        HttpResponseMessage response;
        try
        {
            response = await client.GetAsync(builder.Uri, cts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Timeout);
        }
        catch (OperationCanceledException)
        {
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Cancelled);
        }
        catch (HttpRequestException)
        {
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Network);
        }
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(MapHttpStatus(response.StatusCode));
            try
            {
                var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                var payload = await JsonSerializer.DeserializeAsync<StoreSearchResponse>(stream, JsonOptions, ct)
                                      .ConfigureAwait(false);
                var items = payload?.Items ?? new List<StoreSearchItem>();
                var games = items
                    .Where(i => !string.IsNullOrEmpty(i.Id) && !string.IsNullOrEmpty(i.Name))
                    .Select(i => new GameInfo(
                        id: new AppId(int.Parse(i.Id!, CultureInfo.InvariantCulture)),
                        name: i.Name!))
                    .ToList();
                return Result<IReadOnlyList<GameInfo>, SteamError>.Ok(games);
            }
            catch (JsonException)
            {
                return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Deserialization);
            }
            catch (FormatException)
            {
                return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Deserialization);
            }
        }
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

    private sealed record StoreSearchResponse
    {
        [JsonPropertyName("total")]
        public int Total { get; init; }

        [JsonPropertyName("items")]
        public List<StoreSearchItem>? Items { get; init; }
    }

    private sealed class StoreSearchItem
    {
        [JsonPropertyName("type")]
        public string? Type { get; set; }

        [JsonPropertyName("name")]
        public string? Name { get; set; }

        [JsonPropertyName("id")]
        public string? Id { get; set; }

        [JsonPropertyName("tiny_image")]
        public string? TinyImage { get; set; }
    }
}
