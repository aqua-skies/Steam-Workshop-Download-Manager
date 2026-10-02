using System.Diagnostics;
using System.Collections.Concurrent;
using System.Net.Http.Headers;
using Swdm2.Core.Results;
using Swdm2.Downloads.Disk;
using Swdm2.Downloads.Limiter;

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
    /// <summary>⚠️[D4.8 已锁定=16] 重叠字节数（拼接点校验，D5;spec 16-64 区间；本地 Kestrel 实测 16/32/64 全过+全字节匹配→取最小省带宽）。</summary>
    public const int OverlapBytes = 16;

    private readonly HttpClient _client;
    private readonly IResumeStore _store;
    private readonly int _maxParallel;

    /// <summary>测试/诊断 seam（生产=null=真链）。</summary>
    internal Func<HttpSegmentDownloader, HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? SendFunc { get; set; }

    /// <summary>稀疏分配器 seam（生产=null=默认 SparseFileAllocator;注入假=模拟 exFAT 降级）。</summary>
    internal ISparseFileAllocator? Allocator { get; set; }

    /// <summary>D4.7 限速双点之一：HTTP 读流点（null=不限速）。</summary>
    internal ISpeedLimiter? Limiter { get; set; }

    public HttpSegmentDownloader(HttpClient client, IResumeStore store, int? maxParallel = null,
        ISpeedLimiter? limiter = null, TimeSpan? requestTimeout = null)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _maxParallel = Math.Clamp(maxParallel ?? SegmentPlanner.DefaultMaxSegments, 1, 64);
        Limiter = limiter;
        RequestTimeout = requestTimeout ?? TimeSpan.FromSeconds(30);
    }

    /// <summary>⚠️[D4.8 标定] 段请求超时（慢端点错误率拐点测量用；默认 30s)。</summary>
    public TimeSpan RequestTimeout { get; set; }

    /// <summary>⚠️[D4.8 标定] 重叠字节（拼接点校验 D5;默认=OverlapBytes 常量 32;16-64 spec 区间实测锁定）。</summary>
    public int Overlap { get; set; } = OverlapBytes;

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

        // D4.6 磁盘域：稀疏占位（NTFS）+偏移直写器（exFAT 降级由分配器返回 Method 标注）
        // isResume=文件已存在（部分下载/续传=下载期文件复用，D8 不可逆护栏放行）
        var allocation = await (Allocator ?? new SparseFileAllocator()).AllocateForDownloadAsync(
            dest, total, isResume: File.Exists(dest), ct).ConfigureAwait(false);
        await using var writer = new OffsetFileWriter(dest, total);

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
                    await DownloadSegmentAsync(writer, request.Url, seg, doneSet, ct).ConfigureAwait(false);
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
        catch (OperationCanceledException)
        {
            // D4.8: 请求超时作用域触发（用户未取消）→Timeout 优雅失败而非异常逃逸
            await PersistAsync(dest, request, total, planner, probe, Interlocked.Read(ref received))
                .ConfigureAwait(false);
            return Result<long, SteamError>.Fail(SteamError.Timeout);
        }

        if (!planner.AllDone)
            return Result<long, SteamError>.Fail(SteamError.Network);

        await writer.CompleteAsync(ct).ConfigureAwait(false);
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

    private async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
    {
        if (SendFunc is not null) return await SendFunc(this, req, ct).ConfigureAwait(false);
        return await _client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
    }

    /// <summary>请求级超时作用域（D4.8:读流也纳入超时，否则慢端点超时只作用于 header 阶段=判别失真）。</summary>
    internal CancellationTokenSource CreateRequestScope(CancellationToken ct)
    {
        var scope = CancellationTokenSource.CreateLinkedTokenSource(ct);
        scope.CancelAfter(RequestTimeout);
        return scope;
    }

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
        using var reqScope = CreateRequestScope(ct); // D4.8: 超时含读流
        using var resp = await SendAsync(req, reqScope.Token).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return Result<long, SteamError>.Fail(SteamError.Network);
        await using var src = await resp.Content.ReadAsStreamAsync(reqScope.Token).ConfigureAwait(false);
        await using var file = new FileStream(request.DestinationPath, FileMode.Create, FileAccess.Write,
            FileShare.None, bufferSize: 65536, useAsync: true);
        var buffer = new byte[65536];
        long received = 0;
        int read;
        while ((read = await src.ReadAsync(buffer, ct).ConfigureAwait(false)) > 0)
        {
            await file.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(false);
            received += read;
            // D4.7 限速双点之一：单流回退同样读流节流（一致性）
            if (Limiter is not null) await Limiter.WaitAsync(read, ct).ConfigureAwait(false);
            progress?.Report(received);
        }
        _store.Delete(request.DestinationPath);
        return Result<long, SteamError>.Ok(received);
    }

    /// <summary>单段下载+重叠字节比对（续传起点校验，D5)+偏移直写。</summary>
    private async Task DownloadSegmentAsync(
        IOffsetFileWriter file, string url, Segment seg,
        ConcurrentDictionary<long, long> doneSet, CancellationToken ct)
    {
        // 重叠：起点回退 OverlapBytes（前段已写则比对）
        var overlapStart = Math.Max(0, seg.Start - Overlap);
        var applyOverlap = overlapStart < seg.Start && RegionIsDone(doneSet, overlapStart, seg.Start);

        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.Range = new RangeHeaderValue(overlapStart, seg.End - 1);
        // D4.8: 超时作用域覆盖读流（慢端点判别力）
        using var reqScope = CreateRequestScope(ct);
        var reqToken = reqScope.Token;
        using var resp = await SendAsync(req, reqToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        await using var stream = await resp.Content.ReadAsStreamAsync(reqToken).ConfigureAwait(false);

        var buffer = new byte[seg.End - overlapStart];
        var offset = 0;
        int read;
        while (offset < buffer.Length
               && (read = await stream.ReadAsync(buffer.AsMemory(offset), reqToken).ConfigureAwait(false)) > 0)
        {
            offset += read;
            // D4.7 限速双点之一：HTTP 读流点（令牌桶按实际读取字节消费）
            if (Limiter is not null) await Limiter.WaitAsync(read, ct).ConfigureAwait(false);
        }
        if (offset != buffer.Length)
            throw new InvalidDataException($"段数据短读：{offset}/{buffer.Length}");

        // fetch 恒含 [overlapStart, seg.Start) 前缀（seg.Start>0 时 32B):写偏移须跳过前缀
        // （D4.8 修复：applyOverlap=false 时 dataOffset=0 会把上一段尾部写进自己区=错位污染）
        var dataOffset = seg.Start > overlapStart ? Overlap : 0;
        if (applyOverlap)
        {
            // 比对：重叠区字节必须等于已写区（续传起点校验，D5)
            var written = await file.ReadAtAsync(overlapStart, Overlap, ct).ConfigureAwait(false);
            for (var i = 0; i < written.Length; i++)
            {
                if (buffer[dataOffset - Overlap + i] != written[i])
                    throw new InvalidDataException($"拼接点校验失败 @{overlapStart}+{i}");
            }
        }

        await file.WriteAtAsync(seg.Start, buffer.AsMemory(dataOffset, (int)(seg.End - seg.Start)), ct)
            .ConfigureAwait(false);
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
