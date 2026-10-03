using System.Windows;
using Swdm2.App.Boot;
using Velopack;

namespace Swdm2.App;

/// <summary>
/// App entry (D3.5b minimum testable skeleton):
/// OnStartup = VelopackApp.Run() (D6.1:安装/升级钩子，必须最开头——vpk pack 前置校验）
///            + AppHost.Start() (download chain assembly) + MainWindow show;
/// OnExit = chain async dispose.
/// StartupUri removed: host must boot before the window binds AppHost.Shell.
/// </summary>
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        // D6.1/t58: 首次安装/升级生命周期最开头处理（Velopack 契约；不处理则 vpk pack 拒绝打包）
        VelopackApp.Build().Run();
        base.OnStartup(e);
        AppHost.Start();
        var mainWindow = new MainWindow();
        mainWindow.Show();
    }

    protected override async void OnExit(ExitEventArgs e)
    {
        await AppHost.StopAsync().ConfigureAwait(true);
        base.OnExit(e);
    }
}
