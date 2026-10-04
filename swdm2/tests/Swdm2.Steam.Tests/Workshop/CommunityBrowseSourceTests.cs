using System.IO;
using System.Linq;
using System.Reflection;
using Swdm2.Core.Domain;
using Swdm2.Steam.Workshop;
using Xunit;

namespace Swdm2.Steam.Tests.Workshop;

/// <summary>
/// D9.2/t68 社区 HTML 工坊浏览源解析回归：
/// 真实快照（2026-10-04 抓取 steamcommunity.com/workshop/browse?appid=550)
/// =30 真实 L4D2 工坊条目（PublishedFileId/标题/预览图）。
/// 样本=离线快照文件（快照随 Steam 页面结构变化需重抓；解析失败=源端
/// SteamError.Deserialization 明确错误态不静默）。
/// </summary>
public sealed class CommunityBrowseSourceTests
{
    private const string SnapshotResourceName =
        "Swdm2.Steam.Tests.Workshop.browse_l4d2_snapshot.html";

    private static string LoadSnapshot()
    {
        var dir = Path.GetDirectoryName(typeof(CommunityBrowseSourceTests).Assembly.Location)!;
        var file = Path.Combine(dir, "Workshop", "browse_l4d2_snapshot.html");
        if (!File.Exists(file)
            && Path.GetDirectoryName(dir) is { } parent)
            file = Path.Combine(parent, "Workshop", "browse_l4d2_snapshot.html");
        return File.Exists(file)
            ? File.ReadAllText(file, System.Text.Encoding.UTF8)
            : throw new FileNotFoundException("snapshot missing: " + file);
    }

    /// <summary>真实快照解析=30 条真实 id+标题+预览图。</summary>
    [Fact]
    public void ParseEntries_RealSnapshot_Gets_Real_Items()
    {
        var html = LoadSnapshot();
        var entries = CommunityWorkshopBrowseSource.ParseEntries(html, new AppId(550));

        Assert.Equal(30, entries.Count);
        Assert.All(entries, e => Assert.False(string.IsNullOrEmpty(e.Title)));
        Assert.All(entries, e => Assert.False(string.IsNullOrEmpty(e.Id)));
        Assert.All(entries, e => Assert.False(string.IsNullOrEmpty(e.PreviewImageUrl)));
    }

    /// <summary>条目 Id=真实 PublishedFileId(数字字符串=下载链可直接消费）。</summary>
    [Fact]
    public void ParseEntries_Ids_Are_PublicationIds()
    {
        var entries = CommunityWorkshopBrowseSource.ParseEntries(LoadSnapshot(), new AppId(550));

        Assert.Contains(entries, e => e.Id == "2121557118");
        Assert.Contains(entries, e => e.Title.Contains("Improved Blood Textures"));
        Assert.All(entries, e => Assert.True(long.TryParse(e.Id, out _)));
    }

    /// <summary>去重保序（同 id 重复出现=只留首条）。</summary>
    [Fact]
    public void ParseEntries_Dedupes_Keeps_First()
    {
        var html = LoadSnapshot();
        var first = CommunityWorkshopBrowseSource.ParseEntries(html, new AppId(550));
        var doubled = CommunityWorkshopBrowseSource.ParseEntries(html + html, new AppId(550));

        Assert.Equal(first.Count, doubled.Count);
        Assert.Equal(first[0].Id, doubled[0].Id);
    }

    /// <summary>空/坏 HTML=0 条（不抛=失败语义交 Result.Fail 处理）。</summary>
    [Fact]
    public void ParseEntries_Empty_Html_Returns_Zero()
    {
        Assert.Empty(CommunityWorkshopBrowseSource.ParseEntries(string.Empty, new AppId(550)));
        Assert.Empty(CommunityWorkshopBrowseSource.ParseEntries("<html>broken</html>", new AppId(550)));
    }
}
