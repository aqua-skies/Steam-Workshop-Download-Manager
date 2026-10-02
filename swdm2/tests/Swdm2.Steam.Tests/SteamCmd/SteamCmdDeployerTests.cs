using System.IO.Compression;
using System.Net;
using System.Text;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.SteamCmd;

/// <summary>
/// D3.3 部署器离线测试（桩 HTTP + 桩探针）：
/// - 幂等快路径（0 请求 0 进程）；
/// - 损坏 zip 重下一次（幂等）；
/// - 版本校验语义（exit∈{0,7} + banner 版本串）；
/// - 非 ASCII 路径门控（实测约束：Fatal exit=-2）；
/// - 熔断器接入（RateLimited 记失败）。
/// </summary>
public sealed class SteamCmdDeployerTests
{
    private const string Banner = "Steam Console Client (c) Valve Corporation - version 1788292693";

    /// <summary>桩 HTTP 工厂：按 Url 返回预设 zip 字节或状态码；计数 CreateClient 调用。</summary>
    private sealed class StubHttpFactory : IHttpClientFactory
    {
        private readonly byte[] _zip;
        public int CreateCalls { get; private set; }
        public HttpStatusCode? FailStatus { get; set; }

        public StubHttpFactory(byte[] zip) => _zip = zip;

        public Result<HttpClient, SteamError> CreateClient()
        {
            CreateCalls++;
            if (FailStatus is { } code)
                return Result<HttpClient, SteamError>.Ok(OneShotClient(code));
            return Result<HttpClient, SteamError>.Ok(OneShotClient(_zip));
        }

        private static HttpClient OneShotClient(HttpStatusCode code)
            => new HttpClient(new OneShotHandler(_ => new HttpResponseMessage(code))) { Timeout = TimeSpan.FromSeconds(5) };

        private static HttpClient OneShotClient(byte[] bytes)
            => new HttpClient(new OneShotHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(bytes) }))
            { Timeout = TimeSpan.FromSeconds(5) };
    }

    private sealed class OneShotHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _respond;
        private int _used;
        public OneShotHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) => _respond = respond;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (Interlocked.Exchange(ref _used, 1) == 1)
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
            return Task.FromResult(_respond(request));
        }
    }

    /// <summary>桩探针：预设 (exit, stdout)；计数调用。</summary>
    private sealed class StubProbe : ISteamCmdVersionProbe
    {
        public int Calls { get; private set; }
        private readonly Queue<(int exit, string stdout)> _results = new();

        public void Enqueue(int exit, string stdout) => _results.Enqueue((exit, stdout));

        public Task<VersionProbeResult> ProbeAsync(string exePath, CancellationToken ct = default)
        {
            Calls++;
            var (exit, stdout) = _results.Count > 0 ? _results.Dequeue() : (0, Banner);
            return Task.FromResult(new VersionProbeResult(exit, stdout));
        }
    }

    /// <summary>ASCII 临时根的 PathService 桩（沙箱工作区路径含中文→steamcmd 实测不可启动）。</summary>
    private sealed class StubPaths : IPathService
    {
        public string Root { get; }
        public PathMode Mode => PathMode.Portable;
        public string SteamCmdDirectory { get; }
        public StubPaths()
        {
            // GetTempPath 在 driver 下重定向到工作区 .dtmp（沙箱拒 dotnet 进程写真实 %TEMP%）；
            // 中文路径无害——ASCII 门控在探针级，桩探针不启动进程。
            Root = Path.Combine(Path.GetTempPath(), "swdm2_d33_" + Guid.NewGuid().ToString("N")[..8]);
            SteamCmdDirectory = Path.Combine(Root, "steamcmd");
        }
        public string WorkshopContent(AppId app) => Path.Combine(Root, "content", app.Value.ToString());
        public string DownloadStaging(DownloadTaskId taskId) => Path.Combine(Root, "staging", taskId.Value.ToString());
        public string LogDirectory => Path.Combine(Root, "logs");
        public string ConfigFile => Path.Combine(Root, "config.json");
        public string CredentialsFile => Path.Combine(Root, "credentials.bin");
        public void EnsureDirectories() { if (!Directory.Exists(Root)) Directory.CreateDirectory(Root); }
    }

    /// <summary>ASCII 临时基：GetTempPath 在 driver 下被重定向到含中文的 .dtmp（实测 steamcmd Fatal exit=-2），LocalApplicationData 不受 TMP 重定向影响。</summary>
    private static string AsciiTempBase()
        => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Temp");

    private static byte[] MakeZip()
    {
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            var entry = zip.CreateEntry("steamcmd.exe");
            using var es = entry.Open();
            es.Write("MZ stub"u8);
        }
        return ms.ToArray();
    }

    [Fact]
    public async Task First_Deploy_Downloads_Extracts_Probes_And_Records_Baseline()
    {
        var zip = MakeZip();
        var factory = new StubHttpFactory(zip);
        var probe = new StubProbe();
        probe.Enqueue(0, Banner);
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe, zipUrl: "https://test.invalid/steamcmd.zip");

        var result = await d.EnsureAsync();

        Assert.True(result.IsOk);
        Assert.Equal(1, factory.CreateCalls);
        Assert.Equal(1, probe.Calls);
        Assert.Equal("1788292693", result.Value!.Version);
        Assert.True(File.Exists(Path.Combine(paths.SteamCmdDirectory, "steamcmd.exe")));
        Assert.True(File.Exists(Path.Combine(paths.SteamCmdDirectory, "steamcmd.fingerprint.json")));
        Assert.True(d.Current is not null);
    }

    [Fact]
    public async Task Second_Deploy_Is_Idempotent_Zero_Request_Zero_Process()
    {
        var zip = MakeZip();
        var factory = new StubHttpFactory(zip);
        var probe = new StubProbe();
        probe.Enqueue(0, Banner);
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe);

        await d.EnsureAsync();
        var beforeCalls = factory.CreateCalls;
        var beforeProbes = probe.Calls;

        var second = await d.EnsureAsync();

        Assert.True(second.IsOk);
        Assert.Equal(beforeCalls, factory.CreateCalls);   // 0 次下载
        Assert.Equal(beforeProbes, probe.Calls);          // 0 次探针
        Assert.Equal("1788292693", second.Value!.Version);
    }

    [Fact]
    public async Task Corrupt_Local_Zip_Triggers_Redownload_Once()
    {
        var zip = MakeZip();
        var factory = new StubHttpFactory(zip);
        var probe = new StubProbe();
        probe.Enqueue(0, Banner);
        probe.Enqueue(0, Banner);
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe);

        var first = await d.EnsureAsync();
        Assert.True(first.IsOk);

        // 损坏本地 zip（基线不符）
        File.WriteAllBytes(Path.Combine(paths.SteamCmdDirectory, "steamcmd.zip"), "not-a-zip"u8.ToArray());

        var second = await d.EnsureAsync();
        Assert.True(second.IsOk);
        Assert.True(factory.CreateCalls >= 2);     // 至少重下一次
        Assert.True(second.Value!.Version == "1788292693");
    }

    [Fact]
    public async Task Download_Failure_Maps_RateLimited_And_Records_Breaker()
    {
        var factory = new StubHttpFactory(MakeZip()) { FailStatus = HttpStatusCode.TooManyRequests };
        var probe = new StubProbe();
        var time = new FakeTime();
        var breaker = new CircuitBreaker(time);
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe, breaker: breaker);

        var result = await d.EnsureAsync();

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.RateLimited, result.Error);
        Assert.Equal(1, breaker.GetFailureCount(SteamCmdDeployer.Bucket));
    }

    [Fact]
    public async Task Bad_Exit_Code_Fails_VersionCheck()
    {
        var factory = new StubHttpFactory(MakeZip());
        var probe = new StubProbe();
        probe.Enqueue(9, Banner);   // 非法退出码
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe);

        var result = await d.EnsureAsync();

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.VersionCheck, result.Error);
        Assert.False(File.Exists(Path.Combine(paths.SteamCmdDirectory, "steamcmd.fingerprint.json"))); // 失败不写基线
    }

    [Fact]
    public async Task Banner_Version_Unparseable_Fails_VersionCheck()
    {
        var factory = new StubHttpFactory(MakeZip());
        var probe = new StubProbe();
        probe.Enqueue(0, "some output without banner version line");
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe);

        var result = await d.EnsureAsync();

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.VersionCheck, result.Error);
    }

    [Fact]
    public async Task Restart_Exit_Seven_Is_Accepted_After_Self_Update()
    {
        var factory = new StubHttpFactory(MakeZip());
        var probe = new StubProbe();
        probe.Enqueue(7, Banner);   // 自更新重启语义
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe);

        var result = await d.EnsureAsync();

        Assert.True(result.IsOk);
        Assert.Equal("1788292693", result.Value!.Version);
    }

    [Fact]
    public async Task Non_Ascii_Deploy_Directory_Rejected_By_Probe_As_InvalidConfiguration()
    {
        var factory = new StubHttpFactory(MakeZip());
        // 真实探针（ASCII 门控在其内部——沙箱中文路径不启动进程）
        var paths = new NonAsciiStubPaths();
        var d = new SteamCmdDeployer(paths, factory, new SteamCmdProcessProbe());

        var result = await d.EnsureAsync();

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.InvalidConfiguration, result.Error);
    }

    [Fact]
    public async Task Circuit_Open_Short_Circuits_Without_Request()
    {
        var factory = new StubHttpFactory(MakeZip());
        var probe = new StubProbe();
        probe.Enqueue(0, Banner);
        var time = new FakeTime();
        var breaker = new CircuitBreaker(time);
        for (var i = 0; i < 5; i++) breaker.RecordFailure(SteamCmdDeployer.Bucket);
        var paths = new StubPaths();
        var d = new SteamCmdDeployer(paths, factory, probe, breaker: breaker);

        var result = await d.EnsureAsync();

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.CircuitOpen, result.Error);
        Assert.Equal(0, factory.CreateCalls);
    }

    private sealed class NonAsciiStubPaths : IPathService
    {
        // 固定/相对根会在 bin 下残留上轮基线（快路径命中→不再探针，测试假过）；每次唯一
        public string Root => Path.Combine(Path.GetTempPath(), "非ASCII根_" + _id);
        private readonly string _id = Guid.NewGuid().ToString("N")[..8];
        public PathMode Mode => PathMode.Portable;
        public string SteamCmdDirectory => Path.Combine(Root, "steamcmd");
        public string WorkshopContent(AppId app) => throw new NotImplementedException();
        public string DownloadStaging(DownloadTaskId taskId) => throw new NotImplementedException();
        public string LogDirectory => throw new NotImplementedException();
        public string ConfigFile => throw new NotImplementedException();
        public string CredentialsFile => throw new NotImplementedException();
        public void EnsureDirectories() { }
    }

    /// <summary>假钟（推进逻辑时间测熔断；ResilienceTests 同模式）。</summary>
    private sealed class FakeTime : ITimeProvider
    {
        public DateTime UtcNow { get; set; } = new DateTime(2026, 10, 2, 0, 0, 0, DateTimeKind.Utc);
        public Task DelayAsync(TimeSpan delay, CancellationToken ct = default) => Task.CompletedTask;
    }
}
