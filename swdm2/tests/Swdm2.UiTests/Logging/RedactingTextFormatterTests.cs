using System.IO;
using System.Text;
using Serilog;
using Serilog.Events;
using Serilog.Formatting.Display;
using Swdm2.App.Logging;
using Swdm2.Core.Logging;

namespace Swdm2.UiTests.Logging;

/// <summary>
/// D1.5 脱敏格式化器（Serilog 管道）验收：注入敏感串 → 输出文本无明文。
/// 与 D1.4 联合断言的日志侧：即使上游误把密码拼进日志，经 RedactingTextFormatter 后无明文。
/// </summary>
public sealed class RedactingTextFormatterTests
{
    private const string Account = "user@example.com";
    private const string Password = "P@ssw0rd-饥荒-Don't";

    private static RedactingTextFormatter CreateFormatter()
        => new(new MessageTemplateTextFormatter(SwdmLogging.DefaultOutputTemplate, formatProvider: null),
               new RegexRedactionPolicy());

    [WpfFact]
    public void Structured_Properties_Are_Redacted_By_Name()
    {
        var formatter = CreateFormatter();
        using var writer = new StringWriter();
        var logEvent = MakeEvent("登录 {Account} 密码 {Password}", Account, Password);

        formatter.Format(logEvent, writer);

        var output = writer.ToString();
        Assert.DoesNotContain(Account, output);
        Assert.DoesNotContain(Password, output);
        Assert.Contains("***", output);
    }

    [WpfFact]
    public void Interpolated_Message_Is_Redacted_By_Patterns()
    {
        var formatter = CreateFormatter();
        using var writer = new StringWriter();
        // 错误用法示范：手工拼接（结构化日志应避免，但脱敏层必须兜底）
        var logEvent = MakeEvent($"登录 {Account} 时 password={Password} 失败");

        formatter.Format(logEvent, writer);

        var output = writer.ToString();
        Assert.DoesNotContain(Account, output);
        Assert.DoesNotContain(Password, output);
        Assert.DoesNotContain("P@ssw0rd", output);
    }

    [WpfFact]
    public void Non_Sensitive_Log_Passes_Through()
    {
        var formatter = CreateFormatter();
        using var writer = new StringWriter();
        var logEvent = MakeEvent("下载完成 {ItemId}", 3808352517UL);

        formatter.Format(logEvent, writer);

        var output = writer.ToString();
        Assert.Contains("3808352517", output);
        Assert.DoesNotContain("***", output);
    }

    /// <summary>验收判据（D1.4 联合）：完整 WriteTo.File 管道的落盘文件无明文。</summary>
    [WpfFact]
    public void File_Pipeline_Output_Has_No_Plaintext()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), "swdm2_d15_file_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(tempDir);
        var logPath = Path.Combine(tempDir, "swdm2-test.log");
        try
        {
            var logger = new LoggerConfiguration()
                .WriteTo.File(
                    path: logPath,
                    formatter: CreateFormatter(),
                    rollingInterval: Serilog.RollingInterval.Day,
                    shared: false)
                .CreateLogger();

            logger.Information("登录 {Account} 密码 {Password}", Account, Password);
            logger.Information($"重试 password={Password}");
            logger.Dispose(); // 刷盘

            // rollingInterval=Day 会在文件名追加日期：查找实际产出文件
            var produced = Directory.GetFiles(tempDir, "swdm2-test*.log");
            Assert.NotEmpty(produced);
            var written = File.ReadAllText(produced[0], Encoding.UTF8);
            Assert.DoesNotContain(Password, written);
            Assert.DoesNotContain("P@ssw0rd", written);
            Assert.DoesNotContain(Account, written);
            Assert.Contains("***", written);
        }
        finally
        {
            try { Directory.Delete(tempDir, recursive: true); } catch { }
        }
    }

    private static LogEvent MakeEvent(string template, params object?[] values)
    {
        var properties = new List<LogEventProperty>();
        var templateParser = new Serilog.Parsing.MessageTemplateParser();
        var parsed = templateParser.Parse(template);
        // 简化：结构化洞（{X}）按出现顺序绑定值
        var holes = parsed.Tokens.OfType<Serilog.Parsing.PropertyToken>().ToArray();
        for (var i = 0; i < holes.Length && i < values.Length; i++)
        {
            properties.Add(new LogEventProperty(holes[i].PropertyName,
                new ScalarValue(values[i])));
        }
        return new LogEvent(
            DateTimeOffset.Now,
            LogEventLevel.Information,
            exception: null,
            parsed,
            properties);
    }
}
