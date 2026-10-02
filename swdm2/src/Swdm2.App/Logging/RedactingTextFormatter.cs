using System.IO;
using Serilog.Events;
using Serilog.Formatting;
using Serilog.Formatting.Display;
using Serilog.Parsing;
using Swdm2.Core.Logging;

namespace Swdm2.App.Logging;

/// <summary>
/// Serilog 脱敏文本格式化器（C2：凭据不进日志）。Composed with any <see cref="ITextFormatter"/>（如输出模板），
/// 与 <c>WriteTo.File(..., formatter: ..., rollingInterval, shared)</c> 组合即得滚动文件 + 脱敏（D1.5 正道组合点）。
/// 两层防线：
/// 1. **属性名维度**：结构化属性名为 password/token/account 等 → 值替换 <c>***</c>，再渲染模板；
/// 2. **文本维度**：渲染结果再过 <see cref="IRedactionPolicy"/>（键值标记/Bearer/邮箱），兜底手工拼接泄漏。
/// 例外边界：异常消息按原样经 <c>{Exception}</c> 输出——消息纪律由抛出方负责（D1.4 CredentialStoreException 模式）。
/// </summary>
public sealed class RedactingTextFormatter : ITextFormatter
{
    /// <summary>结构化属性名黑名单（OrdinalIgnoreCase，含包含匹配）。</summary>
    private static readonly HashSet<string> SecretPropertyNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "password", "passwd", "pwd", "secret", "token", "apikey", "api_key",
        "otp", "code", "verificationcode", "verification_code",
        "account", "email", "credentials", "cookie", "sessionid",
    };


    private readonly ITextFormatter _inner;
    private readonly IRedactionPolicy _policy;

    /// <param name="inner">实际输出格式化器（如 <see cref="MessageTemplateTextFormatter"/>）。</param>
    public RedactingTextFormatter(ITextFormatter inner, IRedactionPolicy policy)
    {
        ArgumentNullException.ThrowIfNull(inner);
        ArgumentNullException.ThrowIfNull(policy);
        _inner = inner;
        _policy = policy;
    }

    public void Format(LogEvent logEvent, TextWriter output)
    {
        ArgumentNullException.ThrowIfNull(logEvent);

        // 第一层：属性名维度替换敏感值
        var sanitized = new Dictionary<string, LogEventPropertyValue>();
        foreach (var property in logEvent.Properties)
        {
            sanitized[property.Key] = IsSecretPropertyName(property.Key)
                ? new ScalarValue("***")
                : property.Value;
        }

        // 渲染（模板 + 已脱敏属性）
        string rendered;
        try
        {
            rendered = logEvent.MessageTemplate.Render(sanitized, formatProvider: null);
        }
        catch
        {
            rendered = logEvent.MessageTemplate.Text; // 渲染失败退回原文（再过文本脱敏）
        }

        // 第二层：文本维度正则脱敏（双保险）
        var redactedText = _policy.Redact(rendered);

        var redactedEvent = new LogEvent(
            logEvent.Timestamp,
            logEvent.Level,
            logEvent.Exception, // 例外边界：异常对象按原样（消息纪律由抛出方负责，见类注释）
            BuildTextTemplate(redactedText),
            properties: Enumerable.Empty<LogEventProperty>());

        _inner.Format(redactedEvent, output);
    }

    /// <summary>把已脱敏文本包装成可正确渲染的模板（单 LiteralToken——Render 走 token 流，空 tokens 会渲染出空串）。</summary>
    private static MessageTemplate BuildTextTemplate(string text)
        => new(text, new MessageTemplateToken[] { new TextToken(text) });

    private static bool IsSecretPropertyName(string name)
        => SecretPropertyNames.Contains(name)
           || SecretPropertyNames.Any(s => name.Contains(s, StringComparison.OrdinalIgnoreCase));
}
