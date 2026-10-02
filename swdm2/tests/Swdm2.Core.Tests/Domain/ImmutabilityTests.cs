using Swdm2.Core.Domain;

namespace Swdm2.Core.Tests.Domain;

/// <summary>
/// C1/C5 不变量：领域模型不可变、集合只读、构造时防御性拷贝。
/// （1.x api_cache 污染学费 & 联想模型原地更新闪烁学费的契约守护。）
/// </summary>
public sealed class ImmutabilityTests
{
    [Fact]
    public void WorkshopItem_Is_Immutable_Record()
    {
        var item = MakeItem();

        var clone = item with { Title = "改名" };

        Assert.Equal("标题", item.Title);          // 原实例未被修改
        Assert.Equal("改名", clone.Title);
        Assert.NotSame(item, clone);
        // with 走拷贝构造：Dependencies 数组引用共享，但仅以 IReadOnlyList 暴露（不可写，C5）
        Assert.Equal(item.Dependencies, clone.Dependencies);
    }

    [Fact]
    public void WorkshopItem_Dependencies_Are_Defensively_Copied()
    {
        var mutable = new List<PublishedFileId> { new(1), new(2) };
        var item = new WorkshopItem(new PublishedFileId(100), new AppId(440), "标题", mutable);

        // 外部突变不影响领域实例（C5：缓存/服务返回前深拷贝的等价约束）
        mutable.Add(new PublishedFileId(3));
        Assert.Equal(2, item.Dependencies.Count);

        // 只读集合不允许写入（List<T> 里以 IList 暴露时才可写，IReadOnlyList 不行）
        Assert.IsAssignableFrom<IReadOnlyList<PublishedFileId>>(item.Dependencies);
    }

    [Fact]
    public void WorkshopItem_Default_Dependencies_Is_Empty_And_Never_Null()
    {
        var item = new WorkshopItem(new PublishedFileId(100), new AppId(440), "标题");
        Assert.NotNull(item.Dependencies);
        Assert.Empty(item.Dependencies);
    }

    [Fact]
    public void WorkshopItem_Equality_Is_Value_Based()
    {
        var a = MakeItem();
        var b = new WorkshopItem(new PublishedFileId(100), new AppId(440), "标题", new[] { new PublishedFileId(1), new PublishedFileId(2) })
        {
            Description = "描述",
            FileSize = 1024,
        };
        Assert.Equal(a, b);
        Assert.Equal(a.GetHashCode(), b.GetHashCode());
    }

    [Fact]
    public void GameInfo_Aliases_Are_Defensively_Copied_And_Immutable()
    {
        var aliases = new List<string> { "饥荒", "Don't Starve Together" };
        var game = new GameInfo(new AppId(322330), "Don't Starve Together", aliases, new AppId(343050));

        aliases.Add("DST");
        Assert.Equal(2, game.Aliases.Count);                        // 构造后外部突变不进入领域实例
        Assert.Equal("Don't Starve Together", game.Aliases[1]);     // 构造时快照的原始顺序
        Assert.IsAssignableFrom<IReadOnlyList<string>>(game.Aliases);
        Assert.Equal(343050, game.DsAppIdFallback!.Value);
    }

    [Fact]
    public void DownloadTask_Is_Immutable_Snapshot()
    {
        var task = new DownloadTask(DownloadTaskId.New(), MakeItem(), new AppId(440), @"C:\swdm\440\100")
        {
            TotalBytes = 1024,
            Provider = DownloadProvider.SteamCmd,
        };
        var updated = task with { TotalBytes = 2048 };

        Assert.Equal(1024UL, task.TotalBytes);
        Assert.Equal(2048UL, updated.TotalBytes);
        Assert.Equal(DownloadProvider.SteamCmd, updated.Provider);
    }

    [Fact]
    public void ModLibraryEntry_Is_Immutable()
    {
        var entry = new ModLibraryEntry(new PublishedFileId(100), new AppId(440), "标题", "440\\100")
        {
            InstalledAtUtc = new DateTime(2026, 10, 2, 16, 0, 0, DateTimeKind.Utc),
            FileSize = 4096,
        };
        var updated = entry with { HasUpdate = true };
        Assert.False(entry.HasUpdate);
        Assert.True(updated.HasUpdate);
        Assert.Equal(4096UL, entry.FileSize);
    }

    private static WorkshopItem MakeItem() =>
        new(new PublishedFileId(100), new AppId(440), "标题", new[] { new PublishedFileId(1), new PublishedFileId(2) })
        {
            Description = "描述",
            FileSize = 1024,
        };
}
