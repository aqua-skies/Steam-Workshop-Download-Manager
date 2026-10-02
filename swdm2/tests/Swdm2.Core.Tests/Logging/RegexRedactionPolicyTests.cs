using Swdm2.Core.Logging;

namespace Swdm2.Core.Tests.Logging;

/// <summary>
/// D1.5 脱敏策略验收。验收判据：注入敏感串 → 输出无明文。
/// 场景取自 1.x `_redact_secrets` 学费集合（账号/密码/验证码/Bearer）。
/// </summary>
public sealed class RegexRedactionPolicyTests
{
    private readonly IRedactionPolicy _policy = new RegexRedactionPolicy();
    private const string Secret = "P@ssw0rd-饥荒-Don't";

    [Theory]
    [InlineData("password=P@ssw0rd-饥荒-Don't", "password=***")]
    [InlineData("密码: hunter2", "密码: ***")] // 保留匹配到的原分隔符（含冒号后空格），与下方 JSON 引号形态一致
    [InlineData("\"token\": \"abc.def.ghi\"", "\"token\": \"***\"")]
    [InlineData("user password=secret123 ok", "user password=*** ok")]
    [InlineData("code=987654", "code=***")]
    [InlineData("pwd=s3cr3t", "pwd=***")]
    [InlineData("api_key=AKIAIOSFODNN7EXAMPLE", "api_key=***")]
    [InlineData("secret=hunter2", "secret=***")]
    [InlineData("口令=pa55w0rd", "口令=***")]
    public void KeyValue_Secrets_Redacted(string input, string expected)
        => Assert.Equal(expected, _policy.Redact(input));

    [Fact]
    public void Bearer_Tokens_Redacted()
    {
        Assert.Equal("Bearer ***", _policy.Redact("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIx"));
        Assert.Equal("Basic ***", _policy.Redact("Basic dXNlcjpwYXNz"));
        Assert.Equal("Steam ***", _policy.Redact("Steam deadbeef1234"));
    }

    [Fact]
    public void Email_Accounts_Redacted()
    {
        Assert.Equal("登录账号 ***", _policy.Redact("登录账号 user@example.com"));
        Assert.DoesNotContain("user@example.com", _policy.Redact("user.name+tag@sub.example.com"));
    }

    /// <summary>
    /// 验收判据：复合日志行整句无明文（与 D1.4 凭据值联合断言——用真实形态的密码）。
    /// 现实泄漏形态=敏感串出现在标记（password=/Bearer）旁或账号邮箱处；
    /// 裸串无标记无法被正则识别（不存在的检测能力不设断言——诚实边界）。
    /// </summary>
    [Fact]
    public void Composite_Log_Line_Has_No_Plaintext()
    {
        var account = "user@example.com";
        var line = $"登录账号 {account} 时 password={Secret} 失败，重试（Bearer jwt_{Secret}）";
        var redacted = _policy.Redact(line);
        Assert.DoesNotContain(Secret, redacted);
        Assert.DoesNotContain("P@ssw0rd", redacted);
        Assert.DoesNotContain(account, redacted);
        Assert.Contains("***", redacted);
    }

    [Fact]
    public void Non_Sensitive_Text_Unchanged()
    {
        var plain = "下载完成 3808352517 → C:\\swdm\\steamapps\\workshop\\content\\440 用时 3.2s";
        Assert.Equal(plain, _policy.Redact(plain));
    }

    [Fact]
    public void Null_And_Empty_Handled()
    {
        Assert.Equal(string.Empty, _policy.Redact(null));
        Assert.Equal(string.Empty, _policy.Redact(string.Empty));
    }
}
