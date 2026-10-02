using System.Net;
using System.Net.Sockets;
using System.Text;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Web;

/// <summary>
/// D2.1 HttpClient 工厂验收：ProxyMode 三态注入 SocketsHttpHandler + 指纹头四件套 + MaxConnectionsPerServer 参数化。
/// 真实输入（非 mock 模拟）：本地 TcpListener 捕获真实请求字节 + 真实代理端口行为（Custom → 不可达端口的连接拒绝）。
/// </summary>
public sealed class HttpClientFactoryTests
{
    [Fact]
    public void Create_Client_Ok_And_Four_Fingerprint_Headers_Defaulted()
    {
        var factory = new SteamHttpClientFactory(new SteamOptions());
        var result = factory.CreateClient();

        Assert.True(result.IsOk);
        using var client = result.Value!;
        Assert.Equal(SteamHttpHeaders.UserAgent, client.DefaultRequestHeaders.UserAgent.ToString());
        Assert.Contains("application/json", client.DefaultRequestHeaders.Accept.ToString());
        // 客户端侧集合 ToString 会被框架格式化补空格（"zh-CN, zh; q=0.9"），归一化后断言语义
        Assert.Equal(SteamHttpHeaders.AcceptLanguage.Replace(" ", string.Empty), client.DefaultRequestHeaders.AcceptLanguage.ToString().Replace(" ", string.Empty));
        Assert.Equal(SteamHttpHeaders.XRequestedWith, client.DefaultRequestHeaders.GetValues(SteamHttpHeaders.Names.XRequestedWith).Single());
    }

    /// <summary>验收判据：请求头断言——真实请求到达服务器端时的四件套（尤其 Accept-Language 承重头）。</summary>
    [Fact]
    public async Task Default_Headers_Reach_Server_In_Request()
    {
        using var stub = new LoopbackHttpStub();
        var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct });
        using var client = factory.CreateClient().Value!;

        await client.GetAsync(stub.Url);

        var headers = stub.LastRequestHeaders;
        Assert.StartsWith("GET", stub.LastRequestLine);
        Assert.Contains(SteamHttpHeaders.Names.AcceptLanguage, headers.Keys);

        Assert.Contains(SteamHttpHeaders.Names.UserAgent, headers.Keys);
        Assert.Equal(SteamHttpHeaders.UserAgent, headers[SteamHttpHeaders.Names.UserAgent]);
        // 框架格式化会在 ; 后补空格（"zh-CN, zh; q=0.9"），去空格后与常量等价
        Assert.Equal(SteamHttpHeaders.AcceptLanguage.Replace(" ", string.Empty), headers[SteamHttpHeaders.Names.AcceptLanguage].Replace(" ", string.Empty));
        Assert.Contains(SteamHttpHeaders.Names.XRequestedWith, headers.Keys);
    }

    /// <summary>验收判据：切换 ProxyMode 行为可测——Direct 绕过代理，请求直达 stub 服务器。</summary>
    [Fact]
    public async Task ProxyMode_Direct_Request_Succeeds_Without_Proxy()
    {
        using var stub = new LoopbackHttpStub();
        var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct });
        using var client = factory.CreateClient().Value!;

        var response = await client.GetAsync(stub.Url);
        Assert.Equal(System.Net.HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("ok", await response.Content.ReadAsStringAsync());
    }

    /// <summary>验收判据：Custom 模式请求实际走显式代理——指向关闭端口的代理，请求必失败（非回退直连）。</summary>
    [Fact]
    public async Task ProxyMode_Custom_Request_Goes_Through_Explicit_Proxy()
    {
        var closedProxyPort = GetClosedPort();
        using var stub = new LoopbackHttpStub();
        var factory = new SteamHttpClientFactory(new SteamOptions
        {
            Proxy = ProxyMode.Custom,
            CustomProxyUrl = $"http://127.0.0.1:{closedProxyPort}",
        });
        using var client = factory.CreateClient().Value!;

        // 代理端口关闭：若请求绕过代理则直达 stub 返回 200；走代理则连接被拒（行为差异）
        await Assert.ThrowsAnyAsync<HttpRequestException>(async () => await client.GetAsync(stub.Url));
    }

    /// <summary>验收判据：Direct 与 Custom 的**行为差异可测**——同一切换（前面两例的联合断言）。</summary>
    [Fact]
    public async Task Switching_ProxyMode_Changes_Request_Behavior()
    {
        using var stub = new LoopbackHttpStub();
        // 先 Direct：成功
        using (var directClient = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }).CreateClient().Value!)
        {
            var ok = await directClient.GetAsync(stub.Url);
            Assert.True(ok.IsSuccessStatusCode);
        }
        // 切到 Custom（关闭端口代理）：必失败
        using (var proxiedClient = new SteamHttpClientFactory(
            new SteamOptions { Proxy = ProxyMode.Custom, CustomProxyUrl = $"http://127.0.0.1:{GetClosedPort()}" })
            .CreateClient().Value!)
        {
            await Assert.ThrowsAnyAsync<HttpRequestException>(async () => await proxiedClient.GetAsync(stub.Url));
        }
    }

    [Fact]
    public void ProxyMode_SystemProxy_Injects_System_Proxy()
    {
        var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.SystemProxy });
        using var handler = factory.CreateHandler().Value!;

        Assert.True(handler.UseProxy);
        Assert.NotNull(handler.Proxy);
    }

    [Fact]
    public void ProxyMode_Direct_Disables_Proxy()
    {
        var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct });
        using var handler = factory.CreateHandler().Value!;

        Assert.False(handler.UseProxy);
        Assert.Null(handler.Proxy);
    }

    [Fact]
    public void ProxyMode_Custom_Missing_Url_Returns_InvalidConfiguration()
        => AssertCustomProxyInvalid(null);

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("not-a-url")]
    [InlineData("ftp://127.0.0.1:7897")]
    public void ProxyMode_Custom_Invalid_Url_Returns_InvalidConfiguration(string? url)
        => AssertCustomProxyInvalid(url);

    /// <summary>Custom 代理 URL 非法/缺失 → InvalidConfiguration（CreateClient 与 CreateHandler 双通道）。</summary>
    private static void AssertCustomProxyInvalid(string? url)
    {
        var factory = new SteamHttpClientFactory(new SteamOptions
        {
            Proxy = ProxyMode.Custom,
            CustomProxyUrl = url,
        });

        var clientResult = factory.CreateClient();
        Assert.False(clientResult.IsOk);
        Assert.Equal(SteamError.InvalidConfiguration, clientResult.Error);

        var handlerResult = factory.CreateHandler();
        Assert.False(handlerResult.IsOk);
        Assert.Equal(SteamError.InvalidConfiguration, handlerResult.Error);
    }

    /// <summary>验收判据：参数化注入 SocketsHttpHandler（C7 标注值生效）。</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(8)]
    public void MaxConnectionsPerServer_Applied_To_Handler(int value)
    {
        var factory = new SteamHttpClientFactory(new SteamOptions
        {
            Proxy = ProxyMode.Direct,
            MaxConnectionsPerServer = value,
        });
        using var handler = factory.CreateHandler().Value!;
        Assert.Equal(value, handler.MaxConnectionsPerServer);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void MaxConnectionsPerServer_NonPositive_Returns_InvalidConfiguration(int value)
    {
        var factory = new SteamHttpClientFactory(new SteamOptions
        {
            Proxy = ProxyMode.Direct,
            MaxConnectionsPerServer = value,
        });
        Assert.False(factory.CreateHandler().IsOk);
    }

    /// <summary>取一个当前关闭的本地端口（bind 后立即释放，竞争窗口极小）。</summary>
    private static int GetClosedPort()
    {
        using var socket = new TcpListener(System.Net.IPAddress.Loopback, 0);
        socket.Start();
        var port = ((IPEndPoint)socket.LocalEndpoint).Port;
        socket.Stop();
        return port;
    }

    /// <summary>极简本地 HTTP/1.1 stub：捕获真实请求字节（真实输入纪律——非 mock 头断言）。</summary>
    private sealed class LoopbackHttpStub : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly Task _serveTask;
        private readonly CancellationTokenSource _cts = new();
        private string _lastRequestLine = string.Empty;
        private readonly Dictionary<string, string> _headers = new(StringComparer.OrdinalIgnoreCase);

        public string Url { get; }
        public string LastRequestLine => _lastRequestLine;
        public IReadOnlyDictionary<string, string> LastRequestHeaders => _headers;

        public LoopbackHttpStub()
        {
            _listener = new TcpListener(System.Net.IPAddress.Loopback, 0);
            _listener.Start();
            Url = $"http://127.0.0.1:{((IPEndPoint)_listener.LocalEndpoint).Port}/";
            _serveTask = Task.Run(ServeAsync);
        }

        private async Task ServeAsync()
        {
            while (!_cts.IsCancellationRequested)
            {
                TcpClient client;
                try { client = await _listener.AcceptTcpClientAsync(_cts.Token); }
                catch (OperationCanceledException) { break; }

                using (client)
                using (var stream = client.GetStream())
                {
                    var buffer = new byte[8192];
                    var totalRead = 0;
                    // 读到请求头结束（\r\n\r\n）或缓冲满
                    while (totalRead < buffer.Length)
                    {
                        var read = await stream.ReadAsync(buffer.AsMemory(totalRead), _cts.Token);
                        if (read == 0) break;
                        totalRead += read;
                        var text = Encoding.ASCII.GetString(buffer, 0, totalRead);
                        if (text.Contains("\r\n\r\n")) break;
                    }

                    var raw = Encoding.ASCII.GetString(buffer, 0, totalRead);
                    lock (_headers)
                    {
                        var lines = raw.Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
                        if (lines.Length > 0) _lastRequestLine = lines[0];
                        _headers.Clear();
                        foreach (var line in lines.Skip(1))
                        {
                            var sep = line.IndexOf(':');
                            if (sep > 0) _headers[line[..sep].Trim()] = line[(sep + 1)..].Trim();
                        }
                    }

                    var body = "ok"u8.ToArray();
                    var response = "HTTP/1.1 200 OK\r\n" +
                                   $"Content-Length: {body.Length}\r\n" +
                                   "Connection: close\r\n" +
                                   "Content-Type: text/plain\r\n\r\n";
                    await stream.WriteAsync(Encoding.ASCII.GetBytes(response).AsMemory(0, response.Length), _cts.Token);
                    await stream.WriteAsync(body.AsMemory(0, body.Length), _cts.Token);
                }
            }
        }

        public void Dispose()
        {
            _cts.Cancel();
            _listener.Stop();
            try { _serveTask.Wait(TimeSpan.FromSeconds(2)); } catch { }
            _cts.Dispose();
        }
    }
}
