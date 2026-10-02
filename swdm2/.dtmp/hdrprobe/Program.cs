using System; using System.IO; using System.Net; using System.Net.Sockets; using System.Text; using System.Threading; using System.Threading.Tasks;
using System.Text;
using System.Net;
using System.Net.Sockets;
using Swdm2.Core.Options;
using Swdm2.Steam.Web;

var stub = new Stub();
var factory = new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct });
using var client = factory.CreateClient().Value!;
try
{
    var resp = await client.GetAsync(stub.Url);
    Console.WriteLine("status=" + resp.StatusCode + " body=" + await resp.Content.ReadAsStringAsync());
}
catch (Exception ex) { Console.WriteLine("EX " + ex.GetType().Name + ": " + ex.Message); }
Console.WriteLine("--- captured raw request ---");
Console.WriteLine(stub.Raw);
return 0;

sealed class Stub : IDisposable
{
    private readonly TcpListener _l;
    private readonly CancellationTokenSource _cts = new();
    public string Url { get; }
    public string Raw { get; private set; } = "";
    public Stub()
    {
        _l = new TcpListener(IPAddress.Loopback, 0);
        _l.Start();
        Url = $"http://127.0.0.1:{((IPEndPoint)_l.LocalEndpoint).Port}/";
        Task.Run(async () =>
        {
            while (!_cts.IsCancellationRequested)
            {
                TcpClient c;
                try { c = await _l.AcceptTcpClientAsync(_cts.Token); } catch { break; }
                using (c)
                using (var s = c.GetStream())
                {
                    var buf = new byte[8192];
                    var n = 0;
                    while (n < buf.Length)
                    {
                        var r = await s.ReadAsync(buf.AsMemory(n), _cts.Token);
                        if (r == 0) break;
                        n += r;
                        if (Encoding.ASCII.GetString(buf, 0, n).Contains("\r\n\r\n")) break;
                    }
                    Raw = Encoding.ASCII.GetString(buf, 0, n);
                    var body = "ok"u8.ToArray();
                    var resp = "HTTP/1.1 200 OK\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n";
                    await s.WriteAsync(Encoding.ASCII.GetBytes(resp), _cts.Token);
                    await s.WriteAsync(body, _cts.Token);
                }
            }
        });
    }
    public void Dispose() { _cts.Cancel(); _l.Stop(); _cts.Dispose(); }
}
