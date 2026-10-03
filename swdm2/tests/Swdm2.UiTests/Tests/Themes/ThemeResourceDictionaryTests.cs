using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Markup;
using System.Windows.Media;
using Xunit;
// [WpfFact] only (SP-2: xunit.core↔xunit.v3.core [Fact] ambiguity — new tests use WpfFact)

namespace Swdm2.UiTests.Tests.Themes;

/// <summary>
/// t2 visual_system_2.0.md §1.5 单一事实来源一致性测试（沙箱可跑的逻辑层全覆盖）：
/// - Light ≡ Dark 键集严格相等（切换无键缺失）
/// - 全键 swdm- 前缀（防第三方冲突，架构 A3）
/// - 双资源律：每个颜色令牌成对 Color + Brush，且 Brush.Color 同源
/// - WCAG 对比度断言（正文 ≥4.5:1；t2 §1.2 无障碍基线）
/// - 换 Accent.xaml 即换皮机制（合并覆盖语义，后者胜出）
/// - Common/Accent 主题无关资源存在性
/// 截图像素六清单（§4）= ENV-DOWNGRADE 桌面通道复跑（沙箱无桌面合成：Capture 全黑，
/// 环境容忍门模式同 D3.3/D4.1 Online；逻辑层的切换无闪烁等价断言在 ThemeServiceTests）。
/// </summary>
public sealed class ThemeResourceDictionaryTests
{
    private static readonly string AppRoot = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "..", "..", "..", "..", "..", "src", "Swdm2.App"));

    private static readonly string ThemesRoot = Path.Combine(AppRoot, "Ui", "Themes");

    private static ResourceDictionary LoadXaml(string name)
    {
        var path = Path.Combine(ThemesRoot, name);
        Assert.True(File.Exists(path), $"theme dictionary missing: {path}");
        var text = File.ReadAllText(path);
        return (ResourceDictionary)XamlReader.Parse(text);
    }

    private static IEnumerable<string> KeyNames(ResourceDictionary d)
        => d.Keys.Cast<string>().OrderBy(k => k);

    [WpfFact]
    public void Light_And_Dark_Have_Identical_Key_Sets()
    {
        var light = LoadXaml("Light.xaml");
        var dark = LoadXaml("Dark.xaml");
        Assert.Equal(KeyNames(light), KeyNames(dark));
    }

    [WpfFact]
    public void All_Keys_Have_Swdm_Prefix()
    {
        foreach (var name in new[] { "Light.xaml", "Dark.xaml", "Accent.xaml", "Common.xaml" })
        {
            var dict = LoadXaml(name);
            Assert.All(dict.Keys.Cast<string>(),
                key => Assert.StartsWith("swdm-", key));
        }
    }

    [WpfFact]
    public void Color_Tokens_Pair_Color_And_Brush()
    {
        // 双资源律（t2 §1.2）：每个颜色令牌 = Color + SolidColorBrush 同源
        foreach (var name in new[] { "Light.xaml", "Dark.xaml" })
        {
            var dict = LoadXaml(name);
            var colorKeys = dict.Keys.Cast<string>()
                .Where(k => k.EndsWith("Color", System.StringComparison.Ordinal)).ToList();
            Assert.NotEmpty(colorKeys);
            foreach (var colorKey in colorKeys)
            {
                var brushKey = colorKey[..^5] + "Brush"; // XxxColor → XxxBrush
                Assert.Contains(brushKey, dict.Keys.Cast<string>());
                var color = Assert.IsType<Color>(dict[colorKey]);
                var brush = Assert.IsAssignableFrom<SolidColorBrush>(dict[brushKey]);
                Assert.Equal(color, brush.Color);
            }
        }
    }

    [WpfFact]
    public void Common_Has_Motion_And_Geometry_Scalars()
    {
        var common = LoadXaml("Common.xaml");
        // t2 §5 数值速查表：PCL2 实测动画时长/几何
        Assert.Contains("swdm-MotionColor", common.Keys.Cast<string>());      // 90ms
        Assert.Contains("swdm-MotionFast", common.Keys.Cast<string>());       // 150ms
        Assert.Contains("swdm-MotionSlow", common.Keys.Cast<string>());       // 250ms
        Assert.Contains("swdm-MotionBase", common.Keys.Cast<string>());       // 200ms
        Assert.Contains("swdm-MotionButtonIn", common.Keys.Cast<string>());   // 100ms
        Assert.Contains("swdm-MotionButtonOut", common.Keys.Cast<string>());  // 200ms
        Assert.Contains("swdm-RadiusSm", common.Keys.Cast<string>());         // 5
        Assert.Contains("swdm-CardCollapsedHeight", common.Keys.Cast<string>()); // 40
        Assert.Contains("swdm-ShadowOpacityIdle", common.Keys.Cast<string>());   // 0.07
        Assert.Contains("swdm-ShadowOpacityHover", common.Keys.Cast<string>());  // 0.4
    }

    [WpfFact]
    public void Accent_Dictionary_Has_Neutral_Shadow()
    {
        var accent = LoadXaml("Accent.xaml");
        Assert.Contains("swdm-NeutralShadowColor", accent.Keys.Cast<string>());
        Assert.Contains("swdm-NeutralShadowBrush", accent.Keys.Cast<string>());
    }

    [WpfFact]
    public void Token_Values_Match_Spec_Dark_Palette()
    {
        // t2 §1.2 暗色表行号级抽检（spec 数值 = 单一事实源）
        // v1.4 配色A「薄荷夜」全表重染（math_computation 实算回执 2026-10-03）
        var dark = LoadXaml("Dark.xaml");
        Assert.Equal(Color.FromRgb(0x0D, 0x15, 0x11), (Color)dark["swdm-SurfaceCanvasColor"]);
        Assert.Equal(Color.FromRgb(0x14, 0x20, 0x1A), (Color)dark["swdm-SurfaceCardColor"]);
        Assert.Equal(Color.FromRgb(0xE8, 0xF5, 0xEE), (Color)dark["swdm-TextPrimaryColor"]);
        // v1.4:accent.500=品牌薄荷真色（配深字 text.on_accent=8.14 ✓;白字 1.88 ✗）
        Assert.Equal(Color.FromRgb(0x3E, 0xD5, 0x98), (Color)dark["swdm-Accent500Color"]);
        // v1.4:亮底深字糖果风（Refero Rainbow 同族）
        Assert.Equal(Color.FromRgb(0x07, 0x2B, 0x1D), (Color)dark["swdm-TextOnAccentColor"]);

        var light = LoadXaml("Light.xaml");
        Assert.Equal(Color.FromRgb(0xF6, 0xFB, 0xF7), (Color)light["swdm-SurfaceCanvasColor"]);
        Assert.Equal(Colors.White, (Color)light["swdm-SurfaceCardColor"]);
        Assert.Equal(Color.FromRgb(0x3E, 0xD5, 0x98), (Color)light["swdm-Accent500Color"]);
        Assert.Equal(Color.FromRgb(0x05, 0x2E, 0x1F), (Color)light["swdm-TextOnAccentColor"]);
    }

    [WpfFact]
    public void Contrast_Ratios_Meet_Wcag_Baseline()
    {
        // t2 §1.2 无障碍基线：正文 ≥4.5:1（大字/图标 ≥3:1）
        var dark = LoadXaml("Dark.xaml");
        var light = LoadXaml("Light.xaml");

        // 正文/元信息/链接/强调上文本 对其落点背景
        Assert.True(Contrast((Color)dark["swdm-TextPrimaryColor"], (Color)dark["swdm-SurfaceCanvasColor"]) >= 4.5);
        Assert.True(Contrast((Color)dark["swdm-TextSecondaryColor"], (Color)dark["swdm-SurfaceCardColor"]) >= 4.5);
        Assert.True(Contrast((Color)dark["swdm-TextOnAccentColor"], (Color)dark["swdm-Accent500Color"]) >= 4.5);
        Assert.True(Contrast((Color)dark["swdm-LinkDefaultColor"], (Color)dark["swdm-SurfaceCardColor"]) >= 3);

        Assert.True(Contrast((Color)light["swdm-TextPrimaryColor"], (Color)light["swdm-SurfaceCardColor"]) >= 4.5);
        Assert.True(Contrast((Color)light["swdm-TextSecondaryColor"], (Color)light["swdm-SurfaceCardColor"]) >= 4.5);
        Assert.True(Contrast((Color)light["swdm-TextOnAccentColor"], (Color)light["swdm-Accent500Color"]) >= 4.5);
        // 浅色链接深化至 ≥4.5:1（#66C0F4 白底仅 2.4:1 不可用——t2 §1.2 明示）
        Assert.True(Contrast((Color)light["swdm-LinkDefaultColor"], (Color)light["swdm-SurfaceCardColor"]) >= 4.5);
    }

    [WpfFact]
    public void Accent_Override_Wins_Merged_Last()
    {
        // 换 Accent.xaml 即换皮机制证据：MergedDictionaries 后者覆盖先者
        // （ThemeService 换主题条目同理；App.xaml 合并顺序 Common → Accent → 主题）
        var accentA = LoadXaml("Accent.xaml");
        var accentB = new ResourceDictionary
        {
            ["swdm-NeutralShadowColor"] = Color.FromRgb(0x11, 0x22, 0x33)
        };
        var merged = new ResourceDictionary();
        merged.MergedDictionaries.Add(accentA);
        merged.MergedDictionaries.Add(accentB); // 后者胜
        Assert.Equal(Color.FromRgb(0x11, 0x22, 0x33), (Color)merged["swdm-NeutralShadowColor"]);
    }

    /// <summary>WCAG 相对亮度对比比（t2 §1.5 纯逻辑计算函数）。</summary>
    internal static double Contrast(Color fg, Color bg)
    {
        static double Luminance(Color c)
        {
            static double Chan(double v)
            {
                v /= 255.0;
                return v <= 0.03928 ? v / 12.92 : Math.Pow((v + 0.055) / 1.055, 2.4);
            }
            return 0.2126 * Chan(c.R) + 0.7152 * Chan(c.G) + 0.0722 * Chan(c.B);
        }
        var l1 = Luminance(fg);
        var l2 = Luminance(bg);
        return (Math.Max(l1, l2) + 0.05) / (Math.Min(l1, l2) + 0.05);
    }
}
