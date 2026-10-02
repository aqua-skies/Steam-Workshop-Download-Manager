using System.Collections.ObjectModel;
using System.Windows;
using Swdm2.App.Views;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 下载页 VM（D3.5b 最小骨架）：
/// - 任务行集合绑定 DownloadsPage_TaskList_Items（ListBox）；
/// - 订阅 D3.2 事件总线（节流后快照=不可变 ProgressSnapshot）→ UI 线程 marshal 后应用到行 VM；
/// - Completed（终态）→ 完成弹窗（#255 路径：OkButton 自绘 Window），终态每行只弹一次；
/// - 沙箱/不可达环境任务会走 Failed（真实链路状态回显=状态可断言）——不造假，t28 桌面绿灯。
/// </summary>
public sealed class DownloadsPageViewModel : ViewModelBase, IDisposable
{
    private readonly IDownloadEventBus _bus;
    private readonly IDisposable? _subscription;

    public ObservableCollection<DownloadTaskRowViewModel> Rows { get; } = new();

    public DownloadsPageViewModel(IDownloadEventBus bus)
    {
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
        _subscription = bus.Subscribe(OnSnapshotAsync);
    }

    /// <summary>行 VM 注册（入队即注册；行=状态机可断言载体）。</summary>
    public void RegisterRow(DownloadTaskRowViewModel row)
    {
        ArgumentNullException.ThrowIfNull(row);
        Rows.Add(row);
    }

    private async Task OnSnapshotAsync(ProgressSnapshot snapshot)
    {
        var row = Rows.FirstOrDefault(r => r.Id == snapshot.TaskId);
        if (row is null)
            return;

        // 线程模型：总线投递在后台线程（Timer/ThreadPool），UI 更新必须 marshal。
        Application.Current?.Dispatcher.Invoke(() => row.Apply(snapshot));

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

    public void Dispose()
    {
        _subscription?.Dispose();
    }
}
