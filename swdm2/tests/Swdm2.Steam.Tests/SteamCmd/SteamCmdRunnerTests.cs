using System.Diagnostics;
using System.Text;
using Swdm2.Core.Domain;
using Swdm2.Core.Logging;
using Swdm2.Core.Results;
using Swdm2.Steam.SteamCmd;
using Xunit;

namespace Swdm2.Steam.Tests.SteamCmd;

/// <summary>
/// D3.4 runner 离线测试：cmd /c 批处理伪造 steamcmd 进程（真进程语义：kill 树、
/// 批次行序、退出码、stdout 逐行），1.x 线上回归的离线等价物。
/// 环境教训（沙箱实证）：批处理须无 BOM（cmd 按 GBK 读会破坏首行）+ 纯 ASCII 行
/// （中文路径经 GBK 误解）+ 产物相对路径（CWD=InstallDir）+ 启动参数裸引号转义
/// （ArgumentList 不为 cmd /c 正确处理空格）。
/// 覆盖：成功三元判定（正则+Sweep 非空+退出码∈{0,7}）、M2 偏差&lt;10%、
/// 停滞看门狗、取消无僵尸、失败清空目录、输出脱敏。
/// </summary>
public sealed class SteamCmdRunnerTests
{
    private const ulong Item = 17906;
    private const int App = 4000;
    private const string ContentRel = @"steamapps\workshop\content\4000\17906";

    private static string NewInstallDir()
        => Path.Combine(Path.GetTempPath(), "swdm2_d34_" + Guid.NewGuid().ToString("N")[..8]);

    /// <summary>伪造进程启动器：cmd /c 批处理（批处理行为烤进脚本）。</summary>
    private static Process BatchStart(string batchPath, ProcessStartInfo psi)
    {
        var raw = new ProcessStartInfo("cmd.exe", "/c \"" + batchPath + "\"")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            CreateNoWindow = true,
            WorkingDirectory = psi.WorkingDirectory,
        };
        var p = Process.Start(raw) ?? throw new InvalidOperationException("fake 进程启动失败");
        return p;
    }

    private sealed class FakeScript
    {
        private readonly List<string> _lines = new();
        private int _bytes;
        private bool _writePartial, _hang;
        private int _exitCode = 0;

        public FakeScript LoginOk() { _lines.Add("Connecting anonymously to Steam Public...OK"); return this; }
        public FakeScript Downloading() { _lines.Add("Downloading item 17906"); return this; }
        public FakeScript WriteProduct(int bytes) { _bytes = bytes; return this; }
        public FakeScript WritePartialOnFail() { _writePartial = true; return this; }
        public FakeScript SuccessLine() { _lines.Add($"Success. Downloaded item 17906 to \"{ContentRel}\\mod.bin\" (123456 bytes)"); return this; }
        public FakeScript FailLine(string l) { _lines.Add(l); return this; }
        public FakeScript Hang() { _hang = true; return this; }
        public FakeScript Exit(int code) { _exitCode = code; return this; }

        /// <summary>写批处理（ASCII 全行、无 BOM、相对路径产物），返回路径。</summary>
        public string WriteTo(string fakeDir, string contentDir)
        {
            Directory.CreateDirectory(fakeDir);
            Directory.CreateDirectory(contentDir);
            var batch = Path.Combine(fakeDir, "fake.cmd");
            var sb = new StringBuilder();
            sb.AppendLine("@echo off");
            foreach (var l in _lines) sb.AppendLine("echo " + l);
            if (_bytes > 0)
                sb.AppendLine($"powershell -NoProfile -Command \"[IO.File]::WriteAllBytes('{ContentRel}\\mod.bin', (New-Object byte[] {_bytes}))\"");
            if (_writePartial)
                sb.AppendLine($"powershell -NoProfile -Command \"[IO.File]::WriteAllBytes('{ContentRel}\\partial.bin', (New-Object byte[] 1000))\"");
            if (_hang)
                sb.AppendLine("ping -n 60 127.0.0.1 > nul");
            sb.AppendLine($"exit /b {_exitCode}");
            File.WriteAllText(batch, sb.ToString(), new UTF8Encoding(false));
            return batch;
        }
    }

    private static SteamCmdRunner NewRunner(FakeScript script, string install,
        TimeSpan? stallTimeout = null, IRedactionPolicy? redaction = null)
    {
        var batch = script.WriteTo(Path.Combine(install, "fake"), Path.Combine(install, ContentRel));
        var batchPath = batch;
        return new SteamCmdRunner(redaction, stallTimeout, null,
            psi => BatchStart(batchPath, psi));
    }

    private static SteamCmdRunRequest Request(string install, string? user = null)
        => new(new PublishedFileId(Item), new AppId(App), "cmd.exe", install, Username: user);

    private sealed class CollectObserver : ISteamCmdLineObserver
    {
        public List<string> Lines { get; } = new();
        public void OnLine(string redactedLine) => Lines.Add(redactedLine);
        public void OnThrottleSignal(string kind, string line) { }
    }

    [Fact]
    public async Task Success_Ternary_Sweeps_NonEmpty_And_M2_Deviation_Below_10Pct()
    {
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().LoginOk().Downloading().WriteProduct(123456).SuccessLine(), install);
        var observer = new CollectObserver();

        var result = await runner.DownloadAsync(Request(install), observer: observer);

        Assert.True(result.IsOk);
        Assert.Equal(SteamCmdOutcome.Success, result.Value!.Outcome);
        Assert.Equal(123456, result.Value.BytesDone);
        Assert.Equal(123456, result.Value.EstimatedBytes);            // Sweep == 正则字节 → 偏差 0%
        Assert.True(Math.Abs(result.Value.EstimatedBytes - result.Value.BytesDone) / (double)result.Value.BytesDone < 0.10, "M2 偏差<10%");
        Assert.True(File.Exists(Path.Combine(install, ContentRel, "mod.bin")));
    }

    [Fact]
    public async Task Fake_Success_With_Empty_Product_Rejected()
    {
        // 正则 Success 但产物目录空=假成功（1.x 学费：0 字节假成功被拒）
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().LoginOk().Downloading().SuccessLine(), install);

        var result = await runner.DownloadAsync(Request(install));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.VersionCheck, result.Error);
    }

    [Fact]
    public async Task Fail_Line_Clears_Product_Directory()
    {
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().LoginOk().Downloading().WritePartialOnFail()
            .FailLine("ERROR! Download failed").Exit(1), install);

        var result = await runner.DownloadAsync(Request(install));

        Assert.True(result.IsOk);              // 失败 outcome 也走 Result.Ok（不抛异常语义）
        Assert.Equal(SteamCmdOutcome.Failed, result.Value!.Outcome);
        Assert.False(Directory.Exists(Path.Combine(install, ContentRel)), "失败清空目录：半成品不残留");
    }

    [Fact]
    public async Task Login_Failure_Maps_Outcome()
    {
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().FailLine("Login Failure: Invalid Password").Exit(3), install);

        var result = await runner.DownloadAsync(Request(install));

        Assert.True(result.IsOk);
        Assert.Equal(SteamCmdOutcome.LoginFailure, result.Value!.Outcome);
    }

    [Fact]
    public async Task No_Download_Line_Maps_ItemNotFound()
    {
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().LoginOk(), install);

        var result = await runner.DownloadAsync(Request(install));

        Assert.True(result.IsOk);
        Assert.Equal(SteamCmdOutcome.ItemNotFound, result.Value!.Outcome);
    }

    [Fact]
    public async Task Stall_Watchdog_Kills_Silent_Process()
    {
        // 无输出+无磁盘增长超过 stall 超时→杀进程+StallKilled+清空
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().Hang(), install, stallTimeout: TimeSpan.FromSeconds(1.5));

        var sw = Stopwatch.StartNew();
        var result = await runner.DownloadAsync(Request(install));
        sw.Stop();

        Assert.True(result.IsOk);
        Assert.Equal(SteamCmdOutcome.StallKilled, result.Value!.Outcome);
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(10), "看门狗及时收割，不干等 ping 完成");
        Assert.False(Directory.Exists(Path.Combine(install, ContentRel)), "停滞清空目录");
    }

    [Fact]
    public async Task Cancel_Kills_Entire_Tree_No_Orphan()
    {
        var install = NewInstallDir();
        var runner = NewRunner(new FakeScript().Downloading().Hang(), install);

        using var cts = new CancellationTokenSource();
        var task = runner.DownloadAsync(Request(install), ct: cts.Token);
        await Task.Delay(800);                       // 等 Downloading 行+ping 起来
        cts.Cancel();                                // 取消=杀全树

        var result = await task;

        Assert.True(result.IsOk);
        Assert.Equal(SteamCmdOutcome.Cancelled, result.Value!.Outcome);
        await Task.Delay(500);                       // OS 收尸窗口
        Assert.Empty(Process.GetProcessesByName("ping"));
        Assert.False(Directory.Exists(Path.Combine(install, ContentRel)), "取消清空目录");
    }

    [Fact]
    public async Task Output_Redaction_Before_Observer()
    {
        var install = NewInstallDir();
        var secret = "SteamPublic";
        var policy = new ReplacePolicy(secret, "***");
        var runner = NewRunner(new FakeScript().LoginOk().Downloading().WriteProduct(10).SuccessLine(),
            install, redaction: policy);
        var observer = new CollectObserver();

        await runner.DownloadAsync(Request(install), observer: observer);

        Assert.NotEmpty(observer.Lines);
        Assert.DoesNotContain(observer.Lines, l => l.Contains(secret));   // 敏感串不出现在回调
    }

    [Fact]
    public void Build_Commands_Batch_Anonymous()
    {
        var req = new SteamCmdRunRequest(new PublishedFileId(Item), new AppId(App), "steamcmd.exe", "C:\\install");
        var cmds = SteamCmdRunner.BuildCommands(req);
        Assert.Equal(new[] { "+force_install_dir", "C:\\install", "+login", "anonymous",
            "+workshop_download_item", "4000", "17906", "+quit" }, cmds);
        Assert.True(req.IsAnonymous);
    }

    [Fact]
    public void Build_Commands_Batch_With_User_Validate()
    {
        var req = new SteamCmdRunRequest(new PublishedFileId(Item), new AppId(App), "steamcmd.exe", "C:\\install",
            Validate: true, Username: "user1", Password: "pw2", GuardCode: "g3");
        var cmds = SteamCmdRunner.BuildCommands(req);
        Assert.Equal(new[] { "+force_install_dir", "C:\\install", "+login", "user1", "pw2", "g3",
            "+workshop_download_item", "4000", "17906", "+validate", "+quit" }, cmds);
        Assert.False(req.IsAnonymous);
    }

    private sealed class ReplacePolicy : IRedactionPolicy
    {
        private readonly string _secret, _replacement;
        public ReplacePolicy(string secret, string replacement) { _secret = secret; _replacement = replacement; }
        public string Redact(string? text) => (text ?? string.Empty).Replace(_secret, _replacement);
    }
}
