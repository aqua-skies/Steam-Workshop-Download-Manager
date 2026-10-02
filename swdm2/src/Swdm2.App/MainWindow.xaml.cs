using System.Windows;
using Swdm2.App.Boot;

namespace Swdm2.App;

/// <summary>
/// Interaction logic for MainWindow.xaml
/// </summary>
public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        // AppHost.Start() runs before window construction (App.OnStartup order;
        // the shell VM is the page host + download chain owner).
        DataContext = AppHost.Shell;
    }
}
