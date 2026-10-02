using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// SwdmCard（PCL2 MyCard 等价，t2 §2.1）。
/// 折叠态固定高 40px;ContentPresenter Margin 0,40,0,12 = 头部偏移。
/// 悬停 90ms 四路并行：标题/箭头颜色 + 阴影色 + 阴影 α(0.07→0.4≈5.7×，皮肤感第一签名；
/// 阴影 BlurRadius 6→14 与 ShadowDepth 2→5 随 α 抬升，t2 §2.1 路线 A 令牌）。
/// 交互：左键点击切换 IsExpanded（150ms 高度+250ms 箭头旋转）。
/// 退出动画（200ms scale −0.08 + opacity −1）由宿主页面在移除前调用 <see cref="PlayExit"/>。
/// 全部数值为 PCL2 实测起点值，⚠️[参数待重标定]（D5.x 观感标定）。
/// </summary>
public partial class SwdmCard : UserControl
{
    public static readonly DependencyProperty TitleProperty =
        DependencyProperty.Register(nameof(Title), typeof(string), typeof(SwdmCard),
            new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty IsExpandedProperty =
        DependencyProperty.Register(nameof(IsExpanded), typeof(bool), typeof(SwdmCard),
            new PropertyMetadata(true, OnIsExpandedChanged));

    private double _expandedHeight = double.NaN;

    public SwdmCard()
    {
        InitializeComponent();
    }

    /// <summary>卡片标题（13px Bold）。</summary>
    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    /// <summary>展开/折叠状态（点击切换；150ms 高度+250ms 箭头动画）。</summary>
    public bool IsExpanded
    {
        get => (bool)GetValue(IsExpandedProperty);
        set => SetValue(IsExpandedProperty, value);
    }

    /// <summary>宿主页面移除前的退出动画（200ms scale −0.08 + opacity −1）。</summary>
    public void PlayExit()
    {
        var scale = new ScaleTransform(1, 1);
        RootGrid.RenderTransform = scale;
        RootGrid.RenderTransformOrigin = new Point(0.5, 0.5);
        AniHelper.StartDouble(scale, ScaleTransform.ScaleXProperty,
            0.92, MotionBase, "exit-scale-x");
        AniHelper.StartDouble(scale, ScaleTransform.ScaleYProperty,
            0.92, MotionBase, "exit-scale-y");
        AniHelper.StartDouble(this, OpacityProperty,
            0, MotionBase, "exit-opacity");
    }

    protected override void OnMouseEnter(MouseEventArgs e)
    {
        base.OnMouseEnter(e);
        // 90ms 四路并行：标题→链接色、箭头→链接色、阴影 α 0.07→0.4、blur 6→14
        AniHelper.StartColor(TitleText, TextBlock.ForegroundProperty,
            (Color)FindResource("swdm-TextPrimaryColor"),
            (Color)FindResource("swdm-LinkDefaultColor"),
            MotionColor, "swdm-LinkDefaultBrush", "title-color");
        AniHelper.StartColor(ArrowPath, System.Windows.Shapes.Path.FillProperty,
            (Color)FindResource("swdm-TextSecondaryColor"),
            (Color)FindResource("swdm-LinkDefaultColor"),
            MotionColor, "swdm-LinkDefaultBrush", "arrow-color");
        AniHelper.StartDouble(ShadowEffect, DropShadowEffect.OpacityProperty,
            0.4, MotionColor, "shadow-alpha");
        AniHelper.StartDouble(ShadowEffect, DropShadowEffect.BlurRadiusProperty,
            14, MotionColor, "shadow-blur");
    }

    protected override void OnMouseLeave(MouseEventArgs e)
    {
        base.OnMouseLeave(e);
        AniHelper.StartColor(TitleText, TextBlock.ForegroundProperty,
            (Color)FindResource("swdm-LinkDefaultColor"),
            (Color)FindResource("swdm-TextPrimaryColor"),
            MotionColor, "swdm-TextPrimaryBrush", "title-color");
        AniHelper.StartColor(ArrowPath, System.Windows.Shapes.Path.FillProperty,
            (Color)FindResource("swdm-LinkDefaultColor"),
            (Color)FindResource("swdm-TextSecondaryColor"),
            MotionColor, "swdm-TextSecondaryBrush", "arrow-color");
        AniHelper.StartDouble(ShadowEffect, DropShadowEffect.OpacityProperty,
            0.07, MotionColor, "shadow-alpha");
        AniHelper.StartDouble(ShadowEffect, DropShadowEffect.BlurRadiusProperty,
            6, MotionColor, "shadow-blur");
    }

    protected override void OnPreviewMouseLeftButtonDown(MouseButtonEventArgs e)
    {
        base.OnPreviewMouseLeftButtonDown(e);
        IsExpanded = !IsExpanded;
    }

    private static void OnIsExpandedChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is SwdmCard card)
            card.OnExpandedChanged((bool)e.NewValue);
    }

    private void OnExpandedChanged(bool expanded)
    {
        if (double.IsNaN(_expandedHeight) && ActualHeight > 40)
            _expandedHeight = ActualHeight;

        // 折叠高 40（t2 §2.1 表 / Common.xaml swdm-CardCollapsedHeight）
        var targetHeight = expanded
            ? (double.IsNaN(_expandedHeight) ? ActualHeight : _expandedHeight)
            : 40d;

        if (targetHeight > 0)
        {
            AniHelper.StartDouble(this, HeightProperty,
                targetHeight, MotionFast, EaseExtraStrong, "height");
        }
        // 箭头旋转 180°(250ms QuinticEase)
        AniHelper.StartDouble(ArrowRotate, RotateTransform.AngleProperty,
            expanded ? 0 : 180, MotionSlow, EaseExtraStrong, "arrow-angle");
    }

    private TimeSpan MotionColor => ((Duration)FindResource("swdm-MotionColor")).TimeSpan;
    private TimeSpan MotionFast => ((Duration)FindResource("swdm-MotionFast")).TimeSpan;
    private TimeSpan MotionSlow => ((Duration)FindResource("swdm-MotionSlow")).TimeSpan;
    private TimeSpan MotionBase => ((Duration)FindResource("swdm-MotionBase")).TimeSpan;
    private IEasingFunction EaseExtraStrong => (IEasingFunction)FindResource("swdm-EaseOutExtraStrong");
}
