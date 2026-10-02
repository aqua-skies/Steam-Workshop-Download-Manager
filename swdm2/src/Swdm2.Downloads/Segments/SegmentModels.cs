using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Downloads.Segments;

/// <summary>
/// HTTP 直链分段模型（D4.5,spec §3.3 Segments 域）:
/// - 段 = [Start,End) 闭半开；重叠字节=段起点回退比对（D5 完整性纪律，⚠️[参数待重标定] 16-64B 取 32)
/// - RangeProbe=HEAD/轻探测结果（Accept-Ranges+Content-Length+ETag/Last-Modified;200-not-206→单流）
/// - 续传元数据=.download 尾部文件（JSON;URL/ETag/段表/来源页参数 D7)
/// </summary>
public sealed record Segment(long Start, long End)
{
    /// <summary>段长度。</summary>
    public long Length => End - Start;

    /// <summary>是否完成。</summary>
    public bool Done { get; init; }
}

/// <summary>Range 探测结果（D6)。</summary>
public sealed record RangeProbe(bool SupportsRanges, long? TotalBytes, string? ETag, string? LastModified)
{
    /// <summary>探测失败（网络/状态码异常）。</summary>
    public bool Failed { get; init; }
}

/// <summary>来源页参数（任务持久化；失效链路重解析用，D7)。</summary>
public sealed record SourcePageState(string? PageUrl, IReadOnlyDictionary<string, string> Params);

/// <summary>.download 续传元数据（D7:随文件持久化）。</summary>
public sealed record ResumeMetadata(
    string Url,
    long? TotalBytes,
    string? ETag,
    string? LastModified,
    long FileLength,
    IReadOnlyList<Segment> Segments,
    SourcePageState? SourcePage)
{
    /// <summary>兼容 JSON 序列化（System.Text.Json 反序列化用）。</summary>
    public ResumeMetadata() : this(string.Empty, null, null, null, 0,
        Array.Empty<Segment>(), null) { }
}

/// <summary>HTTP 下载请求（直链场景：预览图/直链 CDN 资源）。</summary>
public sealed record HttpDownloadRequest(
    string Url,
    string DestinationPath,
    string? SourcePageUrl = null,
    IReadOnlyDictionary<string, string>? SourcePageParams = null);
