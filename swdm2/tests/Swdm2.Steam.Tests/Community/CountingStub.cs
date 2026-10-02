using System.Net;
using System.Net.Sockets;
using System.Text;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.Tests.Community;

/// <summary>
/// 轻量 loopback stub（D2.5 测试专用，TcpListener 原始 HTTP——沙箱 HttpListener 不可用的弯路）：
/// 固定/序列化状态+正文、请求计数、出站 URL 重写至 stub 基址（保持 path/query）。
/// </summary>
internal sealed class CountingStub : IDisposable
{
    private readonly TcpListener _listener;
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _serveTask;
    private readonly Queue<(int Code, string Body)> _responses = new();
    private int _count;

    public int RequestCount => Volatile.Read(ref _count);
    public IHttpClientFactory Factory { get; }
    public string Url { get; }

    public CountingStub(string? fixedBody = null, HttpStatusCode? status = null)
    {
        // 有正文或显式状态→入队一个可重复响应（单响应 Peek 不消费；Enqueue 多个按序消费）
        if (fixedBody is not null || status is not null)
            _responses.Enqueue(((int)(status ?? HttpStatusCode.OK), fixedBody ?? string.Empty));

        _listener = new TcpListener(IPAddress.Loopback, 0);
        _listener.Start();
        Url = $"http://127.0.0.1:{((IPEndPoint)_listener.LocalEndpoint).Port}/";
        _serveTask = Task.Run(ServeAsync);
        Factory = new RedirectingFactory(Url);
    }

    /// <summary>加入序列响应（多次出站按序消费；用于"失败→成功"序列测试）。</summary>
    public void Enqueue(HttpStatusCode code, string body) => _responses.Enqueue(((int)code, body));

    private async Task ServeAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            TcpClient client;
            try { client = await _listener.AcceptTcpClientAsync(_cts.Token); }
            catch (OperationCanceledException) { break; }
            catch (SocketException) { break; }

            using (client)
            using (var stream = client.GetStream())
            {
                var buffer = new byte[8192];
                var totalRead = 0;
                try
                {
                    while (totalRead < buffer.Length)
                    {
                        var read = await stream.ReadAsync(buffer.AsMemory(totalRead), _cts.Token);
                        if (read == 0) break;
                        totalRead += read;
                        if (Encoding.ASCII.GetString(buffer, 0, totalRead).Contains("\r\n\r\n")) break;
                    }
                }
                catch (OperationCanceledException) { break; }

                Interlocked.Increment(ref _count);

                var (code, body) = _responses.Count switch
                {
                    0 => (200, string.Empty),
                    1 => _responses.Peek(),      // 单响应：重复服务（固定 fixture）
                    _ => _responses.Dequeue(),   // 多响应：按序消费（序列测试）
                };
                var reason = code == 200 ? "OK" : code == 429 ? "Too Many Requests" : code == 403 ? "Forbidden" : "Not Found";
                var bodyBytes = Encoding.UTF8.GetBytes(body);
                var head = $"HTTP/1.1 {code} {reason}\r\n" +
                           $"Content-Length: {bodyBytes.Length}\r\n" +
                           "Connection: close\r\n" +
                           "Content-Type: text/html; charset=utf-8\r\n\r\n";
                try
                {
                    await stream.WriteAsync(Encoding.ASCII.GetBytes(head).AsMemory(0, head.Length), _cts.Token);
                    if (bodyBytes.Length > 0)
                        await stream.WriteAsync(bodyBytes.AsMemory(0, bodyBytes.Length), _cts.Token);
                }
                catch (OperationCanceledException) { break; }
                catch (SocketException) { }
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

/// <summary>创建直连客户端包装：出站请求 URL 重写至 loopback（path/query 保留；指纹头同 D2.1 四件套）。</summary>
internal sealed class RedirectingFactory : IHttpClientFactory
{
    private readonly string _base;

    public RedirectingFactory(string loopbackBase) => _base = loopbackBase;

    public Result<HttpClient, SteamError> CreateClient()
    {
        // 每请求新 handler+内部直连 client（上层 using 会 dispose 客户端——不可跨请求共享）
        var client = new HttpClient(new RedirectingHandler(_base))
        {
            Timeout = SteamHttpClientFactory.DefaultTimeout,
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd(SteamHttpHeaders.UserAgent);
        client.DefaultRequestHeaders.Accept.ParseAdd(SteamHttpHeaders.Accept);
        client.DefaultRequestHeaders.AcceptLanguage.ParseAdd(SteamHttpHeaders.AcceptLanguage);
        client.DefaultRequestHeaders.Add(SteamHttpHeaders.Names.XRequestedWith, SteamHttpHeaders.XRequestedWith);
        return Result<HttpClient, SteamError>.Ok(client);
    }
}

/// <summary>URL 重写 handler（请求消息**必须克隆**——原消息已被外层 HttpClient 标记 sent）。</summary>
internal sealed class RedirectingHandler : HttpMessageHandler
{
    private readonly string _base;
    private readonly HttpClient _direct = new(new HttpClientHandler { UseProxy = false });

    public RedirectingHandler(string loopbackBase) => _base = loopbackBase;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var uri = request.RequestUri!;
        var redirected = new Uri(_base.TrimEnd('/') + uri.PathAndQuery);

        var clone = new HttpRequestMessage(request.Method, redirected);
        if (request.Content is not null)
        {
            var bytes = await request.Content.ReadAsByteArrayAsync(cancellationToken);
            clone.Content = new ByteArrayContent(bytes);
            foreach (var h in request.Content.Headers)
                clone.Content.Headers.TryAddWithoutValidation(h.Key, h.Value);
        }
        foreach (var h in request.Headers)
            clone.Headers.TryAddWithoutValidation(h.Key, h.Value);

        return await _direct.SendAsync(clone, cancellationToken);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) _direct.Dispose();
        base.Dispose(disposing);
    }
}
