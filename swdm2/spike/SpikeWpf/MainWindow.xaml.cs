using System.Collections.ObjectModel;
using System.Windows;
using Wpf.Ui.Controls;

namespace Swdm2.Spike;

/// <summary>
/// Spike 主窗口：WPF-UI 基座控件 + 自绘 SwdmCard 混排，供 FlaUI 真实输入测试驱动。
/// </summary>
public partial class MainWindow : FluentWindow
{
    private readonly ObservableCollection<string> _results = new();

    public MainWindow()
    {
        InitializeComponent();
        SpikeResultList.ItemsSource = _results;
    }

    /// <summary>搜索按钮：把搜索框文本 + 时间戳加入结果列表（真实状态变更，供断言）。</summary>
    private void SpikeSearchButton_Click(object sender, RoutedEventArgs e)
    {
        AddResult();
    }

    /// <summary>WPF-UI 卡片内按钮：同上（验证基座控件事件链路）。</summary>
    private void SpikeWpfCardButton_Click(object sender, RoutedEventArgs e)
    {
        _results.Insert(0, $"[WPF-UI Card] {SpikeSearchBox.Text} @ {DateTime.Now:HH:mm:ss}");
    }

    /// <summary>自绘卡片内按钮：弹出真实 MessageBox（FlaUI #255 弹窗点击路径测试）。</summary>
    private void SpikeCardButton_Click(object sender, RoutedEventArgs e)
    {
        // 不打桩、不替换：MessageBox 该弹还弹，测试像用户一样去点确定
        MessageBox.Show(this, "这是自绘卡片按钮触发的真实提示弹窗。", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void AddResult()
    {
        var keyword = string.IsNullOrEmpty(SpikeSearchBox.Text) ? "(空)" : SpikeSearchBox.Text;
        _results.Insert(0, $"{keyword} @ {DateTime.Now:HH:mm:ss}");
    }
}
