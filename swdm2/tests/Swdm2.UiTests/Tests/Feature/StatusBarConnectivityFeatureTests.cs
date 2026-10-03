using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke; // UiTestHelpers（同族冒烟门）
using Xunit;
// [WpfFact] feature lives in namespace Xunit (StaFact 2.1.7 verified, same as 1.1.11)

namespace Swdm2.UiTests.Tests.Feature;

/// <summary>
/// D5.9(t48) 状态栏端点可达性 FlaUI 特性测试。
/// Layer 1（沙箱可验证）:启动→MainShell→StatusBar_Connectivity 存在+
/// StatusBar_ProxyMode 文本非空+三端点芯片（API/Store/社区）存在。
/// Layer 2（需桌面合成）:RealClick StatusBar_Refresh→端点芯片文本落入
/// {直连/经代理/封禁/不可达/未探测} 之一=如实显示+可刷新。
/// 沙箱无桌面合成=Capture 全黑→ENV-DOWNGRADE 桌面通道复跑（t28/t38 同门）。
/// </summary>
public sealed class StatusBarConnectivityFeatureTests
{
    private static readonly string[] ValidReachLabels =
        { "直连", "经代理", "封禁", "不可达", "未探测" };

    private static string ResolveAppExe()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && dir.Name != "swdm2" && dir.Parent is not null) dir = dir.Parent;
        var root = dir?.Parent ?? new DirectoryInfo(Directory.GetCurrentDirectory());
        return Path.Combine(root.FullName, "swdm2", "src", "Swdm2.App", "bin", "Debug",
            "net8.0-windows", "Swdm2.App.exe");
    }

    private static AutomationElement? VisibleElement(AutomationElement window, string id)
    {
        var el = window.FindFirstDescendant(cf => cf.ByAutomationId(id));
        return el is { } e && e.BoundingRectangle.Width > 0 && e.BoundingRectangle.Height > 0 ? e : null;
    }

    [WpfFact]
    public void Status_Bar_Connectivity_Reflects_And_Refresh_When_Desktop()
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
            window!.Focus();

            // Layer 1: 状态栏存在+代理模式文本非空+三端点芯片存在
            Console.WriteLine("DIAG t48: window ok");
            var statusBar = Retry.WhileNull(
                () => VisibleElement(window, "StatusBar_Connectivity"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(statusBar);
            Console.WriteLine("DIAG t48: statusbar ok");

            var proxyMode = Retry.WhileNull(
                () => VisibleElement(window, "StatusBar_ProxyMode")?.AsLabel(),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(proxyMode);
            Console.WriteLine("DIAG t48: proxymode ok text=" + proxyMode!.Text);
            Assert.False(string.IsNullOrWhiteSpace(proxyMode!.Text));

            foreach (var expected in new[] { "API", "Store", "社区" })
            {
                var chip = Retry.WhileNull(
                    () => window.FindFirstDescendant(cf => cf.ByName(expected)),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                if (chip is null)
                {
                    Console.WriteLine($"DIAG t48: chip '{expected}' NOT found — dumping tree");
                    UiTestHelpers.DumpTree(window, $"t48 chip {expected} missing");
                }
                Assert.NotNull(chip);
                Assert.True(chip!.BoundingRectangle.Width > 0);
            }
            Console.WriteLine("DIAG t48: chips ok");

            // 环境降级门（沙箱无桌面合成=Capture 全黑→输入不路由；t38/t26 同门）
            if (UiTestHelpers.MainScreenCaptureIsBlank())
            {
                UiTestHelpers.DumpTree(window, "env-downgrade: status bar refresh click not routed");
                Console.WriteLine("ENV-DOWNGRADE: 状态栏 Layer1 契约通过；刷新真实点击层桌面复跑。");
                return;
            }

            // Layer 2: 真实点击刷新（t3 输入三规则：GetClickablePoint+Mouse.Click，无 InvokePattern）
            var refresh = Retry.WhileNull(
                () => VisibleElement(window, "StatusBar_Refresh"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(refresh);
            RealClick(refresh!);

            // 刷新后三端点文本必须落入有效状态集合（如实显示；首探可能 5s 超时=不可达/未探测=合法）
            var any = Retry.WhileNull(
                () => window.FindFirstDescendant(cf => cf.ByName("直连"))
                    ?? window.FindFirstDescendant(cf => cf.ByName("经代理"))
                    ?? window.FindFirstDescendant(cf => cf.ByName("封禁"))
                    ?? window.FindFirstDescendant(cf => cf.ByName("不可达"))
                    ?? window.FindFirstDescendant(cf => cf.ByName("未探测")),
                TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.25)).Result;
            Assert.NotNull(any);
        }
        finally
        {
            try { app.Close(); } catch { }
        }
    }

    private static void RealClick(AutomationElement element)
        => UiTestHelpers.RealClick(element);
}
