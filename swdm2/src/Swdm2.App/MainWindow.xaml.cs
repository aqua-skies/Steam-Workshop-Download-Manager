using System.Windows;
using Swdm2.App.Boot;
using Swdm2.App.Views;

namespace Swdm2.App;

/// <summary>
/// Interaction logic for MainWindow.xaml（D5.3:t2 §2.4 窗口 chrome）。
/// 路线=fallback 条款（WindowChrome+自绘标题栏；弃 WPF-UI FluentWindow/TitleBar
/// ——沙箱 UIA 零子的实证见 MainWindow.xaml 头注）。
/// </summary>
public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        // AppHost.Start() runs before window construction (App.OnStartup order;
        // the shell VM is the page host + download chain owner).
        DataContext = AppHost.Shell;

        // D5.3:页面容器替换（PageNavigationService;返回栈+110→30ms 切页时序）
        // D5.15（用户 2026-10-03 亲定）：默认页=球体主页（进入即球体主页；
        // t54 验收①）。ModDetail 改由贴图点击/导航钮进入。
        AppHost.Navigation.Attach(PageHost);
        AppHost.Navigation.Initialize<Ui.Pages.SphereHomePage>(() => new Ui.Pages.SphereHomePage
        {
            DataContext = AppHost.Shell.SphereHome,
        });
    }

    private void BtnClose_Click(object sender, RoutedEventArgs e) => Close();

    private void BtnMin_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
}
