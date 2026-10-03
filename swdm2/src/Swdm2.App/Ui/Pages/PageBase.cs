using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Swdm2.App.Ui.Controls;

namespace Swdm2.App.Ui.Pages;

/// <summary>
/// 页面基类（t2 §2.5)：不用 Frame/Page —— PageHost(ContentControl）容器替换 + 本基类。
/// 状态机（PCL2 9 态的 2.0 收敛）：<see cref="PageState"/> Empty/Loading/Content/Exiting。
/// 切页时序由 PageNavigationService 驱动：StopPreviousAnimations → RunExit → +110ms 替换
/// Content（新页 Opacity=0)→ +30ms Opacity=1 + RunEnter。
/// 进入动画（PCL2 交错+双段位移）：逐元素 opacity 0→1/100ms OutFluent(Weak)+双段位移
/// +5px/250ms 与 +11px/350ms OutBack 并行，stagger 25ms;退出 opacity −1 + TranslateY −6px/70ms,
/// stagger 15ms。数值全部 PCL2 实测起点值，⚠️[参数待重标定]。
/// 动画推进依赖渲染时钟，headless 测试只断言状态机/不抛。
/// </summary>
public abstract class PageBase : UserControl
{
    public static readonly DependencyProperty StateProperty =
        DependencyProperty.Register(nameof(State), typeof(PageState), typeof(PageBase),
            new PropertyMetadata(PageState.Empty));

    /// <summary>页面状态机（Empty/Loading/Content/Exiting;加载回来不打断退出动画=等退出的等待槽在导航服务）。</summary>
    public PageState State
    {
        get => (PageState)GetValue(StateProperty);
        protected set => SetValue(StateProperty, value);
    }

    /// <summary>页面进入动画（交错 stagger 25ms;由导航服务在 +30ms 抬升窗口后调用）。</summary>
    public virtual void RunEnter()
    {
        State = PageState.Content;
        var stagger = ((Duration)FindResource("swdm-MotionStaggerIn")).TimeSpan;
        var fadeDur = ((Duration)FindResource("swdm-MotionPageEnterFade")).TimeSpan;
        var weakEase = (IEasingFunction)FindResource("swdm-EaseOutFluentWeak");
        var backEase = (IEasingFunction)FindResource("swdm-EaseOutBack");
        var shift1 = ((Duration)FindResource("swdm-MotionPageShift1")).TimeSpan;
        var shift2 = ((Duration)FindResource("swdm-MotionPageShift2")).TimeSpan;

        var index = 0;
        foreach (var child in EnumerateAnimatableChildren())
        {
            var delay = TimeSpan.FromTicks(stagger.Ticks * index++);
            // fade 0→1 / 100ms OutFluent(Weak)
            AniHelper.StartDouble(child, OpacityProperty, 1, fadeDur, weakEase, "page-fade");
            child.Opacity = 0;
            // 双段位移并行：+5px/250ms 与 +11px/350ms OutBack（TranslateTransform 挂在 RenderTransform)
            var transform = new TranslateTransform();
            child.RenderTransform = transform;
            child.RenderTransformOrigin = new Point(0.5, 0.5);
            AniHelper.StartDouble(transform, TranslateTransform.YProperty,
                5, shift1, backEase, "page-shift1");
            var sb2 = new Storyboard();
            var anim = new DoubleAnimation(5, 16, shift2)
            {
                EasingFunction = backEase,
                BeginTime = delay,
            };
            Storyboard.SetTarget(anim, transform);
            Storyboard.SetTargetProperty(anim, new PropertyPath(TranslateTransform.YProperty));
            sb2.Children.Add(anim);
            sb2.Begin();
        }
    }

    /// <summary>页面退出动画（opacity −1 + TranslateY −6px/70ms,stagger 15ms)。</summary>
    public virtual void RunExit()
    {
        State = PageState.Exiting;
        var stagger = ((Duration)FindResource("swdm-MotionStaggerOut")).TimeSpan;
        var exitDur = ((Duration)FindResource("swdm-MotionPageExitElement")).TimeSpan;
        var weakEase = (IEasingFunction)FindResource("swdm-EaseOutFluentWeak");

        var index = 0;
        foreach (var child in EnumerateAnimatableChildren())
        {
            var delay = TimeSpan.FromTicks(stagger.Ticks * index++);
            var sb = new Storyboard();
            var fade = new DoubleAnimation(0, exitDur) { BeginTime = delay, EasingFunction = weakEase };
            Storyboard.SetTarget(fade, child);
            Storyboard.SetTargetProperty(fade, new PropertyPath(OpacityProperty));
            sb.Children.Add(fade);
            sb.Begin();
        }
    }

    /// <summary>停止本页全部命名轨道动画（切页前置，防重入；PCL2 AniStop 语义）。</summary>
    public virtual void StopAnimations()
        => AniHelper.StopAll(this);

    private protected virtual System.Collections.Generic.IEnumerable<FrameworkElement> EnumerateAnimatableChildren()
    {
        var count = VisualChildrenCount;
        for (var i = 0; i < count; i++)
        {
            if (GetVisualChild(i) is FrameworkElement fe)
                yield return fe;
        }
    }
}

/// <summary>页面状态机（t2 §2.5;PCL2 9 态收敛：内容/加载双通道，切走时加载回来不打断退出动画）。</summary>
public enum PageState
{
    Empty,
    Loading,
    Content,
    Exiting,
}
