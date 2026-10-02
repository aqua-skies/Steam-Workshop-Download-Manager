using System.Net;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Swdm2.Core.Results;
using Swdm2.Downloads.Segments;
using Xunit;

namespace Swdm2.Downloads.Tests.Segments;

/// <summary>
/// D4.5 HTTP 直链分段验收（本地 Kestrel fixture,禁公网）:
/// - /big:512KB,Results.File 自动 206 分段支持
/// - /no-range:裸 200（不支持 Range→回退单流）
/// - /slow:手动 Range+延迟（kill 后续传场景）
/// 验收判据：分段下载绿；kill 后续传成功且拼接点校验过；不支持 Range 回退单流。
/// </summary>
[Trait("Category", "Downloads")]
public sealed class HttpSegmentKestrelTests : IDisposable
{
    private const int BigSize = 512 * 1024;
    private readonly byte[] _big = new byte[BigSize];
    private readonly WebApplication _app;
    private readonly string _baseAddress;

    public HttpSegmentKestrelTests()
    {
        // 确定性内容（非随机：可逐字节比对）
        for (var i = 0; i < _big.Length; i++) _big[i] = (byte)(i % 251);

        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0"); // 随机端口=禁公网/无冲突
        _app = builder.Build();

        _app.MapGet("/big", () => Results.File(_big, "application/octet-stream", "big.bin",
            enableRangeProcessing: true));

        // 不支持 Range:裸 200 全量（Kestrel 不自动处理 Range,Results.File 才处理）
        _app.MapGet("/no-range", async ctx =>
        {
            ctx.Response.ContentType = "application/octet-stream";
            ctx.Response.ContentLength = _big.Length;
            await ctx.Response.Body.WriteAsync(_big);
        });

        // 支持 Range 但每段慢（kill-续传确定性）
        _app.MapGet("/slow", async ctx =>
        {
            var rangeHeader = ctx.Request.Headers.Range.ToString();
            if (!TryParseRange(rangeHeader, _big.Length, out var start, out var end))
            {
                ctx.Response.StatusCode = 200;
                await ctx.Response.Body.WriteAsync(_big);
                return;
            }
            ctx.Response.StatusCode = 206;
            ctx.Response.Headers.AcceptRanges = "bytes";
            ctx.Response.Headers.ContentRange = $"bytes {start}-{end}/{_big.Length}";
            ctx.Response.ContentLength = end - start + 1;
            ctx.Response.ContentType = "application/octet-stream";
            var chunk = new byte[16 * 1024];
            var pos = start;
            while (pos <= end)
            {
                var take = (int)Math.Min(chunk.Length, end - pos + 1);
                Array.Copy(_big, pos, chunk, 0, take);
                await ctx.Response.Body.WriteAsync(chunk.AsMemory(0, take));
                await Task.Delay(60); // 制造 kill 窗
                pos += take;
            }
        });

        _app.Start();
        _baseAddress = _app.Urls.First();
    }

    /// <summary>分段下载绿：全字节匹配+.download 清除。</summary>
    [Fact]
    public async Task Kestrel_Segmented_Download_Completes()
    {
        var dest = TempPath("big1.bin");
        var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(), maxParallel: 4);

        var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{_baseAddress}/big", dest))
            ;

        Assert.True(result.IsOk, $"失败={result.Error}");
        Assert.Equal(BigSize, result.Value);
        Assert.Equal(_big, await File.ReadAllBytesAsync(dest));
        Assert.False(File.Exists(dest + ".download")); // 完成=续存清除
    }

    /// <summary>kill 后续传：首次中途取消（Cancelled+续存落盘）→重开=续传成功+拼接点校验过。</summary>
    [Fact]
    public async Task Kestrel_Kill_Then_Resume_Succeeds_Join_Verified()
    {
        var dest = TempPath("resume.bin");
        using var http = new HttpClient();
        var downloader = new HttpSegmentDownloader(http, new JsonResumeStore(), maxParallel: 4);

        // 1) kill：延迟段制造中途中断
        using var killCts = new CancellationTokenSource();
        var first = downloader.DownloadAsync(new HttpDownloadRequest($"{_baseAddress}/slow", dest), null, killCts.Token);
        await Task.Delay(500); // 等部分段落盘
        killCts.Cancel();
        var firstResult = await first;
        Assert.False(firstResult.IsOk);
        Assert.Equal(SteamError.Cancelled, firstResult.Error);

        // 2) 续传（已完成段不重下=收文件不等延时）
        var second = await downloader.DownloadAsync(new HttpDownloadRequest($"{_baseAddress}/slow", dest))
            ;

        Assert.True(second.IsOk, $"续传失败={second.Error}");
        Assert.Equal(_big, await File.ReadAllBytesAsync(dest));
        Assert.False(File.Exists(dest + ".download"));
    }

    /// <summary>不支持 Range→回退单流（内容完整一致）。</summary>
    [Fact]
    public async Task Kestrel_NoRange_Falls_Back_To_Single_Stream()
    {
        var dest = TempPath("single.bin");
        var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(), maxParallel: 4);

        var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{_baseAddress}/no-range", dest))
            ;

        Assert.True(result.IsOk, $"失败={result.Error}");
        Assert.Equal(BigSize, result.Value);
        Assert.Equal(_big, await File.ReadAllBytesAsync(dest));
    }

    internal static bool TryParseRange(string header, long total, out long start, out long end)
    {
        start = end = 0;
        if (string.IsNullOrEmpty(header) || !header.StartsWith("bytes=", StringComparison.OrdinalIgnoreCase))
            return false;
        var spec = header.Substring("bytes=".Length).Trim();
        var dash = spec.IndexOf('-');
        if (dash <= 0) return false;
        if (!long.TryParse(spec.AsSpan(0, dash), out start)) return false;
        var endPart = spec.Substring(dash + 1);
        end = string.IsNullOrEmpty(endPart) ? total - 1 : long.Parse(endPart);
        end = Math.Min(end, total - 1);
        return start <= end && start < total;
    }

    private static string TempPath(string name)
        => Path.Combine(Path.GetTempPath(), "swdm-d45-" + Guid.NewGuid().ToString("N")[..8], name);

    public void Dispose()
    {
        try { _app.StopAsync().Wait(TimeSpan.FromSeconds(5)); } catch { }
        (_app as IDisposable).Dispose();
    }
}

/// <summary>单元：续存原子读写+段规划器 in-half。</summary>
[Trait("Category", "Downloads")]
public sealed class ResumeStoreAndPlannerTests
{
    [Fact]
    public async Task ResumeStore_Roundtrip_And_Corrupt_Tolerance()
    {
        var dir = Path.Combine(Path.GetTempPath(), "swdm-d45-rs-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(dir);
        var dest = Path.Combine(dir, "f.bin");
        var store = new JsonResumeStore();
        var meta = new ResumeMetadata("http://x/f", 100, "\"etag\"", null, 100,
            new List<Segment> { new Segment(0, 50) with { Done = true }, new Segment(50, 100) },
            new SourcePageState("http://x/page", new Dictionary<string, string> { ["k"] = "v" }));

        await store.SaveAsync(dest, meta);
        var loaded = store.Load(dest);
        Assert.NotNull(loaded);
        Assert.Equal("http://x/f", loaded!.Url);
        Assert.Equal(2, loaded.Segments.Count);

        // 损坏→null（不抛）
        await File.WriteAllTextAsync(dest + ".download", "{ corrupt");
        Assert.Null(store.Load(dest));

        // Delete
        File.WriteAllText(dest + ".download", "x");
        store.Delete(dest);
        Assert.False(File.Exists(dest + ".download"));
    }

    [Fact]
    public void Planner_Initial_Segments_Balanced()
    {
        var planner = new SegmentPlanner(8 * 1024 * 1024, maxSegments: 8, minSegmentBytes: 1024);
        var snap = planner.Snapshot;
        Assert.Equal(8, snap.Count);
        Assert.Equal(8 * 1024 * 1024, snap.Sum(s => s.Length));
        Assert.Equal(0, snap[0].Start);
        Assert.Equal(8 * 1024 * 1024, snap[^1].End);
    }

    [Fact]
    public void Planner_InHalf_Split_On_Acquire()
    {
        var planner = new SegmentPlanner(1024, maxSegments: 2, minSegmentBytes: 1);
        var first = planner.TryAcquire()!;
        Assert.NotNull(first);
        Assert.True(first.Length < 1024); // 已分裂（初始 2 段外再分裂）
        Assert.False(planner.AllDone);
        planner.Complete(first);
        Assert.False(planner.AllDone);
    }

    [Fact]
    public void Planner_AllDone_Reflects_Completion()
    {
        var planner = new SegmentPlanner(100, maxSegments: 2, minSegmentBytes: 1);
        foreach (var s in planner.Snapshot) planner.Complete(s);
        Assert.True(planner.AllDone);
    }
}
