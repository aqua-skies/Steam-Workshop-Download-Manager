using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace Swdm2.App.Ui.Converters;

/// <summary>
/// bool→Visibility 反向转换器（D9.1/t67 缩略图占位槽位）:
/// true=Collapsed;false/null=Visible（与 BoolToVisibility 相互补。
/// </summary>
public sealed class InverseBoolToVisibilityConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is Visibility.Collapsed;
}
