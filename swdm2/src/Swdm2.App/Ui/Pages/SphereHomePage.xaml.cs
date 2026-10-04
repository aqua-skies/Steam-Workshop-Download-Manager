using System.Windows;
using System.Windows.Input;
using Swdm2.App.Boot;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Ui.Controls.HomeSphere;
using Swdm2.App.Ui.Navigation;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;
using Swdm2.App.Views;

namespace Swdm2.App.Ui.Pages;

/// <summary>
/// 球体主页（D5.15)：Loaded 启动球体动画；切页退场=球后移虚化（三段编排首段；
/// 完整编排由 t55 动画套件 PageTransitionOrchestrator 接管）。
/// t62 D5.19 instruction⑦/③ 接线：贴图点击=先跑前进相（左文字左移虚化→
/// 选项卡左抽→主区让出；IncomingPage 缺失=DetailEnter 相自动跳过）再导航。
/// </summary>
public partial class SphereHomePage : PageBase
{
    private ICommand? _vmTileCommand;

    /// <summary>前进三相近似总时长（TransitionTimingProfile.DetailProfile 相交错和）。</summary>
    private const int ForwardPhaseBudgetMs = 450;

    public SphereHomePage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (SphereHostControl is not null)
        {
            SphereHostControl.StartAnimation();
            // t62:拦截贴图命令=编排先行（用户"切页动态 UI 全没做"整改）
            _vmTileCommand = SphereHostControl.GameTileClicked;
            SphereHostControl.GameTileClicked = new DelegateTileCommand(OnGameTileClicked);
        }
    }

    /// <summary>
    /// 贴图点击处理：PageTransitionOrchestrator 前进四相对 LeftTabStrip(§2.8
    /// 左侧选项卡外壳=TabDrawer 相）+LeftTabStrip_Inner(§2.9 文字内容=TextFade
    /// 相；t65 拆分=两相不再共用元素跳变）+SphereHostControl（主区让出），
    /// **IncomingPage=真实目标 GameSelectPage(DetailEnter 相跟上=不再 null 跳过）**。
    /// 时序：DetailProfile 0-200/100-300/300-450 三相→450ms 后 DetailEnter(250ms)
    /// 对 nextPage 播 opacity 0→1+Y40→0;本页在 450ms 调 SwapDirect 无动画挂树
    /// （入栈）=用户看见详情进入。失败=降级直接导航（不阻断功能）。
    /// </summary>
    private async void OnGameTileClicked(SphereGameTile tile)
    {
        try
        {
            var nextPage = new GameSelectPage { DataContext = AppHost.Shell.GameSelect };
            var orchestrator = new PageTransitionOrchestrator();
            orchestrator.StartForward(new TransitionTargets
            {
                TextPanel = LeftTabStrip_Inner, // t65:文字相=内部 Grid
                TabStrip = LeftTabStrip,        // t65:抽屉相=外壳 Border
                MainArea = SphereHostControl,
                IncomingPage = nextPage,        // t65:DetailEnter 相=真实目标页（接线）
            });
            await Task.Delay(ForwardPhaseBudgetMs); // 三相 450ms;DetailEnter 即将开播
            AppHost.Navigation.SwapDirect(nextPage); // 无动画挂树=DetailEnter 相 0→1+Y40→0 可见
            return; // 编排已接管导航（不重复 VM 命令的带动画 Navigate)
        }
        catch
        {
            // 编排失败=降级直接导航（不阻断功能）
        }
        _vmTileCommand?.Execute(tile);
    }

    /// <summary>§2.9 空态「前往设置」入口=跳设置页（D5.18 落地）。</summary>
    private void EmptyHint_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        AppHost.Navigation.Navigate<Ui.Pages.Settings.SettingsPage>(
            () => new Ui.Pages.Settings.SettingsPage
            {
                DataContext = AppHost.Shell.Settings,
            });
    }

    /// <summary>贴图命令包装（非泛型 ICommand;RelayCommand 非泛型不接参数）。</summary>
    private sealed class DelegateTileCommand : ICommand
    {
        private readonly Action<SphereGameTile> _action;
        public DelegateTileCommand(Action<SphereGameTile> action) => _action = action;
        public bool CanExecute(object? parameter) => parameter is SphereGameTile;
        public void Execute(object? parameter)
        {
            if (parameter is SphereGameTile t) _action(t);
        }
        public event EventHandler? CanExecuteChanged { add { } remove { } }
    }
}
