using System.Windows;

namespace Swdm2.App.Views;

/// <summary>
/// download complete dialog (#255 path; D3.5b minimum testable skeleton).
/// BasicAutomationProperties contract: Window + OkButton are A7 reliable carriers.
/// </summary>
public partial class DownloadCompleteDialog : Window
{
    public string TaskTitle
    {
        get => (string)GetValue(TaskTitleProperty);
        set => SetValue(TaskTitleProperty, value);
    }

    public string ProductPath
    {
        get => (string)GetValue(ProductPathProperty);
        set => SetValue(ProductPathProperty, value);
    }

    public static readonly DependencyProperty TaskTitleProperty =
        DependencyProperty.Register(nameof(TaskTitle), typeof(string), typeof(DownloadCompleteDialog),
            new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty ProductPathProperty =
        DependencyProperty.Register(nameof(ProductPath), typeof(string), typeof(DownloadCompleteDialog),
            new PropertyMetadata(string.Empty));

    public DownloadCompleteDialog()
    {
        InitializeComponent();
        DataContext = this;
    }

    private void OkButton_Click(object sender, RoutedEventArgs e)
        => DialogResult = true;
}
