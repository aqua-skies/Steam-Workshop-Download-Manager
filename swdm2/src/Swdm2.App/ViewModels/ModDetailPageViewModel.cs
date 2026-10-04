using System.Collections.ObjectModel;
using System.Windows.Input;
using Swdm2.App.Community;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Community;
using Swdm2.Steam.Web;

namespace Swdm2.App.ViewModels;

/// <summary>
/// mod 详情页 VM（D5.6;D3.5b 骨架升级为真详情加载）。
/// 加载链（任务验收口径）：
/// ① **依赖来自 Web API**(ISteamWebApiClient.GetPublishedFileDetailsAsync:
///    Dependencies = API 返回的 required_items→C1 不可变快照）;
/// ② 字段缺失→**社区回退**(ICommunitySource.EnrichDetailAsync 填 Creator/Description/Preview;
///    D2.5 契约：仅 Community 端点已验证可达时调用，失败=Fail 不抛）;
/// ③ 评论区（CommunityCommentSource 共享 community-detail 节流桶拉取 HTML→解析）。
/// **诚实降级**（验收②):每个字段标注来源（API/社区回退/缺失）——显示真值或"字段缺失"，
/// 不造假数据；加载失败=整页错误态（Error+重试命令）。
/// **冲突检测**（本地规则+一次 batch API):
/// - 自引用：item 的 id 出现在自己的 Dependencies 中
/// - 重复依赖：Dependencies 去重后数量减少
/// - 两层循环：任一依赖的依赖回指本物品（batch 一次查，≤30 条防爆请求）
/// </summary>
public sealed class ModDetailPageViewModel : ViewModelBase
{
    private readonly IPathService _paths;
    private readonly IDownloadQueue _queue;
    private readonly DownloadsPageViewModel _downloads;
    private readonly IDownloadProvider _provider;
    private readonly DownloadScheduler _scheduler;
    private readonly Action? _navigateToDownloads;
    private readonly ISteamWebApiClient? _api;
    private readonly ICommunitySource? _community;
    private readonly ICommentSource? _comments;

    public string Title { get; }
    public IReadOnlyList<string> Dependencies { get; }

    public ICommand DownloadCommand { get; }
    public ICommand ReloadCommand { get; }

    // ---- 真详情状态（D5.6) ----
    private WorkshopItem? _item;
    private bool _isLoading;
    private string _errorMessage = string.Empty;
    private string _descriptionSource = "未加载";
    private string _creatorSource = "未加载";
    private string _previewSource = "未加载";
    private string _dependenciesSource = "未加载";
    private string _commentsStatus = "未加载";

    /// <summary>详情主物品（API/社区合并后的快照；null=未加载）。</summary>
    public WorkshopItem? Item
    {
        get => _item;
        private set
        {
            if (SetProperty(ref _item, value))
            {
                RaisePropertyChanged(nameof(ItemTitle));
                RaisePropertyChanged(nameof(ItemCreator));
                RaisePropertyChanged(nameof(ItemDescription));
                RaisePropertyChanged(nameof(IsSampleMode));
            }
        }
    }

    /// <summary>当前关联的工坊物品 id（Browse 项点击传入；null=示例/默认兜底）。</summary>
    public PublishedFileId? CurrentId
    {
        get => _currentId;
        private set
        {
            if (SetProperty(ref _currentId, value))
                RaisePropertyChanged(nameof(IsSampleMode));
        }
    }

    /// <summary>
    /// 示例数据态（D5.20b 用户反馈"详情通篇编号 sample"整改）:
    /// true=未关联真实物品 id 且未加载成功=页面显示示例兜底（标题/依赖为 ctor 样本）。
    /// banner 显式标注"示例"，真实 id 一经传入立即转 false。
    /// </summary>
    public bool IsSampleMode => Item is null && CurrentId is null;

    public bool IsLoading
    {
        get => _isLoading;
        private set => SetProperty(ref _isLoading, value);
    }

    /// <summary>整页错误信息（加载失败时非空；空串=无错误）。诚实降级主通道。</summary>
    public string ErrorMessage
    {
        get => _errorMessage;
        private set
        {
            if (SetProperty(ref _errorMessage, value))
                RaisePropertyChanged(nameof(HasErrorVisibility));
        }
    }

    // ---- 字段来源标注（验收②：社区字段缺失诚实降级显示） ----
    /// <summary>描述来源标签："API"/"社区回退"/"字段缺失"/"未加载"。</summary>
    public string DescriptionSource
    {
        get => _descriptionSource;
        private set => SetProperty(ref _descriptionSource, value);
    }
    public string CreatorSource
    {
        get => _creatorSource;
        private set => SetProperty(ref _creatorSource, value);
    }
    public string PreviewSource
    {
        get => _previewSource;
        private set => SetProperty(ref _previewSource, value);
    }
    /// <summary>依赖来源标签（验收①："API"=依赖来自 Web API)。</summary>
    public string DependenciesSource
    {
        get => _dependenciesSource;
        private set => SetProperty(ref _dependenciesSource, value);
    }

    /// <summary>评论区状态（加载中/失败/计数；空串=未加载）。</summary>
    public string CommentsStatus
    {
        get => _commentsStatus;
        private set => SetProperty(ref _commentsStatus, value);
    }

    // ---- XAML 绑定友好视图属性 ----
    /// <summary>标题显示值（未加载=示例标题；加载后=API/社区标题）。</summary>
    public string ItemTitle => Item?.Title ?? Title;
    /// <summary>作者显示值（未加载/缺失="未知作者"诚实降级）。</summary>
    public string ItemCreator => string.IsNullOrWhiteSpace(Item?.Creator) ? "未知作者" : Item!.Creator!;
    /// <summary>描述显示值（未加载/缺失="暂无简介"诚实降级）。</summary>
    public string ItemDescription => string.IsNullOrWhiteSpace(Item?.Description) ? "暂无简介" : Item!.Description!;

    /// <summary>错误横幅可见性（ErrorMessage 非空→Visible;空→Collapsed)。</summary>
    public System.Windows.Visibility HasErrorVisibility
        => string.IsNullOrEmpty(ErrorMessage) ? System.Windows.Visibility.Collapsed : System.Windows.Visibility.Visible;

    /// <summary>冲突区可见性（有冲突→Visible;无→Collapsed)。</summary>
    public System.Windows.Visibility HasConflictsVisibility
        => Conflicts.Count > 0 ? System.Windows.Visibility.Visible : System.Windows.Visibility.Collapsed;

    /// <summary>依赖列表（API 返回的 required_items;行 VM=DependsRow)。</summary>
    public ObservableCollection<DependsRow> DependencyRows { get; } = new();

    /// <summary>冲突列表（本地规则检测；空=无冲突）。</summary>
    public ObservableCollection<ConflictRow> Conflicts { get; } = new();

    // ---- D5.20b:真实物品 id 关联（Browse→Detail 传参） ----
    private PublishedFileId? _currentId;

    /// <summary>评论列表（社区页解析；空=无评论/解析为空）。</summary>
    public ObservableCollection<WorkshopComment> Comments { get; } = new();

    /// <param name="navigateToDownloads">入队后跳下载页回调。</param>
    /// <param name="api">Web API 元数据源（null=未装配→错误态，不造假）。</param>
    /// <param name="community">D2.5 社区回退源（可选）。</param>
    /// <param name="comments">评论源（可选；共享 community-detail 节流桶）。</param>
    public ModDetailPageViewModel(
        IPathService paths,
        IDownloadQueue queue,
        DownloadsPageViewModel downloads,
        IDownloadProvider provider,
        DownloadScheduler scheduler,
        Action? navigateToDownloads = null,
        ISteamWebApiClient? api = null,
        ICommunitySource? community = null,
        ICommentSource? comments = null)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _queue = queue ?? throw new ArgumentNullException(nameof(queue));
        _downloads = downloads ?? throw new ArgumentNullException(nameof(downloads));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _scheduler = scheduler ?? throw new ArgumentNullException(nameof(scheduler));
        _navigateToDownloads = navigateToDownloads;
        _api = api;
        _community = community;
        _comments = comments;

        Title = "示例 mod · Workshop Download Demo";
        Dependencies = new List<string> { "前置依赖示例 A", "前置依赖示例 B" };

        DownloadCommand = new RelayCommand(async () => await DownloadAsync(), () => true);
        ReloadCommand = new RelayCommand(async () => await LoadDetailAsync(),
            () => !IsLoading);
    }

    /// <summary>加载详情（API→社区回退→评论；失败=整页错误态）。</summary>
    /// <param name="id">要加载的工坊物品 id（默认=当前关联 id 或示例物品 17906)。</param>
    public async Task LoadDetailAsync(ulong? id = null)
    {
        if (_api is null)
        {
            ErrorMessage = "元数据源未装配（API 通道缺失）";
            return;
        }
        IsLoading = true;
        ErrorMessage = string.Empty;
        try
        {
            // D5.20b:显式 id→关联（转非示例态）；未传=当前 id 或示例兜底
            if (id.HasValue)
                CurrentId = new PublishedFileId(id.Value);
            var pubId = CurrentId ?? new PublishedFileId(17906UL);
            var apiResult = await _api.GetPublishedFileDetailsAsync(pubId)
                .ConfigureAwait(true);
            if (!apiResult.IsOk || apiResult.Value is null)
            {
                ErrorMessage = $"详情加载失败：API {apiResult.Error}";
                return;
            }

            var item = apiResult.Value;
            Item = item;

            // 验收①:依赖来自 API(required_items 直显）
            DependenciesSource = item.Dependencies.Count > 0 ? "API" : "API（无前置）";
            DependencyRows.Clear();
            foreach (var dep in item.Dependencies)
                DependencyRows.Add(new DependsRow(dep));

            // 验收②:字段缺失→社区回退；缺失即"字段缺失"诚实标注
            DescriptionSource = MarkSource(item.Description);
            CreatorSource = MarkSource(item.Creator);
            PreviewSource = MarkSource(item.PreviewUrl);

            if (HasMissingFields(item) && _community is not null)
            {
                try
                {
                    var enriched = await _community.EnrichDetailAsync(pubId).ConfigureAwait(true);
                    if (enriched.IsOk && enriched.Value is not null)
                    {
                        var e = enriched.Value;
                        item = item with
                        {
                            Creator = item.Creator ?? e.Creator,
                            Description = item.Description ?? e.Description,
                            PreviewUrl = item.PreviewUrl ?? e.PreviewUrl,
                        };
                        Item = item;
                        // 字段被回退填充→来源改标"社区回退"（未填到=保持"字段缺失"）
                        CreatorSource = item.Creator is not null && CreatorSource == "字段缺失"
                            ? "社区回退" : CreatorSource;
                        DescriptionSource = item.Description is not null && DescriptionSource == "字段缺失"
                            ? "社区回退" : DescriptionSource;
                        PreviewSource = item.PreviewUrl is not null && PreviewSource == "字段缺失"
                            ? "社区回退" : PreviewSource;
                    }
                }
                catch
                {
                    // 社区回退异常=不覆盖主数据（来源保持"字段缺失"诚实）
                }
            }

            RaisePropertyChanged(nameof(ItemTitle));
            RaisePropertyChanged(nameof(ItemCreator));
            RaisePropertyChanged(nameof(ItemDescription));

            // 冲突检测（本地规则：自引用+重复；两层循环=一次 batch)
            await DetectConflictsAsync(item).ConfigureAwait(true);

            // 评论区（失败=状态文本诚实降级，不污染主数据）
            await LoadCommentsAsync(pubId).ConfigureAwait(true);
        }
        catch (Exception ex)
        {
            ErrorMessage = $"详情加载异常：{ex.GetType().Name}";
        }
        finally
        {
            IsLoading = false;
        }
    }

    private static string MarkSource(string? value)
        => string.IsNullOrWhiteSpace(value) ? "字段缺失" : "API";

    private static bool HasMissingFields(WorkshopItem item)
        => string.IsNullOrWhiteSpace(item.Description)
           || string.IsNullOrWhiteSpace(item.Creator)
           || string.IsNullOrWhiteSpace(item.PreviewUrl);

    /// <summary>冲突检测：自引用/重复（本地同步）;两层循环（batch API 查依赖的依赖）。</summary>
    private async Task DetectConflictsAsync(WorkshopItem item)
    {
        Conflicts.Clear();
        var deps = item.Dependencies;
        if (deps.Count == 0)
            return;

        // 自引用
        if (deps.Contains(item.Id))
            Conflicts.Add(new ConflictRow(item.Id, "自引用：物品依赖自身"));

        // 重复依赖
        var dupIds = deps.GroupBy(d => d.Value).Where(g => g.Count() > 1).Select(g => g.Key);
        foreach (var dup in dupIds)
            Conflicts.Add(new ConflictRow(new(dup), "重复依赖：同一前置出现多次"));

        // 两层循环：任一依赖的依赖回指本物品（batch 一次查，≤30 条防爆请求）
        if (_api is not null && deps.Count <= 30)
        {
            try
            {
                var batch = await _api.GetPublishedFileDetailsBatchAsync(deps)
                    .ConfigureAwait(true);
                if (batch.IsOk && batch.Value is not null)
                {
                    foreach (var dep in batch.Value)
                    {
                        if (dep.Dependencies.Contains(item.Id))
                            Conflicts.Add(new ConflictRow(dep.Id,
                                $"循环依赖：{dep.Id.Value} 的前置回指本物品"));
                    }
                }
            }
            catch
            {
                // 循环检测网络失败=不阻塞展示（主依赖已显）
            }
        }
    }

    /// <summary>
    /// D5.20b:Browse 项点击导航入口——关联真实工坊物品 id 并立即触发加载
    /// （自动 LoadDetailAsync:API→社区回退→评论+冲突检测）。页面导航前调用，
    /// 页面 Loaded 见 CurrentId 已加载则不重复请求（重试纽走 ReloadCommand)。
    /// </summary>
    public async Task TryLoadAsync(PublishedFileId id)
    {
        ArgumentNullException.ThrowIfNull(id);
        CurrentId = id; // 立即转非示例态（banner 消失）
        await LoadDetailAsync(id.Value).ConfigureAwait(true);
    }

    /// <summary>评论区加载（失败=状态文本降级，不抛到整页）。</summary>
    private async Task LoadCommentsAsync(PublishedFileId id)
    {
        if (_comments is null)
        {
            CommentsStatus = "评论源未装配";
            return;
        }
        CommentsStatus = "评论加载中…";
        try
        {
            var result = await _comments.GetCommentsAsync(id).ConfigureAwait(true);
            Comments.Clear();
            if (!result.IsOk)
            {
                CommentsStatus = result.Error switch
                {
                    SteamError.RateLimited => "评论区暂时不可达（限流）",
                    SteamError.Blocked => "评论区被阻止（403)",
                    SteamError.Network => "评论区不可达（网络）",
                    _ => "评论区加载失败",
                };
                return;
            }
            foreach (var c in result.Value!)
                Comments.Add(c);
            CommentsStatus = Comments.Count > 0
                ? $"{Comments.Count} 条评论"
                : "暂无评论";
        }
        catch
        {
            CommentsStatus = "评论区加载失败";
        }
    }

    private async Task DownloadAsync()
    {
        // 优先加载到的真实物品；未加载=示例物品（D3.5b 契约不变）
        var app = Item?.AppId ?? new AppId(4000);
        var title = Item?.Title ?? Title;
        var item = new WorkshopItem(Item?.Id ?? new PublishedFileId(17906), app, title)
        {
            FileSize = Item?.FileSize, // 总字节未知时 null → UI 诚实 N/A（D3.2 契约）
        };

        var task = new DownloadTask(DownloadTaskId.New(), item, app, _paths.WorkshopContent(app))
        {
            Provider = DownloadProvider.SteamCmd, // D3.5 链路由
            TotalBytes = item.FileSize,
        };

        await _queue.EnqueueAsync(task).ConfigureAwait(false);

        // 行注册（UI 线程：ObservableCollection.Add)
        var row = new DownloadTaskRowViewModel(task, _provider, _scheduler);
        System.Windows.Application.Current?.Dispatcher.Invoke(() => _downloads.RegisterRow(row));

        _navigateToDownloads?.Invoke();
    }

    /// <summary>依赖行（id 直显；t2 §2.5 页面语义）。</summary>
    public sealed record DependsRow(PublishedFileId Id)
    {
        public string Display => Id.Value.ToString();
    }

    /// <summary>冲突行（冲突原因直显；1.x 冲突展示契约）。</summary>
    public sealed record ConflictRow(PublishedFileId Id, string Reason)
    {
        public string Display => $"{Id.Value} · {Reason}";
    }
}
