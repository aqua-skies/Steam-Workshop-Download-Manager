using System.Diagnostics;
using System.IO;
using System.Net.Http;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Swdm2.Downloads.Segments;
using Xunit;

namespace Swdm2.UiTests.Calibration;

/// <summary>
/// D4.8(t37)⚠️重标定 B3(并发上限）——t3 §5.5 格式。
///
/// **推理起点（经验复验纪律:先问"能否更大/能否更小"）**:
/// - 分段并发 MaxChunkParallelism:DepotDownloader 默认 8 → 问"**能否更小**"（少连接=少被单主机限流风险）
///   候选 {1,2,4,8,16};判据=增益≥10% 最大档默认+错误率&lt;2%
/// - MaxConnectionsPerServer:同问"能否更小"（SocketsHttpHandler 连接池；候选 {2,4,8,16}）
/// - OverlapBytes(D5 spec 16-64 区间）→ 问"**能否更小**"（省带宽）候选 {16,32,64};拼接校验过+全字节匹配
/// - ChunkTimeoutMs(bezzad 5000 起点）→ 慢端点错误率拐点 候选 {2000,5000,15000}
///
/// **强制本地 Kestrel fixture(禁公网）**:全程 127.0.0.1:0,IPv4 loopback。
/// 诚实标注：localhost=内存级，rep 方差&gt;候选差时增益判据不可判别（写入报告作为锁定依据）。
/// 输出：TestArtifacts/calibration_2.csv(逐 sweep 原始行；md/json 由基准报告组装）。
/// 注：测试方法用 [WpfFact](StaFact) 解析 v3 FactAttribute，避开 xunit.core/xunit.v3.core 同命名 [Fact] 二义。
/// </summary>
public sealed class B3ConcurrencyCalibration : IDisposable
{
    private const int Payload = 8 * 1024 * 1024; // 8 MiB:够大测并发增益，localhost 内存级
    private readonly byte[] _payload;
    private readonly WebApplication _app;
    private readonly string _base;

    public B3ConcurrencyCalibration()
    {
        _payload = new byte[Payload];
        for (var i = 0; i < _payload.Length; i++) _payload[i] = (byte)(i % 251);

        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();

        _app.MapGet("/payload", () => Results.File(_payload, "application/octet-stream", "p.bin",
            enableRangeProcessing: true));

        // 慢端点：每 64KB 延迟 250ms(≈256KB/s 供应速率）= 制造超时判别梯度；n=载荷字节数
        _app.MapGet("/slow", async ctx =>
        {
            var n = ctx.Request.Query.TryGetValue("n", out var nv) && int.TryParse(nv, out var np)
                ? np : 1024 * 1024;
            var slowPayload = Math.Min(Math.Max(64 * 1024, n), 8 * 1024 * 1024);
            const int chunk = 64 * 1024;
            ctx.Response.ContentType = "application/octet-stream";
            ctx.Response.ContentLength = slowPayload;
            ctx.Response.Headers.AcceptRanges = "bytes";
            var rangeHeader = ctx.Request.Headers.Range.ToString();
            var (start, end) = ParseRangeOrFull(rangeHeader, slowPayload);
            ctx.Response.StatusCode = (end - start + 1) < slowPayload ? 206 : 200;
            if (ctx.Response.StatusCode == 206)
                ctx.Response.Headers.ContentRange = $"bytes {start}-{end}/{slowPayload}";
            var pos = start;
            var buf = new byte[chunk];
            while (pos <= end)
            {
                var take = (int)Math.Min(chunk, end - pos + 1);
                Array.Copy(_payload, pos, buf, 0, take);
                await ctx.Response.Body.WriteAsync(buf.AsMemory(0, take)).ConfigureAwait(false);
                await Task.Delay(250).ConfigureAwait(false);
                pos += take;
            }
        });

        _app.Start();
        _base = _app.Urls.First();
    }

    /// <summary>A. 分段并发 sweep（Kestrel fixture,禁公网）：maxParallel {1,2,4,8,16}×2 rep。</summary>
    [WpfFact]
    public async Task A_Segment_Parallelism_Sweep()
    {
        var rows = new List<string> { "idx,phase,candidate,rep,elapsed_ms,throughput_kbps,bytes,ok" };
        var candidates = new[] { 1, 2, 4, 8, 16 };
        var idx = 0;
        foreach (var c in candidates)
        {
            for (var rep = 1; rep <= 2; rep++)
            {
                var dest = ArtifactsPath($"b3-a-{c}-{rep}.bin");
                PurgeStale(dest);
                var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(),
                    maxParallel: c);
                var sw = Stopwatch.StartNew();
                var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{_base}/payload", dest));
                sw.Stop();
                var ok = result.IsOk ? 1 : 0;
                var kbps = ok == 1 ? Payload / 1024.0 / sw.Elapsed.TotalSeconds : 0;
                rows.Add($"{idx++},A-maxParallel,{c},{rep},{sw.ElapsedMilliseconds},{kbps:F0},{Payload},{ok}");
                Console.WriteLine($"[B3-A] maxParallel={c} rep{rep}: {sw.ElapsedMilliseconds}ms {kbps:F0}KB/s ok={ok}");
            }
        }
        await AppendCsvAsync(rows);
    }

    /// <summary>B. MaxConnectionsPerServer sweep：连接池上限 {2,4,8,16}×2 rep（maxParallel 固定 8)。</summary>
    [WpfFact]
    public async Task B_Connections_Per_Host_Sweep()
    {
        var rows = new List<string> { "idx,phase,candidate,rep,elapsed_ms,throughput_kbps,bytes,ok" };
        var candidates = new[] { 2, 4, 8, 16 };
        var idx = 0;
        foreach (var c in candidates)
        {
            for (var rep = 1; rep <= 2; rep++)
            {
                var handler = new SocketsHttpHandler { MaxConnectionsPerServer = c };
                using var http = new HttpClient(handler);
                var dest = ArtifactsPath($"b3-b-{c}-{rep}.bin");
                PurgeStale(dest);
                var downloader = new HttpSegmentDownloader(http, new JsonResumeStore(), maxParallel: 8);
                var sw = Stopwatch.StartNew();
                var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{_base}/payload", dest));
                sw.Stop();
                var ok = result.IsOk ? 1 : 0;
                var kbps = ok == 1 ? Payload / 1024.0 / sw.Elapsed.TotalSeconds : 0;
                rows.Add($"{idx++},B-maxConnections,{c},{rep},{sw.ElapsedMilliseconds},{kbps:F0},{Payload},{ok}");
                Console.WriteLine($"[B3-B] maxConn={c} rep{rep}: {sw.ElapsedMilliseconds}ms {kbps:F0}KB/s ok={ok}");
            }
        }
        await AppendCsvAsync(rows);
    }

    /// <summary>C. OverlapBytes sweep：{16,32,64}×2 rep;拼接校验过+全字节匹配=ok。</summary>
    [WpfFact]
    public async Task C_Overlap_Bytes_Sweep()
    {
        var rows = new List<string> { "idx,phase,candidate,rep,elapsed_ms,throughput_kbps,bytes,ok" };
        var candidates = new[] { 16, 32, 64 };
        var idx = 0;
        foreach (var c in candidates)
        {
            for (var rep = 1; rep <= 2; rep++)
            {
                var dest = ArtifactsPath($"b3-c-{c}-{rep}.bin");
                PurgeStale(dest);
                var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(),
                    maxParallel: 8) { Overlap = c };
                var sw = Stopwatch.StartNew();
                var result = await downloader.DownloadAsync(new HttpDownloadRequest($"{_base}/payload", dest));
                sw.Stop();
                var ok = result.IsOk ? 1 : 0;
                var kbps = ok == 1 ? Payload / 1024.0 / sw.Elapsed.TotalSeconds : 0;
                // 拼接点校验过的另一必要条件：全字节匹配
                if (ok == 1 && !await BytesMatchAsync(dest, Payload)) ok = 2; // 2=校验失败
                rows.Add($"{idx++},C-overlap,{c},{rep},{sw.ElapsedMilliseconds},{kbps:F0},{Payload},{ok}");
                Console.WriteLine($"[B3-C] overlap={c} rep{rep}: {sw.ElapsedMilliseconds}ms {kbps:F0}KB/s ok={ok}");
            }
        }
        await AppendCsvAsync(rows);
    }

    /// <summary>D. 段超时 sweep(ChunkTimeoutMs 锁定依据）:供应=256KB/s;候选 {2000,5000,15000}×2 rep。</summary>
    [WpfFact]
    public async Task D_Segment_Timeout_Sweep()
    {
        // 1MiB 载荷+64KB/250ms 供应（满段约 4.1s):2s 超时应 Timeout,5s/15s 应成功
        const int slowPayload = 1024 * 1024;
        var rows = new List<string> { "idx,phase,candidate,rep,elapsed_ms,throughput_kbps,bytes,ok" };
        var candidates = new[] { 2000, 5000, 15000 };
        var idx = 0;
        foreach (var c in candidates)
        {
            for (var rep = 1; rep <= 2; rep++)
            {
                var dest = ArtifactsPath($"b3-d-{c}-{rep}.bin");
                PurgeStale(dest);
                var downloader = new HttpSegmentDownloader(new HttpClient(), new JsonResumeStore(),
                    maxParallel: 2, requestTimeout: TimeSpan.FromMilliseconds(c));
                var sw = Stopwatch.StartNew();
                var result = await downloader.DownloadAsync(
                    new HttpDownloadRequest($"{_base}/slow?n={slowPayload}", dest));
                sw.Stop();
                var ok = result.IsOk ? 1 : 0;
                rows.Add($"{idx++},D-chunkTimeout,{c},{rep},{sw.ElapsedMilliseconds},,{slowPayload},{ok}");
                Console.WriteLine($"[B3-D] timeout={c}ms rep{rep}: {sw.ElapsedMilliseconds}ms ok={ok} err={result.Error}");
            }
        }
        await AppendCsvAsync(rows);
    }

    // ----------helpers----------

    /// <summary>清旧产物（跨运行 stale .download 续存污染=换签名复跑一致性）。</summary>
    private static void PurgeStale(string dest)
    {
        if (File.Exists(dest)) File.Delete(dest);
        var store = dest + ".download";
        if (File.Exists(store)) File.Delete(store);
    }

    private static (long start, long end) ParseRangeOrFull(string header, long total)
    {
        if (string.IsNullOrEmpty(header) || !header.StartsWith("bytes=", StringComparison.OrdinalIgnoreCase))
            return (0, total - 1);
        var spec = header.Substring("bytes=".Length).Trim();
        var dash = spec.IndexOf('-');
        if (dash <= 0) return (0, total - 1);
        if (!long.TryParse(spec.AsSpan(0, dash), out var start)) return (0, total - 1);
        var endPart = spec.Substring(dash + 1);
        var end = string.IsNullOrEmpty(endPart) ? total - 1 : long.Parse(endPart);
        return (start, Math.Min(end, total - 1));
    }

    private static async Task<bool> BytesMatchAsync(string dest, int expectedLength)
    {
        try
        {
            var bytes = await File.ReadAllBytesAsync(dest);
            if (bytes.Length != expectedLength) return false;
            for (var i = 0; i < bytes.Length; i++)
                if (bytes[i] != (byte)(i % 251)) return false;
            return true;
        }
        catch { return false; }
    }

    private static string ArtifactsPath(string name)
    {
        var dir = B3Artifacts.FindArtifactsDir();
        Directory.CreateDirectory(dir);
        return Path.Combine(dir, name);
    }

    /// <summary>calibration_2.csv 追加（t3 §5.5 原始逐行口径；多次 sweep 追加，头行仅首次写）。</summary>
    private static async Task AppendCsvAsync(List<string> rows)
    {
        var dir = B3Artifacts.FindArtifactsDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "calibration_2.csv");
        var first = !File.Exists(path);
        await using var stream = new FileStream(path, FileMode.Append, FileAccess.Write,
            FileShare.None, 4096, useAsync: true);
        var wroteHeader = false;
        foreach (var line in rows)
        {
            var isHeader = line.StartsWith("idx,");
            if (isHeader && (!first || wroteHeader)) continue;
            if (isHeader) wroteHeader = true;
            var bytes = System.Text.Encoding.UTF8.GetBytes(line + "\n");
            await stream.WriteAsync(bytes).ConfigureAwait(false);
        }
    }

    public void Dispose()
    {
        try { _app.StopAsync().Wait(TimeSpan.FromSeconds(5)); } catch { }
        (_app as IDisposable).Dispose();
    }
}
