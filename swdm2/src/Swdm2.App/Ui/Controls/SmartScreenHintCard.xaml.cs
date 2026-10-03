using System.Windows.Controls;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// SmartScreen 未签名提示卡（D6.3;captain v2.1 条款：诚实引导不伪装签名）。
/// 纯展示控件（无代码后逻辑）；将来签名发布时本卡可整体下线。
/// </summary>
public partial class SmartScreenHintCard : UserControl
{
    public SmartScreenHintCard()
    {
        InitializeComponent();
    }
}
