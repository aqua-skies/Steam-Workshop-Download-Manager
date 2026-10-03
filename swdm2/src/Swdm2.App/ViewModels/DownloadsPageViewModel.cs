using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Views;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 下载页 VM（D3.5b 骨架 → D5.7 IDM 体感完整版；t46）：
/// - 任务行集合：Rows（全量）→ FilteredRows（类别树过滤视图，ListBox 绑定源）；
/// - 类别树=游戏→目录（DownloadCategoryNode 二级；来自注册行的 AppId/DestinationDirectory）；
/// - 选中行 SelectedRow：工具栏四命令（暂停/继续/重试/取消选中）选中驱动；
/// - 通知：NotificationKind/Message（三档强度）文本**全部来自事件总线 Message**——
///   聚合规则=Failed/Error→Error;限流/429 关键字→Warning;Completed→Success;其余 Info;
///   不编造文本（字段全部来自事件总线的验收条款）；
/// - 行字段六件（速度/ETA/分段数/大小/状态/Q)绑定 ProgressSnapshot（经行 Apply);
/// - steamcmd 场景分段数=null→"N/A"（诚实，行 VM Apply 契约）。
/// </summary>
public sealed class DownloadsPageViewModel : ViewModelBase, IDisposable
{
    private readonly IDownloadEventBus _bus;
    private readonly IDisposable? _subscription;
    private DownloadTaskRowViewModel? _selectedRow;
    private DownloadCategoryNode? _selectedCategory;
    private string _notificationMessage = "下载队列就绪。";
    private HintKind _notificationKind = HintKind.Info;

    public ObservableCollection<DownloadTaskRowViewModel> Rows { get; } = new();
    /// <summary>过滤后行（ListBox 绑定源；全 null=不过滤=全量）。</summary>
    public ObservableCollection<DownloadTaskRowViewModel> FilteredRows { get; } = new();
    /// <summary>类别树根（游戏层）。</summary>
    public ObservableCollection<DownloadCategoryNode> Categories { get; } = new();

    public DownloadTaskRowViewModel? SelectedRow
    {
        get => _selectedRow;
        set
        {
            if (SetProperty(ref _selectedRow, value))
                RefreshToolbar();
        }
    }

    public string NotificationMessage
    {
        get => _notificationMessage;
        private set => SetProperty(ref _notificationMessage, value);
    }

    public HintKind NotificationKind
    {
        get => _notificationKind;
        private set => SetProperty(ref _notificationKind, value);
    }

    #region 工具栏命令（选中行驱动=状态机 CanXxx 联动）

    public ICommand PauseSelectedCommand { get; }
    public ICommand ResumeSelectedCommand { get; }
    public ICommand RetrySelectedCommand { get; }
    public ICommand CancelSelectedCommand { get; }

    #endregion

    public DownloadsPageViewModel(IDownloadEventBus bus)
    {
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
        _subscription = bus.Subscribe(OnSnapshotAsync);

        PauseSelectedCommand = new RelayCommand(
            () => _selectedRow?.PauseCommand.Execute(null), () => _selectedRow?.CanPause ?? false);
        ResumeSelectedCommand = new RelayCommand(
            () => _selectedRow?.ResumeCommand.Execute(null), () => _selectedRow?.CanResume ?? false);
        RetrySelectedCommand = new RelayCommand(
            () => _selectedRow?.RetryCommand.Execute(null), () => _selectedRow?.CanRetry ?? false);
        CancelSelectedCommand = new RelayCommand(
            () => _selectedRow?.CancelCommand.Execute(null), () => _selectedRow?.CanCancel ?? false);
    }

    /// <summary>行 VM 注册（入队即注册；同步刷新类别树+过滤）。</summary>
    public void RegisterRow(DownloadTaskRowViewModel row)
    {
        ArgumentNullException.ThrowIfNull(row);
        Rows.Add(row);
        RebuildCategories();
        ApplyFilter();
    }

    /// <summary>类别树选中（TreeView SelectedItemChanged 路由）。</summary>
    public void SelectCategory(DownloadCategoryNode node)
    {
        ArgumentNullException.ThrowIfNull(node);
        _selectedCategory = node;
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        FilteredRows.Clear();
        var category = _selectedCategory;
        foreach (var row in Rows)
        {
            if (category is null || category.Matches(row))
                FilteredRows.Add(row);
        }
    }

    /// <summary>类别树增量重建（注册行/新目录时调用）。</summary>
    private void RebuildCategories()
    {
        Categories.Clear();
        var games = Rows.GroupBy(r => r.AppId);
        foreach (var game in games.OrderBy(g => g.Key.Value))
        {
            var gameName = GameAliasTable.KnownGames.FirstOrDefault(g => g.Id == game.Key)?.Name
                ?? $"AppId {game.Key.Value}";
            var gameNode = new DownloadCategoryNode(gameName, null, game.Key);
            foreach (var dir in game.GroupBy(r => r.DestinationDirectory)
                .Select(g => g.Key).Distinct().OrderBy(d => d))
            {
                gameNode.Children.Add(new DownloadCategoryNode(
                    System.IO.Path.GetFileName(dir), dir, game.Key));
            }
            Categories.Add(gameNode);
        }
        ApplyFilter();
    }

    private void RefreshToolbar()
    {
        System.Windows.Input.CommandManager.InvalidateRequerySuggested();
    }

    private async Task OnSnapshotAsync(ProgressSnapshot snapshot)
    {
        var row = Rows.FirstOrDefault(r => r.Id == snapshot.TaskId);
        if (row is null)
            return;

        // 线程模型：总线投递在后台线程（Timer/ThreadPool)，UI 更新必须 marshal；
        // 驱动/无 Application 上下文（WpfFact 无 Application.Current)直接执行=测试可测+真 App 仍走 Dispatcher。
        if (Application.Current is not null)
            Application.Current.Dispatcher.Invoke(() => ApplySnapshot(row, snapshot));
        else
            ApplySnapshot(row, snapshot);

        if (snapshot.State == DownloadState.Completed)
        {
            Application.Current?.Dispatcher.Invoke(() =>
            {
                if (row.NotifiedComplete) return;
                row.NotifiedComplete = true;
                var dialog = new DownloadCompleteDialog
                {
                    TaskTitle = row.FileName,
                    ProductPath = row.DestinationDirectory,
                };
                dialog.ShowDialog();
            });
        }

        await Task.CompletedTask;
    }

    /// <summary>应用快照到 UI 状态（Dispatcher 上下文内或驱动直执行）。</summary>
    private void ApplySnapshot(DownloadTaskRowViewModel row, ProgressSnapshot snapshot)
    {
        row.Apply(snapshot);

        // Q 列=排队序（Queued/Pending 计数器；IDM Q 列语义）
        var queueIndex = 0;
        foreach (var r in Rows)
        {
            if (ReferenceEquals(r, row)) break;
            queueIndex++;
        }
        row.QueueText = row.StateText.StartsWith("排队中") || row.StateText.StartsWith("待定")
            ? $"Q{queueIndex + 1}" : "—";

        // 三档通知（文本=总线 Message;不编造）
        NotificationMessage = string.IsNullOrWhiteSpace(snapshot.Message)
            ? row.StateText : snapshot.Message;
        NotificationKind = MapNotificationKind(row, snapshot);
    }

    /// <summary>三档通知映射（Error>Warning>Success>Info 优先级）。</summary>
    private static HintKind MapNotificationKind(DownloadTaskRowViewModel row, ProgressSnapshot snapshot)
    {
        if (snapshot.State == DownloadState.Failed) return HintKind.Error;
        var message = snapshot.Message ?? string.Empty;
        if (message.Contains("429") || message.Contains("限流") || message.Contains("RateLimited")
            || message.Contains("频繁") || message.Contains("403"))
            return HintKind.Warning;
        if (snapshot.State == DownloadState.Completed) return HintKind.Success;
        return HintKind.Info;
    }

    public void Dispose()
    {
        _subscription?.Dispose();
    }
}

/// <summary>类别树节点（游戏层→目录层）。</summary>
public sealed class DownloadCategoryNode
{
    public string Display { get; }
    public string? Directory { get; }
    public AppId AppId { get; }
    public IList<DownloadCategoryNode> Children { get; } = new List<DownloadCategoryNode>();

    public DownloadCategoryNode(string display, string? directory, AppId appId)
    {
        Display = display;
        Directory = directory;
        AppId = appId;
    }

    /// <summary>行是否属于本节点（游戏层=AppId 匹配；目录层=AppId+目录双匹配）。</summary>
    public bool Matches(DownloadTaskRowViewModel row)
    {
        if (row.AppId != AppId) return false;
        return Directory is null || row.DestinationDirectory == Directory;
    }
}
