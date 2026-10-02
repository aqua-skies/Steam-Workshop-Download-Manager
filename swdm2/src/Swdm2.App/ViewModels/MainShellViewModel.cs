using System.Windows.Input;
using Swdm2.App.Views;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 主壳 VM（D3.5b 最小骨架）：
/// - 两页导航（MainShell_Nav_ModDetailButton / MainShell_Nav_DownloadsButton）；
/// - 详情页下载命令的导航回调=入队后跳下载页（#10 旅程：任务行出现）；
/// - 皮肤级壳（窗口 chrome/侧栏/主题/状态栏连通文本 D5.9）留 D5。
/// </summary>
public sealed class MainShellViewModel : ViewModelBase, IDisposable
{
    private readonly DownloadsPageViewModel _downloads;
    private readonly ModDetailPageViewModel _modDetail;
    private object? _currentPageView;

    public object? CurrentPageView
    {
        get => _currentPageView;
        private set => SetProperty(ref _currentPageView, value);
    }

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

        NavigateModDetailCommand = new RelayCommand(
            () => CurrentPageView = new ModDetailPage { DataContext = _modDetail });
        NavigateDownloadsCommand = new RelayCommand(
            () => CurrentPageView = new DownloadsPage { DataContext = _downloads });

        // 默认页=mod 详情（D3.7 #10 旅程起点：详情可点击下载）
        CurrentPageView = new ModDetailPage { DataContext = _modDetail };
    }

    private void NavigateToDownloads()
        => CurrentPageView = new DownloadsPage { DataContext = _downloads };

    public void Dispose()
    {
        _downloads.Dispose();
    }
}
