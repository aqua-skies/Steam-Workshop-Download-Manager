using System.Windows;
using System.Windows.Controls;

namespace Swdm2.Spike.Controls;

/// <summary>
/// 自绘卡片（PCL2 MyCard 三层结构的 C#/XAML 移植样本，非产品代码）：
/// 阴影层 90ms 0.07→0.4 悬停抬升 + 96% 白卡底 + 标题层。
/// </summary>
public partial class SwdmCard : UserControl
{
    public static readonly DependencyProperty CardTitleProperty =
        DependencyProperty.Register(nameof(CardTitle), typeof(string), typeof(SwdmCard),
            new PropertyMetadata("卡片标题"));

    public string CardTitle
    {
        get => (string)GetValue(CardTitleProperty);
        set => SetValue(CardTitleProperty, value);
    }

    public SwdmCard()
    {
        InitializeComponent();
    }
}
