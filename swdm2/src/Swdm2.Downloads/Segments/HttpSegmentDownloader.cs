using System.Collections.Concurrent;
using System.Net.Http.Headers;
using Swdm2.Core.Results;

namespace Swdm2.Downloads.Segments;

/// <summary>
/// HTTP 直链分段下载器（D4.5,spec §3.3 Segments):
/// - Range 探测（GET bytes=0-0):206→分段；200(+Accept-Ranges 缺失/单流语义）→回退单流（D6)
/// - in-half division:并发 worker 取段（连接复用=同 HttpClient)
/// - 重叠字节比对（段起点回退 32B,与已写区段比对=续传起点校验，D5)
/// - .download 续存（每段完成原子写）；续传前校验服务器（ETag/Last-Modified 匹配+Range 支持）
/// - kill（ct 取消）后重新调用=续传成功（未完成段重下；已完成段不重下）
/// 沙箱测试=本地 Kestrel fixture（禁公网）。
/// </summary>
public sealed class HttpSegmentDownloader
{
    /// <summary>⚠️[参数待重标定] 重叠字节数（16-64 取中 32;D4.8 实测锁定）。</summary>
    public const int OverlapBytes = 32;

    private readonly HttpClient _client;
    private readonly IResumeStore _store;
    private readonly int _maxParallel;

    /// <summary>测试/诊断 seam（生产=null=真链）。</summary>
    internal Func<HttpSegmentDownloader, HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? SendFunc { get; set; }

    public HttpSegmentDownloader(HttpClient client, IResumeStore store, int? maxParallel = null)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _maxParallel = Math.Clamp(maxParallel ?? SegmentPlanner.DefaultMaxSegments, 1, 64);
    }

    /// <summary>下载（分段或单流；progress=累计字节）。</summary>
    public async Task<Result<long, SteamError>> DownloadAsync(
        HttpDownloadRequest request, IProgress<long>? progress = null, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        var probe = await ProbeAsync(request.Url, ct).ConfigureAwait(false);
        if (probe.Failed)
            return Result<long, SteamError>.Fail(SteamError.Network);

        var dest = request.DestinationPath;
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);

        // 单流回退（不支持 Range / 无总长）
        if (!probe.SupportsRanges || probe.TotalBytes is null or <= 0)
            return await DownloadSingleStreamAsync(request, probe, progress, ct).ConfigureAwait(false);

        var total = probe.TotalBytes.Value;

        // 续传：校验服务器与段表一致
        var resumed = _store.Load(dest);
        Segment[]? doneSegments = null;
        if (resumed is { } meta
            && meta.Url == request.Url
            && meta.TotalBytes == total
            && EtagMatches(meta, probe))
        {
            doneSegments = meta.Segments.Where(s => s.Done).ToArray();
            if (doneSegments.Length > 0 && File.Exists(dest))
            {
                var fi = new FileInfo(dest);
                if (fi.Length != meta.FileLength && fi.Length != total) doneSegments = null;
            }
            else doneSegments = null;
        }

        await using var file = new FileStream(dest, FileMode.OpenOrCreate, FileAccess.Write, FileShare.None,
            bufferSize: 65536, useAsync: true);
        file.SetLength(total);

        var planner = new SegmentPlanner(total, _maxParallel);
        var doneSet = new ConcurrentDictionary<long, long>(); // start→end 已完成
        var received = 0L;

        if (doneSegments is not null)
        {
            foreach (var s in doneSegments)
            {
                planner.Complete(s);
                doneSet[s.Start] = s.End;
                received += s.Length;
            }
            progress?.Report(received);
        }

        var pending = new ConcurrentQueue<Segment>();
        foreach (var s in planner.Snapshot.Where(s => !s.Done)) pending.Enqueue(s);

        var workers = new List<Task>();
        var workerCount = Math.Min(_maxParallel, Math.Max(1, pending.Count));
        for (var i = 0; i < workerCount; i++)
        {
            workers.Add(Task.Run(async () =>
            {
                while (!ct.IsCancellationRequested)
                {
                    if (!pending.TryDequeue(out var seg))
                    {
                        seg = planner.TryAcquire(); // in-half 分裂
                        if (seg is null) return; // 收口/全完成
                    }
                    await DownloadSegmentAsync(file, request.Url, seg, doneSet, ct).ConfigureAwait(false);
                    planner.Complete(seg);
                    doneSet[seg.Start] = seg.End;
                    Interlocked.Add(ref received, seg.Length);
                    progress?.Report(Interlocked.Read(ref received));
                    await PersistAsync(dest, request, total, planner, probe, received).ConfigureAwait(false);
                }
            }, ct));
        }

        try
        {
            await Task.WhenAll(workers).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            await PersistAsync(dest, request, total, planner, probe, Interlocked.Read(ref received))
                .ConfigureAwait(false);
            return Result<long, SteamError>.Fail(SteamError.Cancelled); // kill=续存已落盘，下次续传
        }

        if (!planner.AllDone)
            return Result<long, SteamError>.Fail(SteamError.Network);

        await file.FlushAsync(ct).ConfigureAwait(false);
        _store.Delete(dest);
        return Result<long, SteamError>.Ok(total);
    }

    // ---------- 内步 ----------

    private async Task<RangeProbe> ProbeAsync(string url, CancellationToken ct)
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            req.Headers.Range = new RangeHeaderValue(0, 0); // bytes=0-0
            var resp = await SendAsync(req, ct).ConfigureAwait(false);
            var ok = resp.IsSuccessStatusCode;
            var supports = resp.StatusCode == System.Net.HttpStatusCode.PartialContent
                           && resp.Headers.AcceptRanges.Contains("bytes");
            var total = resp.Content.Headers.ContentRange?.Length;
            var etag = respETag(resp);
            var lastMod = respLastModified(resp);
            resp.Dispose();
            if (!ok) return new RangeProbe(false, null, null, null) { Failed = true };
            return new RangeProbe(supports, total, etag, lastMod);
        }
        catch (OperationCanceledException) { throw; }
        catch
        {
            return new RangeProbe(false, null, null, null) { Failed = true };
        }
    }

    private Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
        => SendFunc?.Invoke(this, req, ct) ?? _client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);

    private static string? respETag(HttpResponseMessage r) => r.Headers.ETag?.Tag;
    private static string? respLastModified(HttpResponseMessage r)
        => r.Content.Headers.LastModified?.ToString("R");

    private static bool EtagMatches(ResumeMetadata meta, RangeProbe probe)
    {
        if (!string.IsNullOrEmpty(meta.ETag) && !string.IsNullOrEmpty(probe.ETag))
            return string.Equals(meta.ETag, probe.ETag, StringComparison.Ordinal);
        if (!string.IsNullOrEmpty(meta.LastModified) && !string.IsNullOrEmpty(probe.LastModified))
            return string.Equals(meta.LastModified, probe.LastModified, StringComparison.Ordinal);
        return true; // 都缺=不校验（同 URL+总长一致即放行）
    }

    /// <summary>单流回退（200-not-206 / 无 Range 支持，D6)。</summary>
    private async Task<Result<long, SteamError>> DownloadSingleStreamAsync(
        HttpDownloadRequest request, RangeProbe probe, IProgress<long>? progress, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, request.Url);
        using var resp = await SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return Result<long, SteamError>.Fail(SteamError.Network);
        await using var src = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        await using var file = new FileStream(request.DestinationPath, FileMode.Create, FileAccess.Write,
            FileShare.None, bufferSize: 65536, useAsync: true);
        var buffer = new byte[65536];
        long received = 0;
        int read;
        while ((read = await src.ReadAsync(buffer, ct).ConfigureAwait(false)) > 0)
        {
            await file.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(false);
            received += read;
            progress?.Report(received);
        }
        _store.Delete(request.DestinationPath);
        return Result<long, SteamError>.Ok(received);
    }

    /// <summary>单段下载+重叠字节比对（续传起点校验，D5)+偏移直写。</summary>
    private async Task DownloadSegmentAsync(
        FileStream file, string url, Segment seg,
        ConcurrentDictionary<long, long> doneSet, CancellationToken ct)
    {
        // 重叠：起点回退 OverlapBytes（前段已写则比对）
        var overlapStart = Math.Max(0, seg.Start - OverlapBytes);
        var applyOverlap = overlapStart < seg.Start && RegionIsDone(doneSet, overlapStart, seg.Start);

        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.Range = new RangeHeaderValue(overlapStart, seg.End - 1);
        using var resp = await SendAsync(req, ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        await using var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);

        var buffer = new byte[seg.End - overlapStart];
        var offset = 0;
        int read;
        while (offset < buffer.Length
               && (read = await stream.ReadAsync(buffer.AsMemory(offset), ct).ConfigureAwait(false)) > 0)
        {
            offset += read;
        }
        if (offset != buffer.Length)
            throw new InvalidDataException($"段数据短读：{offset}/{buffer.Length}");

        var dataOffset = applyOverlap ? OverlapBytes : 0;
        if (applyOverlap)
        {
            // 比对：重叠区字节必须等于已写区（续传起点校验，D5)
            var written = new byte[OverlapBytes];
            file.Seek(overlapStart, SeekOrigin.Begin);
            await file.ReadAsync(written.AsMemory(0, OverlapBytes), ct).ConfigureAwait(false);
            for (var i = 0; i < OverlapBytes; i++)
            {
                if (buffer[dataOffset - OverlapBytes + i] != written[i])
                    throw new InvalidDataException($"拼接点校验失败 @{overlapStart}+{i}");
            }
        }

        file.Seek(seg.Start, SeekOrigin.Begin);
        await file.WriteAsync(buffer.AsMemory(dataOffset, (int)(seg.End - seg.Start)), ct).ConfigureAwait(false);
    }

    private static bool RegionIsDone(ConcurrentDictionary<long, long> doneSet, long from, long to)
    {
        foreach (var kv in doneSet)
            if (kv.Key <= from && kv.Value >= to) return true;
        return false;
    }

    private async Task PersistAsync(string dest, HttpDownloadRequest request, long total,
        SegmentPlanner planner, RangeProbe probe, long received)
    {
        var meta = new ResumeMetadata(
            Url: request.Url, TotalBytes: total, ETag: probe.ETag, LastModified: probe.LastModified,
            FileLength: total, Segments: planner.Snapshot,
            SourcePage: request.SourcePageUrl is null && request.SourcePageParams is null ? null
                : new SourcePageState(request.SourcePageUrl,
                    (IReadOnlyDictionary<string, string>?)request.SourcePageParams ?? new Dictionary<string, string>()));
        try { await _store.SaveAsync(dest, meta).ConfigureAwait(false); }
        catch { /* 续存失败不杀下载（重试即重下该段） */ }
    }
}
