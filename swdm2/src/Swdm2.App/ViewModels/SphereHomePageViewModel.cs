using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;
using Swdm2.App.Ui.Controls.HomeSphere;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 球体主页 VM(D5.15;t2 v1.4 §2.8/2.9):
/// - Tiles=球体贴图游戏瓦片（绑定游戏；空=全透明球+空态引导）
/// - DefaultGameTitle/Icon/空态=左侧默认游戏卡四槽位（§2.9)
/// - TileClickedCommand=贴图点击→跳该游戏 mod 选择页（旅程入口）
/// - StartGameCommand/DownloadModCommand=默认游戏卡直通
/// </summary>
public sealed class SphereHomePageViewModel : ViewModelBase
{
    private string _defaultGameTitle = string.Empty;
    private string? _defaultGameIcon;
    private Visibility _emptyHintVisibility = Visibility.Collapsed;

    public ObservableCollection<SphereGameTile> Tiles { get; } = new();

    /// <summary>§2.9 槽位 i 名（默认游戏名；空=空态）。</summary>
    public string DefaultGameTitle
    {
        get => _defaultGameTitle;
        set => SetProperty(ref _defaultGameTitle, value);
    }

    /// <summary>§2.9 槽位 ii 图标（上）。</summary>
    public string? DefaultGameIcon
    {
        get => _defaultGameIcon;
        set => SetProperty(ref _defaultGameIcon, value);
    }

    /// <summary>§2.9 空态「无默认游戏，前往设置」灰字可见性。</summary>
    public Visibility EmptyHintVisibility
    {
        get => _emptyHintVisibility;
        set => SetProperty(ref _emptyHintVisibility, value);
    }

    /// <summary>球体贴图点击=跳该游戏 mod 选择页（AppId 参数）。</summary>
    public ICommand TileClickedCommand { get; }

    /// <summary>§2.9 槽位 iii 开始游戏。</summary>
    public ICommand StartGameCommand { get; }

    /// <summary>§2.9 槽位 iv「下载 mod」直通。</summary>
    public ICommand DownloadModCommand { get; }

    public SphereHomePageViewModel(
        Action<int>? navigateToGameSelect = null,
        Action? startGame = null,
        Action? downloadMod = null)
    {
        TileClickedCommand = new RelayCommand(
            p => navigateToGameSelect?.Invoke(Convert.ToInt32(p, System.Globalization.CultureInfo.InvariantCulture)));
        StartGameCommand = new RelayCommand(() => startGame?.Invoke());
        DownloadModCommand = new RelayCommand(() => downloadMod?.Invoke());
    }

    /// <summary>更新默认游戏卡（无默认游戏=空态灰字）。</summary>
    public void UpdateDefaultGame(string? title, string? icon)
    {
        DefaultGameTitle = string.IsNullOrEmpty(title) ? "未绑定默认游戏" : title;
        DefaultGameIcon = icon;
        EmptyHintVisibility = string.IsNullOrEmpty(title) ? Visibility.Visible : Visibility.Collapsed;
    }
}