using System.Windows;
using Swdm2.App.Boot;
using Swdm2.App.Connectivity;
using Swdm2.App.Ui.Themes;
using Swdm2.App.ViewModels;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Xunit;

namespace Swdm2.UiTests.Tests.Settings;

/// <summary>
/// D5.18 设置页 VM 验收（t57):
/// - Custom 必填校验（空/格式错=拒绝保存+诚实提示）
/// - 保存=JSON 写入 IPathService.ConfigFile(reloadOnChange 热更新）
/// - SwitchProxyModeAsync 重探被调用（t48 契约；Custom 模式 URL 转发）
/// - A2 抽屉：Custom 模式展开=CustomPanelVisibility 可见
/// - 主题即时预览：Theme setter=Apply 调用（A4 无闪烁换皮）
/// </summary>
public sealed class SettingsPageViewModelTests
{
    public SettingsPageViewModelTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private static (SettingsPageViewModel vm, FakeConnectivity conn) NewVm(
        ProxyMode mode = ProxyMode.SystemProxy, string? url = null)
    {
        var tmp = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "swdm-t57-" + System.Guid.NewGuid().ToString("N")[..8]);
        System.IO.Directory.CreateDirectory(tmp);
        var paths = new PathService(PathMode.Portable, tmp);
        var conn = new FakeConnectivity();
        var theme = new ThemeService();
        var steam = new SteamOptions { Proxy = mode, CustomProxyUrl = url };
        var vm = new SettingsPageViewModel(paths, conn, theme, steam);
        return (vm, conn);
    }

    [WpfFact]
    public async Task Save_Rejects_Empty_Custom_Proxy_Url()
    {
        var (vm, conn) = NewVm(ProxyMode.Custom, url: null);
        vm.CustomProxyUrl = "   ";

        await vm.SaveAsync();

        Assert.Equal(0, conn.SwitchCalls); // 保存被拦=重探未触发
        Assert.Contains("必填", vm.ValidationMessage);
    }

    [WpfFact]
    public async Task Save_Rejects_Invalid_Url()
    {
        var (vm, conn) = NewVm(ProxyMode.Custom, url: null);
        vm.CustomProxyUrl = "not a url";

        await vm.SaveAsync();

        Assert.Equal(0, conn.SwitchCalls);
        Assert.Contains("格式无效", vm.ValidationMessage);
    }

    [WpfFact]
    public async Task Save_Writes_Json_And_Retimes_Probe()
    {
        var tmp = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "swdm-t57-" + System.Guid.NewGuid().ToString("N")[..8]);
        System.IO.Directory.CreateDirectory(tmp);
        var paths = new PathService(PathMode.Portable, tmp);
        var conn = new FakeConnectivity();
        var vm = new SettingsPageViewModel(paths, conn, new ThemeService(),
            new SteamOptions { Proxy = ProxyMode.SystemProxy });

        vm.ProxyMode = ProxyMode.Custom;
        vm.CustomProxyUrl = "http://127.0.0.1:7897";
        await vm.SaveAsync();

        Assert.Equal(1, conn.SwitchCalls);
        Assert.Equal(ProxyMode.Custom, conn.LastMode);
        Assert.Equal("http://127.0.0.1:7897", conn.LastUrl);
        Assert.True(System.IO.File.Exists(paths.ConfigFile));
        var json = System.IO.File.ReadAllText(paths.ConfigFile);
        Assert.Contains("Custom", json);
        Assert.Contains("127.0.0.1:7897", json);
        Assert.Contains("已保存", vm.ValidationMessage);
    }

    [WpfFact]
    public void A2_Drawer_Custom_Panel_Visible_Only_For_Custom_Mode()
    {
        var (vm, _) = NewVm(ProxyMode.SystemProxy);
        Assert.Equal(Visibility.Collapsed, vm.CustomPanelVisibility);

        vm.ProxyMode = ProxyMode.Custom;
        Assert.Equal(Visibility.Visible, vm.CustomPanelVisibility); // A2 展开

        vm.ProxyMode = ProxyMode.Direct;
        Assert.Equal(Visibility.Collapsed, vm.CustomPanelVisibility);
    }

    [WpfFact]
    public void ProxyMode_Index_Two_Way_Maps()
    {
        var (vm, _) = NewVm(ProxyMode.SystemProxy);
        Assert.Equal(1, vm.ProxyModeIndex);

        vm.ProxyModeIndex = 2;
        Assert.Equal(ProxyMode.Custom, vm.ProxyMode);

        vm.ProxyModeIndex = 0;
        Assert.Equal(ProxyMode.Direct, vm.ProxyMode);
    }

    [WpfFact]
    public void Theme_Setter_Applies_Immediately()
    {
        var (vm, _) = NewVm();
        // 主题即时预览=A4:setter 触发 Apply（无闪烁换 MergedDictionaries）
        vm.Theme = SwdmTheme.Light;
        Assert.Equal(SwdmTheme.Light, vm.Theme);
        Assert.True(vm.ThemeIsLight);
        Assert.False(vm.ThemeIsDark);
    }

    private sealed class FakeConnectivity : IConnectivityController
    {
        public int SwitchCalls;
        public ProxyMode LastMode;
        public string? LastUrl;

        public ProxyMode CurrentProxyMode => ProxyMode.SystemProxy;
        public string? CustomProxyUrl => null;
        public event EventHandler? ProxyModeChanged;

        public Task RefreshAsync(CancellationToken ct = default) => Task.CompletedTask;

        public Task SwitchProxyModeAsync(ProxyMode mode, string? customProxyUrl,
            CancellationToken ct = default)
        {
            SwitchCalls++;
            LastMode = mode;
            LastUrl = customProxyUrl;
            return Task.CompletedTask;
        }
    }
}