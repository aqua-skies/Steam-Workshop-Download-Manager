namespace Swdm2.Steam.Web;

/// <summary>
/// 1.x 429 学费的指纹头四件套（research/steam_429_403_research.md 实证结论移植）：
/// **承重头=Accept-Language**——Chrome UA 缺该头即 429，任何 UA 加它即 200（各 3/3 复测）；
/// ⚠️ 旧结论已失效：X-Requested-With 单独**不能**让 429→200（research_2 复测推翻），
/// 此处仅作冗余防御层（D1.5 双防线同构：关键头+冗余头），不作为防 429 依赖。
/// UA 用诚实产品名（实测 curl/python-requests UA + Accept-Language 均 200，无需伪装浏览器）。
/// </summary>
public static class SteamHttpHeaders
{
    /// <summary>产品 UA（诚实标识，不带版本号避免指纹膨胀；后续定版本号可带）。</summary>
    public const string UserAgent = "SWDM/2.0 (+https://github.com/aqua-skies/Steam-Workshop-Download-Manager)";

    /// <summary>Accept：API JSON 优先，HTML 回退（社区页解析需要）。</summary>
    public const string Accept = "application/json, text/html;q=0.9, */*;q=0.8";

    /// <summary>**承重头**（1.x 429 根因实测：缺此头 → 详情页 429；加了即 200）。</summary>
    public const string AcceptLanguage = "zh-CN,zh;q=0.9,en;q=0.8";

    /// <summary>冗余防御头（旧结论"单独可解 429"已被 research_2 推翻；仅作第二防线）。</summary>
    public const string XRequestedWith = "XMLHttpRequest";

    /// <summary>头名常量（断言/日志引用）。</summary>
    public static class Names
    {
        public const string AcceptLanguage = "Accept-Language";
        public const string UserAgent = "User-Agent";
        public const string Accept = "Accept";
        public const string XRequestedWith = "X-Requested-With";
    }
}
