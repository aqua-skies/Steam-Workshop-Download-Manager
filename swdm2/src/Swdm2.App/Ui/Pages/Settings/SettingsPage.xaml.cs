using System.ComponentModel;
using System.Windows;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;

namespace Swdm2.App.Ui.Pages.Settings;

/// <summary>
/// 设置页（D5.18):A2 抽屉动画=Custom 输入区可见性变化时 DrawerSlide 300ms。
/// 主题即时预览=VM(ThemeService.Apply 即时换皮 A4)。
/// </summary>
public partial class SettingsPage : PageBase
{
    public SettingsPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (DataContext is SettingsPageViewModel vm)
        {
            vm.PropertyChanged += OnVmPropertyChanged;
        }
    }

    private void OnVmPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(SettingsPageViewModel.CustomPanelVisible)) return;
        // A2：抽屉下拉/收起（DrawerSlide 300ms;arch-20 t587e48c 动画套件）
        if (CustomProxyPanel.Visibility == Visibility.Visible)
            DrawerSlide.SlideDown(CustomProxyPanel);
        else
            DrawerSlide.SlideUp(CustomProxyPanel);
    }
}
