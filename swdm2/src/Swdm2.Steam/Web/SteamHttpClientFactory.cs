using System.Net;
using System.Net.Http;
using Swdm2.Core.Options;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Web;

/// <summary>
/// HttpClient 工厂默认实现（D2.1）：
/// - ProxyMode 三态注入 <see cref="SocketsHttpHandler"/>：Direct=不用代理（UseProxy=false）；
///   SystemProxy=系统代理（WebRequest.GetSystemWebProxy）；Custom=显式 WebProxy(CustomProxyUrl)；
/// - <see cref="SteamOptions.MaxConnectionsPerServer"/> 参数化（C7 ⚠️[参数待重标定]，D2.6 标定）；
/// - 指纹头四件套默认（<see cref="SteamHttpHeaders"/>：1.x 429 学费——Accept-Language 为承重头）；
/// - 配置错误返回 <see cref="SteamError.InvalidConfiguration"/> 的 Result（不抛异常）。
/// Options 为**构造快照语义**：热更新由 App 侧重建工厂
/// （IHttpClientFactory 注册时取 IOptionsMonitor.CurrentValue 组合——D2.x App 装配点）。
/// </summary>
public sealed class SteamHttpClientFactory : IHttpClientFactory
{
    private readonly SteamOptions _options;

    /// <summary>超时默认 30s（⚠️[参数待重标定]：D3+ 下载域单独配置，元数据沿用此值）。</summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(30);

    public SteamHttpClientFactory(SteamOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        _options = options;
    }

    public Result<HttpClient, SteamError> CreateClient()
    {
        var handlerResult = CreateHandler();
        if (!handlerResult.IsOk)
            return Result<HttpClient, SteamError>.Fail(handlerResult.Error ?? SteamError.None);

        var client = new HttpClient(handlerResult.Value!)
        {
            Timeout = DefaultTimeout,
        };
        ApplyDefaultHeaders(client);
        return Result<HttpClient, SteamError>.Ok(client);
    }

    /// <summary>创建底层处理器（测试/自定义装配 seam；生产路径经 CreateClient）。</summary>
    public Result<SocketsHttpHandler, SteamError> CreateHandler()
    {
        var proxy = ResolveProxy(out var proxyError);
        if (proxyError.HasValue)
            return Result<SocketsHttpHandler, SteamError>.Fail(proxyError.Value);

        var maxConns = _options.MaxConnectionsPerServer;
        if (maxConns < 1) // 运行期兜底（绑定层 DataAnnotations Range 之外的防御）
            return Result<SocketsHttpHandler, SteamError>.Fail(SteamError.InvalidConfiguration);

        var handler = new SocketsHttpHandler
        {
            UseProxy = proxy is not null,  // null=Direct 模式显式禁用代理；否则注入解析到的代理
            Proxy = proxy,
            MaxConnectionsPerServer = maxConns,
            AutomaticDecompression = DecompressionMethods.All,
        };
        return Result<SocketsHttpHandler, SteamError>.Ok(handler);
    }

    /// <summary>三态代理解析；Custom 模式校验 URL（缺失/非法 → InvalidConfiguration）。</summary>
    private IWebProxy? ResolveProxy(out SteamError? error)
    {
        error = null;
        return _options.Proxy switch
        {
            ProxyMode.Direct => null,
            ProxyMode.SystemProxy => WebRequest.GetSystemWebProxy(),
            ProxyMode.Custom => ResolveCustomProxy(out error),
            _ => null,
        };
    }

    /// <summary>Custom 模式：校验 CustomProxyUrl 并构造显式 WebProxy（默认凭证由 NetworkCredential 按需配）。</summary>
    private IWebProxy? ResolveCustomProxy(out SteamError? error)
    {
        error = null;
        var url = _options.CustomProxyUrl;
        if (string.IsNullOrWhiteSpace(url)
            || !Uri.TryCreate(url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            error = SteamError.InvalidConfiguration;
            return null;
        }
        return new WebProxy(uri);
    }

    /// <summary>指纹头四件套（1.x 429 学费：Accept-Language 承重，X-Requested-With 冗余防御）。</summary>
    private static void ApplyDefaultHeaders(HttpClient client)
    {
        client.DefaultRequestHeaders.UserAgent.ParseAdd(SteamHttpHeaders.UserAgent);
        client.DefaultRequestHeaders.Accept.ParseAdd(SteamHttpHeaders.Accept);
        client.DefaultRequestHeaders.AcceptLanguage.ParseAdd(SteamHttpHeaders.AcceptLanguage);
        client.DefaultRequestHeaders.Add(SteamHttpHeaders.Names.XRequestedWith, SteamHttpHeaders.XRequestedWith);
    }
}
