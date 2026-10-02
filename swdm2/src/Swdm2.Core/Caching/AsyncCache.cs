using System.Collections.Concurrent;
using System.Text.Json;

namespace Swdm2.Core.Caching;

/// <summary>
/// 默认异步缓存实现：ConcurrentDictionary + 每键 SemaphoreSlim single-flight + TTL + 出口深拷贝。
/// C5 出口深拷贝（1.x api_cache 污染学费）：默认 JSON 往返克隆；不可变 record 可注入轻量克隆器（含 identity）。
/// </summary>
public sealed class AsyncCache<TKey, TValue> : IAsyncCache<TKey, TValue> where TValue : class where TKey : notnull
{
    private static readonly JsonSerializerOptions CloneOptions = new(JsonSerializerDefaults.Web);

    private readonly ConcurrentDictionary<TKey, CacheEntry> _entries = new();
    /// <summary>取该键的信号量（常驻：ConcurrentDictionary + SemaphoreSlim 防击穿，spec §3.1.2）。</summary>
    private readonly ConcurrentDictionary<TKey, SemaphoreSlim> _inflightLocks = new();
    private readonly Func<TValue, TValue> _clone;

    /// <param name="clone">深拷贝策略；默认 = JSON 往返克隆（BCL System.Text.Json）。</param>
    public AsyncCache(Func<TValue, TValue>? clone = null)
    {
        _clone = clone ?? JsonDeepClone;
    }

    public async Task<TValue?> GetOrAddAsync(TKey key, Func<CancellationToken, Task<TValue>> factory, TimeSpan ttl, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(factory);

        // 1. 快速路径：命中且未过期
        if (TryGetFreshEntry(key, out var value))
            return CloneSafe(value);

        // 2. single-flight：取该键的信号量
        var gate = _inflightLocks.GetOrAdd(key, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // 3. 拿到锁后再查一次（防止前一个并发请求已经填入）
            if (TryGetFreshEntry(key, out value))
                return CloneSafe(value);

            // 4. 跑工厂
            var produced = await factory(ct).ConfigureAwait(false);

            // 5. 入缓存：**存克隆**（生产侧隔离——调用方事后修改原对象不污染缓存）;
            //    返回**调用方的原对象**（归属权本就在调用方）。
            //    命中路径另克隆出口（消费侧隔离）——双向隔离因 C5（null 也缓存：负缓存，避免空结果反复击穿后端）
            _entries[key] = new CacheEntry(CloneSafe(produced), DateTimeOffset.UtcNow + ttl);
            return produced;
        }
        finally
        {
            // 信号量常驻（按键去重，内存增长与不同键数成正比）——惰性删除会破坏等待者的 single-flight
            gate.Release();
        }
    }

    /// <summary>未过期才命中；过期视为未命中。</summary>
    private bool TryGetFreshEntry(TKey key, out TValue? value)
    {
        if (_entries.TryGetValue(key, out var entry) && entry.ExpiryUtc > DateTimeOffset.UtcNow)
        {
            value = entry.Value;
            return true;
        }
        value = null;
        return false;
    }

    /// <summary>出口深拷贝（C5）。</summary>
    private TValue? CloneSafe(TValue? value)
        => value is null ? null : _clone(value);

    /// <summary>默认深拷贝：JSON 往返（对公开可变类/record 均可靠）。</summary>
    private static TValue JsonDeepClone(TValue source)
        => JsonSerializer.Deserialize<TValue>(JsonSerializer.Serialize(source, CloneOptions), CloneOptions)!;

    /// <summary>当前条目数（测试/诊断用）。</summary>
    public int Count => _entries.Count;

    /// <summary>清空全部缓存条目。</summary>
    public void Clear() => _entries.Clear();

    private readonly record struct CacheEntry(TValue? Value, DateTimeOffset ExpiryUtc);
}
