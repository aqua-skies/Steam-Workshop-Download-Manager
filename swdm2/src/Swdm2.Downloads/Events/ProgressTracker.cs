using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;

namespace Swdm2.Downloads.Events;

/// <summary>
/// 进度聚合器（D3.2):每任务 EMA 速度 + ETA 推导。
/// - 瞬时速率=字节增量/时间增量（≤0 或瞬时抖动时用 EMA 平滑，alpha=0.4);
/// - ETA=(TotalBytes-Received)/Speed; 前提不足 → null（UI 诚实 N/A);
/// - 线程安全：每任务一个 Tracker，锁内更新。
/// </summary>
public sealed class ProgressTracker
{
    private readonly object _gate = new();
    private ulong _lastBytes;
    private DateTime _lastSampleUtc;
    private double _emaSpeed;

    /// <summary>EMA 平滑因子（0<alpha<1;越大越贴合瞬时值。⚠️[参数待重标定] C7/D2.6 方法学）。</summary>
    public const double DefaultAlpha = 0.4;

    public DownloadTaskId TaskId { get; }

    public ProgressTracker(DownloadTaskId taskId)
    {
        TaskId = taskId;
    }

    /// <summary>
    /// 采样新进度，返回聚合快照（EMA/ETA 计算在锁内完成）。
    /// </summary>
    public ProgressSnapshot Sample(ulong bytesReceived, ulong? totalBytes, DownloadState? state,
        IReadOnlyList<int>? segments = null, string? message = null,
        DateTime? sampleUtc = null, double alpha = DefaultAlpha)
    {
        var now = sampleUtc ?? DateTime.UtcNow;
        double speed;
        TimeSpan? eta;
        ulong? remaining;

        lock (_gate)
        {
            var elapsed = now - _lastSampleUtc;
            var bytesDelta = bytesReceived > _lastBytes ? bytesReceived - _lastBytes : 0UL;

            if (!_lastSampleUtc.Equals(DateTime.MinValue) && elapsed.TotalSeconds > 0 && bytesDelta > 0)
            {
                var instantaneous = bytesDelta / elapsed.TotalSeconds;
                speed = _emaSpeed <= 0 ? instantaneous : alpha * instantaneous + (1 - alpha) * _emaSpeed;
            }
            else
            {
                speed = _emaSpeed; // 无可测增量：保持上次 EMA（首样本=0)
            }

            _emaSpeed = speed;
            _lastBytes = bytesReceived;
            _lastSampleUtc = now;

            remaining = totalBytes.HasValue && totalBytes.Value > bytesReceived
                ? totalBytes.Value - bytesReceived : null;
            eta = remaining.HasValue && speed > 0
                ? TimeSpan.FromSeconds(remaining.Value / speed) : null;
        }

        return new ProgressSnapshot(TaskId, state, bytesReceived, totalBytes, speed, eta,
            ProgressSnapshot.CopySegments(segments), message);
    }
}
