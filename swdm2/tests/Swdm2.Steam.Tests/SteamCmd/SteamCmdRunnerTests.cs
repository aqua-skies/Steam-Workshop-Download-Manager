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
    private const ulong Item2 = 28906;
    private const int App = 4000;
    private const string ContentRel = @"steamapps\workshop\content\4000\17906";

    private static string ContentRelOf(ulong item) => $@"steamapps\workshop\content\4000\{item}";

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
        private readonly ulong _item;
        private int _bytes;
        private bool _writePartial, _hang;
        private int _hangSecs, _exitCode = 0;

        public FakeScript(ulong item = Item) => _item = item;

        public string ContentRel => ContentRelOf(_item);

        public FakeScript LoginOk() { _lines.Add("Connecting anonymously to Steam Public...OK"); return this; }
        public FakeScript Downloading() { _lines.Add($"Downloading item {_item}"); return this; }
        public FakeScript WriteProduct(int bytes) { _bytes = bytes; return this; }
        public FakeScript WritePartialOnFail() { _writePartial = true; return this; }
        public FakeScript SuccessLine() { _lines.Add($"Success. Downloaded item {_item} to \"{ContentRel}\\mod.bin\" ({_successBytes} bytes)"); return this; }
        /// <summary>自定义报数字节（区分两任务产物，验证句柄不互覆；须先于 SuccessLine 调用）。</summary>
        public FakeScript WithSuccessBytes(int b) { _successBytes = b; return this; }
        private int _successBytes = 123456;
        public FakeScript FailLine(string l) { _lines.Add(l); return this; }
        public FakeScript Hang() { _hang = true; return this; }
        public FakeScript HangSecs(int n) { _hangSecs = n; return this; }
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
            if (_hangSecs > 0)
                sb.AppendLine($"ping -n {_hangSecs} 127.0.0.1 > nul");
            else if (_hang)
                sb.AppendLine("ping -n 60 127.0.0.1 > nul");
            sb.AppendLine($"exit /b {_exitCode}");
            File.WriteAllText(batch, sb.ToString(), new UTF8Encoding(false));
            return batch;
        }

        public int ReportBytes => _successBytes;
    }

    private static SteamCmdRunner NewRunner(FakeScript script, string install,
        TimeSpan? stallTimeout = null, IRedactionPolicy? redaction = null, TimeSpan? waitTimeout = null)
    {
        var batchPath = script.WriteTo(Path.Combine(install, "fake"), Path.Combine(install, script.ContentRel));
        return new SteamCmdRunner(redaction, stallTimeout, null, waitTimeout,
            psi => BatchStart(batchPath, psi));
    }

    /// <summary>D3.6 并发场景：按请求 item 派发不同脚本（两个任务→两个 production 目录，共享一个 runner=共享进程槽）。</summary>
    private static SteamCmdRunner NewRunnerMulti(string installRoot, IDictionary<ulong, FakeScript> scripts,
        TimeSpan? stallTimeout = null, TimeSpan? waitTimeout = null)
    {
        Process Seam(ProcessStartInfo psi)
        {
            var key = scripts.Keys.Single(k => psi.ArgumentList.Contains(k.ToString()));
            var s = scripts[key];
            var batch = s.WriteTo(Path.Combine(installRoot, "fake_" + key), Path.Combine(installRoot, s.ContentRel));
            return BatchStart(batch, psi);
        }
        return new SteamCmdRunner(null, stallTimeout, null, waitTimeout, (Func<ProcessStartInfo, Process>)Seam);
    }

    private static SteamCmdRunRequest RequestFor(string install, ulong item)
        => new(new PublishedFileId(item), new AppId(App), "cmd.exe", install);

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

    // ================================================== D3.6 串行化与句柄纪律 ==================================

    /// <summary>验收①：并发两任务→第二等待（串行）；两任务各自正确产物=句柄不互覆、无 NRE。</summary>
    [Fact]
    public async Task D36_Concurrent_Second_Task_Waits_Handle_Not_Overwritten()
    {
        var root = NewInstallDir();
        var slow = new FakeScript(Item).LoginOk().Downloading().WriteProduct(123456)
            .SuccessLine().HangSecs(4);          // 占槽 ~4s
        var fast = new FakeScript(Item2).LoginOk().Downloading().WriteProduct(67890)
            .WithSuccessBytes(67890).SuccessLine();
        var runner = NewRunnerMulti(root, new Dictionary<ulong, FakeScript> { [Item] = slow, [Item2] = fast },
            stallTimeout: TimeSpan.FromSeconds(60), waitTimeout: TimeSpan.FromSeconds(30));

        var t1 = runner.DownloadAsync(RequestFor(root, Item));
        await Task.Delay(300);                    // 让任务1拿到槽
        var sw = Stopwatch.StartNew();
        var r2 = await runner.DownloadAsync(RequestFor(root, Item2));
        sw.Stop();
        var r1 = await t1;

        Assert.True(r1.IsOk && r1.Value!.Outcome == SteamCmdOutcome.Success);
        Assert.True(r2.IsOk && r2.Value!.Outcome == SteamCmdOutcome.Success);
        // 第二任务实际等待了（耗时≈任务1剩余时间，而非瞬时）
        Assert.True(sw.Elapsed.TotalSeconds >= 2.0, $"第二任务应等待≥2s，实际 {sw.Elapsed.TotalSeconds:F1}s");
        // 句柄不互覆的证据：两任务各自的正则字节/估算不串号
        Assert.Equal(123456, r1.Value.BytesDone);
        Assert.Equal(67890, r2.Value.BytesDone);
        Assert.Equal(123456, r1.Value.EstimatedBytes);
        Assert.Equal(67890, r2.Value.EstimatedBytes);
        Assert.True(File.Exists(Path.Combine(root, slow.ContentRel, "mod.bin")));
        Assert.True(File.Exists(Path.Combine(root, fast.ContentRel, "mod.bin")));
    }

    /// <summary>验收②(M4)：等待超时→SteamError.Timeout；不产生 NRE、不覆盖句柄（第二进程从未启动）。</summary>
    [Fact]
    public async Task D36_Wait_Timeout_Maps_SteamError_No_Handle_Launched()
    {
        var root = NewInstallDir();
        var starts = 0;
        var slow = new FakeScript(Item).LoginOk().Downloading().WriteProduct(10)
            .SuccessLine().HangSecs(4);
        var runner = new SteamCmdRunner(null, stallTimeout: TimeSpan.FromSeconds(60), null,
            waitTimeout: TimeSpan.FromMilliseconds(600),
            psi => { Interlocked.Increment(ref starts); return BatchStart(slow.WriteTo(Path.Combine(root, "fake"), Path.Combine(root, slow.ContentRel)), psi); });

        var t1 = runner.DownloadAsync(RequestFor(root, Item));
        await Task.Delay(300);
        var r2 = await runner.DownloadAsync(RequestFor(root, Item2));   // relay 同一脚本占位（超时路径不启动进程）
        var r1 = await t1;

        Assert.False(r2.IsOk);
        Assert.Equal(SteamError.Timeout, r2.Error);                     // M4：映射而非挂死
        Assert.Equal(1, starts);                                        // 第二任务从未启动进程→无句柄
        // 不覆盖句柄：任务1照常成功（任务2的超时未碰任务1的进程）
        Assert.True(r1.IsOk && r1.Value!.Outcome == SteamCmdOutcome.Success);
    }

    /// <summary>验收③：等待期间取消→Cancelled；不 NRE、不误杀任务1进程（1.x 句柄 bug 原地断言）。</summary>
    [Fact]
    public async Task D36_Cancel_While_Waiting_Does_Not_Kill_First_Process()
    {
        var root = NewInstallDir();
        var slow = new FakeScript(Item).LoginOk().Downloading().WriteProduct(123456).SuccessLine().HangSecs(3);
        var fast = new FakeScript(Item2).LoginOk().Downloading().WriteProduct(1).SuccessLine();
        var runner = NewRunnerMulti(root, new Dictionary<ulong, FakeScript> { [Item] = slow, [Item2] = fast },
            stallTimeout: TimeSpan.FromSeconds(60), waitTimeout: TimeSpan.FromSeconds(30));

        var t1 = runner.DownloadAsync(RequestFor(root, Item));
        await Task.Delay(300);
        using var cts2 = new CancellationTokenSource();
        var t2 = runner.DownloadAsync(RequestFor(root, Item2), ct: cts2.Token);
        await Task.Delay(400);
        cts2.Cancel();                                  // 任务2 在等待槽时被取消
        var r2 = await t2;
        var r1 = await t1;

        Assert.True(r2.IsOk);
        Assert.Equal(SteamCmdOutcome.Cancelled, r2.Value!.Outcome);     // 等待期取消=Cancelled（未持槽）
        Assert.Equal(0, r2.Value.BytesDone);                             // 无 NRE：字段全部有值
        // 任务1进程未被动（句柄未被任务2触碰）：仍成功下完
        Assert.True(r1.IsOk && r1.Value!.Outcome == SteamCmdOutcome.Success);
        Assert.Equal(123456, r1.Value.BytesDone);
    }

    /// <summary>验收④（释放纪律/防早释）：任务完成后槽已释放→下一任务短超时也能立刻拿到。</summary>
    [Fact]
    public async Task D36_Slot_Released_After_Completion_Next_Task_Immediate()
    {
        var root = NewInstallDir();
        var first = new FakeScript(Item).LoginOk().Downloading().WriteProduct(123456).SuccessLine().HangSecs(1);
        var second = new FakeScript(Item2).LoginOk().Downloading().WriteProduct(5).SuccessLine();
        var runner = NewRunnerMulti(root, new Dictionary<ulong, FakeScript> { [Item] = first, [Item2] = second },
            stallTimeout: TimeSpan.FromSeconds(60), waitTimeout: TimeSpan.FromMilliseconds(800));

        var r1 = await runner.DownloadAsync(RequestFor(root, Item));
        var sw = Stopwatch.StartNew();
        var r2 = await runner.DownloadAsync(RequestFor(root, Item2));
        sw.Stop();

        Assert.True(r1.IsOk && r1.Value!.Outcome == SteamCmdOutcome.Success);
        Assert.True(r2.IsOk && r2.Value!.Outcome == SteamCmdOutcome.Success);  // 800ms 内拿到=已释放
        Assert.True(sw.Elapsed.TotalSeconds < 3.0);
    }
}
