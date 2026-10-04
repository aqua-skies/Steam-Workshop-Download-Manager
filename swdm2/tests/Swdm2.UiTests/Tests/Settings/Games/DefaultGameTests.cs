using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Swdm2.App.Connectivity;
using Swdm2.App.Games;
using Swdm2.App.Ui.Themes;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Xunit;

namespace Swdm2.UiTests.Tests.Settings.Games;

/// <summary>
/// D5.20c/t64 默认游戏（设置页绑定游戏实物）回归：
/// 用户原话"设置里绑定游戏是一句空话"→设置页搜索选择保存=主页即时显示。
/// 沙箱真点不路由（同族）=逻辑层钉 + 桌面复跑条款。
/// </summary>
public sealed class DefaultGameTests
{
    private static PathService TmpPaths()
    {
        var tmp = Path.Combine(Path.GetTempPath(), "swdm_dg_" + Guid.NewGuid());
        return new PathService(PathMode.Portable, tmp);
    }

    /// <summary>空配置=未绑定（诚实空态，不造 sample)。</summary>
    [WpfFact]
    public void Load_NoConfig_Returns_Null()
    {
        var svc = new DefaultGameService();
        svc.Load(TmpPaths());
        Assert.Null(svc.Current);
    }

    /// <summary>Bind 写入 ConfigFile,Load 回读=AppId/Title 一致（持久化闭环）。</summary>
    [WpfFact]
    public void Bind_Persists_And_Reloads()
    {
        var paths = TmpPaths();
        var svc = new DefaultGameService();
        svc.Bind(paths, new BoundGame(322330, "Don't Starve Together", null));
        Assert.True(svc.Current!.AppId == 322330);

        var svc2 = new DefaultGameService();
        svc2.Load(paths);
        Assert.True(svc2.Current!.AppId == 322330);
        Assert.True(svc2.Current!.Title == "Don't Starve Together");
    }

    /// <summary>SettingsPageVM 选中候选=绑定+显示文本更新。</summary>
    [WpfFact]
    public void Settings_SelectGame_Binds_And_Displays()
    {
        var paths = TmpPaths();
        var svc = new DefaultGameService(); svc.Load(paths);
        var vm = new SettingsPageViewModel(paths, new FakeConnectivity(), new ThemeService(),
            storeSearch: null, defaultGame: svc);

        Assert.Equal("未绑定（搜索并选择游戏后保存）", vm.BoundGameDisplay);

        var game = new GameInfo(new AppId(322330), "Don't Starve Together");
        vm.SelectGameCommand.Execute(game);

        Assert.NotNull(vm.BoundGame);
        Assert.True(vm.BoundGame!.AppId == 322330);
        Assert.True(vm.BoundGameDisplay == "Don't Starve Together (AppId 322330)");
    }

    /// <summary>主页 VM 订阅默认游戏=绑定后卡片+Tiles+EmptyHint 立即响应。</summary>
    [WpfFact]
    public void SphereHome_Reflects_DefaultGame()
    {
        var paths = TmpPaths();
        var svc = new DefaultGameService(); svc.Load(paths);

        var home = new SphereHomePageViewModel(defaultGame: svc);
        Assert.Equal("未绑定默认游戏", home.DefaultGameTitle);
        Assert.Empty(home.Tiles);

        svc.Bind(paths, new BoundGame(322330, "Don't Starve Together", null));

        Assert.Equal("Don't Starve Together", home.DefaultGameTitle);
        Assert.True(home.Tiles.Count == 1);
        Assert.True(home.Tiles[0].AppId == 322330);
        Assert.Equal(System.Windows.Visibility.Collapsed, home.EmptyHintVisibility);
    }

    private sealed class FakeConnectivity : IConnectivityController
    {
        public ProxyMode CurrentProxyMode => ProxyMode.SystemProxy;
        public string? CustomProxyUrl => null;
#pragma warning disable CS0067
        public event EventHandler? ProxyModeChanged;
#pragma warning restore CS0067
        public Task RefreshAsync(CancellationToken ct = default) => Task.CompletedTask;
        public Task SwitchProxyModeAsync(ProxyMode mode, string? customProxyUrl,
            CancellationToken ct = default) => Task.CompletedTask;
    }
}
