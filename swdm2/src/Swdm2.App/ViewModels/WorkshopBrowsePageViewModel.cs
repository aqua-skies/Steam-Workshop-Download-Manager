using System.Collections.ObjectModel;
using Swdm2.App.Games;
using System.Globalization;
using System.Threading;
using Swdm2.Core.Domain;
using Swdm2.Steam.Workshop;
using System.ComponentModel;
using System.Windows.Input;
using Swdm2.Core.Results;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 工坊浏览页 VM(D5.5):
/// - 筛选链：搜索（标题子串）+标签（精确含）+作者（子串）→排序→分页
/// - 每次筛选变更=**重建集合**（C1:不原地改；1.x clear/rebuild 闪烁教训=绑定新引用而非换内容）
/// - 分页：PageSize=50/100/200/0（0=不分页全部交给虚拟化）；分页+虚拟化正交（分页省源、虚拟化省 DOM)
/// - 千项流畅性：源 1000→单页最多 PageSize 或全部；ScrollRenderFrames 由页面代码层计（帧计数）
/// </summary>
public sealed class WorkshopBrowsePageViewModel : ViewModelBase
{
    private IReadOnlyList<WorkshopBrowseItem> _source;
    private string? _errorMessage;

    /// <summary>分页后条目（ListBox 绑定源；重建=重新引用）。</summary>
    public ObservableCollection<WorkshopBrowseItem> PageItems { get; } = new();

    public ObservableCollection<string> TagOptions { get; }

    private string _searchText = string.Empty;
    public string SearchText
    {
        get => _searchText;
        set { if (SetProperty(ref _searchText, value)) Rebuild(); }
    }

    private string? _tagFilter;
    /// <summary>标签筛选（null=全部）。</summary>
    public string? TagFilter
    {
        get => _tagFilter;
        set { if (SetProperty(ref _tagFilter, value)) Rebuild(); }
    }

    private string _authorFilter = string.Empty;
    public string AuthorFilter
    {
        get => _authorFilter;
        set { if (SetProperty(ref _authorFilter, value)) Rebuild(); }
    }

    private BrowseSortKey _sortKey = BrowseSortKey.UpdatedAt;
    public BrowseSortKey SortKey
    {
        get => _sortKey;
        set { if (SetProperty(ref _sortKey, value)) Rebuild(); }
    }

    private bool _sortDescending = true;
    public bool SortDescending
    {
        get => _sortDescending;
        set { if (SetProperty(ref _sortDescending, value)) Rebuild(); }
    }

    private int _pageSize = 100;
    /// <summary>页大小：50/100/200/0（0=全部，交给虚拟化）。</summary>
    public int PageSize
    {
        get => _pageSize;
        set { if (SetProperty(ref _pageSize, value)) Rebuild(); }
    }


    /// <summary>排序组合框索引桥（TwoWay:0=Title/1=Subscribers/2=UpdatedAt)。</summary>
    public int SortKeyAsIndex
    {
        get => (int)SortKey;
        set
        {
            if (value >= 0 && value <= 2 && (BrowseSortKey)value != SortKey)
                SortKey = (BrowseSortKey)value;
        }
    }

    /// <summary>每页组合框索引桥（0=50/1=100/2=200/3=全部）。</summary>
    public int PageSizeAsIndex
    {
        get => PageSize switch { 50 => 0, 100 => 1, 200 => 2, 0 => 3, _ => 1 };
        set
        {
            var size = value switch { 0 => 50, 1 => 100, 2 => 200, 3 => 0, _ => 100 };
            if (size != PageSize) PageSize = size;
        }
    }

    /// <summary>标签筛选桥（组合框=“全部”→null)。</summary>
    public string? SelectedTag
    {
        get => TagFilter;
        set
        {
            var v = value == "全部" ? null : value;
            if (v != TagFilter) TagFilter = v;
        }
    }

    /// <summary>计数标签文本（筛选后/源）。</summary>
    public string ItemCountText => $"筛选 {FilteredCount:N0} / 共 {SourceCount:N0} 项";

    /// <summary>分页标签文本。</summary>
    public string PageLabelText => PageSize > 0 ? $"第 {CurrentPage} / {TotalPages} 页" : "全部条目";
    private int _currentPage = 1;
    public int CurrentPage
    {
        get => _currentPage;
        private set { SetProperty(ref _currentPage, value); }
    }

    private int _totalPages = 1;
    public int TotalPages
    {
        get => _totalPages;
        private set { SetProperty(ref _totalPages, value); }
    }

    private int _filteredCount;
    /// <summary>筛选后总数（分页前）。</summary>
    public int FilteredCount
    {
        get => _filteredCount;
        private set { SetProperty(ref _filteredCount, value); }
    }

    private int _sourceCount;
    public int SourceCount
    {
        get => _sourceCount;
        private set { SetProperty(ref _sourceCount, value); }
    }

    public ICommand NextPageCommand { get; }
    public ICommand PrevPageCommand { get; }
    public ICommand ResetFiltersCommand { get; }

    // ---- D5.20b:条目级动作（详情跳转+下载入队；缺省=命令禁用，非死钮） ----
    private readonly Action<WorkshopBrowseItem>? _openDetail;
    private readonly Func<WorkshopBrowseItem, DownloadTask>? _downloadTaskFactory;
    private readonly IDownloadQueue? _queue;
    private readonly DownloadsPageViewModel? _downloads;
    private readonly IDownloadProvider? _provider;
    private readonly DownloadScheduler? _scheduler;
    private readonly Action? _navigateToDownloads;

    /// <summary>条目「详情」命令（Browse→Detail 传真实 id;PartDetail=本自身）。</summary>
    public ICommand OpenItemDetailCommand { get; }

    /// <summary>条目「下载」命令（点击入队；IDownloadQueue 契约不变）。</summary>
    public ICommand DownloadItemCommand { get; }

    /// <summary>D9.2:错误态显隐（错误横幅 Visibility 绑定源）。
    /// 计算属性=随 ErrorMessage 变化显式通知（否则 WPF 绑定不更新=t68 实测横幅不现的根因）。</summary>
    public bool HasError => !string.IsNullOrEmpty(_errorMessage);

    /// <summary>D9.2:加载/失败状态文案（失败=明确原因中文，不静默；空=已加载或未加载）。</summary>
    public string? ErrorMessage
    {
        get => _errorMessage;
        private set
        {
            if (SetProperty(ref _errorMessage, value))
                RaisePropertyChanged(nameof(HasError));
        }
    }

    /// <summary>D9.2:是否加载中（防重复并发加载；UI 菊花/禁用提示）。</summary>
    private bool _isLoading;
    public bool IsLoading
    {
        get => _isLoading;
        private set => SetProperty(ref _isLoading, value);
    }

    /// <summary>
    /// D9.2:从真实工坊源加载条目（失败=ErrorMessage 中文原因+保留旧数据不静默）。
    /// </summary>
    public async Task LoadFromSourceAsync(
        IWorkshopBrowseSource source, AppId appId, CancellationToken ct = default)
    {
        if (IsLoading) return;
        IsLoading = true;
        ErrorMessage = null;
        try
        {
            var query = new WorkshopBrowseQuery(
                SearchText: appId.Value.ToString(CultureInfo.InvariantCulture),
                Tag: null, Author: null,
                SortKey: WorkshopBrowseSortKey.UpdatedAt, SortDescending: true,
                Page: 1, PageSize: 50);
            var result = await source.FetchAsync(query, ct).ConfigureAwait(false);
            if (result is { IsOk: true, Value: not null })
            {
                var items = WorkshopBrowseItem.FromEntries(result.Value, appId);
                _source = items;
                SourceCount = items.Count;
                TagOptions.Clear();
                foreach (var t in new[] { "全部" }
                             .Concat(items.SelectMany(i => i.Tags).Distinct().OrderBy(t => t)))
                    TagOptions.Add(t);
                Rebuild();
                if (items.Count == 0)
                    ErrorMessage = $"工坊条目为 0（appid {appId.Value} 可能无条目或页面结构变化）";
            }
            else
            {
                ErrorMessage = MapErrorMessage(result.Error ?? SteamError.None);
            }
        }
        catch (OperationCanceledException)
        {
            ErrorMessage = "加载已取消";
        }
        catch (Exception ex)
        {
            ErrorMessage = $"加载失败：{ex.GetType().Name}（{ex.Message}）";
        }
        finally
        {
            IsLoading = false;
        }
    }

    /// <summary>SteamError→中文失败原因（1.x"明确不装"纪律）。</summary>
    private static string MapErrorMessage(SteamError err) => err switch
    {
        SteamError.Network => "网络不可达（steamcommunity.com 连接失败；检查代理/网络）",
        SteamError.Timeout => "请求超时（steamcommunity.com 响应过慢）",
        SteamError.RateLimited => "被限流（Steam 429/熔断开态；稍后重试）",
        SteamError.Blocked => "被屏蔽（403;IP/区域限制）",
        SteamError.NotFound => "工坊页 404（appid 无效）",
        SteamError.CircuitOpen => "熔断开（近期多次失败；稍后重试）",
        SteamError.Deserialization => "页面解析失败（Steam 页面结构变更；需适配）",
        SteamError.InvalidConfiguration => "查询配置无效（缺 appid）",
        _ => $"加载失败：{err}",
    };

    // ---- D9.1(t67):当前游戏快切+示例数据显式标注 ----
    private readonly DefaultGameService? _defaultGame;
    private string _currentGameText = "当前游戏：未绑定";

    /// <summary>顶栏当前游戏文本（绑定 DefaultGameService 即时响应）。</summary>
    public string CurrentGameText
    {
        get => _currentGameText;
        private set => SetProperty(ref _currentGameText, value);
    }

    /// <summary>切换游戏命令（顶栏钮→GameSelect 搜索选择，用户"免点出去切换"）。</summary>
    public ICommand SwitchGameCommand { get; }

    /// <summary>示例数据态（列表为合成样本=醒目标注 banner;真实源接入后 false)。</summary>
    public bool IsSampleData { get; }

    public WorkshopBrowsePageViewModel(IReadOnlyList<WorkshopBrowseItem> source)
        : this(source, null, null, null, null, null, null, null,
               defaultGame: null, switchGame: null, isSampleData: true)
    {
    }

    /// <param name="openDetail">条目→详情页导航（传真实物品 id)。</param>
    /// <param name="downloadTaskFactory">条目→DownloadTask 构建（AppId/标题来自条目）。</param>
    /// <param name="queue">下载队列（入队）。</param>
    /// <param name="downloads">下载页 VM（行注册，与详情页入队同模式）。</param>
    /// <param name="provider">下载 provider（行注册需要）。</param>
    /// <param name="scheduler">调度器（行注册需要）。</param>
    /// <param name="navigateToDownloads">入队后跳下载页（同详情页旅程）。</param>
    /// <param name="defaultGame">D9.1:默认游戏服务（顶栏当前游戏名即时响应）。</param>
    /// <param name="switchGame">D9.1:切换游戏导航（→GameSelect)。</param>
    /// <param name="isSampleData">D9.1:示例数据态（banner 醒目标注）。</param>
    public WorkshopBrowsePageViewModel(
        IReadOnlyList<WorkshopBrowseItem> source,
        Action<WorkshopBrowseItem>? openDetail,
        Func<WorkshopBrowseItem, DownloadTask>? downloadTaskFactory,
        IDownloadQueue? queue,
        DownloadsPageViewModel? downloads,
        IDownloadProvider? provider,
        DownloadScheduler? scheduler,
        Action? navigateToDownloads,
        DefaultGameService? defaultGame = null,
        Action? switchGame = null,
        bool isSampleData = false)
    {
        ArgumentNullException.ThrowIfNull(source);
        _source = source;
        SourceCount = source.Count;
        TagOptions = new ObservableCollection<string>(new[] { "全部" }
            .Concat(source.SelectMany(i => i.Tags).Distinct().OrderBy(t => t)));
        NextPageCommand = new RelayCommand(_ => GoPage(+1), _ => CurrentPage < TotalPages);
        PrevPageCommand = new RelayCommand(_ => GoPage(-1), _ => CurrentPage > 1);
        ResetFiltersCommand = new RelayCommand(_ =>
        {
            SearchText = string.Empty;
            TagFilter = null;
            AuthorFilter = string.Empty;
            SortKey = BrowseSortKey.UpdatedAt;
            SortDescending = true;
            PageSize = 100;
        });

        // D5.20b
        _openDetail = openDetail;
        _downloadTaskFactory = downloadTaskFactory;
        _queue = queue;
        _downloads = downloads;
        _provider = provider;
        _scheduler = scheduler;
        _navigateToDownloads = navigateToDownloads;
        OpenItemDetailCommand = new RelayCommand(
            param => OpenDetail((WorkshopBrowseItem)param!),
            _ => _openDetail is not null);
        DownloadItemCommand = new RelayCommand(
            async param => await DownloadItemAsync((WorkshopBrowseItem)param!).ConfigureAwait(false),
            _ => _downloadTaskFactory is not null && _queue is not null);

        // D9.1(t67):当前游戏快切+样本标注
        _defaultGame = defaultGame;
        IsSampleData = isSampleData;
        // 注：0 参 execute 绑 (Action, Func<bool>) 重载→canExecute 亦 0 参（_ => 会 CS1593)
        SwitchGameCommand = new RelayCommand(
            () => switchGame?.Invoke(),
            () => switchGame is not null);
        if (_defaultGame is not null)
        {
            RefreshCurrentGameText();
            _defaultGame.PropertyChanged += OnDefaultGameChanged;
        }

        Rebuild();
    }

    private void OnDefaultGameChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(DefaultGameService.Current))
            RefreshCurrentGameText();
    }

    private void RefreshCurrentGameText()
    {
        CurrentGameText = _defaultGame?.Current is { } g
            ? $"当前游戏：{g.Title}"
            : "当前游戏：未绑定";
    }

    /// <summary>D5.20b:条目→详情（传真实 id;MainShellVM.NavigateToModDetail(id))。</summary>
    private void OpenDetail(WorkshopBrowseItem item)
        => _openDetail?.Invoke(item);

    /// <summary>
    /// D5.20b:条目下载入队（同详情页 DownloadAsync 模式：入队+行注册+跳下载页）。
    /// **1.x 学费：真实队列契约不变；条目来源样本 AppId=4000（演示默认游戏）。
    /// </summary>
    private async Task DownloadItemAsync(WorkshopBrowseItem item)
    {
        var task = _downloadTaskFactory!(item);
        await _queue!.EnqueueAsync(task).ConfigureAwait(false);

        // 行注册（UI 线程：ObservableCollection.Add;与详情页 DownloadAsync 同模式）
        if (_downloads is not null && _provider is not null && _scheduler is not null)
        {
            var row = new DownloadTaskRowViewModel(task, _provider, _scheduler);
            System.Windows.Application.Current?.Dispatcher.Invoke(() => _downloads.RegisterRow(row));
        }
        _navigateToDownloads?.Invoke();
    }

    private void GoPage(int delta)
    {
        var page = Math.Clamp(CurrentPage + delta, 1, Math.Max(1, TotalPages));
        if (page != CurrentPage)
        {
            CurrentPage = page;
            Rebuild();
        }
    }

    /// <summary>筛选→排序→分页→重建集合（UI 线程同步；无异步=即时反馈 A9)。</summary>
    public void Rebuild()
    {
        var q = _source.AsEnumerable();
        if (!string.IsNullOrWhiteSpace(SearchText))
            q = q.Where(i => i.Title.Contains(SearchText, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(TagFilter))
            q = q.Where(i => i.Tags.Contains(TagFilter, StringComparer.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(AuthorFilter))
            q = q.Where(i => i.Author.Contains(AuthorFilter, StringComparison.OrdinalIgnoreCase));

        q = SortKey switch
        {
            BrowseSortKey.Title => SortDescending
                ? q.OrderByDescending(i => i.Title, StringComparer.OrdinalIgnoreCase)
                : q.OrderBy(i => i.Title, StringComparer.OrdinalIgnoreCase),
            BrowseSortKey.Subscribers => SortDescending
                ? q.OrderByDescending(i => i.Subscribers)
                : q.OrderBy(i => i.Subscribers),
            _ => SortDescending ? q.OrderByDescending(i => i.UpdatedAt) : q.OrderBy(i => i.UpdatedAt),
        };

        var filtered = q.ToList();
        FilteredCount = filtered.Count;
        TotalPages = PageSize > 0
            ? Math.Max(1, (int)Math.Ceiling(filtered.Count / (double)PageSize))
            : 1;
        if (CurrentPage > TotalPages) CurrentPage = TotalPages;

        var page = PageSize > 0
            ? filtered.Skip((CurrentPage - 1) * PageSize).Take(PageSize)
            : filtered;

        PageItems.Clear();
        foreach (var item in page) PageItems.Add(item);
    }

    /// <summary>筛选谓词等价检查（测试用：确认不重建则不变）。</summary>
    public bool Matches(WorkshopBrowseItem item)
    {
        if (!string.IsNullOrWhiteSpace(SearchText)
            && !item.Title.Contains(SearchText, StringComparison.OrdinalIgnoreCase)) return false;
        if (!string.IsNullOrWhiteSpace(TagFilter)
            && !item.Tags.Contains(TagFilter, StringComparer.OrdinalIgnoreCase)) return false;
        if (!string.IsNullOrWhiteSpace(AuthorFilter)
            && !item.Author.Contains(AuthorFilter, StringComparison.OrdinalIgnoreCase)) return false;
        return true;
    }
}
