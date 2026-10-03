using System.Windows;
using System.Windows.Controls;
using Swdm2.App.ViewModels;

namespace Swdm2.App.Ui.Pages.Download;

/// <summary>
/// 下载页（D5.7 IDM 体感完整版；t46）：
/// 类别树选中=过滤条件（游戏→目录）;代码后置仅做视图行为（选中路由到 VM 过滤）。
/// 行字段/按钮态契约在 DownloadsPageViewModel+DownloadTaskRowViewModel。
/// </summary>
public partial class DownloadPage : global::Swdm2.App.Ui.Pages.PageBase
{
    public DownloadPage()
    {
        InitializeComponent();
    }

    /// <summary>类别树选中→VM 过滤（视图行为不泄漏 VM)。</summary>
    private void OnCategorySelected(object sender, RoutedPropertyChangedEventArgs<object> e)
    {
        if (DataContext is DownloadsPageViewModel vm && e.NewValue is DownloadCategoryNode node)
        {
            vm.SelectCategory(node);
        }
    }
}
