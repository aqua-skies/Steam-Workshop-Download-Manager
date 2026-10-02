using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Web;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;

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
    private readonly TimeSpan _timeout;
    private readonly Func<string, string> _endpointOverride;

    public StoreSearchClient(IHttpClientFactory factory, IConnectivityGate? gate = null,
                             TimeSpan? timeout = null, Func<string, string>? endpointOverride = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        _factory = factory;
        _gate = gate;
        _timeout = timeout ?? TimeSpan.FromSeconds(15);
        _endpointOverride = endpointOverride ?? (_ => StoreSearchEndpoint);
    }

    public async Task<Result<IReadOnlyList<GameInfo>, SteamError>> SearchGamesAsync(string term, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(term))
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.InvalidConfiguration);

        if (_gate?.IsApiUnreachable == true) // 可达性门同 Web API（Store 端点统一门）
            return Result<IReadOnlyList<GameInfo>, SteamError>.Fail(SteamError.Network);

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
