using Swdm2.App.Ui.Pages;

using Swdm2.App.Games;
using Swdm2.Steam.Web;
using System.Windows.Input;
using Swdm2.App.Boot;
using Swdm2.App.Library;
using Swdm2.App.Community;
using Swdm2.App.Connectivity;
using Swdm2.App.ViewModels;
using Swdm2.App.Views;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Community;
// t59: 别名规避（Steam.Workshop.WorkshopBrowsePage=缓存载体 ≠ UI 页 WorkshopBrowsePage)
using Swdm2.Steam.Workshop;
using IWorkshopUpdateSource = Swdm2.Steam.Workshop.IWorkshopUpdateSource;
using WorkshopUpdateChecker = Swdm2.Steam.Workshop.WorkshopUpdateChecker;

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
    // [arch-20 t44] D5.5 浏览页 VM
    private readonly WorkshopBrowsePageViewModel _browse;
    // D5.12 库页 VM
    private readonly LibraryPageViewModel _library;
    // D5.15 球体主页 VM（用户 2026-10-03 亲定：进入即球体主页=替换原主页）
    private readonly SphereHomePageViewModel _sphereHome;
    // D5.18 设置页 VM
    private readonly SettingsPageViewModel _settings;

    /// <summary>详情页 VM（MainWindow 初始化默认页时取 DataContext）。</summary>
    public ModDetailPageViewModel ModDetail => _modDetail;

    /// <summary>下载页 VM（导航工厂取 DataContext）。</summary>
    public DownloadsPageViewModel Downloads => _downloads;

    /// <summary>游戏选择页 VM（D5.4:联想搜索+中英别名+即时反馈）。</summary>
    public GameSelectPageViewModel GameSelect => _gameSelect;

    /// <summary>[arch-20 t44] D5.5 工坊浏览页 VM。</summary>
    public WorkshopBrowsePageViewModel Browse => _browse;

    /// <summary>D5.12 库页 VM（P0 旅程 5 载体）。</summary>
    public LibraryPageViewModel Library => _library;

    /// <summary>D5.15 球体主页 VM（默认主页）。</summary>
    public SphereHomePageViewModel SphereHome => _sphereHome;

    /// <summary>D5.18 设置页 VM。</summary>
    public SettingsPageViewModel Settings => _settings;

    /// <summary>D5.9 状态栏连接 VM（MainWindow 状态栏绑定源）。</summary>
    public ConnectivityBarViewModel Connectivity { get; }

    public ICommand NavigateModDetailCommand { get; }
    public ICommand NavigateDownloadsCommand { get; }
    public ICommand NavigateBrowseCommand { get; } // [arch-20 t44]
    public ICommand NavigateGameSelectCommand { get; }
    /// <summary>D5.19/t62:返回上一页（用户"没有返回入口"整改）。</summary>
    public ICommand GoBackCommand { get; }
    public ICommand NavigateLibraryCommand { get; } // D5.12
    public ICommand NavigateSphereHomeCommand { get; } // D5.15
    public ICommand NavigateSettingsCommand { get; } // D5.18

    public MainShellViewModel(
        IPathService paths,
        IDownloadQueue queue,
        IDownloadProvider provider,
        DownloadScheduler scheduler,
        IDownloadEventBus bus,
        IConnectivityController? connectivity = null,
        ISteamWebApiClient? api = null,
        ICommunitySource? community = null,
        ICommentSource? comments = null,
        IWorkshopUpdateSource? updateSource = null)
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
        // [arch-20 t44] D5.5 浏览页（合成千项；网络源 D5.x 同契约注入）
        // D5.20b(t63):条目级动作接线——详情跳转传真实物品 id+下载入队（队列契约不变）
        _browse = new WorkshopBrowsePageViewModel(
            WorkshopBrowseItem.SampleData(),
            openDetail: item => NavigateToModDetail(
                new PublishedFileId((ulong)item.Id)),
            downloadTaskFactory: item =>
            {
                var app = item.AppId ?? new AppId(4000);
                var workshopItem = new WorkshopItem(
                    new PublishedFileId((ulong)item.Id), app, item.Title);
                return new DownloadTask(DownloadTaskId.New(), workshopItem, app,
                    paths.WorkshopContent(app))
                {
                    Provider = DownloadProvider.SteamCmd,
                    TotalBytes = workshopItem.FileSize,
                };
            },
            queue: queue,
            downloads: _downloads,
            provider: provider,
            scheduler: scheduler,
            navigateToDownloads: NavigateToDownloads);
        // D5.12: 库页（P0 旅程 5 载体；LocalLibraryScanner 轻扫，D6.1 替换真实库管理）
        // D6.2(t59): 注入真实更新检查源+下载队列（角标/Hint 不阻塞；入队询问才下载）
        _library = new LibraryPageViewModel(new LocalLibraryScanner(paths), paths, updateSource, queue);

        // D5.3: 导航委托 PageNavigationService（返回栈+时序）
        // D5.19/t62: 返回上一页（PageNavigationService.GoBack;用户"没有返回入口"整改）
        GoBackCommand = new RelayCommand(
            () => AppHost.Navigation.GoBack(),
            () => AppHost.Navigation.BackStackDepth > 0);
        NavigateModDetailCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<ModDetailPage>(
                () => new ModDetailPage { DataContext = _modDetail }));
        NavigateDownloadsCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<DownloadsPage>(
                () => new DownloadsPage { DataContext = _downloads }));
        // [arch-20 t44] D5.5 浏览页导航（契约 id MainShell_Nav_BrowseButton)
        // 全限定规避 Steam.Workshop.WorkshopBrowsePage（t56 缓存载体）歧义
        NavigateBrowseCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<Swdm2.App.Ui.Pages.WorkshopBrowsePage>(
                () => new Swdm2.App.Ui.Pages.WorkshopBrowsePage { DataContext = _browse }));
        // D5.4: 游戏选择页导航（保留契约 id MainShell_Nav_GameSelectButton)
        NavigateGameSelectCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<GameSelectPage>(
                () => new GameSelectPage { DataContext = _gameSelect }));
        // D5.12: 库页导航（契约 id MainShell_Nav_LibraryButton;P0 旅程 5「下载→库」)
        NavigateLibraryCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<LibraryPage>(
                () => new LibraryPage { DataContext = _library }));

        // D5.15: 球体主页（贴图点击→跳该游戏 mod 选择页；开始/下载钮直通）
        // D5.20c:默认游戏服务=设置页绑定后主页即时响应（单例共享）
        var defaultGame = new DefaultGameService();
        defaultGame.Load(paths);
        _sphereHome = new SphereHomePageViewModel(
            navigateToGameSelect: _ => AppHost.Navigation.Navigate<GameSelectPage>(
                () => new GameSelectPage { DataContext = _gameSelect }),
            startGame: () => { /* D5.x:启动默认游戏（阶段 6 启动器） */ },
            downloadMod: () => AppHost.Navigation.Navigate<GameSelectPage>(
                () => new GameSelectPage { DataContext = _gameSelect }),
            defaultGame: defaultGame);
        NavigateSphereHomeCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<Ui.Pages.SphereHomePage>(
                () => new Ui.Pages.SphereHomePage { DataContext = _sphereHome }));

        // D5.18: 设置页（契约 id MainShell_Nav_SettingsButton;主页空态「前往设置」入口）
        // D5.20c:默认游戏搜索=复用 t43 GameAliasTable+storesearch 在线合并
        _settings = new SettingsPageViewModel(paths, AppHost.Connectivity,
            new Ui.Themes.ThemeService(),
            storeSearch: new StoreSearchClient(AppHost.HttpFactory),
            defaultGame: defaultGame);
        NavigateSettingsCommand = new RelayCommand(
            () => AppHost.Navigation.Navigate<Ui.Pages.Settings.SettingsPage>(
                () => new Ui.Pages.Settings.SettingsPage { DataContext = _settings }));
    }

    /// <summary>#10 旅程：详情页下载入队后跳下载页。</summary>
    public void NavigateToDownloads()
        => AppHost.Navigation.Navigate<DownloadsPage>(
            () => new DownloadsPage { DataContext = _downloads });

    /// <summary>旅程 2:游戏选择确认后回详情页。</summary>
    public void NavigateToModDetail()
        => AppHost.Navigation.Navigate<ModDetailPage>(
            () => new ModDetailPage { DataContext = _modDetail });

    /// <summary>
    /// D5.20b(t63):Browse 条目点击→详情页，传真实 PublishedFileId
    /// （TryLoadAsync 立即加载真实详情：标题/描述/作者/依赖；sample 横幅转隐藏）。
    /// 页面 Loaded 见 CurrentId 已加载不重复请求。
    /// </summary>
    public void NavigateToModDetail(PublishedFileId id)
    {
        _ = _modDetail.TryLoadAsync(id);
        AppHost.Navigation.Navigate<ModDetailPage>(
            () => new ModDetailPage { DataContext = _modDetail });
    }

    public void Dispose()
    {
        _downloads.Dispose();
    }
}
