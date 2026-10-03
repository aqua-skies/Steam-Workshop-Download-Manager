using System.Collections.ObjectModel;
using System.Windows.Media;
using System.Windows;
using System.Windows.Input;
using Swdm2.App.Connectivity;
using Swdm2.App.Views;
using Swdm2.Core.Options;
using Swdm2.Steam.Connectivity;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 状态栏连接视图模型（D5.9):
/// - 端点状态条目（Api/Store/Community 三芯片：可达性+延迟+语义色）
/// - 代理模式标签（直连/系统代理/自定义代理）
/// - 失败引导（HasFailures → Hint 横幅+配代理按钮→ProxyConfigDialog)
/// - 刷新/应用代理命令（切代理即时更新=代理切换事件→重探→Current 变更）
/// </summary>
public sealed class ConnectivityBarViewModel : ViewModelBase, IDisposable
{
    private readonly IConnectivityController _controller;
    // D5.4 临时机械修复（归属 arch-20/t48):状态订阅源=IConnectivityState,
    // 控制命令源=IConnectivityController（ConnectivityStateService 同时实现两者）
    private readonly IConnectivityState _state;

    public ObservableCollection<EndpointChipViewModel> Endpoints { get; } = new();

    private string _proxyModeText = "代理：未知";
    /// <summary>代理模式标签（状态栏直显）。</summary>
    public string ProxyModeText
    {
        get => _proxyModeText;
        private set => SetProperty(ref _proxyModeText, value);
    }

    private bool _hasFailures;
    /// <summary>失败引导可见性（任一 Unreachable/Blocked)。</summary>
    public bool HasFailures
    {
        get => _hasFailures;
        private set => SetProperty(ref _hasFailures, value);
    }

    private string _guidanceText = string.Empty;
    /// <summary>失败引导文案（如实列出失败端点）。</summary>
    public string GuidanceText
    {
        get => _guidanceText;
        private set => SetProperty(ref _guidanceText, value);
    }


    private Visibility _guidanceVisibility = Visibility.Collapsed;
    /// <summary>失败引导可见性（XAML 直绑，无转换器依赖）。</summary>
    public Visibility GuidanceVisibility
    {
        get => _guidanceVisibility;
        private set => SetProperty(ref _guidanceVisibility, value);
    }
    public ICommand RefreshCommand { get; }
    public ICommand ConfigureProxyCommand { get; }

    public ConnectivityBarViewModel(IConnectivityState state, IConnectivityController controller)
    {
        ArgumentNullException.ThrowIfNull(state);
        ArgumentNullException.ThrowIfNull(controller);
        _state = state;
        _controller = controller;

        RefreshCommand = new RelayCommand(async _ => await RefreshOnceAsync().ConfigureAwait(false));
        ConfigureProxyCommand = new RelayCommand(_ => OpenProxyConfigDialog());

        _state.Changed += OnStateChanged;
        _controller.ProxyModeChanged += OnProxyModeChanged;

        UpdateProxyText();
        // 初始快照（全 Unknown → 首探后由事件更新）
        OnStateChanged(this, _state.Current);
    }

    /// <summary>刷新一次（状态栏按钮 + 弹窗应用后调用）。</summary>
    public Task RefreshOnceAsync() => _controller.RefreshAsync();

    private void OnStateChanged(object? sender, IReadOnlyDictionary<EndpointKind, EndpointStatus> snapshot)
    {
        // 事件回调在线程池线程（D2.2 契约）→ marshal 到 UI 线程（无 Application=驱动进程直更）
        if (Application.Current?.Dispatcher is { } dispatcher && !dispatcher.CheckAccess())
        {
            dispatcher.BeginInvoke(() => ApplySnapshot(snapshot));
            return;
        }
        ApplySnapshot(snapshot);
    }

    private void OnProxyModeChanged(object? sender, EventArgs e)
    {
        if (Application.Current?.Dispatcher is { } dispatcher && !dispatcher.CheckAccess())
        {
            dispatcher.BeginInvoke(UpdateProxyText);
            return;
        }
        UpdateProxyText();
    }

    private void ApplySnapshot(IReadOnlyDictionary<EndpointKind, EndpointStatus> snapshot)
    {
        Endpoints.Clear();
        var failed = new List<EndpointKind>();
        foreach (var kv in snapshot)
        {
            Endpoints.Add(new EndpointChipViewModel(kv.Value));
            if (kv.Value.Reach is Reachability.Blocked or Reachability.Unreachable)
                failed.Add(kv.Key);
        }
        HasFailures = failed.Count > 0;
        GuidanceVisibility = HasFailures ? Visibility.Visible : Visibility.Collapsed;
        GuidanceText = failed.Count > 0
            ? "端点不可达（" + string.Join("、", failed) + "）→ 可能需要代理"
            : string.Empty;
    }

    private void UpdateProxyText()
    {
        ProxyModeText = _controller.CurrentProxyMode switch
        {
            ProxyMode.Direct => "代理：直连",
            ProxyMode.SystemProxy => "代理：系统代理",
            ProxyMode.Custom => $"代理：自定义（{_controller.CustomProxyUrl}）",
            _ => "代理：未知",
        };
    }

    private void OpenProxyConfigDialog()
    {
        // 失败引导（D5.9):弹代理配置窗（真实模态，#255 路径同族）
        var dialog = new ProxyConfigDialog(_controller)
        {
            Owner = Application.Current?.Windows.OfType<Window>().FirstOrDefault(w => w.IsActive)
        };
        dialog.ShowDialog();
    }

    public void Dispose()
    {
        _state.Changed -= OnStateChanged;
        _controller.ProxyModeChanged -= OnProxyModeChanged;
    }
}

/// <summary>端点芯片 VM:可达性三态文本+延迟数字+语义色键（主题令牌）。</summary>
public sealed class EndpointChipViewModel : ViewModelBase
{
    public string Name { get; }
    public string ReachText { get; }
    public string LatencyText { get; }

    /// <summary>语义色令牌键（Danger/Warning/Success 三档，主题资源取色）。</summary>
    public string StatusBrushKey { get; }

    public EndpointChipViewModel(EndpointStatus status)
    {
        Name = status.Kind switch
        {
            EndpointKind.Api => "API",
            EndpointKind.Store => "Store",
            EndpointKind.Community => "社区",
            _ => status.Kind.ToString(),
        };
        (ReachText, StatusBrushKey) = status.Reach switch
        {
            Reachability.Direct => ("直连", "swdm-Success500Brush"),
            Reachability.ViaProxy => ("经代理", "swdm-Success500Brush"),
            Reachability.Blocked => ("封禁", "swdm-Danger500Brush"),
            Reachability.Unreachable => ("不可达", "swdm-Danger500Brush"),
            _ => ("未探测", "swdm-Warning500Brush"),
        };
        LatencyText = status.LatencyMs >= 0 ? $"{status.LatencyMs}ms" : "—";
    }
}
