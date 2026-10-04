using System.Windows;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;

namespace Swdm2.App.Views;

/// <summary>
/// mod detail page（D5.6;D3.5b 骨架→真详情页）。
/// 显示即加载（Loaded→VM.LoadDetailAsync:API→社区回退→评论+冲突检测）;
/// 失败=整页错误态+重试（ReloadCommand);字段缺失=来源标注诚实降级。
/// AutomationId 契约不动（t3 §3.2 保留表：TitleText/DependencyList_Items/DownloadButton)。
/// </summary>
public partial class ModDetailPage : PageBase
{
    public ModDetailPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        // 每次页面载入触发一次真详情加载（ReloadCommand 同入口；失败可重试）
        // D5.20b:Browse 传入 id 时 TryLoadAsync 已发起加载（CurrentId 非空），
        // 不重复请求；无 id 入口=默认物品/示例兜底加载。
        if (DataContext is ModDetailPageViewModel vm && vm.CurrentId is null)
            _ = vm.LoadDetailAsync();
    }
}
