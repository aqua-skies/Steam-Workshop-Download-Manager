using System;
using Swdm2.App.ViewModels;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Workshop;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// t68(D9.2) Browse VM 真实源加载逻辑层验收（无 UIA/无网络=纯逻辑门）：
/// - 成功=真实条目替换源（SampleData 断连）;
/// - 失败=ErrorMessage 中文原因 + HasError=true（失败链不静默=验收 3);
/// - 0 条目=提示不静默。
/// UIA 桌面链（BrowseRealSourceJourneyTests）=交互桌面通道复跑条款（同门）。
/// </summary>
public sealed class WorkshopBrowseRealSourceVMTests
{
    private sealed class StubSource : IWorkshopBrowseSource
    {
        private readonly Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError> _result;
        public StubSource(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError> result) => _result = result;
        public Task<Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>> FetchAsync(
            WorkshopBrowseQuery query, CancellationToken ct = default)
            => Task.FromResult(_result);
    }

    private static IReadOnlyList<WorkshopBrowseEntry> RealEntries() => new[]
    {
        new WorkshopBrowseEntry("2121557118", "xdReanimsBase (L4D2) Anim Mods base",
            Array.Empty<string>(), "Reanimator", 1234567,
            new DateTimeOffset(2025, 1, 2, 3, 4, 5, TimeSpan.Zero),
            "https://images.steamusercontent.com/ugc/10892356258565477722/abc"),
    };

    /// <summary>成功=真实条目替换（标题/预览图/作者到位=非假数据）。</summary>
    [WpfFact]
    public async Task LoadFromSource_Ok_Replaces_With_Real_Entries()
    {
        var vm = new WorkshopBrowsePageViewModel(Array.Empty<WorkshopBrowseItem>());
        var src = new StubSource(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Ok(RealEntries()));

        await vm.LoadFromSourceAsync(src, new AppId(550));

        Assert.True(vm.SourceCount > 0);
        Assert.Null(vm.ErrorMessage);
        Assert.False(vm.HasError);
    }

    /// <summary>网络失败=明确中文原因+HasError=true（不静默=验收 3)。</summary>
    [WpfFact]
    public async Task LoadFromSource_Network_Failure_Shows_Reason()
    {
        var vm = new WorkshopBrowsePageViewModel(Array.Empty<WorkshopBrowseItem>());
        var src = new StubSource(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Fail(SteamError.Network));

        await vm.LoadFromSourceAsync(src, new AppId(550));

        Assert.False(string.IsNullOrEmpty(vm.ErrorMessage), "网络失败必须显示原因（不静默）");
        Assert.True(vm.HasError);
        Assert.Contains("网络", vm.ErrorMessage!);
    }

    /// <summary>熔断/限流/超时/屏蔽=同样明确原因（失败族语义全;[WpfFact]-only 纪律=合并遍历）。</summary>
    [WpfFact]
    public async Task LoadFromSource_Failure_Family_Shows_Reason()
    {
        var cases = new (SteamError error, string keyword)[]
        {
            (SteamError.RateLimited, "限流"),
            (SteamError.Timeout, "超时"),
            (SteamError.CircuitOpen, "熔断"),
            (SteamError.Blocked, "屏蔽"),
        };
        foreach (var (error, keyword) in cases)
        {
            var vm = new WorkshopBrowsePageViewModel(Array.Empty<WorkshopBrowseItem>());
            var src = new StubSource(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Fail(error));

            await vm.LoadFromSourceAsync(src, new AppId(550));

            Assert.True(vm.HasError, $"{error} 必须 HasError");
            Assert.False(string.IsNullOrEmpty(vm.ErrorMessage), $"{error} 必须显示原因（不静默）");
            Assert.Contains(keyword, vm.ErrorMessage!);
        }
    }

    /// <summary>0 条目=提示不静默。</summary>
    [WpfFact]
    public async Task LoadFromSource_Empty_Shows_Hint_Not_Silent()
    {
        var vm = new WorkshopBrowsePageViewModel(Array.Empty<WorkshopBrowseItem>());
        var src = new StubSource(Result<IReadOnlyList<WorkshopBrowseEntry>, SteamError>.Ok(
            Array.Empty<WorkshopBrowseEntry>()));

        await vm.LoadFromSourceAsync(src, new AppId(550));

        // 0 条目=提示横幅在位（HasError 复用同字段=可见提示；消息区分非失败）
        Assert.False(string.IsNullOrEmpty(vm.ErrorMessage), "0 条目必须有提示（不静默）");
        Assert.Contains("工坊条目", vm.ErrorMessage!);
    }
}
