using System.Windows;
using System.Windows.Media;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// 惯性滚轮附加行为（D5.5,A2 路线 A 增量）：
/// **不包裹 ScrollViewer**(A2 不变量④：虚拟化列表永远不被 ScrollViewer 包）——
/// 挂到 ListBox，运行时定位其**内部** ScrollViewer,PreviewMouseWheel 拦截→
/// 300ms QuinticEase 平滑过渡（t2 §6 MotionSmoothScroll/EaseOutExtraStrong,
/// 资源缺失兜底常量=同值，不崩 XamlReader driver 树）。
/// 数值 ⚠️[参数待重标定]（视觉规格 t2 §6 起点值）。
/// </summary>
public static class SmoothScrollAttach
{
    public static readonly DependencyProperty IsEnabledProperty =
        DependencyProperty.RegisterAttached("IsEnabled", typeof(bool), typeof(SmoothScrollAttach),
            new PropertyMetadata(false, OnIsEnabledChanged));

    public static bool GetIsEnabled(DependencyObject obj) => (bool)obj.GetValue(IsEnabledProperty);
    public static void SetIsEnabled(DependencyObject obj, bool value) => obj.SetValue(IsEnabledProperty, value);

    private static void OnIsEnabledChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not ListBox listBox) return;
        var enabled = (bool)e.NewValue;
        if (enabled) listBox.Loaded += HookInternalScroller;
        else listBox.Loaded -= HookInternalScroller;
    }

    private static void HookInternalScroller(object? sender, RoutedEventArgs e)
    {
        if (sender is not ListBox listBox) return;
        listBox.Loaded -= HookInternalScroller;
        var scroller = FindInternalScrollViewer(listBox);
        if (scroller is null || scroller.IsLoaded) return; // 已挂（容器复用）
        if (scroller.GetValue(HookedProperty) is true) return;
        scroller.SetValue(HookedProperty, true);
        scroller.PreviewMouseWheel += OnSmoothWheel;
    }

    private static readonly DependencyProperty HookedProperty =
        DependencyProperty.RegisterAttached("Hooked", typeof(bool), typeof(SmoothScrollAttach),
            new PropertyMetadata(false));

    private static void OnSmoothWheel(object sender, MouseWheelEventArgs e)
    {
        if (sender is not ScrollViewer scroller) return;
        e.Handled = true;
        var delta = e.Delta;
        var target = Math.Clamp(
            scroller.VerticalOffset - delta * WheelStep, 0, scroller.ScrollableHeight);
        SmoothTo(scroller, target);
    }

    /// <summary>滚轮步长（像素；⚠️[参数待重标定]:视觉规格 t2 §6 起点值=120 单位约一屏 1/3)。</summary>
    private const double WheelStep = 0.4;

    /// <summary>平滑滚动时长（ms，资源缺失兜底常量）。</summary>
    private const double FallbackDurationMs = 300;

    /// <summary>对外可测：对内部 scroller 执行平滑滚动（帧计数测试入口）。</summary>
    public static void SmoothTo(ScrollViewer scroller, double targetVerticalOffset)
    {
        targetVerticalOffset = Math.Clamp(targetVerticalOffset, 0, scroller.ScrollableHeight);
        var durationMs = TryGetDuration(scroller);
        var anim = new DoubleAnimation(scroller.VerticalOffset, targetVerticalOffset,
            TimeSpan.FromMilliseconds(durationMs))
        {
            EasingFunction = new QuinticEase { EasingMode = EasingMode.EaseOut },
        };
        var sb = new Storyboard();
        sb.Children.Add(anim);
        Storyboard.SetTarget(anim, scroller);
        Storyboard.SetTargetProperty(anim, new PropertyPath(ScrollViewerBehavior.VerticalOffsetProperty));
        sb.Begin();
    }

    private static double TryGetDuration(FrameworkElement fe)
    {
        var found = fe.TryFindResource("swdm-MotionSmoothScroll");
        return found is Duration d ? d.TimeSpan.TotalMilliseconds : FallbackDurationMs;
    }

    /// <summary>定位 ListBox 内部 ScrollViewer（VSP 的滚动提供者=A2 不变量④)。</summary>
    public static ScrollViewer? FindInternalScrollViewer(DependencyObject parent)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is ScrollViewer sv) return sv;
            var nested = FindInternalScrollViewer(child);
            if (nested is not null) return nested;
        }
        return null;
    }
}
