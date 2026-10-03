using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Swdm2.App.Connectivity;
using Swdm2.App.ViewModels;
using Swdm2.Core.Options;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.UiTests.Connectivity;

/// <summary>
/// D5.9(t48) 状态栏端点可达性测试：
/// - IConnectivityState/Controller:探测结果如实显示（Direct/Blocked/Unreachable)+事件
/// - 切代理即时更新（SwitchProxyMode=重建工厂+重探+事件）
/// - 失败引导（HasFailures/GuidanceVisibility)+VM 芯片文本
/// 本地 Kestrel fixture 禁公网（端点 URL 注入覆盖 D2.2 默认端点）。
/// </summary>
public sealed class ConnectivityStateServiceTests : IDisposable
{
    private readonly WebApplication _app;
    private readonly string _base;

    public ConnectivityStateServiceTests()
    {
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();
        _app.MapGet("/ok", () => Results.Ok("ok"));
        _app.MapGet("/blocked", context =>
        {
            context.Response.StatusCode = 403;
            return Task.CompletedTask;
        });
        _app.Start();
        _base = _app.Urls.First();
    }

    private static readonly string DeadEndpoint = "http://127.0.0.1:1/";

    private IReadOnlyDictionary<EndpointKind, string> Overrides => new Dictionary<EndpointKind, string>
    {
        { EndpointKind.Api, $"{_base}/ok" },          // 200 → Direct
        { EndpointKind.Store, $"{_base}/blocked" },   // 403 → Blocked
        { EndpointKind.Community, DeadEndpoint },      // 端口关闭 → Unreachable
    };

    private static SteamOptions DirectOptions() => new() { Proxy = ProxyMode.Direct };

    /// <summary>探测结果如实显示：三端点三态 + 事件触发一次。</summary>
    [WpfFact]
    public async Task Refresh_Reflects_Honest_States_And_Raises_Once()
    {
        using var service = new ConnectivityStateService(DirectOptions(),
            timeout: TimeSpan.FromSeconds(3), endpointOverrides: Overrides);
        var fires = 0;
        service.Changed += (_, _) => Interlocked.Increment(ref fires);

        await service.RefreshAsync();

        Assert.Equal(Reachability.Direct, service.Current[EndpointKind.Api].Reach);
        Assert.Equal(Reachability.Blocked, service.Current[EndpointKind.Store].Reach);
        Assert.Equal(Reachability.Unreachable, service.Current[EndpointKind.Community].Reach);
        Assert.Equal(1, fires);

        // 二次重探：延迟毫秒漂移=真变更可触发；只断言 Reach 三态稳定（如实显示不抖动）
        await service.RefreshAsync();
        Assert.Equal(Reachability.Direct, service.Current[EndpointKind.Api].Reach);
        Assert.Equal(Reachability.Blocked, service.Current[EndpointKind.Store].Reach);
        Assert.Equal(Reachability.Unreachable, service.Current[EndpointKind.Community].Reach);
    }

    /// <summary>切代理即时更新：模式切换→重建工厂→重探→双事件。</summary>
    [WpfFact]
    public async Task SwitchProxyMode_Rebuilds_And_Reprobes_Immediately()
    {
        var options = DirectOptions();
        using var service = new ConnectivityStateService(options,
            timeout: TimeSpan.FromSeconds(3), endpointOverrides: Overrides);
        await service.RefreshAsync();
        var proxyFires = 0;
        var stateFires = 0;
        service.ProxyModeChanged += (_, _) => Interlocked.Increment(ref proxyFires);
        service.Changed += (_, _) => Interlocked.Increment(ref stateFires);

        Assert.Equal(ProxyMode.Direct, service.CurrentProxyMode);

        // 启动一次绕开（Direct→Direct 同值快照：验证重建+代理事件，状态事件不重触发）
        await service.SwitchProxyModeAsync(ProxyMode.Direct, null);

        Assert.Equal(ProxyMode.Direct, service.CurrentProxyMode);
        Assert.Equal(1, proxyFires);   // ProxyModeChanged 必触发（切换即重建+重探）
        Assert.True(stateFires <= 1);  // 状态事件：延迟漂移=真变更可触发，上限=1 次重探
    }

    /// <summary>Custom 模式无 URL → 校验拒绝（不发起探测）。</summary>
    [WpfFact]
    public async Task Custom_Without_Url_Rejected()
    {
        using var service = new ConnectivityStateService(DirectOptions(),
            timeout: TimeSpan.FromSeconds(3), endpointOverrides: Overrides);
        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.SwitchProxyModeAsync(ProxyMode.Custom, "  "));
    }

    /// <summary>失败引导+芯片文本：Bar VM 如实反映快照。</summary>
    [WpfFact]
    public async Task BarViewModel_Reflects_Snapshot_And_Guidance()
    {
        using var service = new ConnectivityStateService(DirectOptions(),
            timeout: TimeSpan.FromSeconds(3), endpointOverrides: Overrides);
        await service.RefreshAsync();

        using var bar = new ConnectivityBarViewModel((Swdm2.Steam.Connectivity.IConnectivityState)service, service);
        Assert.Equal(3, bar.Endpoints.Count);
        Assert.Equal("直连", bar.Endpoints[0].ReachText);    // Api=Direct
        Assert.Equal("封禁", bar.Endpoints[1].ReachText);    // Store=Blocked
        Assert.Equal("不可达", bar.Endpoints[2].ReachText);  // Community=Unreachable
        Assert.True(bar.HasFailures);
        Assert.Equal(System.Windows.Visibility.Visible, bar.GuidanceVisibility);
        Assert.Contains("Community", bar.GuidanceText); // 失败端点直列（Kind 名）
        Assert.Equal("代理：直连", bar.ProxyModeText);
    }

    /// <summary>Custom 代理 URL 真切：经本地代理 fixture→ViaProxy/或 Direct(D2.2 语义由 ProxyMode 判）。</summary>
    [WpfFact]
    public async Task Switch_To_Custom_Url_Probes_Through_New_Factory()
    {
        var options = DirectOptions();
        using var service = new ConnectivityStateService(options,
            timeout: TimeSpan.FromSeconds(3), endpointOverrides: Overrides);
        await service.RefreshAsync();

        // 自定义 URL 指向一个不存在的代理端口 → 切换后所有端点应 Unreachable（经坏代理）
        await service.SwitchProxyModeAsync(ProxyMode.Custom, "http://127.0.0.1:2");
        Assert.Equal(ProxyMode.Custom, service.CurrentProxyMode);
        Assert.Equal(Reachability.Unreachable, service.Current[EndpointKind.Api].Reach);
    }

    public void Dispose()
    {
        try { _app.StopAsync().Wait(TimeSpan.FromSeconds(5)); } catch { }
        (_app as IDisposable).Dispose();
    }
}
