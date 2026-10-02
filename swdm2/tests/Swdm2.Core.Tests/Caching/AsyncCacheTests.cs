using System.Collections.Concurrent;
using Swdm2.Core.Caching;

namespace Swdm2.Core.Tests.Caching;

/// <summary>
/// D1.6 异步缓存验收。C5 核心判据：**命中后修改返回对象不影响缓存**——
/// 1.x api_cache 污染事故（browse() 返回可变 dataclass + enrich() 就地修改）的 C# 断言化。
/// </summary>
public sealed class AsyncCacheTests
{
    [Fact]
    public async Task Factory_Produces_Cached_And_Second_Call_Hits()
    {
        var cache = new AsyncCache<string, MutableItem>();
        var calls = 0;

        var first = await cache.GetOrAddAsync("k", _ => { calls++; return Task.FromResult(new MutableItem { Name = "v1" }); }, TimeSpan.FromMinutes(1));
        var second = await cache.GetOrAddAsync("k", _ => { calls++; return Task.FromResult(new MutableItem { Name = "v2" }); }, TimeSpan.FromMinutes(1));

        Assert.Equal(1, calls); // 第二次命中，工厂未再跑
        Assert.Equal("v1", first!.Name);
        Assert.Equal("v1", second!.Name);
    }

    /// <summary>验收判据（C5 / 学费 #11）：命中后修改返回对象不影响缓存。</summary>
    [Fact]
    public async Task Mutating_Returned_Object_Does_Not_Pollute_Cache()
    {
        var cache = new AsyncCache<string, MutableListHolder>();
        var original = new MutableListHolder { Title = "orig", Tags = ["a", "b"] };
        await cache.GetOrAddAsync("k", _ => Task.FromResult(original)!, TimeSpan.FromMinutes(1));

        // 取出命中值并像 1.x enrich() 那样就地修改
        var got = await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableListHolder())!, TimeSpan.FromMinutes(1));
        got!.Title = "MUTATED";
        got.Tags.Add("injected");
        got.Inner = new MutableItem { Name = "injected-inner" };

        // 再次命中：缓存内容未受污染
        var again = await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableListHolder())!, TimeSpan.FromMinutes(1));
        Assert.Equal("orig", again!.Title);
        Assert.Equal(["a", "b"], again.Tags);
        Assert.Null(again.Inner);
        Assert.DoesNotContain("MUTATED", again.Title);
        Assert.DoesNotContain("injected", again.Tags);
    }

    /// <summary>验收判据：两次命中返回**互不相同**的实例（深拷贝证据）且内容相等。</summary>
    [Fact]
    public async Task Hits_Return_Distinct_Equal_Instances()
    {
        var cache = new AsyncCache<string, MutableItem>();
        await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableItem { Name = "same" })!, TimeSpan.FromMinutes(1));

        var a = await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableItem())!, TimeSpan.FromMinutes(1));
        var b = await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableItem())!, TimeSpan.FromMinutes(1));

        Assert.NotSame(a, b);
        Assert.NotSame(a!, b!);
        Assert.Equal(a!.Name, b!.Name);
    }

    /// <summary>验收判据：single-flight——并发同键工厂只执行一次。</summary>
    [Fact]
    public async Task Concurrent_Same_Key_Runs_Factory_Once()
    {
        var cache = new AsyncCache<int, MutableItem>();
        var calls = 0;
        var keys = Enumerable.Range(0, 12).ToArray();

        var tasks = keys.Select(_ => cache.GetOrAddAsync(42, async ct =>
        {
            Interlocked.Increment(ref calls);
            await Task.Delay(80, ct); // 模拟慢工厂，放大竞争窗口
            return new MutableItem { Name = "once" };
        }, TimeSpan.FromMinutes(1))).ToArray();
        var results = await Task.WhenAll(tasks);

        Assert.Equal(1, calls);
        Assert.All(results, r => Assert.Equal("once", r!.Name));
    }

    /// <summary>验收判据：不同键互不串扰。</summary>
    [Fact]
    public async Task Different_Keys_Are_Isolated()
    {
        var cache = new AsyncCache<string, MutableItem>();
        var a = await cache.GetOrAddAsync("a", _ => Task.FromResult(new MutableItem { Name = "A" })!, TimeSpan.FromMinutes(1));
        var b = await cache.GetOrAddAsync("b", _ => Task.FromResult(new MutableItem { Name = "B" })!, TimeSpan.FromMinutes(1));
        Assert.Equal("A", a!.Name);
        Assert.Equal("B", b!.Name);
    }

    /// <summary>验收判据：TTL 过期后重新计算（参数最小可测值——50ms，经验复验纪律）。</summary>
    [Fact]
    public async Task Expired_Entry_Is_Refreshed()
    {
        var cache = new AsyncCache<string, MutableItem>();
        var calls = 0;
        var ttl = TimeSpan.FromMilliseconds(50);

        await cache.GetOrAddAsync("k", _ => { calls++; return Task.FromResult(new MutableItem { Name = "v1" }); }, ttl);
        await Task.Delay(120); // 过期
        var second = await cache.GetOrAddAsync("k", _ => { calls++; return Task.FromResult(new MutableItem { Name = "v2" }); }, ttl);

        Assert.Equal(2, calls);
        Assert.Equal("v2", second!.Name);
    }

    /// <summary>验收判据：未过期内 TTL 内连续命中。</summary>
    [Fact]
    public async Task Within_Ttl_Every_Call_Hits()
    {
        var cache = new AsyncCache<string, MutableItem>();
        var calls = 0;
        var ttl = TimeSpan.FromMilliseconds(500);

        for (var i = 0; i < 5; i++)
            await cache.GetOrAddAsync("k", _ => { calls++; return Task.FromResult(new MutableItem { Name = "v" }); }, ttl);

        Assert.Equal(1, calls);
    }

    /// <summary>验收判据：工厂异常传播且不缓存失败（下次调用重试工厂）。</summary>
    [Fact]
    public async Task Factory_Failure_Propagates_And_Does_Not_Poison()
    {
        var cache = new AsyncCache<string, MutableItem>();
        var calls = 0;

        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await cache.GetOrAddAsync("k", ct =>
            {
                calls++;
                throw new InvalidOperationException("factory boom");
            }, TimeSpan.FromMinutes(1)));

        var recovered = await cache.GetOrAddAsync("k", _ =>
        {
            calls++;
            return Task.FromResult(new MutableItem { Name = "recovered" });
        }, TimeSpan.FromMinutes(1));

        Assert.Equal(2, calls);
        Assert.Equal("recovered", recovered!.Name);
    }

    /// <summary>
    /// 验收判据：克隆器在两个隔离点都被调用——入缓存（生产侧隔离）+ 命中出口（消费侧隔离）。
    /// 插入路径克隆一次存私有副本，命中路径克隆一次给出门口。
    /// </summary>
    [Fact]
    public async Task Custom_Cloner_Is_Used_At_Both_Isolation_Points()
    {
        var cloneCalls = 0;
        var cache = new AsyncCache<string, MutableItem>(clone: v =>
        {
            cloneCalls++;
            return new MutableItem { Name = v.Name };
        });

        await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableItem { Name = "x" })!, TimeSpan.FromMinutes(1));
        await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableItem())!, TimeSpan.FromMinutes(1)); // 命中

        Assert.Equal(2, cloneCalls);
    }

    /// <summary>验收判据（生产侧隔离）：调用方事后修改交给缓存的原对象不污染缓存。</summary>
    [Fact]
    public async Task Mutating_Producer_Object_Does_Not_Pollute_Cache()
    {
        var cache = new AsyncCache<string, MutableListHolder>();
        var original = new MutableListHolder { Title = "orig", Tags = ["a"] };
        await cache.GetOrAddAsync("k", _ => Task.FromResult(original)!, TimeSpan.FromMinutes(1));

        // 调用方事后修改自己的原对象（1.x enrich() 事故的另一面）
        original.Title = "PRODUCER-MUTATED";
        original.Tags.Add("poison");

        var hit = await cache.GetOrAddAsync("k", _ => Task.FromResult(new MutableListHolder())!, TimeSpan.FromMinutes(1));
        Assert.Equal("orig", hit!.Title);
        Assert.Equal(["a"], hit.Tags);
    }

    private sealed class MutableItem
    {
        public string Name { get; set; } = string.Empty;
    }

    /// <summary>嵌套可变结构——检验深拷贝（不是 MemberwiseClone 的浅拷贝）。</summary>
    private sealed class MutableListHolder
    {
        public string Title { get; set; } = string.Empty;
        public List<string> Tags { get; set; } = [];
        public MutableItem? Inner { get; set; }
    }
}
