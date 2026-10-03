using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// A4「过冲回弹」(t55 D5.16;spec §2.10 A4):
/// 卡片/弹层放缩进入 scale 0.94→1.03→1,**300ms,BackEase（片幅 1.3)**;
/// ElasticEase 备选（弹 2 次）。统一换装入口=PopIn(entry)/PopOut(exit)。
/// A7 终态可断言：完成回调钉死 scale=1（中间帧 1.03 不得被采样为终态）。
/// </summary>
public static class Overshoot
{
    /// <summary>过冲回弹总时长 300ms(spec §2.10 A4)。</summary>
    public const int DurationMs = 300;

    /// <summary>进入起点缩放 0.94(spec)。</summary>
    public const double FromScale = 0.94;

    /// <summary>过冲峰值 1.03(spec A4"0.94→1.03→1")。</summary>
    public const double PeakScale = 1.03;

    /// <summary>终态缩放 1.0(A7 钉死值）。</summary>
    public const double FinalScale = 1.0;

    /// <summary>回弹峰值时刻占比（70%)。</summary>
    public const double PeakKeyTimeFraction = 0.7;

    /// <summary>过冲关键帧时间线（模型=纯逻辑可断言，无需渲染）。</summary>
    public static IReadOnlyList<OvershootKey> BuildKeyframes()
        => new[]
        {
            new OvershootKey(0.0, FromScale),
            new OvershootKey(PeakKeyTimeFraction, PeakScale),
            new OvershootKey(1.0, FinalScale),
        };

    /// <summary>放缩进入（0.94→1.03→1)。root=承载 ScaleTransform 的元素。</summary>
    public static void PopIn(FrameworkElement root, string track = "A4-pop")
    {
        if (root is null) return;
        AniHelper.StopAll(root);
        EnsureScale(root);
        var scale = (ScaleTransform)root.RenderTransform;
        scale.ScaleX = FromScale;
        scale.ScaleY = FromScale;
        var sb = new Storyboard();
        var kx = BuildKeyframeAnimation();
        var ky = BuildKeyframeAnimation();
        Storyboard.SetTarget(kx, root);
        Storyboard.SetTargetProperty(kx, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleX)"));
        Storyboard.SetTarget(ky, root);
        Storyboard.SetTargetProperty(ky, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleY)"));
        sb.Children.Add(kx);
        sb.Children.Add(ky);
        sb.Completed += (_, _) =>
        {
            // A7 终态钉死
            scale.ScaleX = FinalScale;
            scale.ScaleY = FinalScale;
        };
        sb.Begin();
    }

    /// <summary>放缩退出（1→0.94+淡出 200ms;反向配套）。</summary>
    public static void PopOut(FrameworkElement root, string track = "A4-pop")
    {
        if (root is null) return;
        AniHelper.StopAll(root);
        EnsureScale(root);
        var sb = new Storyboard();
        var opacity = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(200));
        var scale = new DoubleAnimation(1, FromScale, TimeSpan.FromMilliseconds(200))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(opacity, root);
        Storyboard.SetTargetProperty(opacity, new PropertyPath(UIElement.OpacityProperty));
        Storyboard.SetTarget(scale, root);
        Storyboard.SetTargetProperty(scale, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleX)"));
        sb.Children.Add(opacity);
        sb.Children.Add(scale);
        sb.Begin();
    }

    /// <summary>Elastic 备选通道（spec"弹 2 次"):1→1.06→0.98→1。</summary>
    public static void ElasticPopIn(FrameworkElement root, string track = "A4-elastic")
    {
        if (root is null) return;
        AniHelper.StopAll(root);
        EnsureScale(root);
        var anim = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromMilliseconds(DurationMs) };
        anim.KeyFrames.Add(new LinearDoubleKeyFrame(FromScale, KeyTime.FromPercent(0)));
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(1.06, KeyTime.FromPercent(0.5), new ElasticEase()));
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(0.98, KeyTime.FromPercent(0.75), new ElasticEase()));
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(FinalScale, KeyTime.FromPercent(1)));
        var sb = new Storyboard();
        Storyboard.SetTarget(anim, root);
        Storyboard.SetTargetProperty(anim, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleX)"));
        sb.Children.Add(anim);
        sb.Completed += (_, _) => ((ScaleTransform)root.RenderTransform).ScaleX = FinalScale;
        sb.Begin();
    }

    private static DoubleAnimationUsingKeyFrames BuildKeyframeAnimation()
    {
        var anim = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromMilliseconds(DurationMs) };
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(FromScale, KeyTime.FromPercent(0), new QuinticEase()));
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(PeakScale, KeyTime.FromPercent(PeakKeyTimeFraction), new QuinticEase()));
        anim.KeyFrames.Add(new EasingDoubleKeyFrame(FinalScale, KeyTime.FromPercent(1), new QuinticEase()));
        return anim;
    }

    private static void EnsureScale(FrameworkElement fe)
    {
        if (fe.RenderTransform is ScaleTransform) return;
        fe.RenderTransform = new ScaleTransform(FromScale, FromScale);
        fe.RenderTransformOrigin = new Point(0.5, 0.5);
    }
}

/// <summary>过冲关键帧（scale @ 归一化时间）。</summary>
public sealed record OvershootKey(double TimeFraction, double Scale);
