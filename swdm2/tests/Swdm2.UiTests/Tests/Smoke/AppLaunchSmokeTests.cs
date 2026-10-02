using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Xunit;
// [WpfFact] feature lives in namespace Xunit (StaFact 2.1.7 verified, same as 1.1.11)

namespace Swdm2.UiTests.Tests.Smoke;

/// <summary>
/// D0.2 smoke: launch the app out-of-process and assert the main shell
/// (real launch path, no stubbing).
/// Acceptance: Application.Launch -> locate MainShell by AutomationId (t3 section 3.2
/// reservation table) -> assert passes -> process cleanup.
/// </summary>
public sealed class AppLaunchSmokeTests
{
    [WpfFact]
    public void App_Launches_And_MainShellAutomationIdFound()
    {
        var exe = ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing (build App first): {exe}");

        using var automation = new UIA3Automation();
        var app = Application.Launch(exe);
        try
        {
            var window = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("MainShell"))?.AsWindow(),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;

            Assert.NotNull(window);
            Assert.Equal("MainShell", window!.AutomationId);
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    /// <summary>swdm2/src/Swdm2.App/bin/Debug/net8.0-windows/Swdm2.App.exe (relative to test output dir).</summary>
    /// <remarks>SP-3 driver mode: env SWDM2_APP_EXE can override (t3 section 2.4 UiTestSettings).</remarks>
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
