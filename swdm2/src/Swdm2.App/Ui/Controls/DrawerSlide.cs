using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// A2「拉抽屉」下拉动画（t55 D5.16;spec §2.10 A2):
/// 面板自顶部下滑展开——RenderTransform TranslateY 由 -降距→0 + Opacity 0→1,
/// 300ms QuinticEase（来源选择类设置面板）。回程=上滑收起（反向同曲线）。
/// ⚠️[参数待重标定] 300ms 为 spec 起点值；A7 终态可断言（Completed 里钉死 0/1)。
/// </summary>
public static class DrawerSlide
{
    /// <summary>抽屉动画时长 300ms(spec §2.10 A2)。</summary>
    public const int DurationMs = 300;

    /// <summary>下拉滑出（面板从顶部滑入展开位置）。</summary>
    public static void SlideDown(FrameworkElement panel, string track = "A2-drawer")
    {
        if (panel is null) return;
        AniHelper.StopAll(panel);
        panel.Opacity = 0;
        EnsureTranslate(panel);
        ((TranslateTransform)panel.RenderTransform).Y = -panel.ActualHeight;
        var sb = new Storyboard();
        var opacity = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        var y = new DoubleAnimation(-panel.ActualHeight, 0, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(opacity, panel);
        Storyboard.SetTargetProperty(opacity, new PropertyPath(UIElement.OpacityProperty));
        Storyboard.SetTarget(y, panel);
        Storyboard.SetTargetProperty(y, new PropertyPath("(UIElement.RenderTransform).(TranslateTransform.Y)"));
        sb.Children.Add(opacity);
        sb.Children.Add(y);
        sb.Completed += (_, _) =>
        {
            // A7 终态钉死（防中间帧采样误判）
            panel.Opacity = 1;
            ((TranslateTransform)panel.RenderTransform).Y = 0;
        };
        sb.Begin();
    }

    /// <summary>上拉收起（反向；收完后折叠由调用方处理）。</summary>
    public static void SlideUp(FrameworkElement panel, string track = "A2-drawer")
    {
        if (panel is null) return;
        AniHelper.StopAll(panel);
        EnsureTranslate(panel);
        var target = -panel.ActualHeight;
        var sb = new Storyboard();
        var opacity = new DoubleAnimation(panel.Opacity, 0, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        var y = new DoubleAnimation(((TranslateTransform)panel.RenderTransform).Y, target,
            TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(opacity, panel);
        Storyboard.SetTargetProperty(opacity, new PropertyPath(UIElement.OpacityProperty));
        Storyboard.SetTarget(y, panel);
        Storyboard.SetTargetProperty(y, new PropertyPath("(UIElement.RenderTransform).(TranslateTransform.Y)"));
        sb.Children.Add(opacity);
        sb.Children.Add(y);
        sb.Begin();
    }

    private static void EnsureTranslate(FrameworkElement fe)
    {
        if (fe.RenderTransform is TranslateTransform) return;
        fe.RenderTransform = new TranslateTransform();
    }
}
