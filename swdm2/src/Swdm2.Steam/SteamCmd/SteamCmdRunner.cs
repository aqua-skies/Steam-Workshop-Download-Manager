using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using Swdm2.Core.Domain;
using Swdm2.Core.Logging;
using Swdm2.Core.Results;

namespace Swdm2.Steam.SteamCmd;

/// <summary>
/// steamcmd runner 默认实现（D3.4，1.x steamcmd_engine.py 全量移植）：
/// - 命令：exe +force_install_dir &lt;installDir&gt; +login anonymous|user pass guard
///   +workshop_download_item app item [+validate] +quit（批拼=commands 列表顺序拼接）；
/// - 输出逐行解析（1.x 七正则全移植）；
/// - 成功三元判定：_SUCCESS_RE 匹配 **且** Sweep 产物目录递归非空 **且** 退出码 ∈ {0,7}；
/// - 失败清空目录：content+downloads 下该 item 目录（1.x 重下幂等同语义，防半成品）；
/// - stdin 关闭（1.x 在 finally 写 quit 的替代=Close，同 D3.3 probe 实证可行）；
/// - 三段式收割看门狗：①输出停滞（activity 超时）或 ②磁盘停滞（watched dirs 无新增）→ 终止；
///   ③取消（CancellationToken）→ Kill(entireProcessTree) 全树无僵尸；
/// - 输出脱敏：IRedactionPolicy（Core D1.5）在回调/解析前应用——解析正则只匹配固定串，
///   替换用户名/密码不影响解析（1.x _redact_secrets 同语义）。
/// </summary>
public sealed class SteamCmdRunner : ISteamCmdRunner
{
    // ---------- 1.x 七正则（全量移植，不改语义） ----------
    private static readonly Regex DlRe = new(@"Downloading item (\d+)", RegexOptions.Compiled);
    private static readonly Regex SuccessRe = new(@"Success\. Downloaded item (\d+) to ""([^""]+)"" \((\d+) bytes\)", RegexOptions.Compiled);
    private static readonly Regex FailRe = new(@"(ERROR! .*|Failed to download item \d+.*|Timeout .*|Not Logged On.*)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex LoginOkRe = new(@"(Logged-in OK|Waiting for user info.*OK|Connecting anonymously to Steam Public.*OK)", RegexOptions.Compiled);
    private static readonly Regex LoginFailRe = new(@"(Login Failure|Invalid Password|Not Logged On|rate limit|RateLimit)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex PercentRe = new(@"\[\s*(\d{1,3})\s*%\s*\]", RegexOptions.Compiled);
    private static readonly Regex UpdateStateRe = new(
        @"Update state \(0x[0-9a-fA-F]+\)[^(]*progress:\s*([\d.]+)\s*\(\s*([\d.]+)\s*/\s*([\d.]+)\s*([KkMmGg]?[Bb])",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static readonly Dictionary<string, long> UnitBytes = new(StringComparer.OrdinalIgnoreCase)
    {
        ["b"] = 1, ["kb"] = 1024, ["mb"] = 1024L * 1024, ["gb"] = 1024L * 1024 * 1024,
    };

    /// <summary>⚠️[参数待重标定] 1.x 经验值：输出静默 60s 且磁盘无增长判定卡死。</summary>
    public static readonly TimeSpan DefaultStallTimeout = TimeSpan.FromSeconds(60);

    /// <summary>⚠️[参数待重标定] 1.x 经验值：最小期望速率 200KB/s（原子落盘大文件放宽用）。</summary>
    public const double DefaultMinBytesPerSec = 200_000.0;

    /// <summary>⚠️[参数待重标定] 看门狗轮询间隔（1.x 0.3s）。</summary>
    public static readonly TimeSpan WatchdogInterval = TimeSpan.FromMilliseconds(300);

    private static readonly int[] AcceptExitCodes = { 0, 7 };   // D3.3 实证锚：7=自更新重拉

    private readonly IRedactionPolicy? _redaction;
    private readonly TimeSpan _stallTimeout;
    private readonly double _minBytesPerSec;
    private readonly Func<ProcessStartInfo, Process> _start;

    /// <summary>进程启动 seam（默认 Process.Start；测试注入 cmd /c 批处理伪造进程）。</summary>
    private static Process DefaultStart(ProcessStartInfo psi)
        => Process.Start(psi) ?? throw new InvalidOperationException("Process.Start 未返回进程");

    public SteamCmdRunner(IRedactionPolicy? redaction = null, TimeSpan? stallTimeout = null, double? minBytesPerSec = null)
        : this(redaction, stallTimeout, minBytesPerSec, DefaultStart) { }

    internal SteamCmdRunner(IRedactionPolicy? redaction, TimeSpan? stallTimeout, double? minBytesPerSec,
        Func<ProcessStartInfo, Process> start)
    {
        _redaction = redaction;
        _stallTimeout = stallTimeout ?? DefaultStallTimeout;
        _minBytesPerSec = minBytesPerSec ?? DefaultMinBytesPerSec;
        _start = start ?? DefaultStart;
    }

    public async Task<Result<SteamCmdRunResult, SteamError>> DownloadAsync(
        SteamCmdRunRequest request, IProgress<SteamCmdProgress>? progress = null, CancellationToken ct = default,
        ISteamCmdLineObserver? observer = null)
    {
        ArgumentNullException.ThrowIfNull(request);
        var sw = Stopwatch.StartNew();

        var contentDir = Path.Combine(request.InstallDir, "steamapps", "workshop", "content",
            request.App.Value.ToString(), request.ItemId.Value.ToString());
        // 1.x 注释：content 向上剥 3 层（item→appid→content）到 workshop，downloads 在同层
        var dlTmpDir = Path.Combine(
            Path.GetDirectoryName(Path.GetDirectoryName(Path.GetDirectoryName(contentDir))!)!,
            "downloads", request.App.Value.ToString(), request.ItemId.Value.ToString());
        Directory.CreateDirectory(contentDir);
        Directory.CreateDirectory(dlTmpDir);

        var commands = BuildCommands(request);
        var psi = new ProcessStartInfo(request.ExePath)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            CreateNoWindow = true,
            WorkingDirectory = request.InstallDir,
        };
        foreach (var a in commands) psi.ArgumentList.Add(a);

        Process p;
        try { p = _start(psi); }   // seam：测试注入伪造进程（cmd /c 批处理等）
        catch (Exception) { return Result<SteamCmdRunResult, SteamError>.Fail(SteamError.Network); }
        using var __d = p;   // using 拆分：seam 返回已启动进程

        var state = new RunState();
        if (observer is not null) state.Observer = observer;
        // 外部取消=杀全树（不在此标 Cancelled——取消态判定用 ct.IsCancellationRequested，
        // finally 的清理取消不能误标；1.x bug7 同族教训）
        using var killRegistration = ct.Register(() =>
        {
            try { p.Kill(entireProcessTree: true); } catch { /* 尽力；自然退出兜底 */ }
        });
        // 内部清理 token：只给看门狗/读循环用，不影响取消态判定
        using var cleanup = CancellationTokenSource.CreateLinkedTokenSource(ct);

        p.StandardInput.Close();   // stdin 关闭（1.x 纪律：steamcmd 不等控制台输入；+quit 兜底）

        // 三段式收割看门狗（输出停滞+磁盘停滞；取消走外部 ct 杀全树）
        var wd = WatchdogAsync(p, state, contentDir, dlTmpDir, request.TotalHintBytes, progress, cleanup.Token);
        var reader = ReadLinesAsync(p, state, request, progress, contentDir, cleanup.Token);

        try
        {
            await p.WaitForExitAsync(ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException) { /* 外部取消=已杀全树 */ }
        finally
        {
            // 先把 stdout 排空（行解析对成功判定是前置条件）再停看门狗
            try { await reader.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); } catch { }
            cleanup.Cancel();   // 停看门狗（内部 token，不标 Cancelled）
            try { await wd.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); } catch { }
            if (!p.HasExited) { try { p.Kill(entireProcessTree: true); } catch { } }
        }

        var elapsed = sw.Elapsed.TotalSeconds;

        // 三元判定 + 收尾
        if (state.StallKilled && !state.Success)
            return Finalize(request, contentDir, dlTmpDir, SteamCmdOutcome.StallKilled,
                state.StallReason, state, elapsed, progress);

        if (ct.IsCancellationRequested && !state.Success)
            return Finalize(request, contentDir, dlTmpDir, SteamCmdOutcome.Cancelled, "已取消", state, elapsed, progress);

        if (!state.Success)
        {
            var outcome = !state.LoginOk ? SteamCmdOutcome.LoginFailure
                : !state.DlSeen ? SteamCmdOutcome.ItemNotFound
                : SteamCmdOutcome.Failed;
            var msg = state.Err ?? (!state.LoginOk
                ? "登录失败（可能账号/密码错误，或触发 Steam Guard）"
                : !state.DlSeen ? "未开始下载（物品可能不存在或该游戏不支持匿名下载）" : "下载未完成（可能超时）");
            return Finalize(request, contentDir, dlTmpDir, outcome, msg, state, elapsed, progress);
        }

        // 成功路径：Sweep 完成点估算（M2）
        var estimated = PathSize(new[] { contentDir, dlTmpDir });
        var sweepOk = estimated > 0 && Directory.EnumerateFiles(contentDir, "*", SearchOption.AllDirectories).Any();
        if (!AcceptExitCodes.Contains(p.ExitCode) || !sweepOk)
        {
            // 正则报成功但产物空或退出码非法=假成功（1.x 学费：0 字节假成功被拒绝）
            ClearDir(contentDir); ClearDir(dlTmpDir);
            return Result<SteamCmdRunResult, SteamError>.Fail(SteamError.VersionCheck);
        }

        var result = new SteamCmdRunResult(SteamCmdOutcome.Success, state.SuccessPath!, state.BytesDone,
            estimated, "下载成功", elapsed);
        progress?.Report(new SteamCmdProgress(100, state.BytesDone, "完成"));
        return Result<SteamCmdRunResult, SteamError>.Ok(result);
    }

    // ------------------------------------------------------------------ 命令批拼
    internal static List<string> BuildCommands(SteamCmdRunRequest request)
    {
        var cmds = new List<string> { "+force_install_dir", request.InstallDir };
        cmds.Add("+login");
        if (request.IsAnonymous)
            cmds.Add("anonymous");
        else
        {
            cmds.Add(request.Username!);
            if (request.Password is not null) cmds.Add(request.Password);
            if (request.GuardCode is not null) cmds.Add(request.GuardCode);
        }
        cmds.Add("+workshop_download_item");
        cmds.Add(request.App.Value.ToString());
        cmds.Add(request.ItemId.Value.ToString());
        if (request.Validate) cmds.Add("+validate");
        cmds.Add("+quit");
        return cmds;
    }

    // ------------------------------------------------------------------ 输出解析
    private async Task ReadLinesAsync(Process p, RunState state, SteamCmdRunRequest request,
        IProgress<SteamCmdProgress>? progress, string contentDir, CancellationToken ct)
    {
        using var reader = p.StandardOutput;
        while (await reader.ReadLineAsync(ct).ConfigureAwait(false) is { } raw)
        {
            var line = raw;
            if (string.IsNullOrWhiteSpace(line)) continue;
            line = Redact(line);
            state.Touch();
            state.Observer.OnLine(line);

            if (LoginOkRe.IsMatch(line)) state.LoginOk = true;
            var m = LoginFailRe.Match(line);
            if (m.Success && state.Err is null) state.Err = m.Groups[1].Value.Trim();

            m = DlRe.Match(line);
            if (m.Success)
            {
                state.DlSeen = true;
                progress?.Report(new SteamCmdProgress(1, 0, $"正在下载物品 {m.Groups[1].Value}…"));
            }

            // 实时进度（百分比/Update State；1.x 同源防御性解析）
            if (state.DlSeen && !state.Success)
            {
                m = PercentRe.Match(line);
                if (m.Success)
                {
                    var pct = Math.Clamp(int.Parse(m.Groups[1].Value), 0, 99);
                    var done = request.TotalHintBytes > 0 ? (long)(pct / 100.0 * request.TotalHintBytes) : 0;
                    progress?.Report(new SteamCmdProgress(pct, done, $"下载中 {pct}%"));
                }
                else
                {
                    m = UpdateStateRe.Match(line);
                    if (m.Success)
                    {
                        var pct = Math.Clamp((int)double.Parse(m.Groups[1].Value), 0, 99);
                        var unit = m.Groups[4].Value.ToLowerInvariant();
                        var mult = UnitBytes.TryGetValue(unit, out var mu) ? mu : 1;
                        progress?.Report(new SteamCmdProgress(pct, (long)(double.Parse(m.Groups[2].Value) * mult), $"下载中 {pct}%"));
                    }
                }
            }

            m = SuccessRe.Match(line);
            if (m.Success)
            {
                state.SuccessPath = m.Groups[2].Value;
                state.BytesDone = long.Parse(m.Groups[3].Value);
                state.Success = true;
            }

            m = FailRe.Match(line);
            if (m.Success && state.Err is null) state.Err = m.Groups[1].Value.Trim();
        }
    }

    // ------------------------------------------------------------------ 三段式看门狗
    private async Task WatchdogAsync(Process p, RunState state, string contentDir, string dlTmpDir,
        long totalHint, IProgress<SteamCmdProgress>? progress, CancellationToken ct)
    {
        var maxSilence = _stallTimeout;
        if (totalHint > 0)
            maxSilence = TimeSpan.FromSeconds(Math.Max(maxSilence.TotalSeconds, totalHint / _minBytesPerSec));

        var lastSize = PathSize(new[] { contentDir, dlTmpDir });
        try
        {
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(WatchdogInterval, ct).ConfigureAwait(false);
                if (state.Success || p.HasExited) return;

                var size = PathSize(new[] { contentDir, dlTmpDir });
                if (size > lastSize)
                {
                    lastSize = size;
                    state.Touch();
                    if (!state.Success)
                    {
                        if (totalHint > 0)
                        {
                            var pct = (int)Math.Clamp((double)size / totalHint * 100, 0, 99);
                            progress?.Report(new SteamCmdProgress(pct, size, $"下载中 {pct}%（已落盘）"));
                        }
                        else
                        {
                            progress?.Report(new SteamCmdProgress(-1, size, $"已下载 {size / 1048576.0:F1} MB"));
                        }
                    }
                }

                if (DateTime.UtcNow - state.LastActivityUtc > maxSilence)
                {
                    state.StallKilled = true;
                    state.StallReason = $"下载停滞超时（{(DateTime.UtcNow - state.LastActivityUtc).TotalSeconds:F0}s 无进展）";
                    try { p.Kill(entireProcessTree: true); } catch { }
                    return;
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    // ------------------------------------------------------------------ 工具
    private string Redact(string line)
    {
        if (_redaction is null) return line;
        try { return _redaction.Redact(line); }
        catch { return line; }
    }

    private static Result<SteamCmdRunResult, SteamError> Finalize(SteamCmdRunRequest request,
        string contentDir, string dlTmpDir, SteamCmdOutcome outcome, string? message,
        RunState state, double elapsed, IProgress<SteamCmdProgress>? progress)
    {
        // 失败/取消/停滞：清空该 item 内容目录（半成品不残留；1.x 重下幂等同义）
        ClearDir(contentDir);
        ClearDir(dlTmpDir);
        return Result<SteamCmdRunResult, SteamError>.Ok(
            new SteamCmdRunResult(outcome, string.Empty, 0, 0, message ?? string.Empty, elapsed));
    }

    /// <summary>递归求目录总字节数（容错，忽略不可访问项；1.x _path_size 同源）。</summary>
    internal static long PathSize(string[] dirs)
    {
        var total = 0L;
        foreach (var d in dirs)
        {
            try
            {
                if (!Directory.Exists(d)) continue;
                foreach (var f in Directory.EnumerateFiles(d, "*", SearchOption.AllDirectories))
                {
                    try { total += new FileInfo(f).Length; } catch (IOException) { }
                }
            }
            catch (IOException) { }
        }
        return total;
    }

    private static void ClearDir(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true); }
        catch (IOException) { /* 尽力：文件占用时残留由重下幂等清 */ }
    }

    /// <summary>可变运行状态（单次 DownloadAsync 生命周期内；线程安全需求=输出线程与看门狗并发 touch）。</summary>
    internal sealed class RunState
    {
        public bool LoginOk, DlSeen, Success, StallKilled;
        public string? SuccessPath, Err, StallReason;
        public long BytesDone;
        private DateTime _lastActivityUtc = DateTime.UtcNow;
        private readonly object _actLock = new();

        public DateTime LastActivityUtc
        {
            get { lock (_actLock) return _lastActivityUtc; }
        }

        public void Touch()
        {
            lock (_actLock) _lastActivityUtc = DateTime.UtcNow;
        }

        public ISteamCmdLineObserver Observer { get; set; } = new NullObserver();

        internal sealed class NullObserver : ISteamCmdLineObserver
        {
            public void OnLine(string redactedLine) { }
            public void OnThrottleSignal(string kind, string line) { }
        }
    }
}
