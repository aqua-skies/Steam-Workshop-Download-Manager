using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// Hint 提示条（t2 §2.2)：左 3px 语义色条+圆角 2+padding 12,9。
/// 语义档位（色条+用途，沿用令牌）：
/// Info=link.default / Success=success.500 / Warning=warning.500(429-403 限流提示专用）/
/// Error=danger.500。文字=TextPrimary;背景=SurfaceCard。
/// 关闭钮点击后 Visibility=Collapsed（验收判据②）。
/// </summary>
public partial class Hint : UserControl
{
    public static readonly DependencyProperty MessageProperty =
        DependencyProperty.Register(nameof(Message), typeof(string), typeof(Hint),
            new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty KindProperty =
        DependencyProperty.Register(nameof(Kind), typeof(HintKind), typeof(Hint),
            new PropertyMetadata(HintKind.Info, OnKindChanged));

    public static readonly DependencyProperty CloseAutomationIdProperty =
        DependencyProperty.Register(nameof(CloseAutomationId), typeof(string), typeof(Hint),
            new PropertyMetadata("Page_Hint_Close")); // 消费页注入：<页面>_Hint_Close

    /// <summary>语义色刷（左色条 BorderBrush，四档令牌）。</summary>
    public static readonly DependencyProperty SemanticColorProperty =
        DependencyProperty.Register(nameof(SemanticColor), typeof(SolidColorBrush), typeof(Hint),
            new PropertyMetadata(null));

    public Hint()
    {
        InitializeComponent();
        ApplySemanticColor(Kind);
    }

    /// <summary>提示文案（TextWrapping=Wrap,LineHeight 16)。</summary>
    public string Message
    {
        get => (string)GetValue(MessageProperty);
        set => SetValue(MessageProperty, value);
    }

    /// <summary>语义档位（决定左色条颜色）。</summary>
    public HintKind Kind
    {
        get => (HintKind)GetValue(KindProperty);
        set => SetValue(KindProperty, value);
    }

    /// <summary>关闭钮 AutomationId（t3 契约 &lt;页面&gt;_Hint_Close，消费页注入）。</summary>
    public string CloseAutomationId
    {
        get => (string)GetValue(CloseAutomationIdProperty);
        set => SetValue(CloseAutomationIdProperty, value);
    }

    /// <summary>左色条语义刷（DynamicResource 求值，换主题即时变色）。</summary>
    public SolidColorBrush SemanticColor
    {
        get => (SolidColorBrush)GetValue(SemanticColorProperty);
        private set => SetValue(SemanticColorProperty, value);
    }

    private static void OnKindChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is Hint hint)
            hint.ApplySemanticColor((HintKind)e.NewValue);
    }

    private void ApplySemanticColor(HintKind kind)
    {
        SemanticColor = kind switch
        {
            HintKind.Info => (SolidColorBrush)FindResource("swdm-LinkDefaultBrush"),
            HintKind.Success => (SolidColorBrush)FindResource("swdm-Success500Brush"),
            HintKind.Warning => (SolidColorBrush)FindResource("swdm-Warning500Brush"),
            HintKind.Error => (SolidColorBrush)FindResource("swdm-Danger500Brush"),
            _ => (SolidColorBrush)FindResource("swdm-LinkDefaultBrush"),
        };
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
        => Visibility = Visibility.Collapsed;
}

/// <summary>提示条语义档位（t2 §2.2)。</summary>
public enum HintKind
{
    Info,
    Success,
    Warning,  // 限流提示专用（对齐 SteamError RateLimited)
    Error,
}
