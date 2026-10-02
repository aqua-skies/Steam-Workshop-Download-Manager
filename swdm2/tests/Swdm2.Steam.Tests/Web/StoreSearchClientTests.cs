using System.Net;
using System.Text.Json;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Web;

/// <summary>
/// storesearch 客户端验收（离线 stub + 在线真实请求）。
/// </summary>
[Trait("Category", "StoreSearch")]
public sealed class StoreSearchClientTests
{
    private static readonly string StoreSearchJson = """
    {
      "total": 1,
      "items": [
        { "type": "app", "id": "322330", "name": "Don't Starve Together", "tiny_image": "https://cdn.akamai.steamstatic.com/steam/apps/322330/capsule_184x69.jpg" }
      ]
    }
    """;

    [Fact]
    public async Task Search_Maps_AppId_And_Name()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, StoreSearchJson));
        var client = new StoreSearchClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            endpointOverride: _ => stub.Url);

        var result = await client.SearchGamesAsync("饥荒");

        Assert.True(result.IsOk);
        Assert.Single(result.Value!);
        Assert.Equal(new AppId(322330), result.Value![0].Id);
        Assert.Equal("Don't Starve Together", result.Value![0].Name);
    }

    [Fact]
    public async Task Search_Empty_Term_Returns_InvalidConfiguration()
    {
        var client = new StoreSearchClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }));
        var empty = await client.SearchGamesAsync("");
        Assert.Equal(SteamError.InvalidConfiguration, empty.Error);
        var space = await client.SearchGamesAsync("   ");
        Assert.Equal(SteamError.InvalidConfiguration, space.Error);
    }

    /// <summary>storesearch 的 term=l=cc 查询串经 stub 验证（l=schinese&cc=CN 研究实证值）。</summary>
    [Fact]
    public async Task Search_Query_String_Includes_Locale_And_Country()
    {
        string? capturedUrl = null;
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, StoreSearchJson))
        {
            OnRequest = url => capturedUrl = url,
        };
        var client = new StoreSearchClient(
            new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            endpointOverride: _ => stub.Url);

        await client.SearchGamesAsync("饥荒");

        Assert.NotNull(capturedUrl);
        Assert.Contains("term=", capturedUrl);
        Assert.Contains("l=schinese", capturedUrl);
        Assert.Contains("cc=CN", capturedUrl);
    }
}
