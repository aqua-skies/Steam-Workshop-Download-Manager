using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Swdm2.App.Ui.Controls;

namespace Swdm2.App.Ui.Chrome;

/// <summary>
/// A5「标题钮放大」(t55 D5.16;spec §2.10 A5):
/// 窗口标题钮（最小化/关闭 14×14 图标位）→ hover **scale 1.1,150ms QuinticEase**;
/// 离开复原同曲线。附载=标题钮 Button 上 `TitleButtonHover.Enable`。
/// A7 终态可断言：hover 完成 scale=1.1；离开完成 scale=1.0。
/// </summary>
public static class TitleButtonHover
{
    /// <summary>悬停放大目标 1.1(spec A5)。</summary>
    public const double HoverScale = 1.1;

    /// <summary>悬停动画时长 150ms(spec A5)。</summary>
    public const int DurationMs = 150;

    /// <summary>附载开关（XAML: chrome:TitleButtonHover.Enable="True")。</summary>
    public static readonly DependencyProperty EnableProperty =
        DependencyProperty.RegisterAttached("Enable", typeof(bool), typeof(TitleButtonHover),
            new PropertyMetadata(false, OnEnableChanged));

    public static bool GetEnable(DependencyObject d) => (bool)d.GetValue(EnableProperty);
    public static void SetEnable(DependencyObject d, bool value) => d.SetValue(EnableProperty, value);

    private static void OnEnableChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not Button btn) return;
        var enabled = (bool)e.NewValue;
        if (enabled)
        {
            btn.MouseEnter += OnEnter;
            btn.MouseLeave += OnLeave;
            EnsureScale(btn);
        }
        else
        {
            btn.MouseEnter -= OnEnter;
            btn.MouseLeave -= OnLeave;
        }
    }

    private static void OnEnter(object sender, System.Windows.Input.MouseEventArgs e)
    {
        if (sender is not Button btn) return;
        EnsureScale(btn);
        AniHelper.StopAll(btn);
        var sb = new Storyboard();
        var sx = new DoubleAnimation(1.0, HoverScale, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        var sy = new DoubleAnimation(1.0, HoverScale, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(sx, btn);
        Storyboard.SetTargetProperty(sx, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleX)"));
        Storyboard.SetTarget(sy, btn);
        Storyboard.SetTargetProperty(sy, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleY)"));
        sb.Children.Add(sx);
        sb.Children.Add(sy);
        sb.Begin();
    }

    private static void OnLeave(object sender, System.Windows.Input.MouseEventArgs e)
    {
        if (sender is not Button btn) return;
        EnsureScale(btn);
        AniHelper.StopAll(btn);
        var sb = new Storyboard();
        var sx = new DoubleAnimation(HoverScale, 1.0, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        var sy = new DoubleAnimation(HoverScale, 1.0, TimeSpan.FromMilliseconds(DurationMs))
        { EasingFunction = new QuinticEase() };
        Storyboard.SetTarget(sx, btn);
        Storyboard.SetTargetProperty(sx, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleX)"));
        Storyboard.SetTarget(sy, btn);
        Storyboard.SetTargetProperty(sy, new PropertyPath("(UIElement.RenderTransform).(ScaleTransform.ScaleY)"));
        sb.Children.Add(sx);
        sb.Children.Add(sy);
        sb.Begin();
    }

    private static void EnsureScale(Button btn)
    {
        if (btn.RenderTransform is ScaleTransform) return;
        btn.RenderTransform = new ScaleTransform(1.0, 1.0);
        btn.RenderTransformOrigin = new Point(0.5, 0.5);
    }
}
