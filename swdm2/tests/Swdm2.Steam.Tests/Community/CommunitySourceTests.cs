using System.Reflection;
using Swdm2.Core.Caching;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Community;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Community;

/// <summary>
/// D2.5 社区页面回退验收（真实输入纪律）：
/// - 真实 fixture = 2026-10-02 经代理抓取的 steamcommunity 真实页面字节；
/// - 可达门（S4）= 不可达时 0 请求（stub 计数断言）；
/// - 缓存深拷贝 = D1.6 出口克隆断言（1.x api_cache 污染学费）。
/// </summary>
[Trait("Category", "Community")]
public sealed class CommunitySourceTests
{
    private const string BrowseResource = "Swdm2.Steam.Tests.Community.fixtures.browse.html";
    private const string DetailResource = "Swdm2.Steam.Tests.Community.fixtures.detail.html";

    private static string LoadFixture(string name)
    {
        var asm = Assembly.GetExecutingAssembly();
        using var stream = asm.GetManifestResourceStream(name)
            ?? throw new InvalidOperationException($"fixture resource missing: {name}");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    // ── 真实 fixture 解析（browse 页改 React 版：旧 workshopItem 类消失，id/alt 锚定） ──

    [Fact]
    public void ParseBrowse_Fixture_Parses_Real_Page_Items()
    {
        var html = LoadFixture(BrowseResource);
        var items = CommunityHtmlParser.ParseBrowse(html, new AppId(4000));

        // 真实 browse 页一页 30 条（2026-10-02 实测：60 链接=30 物品，每物品 id 出现 2 次）
        Assert.True(items.Count >= 25, $"expected ≥25 items, got {items.Count}");
        Assert.All(items, i => Assert.True(i.Id.Value > 0));

        var kfc = items.FirstOrDefault(i => i.Id.Value == 3808352517);
        Assert.NotNull(kfc);
        Assert.Equal("KFC - Chicken Bucket", kfc.Title);
        Assert.Contains("images.steamusercontent.com/ugc/", kfc.PreviewUrl ?? "");
    }

    [Fact]
    public void ParseBrowse_Dedupes_Duplicate_Id_Links()
    {
        var html = LoadFixture(BrowseResource);
        var items = CommunityHtmlParser.ParseBrowse(html, new AppId(4000));
        var ids = items.Select(i => i.Id.Value).ToArray();
        Assert.Equal(ids.Length, ids.Distinct().Count());
    }

    [Fact]
    public void ParseBrowse_Empty_Html_Yields_Zero_Items()
    {
        var items = CommunityHtmlParser.ParseBrowse("<html><body>nothing here</body></html>", new AppId(4000));
        Assert.Empty(items);
    }

    [Fact]
    public void ParseDetail_Fixture_Parses_Title_Creator_Preview_AppId()
    {
        var html = LoadFixture(DetailResource);
        Assert.Equal("KFC - Chicken Bucket", CommunityHtmlParser.TryParseTitle(html));
        Assert.Equal("fr3ddy45", CommunityHtmlParser.TryParseCreator(html));
        Assert.Contains("images.steamusercontent.com/ugc/", CommunityHtmlParser.TryParsePreview(html) ?? "");
        Assert.Equal(4000, (int)CommunityHtmlParser.TryParseAppId(html)!);
    }

    // ── 可达门（S4）：不可达 → 0 请求 ──

    [Fact]
    public async Task Browse_Unreachable_Yields_Network_Without_Any_Http_Call()
    {
        using var stub = new CountingStub();
        var state = new ConnectivityState();
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.Unreachable, -1),
        });

        var source = new CommunityPageSource(stub.Factory, state, ProxyMode.Direct);
        var result = await source.BrowseAsync(new AppId(4000));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.Network, result.Error);
        Assert.Equal(0, stub.RequestCount); // S4：不可达不调用
    }

    [Fact]
    public async Task Detail_Blocked_Yields_Network_Without_Any_Http_Call()
    {
        using var stub = new CountingStub();
        var state = new ConnectivityState();
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.Blocked, -1),
        });

        var source = new CommunityPageSource(stub.Factory, state, ProxyMode.Direct);
        var result = await source.EnrichDetailAsync(new PublishedFileId(3808352517));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.Network, result.Error);
        Assert.Equal(0, stub.RequestCount);
    }

    // ── HTTP 集成（loopback stub + 可达状态） ──

    [Fact]
    public async Task Browse_Reachable_Stub_Returns_Parsed_Items()
    {
        var html = LoadFixture(BrowseResource);
        using var stub = new CountingStub(html);
        var state = ReachableState();

        var source = new CommunityPageSource(stub.Factory, state, ProxyMode.Direct);
        var result = await source.BrowseAsync(new AppId(4000));

        Assert.True(result.IsOk);
        Assert.True(result.Value!.Count >= 25);
        Assert.Equal(1, stub.RequestCount);
    }

    [Fact]
    public async Task Detail_429_Maps_To_RateLimited()
    {
        using var stub = new CountingStub(status: System.Net.HttpStatusCode.TooManyRequests);
        var source = new CommunityPageSource(stub.Factory, ReachableState(), ProxyMode.Direct);
        var result = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.False(result.IsOk);
        Assert.Equal(SteamError.RateLimited, result.Error);
    }

    [Fact]
    public async Task Detail_Bad_Markup_Maps_To_Deserialization()
    {
        using var stub = new CountingStub("<html><body>no markers</body></html>");
        var source = new CommunityPageSource(stub.Factory, ReachableState(), ProxyMode.Direct);
        var result = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.False(result.IsOk);
        Assert.Equal(SteamError.Deserialization, result.Error);
    }

    // ── 缓存（D1.6 出口深拷贝） ──

    [Fact]
    public async Task Browse_Cache_Hit_Returns_DeepCopy_Mutation_Isolated()
    {
        var html = LoadFixture(BrowseResource);
        using var stub = new CountingStub(html);

        var cache = new AsyncCache<string, IReadOnlyList<WorkshopItem>>(
            clone: list => list.Select(i => i with { }).ToArray());
        var source = new CommunityPageSource(stub.Factory, ReachableState(), ProxyMode.Direct, browseCache: cache);

        var first = await source.BrowseAsync(new AppId(4000));
        Assert.True(first.IsOk);
        var n = first.Value!.Count;
        Assert.Equal(1, stub.RequestCount);

        // 污染出口（1.x 学费：消费侧修改）
        var polluted = first.Value!.ToList();
        polluted.Add(new WorkshopItem(new PublishedFileId(1), new AppId(4000), "polluted"));
        Assert.Equal(1, stub.RequestCount);

        var second = await source.BrowseAsync(new AppId(4000));
        Assert.True(second.IsOk);
        Assert.Equal(n, second.Value!.Count); // 缓存深拷贝：污染未进入
        Assert.DoesNotContain(second.Value!, i => i.Title == "polluted");
        Assert.Equal(1, stub.RequestCount); // 0 新请求（命中）
    }

    [Fact]
    public async Task Detail_Cache_Hit_Fails_Only_First_Fetch_Hits_Wire()
    {
        var html = LoadFixture(DetailResource);
        using var stub = new CountingStub(html);

        // 克隆器必须注入：record ctor 参数名与属性不匹配，默认 JSON 往返克隆器报错（弯路）
        var cache = new AsyncCache<string, WorkshopItem>(clone: item => item with { });
        var source = new CommunityPageSource(stub.Factory, ReachableState(), ProxyMode.Direct, detailCache: cache);

        var first = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.True(first.IsOk);
        Assert.Equal("KFC - Chicken Bucket", first.Value!.Title);
        Assert.Equal(1, stub.RequestCount);

        var original = first.Value!;
        var second = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.True(second.IsOk);
        Assert.Equal(original, second.Value!); // 结构性相等（C5）
        Assert.NotSame(original, second.Value!); // 但已深拷贝（独立实例）
        Assert.Equal(1, stub.RequestCount);
    }

    [Fact]
    public async Task Detail_Fetch_Failure_Not_Cached()
    {
        // 第一次 429（失败不缓存）→ 第二次换 200 页面：应重新请求并成功
        using var stub = new CountingStub();
        stub.Enqueue(System.Net.HttpStatusCode.TooManyRequests, "");
        stub.Enqueue(System.Net.HttpStatusCode.OK, LoadFixture(DetailResource));

        var cache = new AsyncCache<string, WorkshopItem>(clone: item => item with { });
        var source = new CommunityPageSource(stub.Factory, ReachableState(), ProxyMode.Direct, detailCache: cache);

        var r1 = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.False(r1.IsOk);
        Assert.Equal(SteamError.RateLimited, r1.Error);

        var r2 = await source.EnrichDetailAsync(new PublishedFileId(3808352517));
        Assert.True(r2.IsOk);
        Assert.Equal(2, stub.RequestCount);
    }

    private static ConnectivityState ReachableState()
    {
        var state = new ConnectivityState();
        state.Apply(new Dictionary<EndpointKind, EndpointStatus>
        {
            [EndpointKind.Community] = new(EndpointKind.Community, Reachability.ViaProxy, 100),
        });
        return state;
    }
}
