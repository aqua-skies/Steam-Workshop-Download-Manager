using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Results;
using Swdm2.Steam.Connectivity;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.Web;

/// <summary>
/// D2.3 Web API 客户端验收（真实输入纪律）：
/// 离线 = loopback stub 返回**真实 Steam API JSON 形态**（下载的研究阶段样本字节结构）；
/// 在线 = 真实 API + 真实 id 3808352517（Category=Online + SWDM2_SKIP_ONLINE=1 可跳）。
/// </summary>
[Trait("Category", "WebApi")]
public sealed class SteamWebApiClientTests
{
    private static readonly string DetailsJson = """
    {
      "response": {
        "result": 1,
        "publishedfiledetails": [
          {
            "publishedfileid": "3808352517",
            "result": 1,
            "creator": "76561198000000000",
            "creator_app_id": 322330,
            "title": "测试物品标题",
            "description": "测试描述",
            "file_size": 1048576,
            "preview_url": "https://example.com/preview.jpg",
            "time_updated": 1727740800
          }
        ]
      }
    }
    """;

    private static readonly string DetailsJsonResultZero = """
    {
      "response": {
        "result": 9,
        "publishedfiledetails": [
          { "publishedfileid": "1", "result": 9 }
        ]
      }
    }
    """;

    private static readonly string CollectionJson = """
    {
      "response": {
        "result": 1,
        "collections": [
          {
            "publishedfileid": "999",
            "result": 1,
            "children": [
              { "publishedfileid": "100", "sortorder": 2, "filetype": 0 },
              { "publishedfileid": "101", "sortorder": 1, "filetype": 0 }
            ]
          }
        ]
      }
    }
    """;

    [Fact]
    public async Task GetPublishedFileDetails_Maps_All_Fields()
    {
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, DetailsJson));
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(3808352517));
        Assert.True(result.IsOk);
        var item = result.Value!;
        Assert.Equal(new PublishedFileId(3808352517), item.Id);
        Assert.Equal(new AppId(322330), item.AppId);
        Assert.Equal("测试物品标题", item.Title);
        Assert.Equal("测试描述", item.Description);
        Assert.Equal(1048576UL, item.FileSize);
        Assert.Equal("https://example.com/preview.jpg", item.PreviewUrl);
        Assert.Equal("76561198000000000", item.Creator);
        Assert.Equal(DateTimeOffset.FromUnixTimeSeconds(1727740800).UtcDateTime, item.LastUpdatedUtc);
    }

    [Fact]
    public async Task GetPublishedFileDetailsBatch_Itemcount_Form_Encoding_Verified()
    {
        string? capturedBody = null;
        using var stub = new ScriptedStub((req, idx) =>
        {
            capturedBody = req.Body;
            return (HttpStatusCode.OK, DetailsJson2());
        });
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsBatchAsync(
            new[] { new PublishedFileId(1), new PublishedFileId(2), new PublishedFileId(3) });

        Assert.True(result.IsOk);
        Assert.Equal(2, result.Value!.Count);
        // itemcount=N 批量封包（SO #56018823)
        Assert.NotNull(capturedBody);
        Assert.Contains("itemcount=3", capturedBody);
        Assert.Contains("publishedfileids%5B0%5D=1", capturedBody); // [ ] 编码为 %5B %5D
        Assert.Contains("publishedfileids%5B2%5D=3", capturedBody);
    }

    [Fact]
    public async Task GetPublishedFileDetails_Business_Result_Zero_Maps_NotFound()
    {
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, DetailsJsonResultZero));
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.False(result.IsOk);
        Assert.Equal(SteamError.NotFound, result.Error);
    }

    [Theory]
    [InlineData(HttpStatusCode.TooManyRequests, SteamError.RateLimited)]
    [InlineData(HttpStatusCode.Forbidden, SteamError.Blocked)]
    [InlineData(HttpStatusCode.NotFound, SteamError.NotFound)]
    [InlineData(HttpStatusCode.Unauthorized, SteamError.AuthRequired)]
    [InlineData(HttpStatusCode.InternalServerError, SteamError.Network)]
    public async Task Http_Status_Maps_SteamError(HttpStatusCode status, SteamError expected)
    {
        using var stub = new ScriptedStub((req, idx) => (status, "{}"));
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.False(result.IsOk);
        Assert.Equal(expected, result.Error);
    }

    [Fact]
    public async Task Malformed_Json_Maps_Deserialization()
    {
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, "{not json"));
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.Equal(SteamError.Deserialization, result.Error);
    }

    [Fact]
    public async Task Timeout_Maps_Timeout_Error()
    {
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, DetailsJson), delay: TimeSpan.FromSeconds(3));
        var client = MakeClient(stub, timeout: TimeSpan.FromMilliseconds(500));
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.Equal(SteamError.Timeout, result.Error);
    }

    [Fact]
    public async Task Cancellation_Maps_Cancelled_Error()
    {
        using var cts = new CancellationTokenSource();
        using var stub = new ScriptedStub((req, idx) =>
        {
            cts.Cancel(); // 请求抵达即取消（真实取消路径）
            return (HttpStatusCode.OK, DetailsJson);
        }, delay: TimeSpan.FromMilliseconds(300));
        var client = MakeClient(stub, timeout: TimeSpan.FromSeconds(10));
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1), cts.Token);
        Assert.Equal(SteamError.Cancelled, result.Error);
    }

    [Fact]
    public async Task Collection_Children_Sorted_And_Mapped()
    {
        // 路径保留 override：Details 与 Collection 端点打不同 path，脚本据此返回
        using var stub = new ScriptedStub((req, idx) =>
            req.Url.Contains("GetCollectionDetails") ? (HttpStatusCode.OK, CollectionJson) : (HttpStatusCode.OK, DetailsJson));
        var client = new SteamWebApiClient(new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);
        var result = await client.GetCollectionDetailsAsync(new PublishedFileId(999));

        Assert.True(result.IsOk);
        var collection = result.Value!;
        Assert.Equal(new PublishedFileId(999), collection.Id);
        Assert.Equal("测试物品标题", collection.Title); // 标题取自自身 GetDetails
        // sortorder 修正序：101 在前
        Assert.Equal(new[] { new PublishedFileId(101L), new PublishedFileId(100L) }, collection.ChildIds.ToArray());
    }

    /// <summary>验收判据：集合递归展开——嵌套集合（filetype=0）的子项也被拉平进后代列表（BFS 序）。</summary>
    [Fact]
    public async Task Collection_Nested_Subcollections_Expanded_Recursively()
    {
        var nestedJson = """
        {
          "response": {
            "result": 1,
            "collections": [
              {
                "publishedfileid": "100",
                "result": 1,
                "children": [ { "publishedfileid": "102", "sortorder": 1, "filetype": 1 } ]
              }
            ]
          }
        }
        """;
        var rootJson = """
        {
          "response": {
            "result": 1,
            "collections": [
              {
                "publishedfileid": "999",
                "result": 1,
                "children": [
                  { "publishedfileid": "100", "sortorder": 1, "filetype": 0 },
                  { "publishedfileid": "101", "sortorder": 2, "filetype": 1 }
                ]
              }
            ]
          }
        }
        """;
        using var stub = new ScriptedStub((req, idx) =>
        {
            if (!req.Url.Contains("GetCollectionDetails")) return (HttpStatusCode.OK, DetailsJson);
            return req.Body.Contains("publishedfileids%5B0%5D=100") ? (HttpStatusCode.OK, nestedJson) : (HttpStatusCode.OK, rootJson);
        });
        var client = new SteamWebApiClient(new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

        var result = await client.GetCollectionDetailsAsync(new PublishedFileId(999));

        Assert.True(result.IsOk);
        Assert.Equal(new[] { new PublishedFileId(100L), new PublishedFileId(101L), new PublishedFileId(102L) },
                     result.Value!.ChildIds.ToArray());
    }

    /// <summary>验收判据：集合环引用不死循环（visited + 深度上限保护——1.x 学费）。</summary>
    [Fact]
    public async Task Collection_Circular_Reference_Does_Not_Hang()
    {
        // 真环：999→200→999（自指子项=根本身，必被 visited 跳过）
        var childrenOf999 = """
        {
          "response": {
            "result": 1,
            "collections": [
              {
                "publishedfileid": "999",
                "result": 1,
                "children": [ { "publishedfileid": "200", "sortorder": 1, "filetype": 0 } ]
              }
            ]
          }
        }
        """;
        var childrenOf200 = """
        {
          "response": {
            "result": 1,
            "collections": [
              {
                "publishedfileid": "200",
                "result": 1,
                "children": [ { "publishedfileid": "999", "sortorder": 1, "filetype": 0 } ]
              }
            ]
          }
        }
        """;
        using var stub = new ScriptedStub((req, idx) =>
        {
            if (!req.Url.Contains("GetCollectionDetails")) return (HttpStatusCode.OK, DetailsJson);
            return req.Body.Contains("publishedfileids%5B0%5D=200") ? (HttpStatusCode.OK, childrenOf200) : (HttpStatusCode.OK, childrenOf999);
        });
        var client = new SteamWebApiClient(new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
            endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var result = await client.GetCollectionDetailsAsync(new PublishedFileId(999), cts.Token);

        Assert.True(result.IsOk);
        // 999→200 入列表；200→999 被 visited 跳过；环终止而非死循环
        Assert.Equal(new[] { new PublishedFileId(200L) }, result.Value!.ChildIds.ToArray());
    }

    [Fact]
    public async Task Connectivity_Gate_Blocks_When_Api_Unreachable()
    {
        var gate = new InlineGate(isApiUnreachable: true);
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, DetailsJson));
        var client = new SteamWebApiClient(new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
                                            gate, endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);
        var result = await client.GetPublishedFileDetailsAsync(new PublishedFileId(1));
        Assert.Equal(SteamError.Network, result.Error);
        Assert.Equal(0, stub.RequestCount); // 门生效：未发出请求
    }

    [Fact]
    public async Task Empty_Batch_Returns_Empty_Ok_Without_Request()
    {
        using var stub = new ScriptedStub((req, idx) => (HttpStatusCode.OK, DetailsJson));
        var client = MakeClient(stub);
        var result = await client.GetPublishedFileDetailsBatchAsync(Array.Empty<PublishedFileId>());
        Assert.True(result.IsOk);
        Assert.Empty(result.Value!);
        Assert.Equal(0, stub.RequestCount);
    }

    /// <summary>可达性门适配（D2.2 IConnectivityState → IConnectivityGate)。</summary>
    private sealed class InlineGate : IConnectivityGate
    {
        public bool IsApiUnreachable { get; }
        public InlineGate(bool isApiUnreachable) => IsApiUnreachable = isApiUnreachable;
    }

    private static SteamWebApiClient MakeClient(ScriptedStub stub, TimeSpan? timeout = null)
        => new(new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
               gate: null, timeout: timeout, endpointOverride: real => stub.Url.TrimEnd('/') + new Uri(real).AbsolutePath);

    private static string DetailsJson2() => """
    {
      "response": {
        "result": 1,
        "publishedfiledetails": [
          { "publishedfileid": "1", "result": 1, "creator_app_id": 440, "title": "a" },
          { "publishedfileid": "2", "result": 1, "creator_app_id": 440, "title": "b" }
        ]
      }
    }
    """;

    /// <summary>脚本化 stub：按请求 URL 返回（状态码, JSON 体）；真实 TCP/HTTP 字节交互。</summary>
    public sealed class ScriptedStub : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly Task _serveTask;
        private readonly CancellationTokenSource _cts = new();
        private readonly Func<StubRequest, int, (HttpStatusCode, string)> _script;
        private readonly TimeSpan _delay;
        private int _requestCount;

        public string Url { get; }
        public Action<string>? OnRequest { get; set; }
        public int RequestCount => Volatile.Read(ref _requestCount);

        public ScriptedStub(Func<StubRequest, int, (HttpStatusCode, string)> script, TimeSpan? delay = null)
        {
            _script = script;
            _delay = delay ?? TimeSpan.Zero;
            _listener = new TcpListener(IPAddress.Loopback, 0);
            _listener.Start();
            Url = $"http://127.0.0.1:{((IPEndPoint)_listener.LocalEndpoint).Port}/";
            _serveTask = Task.Run(ServeAsync);
        }

        private async Task ServeAsync()
        {
            while (!_cts.IsCancellationRequested)
            {
                TcpClient tcp;
                try { tcp = await _listener.AcceptTcpClientAsync(_cts.Token); }
                catch (OperationCanceledException) { break; }

                using (tcp)
                using (var stream = tcp.GetStream())
                {
                    var buffer = new byte[16384];
                    var totalRead = 0;
                    while (totalRead < buffer.Length)
                    {
                        var read = await stream.ReadAsync(buffer.AsMemory(totalRead), _cts.Token);
                        if (read == 0) break;
                        totalRead += read;
                        var text = Encoding.ASCII.GetString(buffer, 0, totalRead);
                        if (text.Contains("\r\n\r\n") &&
                            (text.Contains("Content-Length: 0") ||
                             totalRead >= ParseContentLength(text) + text.IndexOf("\r\n\r\n") + 4))
                            break;
                    }

                    var raw = Encoding.ASCII.GetString(buffer, 0, totalRead);
                    var sep = raw.IndexOf("\r\n\r\n");
                    var head = sep >= 0 ? raw[..sep] : raw;
                    var body = sep >= 0 ? raw[(sep + 4)..] : string.Empty;
                    var reqLine = head.Split("\r\n", StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";
                    Interlocked.Increment(ref _requestCount);
                    OnRequest?.Invoke(reqLine);

                    if (_delay > TimeSpan.Zero) await Task.Delay(_delay, _cts.Token);

                    var (status, json) = _script(new StubRequest(reqLine, body), _requestCount);
                    var bodyBytes = Encoding.UTF8.GetBytes(json);
                    var code = (int)status;
                    var respText = $"HTTP/1.1 {code} {status}\r\n" +
                                   $"Content-Length: {bodyBytes.Length}\r\n" +
                                   "Content-Type: application/json\r\n" +
                                   "Connection: close\r\n\r\n";
                    await stream.WriteAsync(Encoding.ASCII.GetBytes(respText).AsMemory(0, respText.Length), _cts.Token);
                    await stream.WriteAsync(bodyBytes.AsMemory(0, bodyBytes.Length), _cts.Token);
                }
            }
        }

        private static int ParseContentLength(string head)
        {
            var lines = head.Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
            foreach (var line in lines)
            {
                if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase))
                    return int.Parse(line[15..].Trim(), CultureInfo.InvariantCulture);
            }
            return -1;
        }

        public void Dispose()
        {
            _cts.Cancel();
            _listener.Stop();
            try { _serveTask.Wait(TimeSpan.FromSeconds(2)); } catch { }
            _cts.Dispose();
        }
    }

    public sealed record StubRequest(string RequestLine, string Body)
    {
        public string Url => RequestLine.Split(' ').Skip(1).FirstOrDefault() ?? "";
        public string Body { get; } = Body;
    }
}
