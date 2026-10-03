using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using Swdm2.App.Boot;
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

    private ProxyMode _proxyMode = ProxyMode.SystemProxy;
    private string _customProxyUrl = string.Empty;
    private SwdmTheme _theme = SwdmTheme.Dark;
    private string _validationMessage = string.Empty;
    private bool _customPanelVisible;
    private string _userName = string.Empty;
    private string _steamCmdDirectory = string.Empty;

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

    // ComboBox=双向绑 ProxyModeIndex（直驱 A2 抽屉，无需命令）

    public SettingsPageViewModel(
        IPathService paths,
        IConnectivityController connectivity,
        ThemeService themeService,
        SteamOptions? steamOptions = null,
        DownloadOptions? downloadOptions = null)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _connectivity = connectivity ?? throw new ArgumentNullException(nameof(connectivity));
        _themeService = themeService ?? throw new ArgumentNullException(nameof(themeService));

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
}