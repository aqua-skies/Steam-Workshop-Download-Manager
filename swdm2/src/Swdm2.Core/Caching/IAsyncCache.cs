namespace Swdm2.Core.Caching;

/// <summary>
/// 异步缓存契约（C5：缓存出口深拷贝——1.x api_cache 污染学费的 C# 断言化）。
/// </summary>
/// <typeparam name="TKey">键类型（ ConcurrentDictionary 键语义）。</typeparam>
/// <typeparam name="TValue">值类型（引用类型；可变或不可变皆可——出口都深拷贝）。</typeparam>
/// <typeparam name=\"TKey\">键类型（不可为 null：缓存键语义）。</typeparam>
public interface IAsyncCache<TKey, TValue> where TValue : class where TKey : notnull
{
    /// <summary>
    /// 取缓存或计算并缓存。
    /// </summary>
    /// <param name="key">缓存键。</param>
    /// <param name="factory">未命中时的值工厂（single-flight：并发同键只跑一次）。</param>
    /// <param name="ttl">存活期；超期视为未命中。</param>
    /// <param name="ct">取消令牌。</param>
    /// <returns>**命中或新算出的值的深拷贝**——调用方修改返回对象不影响缓存（C5）。</returns>
    /// <remarks>
    /// ⚠️ 契约：命中返回前必须深拷贝（1.x api_cache 污染学费——`browse()` 返回的可变 dataclass
    /// 被 `enrich()` 就地修改，缓存数据被污染）。工厂异常会传播且**不缓存失败结果**（不污染下次调用）。
    /// </remarks>
    Task<TValue?> GetOrAddAsync(TKey key, Func<CancellationToken, Task<TValue>> factory, TimeSpan ttl, CancellationToken ct = default);
}
