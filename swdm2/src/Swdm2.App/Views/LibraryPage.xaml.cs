using System.Windows;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;

namespace Swdm2.App.Views;

/// <summary>
/// 库页（D5.12;P0 旅程 5 载体）：显示即扫描加载（RefreshCommand 同入口）。
/// </summary>
public partial class LibraryPage : PageBase
{
    public LibraryPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (DataContext is LibraryPageViewModel vm)
            _ = vm.LoadAsync();
    }
}
