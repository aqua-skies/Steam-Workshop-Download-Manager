using System.Diagnostics;
using System.Runtime.CompilerServices;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Hosting;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Disk;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Limiter;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Downloads.Segments;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Downloads.Tests.Limiter;

/// <summary>
/// D4.7 限速器验收（令牌桶;chunk 调度+HTTP 双点）:
/// - 限速后实测带宽≤配置×（1+10%)(本地 Kestrel fixture 禁公网）
/// - 单流回退路径同样节流（一致性）
/// - chunk 调度点（SteamKitCdnProvider 桩 CDN)+HTTP 读流点（HttpSegmentDownloader 真链）
/// - 不限速（0)=零等待
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SpeedLimiterTests
{
    private const int BigSize = 256 * 1024;

    [Fact]
    public async Task NoLimit_Zero_Wait()
    {
        var limiter = new TokenBucketSpeedLimiter(0);
        var sw = Stopwatch.StartNew();
        await limiter.WaitAsync(1024 * 1024);
        sw.Stop();
        Assert.True(sw.ElapsedMilliseconds < 100, $"不限速却等待 {sw.ElapsedMilliseconds}ms");
    }

    /// <summary>突发后节流：1 秒量突发容量用尽→后续等待≥缺口时间。</summary>
    [Fact]
    public async Task Burst_Then_Throttle_Timing()
    {
        var limiter = new TokenBucketSpeedLimiter(200); // 200 B/s
        var sw = Stopwatch.StartNew();
        await limiter.WaitAsync(200); // 突发容量
        await limiter.WaitAsync(200); // 等约 1s
        sw.Stop();
        Assert.True(sw.ElapsedMilliseconds >= 900, $"节流不足：{sw.ElapsedMilliseconds}ms");
    }

    /// <summary>热改速率即时生效（UpdateRate 后按新速率节流）。</summary>
    [Fact]
    public async Task UpdateRate_Hot_Takes_Effect()
    {
        var limiter = new TokenBucketSpeedLimiter(0);
        limiter.UpdateRate(10_000);
        Assert.Equal(10_000, limiter.BytesPerSecond);
        var sw = Stopwatch.StartNew();
        await limiter.WaitAsync(10_000); // 新容量突发
        await limiter.WaitAsync(10_000); // 等 ~1s
        sw.Stop();
        Assert.True(sw.ElapsedMilliseconds >= 900, $"热改后节流不足：{sw.ElapsedMilliseconds}ms");
    }

    /// <summary>HTTP 读流点真测：Kestrel 全速源+限速→实测带宽≤配置×1.1。</summary>
    [Fact]
    public async Task Kestrel_Http_Layer_Measured_Bandwidth_Within_Budget()
    {
        var big = new byte[BigSize];
        for (var i = 0; i < big.Length; i++) big[i] = (byte)(i % 251);

        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        var app = builder.Build();
        app.MapGet("/mid", () => Results.File(big, "application/octet-stream", "mid.bin",
            enableRangeProcessing: true));
        app.Start();
        try
        {
            var baseAddress = app.Urls.First();
            var dest = Path.Combine(Path.GetTempPath(), "swdm-d47-" + Guid.NewGuid().ToString("N")[..8] + ".bin");
            var limiter = new TokenBucketSpeedLimiter(80 * 1024); // 80 KB/s
            var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(),
                maxParallel: 4, limiter: limiter);

            var sw = Stopwatch.StartNew();
            var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{baseAddress}/mid", dest));
                
            sw.Stop();

            Assert.True(result.IsOk, $"下载失败={result.Error}");
            var elapsedSec = sw.Elapsed.TotalSeconds;
            var measured = BigSize / elapsedSec; // B/s
            var budget = 80 * 1024 * 1.1;
            Console.WriteLine($"[D47-BANDWIDTH] {BigSize}B / {elapsedSec:F2}s = {measured/1024:F1}KB/s " +
                              $"(budget {budget/1024:F1}KB/s, margin 10%)");
            Assert.True(measured <= budget,
                $"实测带宽 {measured/1024:F1}KB/s 超预算 {budget/1024:F1}KB/s");
        }
        finally
        {
            await app.StopAsync();
            (app as IDisposable).Dispose();
        }
    }

    /// <summary>chunk 调度点：SteamKitCdnProvider 桩 CDN chunk 消费节流实测。</summary>
    [Fact]
    public async Task Chunk_Scheduling_Point_Limiter_Bound()
    {
        var chunkBytes = 120 * 1024;
        var chunks = 2;
        var totalBytes = chunkBytes * chunks;

        var session = new StubSessionManager();
        var cdn = new StubCdnClient(chunkBytes, chunks);
        var limiter = new TokenBucketSpeedLimiter(60 * 1024); // 60 KB/s
        await using var bus = new FakeBus();
        var provider = new SteamKitCdnProvider(session, cdn, bus, limiter: limiter);

        var dir = Path.Combine(Path.GetTempPath(), "swdm-d47-chunk-" + Guid.NewGuid().ToString("N")[..8]);
        var task = new DownloadTask(
            new DownloadTaskId(Guid.NewGuid()),
            new WorkshopItem(new PublishedFileId(1), new AppId(4000), "x"),
            new AppId(4000), dir)
        { Provider = DownloadProvider.SteamKitCdn };

        var sw = Stopwatch.StartNew();
        var ok = await provider.ExecuteAsync(new DownloadTaskEntry(task), CancellationToken.None);
            
        sw.Stop();

        Assert.True(ok, "provider 应成功（桩 CDN)");
        var elapsedSec = sw.Elapsed.TotalSeconds;
        var measured = totalBytes / elapsedSec;
        var budget = 60 * 1024 * 1.1;
        Console.WriteLine($"[D47-CHUNK] {totalBytes}B / {elapsedSec:F2}s = {measured/1024:F1}KB/s " +
                          $"(budget {budget/1024:F1}KB/s)");
        Assert.True(sw.ElapsedMilliseconds >= 3500, $"chunk 点未节流：{sw.ElapsedMilliseconds}ms");
        Assert.True(measured <= budget, $"chunk 点带宽超预算：{measured/1024:F1}KB/s");
    }

    // ---- 桩 ----

    private sealed class StubSessionManager : ISteamSessionManager
    {
        public SteamSession? Current { get; private set; } = new("anon", true, 0, DateTimeOffset.UtcNow);

        public Task<Result<SteamSession, SteamError>> LoginAsync(SteamSessionLogin? login,
            CancellationToken ct = default)
            => Task.FromResult(Result<SteamSession, SteamError>.Ok(Current!));

        public void Disconnect() { }
    }

    private sealed class StubCdnClient : ISteamCdnClient
    {
        private readonly int _chunkBytes;
        private readonly int _chunks;

        public StubCdnClient(int chunkBytes, int chunks)
        {
            _chunkBytes = chunkBytes;
            _chunks = chunks;
        }

        public Task<Result<ManifestHandle, SteamError>> ResolveUgcManifestAsync(AppId appId,
            PublishedFileId publishedFileId, CancellationToken ct = default)
            => Task.FromResult(Result<ManifestHandle, SteamError>.Ok(MakeManifest()));

        public Task<Result<ManifestHandle, SteamError>> ResolvePubFileManifestAsync(AppId appId,
            UgcId ugcId, CancellationToken ct = default)
            => Task.FromResult(Result<ManifestHandle, SteamError>.Ok(MakeManifest()));

        public async IAsyncEnumerable<Result<ChunkResult, SteamError>> DownloadChunksAsync(
            ManifestHandle manifest, [EnumeratorCancellation] CancellationToken ct = default)
        {
            for (var i = 0; i < _chunks; i++)
            {
                var data = new byte[_chunkBytes];
                for (var b = 0; b < data.Length; b++) data[b] = (byte)((i + b) % 251);
                yield return Result<ChunkResult, SteamError>.Ok(
                    new ChunkResult("f.bin", i.ToString(), (ulong)(i * _chunkBytes), (uint)data.Length, data));
                await Task.Delay(1, ct);
            }
        }

        private ManifestHandle MakeManifest()
        {
            var chunkList = new List<ManifestChunk>();
            for (var i = 0; i < _chunks; i++)
                chunkList.Add(new ManifestChunk(i.ToString(), new byte[16], 0,
                    (uint)(i * _chunkBytes), (uint)_chunkBytes, (uint)_chunkBytes));
            return new ManifestHandle(4000, 0, 0, DirectFileUrl: null,
                new List<ManifestFile>
                {
                    new("f.bin", (ulong)(_chunkBytes * _chunks), "hash", chunkList)
                }, (ulong)(_chunkBytes * _chunks));
        }
    }

    private sealed class FakeBus : IDownloadEventBus
    {
        public Task ReportProgressAsync(DownloadTaskId taskId, ulong bytesReceived, ulong? totalBytes,
            DownloadState? state = null, IReadOnlyList<int>? segments = null, string? message = null,
            CancellationToken ct = default) => Task.CompletedTask;
        public IDisposable Subscribe(Func<ProgressSnapshot, Task> handler) => new Noop();
        public ProgressSnapshot? GetLatest(DownloadTaskId taskId) => null;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        private sealed class Noop : IDisposable { public void Dispose() { } }
    }
}
