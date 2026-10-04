using System.Collections.ObjectModel;
using System.Windows.Media.Imaging;
using System.Windows.Media;
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
        // D9.1(t67) 用户硬约束"死钮禁止交付"：开始钮=未绑定游戏时禁用
        // （CanExecute 随绑定状态刷新；t64/t65 订阅链同源）
        StartGameCommand = new RelayCommand(
            () => startGame?.Invoke(),
            () => _defaultGame?.Current is not null);
        DownloadModCommand = new RelayCommand(() => downloadMod?.Invoke());

        // D5.20c/t64:默认游戏即时响应（订阅变更=设置页绑定后主页立即刷新）
        if (_defaultGame is not null)
        {
            _defaultGame.PropertyChanged += (_, e) =>
            {
                ApplyDefaultGame();
                if (e.PropertyName == nameof(DefaultGameService.Current))
                    System.Windows.Input.CommandManager.InvalidateRequerySuggested();
            };
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
    /// t65(D5.20d):真实游戏图标=AppId 拼 Steam CDN header 图（1.x 实证
    /// cdn.cloudflare.steamstatic.com/steam/apps/{id}/header.jpg 可用；
    /// 本机实测 322330→200 50512B)。BitmapImage 延迟下载=不阻塞 UI;
    /// CDN 失败=WPF 静默降级空图（不崩；Icon 非空即贴图槽位生效）。
    /// </summary>
    private void ApplyDefaultGame()
    {
        var g = _defaultGame?.Current;
        // 卡片图标槽=同一 CDN header 图（WPF ImageSourceConverter 字符串 URL 自动转）
        UpdateDefaultGame(g?.Title, g is { AppId: > 0 }
            ? $"https://cdn.cloudflare.steamstatic.com/steam/apps/{g.AppId}/header.jpg"
            : null);

        Tiles.Clear();
        if (g is not null)
        {
            // 球体贴图区该游戏图标上浮：Icon=BitmapImage(CDN header 图）
            ImageSource? tileIcon = null;
            if (g.AppId > 0)
            {
                try
                {
                    tileIcon = new BitmapImage(new Uri(
                        $"https://cdn.cloudflare.steamstatic.com/steam/apps/{g.AppId}/header.jpg",
                        UriKind.Absolute));
                }
                catch
                {
                    tileIcon = null; // URL 构造失败=诚实空（控件材质紫色 fallback）
                }
            }
            Tiles.Add(new SphereGameTile
            {
                AppId = g.AppId,
                Title = g.Title,
                Icon = tileIcon,
                AssignedTriangles = new[] { 0 },
            });
        }
    }
}