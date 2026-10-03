using System.Globalization;
using System.Linq;
using System.Text;
using Swdm2.Core.Domain;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 游戏名归一化与本地别名表（D5.4;1.x swdm/core/games.py 直译移植）。
/// **1.x 学费（中英别名 bug）内置防呆**：用户输入"饥荒"必须命中
/// "Don't Starve"(appid 219740)——归一化消除全角/大小写/撇号/空格差异后
/// 按精确→子串两级匹配；storesearch(l=schinese) 是权威中文源，本表作
/// **离线零网络兜底**（网络熔断时联想仍可用，A5 熔断器语义同族）。
/// </summary>
public static class GameAliasTable
{
    /// <summary>
    /// 已知游戏（显示名=英文名；Aliases 含中文俗称/简称）。
    /// AppId 以 Steam store 权威页为准（1.x GAME_ALIASES 对齐校正：
    /// Stardew Valley=413150,1.x GAMES 表 433150 为误记，已在此修正）。
    /// </summary>
    public static readonly IReadOnlyList<GameInfo> KnownGames = new[]
    {
        new GameInfo(new AppId(219740), "Don't Starve", new[] { "饥荒", "dont starve" }),
        new GameInfo(new AppId(322330), "Don't Starve Together", new[] { "饥荒联机版", "dont starve together" }),
        new GameInfo(new AppId(4000), "Garry's Mod", new[] { "盖瑞模组", "gmod" }),
        new GameInfo(new AppId(550), "Left 4 Dead 2", new[] { "求生之路2", "l4d2" }),
        new GameInfo(new AppId(440), "Team Fortress 2", new[] { "军团要塞2", "tf2" }),
        new GameInfo(new AppId(730), "Counter-Strike 2", new[] { "反恐精英2", "cs2" }),
        new GameInfo(new AppId(294100), "RimWorld", new[] { "环世界", "边缘世界", "rimworld" }),
        new GameInfo(new AppId(346110), "ARK: Survival Evolved", new[] { "方舟", "方舟生存进化", "ark" }),
        new GameInfo(new AppId(105600), "Terraria", new[] { "泰拉瑞亚", "terraria" }),
        new GameInfo(new AppId(413150), "Stardew Valley", new[] { "星露谷物语", "stardew valley" }),
        new GameInfo(new AppId(255710), "Cities: Skylines", new[] { "城市天际线", "天际线" }),
        new GameInfo(new AppId(289070), "Sid Meier's Civilization VI", new[] { "文明6", "席德梅尔的文明6" }),
        new GameInfo(new AppId(232290), "The Elder Scrolls V: Skyrim", new[] { "上古卷轴5", "天际省", "skyrim" }),
        new GameInfo(new AppId(251570), "7 Days to Die", new[] { "七日杀" }),
        new GameInfo(new AppId(281990), "Stellaris", new[] { "群星", "stellaris" }),
        new GameInfo(new AppId(107410), "Arma 3", new[] { "武装突袭3", "arma3" }),
        new GameInfo(new AppId(252490), "Rust", new[] { "腐蚀", "rust" }),
        new GameInfo(new AppId(548430), "Deep Rock Galactic", new[] { "深岩银河", "deep rock galactic", "drg" }),
        new GameInfo(new AppId(237990), "Space Engineers", new[] { "太空工程师", "空间工程师" }),
        new GameInfo(new AppId(816450), "Green Hell", new[] { "绿色地狱" }),
        new GameInfo(new AppId(489830), "The Forest", new[] { "森林", "the forest" }),
        new GameInfo(new AppId(1063730), "Tabletop Simulator", new[] { "方桌模拟器", "桌上模拟器", "桌游模拟器" }),
        new GameInfo(new AppId(1966720), "Lethal Company", new[] { "致命公司" }),
        new GameInfo(new AppId(632360), "Risk of Rain 2", new[] { "雨中冒险2", "risk of rain 2" }),
        new GameInfo(new AppId(646570), "Slay the Spire", new[] { "杀戮尖塔", "slay the spire" }),
        new GameInfo(new AppId(435150), "Divinity: Original Sin 2", new[] { "神界原罪2", "divinity original sin 2" }),
    };

    /// <summary>
    /// 归一化（匹配用，非显示用）：NFKC 全角→半角 + 小写 + 仅保留字母数字
    /// （去空格/撇号/冒号/百分号等）。例："Don't Starve" → "dontstarve";
    /// "饥荒"保持中文（CJK 字母 IsLetterOrDigit=true 保留）。
    /// </summary>
    public static string Normalize(string? text)
    {
        if (string.IsNullOrEmpty(text))
            return string.Empty;
        var nfkc = text.Normalize(NormalizationForm.FormKC);
        var lower = nfkc.ToLower(CultureInfo.InvariantCulture);
        return string.Concat(lower.Where(char.IsLetterOrDigit));
    }

    /// <summary>
    /// 输入文本 → 候选游戏（离线兜底；上限 maxCount 条）。
    /// 精确命中优先（归一化等值），子串包含其次（任一方向）。
    /// 1.x 学费（中英别名 bug):归一化后再比=全角/大小写/撇号差异全部消除。
    /// </summary>
    public static IReadOnlyList<GameInfo> Match(string? term, int maxCount = 12)
    {
        var key = Normalize(term);
        if (key.Length < 1)
            return Array.Empty<GameInfo>();

        var exact = new List<GameInfo>();
        var substr = new List<GameInfo>();
        foreach (var game in KnownGames)
        {
            var nameKey = Normalize(game.Name);
            if (nameKey == key)
            { exact.Add(game); continue; }
            foreach (var alias in game.Aliases)
            {
                if (Normalize(alias) == key)
                { exact.Add(game); break; }
            }
        }
        if (exact.Count > 0)
            return exact.Take(maxCount).ToList();

        foreach (var game in KnownGames)
        {
            var nameKey = Normalize(game.Name);
            if (nameKey.Contains(key, StringComparison.Ordinal) || key.Contains(nameKey, StringComparison.Ordinal))
            { substr.Add(game); continue; }
            foreach (var alias in game.Aliases)
            {
                var aliasKey = Normalize(alias);
                if (aliasKey.Contains(key, StringComparison.Ordinal) || key.Contains(aliasKey, StringComparison.Ordinal))
                { substr.Add(game); break; }
            }
        }
        return substr.Take(maxCount).ToList();
    }
}
