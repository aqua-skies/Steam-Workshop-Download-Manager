using System.Windows.Input;
using Swdm2.App.Boot;
using Swdm2.App.Community;
using Swdm2.App.Connectivity;
using Swdm2.App.ViewModels;
using Swdm2.App.Views;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Community;
using Swdm2.Steam.Web;

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
    private readonly GameSelectPageViewModel _gameSelect;

    /// <summary>详情页 VM（MainWindow 初始化默认页时取 DataContext）。</summary>
    public ModDetailPageViewModel ModDetail => _modDetail;

    /// <summary>下载页 VM（导航工厂取 DataContext）。</summary>
    public DownloadsPageViewModel Downloads => _downloads;

    /// <summary>游戏选择页 VM（D5.4:联想搜索+中英别名+即时反馈）。</summary>
    public GameSelectPageViewModel GameSelect => _gameSelect;

    /// <summary>D5.9 状态栏连接 VM（MainWindow 状态栏绑定源）。</summary>
    public ConnectivityBarViewModel Connectivity { get; }

    public ICommand NavigateModDetailCommand { get; }
    public ICommand NavigateDownloadsCommand { get; }
    public ICommand NavigateGameSelectCommand { get; }

    public MainShellViewModel(
        IPathService paths,
        IDownloadQueue queue,
        IDownloadProvider provider,
        DownloadScheduler scheduler,
        IDownloadEventBus bus,
        IConnectivityController? connectivity = null,
        ISteamWebApiClient? api = null,
        ICommunitySource? community = null,
        ICommentSource? comments = null)
    {
        ArgumentNullException.ThrowIfNull(paths);
        ArgumentNullException.ThrowIfNull(queue);
        ArgumentNullException.ThrowIfNull(provider);
        ArgumentNullException.ThrowIfNull(scheduler);
        ArgumentNullException.ThrowIfNull(bus);
        if (connectivity is null) throw new ArgumentNullException(nameof(connectivity));

        // D5.4 机械修复保留双向注入（IConnectivityState 订阅+IConnectivityController 命令；
        // 运行时实例=ConnectivityStateService 同时实现两者——归属 arch-20 t48)
        Connectivity = new ConnectivityBarViewModel((Swdm2.Steam.Connectivity.IConnectivityState)connectivity, connectivity);
        _downloads = new DownloadsPageViewModel(bus);
        // D5.6: 真详情加载链（API→社区回退→评论；null=未装配=VM 错误态不造假）
        _modDetail = new ModDetailPageViewModel(
            paths, queue, _downloads, provider, scheduler, NavigateToDownloads,
            api, community, comments);
        // D5.4: 游戏选择页（在线源可选——网络熔断时本地别名兜底；
        // 确认后回详情页（旅程 2:搜索→确认→详情可下载）
        _gameSelect = new GameSelectPageViewModel(navigateToDetail: _ => NavigateToModDetail());

        // D5.3: 导航委托 PageNavigationService（返回栈+时序）
        NavigateModDetailCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<ModDetailPage>(
                () => new ModDetailPage { DataContext = _modDetail }));
        NavigateDownloadsCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<DownloadsPage>(
                () => new DownloadsPage { DataContext = _downloads }));
        // D5.4: 游戏选择页导航（保留契约 id MainShell_Nav_GameSelectButton)
        NavigateGameSelectCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<GameSelectPage>(
                () => new GameSelectPage { DataContext = _gameSelect }));
    }

    /// <summary>#10 旅程：详情页下载入队后跳下载页。</summary>
    public void NavigateToDownloads()
        => AppHost.Navigation.Navigate<DownloadsPage>(
            () => new DownloadsPage { DataContext = _downloads });

    /// <summary>旅程 2:游戏选择确认后回详情页。</summary>
    public void NavigateToModDetail()
        => AppHost.Navigation.Navigate<ModDetailPage>(
            () => new ModDetailPage { DataContext = _modDetail });

    public void Dispose()
    {
        _downloads.Dispose();
    }
}
