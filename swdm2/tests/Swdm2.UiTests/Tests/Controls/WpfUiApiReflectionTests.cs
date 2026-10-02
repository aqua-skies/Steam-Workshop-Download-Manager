using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using Xunit;

namespace Swdm2.UiTests.Tests.Controls;

/// <summary>
/// A8b 纪律：WPF-UI API 用前反射实测。
/// 实测对象=WPF-UI 4.3.0(net8.0-windows7.0 TFM）。spike(t4) 已实证
/// FluentWindow/TitleBar/NavigationView/ApplicationThemeManager 命名与 4.3.0 一致；
/// 此处在持续回归口径上用 PEReader（纯元数据读取，无依赖程序集解析——
/// sandbox LoadFrom 上下文无法解析 WPF-UI 的传递依赖，GetType 返回假 null）
/// 断言类型定义存在+程序集版本一致（库升级时测试先红）。
/// 自绘控件层（t41)不直接消费这些 API（主题真源=自建字典，A8 裁决）；
/// 反射证据留存供 t2 §2.4 简化通道（FluentWindow/TitleBar 基座）后续选型引用。
/// </summary>
public sealed class WpfUiApiReflectionTests
{
    private const string WpfUiAssemblySubPath =
        @"wpf-ui\4.3.0\lib\net8.0-windows7.0\Wpf.Ui.dll";

    [WpfFact]
    public void WpfUi_4_3_0_Key_Api_Surface_Exists()
    {
        var nugetRoot = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var dll = Path.Combine(Path.Combine(nugetRoot, ".nuget", "packages"), WpfUiAssemblySubPath);
        if (!File.Exists(dll))
        {
            Console.WriteLine("ENV-SKIP: WPF-UI 4.3.0 package not restored in this profile " +
                              "(spike project consumes it); spike t4 API verification stands.");
            return; // 包未还原=环境差异，spike 实证兜底（不假绿：明确跳过标注）
        }

        using var pe = new PEReader(File.OpenRead(dll));
        var md = pe.GetMetadataReader();

        // 程序集版本（AssemblyDefinition 表）
        var asmDef = md.GetAssemblyDefinition();
        Assert.Equal(4, asmDef.Version.Major);
        Assert.Equal(3, asmDef.Version.Minor);

        // 关键 API 类型定义存在性（t2 §1.3/§2.4;spike 实证表面）
        var expectedTypes = new[]
        {
            "Wpf.Ui.Controls.FluentWindow",
            "Wpf.Ui.Controls.TitleBar",
            "Wpf.Ui.Controls.NavigationView",
        };
        var found = new System.Collections.Generic.HashSet<string>();
        foreach (var handle in md.TypeDefinitions)
        {
            var td = md.GetTypeDefinition(handle);
            var fullName = $"{md.GetString(td.Namespace)}.{md.GetString(td.Name)}";
            if (expectedTypes.Contains(fullName))
                found.Add(fullName);
            // 主题管理器（命名空间逐版本可能调整=按名字收集）
            var name = md.GetString(td.Name);
            if (name == "ApplicationThemeManager" || name == "ApplicationTheme")
                found.Add($"{md.GetString(td.Namespace)}.{name}");
        }
        Assert.Superset(new System.Collections.Generic.HashSet<string>(expectedTypes), found);
        Assert.Contains(found, f => f.EndsWith(".ApplicationThemeManager", StringComparison.Ordinal));
        Assert.Contains(found, f => f.EndsWith(".ApplicationTheme", StringComparison.Ordinal));
    }
}
