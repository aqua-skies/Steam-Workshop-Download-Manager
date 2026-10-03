using System.Windows;
using Swdm2.App.Connectivity;
using Swdm2.Core.Options;

namespace Swdm2.App.Views;

/// <summary>
/// 代理配置弹窗（D5.9 失败引导）：S5 ProxyMode 三态 + Custom 必填校验；
/// 应用=SwitchProxyModeAsync（重建工厂+立即重探+状态栏即时更新）。
/// </summary>
public partial class ProxyConfigDialog : Window
{
    private readonly IConnectivityController _controller;

    public ProxyConfigDialog(IConnectivityController controller)
    {
        InitializeComponent();
        _controller = controller ?? throw new ArgumentNullException(nameof(controller));

        // 当前模式回显
        ModeCombo.SelectedIndex = _controller.CurrentProxyMode switch
        {
            ProxyMode.Direct => 0,
            ProxyMode.SystemProxy => 1,
            _ => 2,
        };
        CustomUrlBox.Text = _controller.CustomProxyUrl ?? string.Empty;
    }

    private async void Apply_Click(object sender, RoutedEventArgs e)
    {
        var mode = ModeCombo.SelectedIndex switch
        {
            0 => ProxyMode.Direct,
            1 => ProxyMode.SystemProxy,
            _ => ProxyMode.Custom,
        };
        var url = CustomUrlBox.Text.Trim();

        if (mode == ProxyMode.Custom && string.IsNullOrWhiteSpace(url))
        {
            ErrorText.Text = "Custom 模式需要代理 URL（如 http://127.0.0.1:7897）";
            ErrorText.Visibility = Visibility.Visible;
            return;
        }
        if (mode == ProxyMode.Custom && !Uri.TryCreate(url, UriKind.Absolute, out _))
        {
            ErrorText.Text = "代理 URL 格式无效（需绝对 http/https URL)";
            ErrorText.Visibility = Visibility.Visible;
            return;
        }

        ErrorText.Visibility = Visibility.Collapsed;
        DialogResult = true;
        Close();
        // 切代理即时更新（S5:重建工厂+重探；状态栏由事件即时刷新）
        await _controller.SwitchProxyModeAsync(mode, string.IsNullOrWhiteSpace(url) ? null : url)
            .ConfigureAwait(false);
    }
}
