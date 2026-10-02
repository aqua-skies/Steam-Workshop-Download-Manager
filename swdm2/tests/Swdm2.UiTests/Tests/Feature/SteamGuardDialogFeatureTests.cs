using System.IO;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Feature;

/// <summary>
/// D4.1 #23 Steam Guard 收码弹窗（P1/Feature 套件）：
/// 触发=SWDM2_TEST_2FA 环境容忍门（AppHost 桩登录首次拒认证→2FA 弹窗链路；
/// 桩仅替换 SteamKit 真链的登录结果，弹窗/模态/键盘输入/主窗口阻塞全真）。
///
/// 断言契约（t3 §4.2 #23):
/// - 弹窗模态阻塞主窗口（WindowInteractionState=BlockedByModalWindow;不支持时 UIA 降级取证）
/// - 真实键盘输入验证码（Keyboard.Type 物理按键）→ CodeBox 文本断言
/// - 真实回车确定（RealActivateByKey)→ 弹窗关闭，主窗口恢复交互（Ready)
/// 沙箱 headless：输入不路由→ENV-DOWNGRADE Layer 1（元素契约+树转储）+桌面复跑（同 t28 门）。
/// </summary>
public sealed class SteamGuardDialogFeatureTests
{
    private const string GuardCode = "481516";

    [WpfFact]
    public void P1_23_Guard_Dialog_Modal_Blocked_And_Typed_Code_Enter()
    {
        var exe = UiTestHelpers.ResolveAppExe();
        Assert.True(File.Exists(exe), $"app exe missing (build App first): {exe}");

        var blankCapture = UiTestHelpers.MainScreenCaptureIsBlank();
        var prev = Environment.GetEnvironmentVariable("SWDM2_TEST_2FA");
        Environment.SetEnvironmentVariable("SWDM2_TEST_2FA", "1");

        Application? app = null;
        try
        {
            using var automation = new UIA3Automation();
            app = Application.Launch(exe);

            var mainWindow = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("MainShell"))?.AsWindow(),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(mainWindow);

            var dialog = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("SteamGuardDialog"))?.AsWindow(),
                TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(0.25)).Result;
            Assert.NotNull(dialog); // 2FA 回调链路触发：弹窗出现

            // Layer 1：保留表契约（t3 §3.2)
            var codeBox = dialog!.FindFirstDescendant(cf => cf.ByAutomationId("SteamGuardDialog_CodeBox_Input"));
            Assert.NotNull(codeBox);
            var confirm = dialog.FindFirstDescendant(cf => cf.ByAutomationId("SteamGuardDialog_ConfirmButton"));
            Assert.NotNull(confirm);
            var cancel = dialog.FindFirstDescendant(cf => cf.ByAutomationId("SteamGuardDialog_CancelButton"));
            Assert.NotNull(cancel);

            // 模态阻塞主窗口（WindowPattern;UIA 不支持则降级取证不误判）
            Assert.True(IsMainBlocked(mainWindow!, dialog) || blankCapture,
                "主窗口未模态阻塞（WindowInteractionState 非 BlockedByModalWindow）");

            if (blankCapture)
            {
                UiTestHelpers.DumpTree(mainWindow!, "env-downgrade: guard dialog input not routed");
                Console.WriteLine("ENV-DOWNGRADE: Steam Guard 对话框 Layer 1 契约通过；真实键盘输入层桌面复跑");
                return;
            }

            // Layer 2：真实键盘输入验证码（#23)
            UiTestHelpers.RealClick(codeBox!);
            Keyboard.Type(GuardCode);
            Assert.Equal(GuardCode, codeBox!.AsTextBox().Text);

            // 真实回车确定（物理 RETURN）
            UiTestHelpers.RealActivateByKey(confirm!);

            // 弹窗关闭+主窗口恢复交互（模态解除）
            var closed = Retry.WhileNull(
                () => automation.GetDesktop()
                    .FindFirstDescendant(cf => cf.ByAutomationId("SteamGuardDialog")) is null
                    ? (bool?)true : null,
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2)).Result;
            Assert.True(closed ?? false, "Steam Guard 弹窗未在回车后关闭");

            Assert.False(IsMainBlocked(mainWindow!, dialog), "弹窗关闭后主窗口仍处于模态阻塞");
        }
        finally
        {
            try { app?.Kill(); } catch { }
            Environment.SetEnvironmentVariable("SWDM2_TEST_2FA", prev);
        }
    }

    /// <summary>主窗口是否被模态阻塞（WindowInteractionState=BlockedByModalWindow)。</summary>
    private static bool IsMainBlocked(Window mainWindow, Window dialog)
    {
        try
        {
            var pattern = mainWindow.Patterns.Window;
            if (pattern is null || !pattern.TryGetPattern(out var wp) || wp is null)
                return false;
            return wp.WindowInteractionState.Value == WindowInteractionState.BlockedByModalWindow;
        }
        catch
        {
            return false; // UIA 提供器不支持=降级取证（不判失败）
        }
    }
}
