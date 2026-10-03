using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace Swdm2.App.Ui.Converters;

/// <summary>
/// bool→Visibility 转换器（t59 库页更新角标/Hint/行标记）:
/// true=Visible;false/null=Collapsed。反向=Hidden 语义不用（占位布局无关）。
/// </summary>
public sealed class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is Visibility.Visible;
}
