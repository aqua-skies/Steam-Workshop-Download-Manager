using System.Linq;
using System.Windows;
using System.Windows.Media;
using Swdm2.App.Ui.Themes;
using Xunit;

namespace Swdm2.UiTests.Tests.Themes;

/// <summary>
/// ThemeService 切换机制逻辑层测试（t2 §1.4 / §4 清单 6）。
/// 截图像素六清单之「切换无闪烁门」=截图 diff，沙箱无桌面合成（Capture 全黑）
/// = ENV-DOWNGRADE 桌面通道复跑（环境容忍门同 D3.3/D4.1 Online）；
/// 此处断言其逻辑等价前提：换字典=单次 MergedDictionaries 条目替换，
/// 全树 DynamicResource 立即重应用（无需 InvalidateVisual、无中间帧资源缺失）。
/// </summary>
public sealed class ThemeServiceTests
{
    public ThemeServiceTests()
    {
        // 驱动进程为 STA（WpfFact/Collection 串行）；确保 Application 可用
        if (Application.Current is null)
            new Application();
    }

    [WpfFact]
    public void Apply_Swaps_Theme_Dictionary_Entry()
    {
        var svc = new ThemeService();
        svc.Apply(SwdmTheme.Dark);
        AssertThemeEntry("Dark.xaml");

        svc.Apply(SwdmTheme.Light);
        AssertThemeEntry("Light.xaml");

        svc.Apply(SwdmTheme.Dark);
        AssertThemeEntry("Dark.xaml");
    }

    [WpfFact]
    public void Apply_Resolves_DynamicResource_Immediately()
    {
        // 换字典后资源树立即反映新主题值（DynamicResource 重应用的前提条件）
        // v1.4 配色A：薄荷夜 #0D1511 / 薄荷清晨 #F6FBF7
        var svc = new ThemeService();
        svc.Apply(SwdmTheme.Dark);
        Assert.Equal(Color.FromRgb(0x0D, 0x15, 0x11),
            (Color)Application.Current.Resources["swdm-SurfaceCanvasColor"]);

        svc.Apply(SwdmTheme.Light);
        Assert.Equal(Color.FromRgb(0xF6, 0xFB, 0xF7),
            (Color)Application.Current.Resources["swdm-SurfaceCanvasColor"]);
    }

    [WpfFact]
    public void Apply_Does_Not_Duplicate_Theme_Entries()
    {
        // 不变量①：主题字典条目只有一个（换 = 替换，非叠加；双主题状态=缺陷）
        var svc = new ThemeService();
        svc.Apply(SwdmTheme.Dark);
        svc.Apply(SwdmTheme.Light);
        svc.Apply(SwdmTheme.Dark);

        var themeEntries = Application.Current.Resources.MergedDictionaries
            .Where(d => d.Source is not null
                        && d.Source.OriginalString.Contains("Ui/Themes/")
                        && !d.Source.OriginalString.EndsWith("Common.xaml")
                        && !d.Source.OriginalString.EndsWith("Accent.xaml"))
            .ToList();
        Assert.Single(themeEntries);
    }

    [WpfFact]
    public void Apply_FollowSystem_Does_Not_Throw()
    {
        var svc = new ThemeService();
        svc.Apply(SwdmTheme.FollowSystem); // 沙箱注册表不可读=保守 dark，不抛
        Assert.Equal(SwdmTheme.FollowSystem, svc.Current);
        var resolved = svc.ResolvedTheme;
        Assert.True(resolved == SwdmTheme.Dark || resolved == SwdmTheme.Light);
    }

    private static void AssertThemeEntry(string expectedFileName)
    {
        var entry = Application.Current.Resources.MergedDictionaries
            .FirstOrDefault(d => d.Source is not null
                                 && d.Source.OriginalString.Contains("Ui/Themes/")
                                 && !d.Source.OriginalString.EndsWith("Common.xaml")
                                 && !d.Source.OriginalString.EndsWith("Accent.xaml"));
        Assert.NotNull(entry);
        Assert.EndsWith(expectedFileName, entry!.Source!.OriginalString);
    }
}
