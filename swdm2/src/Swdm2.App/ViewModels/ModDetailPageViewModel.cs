using System.Windows.Input;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;

namespace Swdm2.App.ViewModels;

/// <summary>
/// mod 详情页 VM（D3.5b 最小骨架）：
/// - 示例数据（D3.7 前置可点击载体；真实元数据从 D5.4/D5.6 检索链接入）；
/// - 下载命令=真实入队（IDownloadQueue.EnqueueAsync → 队列自动 Pending→Queued → 调度器/provider 真链）；
/// - 入队成功 → 行注册到下载页 VM + 导航到下载页（#10 旅程：任务行出现）。
/// </summary>
public sealed class ModDetailPageViewModel : ViewModelBase
{
    private readonly IPathService _paths;
    private readonly IDownloadQueue _queue;
    private readonly DownloadsPageViewModel _downloads;
    private readonly IDownloadProvider _provider;
    private readonly DownloadScheduler _scheduler;
    private readonly Action? _navigateToDownloads;

    public string Title { get; }
    public IReadOnlyList<string> Dependencies { get; }

    public ICommand DownloadCommand { get; }

    /// <param name="rowFactory">测试可注入的行 VM 工厂（默认构造用 provider/scheduler 由 DownloadsViewModel 装配）。</param>
    public ModDetailPageViewModel(
        IPathService paths,
        IDownloadQueue queue,
        DownloadsPageViewModel downloads,
        IDownloadProvider provider,
        DownloadScheduler scheduler,
        Action? navigateToDownloads = null)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _queue = queue ?? throw new ArgumentNullException(nameof(queue));
        _downloads = downloads ?? throw new ArgumentNullException(nameof(downloads));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _scheduler = scheduler ?? throw new ArgumentNullException(nameof(scheduler));
        _navigateToDownloads = navigateToDownloads;

        Title = "示例 mod · Workshop Download Demo";
        Dependencies = new List<string> { "前置依赖示例 A", "前置依赖示例 B" };

        DownloadCommand = new RelayCommand(async () => await DownloadAsync(), () => true);
    }

    private async Task DownloadAsync()
    {
        // 示例物品（1.x 学费锚点：sub17906/app4000 匿名下载可行）
        var app = new AppId(4000);
        var item = new WorkshopItem(new PublishedFileId(17906), app, Title)
        {
            FileSize = null, // 总字节未知 → UI 诚实 N/A（D3.2 契约）
        };

        var task = new DownloadTask(DownloadTaskId.New(), item, app, _paths.WorkshopContent(app))
        {
            Provider = DownloadProvider.SteamCmd, // D3.5 链路由
            TotalBytes = item.FileSize,
        };

        await _queue.EnqueueAsync(task).ConfigureAwait(false);

        // 行注册（UI 线程：ObservableCollection.Add）
        var row = new DownloadTaskRowViewModel(task, _provider, _scheduler);
        System.Windows.Application.Current?.Dispatcher.Invoke(() => _downloads.RegisterRow(row));

        _navigateToDownloads?.Invoke();
    }
}
