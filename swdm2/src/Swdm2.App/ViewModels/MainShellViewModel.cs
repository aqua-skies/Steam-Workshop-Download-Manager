using System.Windows.Input;
using Swdm2.App.Boot;
using Swdm2.App.Views;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 主壳 VM（D3.5b 最小骨架；D5.3 导航改 PageNavigationService 返回栈）：
/// - 两页导航（MainShell_Nav_ModDetailButton / MainShell_Nav_DownloadsButton）；
/// - 详情页下载命令的导航回调=入队后跳下载页（#10 旅程：任务行出现）；
/// - 皮肤级壳（侧栏 t2 §2.6/主题状态栏连通文本 D5.9）留后续。
/// 页面容器替换由 PageNavigationService 驱动（110→30ms 切页时序+返回栈）。
/// </summary>
public sealed class MainShellViewModel : ViewModelBase, IDisposable
{
    private readonly DownloadsPageViewModel _downloads;
    private readonly ModDetailPageViewModel _modDetail;

    /// <summary>详情页 VM（MainWindow 初始化默认页时取 DataContext）。</summary>
    public ModDetailPageViewModel ModDetail => _modDetail;

    /// <summary>下载页 VM（导航工厂取 DataContext）。</summary>
    public DownloadsPageViewModel Downloads => _downloads;

    public ICommand NavigateModDetailCommand { get; }
    public ICommand NavigateDownloadsCommand { get; }

    public MainShellViewModel(
        IPathService paths,
        IDownloadQueue queue,
        IDownloadProvider provider,
        DownloadScheduler scheduler,
        IDownloadEventBus bus)
    {
        ArgumentNullException.ThrowIfNull(paths);
        ArgumentNullException.ThrowIfNull(queue);
        ArgumentNullException.ThrowIfNull(provider);
        ArgumentNullException.ThrowIfNull(scheduler);
        ArgumentNullException.ThrowIfNull(bus);

        _downloads = new DownloadsPageViewModel(bus);
        _modDetail = new ModDetailPageViewModel(
            paths, queue, _downloads, provider, scheduler, NavigateToDownloads);

        // D5.3: 导航委托 PageNavigationService（返回栈+时序）
        NavigateModDetailCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<ModDetailPage>(
                () => new ModDetailPage { DataContext = _modDetail }));
        NavigateDownloadsCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<DownloadsPage>(
                () => new DownloadsPage { DataContext = _downloads }));
    }

    /// <summary>#10 旅程：详情页下载入队后跳下载页。</summary>
    public void NavigateToDownloads()
        => AppHost.Navigation.Navigate<DownloadsPage>(
            () => new DownloadsPage { DataContext = _downloads });

    public void Dispose()
    {
        _downloads.Dispose();
    }
}
