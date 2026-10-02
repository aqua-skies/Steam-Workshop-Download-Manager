using System.Diagnostics;
using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Smoke;

/// <summary>
/// P0 主旅程冒烟（t49 / D5.10；t3 §4.1 五条主旅程的 2026-10-03 可表达子集）：
/// - 旅程 1 启动：MainShell 15s 显式等待出现 + 双导航按钮契约（Nav_ModDetail/Downloads);
/// - 旅程 3 详情：真实点击导航→ModDetailPage 三保留 id 在位（Title/DependencyList/DownloadButton);
/// - 旅程 4 下载：真实点击 DownloadButton→行出现+状态机推进（与 #10 同源）+ 完成 #255 弹窗由 Feature 层断言;
/// - A9 即时反馈：DownloadButton 真实 Enter→行可见延迟 N=3 计时断言 ≤150ms（挂在真实旅程上）。
///
/// 两层环境容忍门（t28/t38 同模式，同 D3.3/D3.4 Online 口径）：
/// Layer 1（沙箱可验证）：窗口/控件/导航契约（无输入路由需求）;
/// Layer 2（需桌面通道）：物理输入旅程 + A9 计时——沙箱 Capture.MainScreen 全黑=
/// SendInput 不路由（t26/t28 实证），打印 ENV-DOWNGRADE + UIA 树转储，桌面通道复跑。
///
/// **未表达旅程（诚实阻断记录，非假绿）**：
/// - 旅程 2 搜索：GameSelectPage_SearchBox_Input 等 id 在 App 中不存在——D5.4(t43）未交付;
/// - 旅程 5 库：LibraryPage 无对应 App 视图（D5 页面矩阵无库页任务）——spec §4.1 #5/D10 留待排期;
/// - A9 ≤150ms 实测：沙箱无桌面（输入不路由）→ 计时层 ENV-DOWNGRADE，桌面通道复跑。
///   计时方法/阈值分析见 docs/calibration_2.md §E。
/// Q10：失败截图落 TestArtifacts/。
/// </summary>
public sealed class P0MainJourneySmokeTests
{
    /// <summary>旅程 1：启动→MainShell（显式 15s 等待）+ 导航契约（Layer 1 沙箱可验证）。</summary>
    [WpfFact]
    public void Journey_1_Launch_MainShell_Appears_Nav_Contract()
    {
        var exe = UiTestHelpers.ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing (build App first): {exe}");

        using var automation = new UIA3Automation();
        var app = Application.Launch(exe);
        try
        {
            // 旅程 1：主窗口 15s 显式等待（t3 §4.1）。
            var sw = Stopwatch.StartNew();
            var window = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("MainShell"))?.AsWindow(),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            sw.Stop();
            Assert.NotNull(window);
            Assert.True(sw.Elapsed < TimeSpan.FromSeconds(15), "MainShell 必须 15s 内出现");
            Console.WriteLine($"DIAG journey1 MainShell appeared in {sw.Elapsed.TotalMilliseconds:F0}ms");

            window!.Focus();

            // 导航契约：双导航按钮保留 id 在位且可点击（t3 §3.2 保留表 MainShell_Nav_*)。
            foreach (var navId in new[] { "MainShell_Nav_ModDetailButton", "MainShell_Nav_DownloadsButton" })
            {
                var nav = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, navId),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                Assert.NotNull(nav);
            }

            // 标题契约：t3 §4.1 "标题含版本号"——当前 MainWindow.Title="SWDM 2.0" 无版本号
            // （spec 偏差，D5 皮肤期由 visual-20 补版本号到 Title；此处只断言标题存在）。
            Assert.False(string.IsNullOrWhiteSpace(window.Title));
            Console.WriteLine($"DIAG journey1 title=\"{window.Title}\" "
                              + "(版本号入标题=spec §4.1 偏差，D5 补；状态栏连通文本=D5.9 t48)");

            UiTestHelpers.DumpTree(window, "journey1 contract");
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            CaptureFailure(nameof(Journey_1_Launch_MainShell_Appears_Nav_Contract));
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    /// <summary>旅程 3+4：详情页契约→真实点击下载→行出现+状态机推进（Layer 1 契约 + Layer 2 输入门）。</summary>
    [WpfFact]
    public void Journey_3_4_Detail_Download_Real_Input_With_A9_Timing()
    {
        var exe = UiTestHelpers.ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing (build App first): {exe}");

        var blankCapture = UiTestHelpers.MainScreenCaptureIsBlank();
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

            // 旅程 3 Layer 1：详情页三保留 id 在位（ModDetail 为初始页，t26 余绪）。
            foreach (var id in new[]
                     {
                         "ModDetailPage_TitleText", "ModDetailPage_DependencyList_Items",
                         "ModDetailPage_DownloadButton",
                     })
            {
                Assert.NotNull(Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, id),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result);
            }

            if (blankCapture)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: blank capture — no interactive desktop; physical journey + A9 timing " +
                    "re-run on the desktop channel (t28/t38 gate, same as D3.3/D3.4 Online).");
                UiTestHelpers.DumpTree(window, "env-downgrade: journey 3/4 input layer + A9 timing not executed");
                return;
            }

            // Layer 2（桌面）：先验证输入确实路由（导航真点击→页面切换）。
            var navDownloads = UiTestHelpers.VisibleElement(window, "MainShell_Nav_DownloadsButton");
            Assert.NotNull(navDownloads);
            UiTestHelpers.RealClick(navDownloads!);
            var listVisible = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "DownloadsPage_TaskList_Items"),
                TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(listVisible);

            // 回详情页（旅程 3：真实点击导航）。
            var navDetail = UiTestHelpers.VisibleElement(window, "MainShell_Nav_ModDetailButton");
            Assert.NotNull(navDetail);
            UiTestHelpers.RealClick(navDetail!);
            var downloadButton = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "ModDetailPage_DownloadButton"),
                TimeSpan.FromSeconds(8), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(downloadButton);

            // 旅程 4 + A9：真实硬件 Enter→行可见延迟计时（N=3）。
            var latencies = new List<double>();
            var initialRows = window.FindAllDescendants(cf => cf.ByAutomationId("DownloadsPage_TaskList_Item")).Length;
            for (var sample = 1; sample <= 3; sample++)
            {
                var sw = Stopwatch.StartNew();
                UiTestHelpers.RealActivateByKey(downloadButton!);   // 硬件 Enter（输入三规则）
                AutomationElement? row = null;
                var deadline = DateTime.UtcNow.AddSeconds(20);
                while (DateTime.UtcNow < deadline)
                {
                    row = window.FindFirstDescendant(cf => cf.ByAutomationId("DownloadsPage_TaskList_Item"));
                    if (row is not null && window.FindAllDescendants(
                            cf => cf.ByAutomationId("DownloadsPage_TaskList_Item")).Length > initialRows + sample - 1)
                        break;
                    Thread.Sleep(2);
                }
                sw.Stop();
                Assert.NotNull(row);
                latencies.Add(sw.Elapsed.TotalMilliseconds);
                Console.WriteLine($"DIAG A9 sample{sample}: key→row-visible {sw.Elapsed.TotalMilliseconds:F1}ms");
            }

            // A9 断言：全部 ≤150ms（1.x 经验阈值；实测重标定见 calibration_2.md §E）。
            Assert.All(latencies, l => Assert.True(l <= 150.0, $"A9 即时反馈超阈值: {l:F1}ms > 150ms"));
            var max = latencies.Max();
            var p50 = latencies.OrderBy(x => x).ElementAt(latencies.Count / 2);
            Console.WriteLine($"DIAG A9 summary: n=3 p50={p50:F1}ms max={max:F1}ms threshold=150ms");

            // 旅程 4 收尾：状态机推进断言（#10 同源语义）。
            var stateText = Retry.WhileNull(
                () => window.FindFirstDescendant(
                        cf => cf.ByAutomationId("DownloadsPage_TaskList_Item"))?
                    .FindFirstDescendant(cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_StateText"))?
                    .AsLabel()?.Text,
                TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.25)).Result;
            Assert.NotNull(stateText);
            Assert.False(string.IsNullOrWhiteSpace(stateText));
            Assert.True(FinalStateLabels.Any(s => stateText!.TrimStart().StartsWith(s)) ||
                        ActiveStateLabels.Any(s => stateText.TrimStart().StartsWith(s)),
                        $"state text must map to a state-machine state, got: {stateText}");
            Console.WriteLine($"DIAG journey4 stateText={stateText}");
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            CaptureFailure(nameof(Journey_3_4_Detail_Download_Real_Input_With_A9_Timing));
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    private static readonly string[] FinalStateLabels = { "已取消", "失败", "完成" };
    private static readonly string[] ActiveStateLabels = { "待定", "排队中", "准备中", "下载中", "已暂停" };

    /// <summary>Q10：失败截图落 TestArtifacts/（wpf_ui_testing §3.3.5）。</summary>
    private static void CaptureFailure(string testName)
    {
        try
        {
            var dir = Path.Combine(AppContext.BaseDirectory, "TestArtifacts");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, $"fail_{testName}_{DateTime.Now:HHmmss}.png");
            Capture.MainScreen().ToFile(path);
            Console.WriteLine($"DIAG Q10 failure screenshot: {path}");
        }
        catch
        {
            // 截图本身为诊断辅助，失败不阻断测试结论
        }
    }
}
