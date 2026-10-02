namespace Swdm2.Core.Logging;

/// <summary>
/// 脱敏策略契约（C2：凭据不进日志）。1.x `_redact_secrets` 学费的 C# 对等物：
/// 账号/密码/验证码/Bearer 令牌等敏感串 → <c>***</c>。
/// </summary>
public interface IRedactionPolicy
{
    /// <summary>对日志文本做脱敏替换（返回值不出现明文敏感串）。</summary>
    string Redact(string? text);
}
