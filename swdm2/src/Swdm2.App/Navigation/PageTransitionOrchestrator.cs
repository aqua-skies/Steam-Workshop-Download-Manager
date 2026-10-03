using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Swdm2.App.Ui.Controls;

namespace Swdm2.App.Ui.Navigation;

/// <summary>
/// A3「页面分离编排」骨架（t55 D5.16;spec §2.10 A3 + §2.8.4):
/// 前进（详情类标签）：左选项文字左移虚化→选项卡左抽→主区让出→详情进入；
/// 回程（切主页类标签）：选项卡右拉出→内容上→下右拉半透明→凝实。
/// **终值常量待 visual-20 t54 球体退场时序落地后对齐**(captain 调序令）：
/// 时间线模型+状态机+相序现已就位；SphereProfile 采用 §2.8.4 起点值
/// (250/200/200 重叠 100ms,⚠️[参数待重标定]),t54 落地后复核。
/// A7 终态可断言：每阶段 Completed 钉死终值；全部完成 State=Idle 且
/// FinalSnapshot 记录（逻辑等价=ENV-DOWNGRADE 门：沙箱无渲染时间线可纯断言）。
/// </summary>
public sealed class PageTransitionOrchestrator
{
    /// <summary>编排状态机。</summary>
    public enum TransitionState { Idle, ForwardExiting, ForwardEntering, HomeReturning, HomeSettling }

    /// <summary>阶段（相序=spec 原文顺序）。</summary>
    public enum Phase { TextFade, TabDrawer, MainYield, DetailEnter }

    /// <summary>前进四相（顺序=规格）。</summary>
    private static readonly Phase[] ForwardOrder =
        { Phase.TextFade, Phase.TabDrawer, Phase.MainYield, Phase.DetailEnter };

    /// <summary>回程逆序（选项卡右拉→内容凝实=HomeReturn 逆放）。</summary>
    private static readonly Phase[] HomeReturnOrder =
        { Phase.TabDrawer, Phase.TextFade, Phase.MainYield };

    private readonly List<TransitionStep> _timeline = new();
    private TransitionState _state = TransitionState.Idle;
    private int _phaseIndex = -1;

    /// <summary>当前状态。</summary>
    public TransitionState State => _state;

    /// <summary>展开的时间线（纯逻辑可断言）。</summary>
    public IReadOnlyList<TransitionStep> Timeline => _timeline;

    /// <summary>终态快照（A7 断言锚点：每相终值记录）。</summary>
    public IReadOnlyDictionary<Phase, double> FinalSnapshot => _final;
    private readonly Dictionary<Phase, double> _final = new();

    /// <summary>启动前进编排（详情进入）。</summary>
    public void StartForward(TransitionTargets targets, TransitionTimingProfile? profile = null)
    {
        if (_state != TransitionState.Idle) Cancel();
        var p = profile ?? TransitionTimingProfile.DetailProfile;
        BuildTimeline(ForwardOrder, p, targets);
        _state = TransitionState.ForwardExiting;
        _phaseIndex = -1;
        PlayNextPhase(targets);
    }

    /// <summary>启动回程编排（切回主页类标签）。</summary>
    public void StartHomeReturn(TransitionTargets targets, TransitionTimingProfile? profile = null)
    {
        if (_state != TransitionState.Idle) Cancel();
        var p = profile ?? TransitionTimingProfile.DetailProfile;
        BuildTimeline(HomeReturnOrder, p, targets);
        _state = TransitionState.HomeReturning;
        _phaseIndex = -1;
        PlayNextPhase(targets);
    }

    /// <summary>取消（同轨道先停旧=防叠加闪烁）。</summary>
    public void Cancel()
    {
        _timeline.Clear();
        _final.Clear();
        _phaseIndex = -1;
        _state = TransitionState.Idle;
    }

    private void BuildTimeline(Phase[] order, TransitionTimingProfile p, TransitionTargets t)
    {
        _timeline.Clear();
        var elapsed = 0.0;
        foreach (var phase in order)
        {
            // 目标缺失的相位不入时间线（可组合：调用方按场景注入子集；
            // 不入=不播，与 PlayNextPhase 的跳过语义一致）
            if (TargetFor(phase, t) is null) continue;
            var (dur, overlap) = p[phase];
            var start = Math.Max(0, elapsed - overlap);
            _timeline.Add(new TransitionStep(phase, start, dur));
            elapsed = start + dur;
        }
    }

    private static FrameworkElement? TargetFor(Phase phase, TransitionTargets t) => phase switch
    {
        Phase.TextFade => t.TextPanel,
        Phase.TabDrawer => t.TabStrip,
        Phase.MainYield => t.MainArea,
        Phase.DetailEnter => t.IncomingPage,
        _ => null,
    };

    private void PlayNextPhase(TransitionTargets targets)
    {
        _phaseIndex++;
        if (_phaseIndex >= _timeline.Count)
        {
            _state = TransitionState.Idle;
            return;
        }
        var step = _timeline[_phaseIndex];
        var element = step.Phase switch
        {
            Phase.TextFade => targets.TextPanel,
            Phase.TabDrawer => targets.TabStrip,
            Phase.MainYield => targets.MainArea,
            Phase.DetailEnter => targets.IncomingPage,
            _ => null,
        };
        if (element is null)
        {
            // 目标缺相位=跳过（可组合：调用方按场景注入子集）
            PlayNextPhase(targets);
            return;
        }
        AniHelper.StopAll(element);
        var sb = new Storyboard();
        var opacityFrom = step.Phase == Phase.DetailEnter ? 0.0 : 1.0;
        var opacityTo = step.Phase == Phase.MainYield ? 0.0 : 1.0;
        var translateFrom = step.Phase == Phase.DetailEnter ? 40.0 : 0.0;
        var translateTo = step.Phase == Phase.TextFade || step.Phase == Phase.TabDrawer || step.Phase == Phase.MainYield
            ? -40.0 : 0.0;
        var opacity = new DoubleAnimation(opacityFrom, opacityTo, TimeSpan.FromMilliseconds(step.DurationMs))
        { EasingFunction = new QuinticEase() };
        EnsureTranslate(element);
        var translate = new DoubleAnimation(translateFrom, translateTo, TimeSpan.FromMilliseconds(step.DurationMs))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(opacity, element);
        Storyboard.SetTargetProperty(opacity, new PropertyPath(UIElement.OpacityProperty));
        Storyboard.SetTarget(translate, element);
        Storyboard.SetTargetProperty(translate, new PropertyPath("(UIElement.RenderTransform).(TranslateTransform.Y)"));
        sb.Children.Add(opacity);
        sb.Children.Add(translate);
        sb.Completed += (_, _) =>
        {
            // A7 终态钉死（防中间帧采样误判）
            element.Opacity = opacityTo;
            ((TranslateTransform)element.RenderTransform).Y = translateTo;
            _final[step.Phase] = opacityTo;
            PlayNextPhase(targets);
        };
        sb.Begin();
    }

    private static void EnsureTranslate(FrameworkElement fe)
    {
        if (fe.RenderTransform is TranslateTransform) return;
        fe.RenderTransform = new TranslateTransform();
    }
}

/// <summary>编排目标集（可按场景注入子集=可组合）。</summary>
public sealed class TransitionTargets
{
    public FrameworkElement? TextPanel { get; init; }
    public FrameworkElement? TabStrip { get; init; }
    public FrameworkElement? MainArea { get; init; }
    public FrameworkElement? IncomingPage { get; init; }
}

/// <summary>单步时间线（相+起始+时长）。</summary>
public sealed record TransitionStep(PageTransitionOrchestrator.Phase Phase, double StartMs, double DurationMs)
{
    /// <summary>该步完成时刻。</summary>
    public double EndMs => StartMs + DurationMs;
}

/// <summary>
/// 编排时长剖面（每相=时长+与上一相的重叠）。
/// DetailProfile=spec §2.10 A3 起点值；SphereProfile=§2.8.4 球体主页三点序
/// (250 球后移虚化→200 文字左移重叠 100→200 选项卡左抽）——⚠️[参数待重标定]
/// **终值待 t54(D5.15 球体主页）落地后对齐**。
/// </summary>
public sealed class TransitionTimingProfile
{
    public static readonly TransitionTimingProfile DetailProfile = new(
        textFade: (200, 0), tabDrawer: (200, 100), mainYield: (150, 0), detailEnter: (250, 0));

    /// <summary>§2.8.4 球体主页退场剖面（起点值；t54 落地后复核）。</summary>
    public static readonly TransitionTimingProfile SphereProfile = new(
        textFade: (200, 100), tabDrawer: (200, 0), mainYield: (0, 0), detailEnter: (0, 0));

    private readonly Dictionary<PageTransitionOrchestrator.Phase, (double durationMs, double overlapMs)> _map;

    public TransitionTimingProfile(
        (double durationMs, double overlapMs) textFade,
        (double durationMs, double overlapMs) tabDrawer,
        (double durationMs, double overlapMs) mainYield,
        (double durationMs, double overlapMs) detailEnter)
    {
        _map = new()
        {
            [PageTransitionOrchestrator.Phase.TextFade] = textFade,
            [PageTransitionOrchestrator.Phase.TabDrawer] = tabDrawer,
            [PageTransitionOrchestrator.Phase.MainYield] = mainYield,
            [PageTransitionOrchestrator.Phase.DetailEnter] = detailEnter,
        };
    }

    public (double durationMs, double overlapMs) this[PageTransitionOrchestrator.Phase phase] => _map[phase];
}
