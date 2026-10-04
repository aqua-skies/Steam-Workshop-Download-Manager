using System.Collections.ObjectModel;
using Swdm2.App.Games;
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
    // D5.20c/t64:默认游戏服务（设置页绑定=主页即时响应）
    private readonly DefaultGameService? _defaultGame;

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
        Action? downloadMod = null,
        DefaultGameService? defaultGame = null)
    {
        _defaultGame = defaultGame;

        TileClickedCommand = new RelayCommand(
            p => navigateToGameSelect?.Invoke(Convert.ToInt32(p, System.Globalization.CultureInfo.InvariantCulture)));
        StartGameCommand = new RelayCommand(() => startGame?.Invoke());
        DownloadModCommand = new RelayCommand(() => downloadMod?.Invoke());

        // D5.20c/t64:默认游戏即时响应（订阅变更=设置页绑定后主页立即刷新）
        if (_defaultGame is not null)
        {
            _defaultGame.PropertyChanged += (_, _) => ApplyDefaultGame();
            ApplyDefaultGame();
        }
    }

    /// <summary>更新默认游戏卡（无默认游戏=空态灰字）。</summary>
    public void UpdateDefaultGame(string? title, string? icon)
    {
        DefaultGameTitle = string.IsNullOrEmpty(title) ? "未绑定默认游戏" : title;
        DefaultGameIcon = icon;
        EmptyHintVisibility = string.IsNullOrEmpty(title) ? Visibility.Visible : Visibility.Collapsed;
    }

    /// <summary>
    /// D5.20c:DefaultGameService.Current → 卡片+球体贴图刷新
    /// （贴图上浮=Tiles 首槽位=已绑定游戏；EmptyHint 消失）。
    /// </summary>
    private void ApplyDefaultGame()
    {
        var g = _defaultGame?.Current;
        UpdateDefaultGame(g?.Title, g?.IconUrl);

        Tiles.Clear();
        if (g is not null)
        {
            // 球体贴图区该游戏图标上浮（Icon=IconUrl→ImageSource;D6 真实图标源前=空=透明槽位在位）
            Tiles.Add(new SphereGameTile
            {
                AppId = g.AppId,
                Title = g.Title,
                Icon = null, // 待 D6 图标源（IconUrl 不能直接转 ImageSource,保持诚实空）
                AssignedTriangles = new[] { 0 },
            });
        }
    }
}