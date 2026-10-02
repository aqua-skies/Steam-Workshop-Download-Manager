using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Xunit;
// [WpfFact] 特性位于命名空间 Xunit（StaFact 2.1.7 实证，同 1.1.11）

namespace Swdm2.UiTests.Tests.Smoke;

/// <summary>
/// D0.2 冒烟：进程外启动被测 exe 并断言主窗口（真实启动路径，无打桩）。
/// 验收：Application.Launch → UIA3 定位 AutomationId=MainWindow → 断言通过 → 进程清理。
/// </summary>
public sealed class AppLaunchSmokeTests
{
    [WpfFact]
    public void App_Launches_And_MainWindowAutomationIdFound()
    {
        var exe = ResolveAppExe();
        Assert.True(File.Exists(exe), $"被测 exe 不存在（先 build App）：{exe}");

        using var automation = new UIA3Automation();
        var app = Application.Launch(exe);
        try
        {
            var window = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("MainWindow"))?.AsWindow(),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;

            Assert.NotNull(window);
            Assert.Equal("MainWindow", window!.AutomationId);
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    /// <summary>swdm2/src/Swdm2.App/bin/Debug/net8.0-windows/Swdm2.App.exe（相对测试输出目录）。</summary>
    /// <remarks>SP-3 驱动模式下环境变量 SWDM2_APP_EXE 可覆盖（t3 §2.4 UiTestSettings 约定）。</remarks>
    private static string ResolveAppExe()
    {
        var overridden = Environment.GetEnvironmentVariable("SWDM2_APP_EXE");
        if (!string.IsNullOrEmpty(overridden) && File.Exists(overridden))
            return overridden;
        return Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", "..",
            "src", "Swdm2.App", "bin", "Debug", "net8.0-windows", "Swdm2.App.exe"));
    }
}
