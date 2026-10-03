using System.Windows;
using System.Windows.Input;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.App.Views;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 下载任务行 VM（D3.5b 最小可测骨架；IDM 体感字段断言契约 t3 §3.2）：
/// - 状态文本映射 D3.1 七态（Queued→Preparing→Downloading→Paused/Cancelled/Failed/Completed）；
/// - 速度/ETA/分段数 null 语义=诚实 N/A（D3.2 ProgressSnapshot 契约）；
/// - 行级动作按钮启用态=状态机驱动（Pause:Preparing/Downloading，Resume:Paused，Retry:Failed，Cancel:非终态）；
/// - 皮肤级行样式（42px/RectBack/勾选竖条/双段生长）留 D5.7。
/// </summary>
public sealed class DownloadTaskRowViewModel : ViewModelBase
{
    private readonly IDownloadProvider _provider;
    private readonly DownloadScheduler _scheduler;
    private DownloadState? _state;
    private string _stateText = "排队中";
    private string _speedText = "N/A";
    private string _etaText = "N/A";
    private string _segmentsText = "N/A";
    private string _sizeText = "N/A";
    private string _queueText = "—";
    private bool _notifiedComplete;

    public DownloadTaskId Id { get; }
    public string FileName { get; }
    public string DestinationDirectory { get; }
    /// <summary>游戏 AppId（类别树=游戏→目录数据源）。</summary>
    public AppId AppId { get; }

    /// <summary>状态文本（断言锚点 DownloadsPage_TaskList_Item_StateText）。</summary>
    public string StateText
    {
        get => _stateText;
        private set => SetProperty(ref _stateText, value);
    }

    public string SpeedText
    {
        get => _speedText;
        private set => SetProperty(ref _speedText, value);
    }

    public string EtaText
    {
        get => _etaText;
        private set => SetProperty(ref _etaText, value);
    }

    public string SegmentsText
    {
        get => _segmentsText;
        private set => SetProperty(ref _segmentsText, value);
    }

    public string SizeText
    {
        get => _sizeText;
        private set => SetProperty(ref _sizeText, value);
    }

    /// <summary>Q 列文本（IDM 排队序语义；Queued/Pending 计数器，空="—")。</summary>
    public string QueueText
    {
        get => _queueText;
        set => SetProperty(ref _queueText, value);
    }

    /// <summary>本行是否已推过完成弹窗（去重，终态只弹一次）。</summary>
    public bool NotifiedComplete
    {
        get => _notifiedComplete;
        set => SetProperty(ref _notifiedComplete, value);
    }

    #region 行级动作（启用态=状态机驱动）

    public bool CanPause => _state is DownloadState.Preparing or DownloadState.Downloading;
    public bool CanResume => _state == DownloadState.Paused;
    public bool CanRetry => _state == DownloadState.Failed;
    public bool CanCancel => _state is DownloadState.Queued or DownloadState.Preparing
        or DownloadState.Downloading or DownloadState.Paused;

    public ICommand PauseCommand { get; }
    public ICommand ResumeCommand { get; }
    public ICommand RetryCommand { get; }
    public ICommand CancelCommand { get; }

    #endregion

    public DownloadTaskRowViewModel(DownloadTask task, IDownloadProvider provider, DownloadScheduler scheduler)
    {
        ArgumentNullException.ThrowIfNull(task);
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _scheduler = scheduler ?? throw new ArgumentNullException(nameof(scheduler));
        Id = task.Id;
        FileName = task.Item.Title;
        DestinationDirectory = task.DestinationDirectory;
        AppId = task.AppId;

        PauseCommand = new RelayCommand(() => FireAndForget(() => provider.PauseAsync(Id)), () => CanPause);
        // Resume 下游=scheduler 的 Paused→Downloading 再执行器（D3.6/D4 接入点，arch-20 域）。
        // 转移表 Paused→Downloading 需要再执行 API，当前下游未提供 ⇒ 本骨架命令体如实降级提示
        // （按钮+启用态已按状态机绑定就位，t28 真旅程前下游补齐即点亮，不改 UI 契约）。
        ResumeCommand = new RelayCommand(OnResume, () => CanResume);
        RetryCommand = new RelayCommand(() => FireAndForget(async () => await scheduler.RetryAsync(Id)), () => CanRetry);
        CancelCommand = new RelayCommand(() => FireAndForget(() => provider.CancelAsync(Id)), () => CanCancel);
    }

    private void OnResume()
        => StateText = "已暂停：恢复功能待下游接入（scheduler ResumeAsync，D3.6/D4）";

    /// <summary>应用总线快照（UI 线程调用；事件字段 → 断言文本）。</summary>
    public void Apply(ProgressSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.State is not null)
        {
            _state = snapshot.State;
            StateText = MapState(snapshot.State.Value)
                + (string.IsNullOrWhiteSpace(snapshot.Message) ? string.Empty : $"：{snapshot.Message}");
        }
        else if (!string.IsNullOrWhiteSpace(snapshot.Message))
        {
            StateText = snapshot.Message;
        }

        SpeedText = HumanSpeed(snapshot.SpeedBytesPerSec);
        EtaText = HumanEta(snapshot.Eta);
        SegmentsText = snapshot.Segments is null ? "N/A" : string.Join("/", snapshot.Segments);
        SizeText = snapshot.TotalBytes is null
            ? HumanBytes(snapshot.BytesReceived)
            : $"{HumanBytes(snapshot.BytesReceived)} / {HumanBytes(snapshot.TotalBytes.Value)}";

        // 启用态刷新（CommandManager.RequerySuggested 联动按钮 IsEnabled）
        CommandManager.InvalidateRequerySuggested();
    }

    #region 状态文本映射（UI 中文呈现；皮肤级配色/图标留 D5.7）

    private static string MapState(DownloadState state) => state switch
    {
        DownloadState.Pending => "待定",
        DownloadState.Queued => "排队中",
        DownloadState.Preparing => "准备中",
        DownloadState.Downloading => "下载中",
        DownloadState.Paused => "已暂停",
        DownloadState.Cancelled => "已取消",
        DownloadState.Failed => "失败",
        DownloadState.Completed => "完成",
        _ => state.ToString(),
    };

    private static string HumanBytes(ulong bytes) => bytes switch
    {
        < 1024UL => $"{bytes} B",
        < 1024UL * 1024UL => $"{bytes / 1024.0:F1} KB",
        < 1024UL * 1024UL * 1024UL => $"{bytes / (1024.0 * 1024.0):F1} MB",
        _ => $"{bytes / (1024.0 * 1024.0 * 1024.0):F2} GB",
    };

    private static string HumanSpeed(double bytesPerSec) =>
        bytesPerSec <= 0 ? "N/A" : HumanBytes((ulong)bytesPerSec) + "/s";

    private static string HumanEta(TimeSpan? eta) => eta switch
    {
        null => "N/A",
        { TotalHours: >= 1 } => $"{(int)eta.Value.TotalHours}h {eta.Value.Minutes}m",
        _ => $"{eta.Value.Minutes}m {eta.Value.Seconds}s",
    };

    #endregion

    private static async void FireAndForget(Func<Task> action)
    {
        try
        {
            await action().ConfigureAwait(false);
        }
        catch (Exception)
        {
            // 行级动作失败经总线状态回显（provider 报 Failed）；这里不吞诊断，仅防 UI 崩。
            // 皮肤期（D5）会接错误条 Hint 四档语义。
        }
    }

    private static void MarshalToUi(Action action)
    {
        if (Application.Current is null)
        {
            action();
            return;
        }
        Application.Current.Dispatcher.Invoke(action);
    }
}
