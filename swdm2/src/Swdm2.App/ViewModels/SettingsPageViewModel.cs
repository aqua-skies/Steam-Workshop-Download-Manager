using System.IO;
using System.Collections.ObjectModel;
using System.Linq;
using System.Collections.Generic;
using Swdm2.Core.Domain;
using Swdm2.App.Games;
using Swdm2.Steam.Web;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using Swdm2.App.Boot;
using Swdm2.App.Updates;
using Swdm2.App.Connectivity;
using Swdm2.App.Ui.Themes;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 设置页 VM(D5.18;t2 v1.4 §D5.8 分组规格）:
/// - 分组=账号/SteamCMD/网络（代理模式下拉+A2 抽屉 Custom 输入+必填校验）/
///   外观（主题切换即时预览）/高级（节流/并发/退避起点值）
/// - 保存=写 JSON 到 IPathService.ConfigFile(SwdmConfiguration reloadOnChange
///   叠加=IOptionsMonitor 热更新）+SwitchProxyModeAsync 重探（t48 契约）
/// - 主题即时预览=ThemeService.Apply 立即换皮（A4 无闪烁换 MergedDictionaries）
/// - Custom 校验=空白 URL 拒绝保存+提示（诚实不造假）
/// </summary>
public sealed class SettingsPageViewModel : ViewModelBase
{
    private readonly IPathService _paths;
    private readonly IConnectivityController _connectivity;
    private readonly ThemeService _themeService;
    // D6.3: 升级服务（Velopack UpdateManager 封装）
    private readonly UpdateService? _updates;

    private ProxyMode _proxyMode = ProxyMode.SystemProxy;
    private string _customProxyUrl = string.Empty;
    private SwdmTheme _theme = SwdmTheme.Dark;
    private string _validationMessage = string.Empty;
    private bool _customPanelVisible;
    private string _userName = string.Empty;
    private string _steamCmdDirectory = string.Empty;
    // D5.20c: 默认游戏搜索（复用 t43 GameAliasTable+storesearch 合并）
    private string _gameSearchTerm = string.Empty;
    private bool _isSearchingGames;
    private string _gameSearchHint = string.Empty;
    private readonly IStoreSearchClient? _storeSearch;
    private readonly DefaultGameService? _defaultGame;
    private System.Windows.Threading.DispatcherTimer? _gameDebounce;
    private CancellationTokenSource? _gameCts;

    public ProxyMode ProxyMode
    {
        get => _proxyMode;
        set
        {
            if (SetProperty(ref _proxyMode, value))
            {
                // A2 抽屉：Custom 模式展开输入区（SlideDown 300ms 由 view 触发）
                CustomPanelVisible = value == ProxyMode.Custom;
                ValidationMessage = string.Empty;
                RaisePropertyChanged(nameof(ProxyModeIndex));
                RaisePropertyChanged(nameof(CustomPanelVisibility));
            }
        }
    }

    public string CustomProxyUrl
    {
        get => _customProxyUrl;
        set { SetProperty(ref _customProxyUrl, value); ValidationMessage = string.Empty; }
    }

    /// <summary>主题（即时预览：选择即 Apply;A4 换皮无闪烁）。</summary>
    public SwdmTheme Theme
    {
        get => _theme;
        set
        {
            if (SetProperty(ref _theme, value))
            {
                _themeService.Apply(value); // 即时预览（保存落盘前视觉已变）
                RaisePropertyChanged(nameof(ThemeIsLight));
                RaisePropertyChanged(nameof(ThemeIsDark));
                RaisePropertyChanged(nameof(ThemeIsFollowSystem));
            }
        }
    }

    /// <summary>Custom 输入区可见（A2 抽屉语义；view 层 SlideDown/SlideUp)。</summary>
    public bool CustomPanelVisible
    {
        get => _customPanelVisible;
        set => SetProperty(ref _customPanelVisible, value);
    }

    /// <summary>抽屉 Visibility（直接绑 Visibility;省 converter;A2)。</summary>
    public Visibility CustomPanelVisibility => CustomPanelVisible ? Visibility.Visible : Visibility.Collapsed;

    /// <summary>ComboBox 选中索引（0=Direct/1=SystemProxy/2=Custom)。</summary>
    public int ProxyModeIndex
    {
        get => (int)ProxyMode;
        set
        {
            if (value >= 0 && value <= 2 && (ProxyMode)value != ProxyMode)
                ProxyMode = (ProxyMode)value;
        }
    }

    public bool ThemeIsLight
    {
        get => Theme == SwdmTheme.Light;
        set { if (value) Theme = SwdmTheme.Light; }
    }

    public bool ThemeIsDark
    {
        get => Theme == SwdmTheme.Dark;
        set { if (value) Theme = SwdmTheme.Dark; }
    }

    public bool ThemeIsFollowSystem
    {
        get => Theme == SwdmTheme.FollowSystem;
        set { if (value) Theme = SwdmTheme.FollowSystem; }
    }

    /// <summary>校验/保存结果提示（失败不隐藏=诚实）。</summary>
    public string ValidationMessage
    {
        get => _validationMessage;
        set => SetProperty(ref _validationMessage, value);
    }

    public string UserName
    {
        get => _userName;
        set => SetProperty(ref _userName, value);
    }

    public string SteamCmdDirectory
    {
        get => _steamCmdDirectory;
        set => SetProperty(ref _steamCmdDirectory, value);
    }

    /// <summary>保存=持久化 JSON+重探代理（t48 契约）。</summary>
    public ICommand SaveCommand { get; }

    /// <summary>D6.3:检查更新（Velopack feed)。</summary>
    public ICommand CheckUpdateCommand { get; }

    /// <summary>D6.3:下载更新（进度推进）。</summary>
    public ICommand DownloadUpdateCommand { get; }

    /// <summary>D6.3:应用更新并重启（VelopackApp.Run 钩子消费）。</summary>
    public ICommand ApplyUpdateCommand { get; }

    // ===== D5.20c/t64:默认游戏（设置页绑定游戏实物）=====

    /// <summary>搜索候选（别名表本地即时+storesearch 在线合并，t43 同算法）。</summary>
    public ObservableCollection<GameInfo> GameSuggestions { get; } = new();

    /// <summary>搜索词（防抖 350ms)。</summary>
    public string GameSearchTerm
    {
        get => _gameSearchTerm;
        set
        {
            if (!SetProperty(ref _gameSearchTerm, value)) return;
            IsSearchingGames = true;
            _gameDebounce?.Stop();
            if (!string.IsNullOrWhiteSpace(value)) _gameDebounce?.Start();
            else { GameSuggestions.Clear(); IsSearchingGames = false; GameSearchHint = string.Empty; }
        }
    }

    public bool IsSearchingGames
    {
        get => _isSearchingGames;
        private set => SetProperty(ref _isSearchingGames, value);
    }

    /// <summary>候选来源提示（离线兜底显式标注：sample/别名表/在线）。</summary>
    public string GameSearchHint
    {
        get => _gameSearchHint;
        private set => SetProperty(ref _gameSearchHint, value);
    }

    /// <summary>选中候选=绑定默认游戏并持久化（主页即时响应）。</summary>
    public ICommand SelectGameCommand { get; }

    /// <summary>当前已绑定游戏（null=空态）。</summary>
    public BoundGame? BoundGame => _defaultGame?.Current;

    /// <summary>已绑定显示文本（未绑定=空态引导）。</summary>
    public string BoundGameDisplay => _defaultGame?.Current is { } g
        ? $"{g.Title} (AppId {g.AppId})" : "未绑定（搜索并选择游戏后保存）";

    /// <summary>sample 离线兜底显式标注（搜索源说明）。</summary>
    public string GameSourceNote => _storeSearch is null
        ? "离线别名表（在线源未装配）"
        : "内置别名表+Steam storesearch 在线合并（离线时仅别名表兜底）";

    /// <summary>D6.3:升级服务状态镜像（绑 Message/Progress)。</summary>
    public UpdateService? Updates => _updates;

    /// <summary>升级进度（0-100;下载中推进）。</summary>
    public int UpdateDownloadProgress => _updates?.DownloadProgress ?? 0;

    /// <summary>升级状态消息（检查/下载/错误文案；诚实不吞）。</summary>
    public string UpdateMessage => _updates?.Message ?? string.Empty;

    /// <summary>覆盖安装（非 Velopack 通道）提示可见性（t58 诚实降级②)。</summary>
    public Visibility UpdateOverwriteHintVisibility =>
        _updates is { State: UpdateService.UpdateState.OverwriteInstall }
            ? Visibility.Visible : Visibility.Collapsed;

    /// <summary>下载进度条可见性（仅 Downloading)。</summary>
    public Visibility UpdateProgressVisibility =>
        _updates is { State: UpdateService.UpdateState.Downloading }
            ? Visibility.Visible : Visibility.Collapsed;

    // ComboBox=双向绑 ProxyModeIndex（直驱 A2 抽屉，无需命令）

    /// <summary>
    /// D6.3 releases feed 默认值：开发期=file:// artifacts(t58 已就位双版本索引）;
    /// 生产期换 GitHub Releases URL(D7 发布前配置化）。
    /// </summary>
    /// <summary>
    /// 默认升级 feed 解析：上溯 artifacts(t58 双版本索引）→Velopack 自安装上下文
    /// （update.exe 同级);缺则回退 exe 目录（覆盖安装下不读 feed=降级②安全路径）。
    /// </summary>
    private static IUpdateManager CreateDefaultUpdateManager(string? urlOverride)
    {
        var feed = urlOverride;
        if (string.IsNullOrEmpty(feed))
        {
            var dir = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var cand = System.IO.Path.Combine(dir.FullName, "artifacts");
                if (System.IO.File.Exists(System.IO.Path.Combine(cand, "RELEASES")))
                {
                    feed = cand;
                    break;
                }
                dir = dir.Parent;
            }
        }
        try
        {
            return new VelopackUpdateManager(feed ?? AppContext.BaseDirectory);
        }
        catch
        {
            return new NullUpdateManager(); // 上下文不可用=覆盖安装诚实降级②
        }
    }

    public SettingsPageViewModel(
        IPathService paths,
        IConnectivityController connectivity,
        ThemeService themeService,
        SteamOptions? steamOptions = null,
        DownloadOptions? downloadOptions = null,
        IUpdateManager? updateManager = null,
        string? releasesFeedUrl = null,
        IStoreSearchClient? storeSearch = null,
        DefaultGameService? defaultGame = null)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _connectivity = connectivity ?? throw new ArgumentNullException(nameof(connectivity));
        _themeService = themeService ?? throw new ArgumentNullException(nameof(themeService));

        // D6.3:升级服务（可注入桩测试；默认=上溯本地 artifacts feed(t60 实测通道；
        // Velopack 安装环境=update.exe 同级 feed，GitHub Releases 于 D7 发布期配置化）
        _storeSearch = storeSearch;
        _defaultGame = defaultGame;
        _gameDebounce = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromMilliseconds(350) };
        _gameDebounce.Tick += OnGameDebounceTick;
        _updates = new UpdateService(
            updateManager ?? CreateDefaultUpdateManager(releasesFeedUrl));

        // 当前值加载（option 快照）
        if (steamOptions is not null)
        {
            _proxyMode = steamOptions.Proxy;
            _customProxyUrl = steamOptions.CustomProxyUrl ?? string.Empty;
            CustomPanelVisible = _proxyMode == ProxyMode.Custom;
        }
        _steamCmdDirectory = Path.Combine(paths.SteamCmdDirectory, "steamcmd.exe");
        _theme = _themeService.Current;

        SaveCommand = new RelayCommand(async () => await SaveAsync()); // 校验在 Save 内

        // D6.3:升级流程命令（转发 UpdateService 状态机；UI 进度/消息经 mirror 属性）
        CheckUpdateCommand = new RelayCommand(async () =>
        {
            if (_updates is null) return;
            await _updates.CheckAsync();
            RaiseUpdateMirrors();
        });
        DownloadUpdateCommand = new RelayCommand(async () =>
        {
            if (_updates is null) return;
            await _updates.DownloadAsync();
            RaiseUpdateMirrors();
        });
        ApplyUpdateCommand = new RelayCommand(async () =>
        {
            if (_updates is null) return;
            await _updates.ApplyAsync();
            RaiseUpdateMirrors();
        });

        // D5.20c/t64:选中候选=绑定默认游戏（持久化+主页即时响应）
        SelectGameCommand = new RelayCommand(obj =>
        {
            if (obj is not GameInfo g || _defaultGame is null) return;
            _defaultGame.Bind(_paths, new BoundGame(g.Id.Value, g.Name, null)); // IconUrl 待 D6 图标源
            GameSearchTerm = string.Empty;
            GameSuggestions.Clear();
            RaisePropertyChanged(nameof(BoundGame));
            RaisePropertyChanged(nameof(BoundGameDisplay));
            ValidationMessage = $"已绑定默认游戏：{g.Name}";
        });
    }

    /// <summary>D6.3:UpdateService 状态变化后镜像属性刷新（消息/进度/可见性）。</summary>
    private void RaiseUpdateMirrors()
    {
        RaisePropertyChanged(nameof(UpdateMessage));
        RaisePropertyChanged(nameof(UpdateDownloadProgress));
        RaisePropertyChanged(nameof(UpdateProgressVisibility));
        RaisePropertyChanged(nameof(UpdateOverwriteHintVisibility));
    }

    /// <summary>保存：校验→写 JSON→重探（端点/代理）。</summary>
    public async Task SaveAsync()
    {
        // Custom 必填校验（t57 契约；失败=提示不保存）
        if (ProxyMode == ProxyMode.Custom && string.IsNullOrWhiteSpace(CustomProxyUrl))
        {
            ValidationMessage = "自定义代理 URL 必填（Custom 模式）";
            return;
        }
        if (ProxyMode == ProxyMode.Custom && !Uri.TryCreate(CustomProxyUrl, UriKind.Absolute, out _))
        {
            ValidationMessage = "自定义代理 URL 格式无效（如 http://127.0.0.1:7897）";
            return;
        }

        try
        {
            // 主题即时预览已 Apply;持久化=JSON 写 ConfigFile
            var payload = new
            {
                Steam = new
                {
                    Proxy = ProxyMode.ToString(),
                    CustomProxyUrl = string.IsNullOrWhiteSpace(CustomProxyUrl) ? null : CustomProxyUrl.Trim(),
                },
                Appearance = new { Theme = Theme.ToString() },
            };
            var json = JsonSerializer.Serialize(payload, new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            });
            Directory.CreateDirectory(Path.GetDirectoryName(_paths.ConfigFile)!);
            File.WriteAllText(_paths.ConfigFile, json); // reloadOnChange=IOptionsMonitor 热更

            // 重探（t48 契约：端点/代理；Custom 必填其内再守一次）
            await _connectivity.SwitchProxyModeAsync(ProxyMode,
                ProxyMode == ProxyMode.Custom ? CustomProxyUrl.Trim() : null);

            ValidationMessage = "已保存并重新探测端点";
        }
        catch (Exception ex)
        {
            ValidationMessage = $"保存失败：{ex.GetType().Name}"; // 诚实不吞
        }
    }

    /// <summary>D5.20c:防抖到点=本地别名表即时+storesearch 在线合并（t43 同算法）。</summary>
    private async void OnGameDebounceTick(object? sender, EventArgs e)
    {
        _gameDebounce?.Stop();
        _gameCts?.Cancel();
        _gameCts = new CancellationTokenSource();
        var ct = _gameCts.Token;
        var term = _gameSearchTerm;
        if (string.IsNullOrWhiteSpace(term)) { GameSuggestions.Clear(); IsSearchingGames = false; return; }

        var local = GameAliasTable.Match(term, maxCount: 10);
        GameSuggestions.Clear();
        foreach (var g in local) GameSuggestions.Add(g);

        if (_storeSearch is not null)
        {
            try
            {
                var result = await _storeSearch.SearchGamesAsync(term, ct);
                if (!ct.IsCancellationRequested && result is { IsOk: true, Value: not null })
                {
                    var merged = new List<GameInfo>(result.Value);
                    var ids = new HashSet<int>(result.Value.Select(x => x.Id.Value));
                    foreach (var g in local) if (ids.Add(g.Id.Value)) merged.Add(g);
                    GameSuggestions.Clear();
                    foreach (var g in merged) GameSuggestions.Add(g);
                    GameSearchHint = merged.Count + " 条候选（内置别名表+在线合并）";
                }
            }
            catch (OperationCanceledException) { }
            catch
            {
                if (!ct.IsCancellationRequested)
                    GameSearchHint = GameSuggestions.Count + " 条候选（在线不可达=别名表兜底）";
            }
        }
        else
        {
            GameSearchHint = local.Count + " 条候选（仅本地别名表）";
        }
        if (!ct.IsCancellationRequested) IsSearchingGames = false;
    }
}