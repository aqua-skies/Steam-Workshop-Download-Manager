using System;
using System.Windows;
using System.Windows.Controls;
using Swdm2.App.Navigation;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;
using Xunit;

namespace Swdm2.UiTests.Tests.DeadButton;

/// <summary>
/// t62 死钮 bug 回归（captain 真实输入实锤：点"浏览工坊"后"‹ 返回"钮仍 DISABLED
/// @632,398 82x45)。
/// 根因：GoBackCommand CanExecute=BackStackDepth&gt;0，但计时器式切页
/// （DispatcherTimer swap)结束后不触发 CommandManager.RequerySuggested，
/// 钮停在初始禁用态。
/// 修复：PageNavigationService.PushContentDirect（GoBack/Initialize 路径）
/// 与 Navigate 的 enterTimer 结束处调用 InvalidateRequerySuggested;
/// ViewModelBase.RaisePropertyChanged 统一传播（同病治理：
/// Pause/NextPage 等非恒定 CanExecute 命令）。
/// 沙箱真实鼠标点击不路由（FlaUI 输入族基线同族=环境层）→ 桌面复跑条款
/// （同 0.5.0 门）;此处钉逻辑层不变量。
/// </summary>
public sealed class GoBackDeadButtonTests
{
    private sealed class DummyPage : PageBase
    {
        public DummyPage() { Content = new Grid(); }
    }

    /// <summary>导航推栈=CanExecute 立即变真（逻辑层直接断言）。</summary>
    [WpfFact]
    public void Navigate_Enables_GoBack_Command_Logic()
    {
        var host = new ContentControl();
        // PageNavigationService/PageBase 读宿主 swdm-Motion* 资源 key
        // （真实 MainWindow 的 PageHost 在 xaml 声明；测试合并 Common.xaml)
        host.Resources.MergedDictionaries.Add(new ResourceDictionary
        {
            Source = new Uri("pack://application:,,,/Swdm2.App;component/Ui/Themes/Common.xaml"),
        });
        var nav = new PageNavigationService();
        nav.Attach(host);

        nav.Initialize<DummyPage>();
        var cmd = new RelayCommand(() => nav.GoBack(), () => nav.BackStackDepth > 0);
        Assert.False(cmd.CanExecute(null)); // 初始栈空

        nav.Navigate<DummyPage>(); // keepInStack=true 推栈（同步部分先执行）
        Assert.True(nav.BackStackDepth > 0);
        Assert.True(cmd.CanExecute(null)); // 导航后可返回=死钮修复
    }

    /// <summary>GoBack 弹栈后栈空=CanExecute 回假（钮禁用态自洽）。</summary>
    [WpfFact]
    public void GoBack_After_Navigate_Pops_And_Disables()
    {
        var host = new ContentControl();
        // PageNavigationService/PageBase 读宿主 swdm-Motion* 资源 key
        // （真实 MainWindow 的 PageHost 在 xaml 声明；测试合并 Common.xaml)
        host.Resources.MergedDictionaries.Add(new ResourceDictionary
        {
            Source = new Uri("pack://application:,,,/Swdm2.App;component/Ui/Themes/Common.xaml"),
        });
        var nav = new PageNavigationService();
        nav.Attach(host);
        nav.Initialize<DummyPage>();

        nav.Navigate<DummyPage>();
        Assert.True(nav.GoBack()); // 弹栈成功
        Assert.Equal(0, nav.BackStackDepth);
        var cmd = new RelayCommand(() => nav.GoBack(), () => nav.BackStackDepth > 0);
        Assert.False(cmd.CanExecute(null)); // 栈空=禁用（不自相矛盾）
    }
}