using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Providers;
using Swdm2.Downloads.Queue;
using Swdm2.Steam.Community;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.UiTests.Tests.ModDetail;

/// <summary>
/// D5.20b(t63) ModDetail 真实 id 接线验收：
/// - TryLoad(PublishedFileId)=关联真实物品+自动 LoadDetailAsync（标题/作者/描述/依赖真实）
/// - sample 兜底显式标注：未关联 id 且未加载成功=IsSampleMode（banner 可见）
/// - 重试/重载走 CurrentId（Browse 传入 id 不回退示例值）
/// 用户反馈"详情页通篇编号种类，无标题无详情"整改的回归闸门。
/// </summary>
public sealed class ModDetailTryLoadTests
{
    public ModDetailTryLoadTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private sealed class RecordingApi : ISteamWebApiClient
    {
        private readonly WorkshopItem _item;
        public List<PublishedFileId>Requested { get; } = new();

        public RecordingApi(WorkshopItem item) => _item = item;

        public Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(
            PublishedFileId id, CancellationToken ct = default)
        {
            Requested.Add(id);
            return Task.FromResult(Result<WorkshopItem, SteamError>.Ok(_item));
        }

        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
            IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default)
            => Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(Array.Empty<WorkshopItem>()));

        public Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(
            PublishedFileId collectionId, CancellationToken ct = default)
            => Task.FromResult(Result<CollectionDetails, SteamError>.Fail(SteamError.NotFound));
    }

    private static ModDetailPageViewModel NewVm(ISteamWebApiClient? api)
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        var bus = new DownloadEventBus(100);
        var downloads = new DownloadsPageViewModel(bus);
        var provider = new DownloadProviderRouter(
            new StubProvider(), new StubProvider(), bus);
        var scheduler = new DownloadScheduler(new DownloadQueue(), (e, ct) => Task.FromResult(true), 1);
        return new ModDetailPageViewModel(paths, new DownloadQueue(), downloads,
            provider, scheduler, navigateToDownloads: null, api);
    }

    private static ModDetailPageViewModel NewVm(ISteamWebApiClient? api, ICommunitySource? community)
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        var bus = new DownloadEventBus(100);
        var downloads = new DownloadsPageViewModel(bus);
        var provider = new DownloadProviderRouter(
            new StubProvider(), new StubProvider(), bus);
        var scheduler = new DownloadScheduler(new DownloadQueue(), (e, ct) => Task.FromResult(true), 1);
        return new ModDetailPageViewModel(paths, new DownloadQueue(), downloads,
            provider, scheduler, navigateToDownloads: null, api, community);
    }

    private sealed class StubProvider : IDownloadProvider
    {
        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct) => Task.FromResult(true);
        public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
    }

    [WpfFact]
    public void Before_Any_Load_Sample_Mode_Banner_Visible()
    {
        var vm = NewVm(null); // API 未装配也能构造（示例态）

        Assert.True(vm.IsSampleMode);
        Assert.Null(vm.CurrentId);
        Assert.Null(vm.Item);
    }

    [WpfFact]
    public async Task Try_Load_Sets_Real_Id_And_Exits_Sample_Mode()
    {
        var item = new WorkshopItem(new(555), new(4000), "真实 Mod 标题")
        {
            Description = "真实描述",
            Creator = "真实作者",
            Dependencies = new[] { new PublishedFileId(777) },
        };
        var api = new RecordingApi(item);
        var vm = NewVm(api);

        await vm.TryLoadAsync(new PublishedFileId(555));

        Assert.Equal(new PublishedFileId(555), vm.CurrentId);
        Assert.False(vm.IsSampleMode); // banner 消失
        Assert.NotNull(vm.Item);
        Assert.Equal("真实 Mod 标题", vm.ItemTitle);
        Assert.Equal("真实作者", vm.ItemCreator);
        Assert.Equal("真实描述", vm.ItemDescription);
        Assert.Equal("API", vm.DependenciesSource);
        Assert.Single(vm.DependencyRows);
        Assert.Equal(777UL, vm.DependencyRows[0].Id.Value);
        Assert.Equal(new PublishedFileId(555), api.Requested[0]); // 拉的是传入 id
    }

    [WpfFact]
    public async Task Reload_After_Try_Load_Uses_CurrentId_Not_Sample_Fallback()
    {
        var item = new WorkshopItem(new(555), new(4000), "真实标题");
        var api = new RecordingApi(item);
        var vm = NewVm(api);
        await vm.TryLoadAsync(new PublishedFileId(555));

        await vm.LoadDetailAsync(); // 无参重载=重载当前 id

        Assert.Equal(2, api.Requested.Count);
        Assert.All(api.Requested, id => Assert.Equal(555UL, id.Value));
        Assert.False(vm.IsSampleMode);
    }

    [WpfFact]
    public async Task Try_Load_Failure_Keeps_Honest_Error_State()
    {
        var vm = NewVm(new FailApi());
        await vm.TryLoadAsync(new PublishedFileId(555));

        Assert.Equal(new PublishedFileId(555), vm.CurrentId);
        Assert.False(vm.IsSampleMode); // 已关联真实 id=非示例（载失败≠示例）
        Assert.Null(vm.Item);
        Assert.Contains("详情加载失败", vm.ErrorMessage); // 整页错误态+可重试
    }

    private sealed class FailApi : ISteamWebApiClient
    {
        public Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(
            PublishedFileId id, CancellationToken ct = default)
            => Task.FromResult(Result<WorkshopItem, SteamError>.Fail(SteamError.AuthRequired)); // 401 同款
        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
            IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default)
            => Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(Array.Empty<WorkshopItem>()));
        public Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(
            PublishedFileId collectionId, CancellationToken ct = default)
            => Task.FromResult(Result<CollectionDetails, SteamError>.Fail(SteamError.NotFound));
    }

    /// <summary>社区源桩（D10.1/t70 断点②:API 401→社区整体回退）。</summary>
    private sealed class StubCommunity : ICommunitySource
    {
        private readonly WorkshopItem? _item;
        private readonly SteamError _error;
        public List<PublishedFileId> Requested { get; } = new();

        public StubCommunity(WorkshopItem? item, SteamError error = SteamError.None)
        {
            _item = item;
            _error = error;
        }

        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> BrowseAsync(
            AppId appId, CancellationToken ct = default)
            => Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(Array.Empty<WorkshopItem>()));

        public Task<Result<WorkshopItem, SteamError>> EnrichDetailAsync(
            PublishedFileId id, CancellationToken ct = default)
        {
            Requested.Add(id);
            return _item is null || _error != SteamError.None
                ? Task.FromResult(Result<WorkshopItem, SteamError>.Fail(_error == SteamError.None ? SteamError.Network : _error))
                : Task.FromResult(Result<WorkshopItem, SteamError>.Ok(_item));
        }
    }

    /// <summary>D10.1/t70 断点②：API 401=社区详情整体回退（真实标题，非 demo 兜底）。</summary>
    [WpfFact]
    public async Task Api_Failure_Falls_Back_To_Community_Detail()
    {
        var community = new StubCommunity(new WorkshopItem(new(555), new(4000), "社区真实标题")
        {
            Creator = "社区作者",
            PreviewUrl = "https://cdn/preview.jpg",
        });
        var vm = NewVm(new FailApi(), community);

        await vm.TryLoadAsync(new PublishedFileId(555));

        Assert.False(vm.IsSampleMode);
        Assert.NotNull(vm.Item);
        Assert.Equal("社区真实标题", vm.ItemTitle); // 非"示例 mod · Workshop Download Demo"
        Assert.Equal("社区作者", vm.ItemCreator);
        Assert.Equal("社区回退", vm.CreatorSource);
        Assert.Equal("社区回退", vm.PreviewSource);
        Assert.Equal("字段缺失", vm.DescriptionSource); // 社区不解析描述=诚实标注
        Assert.Equal("社区（无依赖解析）", vm.DependenciesSource);
        Assert.Empty(vm.ErrorMessage);
    }

    /// <summary>API 与社区双失败=双原因合计错误态（不静默不 sample 兜底）。</summary>
    [WpfFact]
    public async Task Api_And_Community_Both_Fail_Shows_Combined_Error()
    {
        var vm = NewVm(new FailApi(), new StubCommunity(null));

        await vm.TryLoadAsync(new PublishedFileId(555));

        Assert.Null(vm.Item);
        Assert.Contains("详情加载失败", vm.ErrorMessage);
        Assert.Contains("社区回退", vm.ErrorMessage);
    }
}
