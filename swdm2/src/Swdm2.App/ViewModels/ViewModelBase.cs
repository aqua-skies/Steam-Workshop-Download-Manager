using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Swdm2.App.ViewModels;

/// <summary>
/// MVVM base（D3.5b 最小骨架）：INotifyPropertyChanged + SetProperty。
/// 皮肤级实现（CommunityToolkit.Mvvm 源生成器）留 D5 统一切换；本阶段手写零依赖。
/// </summary>
public abstract class ViewModelBase : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    protected bool SetProperty<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
            return false;
        field = value;
        RaisePropertyChanged(propertyName);
        return true;
    }

    protected void RaisePropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
