using System.Text.RegularExpressions;

namespace Swdm2.Core.Logging;

/// <summary>
/// 正则脱敏策略（默认实现，纯 BCL）。覆盖三类泄漏形态：
/// 1. 键值标记型：<c>password=xxx / 密码: xxx / token="..."</c>（中英标记）→ 键保留、值→***；
/// 2. 授权头型：<c>Bearer/Basic/Steam &lt;token&gt;</c> → scheme 保留、令牌→***；
/// 3. 账号型：邮箱（登录账号的最常见形态）→***。
/// 属性名维度的脱敏见 App 侧 RedactingSink（按属性名拦截，比文本扫描更可靠）。
/// </summary>
public sealed class RegexRedactionPolicy : IRedactionPolicy
{
    /// <summary>密码/令牌/验证码类标记键（中英）；裸 code 带词边界防 postcode 类误伤。</summary>
    /// <para>sep 允许 key 后带可选引号（JSON 形态 "token": ...）；裸值放行撇号（密码含 ' 不能截断）。</para>
    private static readonly Regex KeyValueSecretPattern = new(
        @"(?<key>password|passwd|pwd|secret|token|api[_-]?key|otp|verification[_-]?code|validation[_-]?code|\bcode|密码|口令|验证码)(?<sep>\s*[""]?[:=：]\s*)(""(?<vq>[^""]*)""|'(?<vs>[^']*)'|(?<vb>[^\s;,\]}>]+))",
        RegexOptions.Compiled | RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>授权头：Bearer/Basic/Steam + 令牌。</summary>
    private static readonly Regex AuthorizationPattern = new(
        @"(?<scheme>Bearer|Basic|Steam)\s+(?<token>\S+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>邮箱（登录账号常见形态）。</summary>
    private static readonly Regex EmailPattern = new(
        @"[0-9A-Za-z.=_+\-]+@[0-9A-Za-z.\-]+\.[A-Za-z]{2,}",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    /// <summary>脱敏占位符。</summary>
    public const string Placeholder = "***";

    public string Redact(string? text)
    {
        if (string.IsNullOrEmpty(text))
            return text ?? string.Empty;

        // 保留匹配到的原分隔符（含间距）与引号形态（裸值/双引号/单引号）
        text = KeyValueSecretPattern.Replace(text, match =>
        {
            var key = match.Groups["key"].Value;
            var sep = match.Groups["sep"].Value;
            if (match.Groups["vq"].Success)
                return $"{key}{sep}\"{Placeholder}\"";
            if (match.Groups["vs"].Success)
                return $"{key}{sep}'{Placeholder}'";
            return $"{key}{sep}{Placeholder}";
        });
        text = AuthorizationPattern.Replace(text, "${scheme} " + Placeholder);
        text = EmailPattern.Replace(text, Placeholder);
        return text;
    }
}
