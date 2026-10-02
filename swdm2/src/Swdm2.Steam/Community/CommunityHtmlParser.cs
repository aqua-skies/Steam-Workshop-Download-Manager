using System.Net;
using System.Text.RegularExpressions;
using Swdm2.Core.Domain;

namespace Swdm2.Steam.Community;

/// <summary>
/// 社区页 HTML 解析器（D2.5）：**只锚定稳定结构**——
/// 2026-10-02 实测：browse 页已改 React 版（旧 class="workshopItem" 标记消失，混淆 CSS 类），
/// 但 `<a href=".../sharedfiles/filedetails/?id=N">` + `<img src="...ugc..." alt="标题">` 稳定；
/// detail 页旧类（workshopItemTitle/creatorsBlock）仍稳定。
/// 设计对照：解析失败 → 调用方 Fail(Deserialization)，不抛异常、不返回半假数据。
/// </>(非 AngleSharp 依赖：目标锚点稳定且页可达 679KB 全量 DOM 解析成本高；改版由 fixture 测试守）
/// </summary>
public static class CommunityHtmlParser
{
    private static readonly Regex AnchorIdRegex = new(
        @"sharedfiles/filedetails/\?id=(\d{2,20})",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex ImgSrcRegex = new(
        @"src=""(https://images\.steamusercontent\.com/ugc/[^""]+)""",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex AltTitleRegex = new(
        @"alt=\""(.*?)\""",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.Singleline);

    private const int ItemContextChars = 400; // 锚点后取窗口提取 img/alt（同卡片内）

    /// <summary>
    /// 解析 browse 页：返回 (id, title, previewUrl) 三元组（标题/预览缺失允许：
    /// 混淆类改版时常先掉副属性；id 为唯一必需项）。0 id → 返回空列表由调用方判 Deserialization。
    /// </summary>
    public static IReadOnlyList<(PublishedFileId Id, string Title, string? PreviewUrl)> ParseBrowse(string html, AppId appId)
    {
        ArgumentNullException.ThrowIfNull(html);
        var seen = new HashSet<ulong>();
        var items = new List<(PublishedFileId, string, string?)>();

        foreach (Match anchor in AnchorIdRegex.Matches(html))
        {
            var idRaw = anchor.Groups[1].Value;
            var idNum = ulong.Parse(idRaw, System.Globalization.CultureInfo.InvariantCulture);
            if (!seen.Add(idNum))
                continue;

            var window = SubSafe(html, anchor.Index, ItemContextChars);
            var title = MatchFirst(AltTitleRegex, window);
            var preview = MatchFirst(ImgSrcRegex, window);

            items.Add((new PublishedFileId(idNum), title, preview));
        }
        return items;
    }

    /// <summary>解析 detail 页标题（workshopItemTitle 稳定旧类）。</summary>
    public static string? TryParseTitle(string html)
    {
        ArgumentNullException.ThrowIfNull(html);
        var m = Regex.Match(html, @"class=""workshopItemTitle""[^>]*>\s*([^<]+?)\s*<",
            RegexOptions.CultureInvariant);
        return m.Success ? WebUtility.HtmlDecode(m.Groups[1].Value) : null;
    }

    /// <summary>解析 detail 页作者（creatorsBlock 区域内的 /id/&lt;name&gt; 链接）。</summary>
    public static string? TryParseCreator(string html)
    {
        ArgumentNullException.ThrowIfNull(html);
        var block = Regex.Match(html, @"class=""creatorsBlock""(.{0,600})",
            RegexOptions.CultureInvariant | RegexOptions.Singleline);
        if (!block.Success) return null;
        var m = Regex.Match(block.Groups[1].Value, @"steamcommunity\.com/id/([^""/]+)",
            RegexOptions.CultureInvariant);
        return m.Success ? WebUtility.HtmlDecode(m.Groups[1].Value) : null;
    }

    /// <summary>解析 detail 页预览图（首个 ugc 图片=物品预览）。</summary>
    public static string? TryParsePreview(string html)
    {
        ArgumentNullException.ThrowIfNull(html);
        var m = ImgSrcRegex.Match(html);
        return m.Success ? m.Groups[1].Value : null;
    }

    /// <summary>
    /// 解析 detail 页所属 AppId：锚定创作者工坊链接 myworkshopfiles/?appid=N
    /// （2026-10-02 实测：评论区 JSON 内的 "appid" 是**转义**串（\"appid\":N），
    /// 且页面里多个 appid 候选——创作者链接的 query 参数是最稳锚点）。
    /// </summary>
    public static AppId? TryParseAppId(string html)
    {
        ArgumentNullException.ThrowIfNull(html);
        var m = Regex.Match(html, @"myworkshopfiles/\?appid=(\d+)",
            RegexOptions.CultureInvariant);
        return m.Success && int.TryParse(m.Groups[1].Value, out var v) && v > 0 ? new AppId(v) : null;
    }

    private static string MatchFirst(Regex rx, string input)
    {
        var m = rx.Match(input);
        return m.Success ? WebUtility.HtmlDecode(m.Groups[1].Value) : string.Empty;
    }

    private static string SubSafe(string s, int start, int len)
    {
        if (start >= s.Length) return string.Empty;
        var available = s.Length - start;
        return s.Substring(start, Math.Min(len, available));
    }
}
