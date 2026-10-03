using System.Windows.Controls;
using System.Windows.Input;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;

namespace Swdm2.App.Views;

/// <summary>
/// 游戏选择页（D5.4):联想搜索+中英别名归一化+即时反馈（1.x 三 bug 防呆见 VM)。
/// 回车/双击同入口=VM.HandleEnterKey/ConfirmSelection;回车时候选未到=挂起
/// （候选到达自动兑现，词不被静默丢弃——1.x 学费）。
/// </summary>
public partial class GameSelectPage : PageBase
{
    public GameSelectPage()
    {
        InitializeComponent();

        // 设计期/无 DataContext 场景的回退 VM（真实装配由 MainWindow 工厂注入）
        DataContext ??= new GameSelectPageViewModel();
    }

    private void SearchBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter)
            return;
        // 1.x 回车去重：候选未到时由 VM 挂起，候选到达自动选中（词不丢弃）
        if (DataContext is GameSelectPageViewModel vm)
            vm.HandleEnterKey();
        e.Handled = true;
    }

    private void SuggestionList_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (sender is not ListBox list)
            return;
        if (list.SelectedItem is GameInfo game
            && DataContext is GameSelectPageViewModel vm)
            vm.ConfirmSelection(game);
    }
}
