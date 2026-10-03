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
        // 默认页=ModDetailPage(D3.7 #10 旅程起点：详情可点击下载）
        AppHost.Navigation.Attach(PageHost);
        AppHost.Navigation.Initialize<ModDetailPage>(() => new ModDetailPage
        {
            DataContext = AppHost.Shell.ModDetail,
        });
    }

    private void BtnClose_Click(object sender, RoutedEventArgs e) => Close();

    private void BtnMin_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
}
