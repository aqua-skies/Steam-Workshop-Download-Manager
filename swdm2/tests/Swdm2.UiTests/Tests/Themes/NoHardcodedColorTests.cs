using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Windows;
using Swdm2.App.Ui.Themes;
using Xunit;

namespace Swdm2.UiTests.Tests.Themes;

/// <summary>
/// t2 §1.5 不变量④ 静态断言：Ui/Themes/*.xaml 之外不得出现硬编码颜色字面量
/// （例外白名单：图标 path 几何——不带 # 的 Data；Transparent——无 #hex 形式）。
/// 范围：src/Swdm2.App/ 下全部 XAML 排除 Ui/Themes/（令牌定义唯一允许处）。
/// </summary>
public sealed class NoHardcodedColorTests
{
    private static readonly string AppRoot = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "..", "..", "..", "..", "..", "src", "Swdm2.App"));

    // 引号内的 #hex 属性值（WPF 颜色字面量的唯一合法形态）
    private static readonly Regex HexColorPattern =
        new("\"#[0-9A-Fa-f]{3,8}\"", RegexOptions.Compiled);

    private static IEnumerable<string> ScannedXamlFiles()
    {
        var themesRoot = Path.Combine(AppRoot, "Ui", "Themes");
        return Directory.EnumerateFiles(AppRoot, "*.xaml", SearchOption.AllDirectories)
            .Where(f => !f.StartsWith(themesRoot, System.StringComparison.OrdinalIgnoreCase));
    }

    [WpfFact]
    public void No_Hardcoded_Color_Literals_Outside_Theme_Dictionaries()
    {
        var violations = new List<string>();
        foreach (var file in ScannedXamlFiles())
        {
            var lines = File.ReadAllLines(file);
            for (var i = 0; i < lines.Length; i++)
            {
                var line = lines[i];
                // 跳过注释行（XAML 注释内的问题编号如 #255 不是颜色）
                var codeOnly = Regex.Replace(line, @"<!--.*?-->", string.Empty);
                foreach (Match m in HexColorPattern.Matches(codeOnly))
                    violations.Add($"{Path.GetFileName(file)}:{i + 1} {m.Value}");
            }
        }
        Assert.Empty(violations);
    }
}
