using System.Text;
using System.Diagnostics;
using System.IO;
using System.Windows;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;
using Xunit;
using Application = FlaUI.Core.Application;
using Window = FlaUI.Core.AutomationElements.Window;

namespace Swdm2.Spike.FlaUiTests;

/// <summary>
/// t4 spike 冒烟测试：进程外启动被测 exe + 真实鼠标/键盘输入 + 断言（无打桩）。
/// 验证 FlaUI 5.0.0 UIA3 对 WPF-UI 4.3.0 控件与自绘控件的可达性（Q2）+ 截图链路（Q3）。
/// </summary>
public sealed class SpikeSmokeTests : IDisposable
{
    private readonly Application _app;
    private readonly UIA3Automation _automation = new();
    private readonly Window _window;
    private readonly string _testName;

    private static readonly string Artifacts = Path.Combine(AppContext.BaseDirectory, "TestArtifacts");

    // 进程外启动被测 exe：swdm2/spike/SpikeWpf/bin/Debug/net8.0-windows/Swdm2Spike.exe
    private static readonly string SpikeExe = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "..", "..", "..", "..", "SpikeWpf", "bin", "Debug", "net8.0-windows", "Swdm2Spike.exe"));

    public SpikeSmokeTests()
    {
        _testName = "setup";
        Directory.CreateDirectory(Artifacts);
        Assert.True(File.Exists(SpikeExe), $"被测 exe 不存在（先 build SpikeWpf）：{SpikeExe}");

        _app = Application.Launch(SpikeExe);
        _window = Retry.WhileNull(
            () => _automation.GetDesktop().FindFirstDescendant(cf => cf.ByAutomationId("MainWindow"))?.AsWindow(),
            TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(0.2)).Result
            ?? throw new InvalidOperationException("主窗口 20s 内未出现（WPF-UI 初始化失败？）");
        Assert.Equal("MainWindow", _window.AutomationId);  // 窗口自动化 ID = 设置值
    }

    /// <summary>Q2 核心数据：AutomationId 清单命中率（WPF-UI 控件 + 自绘控件各一）。</summary>
    [WpfFact]
    public void AutomationIdChecklist_AllExpectedControlsReachable()
    {
        var expected = new[]
        {
            // ui:TitleBar 自身不暴露 AutomationId → 以其模板部件固定 id 为契约（spike 实证）
            "TitleBarCloseButton",
            "SpikeSearchBox", "SpikeSearchButton", "SpikeResultList",
            // ui:Card 自身不暴露 AutomationId → 外层容器 Grid 承载（A7 修正）
            "SpikeSelfCard", "SpikeCardButton"           // 自绘控件 UserControl 完全可达
        };
        var missed = new List<string>();
        foreach (var id in expected)
        {
            var el = _window.FindFirstDescendant(cf => cf.ByAutomationId(id));
            if (el == null) missed.Add(id);
        }
        DumpTree();   // 诊断：TitleBar/Card 的 UIA 表面
        Assert.True(missed.Count == 0, "缺失 AutomationId: " + string.Join(", ", missed));
    }

    /// <summary>主旅程 A：ValuePattern 中文输入 + 真实物理点击搜索按钮 → 列表出现结果。</summary>
    [WpfFact]
    public void Search_饥荒_ValuePatternEnter_PhysicalClick_ShowsResult()
    {
        var box = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeSearchBox")).AsTextBox();
        Assert.NotNull(box);
        box.Focus();
        box.Enter("饥荒");                       // 路径 A：ValuePattern 直设 Unicode
        Assert.Equal("饥荒", box.Text);         // 值真进了控件

        var btn = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeSearchButton")).AsButton();
        Assert.NotNull(btn);

        // 真实物理点击（非 Invoke 语义级调用）
        ClickPhysically(btn);

        var list = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeResultList")).AsListBox();
        Assert.NotNull(list);
        // 轮询自己的关键字而非首项（跨测试共享列表，防脏数据误判——显式等待）
        var hit = Retry.WhileNull(
            () => list.Items.FirstOrDefault(i => (i.Name ?? string.Empty).Contains("饥荒")),
            TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
        Assert.NotNull(hit);
        Assert.Contains("饥荒", hit!.Name ?? string.Empty);
    }

    /// <summary>主旅程 B：真实回车键触发搜索（VK_RETURN 注入，非命令直调）。</summary>
    [WpfFact]
    public void Search_RealReturnKey_TriggersSearchFromTextBox()
    {
        var box = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeSearchBox")).AsTextBox();
        Assert.NotNull(box);
        ClickPhysically(box);                     // 真实点击使文本框获得键盘焦点（用户语义）
        // Enter() 对含空格/撇号的 ASCII 会被吞（实测 "Don't Starve"→"Don'tStarve"），故用无特殊字符词
        box.Enter("CaveStory");

        var list2 = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeResultList")).AsListBox();
        Assert.NotNull(list2);

        // 诊断 + 重试：真实回车注入（Press/Release 真按键路径），最多 3 次尝试
        FlaUI.Core.AutomationElements.ListBoxItem? hit2 = null;
        for (var attempt = 1; attempt <= 3 && hit2 == null; attempt++)
        {
            var before = list2.Items.Length;
            File.AppendAllText(Path.Combine(Artifacts, "spike_return_diag.txt"),
                $"[{DateTime.Now:HH:mm:ss}] attempt={attempt} count={list2.Items.Length} text=[{box.Text}] before={before}{Environment.NewLine}");
            Keyboard.Press(VirtualKeyShort.RETURN);
            Keyboard.Release(VirtualKeyShort.RETURN);
            hit2 = Retry.WhileNull(
                () => list2.Items.FirstOrDefault(i => (i.Name ?? string.Empty).Contains("CaveStory")),
                TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(0.2)).Result;
        }
        Assert.True(hit2 != null, $"3 次真实回车注入均未触发搜索（最后一次后 count={list2.Items.Length}）");
        Assert.Contains("CaveStory", hit2!.Name ?? string.Empty);
    }

    /// <summary>弹窗路径：真实点击自绘卡片按钮 → MessageBox → 像用户一样点确定（#255，无打桩）。</summary>
    [WpfFact]
    public void MessageBox_RealClickOk_ClosesDialog()
    {
        var btn = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeCardButton"))?.AsButton();
        Assert.NotNull(btn);
        btn.Focus();
        ClickPhysically(btn);

        // MessageBox 是 ControlType.Window：找模态子窗口（不替换实现）
        var dialog = Retry.WhileNull(
            () => _window.ModalWindows.FirstOrDefault(w => w.Name == "提示"),
            TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
        Assert.NotNull(dialog);

        var okBtn = dialog!.FindFirstDescendant(cf => cf.ByName("确定").Or(cf.ByName("OK")))?.AsButton();
        Assert.NotNull(okBtn);
        ClickPhysically(okBtn!);

        var closed = Retry.WhileTrue(() => _window.ModalWindows.Any(w => w.Name == "提示"),
            TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2));
        Assert.False(closed.TimedOut, "10s 内弹窗未关闭（确定按钮真实点击失败？）");
    }

    /// <summary>Q3：截图链路——Capture.Element + MainScreen 落盘且文件非空。</summary>
    [WpfFact]
    public void Screenshot_ElementAndScreen_ProduceNonEmptyFiles()
    {
        var list = _window.FindFirstDescendant(cf => cf.ByAutomationId("SpikeResultList"));
        Assert.NotNull(list);

        var elementShot = Capture.Element(list);
        var elementPath = Path.Combine(Artifacts, "spike_element_resultlist.png");
        elementShot.ToFile(elementPath);

        var screenShot = Capture.MainScreen();
        var screenPath = Path.Combine(Artifacts, "spike_screen_full.png");
        screenShot.ToFile(screenPath);

        Assert.True(new FileInfo(elementPath).Length > 10_000, "元素截图过小/为空");
        Assert.True(new FileInfo(screenPath).Length > 20_000, "全屏截图过小/为空");
    }

    /// <summary>真实物理点击；控件无 ClickablePoint（自绘卡片内容、模板深处）时退到包围矩形中心。</summary>
    private static void ClickPhysically(FlaUI.Core.AutomationElements.AutomationElement element)
    {
        System.Drawing.Point pt;
        try
        {
            pt = element.GetClickablePoint();
        }
        catch (FlaUI.Core.Exceptions.NoClickablePointException)
        {
            var r = element.BoundingRectangle;
            pt = new System.Drawing.Point(r.X + r.Width / 2, r.Y + r.Height / 2);
        }
        Mouse.MoveTo(pt);
        Mouse.Click(MouseButton.Left);
    }

    /// <summary>UIA 树诊断：前 4 层子树的 Name/AutomationId/ControlType 落盘（供架构裁决）。</summary>
    private void DumpTree()
    {
        var sb = new StringBuilder();
        sb.AppendLine($"window: name=[{_window.Name}] id=[{_window.AutomationId}] type={_window.ControlType}");
        DumpChildren(_window, 0, 4, sb);
        File.WriteAllText(Path.Combine(Artifacts, "spike_tree.txt"), sb.ToString());
    }

    private static void DumpChildren(AutomationElement parent, int depth, int maxDepth, StringBuilder sb)
    {
        if (depth >= maxDepth) return;
        foreach (var child in parent.FindAllChildren())
        {
            sb.AppendLine(new string(' ', depth * 2)
                + $"- name=[{child.Name}] id=[{child.AutomationId}] type={child.ControlType}");
            DumpChildren(child, depth + 1, maxDepth, sb);
        }
    }

    public void Dispose()
    {
        // 失败现场截图（Assert 异常后 Dispose 仍被 xUnit 调用）
        try
        {
            var shot = Capture.MainScreen();
            shot.ToFile(Path.Combine(Artifacts, $"fail_{_testName}_{DateTime.Now:yyyyMMdd_HHmmss}.png"));
        }
        catch { /* 截图失败不影响清理 */ }

        try { _window?.Close(); } catch { }
        try { _app?.Close(); } catch { try { _app?.Kill(); } catch { } }
        try { _automation?.Dispose(); } catch { }
        // 兜底：清残留进程
        foreach (var p in Process.GetProcessesByName("Swdm2Spike"))
        {
            try { p.Kill(); p.WaitForExit(2000); } catch { }
        }
    }
}
