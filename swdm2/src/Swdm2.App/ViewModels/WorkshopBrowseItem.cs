using System.Collections.ObjectModel;
using System;
using System.Collections.Generic;
using System.Globalization;
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
    /// <summary>有预览图（缩略图槽位显隐绑定源；null/空=占位灰底）。</summary>
    public bool HasPreview => !string.IsNullOrEmpty(PreviewImageUrl);

    /// <summary>类别副标题（D9.1:类别后置=首个 tag;tag 串以 · 分隔）。</summary>
    public string CategorySubtitle =>
        Tags.Count > 0 ? string.Join(" · ", Tags) : "未分类";

    /// <summary>
    /// D9.2/t68:真实工坊条目（CommunityWorkshopBrowseSource HTML 解析出口）→
    /// App 域 VM 条目。Id=真实 PublishedFileId(long);作者/订阅数/更新时间
    /// 社区源暂未解析=诚实 0/MinValue（详情页 API 补全；不造假）。
    /// </summary>
    public static IReadOnlyList<WorkshopBrowseItem> FromEntries(
        IEnumerable<Swdm2.Steam.Workshop.WorkshopBrowseEntry> entries, AppId appId)
    {
        var items = new List<WorkshopBrowseItem>();
        foreach (var e in entries)
        {
            if (!long.TryParse(e.Id, NumberStyles.Integer, CultureInfo.InvariantCulture, out var pubId))
                continue; // 非数字 id=坏条目跳过（诚实不混入）
            items.Add(new WorkshopBrowseItem(
                Id: pubId,
                Title: e.Title,
                Author: e.Author ?? string.Empty,
                Tags: e.Tags,
                Subscribers: e.Subscribers ?? 0,
                UpdatedAt: e.UpdatedAt ?? DateTimeOffset.MinValue,
                PreviewImageUrl: e.PreviewImageUrl,
                AppId: appId));
        }
        return items;
    }

    /// <summary>
    /// 合成千项样本（1000 条：流畅性/虚拟化基准与 VM 逻辑测试共用）。
    /// D9.1(t67) 用户骂点"假数据 Mod #123456·剧情作品"整改——
    /// **标题=mod 名字优先**（无编号前缀）;类别/tag 降为副标题由模板后置；
    /// PreviewImageUrl=null=占位图槽位诚实（不装真图）。
    /// </summary>
    public static IReadOnlyList<WorkshopBrowseItem> SampleData(int count = 1000)
    {
        var tagPool = new[] { "地图", "模型", "玩法", "皮肤", "工具", "剧情", "音乐", "UI" };
        var authorPool = new[] { "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel" };
        // D9.1:mod 名字池（名字优先；类别不再进标题）
        var namePool = new[]
        {
            "遗忘之城", "机械纪元", "深渊之声", "星空要塞", "暮色庄园", "熔铁工坊", "幻梦回廊",
            "荒野猎歌", "晶蓝海洋", "古神试炼", "霓虹街景", "林间小屋", "城堡战争", "末日列车",
            "云端赛道", "暗影契约", "沙丘帝国", "极光观测站", "苔原生存", "钟楼怪人", "潮汐之刃",
        };
        var items = new List<WorkshopBrowseItem>(count);
        var seed = 1337;
        int Rnd(int max) { seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF; return seed % max; }
        for (var i = 0; i < count; i++)
        {
            var tagCount = 1 + Rnd(3);
            var tags = new HashSet<string>();
            for (var t = 0; t < tagCount; t++) tags.Add(tagPool[Rnd(tagPool.Length)]);
            var name = namePool[Rnd(namePool.Length)];
            var suffix = Rnd(20) == 0 ? "Ⅱ" : (Rnd(12) == 0 ? "·重制版" : string.Empty);
            items.Add(new WorkshopBrowseItem(
                Id: 100000 + i,
                Title: $"{name}{suffix}",
                Author: authorPool[Rnd(authorPool.Length)] + Rnd(90),
                Tags: tags.ToArray(),
                Subscribers: Rnd(50000),
                UpdatedAt: DateTimeOffset.Now.AddDays(-Rnd(365)),
                PreviewImageUrl: null, // 无图=占位槽位（诚实，不装真图）
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
