using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Swdm2.Steam.Workshop;
using Xunit;

namespace Swdm2.Steam.Tests.Workshop;

/// <summary>
/// t59 D6.2 更新检查器验收（stub ISteamWebApiClient;离线逻辑层）：
/// - 批量时间戳对比（远端新→候选；旧/同→无；本地未知=诚实不报）
/// - 缺失 id 跳过；空输入直返；分块多请求；失败传播 Result Fail
/// 弹性链（指纹头/Api 桶/熔断）在 apiClient 内=SteamWebApiClientTests 覆盖，此处桩注入。
/// </summary>
[Trait("Category", "WorkshopUpdate")]
public sealed class WorkshopUpdateCheckerTests
{
    private static readonly PublishedFileId IdA = new(1001);
    private static readonly PublishedFileId IdB = new(1002);
    private static readonly PublishedFileId IdC = new(1003);

    private sealed class StubApiClient : ISteamWebApiClient
    {
        private readonly Result<IReadOnlyList<WorkshopItem>, SteamError> _result;
        public List<IReadOnlyList<PublishedFileId>> Calls { get; } = new();

        public StubApiClient(Result<IReadOnlyList<WorkshopItem>, SteamError> result) => _result = result;

        public Task<Result<IReadOnlyList<WorkshopItem>, SteamError>> GetPublishedFileDetailsBatchAsync(
            IReadOnlyList<PublishedFileId> ids, CancellationToken ct = default)
        {
            Calls.Add(ids);
            return Task.FromResult(_result);
        }

        public Task<Result<WorkshopItem, SteamError>> GetPublishedFileDetailsAsync(
            PublishedFileId id, CancellationToken ct = default) =>
            throw new NotSupportedException("更新检查只走批量端点");

        public Task<Result<CollectionDetails, SteamError>> GetCollectionDetailsAsync(
            PublishedFileId collectionId, CancellationToken ct = default) =>
            throw new NotSupportedException();
    }

    private static WorkshopItem Item(PublishedFileId id, DateTime updated) => new(
        id: id, appId: new AppId(4000), title: $"mod-{id.Value}")
    { LastUpdatedUtc = updated };

    private static Result<IReadOnlyList<WorkshopItem>, SteamError> OkBatch(params WorkshopItem[] items) =>
        Result<IReadOnlyList<WorkshopItem>, SteamError>.Ok(items);

    [Fact]
    public async Task Remote_Newer_Than_Local_Produces_Candidate()
    {
        var remote = new DateTime(2026, 10, 1, 12, 0, 0, DateTimeKind.Utc);
        var local = remote.AddDays(-2);
        var stub = new StubApiClient(OkBatch(Item(IdA, remote)));
        var checker = new WorkshopUpdateChecker(stub);

        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, local),
        });

        Assert.True(result.IsOk);
        var c = Assert.Single(result.Value!);
        Assert.Equal(IdA, c.ItemId);
        Assert.Equal(remote, c.RemoteLastUpdatedUtc);
        Assert.Equal(local, c.LocalLastUpdatedUtc);
        Assert.NotNull(c.RemoteItem);
    }

    [Fact]
    public async Task Local_Equal_Or_Newer_Produces_Nothing()
    {
        var t = new DateTime(2026, 10, 1, 12, 0, 0, DateTimeKind.Utc);
        var stub = new StubApiClient(OkBatch(Item(IdA, t)));
        var checker = new WorkshopUpdateChecker(stub);

        var same = await checker.CheckUpdatesAsync(new[] { new InstalledModSnapshot(IdA, t) });
        Assert.True(same.IsOk);
        Assert.Empty(same.Value!);

        var newer = await checker.CheckUpdatesAsync(
            new[] { new InstalledModSnapshot(IdA, t.AddMinutes(1)) });
        Assert.True(newer.IsOk);
        Assert.Empty(newer.Value!);
    }

    /// <summary>本地时间戳未知（t51 轻扫现状）=诚实不报假更新（1.x 学费对照）。</summary>
    [Fact]
    public async Task Unknown_Local_Timestamp_Not_Reported_Honestly()
    {
        var remote = new DateTime(2026, 10, 1, 12, 0, 0, DateTimeKind.Utc);
        var stub = new StubApiClient(OkBatch(Item(IdA, remote)));
        var checker = new WorkshopUpdateChecker(stub);

        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, null), // 本地未知
        });
        Assert.True(result.IsOk);
        Assert.Empty(result.Value!); // 宁可漏不谎报
    }

    /// <summary>远端不返回该 id（或端点无此条目）=缺失跳过。</summary>
    [Fact]
    public async Task Id_Not_In_Response_Skipped()
    {
        var stub = new StubApiClient(OkBatch(Item(IdC, DateTime.UtcNow)));
        var checker = new WorkshopUpdateChecker(stub);
        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, DateTime.UtcNow.AddDays(-5)),
            new InstalledModSnapshot(IdB, DateTime.UtcNow.AddDays(-5)),
        });
        Assert.True(result.IsOk);
        Assert.Empty(result.Value!);
    }

    [Fact]
    public async Task Empty_Input_Returns_Empty_Without_Call()
    {
        var stub = new StubApiClient(OkBatch());
        var checker = new WorkshopUpdateChecker(stub);
        var result = await checker.CheckUpdatesAsync(Array.Empty<InstalledModSnapshot>());
        Assert.True(result.IsOk);
        Assert.Empty(result.Value!);
        Assert.Empty(stub.Calls);
    }

    [Fact]
    public async Task Batching_Chunks_At_BatchSize()
    {
        var remote = DateTime.UtcNow;
        var stub = new StubApiClient(OkBatch(Item(IdA, remote), Item(IdB, remote)));
        var checker = new WorkshopUpdateChecker(stub, batchSize: 1);

        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, remote.AddDays(-1)),
            new InstalledModSnapshot(IdB, remote.AddDays(-1)),
        });

        Assert.True(result.IsOk);
        Assert.Equal(2, stub.Calls.Count);
        Assert.Single(stub.Calls[0]);
        Assert.Single(stub.Calls[1]);
        Assert.Equal(2, result.Value!.Count);
    }

    [Fact]
    public async Task Failure_Propagates_As_Fail()
    {
        var stub = new StubApiClient(Result<IReadOnlyList<WorkshopItem>, SteamError>
            .Fail(SteamError.RateLimited));
        var checker = new WorkshopUpdateChecker(stub);
        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, DateTime.UtcNow.AddDays(-5)),
        });
        Assert.False(result.IsOk);
        Assert.Equal(SteamError.RateLimited, result.Error);
    }

    [Fact]
    public async Task Mixed_Batch_Only_Newer_Reported()
    {
        var t = new DateTime(2026, 10, 1, 12, 0, 0, DateTimeKind.Utc);
        var stub = new StubApiClient(OkBatch(
            Item(IdA, t),            // A 本地同时间=无更新
            Item(IdB, t.AddDays(3)), // B 远端新
            Item(IdC, t.AddDays(-1)) // C 远端旧于本地
        ));
        var checker = new WorkshopUpdateChecker(stub);
        var result = await checker.CheckUpdatesAsync(new[]
        {
            new InstalledModSnapshot(IdA, t),
            new InstalledModSnapshot(IdB, t),
            new InstalledModSnapshot(IdC, t),
        });
        Assert.True(result.IsOk);
        var c = Assert.Single(result.Value!);
        Assert.Equal(IdB, c.ItemId);
    }
}
