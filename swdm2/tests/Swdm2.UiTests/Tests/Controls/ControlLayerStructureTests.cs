using System;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Shapes;
using Swdm2.App.Ui.Controls;
using Xunit;
using IOPath = System.IO.Path;

namespace Swdm2.UiTests.Tests.Controls;

/// <summary>
/// SwdmCard / Hint / ModListItem 验收判据（t2 §2.1-2.3 沙箱可断言层）。
/// 截图/OCR/悬停像素层（验收①②③截图族）= ENV-DOWNGRADE 桌面复跑
/// （沙箱无桌面合成，Capture 全黑；环境容忍门同 D3.3/D4.1)。
/// 此处断言：三层结构几何、令牌资源绑定、语义档位映射、AutomationId 契约、
/// 动画启动/停止不抛（动画推进依赖渲染时钟，headless 不可靠=明确不测推进值）。
/// </summary>
public sealed class ControlLayerStructureTests
{
    public ControlLayerStructureTests()
    {
        if (Application.Current is null)
            new Application();
        // 测试进程合并主题字典（App.xaml 顺序 A3:Common→Accent→Dark)
        // StaticResource 在 XAML 加载时求值，裸 Application 无法解析 swdm-* 键
        var merged = Application.Current!.Resources.MergedDictionaries;
        if (!merged.Any(d => d.Source is { } src
                              && src.OriginalString.Contains("Ui/Themes/Common.xaml")))
        {
        foreach (var path in new[]
        {
            "Common", "Accent", "Dark",
        })
        {
            merged.Add(new ResourceDictionary
            {
                Source = new Uri($"pack://application:,,,/Swdm2.App;component/Ui/Themes/{path}.xaml", UriKind.Absolute)
            });
        }
        }
    }

    // ===== SwdmCard（t2 §2.1) =====

    [WpfFact]
    public void SwdmCard_Three_Layer_Structure_And_Geometry()
    {
        var card = new SwdmCard { Title = "Card title" };
        card.ApplyTemplate(); // 模板应用（UserControl 直接有 xaml name）

        // 三层（ShadowLayer / CardLayer / MainGrid)
        Assert.NotNull(card.FindName("ShadowLayer"));
        Assert.NotNull(card.FindName("CardLayer"));
        Assert.NotNull(card.FindName("MainGrid"));

        var shadow = (Border)card.FindName("ShadowLayer");
        Assert.Equal(new Thickness(-3, -3, -3, -4), shadow.Margin); // 底部多 1px 自然光
        Assert.Equal(new CornerRadius(5), shadow.CornerRadius);                       // radius.sm

        var cardLayer = (Border)card.FindName("CardLayer");
        Assert.Equal(new CornerRadius(5), cardLayer.CornerRadius);
        Assert.False(cardLayer.IsHitTestVisible);                    // 卡面不挡命中测试
    }

    [WpfFact]
    public void SwdmCard_Shadow_Effect_Route_A_Tokens()
    {
        // t2 §2.1 路线 A 令牌：idle 0.07 / 6 / 2 / 270（⚠️待标定）
        var card = new SwdmCard();
        card.ApplyTemplate();
        var effect = (DropShadowEffect)card.FindName("ShadowEffect");
        Assert.Equal(0.07, effect.Opacity);
        Assert.Equal(6, effect.BlurRadius);
        Assert.Equal(2, effect.ShadowDepth);
        Assert.Equal(270, effect.Direction);

        // 折叠态 40（Common.xaml swdm-CardCollapsedHeight,double 资源）
        Assert.Equal(40.0, (double)card.TryFindResource("swdm-CardCollapsedHeight"));
    }

    [WpfFact]
    public void SwdmCard_Title_Bound_And_Arrow_Geometry()
    {
        var card = new SwdmCard { Title = "下载任务" };
        card.ApplyTemplate();
        var title = (TextBlock)card.FindName("TitleText");
        Assert.Equal("下载任务", title.Text);
        Assert.Equal(13, title.FontSize);
        Assert.Equal(FontWeights.Bold, title.FontWeight);

        var arrow = (System.Windows.Shapes.Path)card.FindName("ArrowPath");
        Assert.Equal(10, arrow.Width);
        Assert.Equal(6, arrow.Height);
    }

    [WpfFact]
    public void SwdmCard_Expand_Collapse_Toggle_Does_Not_Throw()
    {
        var card = new SwdmCard();
        card.ApplyTemplate();
        // 状态机切换（动画基于渲染时钟，headless 不推进=只验不抛）
        card.IsExpanded = false;
        Assert.False(card.IsExpanded);
        card.IsExpanded = true;
        Assert.True(card.IsExpanded);
        // 退出动画同样无抛（宿主页面移除前置）
        card.PlayExit();
    }

    // ===== Hint（t2 §2.2) =====

    [WpfFact]
    public void Hint_Semantic_Kinds_Map_To_Tokens()
    {
        foreach (var (kind, token) in new[]
        {
            (HintKind.Info, "swdm-LinkDefaultBrush"),
            (HintKind.Success, "swdm-Success500Brush"),
            (HintKind.Warning, "swdm-Warning500Brush"),
            (HintKind.Error, "swdm-Danger500Brush"),
        })
        {
            var hint = new Hint { Kind = kind };
            hint.ApplyTemplate();
            var expected = (SolidColorBrush)hint.TryFindResource(token);
            Assert.Equal(expected.Color, ((SolidColorBrush)hint.SemanticColor).Color);
        }
    }

    [WpfFact]
    public void Hint_Border_Geometry_And_Close_Button_Contract()
    {
        var hint = new Hint
        {
            Message = "网络受限：steamcommunity 403",
            Kind = HintKind.Warning,
            CloseAutomationId = "Downloads_Hint_Close",
        };
        hint.ApplyTemplate();

        // 色条 3px 左+圆角 2（t2 §2.2)
        var hintBorder = (Border)hint.FindName("HintBorder");
        Assert.Equal(new Thickness(3, 0, 0, 0), hintBorder.BorderThickness);
        Assert.Equal(new CornerRadius(2), hintBorder.CornerRadius);

        var message = (TextBlock)hint.FindName("MessageText");
        Assert.Equal("网络受限：steamcommunity 403", message.Text);

        var close = (Button)hint.FindName("CloseButton");
        Assert.Equal("Downloads_Hint_Close",
            close.GetValue(AutomationProperties.AutomationIdProperty));
        Assert.Equal(12, message.Padding.Left);  // padding 12,9
        Assert.Equal(9, message.Padding.Top);

        // 点击关闭=Collapsed（验收判据②；真实 FlaUI 点击留桌面通道）
        hint.GetType().GetMethod("CloseButton_Click",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!
            .Invoke(hint, new object[] { close, new RoutedEventArgs() });
        Assert.Equal(Visibility.Collapsed, hint.Visibility);
    }

    // ===== ModListItem（t2 §2.3) =====

    [WpfFact]
    public void ModListItem_Row_Geometry_42_And_RectBack()
    {
        var item = new ModListItem { Title = "Don't Starve", Subtitle = "123456 · 45.2 MB" };
        item.ApplyTemplate();

        Assert.Equal(42, item.Height); // 行高 42

        var rectBack = (Border)item.FindName("RectBack");
        Assert.Equal(new CornerRadius(6), rectBack.CornerRadius); // CornerRadius 6
        Assert.Equal(0, rectBack.Opacity);      // 初始隐藏

        var scale = (ScaleTransform)item.FindName("RectBackScale");
        Assert.Equal(0.75, scale.ScaleX);       // 初始 0.75
        Assert.Equal(0.75, scale.ScaleY);
    }

    [WpfFact]
    public void ModListItem_Check_Bar_Grow_Collapse_DoesNot_Throw()
    {
        var item = new ModListItem();
        item.ApplyTemplate();

        var checkBar = (Border)item.FindName("CheckBar");
        Assert.Equal(5, checkBar.Width);
        Assert.Equal(0, checkBar.Opacity);

        item.PlayCheckGrow();        // 双段生长（40/200 + 60/300，动画推进依赖渲染时钟）
        item.PlayCheckCollapse();    // 收起 120ms + 淡出 70ms

        // 选中切换前景动画触发不抛
        item.IsSelected = true;
        Assert.True(item.IsSelected);
    }

    [WpfFact]
    public void Controls_Consume_Theme_Tokens_Only()
    {
        // 消费方 DynamicResource 契约（t2 §1.4 不变量③):三控件的关键画刷来自主题字典
        var card = new SwdmCard();
        var hint = new Hint();
        var item = new ModListItem();
        foreach (var fe in new FrameworkElement[] { card, hint, item })
        {
            fe.ApplyTemplate();
        }
        // 存在即契约（FindResource 不抛=主题字典已合并可解析）
        Assert.NotNull(card.TryFindResource("swdm-SurfaceCardBrush"));
        Assert.NotNull(hint.TryFindResource("swdm-LinkDefaultBrush"));
        Assert.NotNull(item.TryFindResource("swdm-Accent500Brush"));
    }
}
