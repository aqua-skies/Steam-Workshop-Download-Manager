using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Windows.Input;
using Swdm2.App.Library;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Workshop;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 库页 VM(D5.12;P0 旅程 5「下载→库」载体；D6.2 更新检查 t59)。
/// 呈现契约：已下载 mod 列表（分类/扫描结果）+打开目录+更新检查（不阻塞主线程）。
/// 数据源=ILibraryScanner（t51 默认 LocalLibraryScanner 轻扫；D6.1 阶段 6
/// 接入真实库管理扫描/导入导出——依赖时延后，本 VM 不变）。
/// 更新检查=IWorkshopUpdateSource（t59 真实实现走 GetPublishedFileDetails 批量链）;
/// **1.x 学费：检查→通知+入队询问，绝不自动下载**（自动更新检查只刷新角标，
/// 下载须用户点「下载全部更新」；弹窗真实阻塞规则在 FlaUI 层处理）。
/// 空库=诚实空态文案，不造假条目（1.x 学费同族）。
/// </summary>
public sealed class LibraryPageViewModel : ViewModelBase
{
    private readonly ILibraryScanner _scanner;
    private readonly IPathService _paths;
    private readonly IWorkshopUpdateSource? _updateSource;
    private readonly IDownloadQueue? _queue;
    private bool _isLoading;
    private bool _isChecking;
    private bool _hasUpdateHint;
    private bool _hasUpdates;
    private int _updateCount;
    private string _updateHint = string.Empty;
    private string _emptyHint = "库为空——下载完成的 mod 会自动出现在这里";
    private LibraryRow? _selectedRow;

    /// <summary>库条目行（标题/AppId/路径/大小/更新标记；分类=按游戏 AppId 分组）。</summary>
    public ObservableCollection<LibraryRow> Rows { get; } = new();

    /// <summary>按游戏分组的分类视图（键=AppId 显示名）。</summary>
    public ObservableCollection<LibraryGroup> Groups { get; } = new();

    /// <summary>更新候选列表（t59;标题+远端时间+差异；深拷贝语义=检查刷新即重建）。</summary>
    public ObservableCollection<ModUpdateCandidate> UpdateCandidates { get; } = new();

    public bool IsLoading
    {
        get => _isLoading;
        private set => SetProperty(ref _isLoading, value);
    }

    /// <summary>更新检查中（异步不阻塞主线程；命令期间禁用）。</summary>
    public bool IsChecking
    {
        get => _isChecking;
        private set => SetProperty(ref _isChecking, value);
    }

    /// <summary>可更新 mod 数（角标 Source;0=无角标）。</summary>
    public int UpdateCount
    {
        get => _updateCount;
        private set
        {
            if (SetProperty(ref _updateCount, value))
                HasUpdates = value > 0;
        }
    }

    /// <summary>更新提示文案（非阻塞 Hint;空串=无更新态）。</summary>
    public string UpdateHint
    {
        get => _updateHint;
        private set
        {
            if (SetProperty(ref _updateHint, value))
                HasUpdateHint = !string.IsNullOrEmpty(value);
        }
    }

    /// <summary>更新提示可见性（bool→Visibility 转换器源。</summary>
    public bool HasUpdateHint
    {
        get => _hasUpdateHint;
        private set => SetProperty(ref _hasUpdateHint, value);
    }

    /// <summary>有更新（角标可见源；UpdateCount&gt;0)。</summary>
    public bool HasUpdates
    {
        get => _hasUpdates;
        private set => SetProperty(ref _hasUpdates, value);
    }

    /// <summary>空态提示（无库条目时；诚实文案）。</summary>
    public string EmptyHint
    {
        get => _emptyHint;
        private set => SetProperty(ref _emptyHint, value);
    }

    public LibraryRow? SelectedRow
    {
        get => _selectedRow;
        set => SetProperty(ref _selectedRow, value);
    }

    public ICommand RefreshCommand { get; }
    public ICommand OpenDirectoryCommand { get; }
    public ICommand CheckForUpdatesCommand { get; }
    public ICommand EnqueueAllUpdatesCommand { get; }

    public LibraryPageViewModel(ILibraryScanner scanner, IPathService paths,
        IWorkshopUpdateSource? updateSource = null, IDownloadQueue? queue = null)
    {
        _scanner = scanner ?? throw new ArgumentNullException(nameof(scanner));
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _updateSource = updateSource;
        _queue = queue;

        RefreshCommand = new RelayCommand(async () => await LoadAsync(), () => !IsLoading);
        OpenDirectoryCommand = new RelayCommand(OpenDirectory, () => SelectedRow is not null);
        CheckForUpdatesCommand = new RelayCommand(async () => await CheckForUpdatesAsync(),
            () => _updateSource is not null && !IsChecking && !IsLoading && Rows.Count > 0);
        EnqueueAllUpdatesCommand = new RelayCommand(async () => await EnqueueAllUpdatesAsync(),
            () => _queue is not null && UpdateCandidates.Count > 0 && !IsChecking);
    }

    /// <summary>
    /// 更新检查（t59;后台线程请求→主线程更新 UI;**不自动下载**——
    /// 仅刷新候选/角标/提示，下载=用户 EnqueueAllUpdates 手势）。
    /// </summary>
    public async Task CheckForUpdatesAsync()
    {
        if (_updateSource is null || IsChecking || Rows.Count == 0)
            return;
        IsChecking = true;
        try
        {
            // 库快照：ItemId+本地基线（ItemLastUpdatedUtc 安装时记录值优先；
            // 缺失=InstalledAtUtc 安装时间兜底——remote 严格新于安装时间才报更新，
            // 免首次全量假更新；D6.1 真扫描接入后两值同源更精确）
            var snapshots = Rows
                .Select(r => new InstalledModSnapshot(
                    new PublishedFileId(ulong.Parse(r.ItemIdText, System.Globalization.CultureInfo.InvariantCulture)),
                    r.ItemLastUpdatedUtc ?? r.InstalledAtUtc))
                .ToList();

            var result = await _updateSource.CheckUpdatesAsync(snapshots)
                .ConfigureAwait(true);
            UpdateCandidates.Clear();
            foreach (var row in Rows)
                row.HasUpdate = false;

            if (!result.IsOk)
            {
                UpdateCount = 0;
                UpdateHint = $"更新检查失败（{result.Error}）——稍后再试";
                return;
            }
            foreach (var c in result.Value!)
            {
                UpdateCandidates.Add(c);
                var row = Rows.FirstOrDefault(r => r.ItemIdText == c.ItemId.Value.ToString(
                    System.Globalization.CultureInfo.InvariantCulture));
                if (row is not null)
                    row.HasUpdate = true;
            }
            UpdateCount = UpdateCandidates.Count;
            UpdateHint = UpdateCount > 0
                ? $"{UpdateCount} 个 mod 有更新（远端版本新于本地）"
                : "全部为最新版本";
        }
        catch (Exception)
        {
            // 诚实降级：检查异常不崩，错误态提示
            UpdateCount = 0;
            UpdateHint = "更新检查失败（网络或数据异常）——稍后再试";
        }
        finally
        {
            IsChecking = false;
            // 命令可用性刷新（CanExecute 依赖 UpdateCandidates/IsChecking)
            System.Windows.Input.CommandManager.InvalidateRequerySuggested();
        }
    }

    /// <summary>
    /// 入队询问后的下载手势（1.x 学费：询问才入队，不自动下载）。
    /// 候选 RemoteItem→DownloadTask→IDownloadQueue（同 t46 下载链）。
    /// </summary>
    public async Task EnqueueAllUpdatesAsync()
    {
        if (_queue is null || UpdateCandidates.Count == 0 || IsChecking)
            return;
        var enqueued = 0;
        foreach (var candidate in UpdateCandidates.ToList())
        {
            var dest = Path.Combine(_paths.SteamCmdDirectory, "steamapps", "workshop",
                "content", candidate.RemoteItem.AppId.Value.ToString(
                    System.Globalization.CultureInfo.InvariantCulture));
            var task = new DownloadTask(
                DownloadTaskId.New(),
                candidate.RemoteItem,
                candidate.RemoteItem.AppId,
                dest);
            await _queue.EnqueueAsync(task).ConfigureAwait(false);
            enqueued++;
        }
        UpdateHint = $"{enqueued} 个更新已加入下载队列（询问后下载，1.x 学费规则）";
        UpdateCandidates.Clear();
        UpdateCount = 0;
        foreach (var row in Rows)
            row.HasUpdate = false;
        System.Windows.Input.CommandManager.InvalidateRequerySuggested();
    }

    /// <summary>加载库（扫描；失败=空态提示带错误信息，不抛）。</summary>
    public async Task LoadAsync()
    {
        IsLoading = true;
        try
        {
            var entries = await _scanner.ScanAsync().ConfigureAwait(true);
            Rows.Clear();
            Groups.Clear();
            foreach (var e in entries)
                Rows.Add(new LibraryRow(e));

            // 分类=按游戏 AppId 分组
            foreach (var g in Rows.GroupBy(r => r.AppIdText)
                         .Select(g => new LibraryGroup(g.Key, g.ToList())))
                Groups.Add(g);

            EmptyHint = Rows.Count > 0
                ? $"{Rows.Count} 个条目 · {Groups.Count} 个游戏"
                : "库为空——下载完成的 mod 会自动出现在这里";
        }
        catch (Exception)
        {
            EmptyHint = "库扫描失败（目录不可读）——请检查库目录权限";
            // 诚实降级：扫描失败不抛到 UI，空态文案说明
        }
        finally
        {
            IsLoading = false;
        }
    }

    private void OpenDirectory()
    {
        if (SelectedRow is null) return;
        var abs = Path.Combine(_paths.SteamCmdDirectory, "steamapps", "workshop",
            "content", SelectedRow.AppIdText, SelectedRow.ItemIdText);
        if (!Directory.Exists(abs))
        {
            EmptyHint = "目录不存在（可能已被移动或删除）";
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo("explorer.exe", abs) { UseShellExecute = true });
        }
        catch (Exception)
        {
            // 打开失败=状态文案（不崩）
            EmptyHint = "打开目录失败（explorer 启动失败）";
        }
    }
}

/// <summary>库行 VM（呈现契约：标题/AppId/路径/大小/更新标记）。</summary>
public sealed class LibraryRow : ViewModelBase
{
    public string Title { get; }
    public string AppIdText { get; }
    public string ItemIdText { get; }
    public string RelativePath { get; }
    public string SizeText { get; }
    public DateTime InstalledAtUtc { get; }

    /// <summary>物品元数据声明的更新时间（t59 更新检查基线；可空）。</summary>
    public DateTime? ItemLastUpdatedUtc { get; }

    private bool _hasUpdate;

    /// <summary>可更新标记（t59 角标/行标记；检查后刷新）。</summary>
    public bool HasUpdate
    {
        get => _hasUpdate;
        set => SetProperty(ref _hasUpdate, value);
    }

    public LibraryRow(ModLibraryEntry entry)
    {
        Title = string.IsNullOrWhiteSpace(entry.Title) ? entry.ItemId.Value.ToString() : entry.Title;
        AppIdText = entry.AppId.Value.ToString();
        ItemIdText = entry.ItemId.Value.ToString();
        RelativePath = entry.RelativePath;
        SizeText = entry.FileSize is null ? "未知" : HumanBytes(entry.FileSize.Value);
        InstalledAtUtc = entry.InstalledAtUtc;
        ItemLastUpdatedUtc = entry.ItemLastUpdatedUtc;
    }

    private static string HumanBytes(ulong bytes) => bytes switch
    {
        < 1024UL => $"{bytes} B",
        < 1024UL * 1024UL => $"{bytes / 1024.0:F1} KB",
        < 1024UL * 1024UL * 1024UL => $"{bytes / (1024.0 * 1024.0):F1} MB",
        _ => $"{bytes / (1024.0 * 1024.0 * 1024.0):F2} GB",
    };

    public override string ToString() => $"{Title} ({AppIdText}/{ItemIdText})";
}

/// <summary>库分类组（按游戏 AppId)。</summary>
public sealed class LibraryGroup
{
    public string AppIdText { get; }
    public IReadOnlyList<LibraryRow> Rows { get; }

    public LibraryGroup(string appIdText, IReadOnlyList<LibraryRow> rows)
    {
        AppIdText = appIdText;
        Rows = rows;
    }
}