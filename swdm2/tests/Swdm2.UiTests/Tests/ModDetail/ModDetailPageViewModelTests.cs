using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.Community;
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
/// D5.6 mod 详情页逻辑层验收（t45):
/// - **依赖来自 API**(①):LoadDetailAsync→ISteamWebApiClient required_items→
///   DependencyRows 直显+DependenciesSource="API" 断言
/// - **诚实降级**（②):API 失败=整页错误态+可重试；字段缺失→来源标注"字段缺失"
///   →社区回退填充后改标"社区回退";回退失败保持"字段缺失"不造假
/// - 冲突检测（自引用/重复/两层循环）
/// - 评论解析器（1.x detail_dialog 正则移植 fixture)
/// 沙箱网络不可达=fixtures 注入桩源（真实网络路径由 D2.5 契约测试覆盖）。
/// </summary>
public sealed class ModDetailPageViewModelTests
{
    public ModDetailPageViewModelTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private static ModDetailPageViewModel NewVm(
        ISteamWebApiClient? api,
        ICommunitySource? community = null,
        ICommentSource? comments = null)
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        var bus = new DownloadEventBus(100);
        var downloads = new DownloadsPageViewModel(bus);
        var provider = new DownloadProviderRouter(StubProvider.Instance, StubProvider.Instance, bus);
        var scheduler = new DownloadScheduler(new DownloadQueue(), (e, ct) => Task.FromResult(true), 1);
        return new ModDetailPageViewModel(paths, new DownloadQueue(), downloads,
            provider, scheduler, navigateToDownloads: null,
            api, community, comments);
    }

    /// <summary>验收①:依赖列表来自 Web API(required_items 直显）。</summary>
    [WpfFact]
    public async Task Dependencies_Come_From_Web_Api()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "Test Mod")
        {
            Description = "desc",
            Creator = "author",
            PreviewUrl = "https://x/p.png",
            Dependencies = new[] { new PublishedFileId(111), new PublishedFileId(222) },
        });
        var vm = NewVm(api);

        await vm.LoadDetailAsync();

        Assert.Equal("API", vm.DependenciesSource);
        Assert.Equal(2, vm.DependencyRows.Count);
        Assert.Equal(111UL, vm.DependencyRows[0].Id.Value);
        Assert.Equal(222UL, vm.DependencyRows[1].Id.Value);
        Assert.Equal("Test Mod", vm.ItemTitle);
        Assert.Equal("author", vm.ItemCreator);
        Assert.Equal("desc", vm.ItemDescription);
        Assert.Empty(vm.ErrorMessage);
    }

    /// <summary>验收②:API 失败=整页错误态+诚实（不造假）。</summary>
    [WpfFact]
    public async Task Api_Failure_Shows_Page_Error_With_Retry()
    {
        var api = new StubApi(fail: SteamError.Network);
        var vm = NewVm(api);

        await vm.LoadDetailAsync();

        Assert.False(vm.IsLoading);
        Assert.Contains("详情加载失败", vm.ErrorMessage);
        Assert.Equal(Visibility.Visible, vm.HasErrorVisibility);
        Assert.Null(vm.Item);
        Assert.True(vm.ReloadCommand.CanExecute(null)); // 重试入口可用
    }

    /// <summary>验收②:字段缺失→社区回退填充→来源改标"社区回退"。</summary>
    [WpfFact]
    public async Task Missing_Fields_Filled_By_Community_Fallback()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Creator = null, Description = null, PreviewUrl = null,
        });
        var community = new StubCommunity(new WorkshopItem(new(17906), new(4000), "T")
        {
            Creator = "社区作者",
            Description = "社区描述",
            PreviewUrl = "https://x/c.png",
        });
        var vm = NewVm(api, community);

        await vm.LoadDetailAsync();

        Assert.Equal("社区回退", vm.CreatorSource);
        Assert.Equal("社区回退", vm.DescriptionSource);
        Assert.Equal("社区回退", vm.PreviewSource);
        Assert.Equal("社区作者", vm.ItemCreator);
        Assert.Equal("社区描述", vm.ItemDescription);
    }

    /// <summary>验收②:社区回退失败=来源保持"字段缺失"（不造假数据）。</summary>
    [WpfFact]
    public async Task Community_Fallback_Failure_Keeps_Missing_Label()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Creator = null, Description = null, PreviewUrl = null,
        });
        var community = new StubCommunity(fail: SteamError.Network);
        var vm = NewVm(api, community);

        await vm.LoadDetailAsync();

        Assert.Equal("字段缺失", vm.CreatorSource);
        Assert.Equal("字段缺失", vm.DescriptionSource);
        Assert.Equal("未知作者", vm.ItemCreator); // 诚实降级显示
        Assert.Equal("暂无简介", vm.ItemDescription);
    }

    /// <summary>冲突：自引用+重复（本地规则）。</summary>
    [WpfFact]
    public async Task Conflicts_Self_Reference_And_Duplicate_Detected()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Dependencies = new[] { new PublishedFileId(17906), new PublishedFileId(333), new PublishedFileId(333) },
            Description = "d", Creator = "a", PreviewUrl = "u",
        });
        var vm = NewVm(api, comments: new StubComments(Array.Empty<WorkshopComment>()));

        await vm.LoadDetailAsync();

        Assert.Equal(2, vm.Conflicts.Count);
        Assert.Contains(vm.Conflicts, c => c.Display.Contains("自引用"));
        Assert.Contains(vm.Conflicts, c => c.Display.Contains("重复依赖"));
    }

    /// <summary>冲突：两层循环（依赖的依赖回指本物品，batch API 查出）。</summary>
    [WpfFact]
    public async Task Conflict_Circular_Dependency_Detected_Via_Batch()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Dependencies = new[] { new PublishedFileId(111) },
            Description = "d", Creator = "a", PreviewUrl = "u",
        }, batchItems: new[]
        {
            new WorkshopItem(new(111), new(4000), "Dep")
            {
                Dependencies = new[] { new PublishedFileId(17906) }, // 回指=循环
                Description = "d", Creator = "a", PreviewUrl = "u",
            },
        });
        var vm = NewVm(api, comments: new StubComments(Array.Empty<WorkshopComment>()));

        await vm.LoadDetailAsync();

        Assert.Contains(vm.Conflicts, c => c.Display.Contains("循环依赖"));
    }

    /// <summary>评论加载失败=状态文本降级（不污染主数据）。</summary>
    [WpfFact]
    public async Task Comments_Failure_Degrades_To_Status_Text()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Description = "d", Creator = "a", PreviewUrl = "u",
        });
        var vm = NewVm(api, comments: new StubComments(fail: SteamError.RateLimited));

        await vm.LoadDetailAsync();

        Assert.Contains("限流", vm.CommentsStatus);
        Assert.Empty(vm.Comments);
        Assert.Empty(vm.ErrorMessage); // 主数据未受影响
    }

    /// <summary>评论成功=计数+来源。</summary>
    [WpfFact]
    public async Task Comments_Loaded_Counted()
    {
        var api = new StubApi(new WorkshopItem(new(17906), new(4000), "T")
        {
            Description = "d", Creator = "a", PreviewUrl = "u",
        });
        var vm = NewVm(api, comments: new StubComments(new[]
        {
            new WorkshopComment { Author = "A", Time = "2026-01-01 10:00", Content = "hello" },
        }));

        await vm.LoadDetailAsync();

        Assert.Equal("1 条评论", vm.CommentsStatus);
        Assert.Single(vm.Comments); // [arch-20 补] xUnit2013 trivial 修+归属注（t48 warnaserror 门）
    }

    // ---- 评论解析器 fixture（移植 1.x parse_comments 正则行为） ----

    [WpfFact]
    public void Comment_Parser_Parses_Author_Time_Content()
    {
        var html = """
            <div class="commentthread_comment" id="comment_123">
                <a class="commentthread_author_link" href="x"><bdi>Alice</bdi></a>
                <div data-timestamp="1735689600">some date</div>
                <div class="commentthread_comment_text">Nice mod!<br/>Second line</div>
            </div>
            """;
        var comments = CommunityCommentParser.ParseComments(html);
        Assert.Single(comments);
        Assert.Equal(123UL, comments[0].Id);
        Assert.Equal("Alice", comments[0].Author);
        Assert.Contains("2025", comments[0].Time ?? "");
        Assert.Contains("Nice mod!", comments[0].Content);
        Assert.Contains("Second line", comments[0].Content);
    }

    [WpfFact]
    public void Comment_Parser_Empty_Html_Returns_Empty()
    {
        Assert.Empty(CommunityCommentParser.ParseComments(""));
        Assert.Empty(CommunityCommentParser.ParseComments(null));
        Assert.Empty(CommunityCommentParser.ParseComments("<html>no comments</html>"));
    }

    [WpfFact]
    public void Comment_Total_Parses_Head_Count()
    {
        Assert.Equal(42, CommunityCommentParser.CommentTotal(
            "<span id=\"commentthread_Comments_totalcount\">  42</span>"));
        Assert.Equal(0, CommunityCommentParser.CommentTotal(null));
        Assert.Equal(0, CommunityCommentParser.CommentTotal("no counter"));
    }

    [WpfFact]
    public void Description_Parser_Extracts_Rich_Text()
    {
        var html = """
            <div class="workshopItemDescription" id="highlightContent">
                <p>Hello <b>world</b></p>
            </div>
            """;
        var desc = CommunityCommentParser.ParseDescription(html);
        Assert.Contains("Hello <b>world</b>", desc);
        Assert.Equal(string.Empty, CommunityCommentParser.ParseDescription(null));
    }

    // ---- Stubs ----

    private sealed class StubApi : ISteamWebApiClient
    {
        private readonly WorkshopItem? _item;
        private readonly SteamError? _fail;
        private readonly IReadOnlyList<WorkshopItem> _batchItems;

        public StubApi(WorkshopItem item) : this(item, Array.Empty<WorkshopItem>()) { }

        public StubApi(WorkshopItem item, WorkshopItem[] batchItems)
            => (_item, _fail, _batchItems) = (item, null, batchItems);

        public StubApi(SteamError fail) => (_item, _fail, _batchItems) = (null, fail, Array.Empty<WorkshopItem>());

        public Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(
            PublishedFileId id, CancellationToken ct = default)
            => _fail is { } e
                ? Task.FromResult(Result<WorkshopItem, SteamError>.Fail(e))
                : Task.FromResult(Result<WorkshopItem, SteamError>.Ok(_item!));

        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
            IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default)
            => Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(_batchItems));

        public Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(
            PublishedFileId collectionId, CancellationToken ct = default)
            => Task.FromResult(Result<CollectionDetails, SteamError>.Fail(SteamError.NotFound));
    }

    private sealed class StubCommunity : ICommunitySource
    {
        private readonly WorkshopItem? _item;
        private readonly SteamError? _fail;

        public StubCommunity(WorkshopItem item) => _item = item;
        public StubCommunity(SteamError fail) => _fail = fail;

        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> BrowseAsync(
            AppId appId, CancellationToken ct = default)
            => Task.FromResult(Result<IReadOnlyList<WorkshopItem>, SteamError>.Fail(SteamError.Network));

        public Task<Result<WorkshopItem, SteamError>> EnrichDetailAsync(
            PublishedFileId id, CancellationToken ct = default)
            => _fail is { } e
                ? Task.FromResult(Result<WorkshopItem, SteamError>.Fail(e))
                : Task.FromResult(Result<WorkshopItem, SteamError>.Ok(_item!));
    }

    private sealed class StubProvider : IDownloadProvider
    {
        public static readonly StubProvider Instance = new();
        public Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
            => Task.FromResult(true);
        public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
        public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
    }

    private sealed class StubComments : ICommentSource
    {
        private readonly IReadOnlyList<WorkshopComment> _items = Array.Empty<WorkshopComment>();
        private readonly SteamError? _fail;

        public StubComments(IReadOnlyList<WorkshopComment> items) => _items = items;
        public StubComments(SteamError fail) => _fail = fail;

        public Task<Result<IReadOnlyList<WorkshopComment>, SteamError>> GetCommentsAsync(
            PublishedFileId id, CancellationToken ct = default)
            => _fail is { } e
                ? Task.FromResult(Result<IReadOnlyList<WorkshopComment>, SteamError>.Fail(e))
                : Task.FromResult(Result<IReadOnlyList<WorkshopComment>, SteamError>.Ok(_items));
    }
}
