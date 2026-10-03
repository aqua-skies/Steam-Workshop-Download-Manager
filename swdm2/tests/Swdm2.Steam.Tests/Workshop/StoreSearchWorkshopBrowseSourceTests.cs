using System.Net;
using Swdm2.Core.Caching;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Tests.Web;
using Swdm2.Steam.Web;
using Swdm2.Steam.Workshop;
using Xunit;

namespace Swdm2.Steam.Tests.Workshop;

/// <summary>
/// t56 D5.17 工坊浏览真实数据源验收（离线 ScriptedStub;same-module 复用 D2.3 模式）：
/// - storesearch 载荷解析（id/name/tiny_image→PreviewImageUrl)
/// - 指纹头（Accept-Language 承重头=1.x 429 学费）
/// - 节流桶 Store + 熔断门（CircuitOpen 直拒 + 成败计数）
/// - 缓存深拷贝（api_cache 污染学费 C5)
/// - 诚实降级（载荷缺字段 null/空；非 Title 排序键=LastSortDegraded 标记）
/// - 分页/查询指纹隔离缓存键
/// </summary>
[Trait("Category", "WorkshopBrowse")]
public sealed class StoreSearchWorkshopBrowseSourceTests
{
    private static readonly string PayloadJson = """
    {
      "total": 3,
      "items": [
        { "type": "app", "id": "322330", "name": "Don't Starve Together", "tiny_image": "https://cdn.akamai.steamstatic.com/steam/apps/322330/capsule_184x69.jpg" },
        { "type": "app", "id": "892970", "name": "Valheim", "tiny_image": "https://cdn.akamai.steamstatic.com/steam/apps/892970/capsule_184x69.jpg" },
        { "type": "app", "id": "108600", "name": "Project Zomboid", "tiny_image": "https://cdn.akamai.steamstatic.com/steam/apps/108600/capsule_184x69.jpg" }
      ]
    }
    """;

    private sealed class StubFactory : IHttpClientFactory
    {
        private readonly HttpMessageHandler _handler;
        public StubFactory(HttpMessageHandler handler) => _handler = handler;
        // disposeHandler:false=源 using 可释放客户端而不杀共享处理器（多请求测试存活）
        public Result<HttpClient, SteamError> CreateClient() =>
            Result<HttpClient, SteamError>.Ok(new HttpClient(_handler, disposeHandler: false));
    }

    private sealed class FakeBreaker : ICircuitBreaker
    {
        public bool Open { get; set; }
        public int Successes { get; private set; }
        public int Failures { get; private set; }
        public bool IsOpen(string bucket) => Open;
        public void RecordSuccess(string bucket) => Successes++;
        public void RecordFailure(string bucket) => Failures++;
    }

    private sealed class NoOpThrottler : IThrottler
    {
        public int Calls { get; private set; }
        public Task AcquireAsync(string bucket, CancellationToken ct = default)
        {
            Calls++;
            Assert.Equal(ThrottleBuckets.Store, bucket); // ⚠️Store 桶（browse 2s 档=社区 HTML 源；本载体走 store 域=文档已标注）
            return Task.CompletedTask;
        }
    }

    private static (StoreSearchWorkshopBrowseSource source, NoOpThrottler throttler, FakeBreaker breaker) Build(
        SteamWebApiClientTests.ScriptedStub stub, IAsyncCache<string, WorkshopBrowsePage>? cache = null,
        Func<string, string>? endpointOverride = null)
    {
        var handler = new HttpClientHandler(); // 真实请求路径（stub 拦截 TCP 层同 D2.3)
        var factory = new StubFactory(handler);
        var throttler = new NoOpThrottler();
        var breaker = new FakeBreaker();
        var source = new StoreSearchWorkshopBrowseSource(factory, cache, throttler, breaker,
            endpointOverride: endpointOverride ?? (_ => stub.Url));
        return (source, throttler, breaker);
    }

    [Fact]
    public async Task Fetch_Maps_Id_Title_Preview_Authors_Null()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, _) = Build(stub);
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒"));
        Assert.True(result.IsOk);
        Assert.Equal(3, result.Value!.Count);
        Assert.Equal("322330", result.Value[0].Id);
        Assert.Equal("Don't Starve Together", result.Value[0].Title);
        Assert.Equal("https://cdn.akamai.steamstatic.com/steam/apps/322330/capsule_184x69.jpg",
            result.Value[0].PreviewImageUrl);
        // storesearch 载荷缺乏=诚实 null/空（不造假）
        Assert.Null(result.Value[0].Author);
        Assert.Empty(result.Value[0].Tags);
        Assert.Null(result.Value[0].Subscribers);
        Assert.Null(result.Value[0].UpdatedAt);
    }

    [Fact]
    public async Task Empty_Search_Returns_InvalidConfiguration_No_Request()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, _) = Build(stub);
        var empty = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: ""));
        Assert.Equal(SteamError.InvalidConfiguration, empty.Error);
        var whitespace = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "   "));
        Assert.Equal(SteamError.InvalidConfiguration, whitespace.Error);
        Assert.Equal(0, stub.RequestCount);
    }

    [Fact]
    public async Task Throttle_Bucket_Store_And_Breaker_Success_Counted()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, throttler, breaker) = Build(stub);
        await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒"));
        Assert.Equal(1, throttler.Calls);
        Assert.Equal(1, breaker.Successes);
        Assert.Equal(0, breaker.Failures);
    }

    [Fact]
    public async Task Circuit_Open_Fails_Without_Request()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, breaker) = Build(stub);
        breaker.Open = true;
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒"));
        Assert.Equal(SteamError.CircuitOpen, result.Error);
        Assert.Equal(0, stub.RequestCount);
    }

    [Fact]
    public async Task RateLimited_Maps_And_Counts_Breaker_Failure()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.TooManyRequests, "{}"));
        var (source, _, breaker) = Build(stub);
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒"));
        Assert.Equal(SteamError.RateLimited, result.Error);
        Assert.Equal(1, breaker.Failures);
    }

    [Fact]
    public async Task Cache_Hit_Second_Call_No_Request()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var cache = new AsyncCache<string, WorkshopBrowsePage>();
        var (source, _, _) = Build(stub, cache);
        var q = new WorkshopBrowseQuery(SearchText: "饥荒");
        var first = await source.FetchAsync(q);
        var second = await source.FetchAsync(q);
        Assert.True(first.IsOk && second.IsOk);
        Assert.Equal(1, stub.RequestCount); // 第二次=缓存命中
        Assert.Equal(3, second.Value!.Count);
    }

    [Fact]
    public async Task Cache_Deep_Clone_Mutation_Does_Not_Pollute()
    {
        // 1.x api_cache 学费：enrich() 就地修改污染缓存 → C5 双向深拷贝断言
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var cache = new AsyncCache<string, WorkshopBrowsePage>();
        var (source, _, _) = Build(stub, cache);
        var q = new WorkshopBrowseQuery(SearchText: "饥荒");
        var first = await source.FetchAsync(q);
        // 调用方就地破坏（模拟 enrich 污染）
        var asList = (List<WorkshopBrowseEntry>)first.Value!;
        asList.Clear();
        var second = await source.FetchAsync(q);
        Assert.Equal(3, second.Value!.Count); // 缓存未污染
    }

    [Fact]
    public async Task Query_Fingerprint_Isolates_Cache_Keys()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var cache = new AsyncCache<string, WorkshopBrowsePage>();
        var (source, _, _) = Build(stub, cache);
        await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒"));
        await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "饥荒", Page: 2));
        var queries = new[]
        {
            new WorkshopBrowseQuery(SearchText: "a"),
            new WorkshopBrowseQuery(SearchText: "a", Tag: "x"),
            new WorkshopBrowseQuery(SearchText: "a", Author: "y"),
        };
        Assert.Equal(3, queries.Select(q => q.CacheKey).Distinct().Count());
        Assert.Equal(2, stub.RequestCount); // 两个不同缓存键=两次请求
    }

    [Fact]
    public async Task Title_Sort_Client_Side_Works()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, _) = Build(stub);
        var asc = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x",
            SortKey: WorkshopBrowseSortKey.Title, SortDescending: false));
        var titles = asc.Value!.Select(e => e.Title).ToList();
        Assert.Equal(titles.OrderBy(t => t, StringComparer.OrdinalIgnoreCase), titles);

        var desc = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x",
            SortKey: WorkshopBrowseSortKey.Title, SortDescending: true));
        Assert.Equal(titles.OrderByDescending(t => t, StringComparer.OrdinalIgnoreCase),
            desc.Value!.Select(e => e.Title));
    }

    [Fact]
    public async Task Non_Title_Sort_Key_Degrades_Honestly()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, _) = Build(stub);
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x",
            SortKey: WorkshopBrowseSortKey.Subscribers));
        Assert.True(result.IsOk);
        Assert.Equal(WorkshopBrowseSortKey.Subscribers, source.LastSortDegraded);
        // 端点序保持（相关性）=不造假
        Assert.Equal("322330", result.Value![0].Id);
    }

    [Fact]
    public async Task Page_Size_Slices_Client_Side()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, PayloadJson));
        var (source, _, _) = Build(stub);
        var page1 = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x", PageSize: 2, Page: 1));
        var page2 = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x", PageSize: 2, Page: 2));
        Assert.Equal(2, page1.Value!.Count);
        Assert.Single(page2.Value!);
        Assert.Equal(2, stub.RequestCount); // 不同缓存键（页号）
    }

    [Fact]
    public async Task Bad_Json_Returns_Deserialization()
    {
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, "not-json"));
        var (source, _, _) = Build(stub);
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x"));
        Assert.Equal(SteamError.Deserialization, result.Error);
    }

    [Fact]
    public async Task Missing_Items_Dropped()
    {
        var json = """{"total":2,"items":[{"type":"app","id":"","name":"NoId"},{"type":"app","id":"42","name":"Ok"}]}""";
        using var stub = new SteamWebApiClientTests.ScriptedStub((req, idx) => (HttpStatusCode.OK, json));
        var (source, _, _) = Build(stub);
        var result = await source.FetchAsync(new WorkshopBrowseQuery(SearchText: "x"));
        Assert.True(result.IsOk);
        Assert.Single(result.Value!);
        Assert.Equal("42", result.Value![0].Id);
    }
}
