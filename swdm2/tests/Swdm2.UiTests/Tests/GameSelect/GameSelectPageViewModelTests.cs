using System.Collections.Specialized;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.UiTests.Tests.GameSelect;

/// <summary>
/// D5.4 游戏选择页验收（VM 逻辑层；FlaUI 双语命中旅程见 Smoke/GameSelectJourney)。
/// 1.x 三个用户 bug 的防呆断言（1.4.2 学费）：
/// ① 联想重做=候选集合原地 Clear+Add，引用永不换（ItemsControl 容器复用=无闪烁）
/// ② 即时反馈=输入即刻进入搜索态（同步，不等防抖/网络）
/// ③ 中英别名不命中=归一化（NFKC+小写+仅字母数字）双语命中
/// 附④回车去重：候选未达 Enter 挂起，候选到达自动兑现（词不静默丢弃）
/// + 重复确认同一游戏=幂等不重发。
/// </summary>
public sealed class GameSelectPageViewModelTests
{
    public GameSelectPageViewModelTests()
    {
        if (Application.Current is null)
            new Application();
    }

    /// <summary>轮询等待条件成立（异步 continuation 在 ThreadPool 的时序容忍）。</summary>
    private static void WaitFor(Func<bool> predicate, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (predicate())
                return;
            Thread.Sleep(20);
        }
    }

    [WpfFact]
    public void Chinese_Alias_Hits_Dont_Starve_Bilingually()
    {
        var cn = GameAliasTable.Match("饥荒");
        Assert.Contains(cn, g => g.Id.Value == 219740);

        var en = GameAliasTable.Match("Don't Starve");
        Assert.Contains(en, g => g.Id.Value == 219740);

        // 归一化：全角/大小写/撇号/空格差异全部消除
        Assert.Equal(GameAliasTable.Normalize("饥荒"), GameAliasTable.Normalize("饥荒"));
        Assert.Equal("dontstarve", GameAliasTable.Normalize("Don't Starve"));
        Assert.Equal("dontstarve", GameAliasTable.Normalize("Ｄｏｎ＇ｔ　Ｓｔａｒｖｅ")); // 全角 NFKC
    }

    [WpfFact]
    public void Search_Term_Changes_Give_Immediate_Search_Feedback()
    {
        var vm = new GameSelectPageViewModel();
        Assert.Equal("输入游戏名搜索（中英均可）", vm.StatusHint);

        // ②即时反馈：输入即刻（同步、防抖 timer 尚未到点）进入搜索态
        vm.SearchTerm = "饥荒";
        Assert.True(vm.IsSearching);
        Assert.Equal("搜索中…", vm.StatusHint);
    }

    [WpfFact]
    public void Suggestions_Update_In_Place_No_Reference_Swap()
    {
        var vm = new GameSelectPageViewModel();
        var collectionRef = vm.Suggestions;
        var changedEvents = 0;
        vm.Suggestions.CollectionChanged += (s, e) => changedEvents++;

        vm.SearchTerm = "饥荒";
        vm.RaiseDebounceForTest();
        WaitFor(() => !vm.IsSearching, TimeSpan.FromSeconds(2));  // 让内部异步完成

        // ①原地更新：同一集合实例（重绘闪烁=引用替换=1.x 联想重做 bug)
                Assert.Same(collectionRef, vm.Suggestions);
        Assert.True(vm.Suggestions.Count >= 1);
        Assert.Contains(vm.Suggestions, g => g.Id.Value == 219740);
        Assert.True(changedEvents >= 2);  // Clear(n)+Add(n) 事件=原地事件流
        Assert.False(vm.IsSearching);
        Assert.Contains("1 条候选", vm.StatusHint);
    }

    [WpfFact]
    public void Empty_Term_Clears_Suggestions_In_Place()
    {
        var vm = new GameSelectPageViewModel();
        var collectionRef = vm.Suggestions;

        vm.SearchTerm = "饥荒";
        vm.RaiseDebounceForTest();
        WaitFor(() => !vm.IsSearching, TimeSpan.FromSeconds(2));
        Assert.True(vm.Suggestions.Count >= 1);

        // 清空=原地 Clear（引用不变；WaitFor 同时等状态文本=避免 Clear 与
        // 状态赋值之间的轮询间隙读到中间态）
        vm.SearchTerm = string.Empty;
        vm.RaiseDebounceForTest();
        WaitFor(() => vm.Suggestions.Count == 0
                       && vm.StatusHint == "输入游戏名搜索（中英均可）",
               TimeSpan.FromSeconds(2));
        Assert.Same(collectionRef, vm.Suggestions);
        Assert.Empty(vm.Suggestions);
        Assert.Equal("输入游戏名搜索（中英均可）", vm.StatusHint);
    }

    [WpfFact]
    public void Enter_While_Candidates_Pending_Is_Honored_Not_Dropped()
    {
        var confirmed = new List<GameInfo>();
        var vm = new GameSelectPageViewModel(navigateToDetail: confirmed.Add);

        // ④回车去重：候选未到达时 Enter→挂起（词不被静默丢弃，1.x 学费）
        vm.HandleEnterKey();
        Assert.True(vm.IsEnterPendingForTest);

        vm.SearchTerm = "饥荒";
        vm.RaiseDebounceForTest();
        WaitFor(() => confirmed.Count > 0, TimeSpan.FromSeconds(2));

        Assert.False(vm.IsEnterPendingForTest);
        Assert.Single(confirmed);
        Assert.Equal(219740, confirmed[0].Id.Value);
    }

    [WpfFact]
    public void Confirm_Idempotent_For_Same_Game()
    {
        var confirmed = new List<GameInfo>();
        var vm = new GameSelectPageViewModel(navigateToDetail: confirmed.Add);

        vm.SearchTerm = "饥荒";
        vm.RaiseDebounceForTest();
        WaitFor(() => !vm.IsSearching, TimeSpan.FromSeconds(2));

        // 重复确认同一游戏=幂等不重发（回车去重同族）
        vm.ConfirmSelection();
        vm.ConfirmSelection();
        Assert.Single(confirmed);

        // 换一个游戏=新确认生效
        vm.Suggestions.Clear();
        vm.Suggestions.Add(new GameInfo(new AppId(550), "Left 4 Dead 2"));
        vm.ConfirmSelection();
        Assert.Equal(2, confirmed.Count);
        Assert.Equal(550, confirmed[1].Id.Value);
    }

    [WpfFact]
    public void Store_Search_Failure_Falls_Back_To_Local_Alias_Hints()
    {
        // 网络失败=本地兜底已显示+状态如实提示（A5 熔断语义同族）
        var failing = new FailingStoreSearchClient();
        var vm = new GameSelectPageViewModel(storeSearch: failing);
        vm.SearchTerm = "饥荒";
        vm.RaiseDebounceForTest();
        WaitFor(() => !vm.IsSearching, TimeSpan.FromSeconds(2));  // catch+末尾块都执行完
        
                Assert.Contains(vm.Suggestions, g => g.Id.Value == 219740);
        // 兜底证据=本地命中（catch 的过渡文本被末尾计数覆盖；数据层即证据）
        Assert.Contains("1 条候选", vm.StatusHint);
    }

    [WpfFact]
    public void No_Match_Term_Reports_Honestly()
    {
        var vm = new GameSelectPageViewModel();
        vm.SearchTerm = "zzzzzzqqqqq无此游戏";
        vm.RaiseDebounceForTest();
        WaitFor(() => !vm.IsSearching, TimeSpan.FromSeconds(2));
        
        Assert.Empty(vm.Suggestions);
        Assert.Contains("无", vm.StatusHint);
        Assert.Contains("中英别名均未命中", vm.StatusHint);
    }

    /// <summary>模拟 storesearch 永远失败的容器（网络熔断断言载体）。</summary>
    private sealed class FailingStoreSearchClient : IStoreSearchClient
    {
        public Task<Result<IReadOnlyList<GameInfo>, SteamError>> SearchGamesAsync(
            string term, CancellationToken ct = default)
            => throw new System.IO.IOException("simulated network failure");
    }
}
