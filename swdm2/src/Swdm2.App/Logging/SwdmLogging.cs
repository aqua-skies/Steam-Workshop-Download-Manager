using System.IO;
using System.Text;
using Serilog;
using Serilog.Formatting.Display;
using Swdm2.Core.Logging;
using Swdm2.Core.Paths;

namespace Swdm2.App.Logging;

/// <summary>
/// D1.5 日志接桥：Serilog → 脱敏格式化器 → 滚动文件（&lt;Root&gt;/logs/swdm2-*.log 按天，UTF8 无 BOM）。
/// C2：所有日志出口默认经过 <see cref="RedactingTextFormatter"/>（启动期单点装配）。
/// </summary>
public static class SwdmLogging
{
    /// <summary>默认输出模板（Serilog 标准 + 异常尾巴）。</summary>
    public const string DefaultOutputTemplate =
        "{Timestamp:yyyy-MM-dd HH:mm:ss.fff zzz} [{Level:u3}] {Message:lj}{NewLine}{Exception}";

    /// <summary>创建默认产品日志：脱敏 + 按天滚动文件 + 共享写（多实例安全）。</summary>
    public static ILogger CreateLogger(IPathService paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        paths.EnsureDirectories();

        var innerFormatter = new MessageTemplateTextFormatter(DefaultOutputTemplate, formatProvider: null);
        var redacting = new RedactingTextFormatter(innerFormatter, new RegexRedactionPolicy());

        return new LoggerConfiguration()
            .MinimumLevel.Information()
            .WriteTo.File(
                path: Path.Combine(paths.LogDirectory, "swdm2-.log"),
                formatter: redacting,
                rollingInterval: Serilog.RollingInterval.Day,
                shared: true,
                encoding: new UTF8Encoding(encoderShouldEmitUTF8Identifier: false))
            .CreateLogger();
    }
}
