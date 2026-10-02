using SteamKit2.CDN;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Steam.Tests.Cdn;

/// <summary>
/// D4.3 chunk 并行下载+SHA/Adler 校验验收（离线=注入 chunk seam):
/// - 并行度按注入值真实生效（max-1=串行；max=4 观测并行）
/// - 损坏 chunk(Adler/长度不过）→InvalidChecksum 语义重下，重试后成功
/// - 重试耗尽→该项枚举 Fail(InvalidChecksum)，其余 chunk 不受影响
/// - 无 depot key→AuthRequired;直链 manifest→InvalidConfiguration
/// 真链 chunk 下载（沙箱环境阻断）随 Online 套件覆盖（同 D4.2 门模式）。
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SteamKitCdnClientChunkTests
{
    private static readonly byte[] ChunkId = new byte[20];
    private static readonly byte[] Good = Enumerable.Range(1, 32).Select(i => (byte)i).ToArray();
    private static readonly byte[] Bad = new byte[] { 0x01 }; // 长度即错

    private static ManifestChunk Chunk(uint checksum, ulong offset = 0)
        => new("aa", ChunkId, checksum, offset, 24, (uint)Good.Length);

    private static ManifestHandle Handle(IEnumerable<ManifestChunk> chunks, byte[]? depotKey = null)
        => new ManifestHandle(4000, 4001, 888, null,
            new List<ManifestFile>
            {
                new("addon.txt", (ulong)Good.Length, "aa", chunks.ToList())
            },
            (ulong)Good.Length)
        { DepotKey = depotKey ?? new byte[32] };

    /// <summary>校验器单元：好数据过；错 Adler 不过；错长度不过。</summary>
    [Fact]
    public void VerifyChunk_Adler_And_Length_Gate()
    {
        var goodAdler = AdlerHash(Good);
        Assert.True(SteamKitCdnClient.VerifyChunk(Chunk(goodAdler), Good));
        Assert.False(SteamKitCdnClient.VerifyChunk(Chunk(goodAdler + 1), Good)); // Adler 不符
        Assert.False(SteamKitCdnClient.VerifyChunk(Chunk(goodAdler), Bad));     // 长度不符
    }

    /// <summary>并行度注入真实生效：max=4 时并发观测 ≥2；max=1 时严格串行。</summary>
    [Fact]
    public async Task Chunk_Parallelism_Injected_Effective()
    {
        for (var p = 1; p <= 4; p++)
        {
            var inFlight = 0;
            var maxInFlight = 0;
            var chunks = Enumerable.Range(0, 8).Select(i => Chunk(AdlerHash(Good), (ulong)i)).ToArray();
            var client = MakeClient(p, stub: (_, _, _, _, _, _) =>
            {
                Interlocked.Increment(ref inFlight);
                Thread.Sleep(60); // 让并发窗口可观测（Windows 计时器动态上界：不依赖精确睡眠）
                // 无锁 max 更新
                int observed;
                do { observed = maxInFlight; } while (inFlight > observed
                    && Interlocked.CompareExchange(ref maxInFlight, inFlight, observed) != observed);
                Interlocked.Decrement(ref inFlight);
                return Task.FromResult<byte[]?>(Good);
            });

            var count = 0;
            await foreach (var r in client.DownloadChunksAsync(Handle(chunks)))
            {
                Assert.True(r.IsOk);
                count++;
            }

            Assert.Equal(8, count);
            var expectedMax = p == 1 ? 1 : 2; // max=1 严格串行；>1 至少观测到 2 并发
            Assert.True(maxInFlight >= expectedMax && maxInFlight <= p,
                $"parallelism={p}: observed max in-flight={maxInFlight}（期望 [{expectedMax}..{p}]）");
            if (p == 1) Assert.Equal(1, maxInFlight);
        }
    }

    /// <summary>损坏 chunk→InvalidChecksum 语义重下：首次返坏数据，重试好数据→最终 OK。</summary>
    [Fact]
    public async Task Damaged_Chunk_Retries_And_Succeeds()
    {
        var damagedOnce = new bool[1];
        var attempts = 0;
        var chunks = new[] { Chunk(AdlerHash(Good)) };
        var client = MakeClient(2, stub: (_, _, _, _, _, _) =>
        {
            Interlocked.Increment(ref attempts);
            if (!damagedOnce[0])
            {
                damagedOnce[0] = true;
                return Task.FromResult<byte[]?>(Bad); // 损坏
            }
            return Task.FromResult<byte[]?>(Good);
        });

        var results = new List<Result<ChunkResult, SteamError>>();
        await foreach (var r in client.DownloadChunksAsync(Handle(chunks))) results.Add(r);

        Assert.Equal(2, attempts); // 损坏 1 次+重下 1 次
        Assert.True(results[0].IsOk);
        Assert.Equal(Good, results[0].Value!.Data);
    }

    /// <summary>重试耗尽→Fail(InvalidChecksum)，枚举继续（多 chunk 其余不受影响）。</summary>
    [Fact]
    public async Task Persistently_Damaged_Chunk_Fails_InvalidChecksum_Others_Survive()
    {
        var badChunk = Chunk(0); // Adler 永远不符（good 数据校验失败）
        var goodChunk = Chunk(AdlerHash(Good));
        var chunks = new[] { badChunk, goodChunk };
        var attempts = 0;
        var client = MakeClient(1, stub: (_, _, _, _, _, ct) =>
        {
            Interlocked.Increment(ref attempts);
            return Task.FromResult<byte[]?>(Good);
        });

        var results = new List<Result<ChunkResult, SteamError>>();
        await foreach (var r in client.DownloadChunksAsync(Handle(chunks))) results.Add(r);

        Assert.Equal(2, results.Count);
        var failed = results.Single(r => !r.IsOk);
        Assert.Equal(SteamError.InvalidChecksum, failed.Error);
        Assert.True(results.Single(r => r.IsOk).Value!.Data.SequenceEqual(Good));
        Assert.True(attempts >= 1 + SteamKitCdnClient.MaxChunkRetries); // 坏 chunk 重试耗尽
    }

    /// <summary>无 depot key→AuthRequired（保护的缺失前置）。</summary>
    [Fact]
    public async Task Missing_Depot_Key_Returns_AuthRequired()
    {
        var client = MakeClient(2, stub: (_, _, _, _, _, _) => Task.FromResult<byte[]?>(Good));
        var handle = new ManifestHandle(4000, 4001, 888, null,
            new List<ManifestFile>
            {
                new("addon.txt", (ulong)Good.Length, "aa", new[] { Chunk(AdlerHash(Good)) }.ToList())
            },
            (ulong)Good.Length); // DepotKey=null（显式缺失）

        var results = new List<Result<ChunkResult, SteamError>>();
        await foreach (var r in client.DownloadChunksAsync(handle)) results.Add(r);

        var single = Assert.Single(results);
        Assert.False(single.IsOk);
        Assert.Equal(SteamError.AuthRequired, single.Error);
    }

    /// <summary>直链 manifest→InvalidConfiguration（直链不经 chunk 路径）。</summary>
    [Fact]
    public async Task Direct_Link_Manifest_Does_Not_Enter_Chunk_Path()
    {
        var client = MakeClient(2, stub: (_, _, _, _, _, _) =>
            throw new InvalidOperationException("不应调用 chunk 下载"));
        var handle = Handle([]) with { DirectFileUrl = "https://cdn/kfc.txt" };

        var results = new List<Result<ChunkResult, SteamError>>();
        await foreach (var r in client.DownloadChunksAsync(handle)) results.Add(r);

        var single = Assert.Single(results);
        Assert.Equal(SteamError.InvalidConfiguration, single.Error);
    }

    // ---------- helpers ----------

    private static uint AdlerHash(byte[] data) => DepotChunk.AdlerHash(data);

    private static SteamKitCdnClient MakeClient(
        int chunkParallelism,
        Func<uint, byte[]?, string?, ManifestChunk, Server?, CancellationToken, Task<byte[]?>> stub)
        => new(new SteamKitSessionManager(), chunkParallelism: chunkParallelism)
        {
            DownloadChunkFunc = stub,
            ServerFunc = (_, _) => Task.FromResult<Server?>(new Server())
        };
}
