using System.Net;
using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Steam.Resilience;
using Swdm2.Steam.Web;

namespace Swdm2.Steam.SteamCmd;

/// <summary>
/// 版本探针契约（D3.3 seam）：运行 steamcmd 并返回 (ExitCode, StdOut)。
/// 真实实现 <see cref="SteamCmdProcessProbe"/>；测试注入桩以离线断言校验语义。
/// </summary>
public interface ISteamCmdVersionProbe
{
    Task<VersionProbeResult> ProbeAsync(string exePath, CancellationToken ct = default);
}

/// <summary>探针结果：直接子进程退出码（自更新重拉=7）+ 合并 stdout。</summary>
public sealed record VersionProbeResult(int ExitCode, string StdOut, SteamError? Error = null);

/// <summary>
/// 默认探针：`steamcmd.exe +login anonymous +quit`（实测 2026-10-02）：
/// - `+version` 命令不存在（"Command not found: version"）——版本串只从 banner 行解析；
/// - banner: `Steam Console Client (c) Valve Corporation - version 1788292693`；
/// - 退出码：冷启动自更新后=7（父进程交由更新链重启），已自举=0；两值均视作"可运行"；
/// - 纪律（1.x 移植）：stdin 关闭防等输入；超时杀全树（taskkill /F /T）防僵尸子进程链。
/// </summary>
public sealed class SteamCmdProcessProbe : ISteamCmdVersionProbe
{
    /// <summary>⚠️[参数待重标定] 首跑自举下载 43+29MB，上限 300s；已自举实测 7.6s。</summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(300);

    private readonly TimeSpan _timeout;
    public SteamCmdProcessProbe(TimeSpan? timeout = null) => _timeout = timeout ?? DefaultTimeout;

    public Task<VersionProbeResult> ProbeAsync(string exePath, CancellationToken ct = default)
    {
        // 实测约束：steamcmd 不能从含非 ASCII 字符的路径启动（Fatal exit=-2，
        // "cannot run from a folder path that includes non-English characters"）。
        // 门控在探针级：不启动进程直接返回 InvalidConfiguration；
        // 桩探针不启动进程故不受影响（测试 seam——沙箱无 ASCII 可写目录时离线测试仍可跑）。
        if (exePath.Any(c => c > 127))
            return Task.FromResult(new VersionProbeResult(0, string.Empty, SteamError.InvalidConfiguration));

        return ProbeCoreAsync(exePath, ct);
    }

    private async Task<VersionProbeResult> ProbeCoreAsync(string exePath, CancellationToken ct)
    {
        using var p = new Process();
        p.StartInfo = new ProcessStartInfo(exePath, "+login anonymous +quit")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            CreateNoWindow = true,
        };
        p.Start();
        p.StandardInput.Close(); // 1.x 纪律：stdin 关闭，steamcmd 不等控制台输入
        var readOut = p.StandardOutput.ReadToEndAsync(ct);
        try
        {
            await p.WaitForExitAsync(ct).WaitAsync(_timeout, ct);
        }
        catch (TimeoutException)
        {
            KillTree(p);
            try { await readOut.WaitAsync(TimeSpan.FromSeconds(5), CancellationToken.None); } catch { }
            throw new TimeoutException($"steamcmd probe 超时 {_timeout.TotalSeconds:F0}s");
        }
        var stdout = await readOut.WaitAsync(TimeSpan.FromSeconds(5), CancellationToken.None);
        return new VersionProbeResult(p.ExitCode, stdout);
    }

    /// <summary>杀全树（steamcmd 自更新会重拉子进程，进程链持有重定向句柄）。</summary>
    private static void KillTree(Process p)
    {
        try { p.Kill(entireProcessTree: true); }
        catch { /* 尽力而为：句柄释放由 owning 退出兜底 */ }
    }
}

/// <summary>
/// steamcmd 部署器默认实现（D3.3）：
/// - 下载：D2.1 IHttpClientFactory（指纹头四件套）+ ResiliencePipeline（熔断器；bucket=steamcmd-cdn，
///   Throttler 未知 bucket 回退 Zero=无节流——CDN 大文件单发，非 D2.6 元数据高频域，无实测需求）；
/// - 幂等：快路径（exe+zip 存在 & sha 与指纹基线一致）直接返回，0 请求 0 进程；
/// - 损坏检测：zip/exe sha 与基线不符 → 重下或重解压（单次重试，幂等）；
/// - 基线 sidecar：steamcmd.fingerprint.json（自记录，M1：Valve 无官方签名）。
/// </summary>
public sealed class SteamCmdDeployer : ISteamCmdDeployer
{
    public const string OfficialZipUrl = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip";
    public const string Bucket = "steamcmd-cdn";
    private const string ExeName = "steamcmd.exe";
    private const string ZipName = "steamcmd.zip";
    private const string PartName = "steamcmd.zip.part";
    private const string FingerprintName = "steamcmd.fingerprint.json";

    private static readonly Regex BannerVersion = new(
        @"Steam Console Client \(c\) Valve Corporation - version (\d+)", RegexOptions.Compiled);

    private readonly IPathService _paths;
    private readonly IHttpClientFactory _factory;
    private readonly ISteamCmdVersionProbe _probe;
    private readonly string _zipUrl;
    private readonly ICircuitBreaker? _breaker;
    private readonly IThrottler? _throttler;

    public SteamCmdDeployer(IPathService paths, IHttpClientFactory factory, ISteamCmdVersionProbe probe,
        string? zipUrl = null, ICircuitBreaker? breaker = null, IThrottler? throttler = null)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _factory = factory ?? throw new ArgumentNullException(nameof(factory));
        _probe = probe ?? throw new ArgumentNullException(nameof(probe));
        _zipUrl = string.IsNullOrWhiteSpace(zipUrl) ? OfficialZipUrl : zipUrl;
        _breaker = breaker;
        _throttler = throttler;
    }

    public SteamCmdDeployment? Current
    {
        get
        {
            var (dir, exe, zip, fpFile) = Paths();
            return File.Exists(exe) && File.Exists(zip) && File.Exists(fpFile)
                ? ReadFingerprint(fpFile)
                : null;
        }
    }

    public async Task<Result<SteamCmdDeployment, SteamError>> EnsureAsync(CancellationToken ct = default)
    {
        var (dir, exe, zip, fpFile) = Paths();


        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

        var baseline = ReadFingerprint(fpFile);

        // 快路径：文件齐 + sha 与基线一致 → 0 请求 0 进程（幂等）
        if (baseline is not null && File.Exists(exe) && File.Exists(zip)
            && Sha256(zip) == baseline.ZipSha256)
        {
            return Result<SteamCmdDeployment, SteamError>.Ok(baseline with { ExePath = exe });
        }

        // 慢路径：需要 zip（下载或重下）→ 解压 → 探针 → 基线
        for (var attempt = 1; attempt <= 2; attempt++)
        {
            var needDownload = !File.Exists(zip)
                || (baseline is not null && Sha256(zip) != baseline.ZipSha256)
                || !IsValidZip(zip);

            if (needDownload)
            {
                var dl = await DownloadAsync(ct).ConfigureAwait(false);
                if (!dl.IsOk)
                    return Result<SteamCmdDeployment, SteamError>.Fail(dl.Error ?? SteamError.None);
                var target = Path.Combine(dir, ZipName);
                try { if (File.Exists(target)) File.Delete(target); File.Move(Path.Combine(dir, PartName), target); }
                catch (IOException) { /* 覆盖失败则下一轮重下 */ }
            }

            var extract = Extract(zip, dir);
            if (!extract.IsOk)
            {
                // zip 损坏：删除本地副本重下一次（1.x 幂等重下经验）
                TryDelete(zip);
                if (attempt == 2)
                    return Result<SteamCmdDeployment, SteamError>.Fail(extract.Error ?? SteamError.CorruptAsset);
                continue;
            }

            if (!File.Exists(exe))
                return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.CorruptAsset);

            // probe + 版本解析
            try
            {
                var pr = await _probe.ProbeAsync(exe, ct).ConfigureAwait(false);
                if (pr.Error is not null)
                    return Result<SteamCmdDeployment, SteamError>.Fail(pr.Error.Value);  // 探针级门控（非 ASCII 路径等）
                if (pr.ExitCode != 0 && pr.ExitCode != 7)
                    return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.VersionCheck);
                var version = ParseVersion(pr.StdOut);
                if (version is null)
                    return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.VersionCheck);

                var zipSha = Sha256(zip);
                var zipBytes = new FileInfo(zip).Length;
                var deployment = new SteamCmdDeployment(exe, version, zipSha, zipBytes, DateTimeOffset.UtcNow);
                WriteFingerprint(fpFile, deployment);
                return Result<SteamCmdDeployment, SteamError>.Ok(deployment);
            }
            catch (OperationCanceledException) { throw; }
            catch (TimeoutException)
            {
                return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.Timeout);
            }
            catch (Exception)
            {
                return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.Network);
            }
        }

        return Result<SteamCmdDeployment, SteamError>.Fail(SteamError.CorruptAsset);
    }

    private (string dir, string exe, string zip, string fp) Paths()
    {
        var dir = _paths.SteamCmdDirectory;
        return (dir, Path.Combine(dir, ExeName), Path.Combine(dir, ZipName), Path.Combine(dir, FingerprintName));
    }

    /// <summary>下载到 .part（熔断器护栏；状态码映射同 D2.3 口径）。</summary>
    private async Task<Result<string, SteamError>> DownloadAsync(CancellationToken ct)
    {
        var (_, _, zip, _) = Paths();
        var part = Path.Combine(_paths.SteamCmdDirectory, PartName);

        return await ResiliencePipeline.ExecuteAsync(Bucket, _throttler, _breaker, async token =>
        {
            var clientResult = _factory.CreateClient();
            if (!clientResult.IsOk)
                return Result<string, SteamError>.Fail(clientResult.Error ?? SteamError.None);

            using var client = clientResult.Value!;
            try
            {
                using var resp = await client.GetAsync(_zipUrl, HttpCompletionOption.ResponseHeadersRead, token)
                    .ConfigureAwait(false);
                if (resp.StatusCode == HttpStatusCode.TooManyRequests)
                    return Result<string, SteamError>.Fail(SteamError.RateLimited);
                if (resp.StatusCode == HttpStatusCode.Forbidden)
                    return Result<string, SteamError>.Fail(SteamError.Blocked);
                if (resp.StatusCode == HttpStatusCode.NotFound)
                    return Result<string, SteamError>.Fail(SteamError.NotFound);
                if (!resp.IsSuccessStatusCode)
                    return Result<string, SteamError>.Fail(SteamError.Network);

                await using (var fs = File.Create(part))
                    await resp.Content.CopyToAsync(fs, token).ConfigureAwait(false);
                return Result<string, SteamError>.Ok(part);
            }
            catch (TaskCanceledException) when (!token.IsCancellationRequested)
            {
                return Result<string, SteamError>.Fail(SteamError.Timeout);
            }
            catch (HttpRequestException)
            {
                return Result<string, SteamError>.Fail(SteamError.Network);
            }
        }, ct).ConfigureAwait(false);
    }

    /// <summary>覆盖解压（US-ASCII 路径已门控；解压失败=CorruptAsset）。</summary>
    private static Result<bool, SteamError> Extract(string zip, string dir)
    {
        try
        {
            ZipFile.ExtractToDirectory(zip, dir, overwriteFiles: true);
            return Result<bool, SteamError>.Ok(default);
        }
        catch (InvalidDataException)
        {
            return Result<bool, SteamError>.Fail(SteamError.CorruptAsset);
        }
        catch (Exception)
        {
            return Result<bool, SteamError>.Fail(SteamError.CorruptAsset);
        }
    }

    private static string? ParseVersion(string stdout)
        => BannerVersion.Match(stdout) is { Success: true } m ? m.Groups[1].Value : null;

    private static string Sha256(string file)
    {
        using var sha = SHA256.Create();
        using var fs = File.OpenRead(file);
        return Convert.ToHexString(sha.ComputeHash(fs));
    }

    private static bool IsValidZip(string file)
    {
        try { using var _ = ZipFile.OpenRead(file); return true; }
        catch { return false; }
    }

    private static void TryDelete(string file)
    {
        try { if (File.Exists(file)) File.Delete(file); }
        catch (IOException) { }
    }

    private static SteamCmdDeployment? ReadFingerprint(string file)
    {
        try
        {
            if (!File.Exists(file)) return null;
            var doc = JsonDocument.Parse(File.ReadAllText(file));
            var root = doc.RootElement;
            return new SteamCmdDeployment(
                root.GetProperty("exePath").GetString()!,
                root.GetProperty("version").GetString()!,
                root.GetProperty("zipSha256").GetString()!,
                root.GetProperty("zipBytes").GetInt64(),
                root.GetProperty("recordedAtUtc").GetDateTimeOffset());
        }
        catch { return null; }
    }

    private static void WriteFingerprint(string file, SteamCmdDeployment d)
    {
        var json = JsonSerializer.Serialize(new
        {
            exePath = d.ExePath, version = d.Version, zipSha256 = d.ZipSha256,
            zipBytes = d.ZipBytes, recordedAtUtc = d.RecordedAtUtc,
        }, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(file, json);
    }
}
