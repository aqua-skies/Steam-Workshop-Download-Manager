using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// 平滑滚动查看器（PCL2 MyScrollViewer 等价，t2 §3/§5）。
/// 手指/滚轮滚动到目标偏移用 300ms QuinticEase 动画过渡（⚠️曲线近似，t2 §6)。
/// 滚动条样式（8px/圆角 3/margin 2/1% 底色轨道）在 Generic 样式层（t2 §2.7)。
/// 数值 ⚠️[参数待重标定]。
/// </summary>
public class SmoothScrollViewer : ScrollViewer
{
    private double _targetVerticalOffset;
    private bool _animating;

    public SmoothScrollViewer()
    {
        PreviewMouseWheel += OnPreviewMouseWheel;
    }

    /// <summary>平滑滚动到指定垂直偏移（300ms QuinticEase EaseOut)。</summary>
    public void ScrollToVerticalOffsetSmooth(double offset)
    {
        _targetVerticalOffset = Clamp(offset, 0, ScrollableHeight);
        if (_animating) return;
        _animating = true;

        var anim = new DoubleAnimation(VerticalOffset, _targetVerticalOffset,
            ((Duration)FindResource("swdm-MotionSmoothScroll")).TimeSpan)
        {
            EasingFunction = (IEasingFunction)FindResource("swdm-EaseOutExtraStrong"),
        };
        var sb = new Storyboard();
        sb.Children.Add(anim);
        Storyboard.SetTarget(anim, this);
        Storyboard.SetTargetProperty(anim, new PropertyPath(ScrollViewerBehavior.VerticalOffsetProperty));
        sb.Completed += (_, _) => _animating = false;
        sb.Begin();
    }

    private void OnPreviewMouseWheel(object sender, MouseWheelEventArgs e)
    {
        // 滚轮一格动画一次（而非原生立即跳变）
        var delta = e.Delta > 0 ? -ViewportHeight * 0.25 : ViewportHeight * 0.25;
        ScrollToVerticalOffsetSmooth(VerticalOffset + delta);
        e.Handled = true;
    }

    private static double Clamp(double v, double min, double max)
        => v < min ? min : (v > max ? max : v);
}

/// <summary>ScrollViewer 动画偏移附加属性（Storyboard 不能直接动画 ScrollViewer.VerticalOffset——DP 注册到行为附加属性）。</summary>
public static class ScrollViewerBehavior
{
    public static readonly DependencyProperty VerticalOffsetProperty =
        DependencyProperty.RegisterAttached("VerticalOffset", typeof(double), typeof(ScrollViewerBehavior),
            new PropertyMetadata(0d, OnVerticalOffsetChanged));

    public static double GetVerticalOffset(DependencyObject obj)
        => (double)obj.GetValue(VerticalOffsetProperty);

    public static void SetVerticalOffset(DependencyObject obj, double value)
        => obj.SetValue(VerticalOffsetProperty, value);

    private static void OnVerticalOffsetChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is ScrollViewer viewer)
            viewer.ScrollToVerticalOffset((double)e.NewValue);
    }
}
