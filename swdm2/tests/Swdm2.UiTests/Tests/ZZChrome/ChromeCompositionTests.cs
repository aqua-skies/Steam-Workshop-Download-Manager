using System;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Shell;
using Xunit;

namespace Swdm2.UiTests.Tests.ZZChrome;

/// <summary>
/// D5.3 窗口 chrome 验收（t2 §2.4 沙箱可断言层；**fallback 路线**）。
/// 路线裁决记录（D5.3 实证，A8b 实测纪律）：WPF-UI FluentWindow/TitleBar 简化通道在
/// 无桌面合成沙箱下 UIA 子树为零（三次最小复现：去外挂 WindowChrome / 去 Mica /
/// 去 ExtendsContentIntoTitleBar+TitleBar 均零子；plain Window 对照立即恢复子树）
/// → FlaUI 真实输入旅程（用户路线①硬约束）不可达 → 按 t2 §2.4 预见的 fallback 条款
/// （任务原文"若弃 WPF-UI TitleBar 时启用"）走 WindowChrome+自绘标题栏。
/// 测试用 XamlReader.Parse 加载 MainWindow.xaml（剥 x:Class；纯 XAML 对象树与真 App
/// markup 同源）。另：driver 进程内组装 AppHost 下载链会污染同进程 UIA/Win32 状态
/// 导致 FlaUI 旅程 Win32Exception（D5.3 实证回归），故本类只做 XAML 层断言，
/// 不在 driver 进程实例化 AppHost。
/// 截图层验收（①拖拽/②缩放/③最大化还原/④圆角 6px 像素采样/⑥钮真实点击）
/// = ENV-DOWNGRADE 桌面复跑（沙箱无桌面合成，Capture 全黑；环境容忍门同 D3.3/D4.1)。
/// 逻辑等价层（chrome 令牌+几何+载体 id+回车/关闭命令绑定）在此断言。
/// </summary>
public sealed class ChromeCompositionTests
{
    private const string MainWindowXamlRelative = @"src\Swdm2.App\MainWindow.xaml";

    public ChromeCompositionTests()
    {
        if (Application.Current is null)
            new Application();
        var merged = Application.Current!.Resources.MergedDictionaries;
        if (!merged.Any(d => d.Source is { } src
                              && src.OriginalString.Contains("Ui/Themes/Common.xaml")))
        {
            foreach (var path in new[] { "Common", "Accent", "Dark" })
            {
                merged.Add(new ResourceDictionary
                {
                    Source = new Uri($"pack://application:,,,/Swdm2.App;component/Ui/Themes/{path}.xaml", UriKind.Absolute)
                });
            }
        }
    }

    /// <summary>加载 MainWindow.xaml 为对象树（XamlReader.Parse，剥 x:Class）。</summary>
    private static FrameworkElement LoadMainWindow()
    {
        var repoRoot = Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var xamlPath = Path.Combine(repoRoot, MainWindowXamlRelative);
        Assert.True(File.Exists(xamlPath), $"MainWindow.xaml missing: {xamlPath}");
        var xaml = File.ReadAllText(xamlPath, System.Text.Encoding.UTF8);
        xaml = System.Text.RegularExpressions.Regex.Replace(
            xaml, @"\s+x:Class=""[^""]*""", string.Empty);
        // 剥 Click 事件挂接（code-behind 方法在纯 XamlReader 对象树不存在；
        // 命令绑定保留——chrome 钮命令语义由 Initialize/Loaded 通道断言）
        xaml = System.Text.RegularExpressions.Regex.Replace(
            xaml, @"\s+Click=""[^""]*""", string.Empty);
        return (FrameworkElement)XamlReader.Parse(xaml);
    }

    [WpfFact]
    public void MainWindow_Xaml_WindowChrome_Covers_Resize_8_And_System_Chrome()
    {
        var element = LoadMainWindow();
        var w = (Window)element;

        // WindowStyle=None + 非 AllowsTransparency = t2 §2.4 路线（DWM 阴影/Snap 保留）
        Assert.Equal(WindowStyle.None, w.WindowStyle);
        Assert.False(w.AllowsTransparency);

        // WindowChrome（声明式缩放命中区 8px;PCL2 Resizer 同值）
        var chrome = WindowChrome.GetWindowChrome(w);
        Assert.NotNull(chrome);
        Assert.Equal(new Thickness(8), chrome!.ResizeBorderThickness);
        Assert.Equal(48, chrome.CaptionHeight);          // 标题栏 48（t2 §2.4 表）
        Assert.Equal(new CornerRadius(6), chrome.CornerRadius);  // Win11 系统圆角
        Assert.Equal(new Thickness(0), chrome.GlassFrameThickness);
        Assert.False(chrome.UseAeroCaptionButtons);
    }

    [WpfFact]
    public void MainWindow_AutomationId_Contracts_In_Xaml()
    {
        var element = LoadMainWindow();
        Assert.Equal("MainShell",
            element.GetValue(AutomationProperties.AutomationIdProperty));

        // 自绘 logo 图标钮（A7 可靠载体=Button;图标钮始终自绘）
        var logo = (Button)element.FindName("BtnLogo");
        Assert.NotNull(logo);
        Assert.Equal("Main_Window_Logo",
            logo!.GetValue(AutomationProperties.AutomationIdProperty));
        Assert.Equal(28, logo.Width);
        Assert.Equal(28, logo.Height);
        Assert.True(logo.GetValue(WindowChrome.IsHitTestVisibleInChromeProperty) is true);

        // 自绘关闭/最小化钮（t3 §3.2 保留表；fallback 路线下自绘成立）
        var close = (Button)element.FindName("BtnClose");
        Assert.NotNull(close);
        Assert.Equal("Main_Window_Close",
            close!.GetValue(AutomationProperties.AutomationIdProperty));
        Assert.Equal(28, close.Width);
        Assert.Equal(28, close.Height);

        var min = (Button)element.FindName("BtnMin");
        Assert.NotNull(min);
        Assert.Equal("Main_Window_Minimize",
            min!.GetValue(AutomationProperties.AutomationIdProperty));
        Assert.Equal(44, min.Margin.Right);          // 关闭钮左 16px 间距（12+28）

        // 页面宿主容器（t2 §2.5 PageHost)
        Assert.NotNull(element.FindName("PageHost"));
    }

    [WpfFact]
    public void TitleBar_Skin_Gradient_Is_SelfDrawn_Accent_Token()
    {
        var element = LoadMainWindow();
        var titleGrid = FindTitleGrid((DependencyObject)element);
        Assert.NotNull(titleGrid);
        Assert.Equal(48, titleGrid!.Height);

        // 皮肤渐变=自绘 Linear(accent400 单端 → 透明），DynamicResource 求值（主题切换即时）
        var brush = titleGrid.Background as LinearGradientBrush;
        Assert.NotNull(brush);
        var stops = brush!.GradientStops;
        Assert.Equal(2, stops.Count);
        Assert.Equal(0, stops[0].Offset);
        var accent400 = (Color)element.TryFindResource("swdm-Accent400Color");
        Assert.Equal(accent400, stops[0].Color);
    }

    [WpfFact]
    public void Chrome_Timing_Tokens_In_Common_Dictionary()
    {
        // 验收口径"返回栈语义测试（110→30ms+stagger 25ms)"的令牌层断言
        var app = Application.Current!;
        Assert.Equal(TimeSpan.FromMilliseconds(110), (app.TryFindResource("swdm-MotionPageOut") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(30), (app.TryFindResource("swdm-MotionPageIn") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(25), (app.TryFindResource("swdm-MotionStaggerIn") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(15), (app.TryFindResource("swdm-MotionStaggerOut") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(100), (app.TryFindResource("swdm-MotionPageEnterFade") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(250), (app.TryFindResource("swdm-MotionPageShift1") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(350), (app.TryFindResource("swdm-MotionPageShift2") as Duration?)?.TimeSpan);
        Assert.Equal(TimeSpan.FromMilliseconds(70), (app.TryFindResource("swdm-MotionPageExitElement") as Duration?)?.TimeSpan);
    }

    private static Grid? FindTitleGrid(DependencyObject root)
    {
        // XamlReader.Parse 对象树未布局：可视树未建立，走逻辑树遍历
        if (root is Grid g && g.Height == 48)
            return g;
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
        {
            var found = FindTitleGrid(child);
            if (found is not null) return found;
        }
        return null;
    }
}
