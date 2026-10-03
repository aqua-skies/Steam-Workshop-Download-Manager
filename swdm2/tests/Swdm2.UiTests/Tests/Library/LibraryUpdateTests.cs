using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.Library;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Workshop;
using Xunit;

namespace Swdm2.UiTests.Tests.Library;

/// <summary>
/// t59 D6.2 库页更新检查逻辑层验收：
/// - 检查流（不阻塞主线程的语义=async VM 命令；角标/候选/Hint/行标记）
/// - 失败=错误态诚实降级（不造假候选/角标）
/// - 入队询问才下载（1.x 学费：EnqueueAllUpdates=用户手势；检查本身不入队）
/// - 未知本地时间戳=无候选（checker 诚实规则端到端验证）
/// </summary>
public sealed class LibraryUpdateTests
{
    public LibraryUpdateTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private static readonly PublishedFileId IdA = new(111);
    private static readonly PublishedFileId IdB = new(222);

    private sealed class StubScanner : ILibraryScanner
    {
        private readonly IReadOnlyList<ModLibraryEntry> _entries;
        public StubScanner(IReadOnlyList<ModLibraryEntry> entries) => _entries = entries;
        public Task<IReadOnlyList<ModLibraryEntry>> ScanAsync(CancellationToken ct = default) =>
            Task.FromResult(_entries);
    }

    private sealed class StubUpdateSource : IWorkshopUpdateSource
    {
        private readonly Result<IReadOnlyList<ModUpdateCandidate>, SteamError> _result;
        public int Calls { get; private set; }

        public StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError> result) => _result = result;

        public Task<Result<IReadOnlyList<ModUpdateCandidate>, SteamError>> CheckUpdatesAsync(
            IReadOnlyList<InstalledModSnapshot> installed, CancellationToken ct = default)
        {
            Calls++;
            Assert.All(installed, s => Assert.Null(s.LocalLastUpdatedUtc)); // t51 轻扫=本地未知
            return Task.FromResult(_result);
        }
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
        public IAsyncEnumerable<DownloadTaskEntry> ReadAllAsync(CancellationToken ct = default) =>
            EmptyQueue();
        private static async IAsyncEnumerable<DownloadTaskEntry> EmptyQueue()
        {
            await Task.CompletedTask;
            yield break;
        }
        public DownloadTaskEntry? GetEntry(DownloadTaskId id) => null;
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private static ModUpdateCandidate Candidate(PublishedFileId id, AppId appId, string title)
    {
        var item = new WorkshopItem(id, appId, title);
        return new ModUpdateCandidate(id, item, DateTime.UtcNow, null);
    }

    private static LibraryPageViewModel NewVm(
        IReadOnlyList<ModLibraryEntry> entries,
        StubUpdateSource? source = null,
        StubQueue? queue = null)
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        return new LibraryPageViewModel(new StubScanner(entries), paths, source, queue);
    }

    private static ModLibraryEntry Entry(PublishedFileId id, AppId app, string title, DateTime? updated = null) =>
        new(id, app, title, $"{app.Value}/{id.Value}")
        { ItemLastUpdatedUtc = updated };

    [WpfFact]
    public async Task Check_Updates_Updates_Badge_Hint_Rows()
    {
        var source = new StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError>.Ok(new[]
        {
            Candidate(IdA, new AppId(4000), "Mod A"),
        }));
        var queue = new StubQueue();
        var vm = NewVm(new[]
        {
            Entry(IdA, new AppId(4000), "Mod A"),
            Entry(IdB, new AppId(4000), "Mod B"),
        }, source, queue);

        await vm.LoadAsync();
        await vm.CheckForUpdatesAsync();

        Assert.Equal(1, vm.UpdateCount);
        Assert.True(vm.HasUpdates);
        Assert.Contains("1 个 mod 有更新", vm.UpdateHint);
        Assert.True(vm.HasUpdateHint);
        Assert.Single(vm.UpdateCandidates);
        Assert.True(vm.Rows[0].HasUpdate);  // 行标记
        Assert.False(vm.Rows[1].HasUpdate);
        Assert.Equal(1, source.Calls);
        Assert.Empty(queue.Enqueued); // 1.x 学费：检查本身不入队
    }

    [WpfFact]
    public async Task Check_Updates_Failure_Is_Honest_Not_Fake()
    {
        var source = new StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError>
            .Fail(SteamError.RateLimited));
        var vm = NewVm(new[]
        {
            Entry(IdA, new AppId(4000), "Mod A"),
        }, source);

        await vm.LoadAsync();
        await vm.CheckForUpdatesAsync();

        Assert.Equal(0, vm.UpdateCount);
        Assert.False(vm.HasUpdates);
        Assert.Contains("更新检查失败", vm.UpdateHint);
        Assert.Empty(vm.UpdateCandidates);
        Assert.False(vm.Rows[0].HasUpdate);
    }

    [WpfFact]
    public async Task Check_Updates_No_Updates_Latest_Hint()
    {
        var source = new StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError>
            .Ok(Array.Empty<ModUpdateCandidate>()));
        var vm = NewVm(new[]
        {
            Entry(IdA, new AppId(4000), "Mod A"),
        }, source);

        await vm.LoadAsync();
        await vm.CheckForUpdatesAsync();

        Assert.Equal(0, vm.UpdateCount);
        Assert.Contains("最新", vm.UpdateHint);
    }

    [WpfFact]
    public async Task Empty_Library_Check_Makes_No_Call()
    {
        var source = new StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError>
            .Ok(Array.Empty<ModUpdateCandidate>()));
        var vm = NewVm(Array.Empty<ModLibraryEntry>(), source);

        await vm.LoadAsync();
        Assert.False(vm.CheckForUpdatesCommand.CanExecute(null)); // 空库=命令禁用
    }

    /// <summary>1.x 学费端到端：入队=询问手势（用户点钮），不自动下载。</summary>
    [WpfFact]
    public async Task Enqueue_All_Updates_After_Ask_Gesture()
    {
        var source = new StubUpdateSource(Result<IReadOnlyList<ModUpdateCandidate>, SteamError>.Ok(new[]
        {
            Candidate(IdA, new AppId(4000), "Mod A"),
            Candidate(IdB, new AppId(440), "Mod B"),
        }));
        var queue = new StubQueue();
        var vm = NewVm(new[]
        {
            Entry(IdA, new AppId(4000), "Mod A"),
            Entry(IdB, new AppId(440), "Mod B"),
        }, source, queue);

        await vm.LoadAsync();
        await vm.CheckForUpdatesAsync();
        Assert.Equal(2, vm.UpdateCandidates.Count);

        await vm.EnqueueAllUpdatesAsync();

        Assert.Equal(2, queue.Enqueued.Count);
        Assert.Contains("已加入下载队列", vm.UpdateHint);
        Assert.Equal(0, vm.UpdateCount);
        Assert.Empty(vm.UpdateCandidates);
        Assert.False(vm.Rows[0].HasUpdate); // 角标清零
    }

    /// <summary>未注入更新源/队列时（t51 旧两参构造）=命令禁用，保持开放封闭。</summary>
    [WpfFact]
    public async Task Without_Source_Commands_Disabled()
    {
        var vm = NewVm(new[] { Entry(IdA, new AppId(4000), "Mod A") });
        await vm.LoadAsync();

        Assert.False(vm.CheckForUpdatesCommand.CanExecute(null));
        Assert.False(vm.EnqueueAllUpdatesCommand.CanExecute(null));
    }
}
