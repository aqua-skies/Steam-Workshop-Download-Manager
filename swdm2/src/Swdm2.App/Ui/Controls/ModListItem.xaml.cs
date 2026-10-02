using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// ModListItem 列表行（PCL2 MyListItem 等价，t2 §2.3)。
/// 行高 42;悬停浮层 RectBack(CornerRadius 6,scale 0.75→1，背景+边描边并行，
/// 时长=基础×1.6);整行按下 scale 0.98;选中=主标题前景 accent400(200ms)。
/// 勾选竖条双段生长：40%/200ms(QuadraticEase≈OutFluent(Weak)) + 60%/300ms
/// (BackEase Amplitude≈0.5≈OutBack(Weak))，⚠️曲线近似（t2 §6)。
/// 数值全部 PCL2 实测起点值，⚠️[参数待重标定]。
/// </summary>
public partial class ModListItem : UserControl
{
    public static readonly DependencyProperty TitleProperty =
        DependencyProperty.Register(nameof(Title), typeof(string), typeof(ModListItem),
            new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty SubtitleProperty =
        DependencyProperty.Register(nameof(Subtitle), typeof(string), typeof(ModListItem),
            new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty IsSelectedProperty =
        DependencyProperty.Register(nameof(IsSelected), typeof(bool), typeof(ModListItem),
            new PropertyMetadata(false, OnIsSelectedChanged));

    private bool _mouseDown;

    public ModListItem()
    {
        InitializeComponent();
    }

    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    public string Subtitle
    {
        get => (string)GetValue(SubtitleProperty);
        set => SetValue(SubtitleProperty, value);
    }

    public bool IsSelected
    {
        get => (bool)GetValue(IsSelectedProperty);
        set => SetValue(IsSelectedProperty, value);
    }

    protected override void OnMouseEnter(MouseEventArgs e)
    {
        base.OnMouseEnter(e);
        // 悬停浮层淡入+scale 0.75→1（时长=MotionColor ×1.6=悬停基础时长放大）
        var duration = MotionFromResource("swdm-MotionFast");
        var durationX16 = TimeSpan.FromTicks(duration.Ticks * 16 / 10);
        AniHelper.StartDouble(this, OpacityProperty, 1, TimeSpan.Zero, "hover-fade");
        AniHelper.StartDouble(RectBack, OpacityProperty, 1, duration, "rect-fade");
        AniHelper.StartDouble(RectBackScale, ScaleTransform.ScaleXProperty,
            1, durationX16, "rect-scale-x");
        AniHelper.StartDouble(RectBackScale, ScaleTransform.ScaleYProperty,
            1, durationX16, "rect-scale-y");
        // 按钮组悬停才淡入（低密度默认，t2 §2.3）
        AniHelper.StartDouble(ButtonGroup, OpacityProperty, 1, duration, "btn-fade");
    }

    protected override void OnMouseLeave(MouseEventArgs e)
    {
        base.OnMouseLeave(e);
        var duration = MotionFromResource("swdm-MotionFast");
        AniHelper.StartDouble(RectBack, OpacityProperty, 0, duration, "rect-fade");
        AniHelper.StartDouble(RectBackScale, ScaleTransform.ScaleXProperty,
            0.75, MotionFromResource("swdm-MotionBase"), "rect-scale-x");
        AniHelper.StartDouble(RectBackScale, ScaleTransform.ScaleYProperty,
            0.75, MotionFromResource("swdm-MotionBase"), "rect-scale-y");
        AniHelper.StartDouble(ButtonGroup, OpacityProperty, 0, duration, "btn-fade");
        if (_mouseDown)
            RestorePressedScale();
    }

    protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e)
    {
        base.OnMouseLeftButtonDown(e);
        _mouseDown = true;
        // 整行按下 scale 0.98
        var scale = new ScaleTransform(1, 1);
        RootGrid.RenderTransform = scale;
        RootGrid.RenderTransformOrigin = new Point(0.5, 0.5);
        AniHelper.StartDouble(scale, ScaleTransform.ScaleXProperty,
            0.98, MotionFromResource("swdm-MotionColor"), "press-x");
        AniHelper.StartDouble(scale, ScaleTransform.ScaleYProperty,
            0.98, MotionFromResource("swdm-MotionColor"), "press-y");
    }

    protected override void OnMouseLeftButtonUp(MouseButtonEventArgs e)
    {
        base.OnMouseLeftButtonUp(e);
        _mouseDown = false;
        RestorePressedScale();
    }

    /// <summary>勾选竖条双段生长（外部选中流调用）。</summary>
    public void PlayCheckGrow()
    {
        var weakOut = new QuadraticEase { EasingMode = EasingMode.EaseOut };   // ≈ OutFluent(Weak)
        var backOut = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.5 }; // ≈ OutBack(Weak)
        // 段 1:40% / 200ms;段 2(Height 由 0→5 宽度等效用 Opacity+Width 两段）
        AniHelper.StartDouble(CheckBar, OpacityProperty,
            1, TimeSpan.FromMilliseconds(30), "check-fade");
        AniHelper.StartDouble(CheckBar, WidthProperty,
            2, TimeSpan.FromMilliseconds(200), weakOut, "check-grow-1");   // 40%
        // 段 2:60% / 300ms OutBack——顺接段 1（Duration 计数内追加第二Storyboard)
        var sb2 = new Storyboard();
        var anim = new DoubleAnimation(2, 5, TimeSpan.FromMilliseconds(300))
        {
            EasingFunction = backOut,
            BeginTime = TimeSpan.FromMilliseconds(200),
        };
        Storyboard.SetTarget(anim, CheckBar);
        Storyboard.SetTargetProperty(anim, new PropertyPath(WidthProperty));
        sb2.Children.Add(anim);
        sb2.Begin();
    }

    /// <summary>收起：120ms + 70ms 淡出（t2 §2.3)。</summary>
    public void PlayCheckCollapse()
    {
        AniHelper.StartDouble(CheckBar, OpacityProperty,
            0, TimeSpan.FromMilliseconds(70), "check-fade");
        AniHelper.StartDouble(CheckBar, WidthProperty,
            0, TimeSpan.FromMilliseconds(120), "check-collapse");
    }

    private void RestorePressedScale()
    {
        if (RootGrid.RenderTransform is ScaleTransform scale)
        {
            AniHelper.StartDouble(scale, ScaleTransform.ScaleXProperty,
                1, MotionFromResource("swdm-MotionColor"), "press-x");
            AniHelper.StartDouble(scale, ScaleTransform.ScaleYProperty,
                1, MotionFromResource("swdm-MotionColor"), "press-y");
        }
    }

    private static void OnIsSelectedChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is ModListItem item && (bool)e.NewValue)
        {
            // 选中前景色 = accent400(200ms)
            AniHelper.StartColor(item.TitleText, TextBlock.ForegroundProperty,
                (Color)item.FindResource("swdm-TextPrimaryColor"),
                (Color)item.FindResource("swdm-Accent400Color"),
                item.MotionFromResource("swdm-MotionBase"),
                "swdm-Accent400Brush", "title-color");
        }
    }

    private TimeSpan MotionFromResource(string key)
        => ((Duration)FindResource(key)).TimeSpan;
}
