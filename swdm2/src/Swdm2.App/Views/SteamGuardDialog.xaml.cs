using System.Windows;

namespace Swdm2.App.Views;

/// <summary>
/// Steam Guard 收码弹窗（D4.1 A11/#23):
/// - AutomationId 全套按 t3 §3.2 保留表（SteamGuardDialog / CodeBox_Input / ConfirmButton / CancelButton);
/// - ShowDialog 模态阻塞主窗口（#23 断言点）；确定=返回验证码，取消=返回 null（登录侧 AuthRequired);
/// - 验证码通过 <see cref="SteamGuardDialog_CodeBox_Input"/> TextBox 真实键盘输入（#23 真实输入）。
/// </summary>
public partial class SteamGuardDialog : Window
{
    public string? Code => CodeBoxInput.Text;

    public SteamGuardDialog(string account)
    {
        InitializeComponent();
        AccountLabel.Text = string.IsNullOrEmpty(account) ? "账号：anonymous" : $"账号：{account}";
    }

    private void ConfirmButton_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
        Close();
    }

    private void CancelButton_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
