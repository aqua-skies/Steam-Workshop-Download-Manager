using System;
using System.Diagnostics;
using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.ModDetail;

/// <summary>
/// t70/t71 e2e 断点回归：下载钮挤出窗口可见区（qa e2e 复现 rect y887&gt;winBottom809,
/// 物理鼠标点击落点出界无效——用户"按键每页真实有效"纪律）。
/// 修复=固定底部操作栏（PCL2 同款；P0 旅程锚点 ModDetailPage_DownloadButton 不变）。
/// 几何断言（沙箱可验证=Layer 1 命令链口径 InvokePattern 导航）：
/// 按钮底边 &lt; 窗口底（留白&gt;0);按钮顶边 &gt; 窗口顶。
/// </summary>
public sealed class ModDetailStickyDownloadButtonTests
{
    [WpfFact]
    public void Download_Button_Stays_Inside_Visible_Window()
    {
        var exe = UiTestHelpers.ResolveAppExe();
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
            System.Threading.Thread.Sleep(1200); // 切页编排四相

            var navDetail = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "MainShell_Nav_ModDetailButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navDetail);
            navDetail!.AsButton().Invoke();

            var btn = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "ModDetailPage_DownloadButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.3)).Result;
            Assert.NotNull(btn);

            var w = window.BoundingRectangle;
            var b = btn!.BoundingRectangle;
            Console.WriteLine(
                $"DIAG t71 DLBTN=({b.X},{b.Y},{b.Width}x{b.Height}) WIN=({w.X},{w.Y},{w.Width}x{w.Height})");
            Assert.True(b.Y + b.Height <= w.Y + w.Height,
                $"下载钮必须全部在窗口可见区内：btnBottom={b.Y + b.Height} winBottom={w.Y + w.Height}");
            Assert.True(b.Y >= w.Y,
                $"下载钮顶边不得在窗口顶之上：btnTop={b.Y} winTop={w.Y}");
            Assert.True(b.Width > 0 && b.Height > 0, "下载钮必须有非零尺寸");
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            UiTestHelpers.CaptureFailure(nameof(Download_Button_Stays_Inside_Visible_Window));
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }
}
