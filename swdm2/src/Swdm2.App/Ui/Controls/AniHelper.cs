using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// 命名轨道动画辅助（PCL2 AniHelper 的 2.0 C# 等价）。
/// 命名轨道：同元素同轨道的新动画启动前先停旧动画，防重入叠加
/// （对应 PCL2 AniStop 语义；t2 §2.5 切页时序 StopPreviousAnimations 的前置）。
/// 颜色动画（PCL2 陷阱已修，t2 §2.1 行 218）：动画期用独立可写 brush 实例
/// （资源字典 brush 是共享/frozen，子属性动画会污染所有消费者），
/// Completed 后 SetResourceReference 回 DynamicResource = 主题切换即时生效。
/// 全部时长/曲线资源来自 ThemeService 合并的 Common.xaml（swdm-Motion*，⚠️[参数待重标定]）。
/// </summary>
public static class AniHelper
{
    private static readonly Dictionary<(DependencyObject target, string track), Storyboard> s_tracks = new();

    /// <summary>
    /// 启动颜色动画（90ms 色系：悬停标题/箭头/阴影色）。
    /// animatedProperty 必须是可承载 SolidColorBrush 的画刷属性（Foreground/Background/Fill）；
    /// restoreResourceKey 为动画结束后回绑的 DynamicResource 键（如 swdm-TextPrimaryBrush）。
    /// </summary>
    public static void StartColor(
        FrameworkElement target, DependencyProperty animatedProperty,
        Color from, Color to, TimeSpan duration,
        string restoreResourceKey, string track = "color")
    {
        // 独立可写实例：避免动画 frozen/共享资源字典 brush 污染
        var brush = new SolidColorBrush(from);
        target.SetCurrentValue(animatedProperty, brush);
        var anim = new ColorAnimation(from, to, duration);
        Storyboard.SetTarget(anim, brush);
        Storyboard.SetTargetProperty(anim, new PropertyPath(SolidColorBrush.ColorProperty));
        var sb = new Storyboard();
        sb.Children.Add(anim);
        RegisterTrack(target, track, sb);
        sb.Completed += (_, _) =>
        {
            UnregisterTrack(target, track, sb);
            // 陷阱修复：回绑 DynamicResource（PCL2 同语义）
            target.SetResourceReference(animatedProperty, restoreResourceKey);
        };
        sb.Begin();
    }

    /// <summary>启动双精度动画（高度 150ms / 透明度 / scale 等）。</summary>
    public static void StartDouble(
        DependencyObject target, DependencyProperty property,
        double to, TimeSpan duration, string track = "number")
        => StartAnimation(target, property, new DoubleAnimation(to, duration), track);

    /// <summary>带缓动曲线的双精度动画（高度=QuinticEase EaseOut 等）。</summary>
    public static void StartDouble(
        DependencyObject target, DependencyProperty property,
        double to, TimeSpan duration, IEasingFunction ease, string track = "number")
        => StartAnimation(target, property, new DoubleAnimation(to, duration) { EasingFunction = ease }, track);

    /// <summary>停止指定元素的全部命名轨道（切页/移除前置）。</summary>
    public static void StopAll(DependencyObject target)
    {
        var keys = new List<(DependencyObject, string)>();
        foreach (var key in s_tracks.Keys)
            if (ReferenceEquals(key.target, target)) keys.Add(key);
        foreach (var key in keys)
        {
            if (s_tracks.TryGetValue(key, out var sb))
            {
                sb.Stop();
                s_tracks.Remove(key);
            }
        }
    }

    private static void StartAnimation(
        DependencyObject target, DependencyProperty property,
        Timeline animation, string track)
    {
        var key = (target, track);
        if (s_tracks.TryGetValue(key, out var existing))
        {
            existing.Stop();
            s_tracks.Remove(key);
        }
        Storyboard.SetTarget(animation, target);
        Storyboard.SetTargetProperty(animation, new PropertyPath(property));
        var sb = new Storyboard();
        sb.Children.Add(animation);
        RegisterTrack(target, track, sb);
        sb.Completed += (_, _) => UnregisterTrack(target, track, sb);
        sb.Begin();
    }

    private static void RegisterTrack(DependencyObject target, string track, Storyboard sb)
        => s_tracks[(target, track)] = sb;

    private static void UnregisterTrack(DependencyObject target, string track, Storyboard sb)
    {
        if (s_tracks.TryGetValue((target, track), out var registered) && ReferenceEquals(registered, sb))
            s_tracks.Remove((target, track));
    }
}
