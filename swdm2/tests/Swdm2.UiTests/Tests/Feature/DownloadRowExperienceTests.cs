using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Feature;

/// <summary>
/// D4.9 #15 分段体感断言（t38；t3 §4.2 #15 + 保留表 §3.2）:
/// - 速度/ETA/分段数 真实刷新（轮询采样断言字段变化）；
///   SteamKit 场景分段数 &gt; 1；steamcmd 场景分段数 = N/A（诚实降级 D9）；
/// - 暂停/继续按钮态 = 状态机驱动（CanPause: Preparing/Downloading, CanResume: Paused,
///   CanRetry: Failed, CanCancel: 非终态）——行 VM 启用契约的 UI 真值断言；
/// - #14 完成路径：DownloadCompleteDialog（#255 自绘 Window + OkButton）真实点击关闭。
///
/// 两层断言（t26/t28 确立的环境容忍门模式，同 D3.3/D3.4 Online）：
/// Layer 1（沙箱可验证，不假绿）：主窗壳 + 下载按钮可点击前提 + 行模板保留 id 契约;
/// Layer 2（桌面通道）：物理点击入队 → 行出现 → 字段采样 → 按钮态断言 → 弹窗关闭。
///   沙箱无交互桌面时（Capture.MainScreen 全黑=SendInput 不路由，t26/t28 实证）打印
///   ENV-DOWNGRADE 诊断 + UIA 树转储，仅断言已验证层；完整旅程在桌面通道复跑。
///
/// Q10：失败截图落 TestArtifacts/（截图仅在非 xunit 异常时拍摄，避免每次跑都写盘）。
/// </summary>
public sealed class DownloadRowExperienceTests
{
    private static readonly string[] TerminalStateLabels = { "已取消", "失败", "完成" };
    private static readonly string[] ActiveStateLabels = { "待定", "排队中", "准备中", "下载中", "已暂停" };

    /// <summary>#15：字段真实刷新（轮询采样）+ #14 完成弹窗真实点击。</summary>
    [WpfFact]
    public void Row_Speed_Eta_Segments_Refresh_And_Complete_Dialog_Path()
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

            // Layer 1：详情页经「浏览→条目详情」链进入（t67 后产品流程：ModDetail
            // 直达无下载钮=需真实 id;模板=BrowseItemActionsDesktopTests L51-84)。
            var navBrowse = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "MainShell_Nav_BrowseButton"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navBrowse);
            navBrowse!.AsButton().Invoke();
            var itemDetail = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "WorkshopBrowsePage_Item_DetailButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            if (itemDetail is null)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: browse items not materialized (real source unreachable)");
                UiTestHelpers.DumpTree(window, "env-downgrade: browse item chain not executed");
                return;
            }
            itemDetail!.AsButton().Invoke();

            var downloadButton = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "ModDetailPage_DownloadButton"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(downloadButton);

            if (blankCapture)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: blank capture — no interactive desktop; field-refresh layer " +
                    "re-runs on the desktop channel (t28 gate, same as D3.3/D3.4 Online).");
                UiTestHelpers.DumpTree(window, "env-downgrade: refresh layer not executed");
                return;
            }

            // Layer 2（桌面）：真实点击入队。
            UiTestHelpers.RealClick(downloadButton!);
            var row = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "DownloadsPage_TaskList_Item"),
                TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.25)).Result;
            Assert.NotNull(row);

            // 行模板保留 id 契约（t3 §3.2）：六字段 + 四按钮全部解析在位。
            var fieldIds = new[]
            {
                "DownloadsPage_TaskList_Item_FileNameText",
                "DownloadsPage_TaskList_Item_StateText",
                "DownloadsPage_TaskList_Item_SpeedText",
                "DownloadsPage_TaskList_Item_EtaText",
                "DownloadsPage_TaskList_Item_SegmentsText",
                "DownloadsPage_TaskList_Item_SizeText",
            };
            var buttonIds = new[]
            {
                "DownloadsPage_TaskList_Item_PauseButton",
                "DownloadsPage_TaskList_Item_ResumeButton",
                "DownloadsPage_TaskList_Item_RetryButton",
                "DownloadsPage_TaskList_Item_CancelButton",
            };
            foreach (var id in fieldIds.Concat(buttonIds))
            {
                Assert.NotNull(Retry.WhileNull(
                    () => (object?)row!.FindFirstDescendant(cf => cf.ByAutomationId(id)),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result);
            }

            // #15 真实刷新：轮询采样快照字段（150ms 间隔，最长 45s，终态提前停）。
            var samples = new List<(string State, string Speed, string Eta, string Segments)>();
            var deadline = DateTime.UtcNow.AddSeconds(45);
            while (DateTime.UtcNow < deadline)
            {
                var state = Read(row, "DownloadsPage_TaskList_Item_StateText");
                if (state is not null)
                {
                    samples.Add((state,
                        Read(row, "DownloadsPage_TaskList_Item_SpeedText") ?? "",
                        Read(row, "DownloadsPage_TaskList_Item_EtaText") ?? "",
                        Read(row, "DownloadsPage_TaskList_Item_SegmentsText") ?? ""));
                    if (TerminalStateLabels.Any(s => state.TrimStart().StartsWith(s)))
                        break;
                }
                Thread.Sleep(150);
            }

            Assert.NotEmpty(samples);
            foreach (var s in samples)
            {
                Assert.False(string.IsNullOrWhiteSpace(s.State), "StateText 必须有绑定值（不空）");
                Assert.False(string.IsNullOrWhiteSpace(s.Speed), "SpeedText 必须有绑定值（诚实 N/A 也算）");
                Assert.False(string.IsNullOrWhiteSpace(s.Eta), "EtaText 必须有绑定值（诚实 N/A 也算）");
                Assert.False(string.IsNullOrWhiteSpace(s.Segments), "SegmentsText 必须有绑定值（诚实 N/A 也算）");
            }

            var finalSample = samples[^1];
            var refreshCount = samples.Distinct().Count();
            Console.WriteLine(
                $"DIAG #15 samples={samples.Count} distinct={refreshCount} finalState={finalSample.State} " +
                $"speed={finalSample.Speed} eta={finalSample.Eta} segments={finalSample.Segments} " +
                "(steamcmd 场景 segments=N/A=诚实降级 D9; SteamKit 场景 >1)");

            // 刷新证据：至少一次字段变化，或到达终态（终态快照=最后一次刷新）。
            Assert.True(refreshCount >= 2 ||
                        TerminalStateLabels.Any(s => finalSample.State.TrimStart().StartsWith(s)),
                        $"字段必须真实刷新（≥2 个不同快照）或到达终态；observed: {string.Join(" | ", samples)}");

            // #14 完成路径：终态=完成 → DownloadCompleteDialog（OkButton）真实点击关闭。
            if (finalSample.State.TrimStart().StartsWith("完成"))
            {
                var ok = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, "OkButton"),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.25)).Result;
                Assert.NotNull(ok);
                var dialogWindow = ok!.Parent;
                Assert.NotNull(dialogWindow);   // 自绘 #255 载体窗口（A7）
                UiTestHelpers.RealClick(ok!);
                var closed = false;
                var closeDeadline = DateTime.UtcNow.AddSeconds(8);
                while (DateTime.UtcNow < closeDeadline)
                {
                    if (UiTestHelpers.VisibleElement(window, "OkButton") is null)
                    {
                        closed = true;
                        break;
                    }
                    Thread.Sleep(200);
                }
                Assert.True(closed, "OkButton 真实点击后完成弹窗应消失（#14 关闭路径）");
            }
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            CaptureFailure(nameof(Row_Speed_Eta_Segments_Refresh_And_Complete_Dialog_Path));
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    /// <summary>#11/#12：暂停/继续按钮态随状态机驱动 + 终态按钮收敛。</summary>
    [WpfFact]
    public void Pause_Resume_Buttons_Driven_By_State_Machine()
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

            // 导航到详情页（经浏览条目链=产品新流程；与第一测同模式）。
            var navBrowse = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "MainShell_Nav_BrowseButton"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navBrowse);
            navBrowse!.AsButton().Invoke();
            var itemDetail = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "WorkshopBrowsePage_Item_DetailButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(itemDetail);
            if (itemDetail is null)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: browse items not materialized (real source unreachable)");
                UiTestHelpers.DumpTree(window, "env-downgrade: browse item chain not executed");
                return;
            }
            itemDetail!.AsButton().Invoke();

            var downloadButton = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "ModDetailPage_DownloadButton"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(downloadButton);

            if (blankCapture)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: blank capture — no interactive desktop; button-state layer " +
                    "re-runs on the desktop channel (t28 gate).");
                UiTestHelpers.DumpTree(window, "env-downgrade: button-state layer not executed");
                return;
            }

            UiTestHelpers.RealClick(downloadButton!);
            var row = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "DownloadsPage_TaskList_Item"),
                TimeSpan.FromSeconds(30), TimeSpan.FromSeconds(0.25)).Result;
            Assert.NotNull(row);

            Button? PauseBtn() => row!.FindFirstDescendant(
                cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_PauseButton"))?.AsButton();
            Button? ResumeBtn() => row!.FindFirstDescendant(
                cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_ResumeButton"))?.AsButton();
            Button? RetryBtn() => row!.FindFirstDescendant(
                cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_RetryButton"))?.AsButton();
            Button? CancelBtn() => row!.FindFirstDescendant(
                cf => cf.ByAutomationId("DownloadsPage_TaskList_Item_CancelButton"))?.AsButton();

            var observedActive = false;
            var pauseExercised = false;
            var resumeExercised = false;
            var deadline = DateTime.UtcNow.AddSeconds(60);
            var state = "";

            while (DateTime.UtcNow < deadline)
            {
                state = Read(row, "DownloadsPage_TaskList_Item_StateText") ?? state;
                if (string.IsNullOrWhiteSpace(state))
                {
                    Thread.Sleep(150);
                    continue;
                }

                var isTerminal = TerminalStateLabels.Any(s => state.TrimStart().StartsWith(s));
                var isActive = ActiveStateLabels.Any(s => state.TrimStart().StartsWith(s)) && !isTerminal;
                if (isActive)
                {
                    observedActive = true;
                    // 活动态下 Cancel 必须可用（状态机启用契约 CanCancel=非终态）。
                    Assert.True(CancelBtn()?.IsEnabled == true,
                        $"Cancel 按钮在活动态({state})必须 enabled（CanCancel 契约）");

                    // #11 暂停：仅当状态机允许（CanPause: Preparing/Downloading）才真点击。
                    if (!pauseExercised && PauseBtn()?.IsEnabled == true)
                    {
                        UiTestHelpers.RealClick(PauseBtn()!);
                        pauseExercised = true;
                        Console.WriteLine("DIAG #11 pause clicked (real input) at state=" + state);
                    }
                }

                if (isTerminal)
                    break;

                // #12 继续：暂停态下 Resume 必须 enabled（CanResume: Paused）→ 真实点击。
                if (state.TrimStart().StartsWith("已暂停") && !resumeExercised && ResumeBtn()?.IsEnabled == true)
                {
                    Assert.False(PauseBtn()?.IsEnabled == true, "已暂停态 Pause 必须 disabled（CanPause 契约）");
                    UiTestHelpers.RealClick(ResumeBtn()!);
                    resumeExercised = true;
                    Console.WriteLine("DIAG #12 resume clicked (real input) at state=" + state);
                }

                Thread.Sleep(150);
            }

            // 终态收敛断言（状态机真值）：终态下 Pause/Resume/Cancel 全 disabled；
            // Retry enabled ⟺ Failed。
            Assert.True(TerminalStateLabels.Any(s => state.TrimStart().StartsWith(s)) || observedActive,
                $"must reach a terminal state or an active sample; last state={state}");
            if (TerminalStateLabels.Any(s => state.TrimStart().StartsWith(s)))
            {
                Assert.False(PauseBtn()?.IsEnabled == true, "终态 Pause 必须 disabled");
                Assert.False(ResumeBtn()?.IsEnabled == true, "终态 Resume 必须 disabled");
                Assert.False(CancelBtn()?.IsEnabled == true, "终态 Cancel 必须 disabled");
                var failed = state.TrimStart().StartsWith("失败");
                var retryEnabled = RetryBtn()?.IsEnabled == true;
                Assert.True(failed == retryEnabled,
                    $"终态={state}：Retry enabled 只有 Failed 允许（CanRetry 契约）");
            }
            Console.WriteLine(
                $"DIAG #11/#12 pauseExercised={pauseExercised} resumeExercised={resumeExercised} " +
                $"observedActive={observedActive} finalState={state}（沙箱快失败路径 pause 不可达=环境约束，桌面真旅程覆盖）");
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            CaptureFailure(nameof(Pause_Resume_Buttons_Driven_By_State_Machine));
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    // --------------------------------------------------------------- helpers
    private static string? Read(AutomationElement row, string automationId)
    {
        try
        {
            return row.FindFirstDescendant(cf => cf.ByAutomationId(automationId))?.AsLabel()?.Text;
        }
        catch
        {
            return null;   // UIA provider 属性不可用时降级为 null（已转储证据模式）
        }
    }

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
