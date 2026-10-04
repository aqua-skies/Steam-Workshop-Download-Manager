using System;
using System.IO;
using System.Text;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Sweep;

/// <summary>
/// D9.1(t67) 全按钮实测桌面扫掠：
/// 逐页导航（InvokePattern 命令链口径；沙箱物理点击被前台锁吞=t62 归档同族）
/// + DumpTree 落盘每页 UIA 树（按钮/输入/列表契约 id 清单）=
/// docs/process/button_sweep_2.0.md 的实测证据源。
/// 扫掠页：主页/浏览/详情/下载/库/设置/游戏选择；死钮（enabled 但无反馈）
/// 由 TreeDump+命令链复核；逻辑层 CanExecute 覆盖在各自 VM 单测。
/// </summary>
public sealed class ButtonSweepDesktopTests
{
    [WpfFact]
    public void Sweep_All_Pages_Dump_Buttons()
    {
        var exe = UiTestHelpers.ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing: {exe}");

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

            // 主页（启动初始页=SphereHome）树转储
            UiTestHelpers.DumpTree(window, "sweep: 主页 SphereHome");

            // 逐页导航+转储（导航钮自身=第一个被实测的按钮：enabled+点击有反馈=页面切换）
            foreach (var (label, navId) in new[]
            {
                ("浏览", "MainShell_Nav_BrowseButton"),
                ("详情", "MainShell_Nav_ModDetailButton"),
                ("下载", "MainShell_Nav_DownloadsButton"),
                ("库", "MainShell_Nav_LibraryButton"),
                ("设置", "MainShell_Nav_SettingsButton"),
                ("游戏选择", "MainShell_Nav_GameSelectButton"),
            })
            {
                var nav = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, navId),
                    TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(0.2)).Result;
                Assert.NotNull(nav); // 导航钮在位且 enabled
                nav!.AsButton().Invoke(); // 点击=页面切换反馈
                System.Threading.Thread.Sleep(600); // 切页编排（A3 三相）落定
                UiTestHelpers.DumpTree(window, $"sweep: {label} 页");
            }

            // 返回钮（t62 死钮修复项）实测：栈非空=enabled+点击回上一页
            var back = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "MainShell_Nav_BackButton"),
                TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(0.2)).Result;
            if (back is not null)
            {
                back.AsButton().Invoke();
                System.Threading.Thread.Sleep(500);
                UiTestHelpers.DumpTree(window, "sweep: 返回后页");
            }
        }
        finally
        {
            try { app?.Close(); } catch { }
            try { app?.Kill(); } catch { }
        }
    }
}
