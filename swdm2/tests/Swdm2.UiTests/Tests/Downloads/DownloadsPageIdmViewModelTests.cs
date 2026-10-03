using Swdm2.App.Ui.Controls;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;
using Xunit;

namespace Swdm2.UiTests.Tests.Downloads;

/// <summary>
/// D5.7(t46) 下载页 IDM 体感完整版 VM 逻辑测试（离线、确定性）:
/// - 类别树=游戏→目录（分组/显示名匹配 GameAliasTable 兜底 AppId);
/// - 类别选中→FilteredRows 过滤（游戏层/目录层/清除）;
/// - Q 列=排队序（Queued/Pending →Q1/Q2…;活跃/终态→"—");
/// - 三档通知（HintKind):Failed→Error,429/限流关键字→Warning,Completed→Success,其余 Info;
///   通知消息文本全部来自总线 ProgressSnapshot.Message/状态映射（不编造）;
/// - 选中行驱动工具栏命令 CanExecute=行状态机联动;
/// - steamcmd 场景 Segments=null→"N/A"（诚实，行 VM Apply 契约回归）。
/// 依赖注入：假 provider/scheduler（复用 t38 旅程桩模式）。
/// </summary>
public sealed class DownloadsPageIdmViewModelTests
{
    private static readonly AppId GameDontStarve = new(219740);
    private static readonly AppId GameGmod = new(4000);

    private sealed class FakeProvider : Swdm2.Downloads.Providers.IDownloadProvider
    {
        public Task PauseAsync(DownloadTaskId id) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId id) => Task.CompletedTask;
        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
            => Task.FromResult(true);
    }

    private static DownloadTaskRowViewModel MakeRow(AppId app, string dir, string title)
    {
        var item = new WorkshopItem(new PublishedFileId(1), app, title);
        var task = new Core.Domain.DownloadTask(
            new DownloadTaskId(Guid.NewGuid()), item, app, dir);
        return new DownloadTaskRowViewModel(task, new FakeProvider(), MakeScheduler());
    }

    private static DownloadsPageViewModel MakeVm(params DownloadTaskRowViewModel[] rows)
    {
        var vm = new DownloadsPageViewModel(new DownloadEventBus(1));
        foreach (var row in rows) vm.RegisterRow(row);
        return vm;
    }


    private static DownloadScheduler MakeScheduler()
        => new DownloadScheduler(new DownloadQueue(), (_, _) => Task.FromResult(true), 1);

    [WpfFact]
    public void Category_Tree_Groups_By_Game_Then_Directory()
    {
        var vm = MakeVm(
            MakeRow(GameDontStarve, @"C:\games\dst\mods", "饥荒 mod A"),
            MakeRow(GameDontStarve, @"C:\games\dst\mods", "饥荒 mod B"),
            MakeRow(GameDontStarve, @"C:\games\dst\other", "饥荒 mod C"),
            MakeRow(GameGmod, @"C:\games\gmod\addons", "gmod addon"));

        Assert.Equal(2, vm.Categories.Count);
        // 按 AppId.Value 排序：GMod(4000) < Don't Starve(219740)
        var first = vm.Categories[0];
        Assert.Equal("Garry's Mod", first.Display);
        Assert.Single(first.Children);
        Assert.Equal("addons", first.Children[0].Display);
        var second = vm.Categories[1];
        Assert.Equal("Don't Starve", second.Display);
        Assert.Equal(2, second.Children.Count);
        Assert.Equal("mods", second.Children[0].Display);
        Assert.Equal("other", second.Children[1].Display);
    }

    [WpfFact]
    public void Category_Unknown_Game_Falls_Back_To_AppId()
    {
        var unknownApp = new AppId(999999);
        var vm = MakeVm(MakeRow(unknownApp, @"C:\x\y", "unknown"));

        Assert.Single(vm.Categories);
        Assert.Equal("AppId 999999", vm.Categories[0].Display);
    }

    [WpfFact]
    public void Category_Select_Game_Filters_Rows()
    {
        var rowA = MakeRow(GameDontStarve, @"C:\a", "A");
        var rowB = MakeRow(GameGmod, @"C:\b", "B");
        var vm = MakeVm(rowA, rowB);

        vm.SelectCategory(vm.Categories.Single(c => c.AppId == GameGmod));

        Assert.Single(vm.FilteredRows);
        Assert.Same(rowB, vm.FilteredRows[0]);
    }

    [WpfFact]
    public void Category_Select_Directory_Filters_To_Game_Plus_Dir()
    {
        var mods = MakeRow(GameDontStarve, @"C:\a\mods", "A");
        var other = MakeRow(GameDontStarve, @"C:\a\other", "B");
        var vm = MakeVm(mods, other);

        var gameNode = vm.Categories[0];
        var modsNode = gameNode.Children.Single(c => c.Display == "mods");
        vm.SelectCategory(modsNode);

        Assert.Single(vm.FilteredRows);
        Assert.Same(mods, vm.FilteredRows[0]);
    }

    [WpfFact]
    public async Task Notification_Text_Comes_From_Event_Bus_Message()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var row = MakeRow(GameDontStarve, @"C:\a", "A");
        vm.RegisterRow(row);

        await bus.ReportProgressAsync(row.Id, 100, 1000, DownloadState.Downloading,
            message: "正在下载", segments: new[] { 1, 2, 3, 4 });

        Assert.Equal("正在下载", vm.NotificationMessage);
        Assert.Equal(HintKind.Info, vm.NotificationKind);
    }

    [WpfFact]
    public async Task Notification_Three_Tiers_Map_By_State_And_Message()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var row = MakeRow(GameDontStarve, @"C:\a", "A");
        vm.RegisterRow(row);

        await bus.ReportProgressAsync(row.Id, 0, null, DownloadState.Failed, segments: null, message: "下载失败");
        await WaitForFlush(bus);
        Assert.Equal(HintKind.Error, vm.NotificationKind);

        await bus.ReportProgressAsync(row.Id, 10, 100, DownloadState.Downloading, segments: null, message: "HTTP 429 限流");
        await WaitForFlush(bus);
        Assert.Equal(HintKind.Warning, vm.NotificationKind);

        await bus.ReportProgressAsync(row.Id, 100, 100, DownloadState.Completed, segments: null, message: "下载完成");
        await WaitForFlush(bus);
        Assert.Equal(HintKind.Success, vm.NotificationKind);
    }

    /// <summary>等节流窗（1ms)+timer 刷新到尾帧（≥30ms 让 FlushPending 拿到最新 pending)。</summary>
    private static async Task WaitForFlush(DownloadEventBus bus)
    {
        await Task.Delay(35);
    }

    [WpfFact]
    public async Task Queue_Text_Ranks_Queued_Rows_Ordinal()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var rowA = MakeRow(GameDontStarve, @"C:\a", "A");
        var rowB = MakeRow(GameDontStarve, @"C:\a", "B");
        vm.RegisterRow(rowA);
        vm.RegisterRow(rowB);

        await bus.ReportProgressAsync(rowA.Id, 0, null, DownloadState.Queued);
        await bus.ReportProgressAsync(rowB.Id, 0, null, DownloadState.Queued);

        Assert.Equal("Q1", rowA.QueueText);
        Assert.Equal("Q2", rowB.QueueText);
    }

    [WpfFact]
    public async Task Queue_Text_Active_Or_Terminal_Is_Dash()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var row = MakeRow(GameDontStarve, @"C:\a", "A");
        vm.RegisterRow(row);

        await bus.ReportProgressAsync(row.Id, 10, 100, DownloadState.Downloading, segments: null, message: null);

        Assert.Equal("—", row.QueueText);
    }

    /// <summary>steamcmd 场景（provider 单段）分段数字段=诚实 N/A。</summary>
    [WpfFact]
    public async Task Steamcmd_Single_Segment_Fields_Honest_NA()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var row = MakeRow(GameDontStarve, @"C:\a", "A");
        vm.RegisterRow(row);

        // steamcmd 场景=single segments=null（无分段元数据）
        await bus.ReportProgressAsync(row.Id, 10, 100, DownloadState.Downloading, segments: null, message: null);

        Assert.Equal("N/A", row.SegmentsText);
    }

    [WpfFact]
    public async Task Toolbar_Commands_CanExecute_From_Selected_Row_State_Machine()
    {
        var bus = new DownloadEventBus(1);
        var vm = new DownloadsPageViewModel(bus);
        var row = MakeRow(GameDontStarve, @"C:\a", "A");
        vm.RegisterRow(row);

        // 未选中=全部禁用
        Assert.False(vm.PauseSelectedCommand.CanExecute(null));

        vm.SelectedRow = row;

        await ReportAndWait(bus, row.Id, 10, 100, DownloadState.Downloading);
        Assert.True(vm.PauseSelectedCommand.CanExecute(null));
        Assert.True(vm.CancelSelectedCommand.CanExecute(null));
        Assert.False(vm.ResumeSelectedCommand.CanExecute(null));
        Assert.False(vm.RetrySelectedCommand.CanExecute(null));

        await ReportAndWait(bus, row.Id, 10, 100, DownloadState.Paused);
        Assert.False(vm.PauseSelectedCommand.CanExecute(null));
        Assert.True(vm.ResumeSelectedCommand.CanExecute(null));

        await ReportAndWait(bus, row.Id, 10, 100, DownloadState.Failed);
        Assert.True(vm.RetrySelectedCommand.CanExecute(null));

        await ReportAndWait(bus, row.Id, 100, 100, DownloadState.Completed);
        Assert.False(vm.CancelSelectedCommand.CanExecute(null));
    }

    /// <summary>上报+等节流窗刷新（避免快照被 1ms 节流吃掉中间帧）。</summary>
    private static async Task ReportAndWait(DownloadEventBus bus, DownloadTaskId id, ulong bytes, ulong? total, DownloadState state)
    {
        await bus.ReportProgressAsync(id, bytes, total, state, segments: null, message: null);
        await Task.Delay(35);
    }
}
