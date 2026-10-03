using System.Windows;
using Swdm2.App.Boot;
using Swdm2.App.Ui.Pages;

namespace Swdm2.App.Ui.Pages;

/// <summary>
/// 球体主页（D5.15）：Loaded 启动球体动画；切页退场=球后移虚化（三段编排首段；
/// 完整编排由 t55 动画套件 PageTransitionOrchestrator 接管）。
/// </summary>
public partial class SphereHomePage : PageBase
{
    public SphereHomePage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (SphereHostControl is not null)
            SphereHostControl.StartAnimation();
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
}