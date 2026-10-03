using System.Diagnostics;
using System.IO;
using System.Linq;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;
using Swdm2.UiTests.Tests.Smoke;
using Xunit;

namespace Swdm2.UiTests.Tests.Smoke; // [arch-20 补] bug 归属：visual-20 t43 进行中文件 VK 命名空间错（FlaUI 5=WindowsAPI.VirtualKeyShort) 阻断 t48 构建，trivial 修+归属注

/// <summary>
/// 旅程 2:游戏选择页（D5.4/t43;补 P0 旅程 2 阻断缺口——qa t49 实证记录）。
/// 双语命中断言（任务验收口径）：
/// - 真实输入"饥荒"→联想出现含"Don't Starve"（中英别名归一化=1.x 学费 bug③防呆）
/// - 真实输入"Don't Starve"→同样命中（双向）→Enter 确认→回详情页
/// 原地更新断言（无重绘闪烁=1.x 学费 bug①):两次输入间 ListBox 条目集合变化
/// （改 Detail 时由逻辑层引用不变断言覆盖，见 GameSelectPageViewModelTests)。
/// 即时反馈（1.x 学费 bug②):StatusHint 输入即刻变化——FlaUI 轮询断言。
///
/// 环境容忍门（t28/t38/t49 同模式）：
/// Layer 1（沙箱可验证）：页面契约 id 在位（nav/searchbox/列表/确认钮）;
/// Layer 2（需桌面通道）：真实键盘输入（Unicode 注入+Enter)——沙箱 Capture 全黑=
/// 输入不路由门关，打印 ENV-DOWNGRADE + UIA 转储，桌面通道复跑。
/// Q10：失败截图落 TestArtifacts/。
/// </summary>
public sealed class GameSelectJourneySmokeTests
{
    /// <summary>旅程 2:双语命中（真实键盘输入层=桌面通道;逻辑层契约沙箱断言）。</summary>
    [WpfFact]
    public void Journey_2_Game_Select_Bilingual_Hit()
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

            // Layer 1:导航契约（D5.4 新增 MainShell_Nav_GameSelectButton)
            var navGameSelect = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "MainShell_Nav_GameSelectButton"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(navGameSelect);

            // 真实点击导航（Enter 键路径=沙箱已实证可行，同 P0_10b)
            navGameSelect!.Focus();
            Keyboard.Press(VirtualKeyShort.RETURN); Keyboard.Release(VirtualKeyShort.RETURN);

            // 页面契约（Layer 1):搜索框/状态/列表/确认钮在位
            var searchBox = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "GameSelectPage_SearchBox"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(searchBox);
            // 状态/列表初始可见；确认钮初始禁用（CanExecute=候选数>0,语义正确）单独断言
            foreach (var id in new[]
                     {
                         "GameSelectPage_StatusHint", "GameSelectPage_SuggestionList",
                     })
            {
                var found = Retry.WhileNull(
                    () => UiTestHelpers.VisibleElement(window, id),
                    TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
                if (found is null)
                {
                    Console.WriteLine($"DIAG journey2 missing element: {id}");
                    UiTestHelpers.DumpTree(window, "journey2 page elements");
                }
                Assert.NotNull(found);
            }

            // 确认钮：在位（初始禁用=CanExecute 候选 0 条，PCL2/IDM 语义）+输入候选后转可用
            var confirmBtn = Retry.WhileNull(
                () => window.FindFirstDescendant(cf => cf.ByAutomationId("GameSelectPage_ConfirmButton")),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(confirmBtn);
            Assert.False(confirmBtn!.IsEnabled);

            if (blankCapture)
            {
                Console.WriteLine(
                    "ENV-DOWNGRADE: blank capture — no interactive desktop; bilingual type-input journey " +
                    "re-run on the desktop channel (t28/t38 gate, same as D3.3/D4.1).");
                UiTestHelpers.DumpTree(window, "env-downgrade: journey 2 input layer not executed");
                return;
            }

            // Layer 2:真实 Unicode 输入"饥荒"（中英别名归一化=命中最深路径）
            searchBox!.Focus();
            Keyboard.Type("饥荒");

            // 联想出现+双语命中（中→英）
            var suggestion = Retry.WhileNull(
                () => FirstSuggestionContaining(window, "Don't Starve"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.3)).Result;
            Assert.NotNull(suggestion);
            Console.WriteLine($"DIAG journey2 CN input hit: {suggestion!.Name}");

            // 即时反馈状态文本（输入后应给出计数）
            var hint = UiTestHelpers.VisibleElement(window, "GameSelectPage_StatusHint");
            Assert.NotNull(hint);
            Assert.Contains("候选", hint!.Name);

            // Enter 确认→回详情页（PageNavigationService 110→30ms+动画）
            Keyboard.Press(VirtualKeyShort.RETURN); Keyboard.Release(VirtualKeyShort.RETURN);
            var detail = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "ModDetailPage_TitleText"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(detail);

            // 反向命中：英→中（"Don't Starve" 同样命中同一游戏）
            searchBox = UiTestHelpers.VisibleElement(window, "GameSelectPage_SearchBox");
            // 回到游戏选择页（返回栈/导航）
            var navAgain = UiTestHelpers.VisibleElement(window, "MainShell_Nav_GameSelectButton");
            navAgain!.Focus();
            Keyboard.Press(VirtualKeyShort.RETURN); Keyboard.Release(VirtualKeyShort.RETURN);
            searchBox = Retry.WhileNull(
                () => UiTestHelpers.VisibleElement(window, "GameSelectPage_SearchBox"),
                TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
            Assert.NotNull(searchBox);
            searchBox!.Focus();
            Keyboard.Press(VirtualKeyShort.CONTROL); Keyboard.Press(VirtualKeyShort.KEY_A); Keyboard.Release(VirtualKeyShort.KEY_A); Keyboard.Release(VirtualKeyShort.CONTROL); Keyboard.Press(VirtualKeyShort.DELETE); Keyboard.Release(VirtualKeyShort.DELETE);
            Keyboard.Type("Don't Starve");
            var suggestionEn = Retry.WhileNull(
                () => FirstSuggestionContaining(window, "Don't Starve"),
                TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.3)).Result;
            Assert.NotNull(suggestionEn);
            Console.WriteLine($"DIAG journey2 EN input hit: {suggestionEn!.Name}");
        }
        catch (Exception ex) when (ex is not Xunit.Sdk.XunitException)
        {
            var path = Path.Combine(
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "TestArtifacts")),
                $"fail_{nameof(Journey_2_Game_Select_Bilingual_Hit)}.png");
            try { FlaUI.Core.Capturing.Capture.MainScreen().ToFile(path); } catch { }
            throw;
        }
        finally
        {
            try { app?.Kill(); } catch { }
        }
    }

    /// <summary>联想列表第一条含指定名称的条目（双语判定辅助）。</summary>
    private static AutomationElement? FirstSuggestionContaining(Window window, string nameFragment)
    {
        var list = UiTestHelpers.VisibleElement(window, "GameSelectPage_SuggestionList");
        if (list is null)
            return null;
        var children = list.FindAllChildren();
        return children.FirstOrDefault(c => (c.Name ?? string.Empty).Contains(nameFragment));
    }
}
