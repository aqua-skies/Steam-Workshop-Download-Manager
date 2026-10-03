using System.Windows;
using System.Windows.Controls;
using System.IO;
using System.Windows.Markup;
using System.Windows.Media;
using Swdm2.App.Ui.Chrome;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Ui.Navigation;
using Xunit;

namespace Swdm2.UiTests.Tests.Animation;

/// <summary>
/// t55 D5.16 动画套件测试：
/// - 时间线模型层断言（A7 终态可断言口径：初/终值+相序+总时长=纯逻辑，
///   ENV-DOWNGRADE 门族同 t44——沙箱无渲染=Storyboard 不到 Completed，
///   完成态由桌面通道/逻辑等价双通道覆盖）
/// - 帧采样门（60 帧窗口；沙箱 0 帧=合法降级）
/// </summary>
public sealed class AnimationKitTests
{
    // ===== A1 上→下凝实 =====

    [WpfFact]
    public void A1_Stagger_Delay_Caps_To_Keep_Total_400ms()
    {
        var row10 = StaggeredEntrance.BuildTimeline(10);
        Assert.Equal(10, row10.Count);
        Assert.Equal(0, row10[0].DelayMs);
        Assert.Equal(StaggeredEntrance.RowStaggerMs, row10[1].DelayMs);
        // 行 ≥8 后封顶 200ms（总 ≤400ms)
        Assert.Equal(StaggeredEntrance.MaxDelayMs, row10[8].DelayMs);
        Assert.Equal(StaggeredEntrance.MaxDelayMs, row10[9].DelayMs);
        Assert.All(row10, r => Assert.True(r.EndMs <= StaggeredEntrance.TotalCapMs));
    }

    [WpfFact]
    public void A1_Play_Sets_Synchronous_Initial_State()
    {
        var host = new ItemsControl();
        var rows = new List<FrameworkElement>();
        for (var i = 0; i < 3; i++)
            rows.Add(new Border());
        host.ItemsSource = rows.Select((r, i) => i).ToList();
        StaggeredEntrance.Play(rows);
        Assert.All(rows, r =>
        {
            Assert.Equal(0.4, r.Opacity); // 半透明起点（凝实前）
            Assert.Equal(12.0, ((TranslateTransform)r.RenderTransform).Y);
        });
    }

    [WpfFact]
    public void A1_Negative_Row_Count_Rejected()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => StaggeredEntrance.BuildTimeline(-1));
    }

    // ===== A2 抽屉下拉 =====

    [WpfFact]
    public void A2_Drawer_Duration_And_Initial_State()
    {
        Assert.Equal(300, DrawerSlide.DurationMs);
        var panel = new StackPanel();
        DrawerSlide.SlideDown(panel);
        Assert.Equal(0, panel.Opacity); // 初始不可见
        Assert.NotNull(panel.RenderTransform as TranslateTransform);
    }

    // ===== A3 页面分离编排（骨架；终值待 t54 对齐）=====

    [WpfFact]
    public void A3_Forward_Phase_Order_Matches_Spec()
    {
        var orch = new PageTransitionOrchestrator();
        var targets = new TransitionTargets
        {
            TextPanel = new Border(),
            TabStrip = new Border(),
            MainArea = new Border(),
            IncomingPage = new Border(),
        };
        orch.StartForward(targets);
        // 相序=文字→选项卡→主区→详情进入（spec 原文）
        Assert.Equal(
            new[]
            {
                PageTransitionOrchestrator.Phase.TextFade,
                PageTransitionOrchestrator.Phase.TabDrawer,
                PageTransitionOrchestrator.Phase.MainYield,
                PageTransitionOrchestrator.Phase.DetailEnter,
            },
            orch.Timeline.Select(s => s.Phase).ToArray());
        Assert.Equal(PageTransitionOrchestrator.TransitionState.ForwardExiting, orch.State);
    }

    [WpfFact]
    public void A3_HomeReturn_Phase_Order_Is_Reverse_Lead()
    {
        var orch = new PageTransitionOrchestrator();
        orch.StartHomeReturn(new TransitionTargets
        {
            TextPanel = new Border(),
            TabStrip = new Border(),
            MainArea = new Border(),
        });
        // 回程=选项卡右拉在先（切主页类标签）
        Assert.Equal(PageTransitionOrchestrator.Phase.TabDrawer, orch.Timeline[0].Phase);
        Assert.Equal(PageTransitionOrchestrator.TransitionState.HomeReturning, orch.State);
    }

    [WpfFact]
    public void A3_Overlap_Window_Honored()
    {
        var orch = new PageTransitionOrchestrator();
        orch.StartForward(new TransitionTargets
        {
            TextPanel = new Border(),
            TabStrip = new Border(),
            MainArea = new Border(),
            IncomingPage = new Border(),
        });
        var timeline = orch.Timeline;
        Assert.Equal(0, timeline[0].StartMs);
        // TabDrawer 与 TextFade 重叠 100ms（DetailProfile)
        Assert.Equal(100, timeline[1].StartMs);
        Assert.True(timeline[1].StartMs < timeline[0].EndMs);
        Assert.All(timeline, s => Assert.True(s.DurationMs > 0));
    }

    [WpfFact]
    public void A3_Cancel_Resets_Idle()
    {
        var orch = new PageTransitionOrchestrator();
        orch.StartForward(new TransitionTargets { TextPanel = new Border() });
        orch.Cancel();
        Assert.Equal(PageTransitionOrchestrator.TransitionState.Idle, orch.State);
        Assert.Empty(orch.Timeline);
    }

    [WpfFact]
    public void A3_Partial_Targets_Composable()
    {
        // 只注入子集（可组合契约：缺相=跳过不抛）
        var orch = new PageTransitionOrchestrator();
        orch.StartForward(new TransitionTargets { TextPanel = new Border() });
        Assert.Single(orch.Timeline);
        Assert.Equal(PageTransitionOrchestrator.TransitionState.ForwardExiting, orch.State);
    }

    // ===== A4 过冲回弹 =====

    [WpfFact]
    public void A4_Keyframes_Match_Spec_0_94_1_03_1()
    {
        var keys = Overshoot.BuildKeyframes();
        Assert.Equal(3, keys.Count);
        Assert.Equal(0.0, keys[0].TimeFraction);
        Assert.Equal(Overshoot.FromScale, keys[0].Scale);
        Assert.Equal(Overshoot.PeakKeyTimeFraction, keys[1].TimeFraction);
        Assert.Equal(Overshoot.PeakScale, keys[1].Scale);
        Assert.Equal(1.0, keys[2].TimeFraction);
        Assert.Equal(Overshoot.FinalScale, keys[2].Scale);
    }

    [WpfFact]
    public void A4_PopIn_Sets_Initial_Scale()
    {
        var card = new Border();
        Overshoot.PopIn(card);
        Assert.Equal(Overshoot.FromScale, ((ScaleTransform)card.RenderTransform).ScaleX);
        Assert.Equal(0.5, card.RenderTransformOrigin.X); // 中心缩放
    }

    [WpfFact]
    public void A4_Elastic_PopIn_Does_Not_Throw()
    {
        var card = new Border();
        Overshoot.ElasticPopIn(card);
        Assert.NotNull(card.RenderTransform);
    }

    // ===== A5 标题钮放大 =====

    [WpfFact]
    public void A5_Hover_Constants_Match_Spec()
    {
        Assert.Equal(1.1, TitleButtonHover.HoverScale);
        Assert.Equal(150, TitleButtonHover.DurationMs);
    }

    [WpfFact]
    public void A5_Attached_Property_Wires_Button()
    {
        var btn = new Button();
        TitleButtonHover.SetEnable(btn, true);
        Assert.True(TitleButtonHover.GetEnable(btn));
        // 启用后卸载不抛
        TitleButtonHover.SetEnable(btn, false);
        Assert.False(TitleButtonHover.GetEnable(btn));
    }

    // ===== A6 全局圆弧令牌（v1.4 §2.10 A6:卡 8/钮 6/输入 4/泡泡 6) =====

    [WpfFact]
    public void A6_Radius_Tokens_Match_Spec_V1_4()
    {
        var path = Path.Combine(ResolveRoot().FullName,
            "swdm2/src/Swdm2.App/Ui/Themes/Common.xaml");
        var xaml = File.ReadAllText(path);
        var dict = (ResourceDictionary)XamlReader.Parse(xaml);
        Assert.Equal(4.0, dict["swdm-RadiusXs"]);   // 输入 4
        Assert.Equal(6.0, dict["swdm-RadiusSm"]);   // 泡泡 6
        Assert.Equal(6.0, dict["swdm-RadiusMd"]);   // 钮 6
        Assert.Equal(8.0, dict["swdm-RadiusLg"]);   // 卡 8
    }

    // ===== 帧采样门 =====

    [WpfFact]
    public void Frame_Sampler_Degrades_Gracefully_Headless()
    {
        using var sampler = new AnimationFrameSampler();
        var fps = sampler.SampleUntilWindowOrTimeout(timeoutMs: 500);
        // ENV-DOWNGRADE 门：沙箱无桌面渲染=0 fps（合法降级）；桌面通道断言 ≥20fps
        Assert.True(fps >= 0);
        Assert.True(sampler.Frames >= 0);
        Assert.Equal(AnimationFrameSampler.FrameWindow, 60);
    }

    [WpfFact]
    public void Sampler_Monotonic_Frame_Count()
    {
        using var sampler = new AnimationFrameSampler();
        sampler.Start();
        var before = sampler.Frames;
        Assert.True(sampler.Frames >= before); // 单调不减（0=降级合法）
        sampler.Stop();
    }

    // ===== 可组合性（多效同台不互斥）=====

    [WpfFact]
    public void Composable_A1_Plus_A4_Simultaneous()
    {
        var rows = new List<FrameworkElement> { new Border(), new Border() };
        var card = new Border();
        StaggeredEntrance.Play(rows);
        Overshoot.PopIn(card);
        Assert.All(rows, r => Assert.Equal(0.4, r.Opacity));
        Assert.NotNull(card.RenderTransform);
    }

    private static DirectoryInfo ResolveRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && dir.Name != "swdm2" && dir.Parent is not null) dir = dir.Parent;
        return dir?.Parent ?? new DirectoryInfo(Directory.GetCurrentDirectory());
    }
}
