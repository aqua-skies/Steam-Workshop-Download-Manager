using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Swdm2.App.Updates;

/// <summary>
/// 升级流程状态机（D6.3;纯逻辑层可测）:
/// Idle → Checking → UpToDate | Available | Error
/// Available → Downloading(progress) → ReadyToApply | Error
/// ReadyToApply → Applied（待重启生效；Velopack 契约=下次 OnStartup 消费）
/// 覆盖安装（IsVelopackInstalled=false)=诚实降级②：状态.OverwriteInstall,
/// UI 引导 Setup/releases 而非自动升级。
/// 不变量：Error 状态保留 Message（不吞异常=诚实）;状态转移单向。
/// </summary>
public sealed class UpdateService : INotifyPropertyChanged
{
    public enum UpdateState
    {
        Idle = 0,
        Checking,
        UpToDate,
        Available,
        Downloading,
        ReadyToApply,
        Applied,
        Error,
        OverwriteInstall, // t58 诚实降级②:覆盖安装非升级路径
    }

    private readonly IUpdateManager _manager;
    private UpdateState _state = UpdateState.Idle;
    private UpdateInfo? _pendingUpdate;
    private string _message = string.Empty;
    private int _downloadProgress;

    public UpdateState State
    {
        get => _state;
        private set { if (SetField(ref _state, value)) RaiseAll(); }
    }

    public UpdateInfo? PendingUpdate
    {
        get => _pendingUpdate;
        private set => SetField(ref _pendingUpdate, value);
    }

    /// <summary>状态/错误消息（Error 时=异常信息；诚实不吞）。</summary>
    public string Message
    {
        get => _message;
        private set => SetField(ref _message, value);
    }

    /// <summary>下载进度 0-100。</summary>
    public int DownloadProgress
    {
        get => _downloadProgress;
        private set => SetField(ref _downloadProgress, value);
    }

    public bool CanCheck => State is UpdateState.Idle or UpdateState.UpToDate
        or UpdateState.Available or UpdateState.Error or UpdateState.OverwriteInstall;

    public bool CanDownload => State == UpdateState.Available && PendingUpdate is not null;

    public bool CanApply => State == UpdateState.ReadyToApply && PendingUpdate is not null;

    public UpdateService(IUpdateManager manager)
    {
        _manager = manager ?? throw new ArgumentNullException(nameof(manager));

        // 覆盖安装=前置降级（不在每次 Check 时才发现）
        if (!_manager.IsVelopackInstalled)
        {
            State = UpdateState.OverwriteInstall;
            Message = "当前为覆盖安装（非 Velopack 升级通道）——自动升级不可用，请用 Setup 或 releases 发布包";
        }
    }

    /// <summary>检查更新（读 feed)。</summary>
    public async Task CheckAsync(CancellationToken ct = default)
    {
        if (!CanCheck) return;
        if (State == UpdateState.OverwriteInstall) return; // 降级路径不检查

        State = UpdateState.Checking;
        Message = string.Empty;
        try
        {
            var info = await _manager.CheckForUpdatesAsync(ct).ConfigureAwait(true);
            if (info is null)
            {
                State = UpdateState.UpToDate;
                Message = "已是最新版本";
            }
            else
            {
                PendingUpdate = info;
                State = UpdateState.Available;
                Message = $"发现新版本 {info.TargetVersion}";
            }
        }
        catch (Exception ex)
        {
            Message = ex.Message; // 网络/feed 读失败=诚实文案，不误读"不可行"
            State = UpdateState.Error;
        }
    }

    /// <summary>下载更新（进度推进）。</summary>
    public async Task DownloadAsync(CancellationToken ct = default)
    {
        if (!CanDownload) return;
        var info = PendingUpdate!;
        State = UpdateState.Downloading;
        DownloadProgress = 0;
        try
        {
            // 同步进度（Progress<T>.Report 在无 SynchronizationContext 的驱动/沙箱
            // 进程会 post 到线程池=断言时序假阴性；Velopack Action<int> 本就是同步回调）
            var progress = new SyncProgress(p => DownloadProgress = p);
            await _manager.DownloadUpdatesAsync(info, progress, ct).ConfigureAwait(true);
            State = UpdateState.ReadyToApply;
            Message = "下载完成，重启后应用";
        }
        catch (Exception ex)
        {
            Message = ex.Message;
            State = UpdateState.Error;
        }
    }

    /// <summary>应用更新（写钩子；下次重启 VelopackApp.Run 消费后升级）。</summary>
    public async Task ApplyAsync(CancellationToken ct = default)
    {
        if (!CanApply) return;
        var info = PendingUpdate!;
        try
        {
            await _manager.ApplyUpdatesAsync(info, ct).ConfigureAwait(true);
            State = UpdateState.Applied; // ApplyUpdatesAndRestart 会请求重启
            Message = "升级已写入，重启生效";
        }
        catch (Exception ex)
        {
            Message = ex.Message;
            State = UpdateState.Error;
        }
    }

    /// <summary>同步 IProgress&lt;int&gt; 实现（调用即更新；无 post 延迟）。</summary>
    private sealed class SyncProgress : IProgress<int>
    {
        private readonly Action<int> _action;
        public SyncProgress(Action<int> action) => _action = action;
        public void Report(int value) => _action(value);
    }

    /// <summary>重置回 Idle（错误后可再检查）。</summary>
    public void Reset() { State = UpdateState.Idle; Message = string.Empty; }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void RaiseAll()
    {
        OnPropertyChanged(nameof(CanCheck));
        OnPropertyChanged(nameof(CanDownload));
        OnPropertyChanged(nameof(CanApply));
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(name);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}