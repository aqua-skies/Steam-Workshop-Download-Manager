using System.Windows;
using System.Windows.Controls;
using Swdm2.App.Navigation;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Ui.Navigation;
using Swdm2.App.Ui.Pages;
using Xunit;

namespace Swdm2.UiTests.Tests.Transition;

/// <summary>
/// t65(D5.20d) DetailEnter 相接线+SwapDirect 逻辑层回归：
/// 用户 instruction #3「切页动态 UI」收口=贴图点击→前进四相→
/// IncomingPage=真实目标页→DetailEnter 相跟上（不再 null 跳过）。
/// 沙箱真点/截图不路由（同族）=逻辑层钉 + 桌面复跑条款。
/// </summary>
public sealed class TransitionWiringTests
{
    private sealed class DummyPage : PageBase
    {
        public DummyPage() { Content = new Grid(); }
    }

    private static PageNavigationService NewNav(out ContentControl host)
    {
        host = new ContentControl();
        // PageBase 读宿主 swdm-Motion* key（真实 MainWindow 的 PageHost 在 xaml 声明）
        host.Resources.MergedDictionaries.Add(new ResourceDictionary
        {
            Source = new Uri("pack://application:,,,/Swdm2.App;component/Ui/Themes/Common.xaml"),
        });
        var nav = new PageNavigationService();
        nav.Attach(host);
        nav.Initialize<DummyPage>();
        return nav;
    }

    /// <summary>SwapDirect=无动画挂树+入栈（详情进入编排路径）。</summary>
    [WpfFact]
    public void SwapDirect_Mounts_And_PushesStack()
    {
        var nav = NewNav(out var host);
        var page = new DummyPage();
        nav.SwapDirect(page);
        Assert.Same(page, host.Content);
        Assert.Equal(1, nav.BackStackDepth);
        Assert.True(page.Opacity == 1.0);
    }

    /// <summary>IncomingPage 注入=DetailEnter 相入时间线（接线=不再跳过）。</summary>
    [WpfFact]
    public void StartForward_With_IncomingPage_Includes_DetailEnter()
    {
        var textPanel = new Grid();
        var tabStrip = new Border();
        var mainArea = new Grid();
        var incoming = new DummyPage();

        var orchestrator = new PageTransitionOrchestrator();
        orchestrator.StartForward(new TransitionTargets
        {
            TextPanel = textPanel,
            TabStrip = tabStrip,
            MainArea = mainArea,
            IncomingPage = incoming,
        });

        Assert.Contains(orchestrator.Timeline,
            t => t.Phase == PageTransitionOrchestrator.Phase.DetailEnter);
        Assert.NotEqual(PageTransitionOrchestrator.TransitionState.Idle, orchestrator.State);
    }
}