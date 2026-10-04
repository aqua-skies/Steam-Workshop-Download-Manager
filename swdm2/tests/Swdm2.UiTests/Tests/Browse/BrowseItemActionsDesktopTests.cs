using System;
using System.IO;
using System.Threading;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// D5.20b(t63) 浏览条目动作桌面通道验证：
/// - 「详情」/「下载」实物钮在位（AutomationId 契约）
/// - 详情：InvokePattern 点击→ModDetailPage 真实标题出现+示例横幅隐藏（CurrentId 接线）
/// - 下载：InvokePattern 点击→DownloadsPage_TaskList_Item 行出现（队列出现任务）
///
/// **输入层口径**（t62 实测同族环境约束）：沙箱真实物理鼠标点击被前台锁吞
/// （SetForegroundWindow 环境锁），本测走 InvokePattern=命令链验证（captain 认可的
/// 桌面通道降级口径）；真实用户端复测=qa-20 桌面通道职责。
/// </summary>
public sealed class BrowseItemActionsDesktopTests
{
    [WpfFact]
    public void Browse_Item_Buttons_Present_And_Command_Chain_Works()
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

            // 导航到浏览页（InvokePattern=命令链口径）
            var navBrowse = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "MainShell_Nav_BrowseButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navBrowse);
            navBrowse!.AsButton().Invoke();

            // 实物钮在位（详情+下载）
            var detailBtn = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "WorkshopBrowsePage_Item_DetailButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(detailBtn);
            var downloadBtn = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "WorkshopBrowsePage_Item_DownloadButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(downloadBtn);

            // 【详情链】点第一条「详情」→ModDetailPage 真实标题出现+示例横幅隐藏
            detailBtn!.AsButton().Invoke();
            var title = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "ModDetailPage_TitleText"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(title); // 真实详情页就位（TryLoad 已接 id)
            // 示例横幅：CurrentId 非空=IsSampleMode false → 横幅 COLLAPSED（可见性=null 断言）
            Thread.Sleep(800); // TryLoad 异步加载一拍
            var sampleBanner = window!.FindFirstDescendant(
                cf => cf.ByAutomationId("ModDetailPage_SampleBanner"));
            Assert.True(sampleBanner is null || !sampleBanner.IsAvailable,
                "示例横幅应在真实 id 接线后隐藏");

            // 【下载链】回浏览页点「下载」→下载页出现任务行
            navBrowse = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "MainShell_Nav_BrowseButton"),
                TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navBrowse);
            navBrowse!.AsButton().Invoke();
            downloadBtn = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "WorkshopBrowsePage_Item_DownloadButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(downloadBtn);
            downloadBtn!.AsButton().Invoke();

            var row = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window!, "DownloadsPage_TaskList_Item"),
                TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(row); // 队列出现任务（入队+行注册成功）
        }
        finally
        {
            try { app?.Close(); } catch { /* 进程清理兜底 */ }
            try { app?. Kill(); } catch { }
        }
    }
}
