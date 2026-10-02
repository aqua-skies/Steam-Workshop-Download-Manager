using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Events;

/// <summary>
/// 进度快照（事件负载；D3.2):**不可变 record**(C1/Core D1.1 纪律）。
/// 字段契约（visual-20 D3.2 对齐 t28/t5.10 行级断言 _SpeedText/_EtaText/_SegmentsText):
/// - 速度 EMA（平滑瞬时速率；1.x 学费：瞬时速率抖动 UI 跳变）
/// - ETA（剩余时间；TotalBytes 或速度未知时为 null=UI 诚实 N/A)
/// - 分段数（provider 知则给，未知 null → UI N/A 诚实降级）
/// - 字节数/状态/消息
/// </summary>
/// <param name="TaskId">任务 id。</param>
/// <param name="State">状态机当前态（D3.1)。</param>
/// <param name="BytesReceived">已接收字节。</param>
/// <param name="TotalBytes">总字节；未知=null。</param>
/// <param name="SpeedBytesPerSec">EMA 平速度（字节/秒）;首样本前=0。</param>
/// <param name="Eta">剩余时间；计算前提不足=null。</param>
/// <param name="Segments">分段数（如分片下载）；未知=null。</param>
/// <param name="Message">附加消息（错误码/阶段提示；UI Hint 四档映射点）。</param>
public sealed record ProgressSnapshot(
    DownloadTaskId TaskId,
    DownloadState? State,
    ulong BytesReceived,
    ulong? TotalBytes,
    double SpeedBytesPerSec,
    TimeSpan? Eta,
    IReadOnlyList<int>? Segments,
    string? Message)
{
    /// <summary>分段数可空单值构造（常见场景）。</summary>
    public ProgressSnapshot(
        DownloadTaskId taskId, DownloadState? state, ulong bytesReceived, ulong? totalBytes,
        double speedBytesPerSec, TimeSpan? eta, int? segments, string? message)
        : this(taskId, state, bytesReceived, totalBytes, speedBytesPerSec, eta,
            segments is null ? null : new List<int> { segments.Value }, message)
    {
    }

    /// <summary>结构性相等（record 默认；Segments 按元素比较——C5 缓存语义同 WorkshopItem)。</summary>
    public bool Equals(ProgressSnapshot? other)
        => other is not null
           && TaskId == other.TaskId
           && State == other.State
           && BytesReceived == other.BytesReceived
           && TotalBytes == other.TotalBytes
           && SpeedBytesPerSec == other.SpeedBytesPerSec
           && Eta == other.Eta
           && Segments is null == (other.Segments is null)
           && (Segments is null || Segments.SequenceEqual(other.Segments!))
           && Message == other.Message;

    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(TaskId);
        hash.Add(State);
        hash.Add(BytesReceived);
        hash.Add(TotalBytes);
        hash.Add(SpeedBytesPerSec);
        hash.Add(Eta);
        hash.Add(Message);
        if (Segments is not null) foreach (var s in Segments) hash.Add(s);
        return hash.ToHashCode();
    }

    /// <summary>构造时防御性拷贝 Segments（外部 List 突变不污染快照，C1/C5)。</summary>
    internal static IReadOnlyList<int>? CopySegments(IReadOnlyList<int>? segments)
        => segments is null ? null : new List<int>(segments).AsReadOnly();
}
