using System;
using System.Linq;
using System.Windows;
using Microsoft.Win32;

namespace Swdm2.App.Ui.Themes;

/// <summary>
/// 主题切换服务（t2 visual_system_2.0.md §1.4）：换 <see cref="ResourceDictionary"/> 条目，
/// 全树 DynamicResource 立即重应用——无闪烁（pcl2 §5.3 已验证机制）。
/// 不变量（承接架构规格 A3）：
/// ① 主题字典只在 App.xaml 合并一次，切换 = 换 MergedDictionaries 条目；
/// ② 键名一律 swdm- 前缀；
/// ③ 消费处一律 DynamicResource；
/// ④ 主题真源=自建字典，不与 WPF-UI ApplicationThemeManager 并存（A8 裁决）。
/// 持久化（IOptionsMonitor&lt;ThemeOptions&gt;）与系统主题跟随订阅延后到 D5.x 设置页接线。
/// </summary>
public enum SwdmTheme { Light, Dark, FollowSystem }

public sealed class ThemeService
{
    // 组件限定 pack URI：跨程序集解析（测试驱动进程内 Application 无 StartupUri 时，
    // 不带组件名的 pack URI 无法定位资源；带组件名在真 App 进程同效）。
    private const string DarkPath = "pack://application:,,,/Swdm2.App;component/Ui/Themes/Dark.xaml";
    private const string LightPath = "pack://application:,,,/Swdm2.App;component/Ui/Themes/Light.xaml";
    private const string ThemeMarker = "Ui/Themes/";

    public SwdmTheme Current { get; private set; } = SwdmTheme.Dark;

    /// <summary>当前生效的主题（FollowSystem 解析后的实际值）。</summary>
    public SwdmTheme ResolvedTheme =>
        Current == SwdmTheme.FollowSystem ? DetectSystemTheme() : Current;

    /// <summary>
    /// 换主题字典条目（先移除旧的再添加新的，避免双主题状态）。
    /// 所有消费处 DynamicResource 在字典交换后立即重应用 = 无闪烁。
    /// </summary>
    public void Apply(SwdmTheme theme)
    {
        var resolved = theme == SwdmTheme.FollowSystem ? DetectSystemTheme() : theme;
        var newPath = resolved == SwdmTheme.Light ? LightPath : DarkPath;
        var resources = Application.Current?.Resources;
        if (resources is null) return;

        var existing = resources.MergedDictionaries
            .FirstOrDefault(d => d.Source is not null
                                 && d.Source.OriginalString.Contains(ThemeMarker)
                                 && !d.Source.OriginalString.EndsWith("Common.xaml", StringComparison.Ordinal)
                                 && !d.Source.OriginalString.EndsWith("Accent.xaml", StringComparison.Ordinal));
        if (existing is not null)
            resources.MergedDictionaries.Remove(existing);

        resources.MergedDictionaries.Add(new ResourceDictionary
        {
            Source = new Uri(newPath, UriKind.Absolute)
        });
        Current = theme;
    }

    /// <summary>系统主题探测（注册表 AppsUseLightTheme: 0=dark, 1=light; 解析失败=dark)</summary>
    internal static SwdmTheme DetectSystemTheme()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            if (key?.GetValue("AppsUseLightTheme") is int useLight)
                return useLight == 1 ? SwdmTheme.Light : SwdmTheme.Dark;
        }
        catch
        {
            // 注册表不可读（沙箱/受限）=保守 dark（1.x 品牌延续）
        }
        return SwdmTheme.Dark;
    }
}
