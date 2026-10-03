using System.Globalization;
using System.Net;
using System.Text.RegularExpressions;
using Swdm2.Core.Domain;

namespace Swdm2.App.Community;

/// <summary>
/// 工坊评论（社区页解析；C1 不可变 record)。
/// 1.x 学费：评论数据是**显示快照**——解析失败给空串而非抛异常（半假数据的反面）。
/// </summary>
public sealed record WorkshopComment
{
    /// <summary>评论 id（社区页 comment_N DOM id;0=未解析）。</summary>
    public ulong Id { get; init; }

    /// <summary>作者名（可空→UI 诚实降级"未知作者"）。</summary>
    public string? Author { get; init; }

    /// <summary>评论时间文本（可空→"未知时间"）。</summary>
    public string? Time { get; init; }

    /// <summary>正文（保留换行、去标签、还原实体；空串=解析为空正文）。</summary>
    public string Content { get; init; } = string.Empty;
}

/// <summary>
/// 社区详情页评论 + 描述解析器（D5.6;1.x swdm/gui/detail_dialog.py 直译移植）。
/// **只锚定稳定结构**（2026-10-02 实测与 D2.5 CommunityHtmlParser 同期口径）：
/// - 评论块：`&lt;div class="commentthread_comment" id="comment_N"&gt;` 稳定
/// - 作者：`commentthread_author_link` 链接文本稳定
/// - 时间戳：`data-timestamp` 属性稳定（unix → 本地时区文本，失败给空）
/// - 描述：`workshopItemDescription` + `highlightContent`（富文本，保留原始标签）
/// 解析失败一律返回**空/默认**（评论 0 条、描述空串），由调用方/UI 诚实降级显示。
/// </summary>
public static class CommunityCommentParser
{
    private static readonly Regex CommentStartRegex = new(
        @"<div[^>]*class=""[^""]*commentthread_comment[^""]*""[^>]*id=""comment_(\d+)""",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex AuthorRegex = new(
        @"commentthread_author_link""[^>]*>(?:\s*<bdi>)?(.*?)(?:</bdi>)?\s*</a>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.Singleline);

    private static readonly Regex TimestampRegex = new(
        @"data-timestamp=""(\d+)""",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex CommentTotalRegex = new(
        @"id=""commentthread_[^""]*_totalcount"">\s*(\d+)",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex TagRegex = new(@"<[^>]+>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly Regex BrRegex = new(@"<br\s*/?>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex BlockEndRegex = new(@"</p>|</div>|</li>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex DescriptionStartRegex = new(
        @"<div[^>]*class=""[^""]*workshopItemDescription[^""]*""[^>]*id=""highlightContent""[^>]*>",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    /// <summary>评论总数（页面头部计数；0=未找到/无评论）。</summary>
    public static int CommentTotal(string? html)
    {
        if (string.IsNullOrEmpty(html))
            return 0;
        var m = CommentTotalRegex.Match(html);
        return m.Success && int.TryParse(m.Groups[1].Value, NumberStyles.Integer,
                   CultureInfo.InvariantCulture, out var v) && v >= 0 ? v : 0;
    }

    /// <summary>
    /// 解析评论列表（空页面/解析失败→空列表，不抛异常）。
    /// 1.x 语义：块级 div 配对截取（_slice_balanced_div 移植）。
    /// </summary>
    public static IReadOnlyList<WorkshopComment> ParseComments(string? html, int maxComments = 50)
    {
        if (string.IsNullOrEmpty(html))
            return Array.Empty<WorkshopComment>();

        var comments = new List<WorkshopComment>();
        foreach (Match start in CommentStartRegex.Matches(html))
        {
            if (comments.Count >= maxComments)
                break;
            if (!ulong.TryParse(start.Groups[1].Value, NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out var id) || id == 0)
                continue;

            // 块尾：配对 </div>（块内嵌套 div 计数）
            var block = SliceBalancedDiv(html, start.Index + start.Length);
            comments.Add(new WorkshopComment
            {
                Id = id,
                Author = DecodeOrNull(AuthorRegex.Match(block)),
                Time = FormatTimestamp(TimestampRegex.Match(block)),
                Content = CleanContent(block),
            });
        }
        return comments;
    }

    /// <summary>详情页描述（富文本保留原始标签；空串=未找到）。</summary>
    public static string ParseDescription(string? html)
    {
        if (string.IsNullOrEmpty(html))
            return string.Empty;
        var m = DescriptionStartRegex.Match(html);
        if (!m.Success)
            return string.Empty;
        return SliceBalancedDiv(html, m.Index + m.Length).Trim();
    }

    private static string SliceBalancedDiv(string html, int start)
    {
        var depth = 1;
        var i = start;
        while (i < html.Length && depth > 0)
        {
            var open = html.IndexOf("<div", i, StringComparison.Ordinal);
            var close = html.IndexOf("</div>", i, StringComparison.Ordinal);
            if (close == -1)
                break;
            if (open != -1 && open < close)
            {
                depth++;
                i = open + 4;
            }
            else
            {
                depth--;
                i = close + 6;
            }
        }
        return html[start..i];
    }

    private static string CleanContent(string s)
    {
        s = BrRegex.Replace(s, "\n");
        s = BlockEndRegex.Replace(s, "\n");
        s = TagRegex.Replace(s, string.Empty);
        return WebUtility.HtmlDecode(s).Trim();
    }

    private static string? DecodeOrNull(Match m)
        => m.Success ? WebUtility.HtmlDecode(m.Groups[1].Value).Trim() : null;

    private static string? FormatTimestamp(Match m)
    {
        if (!m.Success || !long.TryParse(m.Groups[1].Value, NumberStyles.Integer,
                CultureInfo.InvariantCulture, out var ts) || ts <= 0)
            return null;
        try
        {
            var dt = DateTimeOffset.FromUnixTimeSeconds(ts).LocalDateTime;
            return dt.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
        }
        catch (ArgumentOutOfRangeException)
        {
            return null; // 越界时间戳=诚实空（1.x OSError/Overflow 同族）
        }
    }
}
