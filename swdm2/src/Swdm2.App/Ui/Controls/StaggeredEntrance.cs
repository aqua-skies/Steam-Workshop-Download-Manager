using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Swdm2.App.Ui.Controls;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// A1「上→下凝实」(t55 D5.16;spec §2.10 A1):
/// 列表行自上而下交错淡入——每行 Opacity 0.4→1 + TranslateY 12→0,
/// 单行 200ms QuinticEase;行间延迟 ~25ms,**总时长恒 ≤400ms**(行数&gt;8 后
/// 延迟封顶 200ms=PCL2 实测"多行不拖尾"行为，⚠️[参数待重标定] 起点值）。
/// 终态可断言（A7):完成回调里容器 Opacity=1/TranslateY=0(逻辑等价：
/// ENV-DOWNGRADE 桌面门族同 t44——沙箱无渲染=时间线模型层断言）。
/// </summary>
public static class StaggeredEntrance
{
    /// <summary>单行动画时长 200ms(spec §2.10 A1)。</summary>
    public const int RowDurationMs = 200;

    /// <summary>行间交错延迟起点 25ms(⚠️[参数待重标定] B-动画）。</summary>
    public const int RowStaggerMs = 25;

    /// <summary>总时长硬顶 400ms(spec 原文"总 400ms")。</summary>
    public const int TotalCapMs = 400;

    /// <summary>最大封顶延迟=TotalCap-RowDuration(超过 8 行后不再加延迟）。</summary>
    public const int MaxDelayMs = TotalCapMs - RowDurationMs;

    /// <summary>行 i 的起始延迟（0 基；封顶保护总时长 ≤400ms)。</summary>
    public static int DelayForRowIndex(int i)
        => Math.Min(i * RowStaggerMs, MaxDelayMs);

    /// <summary>交错时间线（每行=延迟+时长；可纯逻辑断言，无需渲染）。</summary>
    public static IReadOnlyList<RowEntrance> BuildTimeline(int rowCount)
    {
        if (rowCount < 0) throw new ArgumentOutOfRangeException(nameof(rowCount));
        var rows = new List<RowEntrance>(rowCount);
        for (var i = 0; i < rowCount; i++)
            rows.Add(new RowEntrance(i, DelayForRowIndex(i), RowDurationMs));
        return rows;
    }

    /// <summary>对已生成容器播放 A1(ItemsControl.Loaded/容器生成后调）。</summary>
    public static void Play(ItemsControl host, string track = "A1-entrance")
    {
        if (host is null) return;
        var containers = new List<FrameworkElement>();
        foreach (var item in host.Items)
        {
            if (host.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement fe)
                containers.Add(fe);
        }
        Play(containers, track);
    }

    /// <summary>对显式容器集播放 A1(测试可注入确定序列）。</summary>
    public static void Play(IReadOnlyList<FrameworkElement> containers, string track = "A1-entrance")
    {
        if (containers is null || containers.Count == 0) return;
        for (var i = 0; i < containers.Count; i++)
        {
            var fe = containers[i];
            // 初态：半透明+下移 12px(凝实起点）
            fe.Opacity = 0.4;
            var delay = DelayForRowIndex(i);
            var sb = new Storyboard();
            var opacity = new DoubleAnimation(0.4, 1.0, TimeSpan.FromMilliseconds(RowDurationMs))
            {
                BeginTime = TimeSpan.FromMilliseconds(delay),
                EasingFunction = new QuinticEase(),
            };
            var translate = new DoubleAnimation(12, 0, TimeSpan.FromMilliseconds(RowDurationMs))
            {
                BeginTime = TimeSpan.FromMilliseconds(delay),
                EasingFunction = new QuinticEase(),
            };
            EnsureTranslate(fe);
            Storyboard.SetTarget(opacity, fe);
            Storyboard.SetTargetProperty(opacity, new PropertyPath(UIElement.OpacityProperty));
            Storyboard.SetTarget(translate, fe);
            Storyboard.SetTargetProperty(translate, new PropertyPath("(UIElement.RenderTransform).(TranslateTransform.Y)"));
            sb.Children.Add(opacity);
            sb.Children.Add(translate);
            sb.Completed += (_, _) =>
            {
                // A7 终态修正（防中间帧采样误判）
                fe.Opacity = 1.0;
                ((TranslateTransform)fe.RenderTransform).Y = 0;
            };
            // 同轨道先停旧（AniHelper 精神：防叠加闪烁）
            AniHelper.StopAll(fe);
            sb.Begin();
        }
    }

    private static void EnsureTranslate(FrameworkElement fe)
    {
        if (fe.RenderTransform is TranslateTransform) return;
        var existing = fe.RenderTransform as TransformGroup;
        if (existing is not null)
        {
            foreach (var t in existing.Children.OfType<TranslateTransform>())
            {
                fe.RenderTransform = t;
                return;
            }
        }
        fe.RenderTransform = new TranslateTransform { Y = 12 };
    }
}

/// <summary>单行凝实步骤（模型=可断言时间线）。</summary>
public sealed record RowEntrance(int RowIndex, int DelayMs, int DurationMs)
{
    /// <summary>该行完成时刻（≥0 基准）。</summary>
    public int EndMs => DelayMs + DurationMs;
}
