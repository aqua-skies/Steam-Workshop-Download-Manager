using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Queue;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// D5.20b(t63) 浏览页条目级动作验收：
/// - 「详情」命令=传条目（含真实物品 id）到 openDetail（→ MainShell NavigateToModDetail(id))
/// - 「下载」命令=条目→DownloadTask→IDownloadQueue 入队（契约不变）+行注册+跳转回调
/// - 未注入动作=命令禁用（禁用≠死钮；独立页/设计期不禁用契约）
/// 用户反馈"下载 mod 连下载按钮都没有"整改的回归闸门。
/// </summary>
public sealed class WorkshopBrowseItemActionsTests
{
    public WorkshopBrowseItemActionsTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private sealed class StubQueue : IDownloadQueue
    {
        public List<DownloadTask> Enqueued { get; } = new();
        public int PendingCount => Enqueued.Count;
        public ValueTask<DownloadTaskEntry> EnqueueAsync(DownloadTask task, CancellationToken ct = default)
        {
            Enqueued.Add(task);
            return ValueTask.FromResult(new DownloadTaskEntry(task));
        }
        public ValueTask RequeueAsync(DownloadTaskEntry entry, CancellationToken ct = default) => ValueTask.CompletedTask;
        public bool TryDequeue(out DownloadTaskEntry? entry) { entry = null; return false; }
        public IAsyncEnumerable<DownloadTaskEntry> ReadAllAsync(CancellationToken ct = default)
        {
            return ReadAllCore(ct);
            static async IAsyncEnumerable<DownloadTaskEntry> ReadAllCore(
                [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct)
            { await Task.CompletedTask; yield break; }
        }
        public DownloadTaskEntry? GetEntry(DownloadTaskId id) => null;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private static WorkshopBrowseItem Item(long id = 100001) =>
        WorkshopBrowseItem.SampleData(1)[0] with { Id = id };

    [WpfFact]
    public void Commands_Disabled_When_Actions_Not_Injected()
    {
        var vm = new WorkshopBrowsePageViewModel(WorkshopBrowseItem.SampleData(10));

        Assert.False(vm.OpenItemDetailCommand.CanExecute(null));
        Assert.False(vm.DownloadItemCommand.CanExecute(null));
    }

    [WpfFact]
    public void Open_Detail_Command_Passes_Item_To_Navigation()
    {
        WorkshopBrowseItem? passed = null;
        var vm = new WorkshopBrowsePageViewModel(
            new[] { Item(100001) },
            openDetail: item => passed = item,
            downloadTaskFactory: null, queue: null,
            downloads: null, provider: null, scheduler: null,
            navigateToDownloads: null);

        Assert.True(vm.OpenItemDetailCommand.CanExecute(null));
        vm.OpenItemDetailCommand.Execute(Item(100001));

        Assert.NotNull(passed);
        Assert.Equal(100001L, passed!.Id); // 真实物品 id 传到导航（→PublishedFileId)
    }

    [WpfFact]
    public async Task Download_Item_Command_Enqueues_Task_With_Item_Data()
    {
        var queue = new StubQueue();
        var navigated = false;
        var vm = new WorkshopBrowsePageViewModel(
            new[] { Item(100001) },
            openDetail: null,
            downloadTaskFactory: item =>
            {
                var app = item.AppId ?? new AppId(4000);
                var workshopItem = new WorkshopItem(new PublishedFileId((ulong)item.Id), app, item.Title);
                return new DownloadTask(DownloadTaskId.New(), workshopItem, app, $"C:/w/{app.Value}")
                {
                    Provider = DownloadProvider.SteamCmd,
                };
            },
            queue: queue,
            downloads: null, provider: null, scheduler: null,
            navigateToDownloads: () => navigated = true);

        Assert.True(vm.DownloadItemCommand.CanExecute(null));
        vm.DownloadItemCommand.Execute(Item(100001));
        // 异步命令完成（RelayCommand async;等一拍）
        await Task.Delay(50);

        Assert.Single(queue.Enqueued);
        var task = queue.Enqueued[0];
        Assert.Equal(100001UL, task.Item.Id.Value);
        Assert.Equal(4000, task.Item.AppId.Value);
        Assert.Equal(DownloadProvider.SteamCmd, task.Provider);
        Assert.True(navigated); // 入队后跳下载页（同详情页旅程）
    }

    [WpfFact]
    public void Actions_Null_Constructors_Keep_Page_Standalone()
    {
        // 独立页（WorkshopBrowsePage.xaml.cs 默认装配）保持可构造
        var vm = new WorkshopBrowsePageViewModel(
            new[] { Item(100001) },
            openDetail: null, downloadTaskFactory: null, queue: null,
            downloads: null, provider: null, scheduler: null,
            navigateToDownloads: null);

        Assert.Equal(1, vm.SourceCount);
        Assert.False(vm.OpenItemDetailCommand.CanExecute(null));
        Assert.False(vm.DownloadItemCommand.CanExecute(null));
    }
}
