using System.Windows;
using Swdm2.App.Boot;

namespace Swdm2.App;

/// <summary>
/// App entry (D3.5b minimum testable skeleton):
/// OnStartup = AppHost.Start() (download chain assembly) + MainWindow show;
/// OnExit = chain async dispose.
/// StartupUri removed: host must boot before the window binds AppHost.Shell.
/// </summary>
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
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
