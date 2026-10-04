using System.Collections.ObjectModel;
using Swdm2.Core.Domain;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 工坊浏览条目（D5.5;D5.20b 增 AppId 供下载入队/详情跳转）:
/// record 不可变（C1 不变量：集合只读、不原地改）。
/// 生产源=Web API/community 浏览（D5.x 接入）；本阶段 VM 注入（合成千项=流畅性基准）。
/// </summary>
public sealed record WorkshopBrowseItem(
    long Id,
    string Title,
    string Author,
    IReadOnlyList<string> Tags,
    long Subscribers,
    DateTimeOffset UpdatedAt,
    string? PreviewImageUrl,
    AppId? AppId = null)
{
    /// <summary>合成千项样本（1000 条：流畅性/虚拟化基准与 VM 逻辑测试共用）。</summary>
    /// <remarks>D5.20b:样本 AppId=Garry's Mod(4000)=演示默认游戏（真实条目由网络源填实值）。</remarks>
    public static IReadOnlyList<WorkshopBrowseItem> SampleData(int count = 1000)
    {
        var tagPool = new[] { "地图", "模型", "玩法", "皮肤", "工具", "剧情", "音乐", "UI" };
        var authorPool = new[] { "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel" };
        var items = new List<WorkshopBrowseItem>(count);
        var seed = 1337;
        int Rnd(int max) { seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF; return seed % max; }
        for (var i = 0; i < count; i++)
        {
            var tagCount = 1 + Rnd(3);
            var tags = new HashSet<string>();
            for (var t = 0; t < tagCount; t++) tags.Add(tagPool[Rnd(tagPool.Length)]);
            items.Add(new WorkshopBrowseItem(
                Id: 100000 + i,
                Title: $"Mod #{100000 + i} · {tagPool[Rnd(tagPool.Length)]}作品",
                Author: authorPool[Rnd(authorPool.Length)] + Rnd(90),
                Tags: tags.ToArray(),
                Subscribers: Rnd(50000),
                UpdatedAt: DateTimeOffset.Now.AddDays(-Rnd(365)),
                PreviewImageUrl: null,
                AppId: new AppId(4000)));
        }
        return items;
    }
}

/// <summary>
/// 排序键（D5.5)。
/// </summary>
public enum BrowseSortKey
{
    Title,
    Subscribers,
    UpdatedAt,
}
