using System.Collections.Concurrent;

namespace Swdm2.Downloads.Segments;

/// <summary>
/// IDM in-half division 段规划器（D4.5,spec §3.3 ISegmentPlanner):
/// - 初始 N 段（min(注入并发，总长/最小段）=均衡负载）
/// - 段完成→从最大未完成段中点分裂→指派空闲 worker（段长==1B 时不分裂=收口）
/// 线程安全（锁内分裂决策）。
/// </summary>
public sealed class SegmentPlanner
{
    /// <summary>⚠️[参数待重标定] 初始段数上限（D4.8 B3 并发重标定）。</summary>
    public const int DefaultMaxSegments = 8;

    /// <summary>⚠️[参数待重标定] 最小段长（避免碎段风暴）。</summary>
    public const long DefaultMinSegmentBytes = 1024 * 1024;

    private readonly object _gate = new();
    private readonly ConcurrentQueue<Segment> _pending = new();
    private readonly List<Segment> _all = new();
    private readonly long _minSegmentBytes;
    private readonly int _maxSegments;

    public SegmentPlanner(long totalLength, int? maxSegments = null, long? minSegmentBytes = null)
    {
        if (totalLength <= 0) throw new ArgumentOutOfRangeException(nameof(totalLength));
        _maxSegments = Math.Clamp(maxSegments ?? DefaultMaxSegments, 1, 64);
        _minSegmentBytes = Math.Max(1, minSegmentBytes ?? DefaultMinSegmentBytes);

        var initial = Math.Min(_maxSegments, Math.Max(1, (long)Math.Ceiling((double)totalLength / _minSegmentBytes)));
        var per = totalLength / initial;
        long pos = 0;
        for (var i = 0; i < initial; i++)
        {
            var end = i == initial - 1 ? totalLength : pos + per;
            _all.Add(new Segment(pos, end));
            _pending.Enqueue(new Segment(pos, end));
            pos = end;
        }
    }

    /// <summary>取下一段（无待做段=返回 null;会尝试分裂最大未完成段——仅分裂**未在途**段）。</summary>
    public Segment? TryAcquire()
    {
        lock (_gate)
        {
            if (_pending.TryDequeue(out var seg))
            {
                _inFlight.Add((seg.Start, seg.End));
                return seg;
            }
            // 分裂最大未完成且未在途段（in-half division;在途段分裂=两 worker 写重叠区=内容交错损坏）
            if (_all.Count >= _maxSegments * 4) return null; // 收口防爆段
            var candidate = _all.Where(s => !s.Done && !_inFlight.Contains((s.Start, s.End)) && s.Length > _minSegmentBytes * 2)
                .OrderByDescending(s => s.Length).FirstOrDefault();
            if (candidate is null || candidate.Start == candidate.End) return null;
            var mid = candidate.Start + candidate.Length / 2;
            var left = candidate with { End = mid };
            var right = new Segment(mid, candidate.End);
            _all.Remove(candidate);
            _inFlight.Remove((candidate.Start, candidate.End)); // 防御性
            _all.Add(left);
            _all.Add(right);
            _pending.Enqueue(right);
            _inFlight.Add((left.Start, left.End));
            return left;
        }
    }

    /// <summary>段完成登记（移除在途标记+置 Done)。</summary>
    public void Complete(Segment segment)
    {
        lock (_gate)
        {
            _inFlight.Remove((segment.Start, segment.End));
            var idx = _all.FindIndex(s => s.Start == segment.Start && s.End == segment.End);
            if (idx >= 0) _all[idx] = segment with { Done = true };
        }
    }

    private readonly HashSet<(long start, long end)> _inFlight = new(); // 键元组规避 record Done 变更的 hash 漂移

    /// <summary>全部完成。</summary>
    public bool AllDone
    {
        get { lock (_gate) return _all.Count > 0 && _all.All(s => s.Done); }
    }

    /// <summary>当前段快照（续存/断言用）。</summary>
    public IReadOnlyList<Segment> Snapshot
    {
        get { lock (_gate) return _all.ToList(); }
    }
}
