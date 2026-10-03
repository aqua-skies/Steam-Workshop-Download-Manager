using System;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using Swdm2.App.Navigation;
using Swdm2.App.Ui.Pages;
using Swdm2.App.Views;
using Xunit;

namespace Swdm2.UiTests.Tests.ZZNavigation;

/// <summary>
/// D5.3 页面导航验收（t2 §2.5):返回栈语义+切换时序令牌（110→30ms)+stagger。
/// 沙箱逻辑层断言：
/// - 返回栈工厂快照语义（Navigate 推栈/GoBack 出栈/栈空 false);
/// - 状态机与类型层级（PageBase 基类、PageState 四态）。
/// 时序推进（DispatcherTimer tick）与动画帧采样（验收①③）
/// = ENV-DOWNGRADE 桌面复跑：driver 的 STA 线程不运行 Dispatcher 帧，
/// DispatcherTimer 不 tick（WpfFact 上下文同证），渲染时钟 headless 不可靠。
/// 桌面通道复跑时序与交错可见性（前后截图）。
/// </summary>
public sealed class PageNavigationTests
{
    public PageNavigationTests()
    {
        if (Application.Current is null)
            new Application();
        var merged = Application.Current!.Resources.MergedDictionaries;
        if (!merged.Any(d => d.Source is { } src
                              && src.OriginalString.Contains("Ui/Themes/Common.xaml")))
        {
            foreach (var path in new[] { "Common", "Accent", "Dark" })
            {
                merged.Add(new ResourceDictionary
                {
                    Source = new Uri($"pack://application:,,,/Swdm2.App;component/Ui/Themes/{path}.xaml", UriKind.Absolute)
                });
            }
        }
    }

    [WpfFact]
    public void Initialize_Places_First_Page_Without_Stack()
    {
        var host = new ContentControl();
        var nav = new PageNavigationService();
        nav.Attach(host);

        nav.Initialize<ModDetailPage>();
        Assert.Equal(0, nav.BackStackDepth);
        Assert.IsType<ModDetailPage>(nav.Current);
        Assert.Same(host.Content, nav.Current);
        Assert.Equal(1, nav.Current!.Opacity);  // 首页无时序：直接抬升
    }

    [WpfFact]
    public void Navigate_Enqueues_Stack_Snapshot_Factory()
    {
        var host = new ContentControl();
        var nav = new PageNavigationService();
        nav.Attach(host);
        nav.Initialize<ModDetailPage>();

        // 时序进行中的同步态：栈已推入工厂快照（旧页引用，非可变 _current 闭包）
        nav.Navigate<DownloadsPage>();
        Assert.Equal(1, nav.BackStackDepth);
        // driver STA 无 Dispatcher 帧：swapTimer 不 tick,host 仍持旧页
        // （桌面通道复跑验证 tick 时序；此处断言快照语义+状态）
        Assert.IsType<ModDetailPage>(host.Content);
    }

    [WpfFact]
    public void GoBack_Semantics_Empty_Stack_Returns_False()
    {
        var host = new ContentControl();
        var nav = new PageNavigationService();
        Assert.False(nav.GoBack()); // 未 Attach+空栈

        nav.Attach(host);
        nav.Initialize<ModDetailPage>();
        Assert.False(nav.GoBack()); // 栈空
    }

    [WpfFact]
    public void PageBase_State_Machine_Defaults()
    {
        var page = new ModDetailPage();
        Assert.Equal(PageState.Empty, page.State);
        // 状态机迁移：RunExit→Exiting;RunEnter→Content
        page.RunExit();
        Assert.Equal(PageState.Exiting, page.State);
        page.RunEnter();
        Assert.Equal(PageState.Content, page.State);
    }

    [WpfFact]
    public void Navigate_Before_Attach_Throws()
    {
        var nav = new PageNavigationService();
        Assert.Throws<InvalidOperationException>(() => nav.Navigate<DownloadsPage>());
    }

    [WpfFact]
    public void Page_Types_Are_PageBase()
    {
        Assert.IsAssignableFrom<PageBase>(new ModDetailPage());
        Assert.IsAssignableFrom<PageBase>(new DownloadsPage());
    }
}
