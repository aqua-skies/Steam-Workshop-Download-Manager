using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using Xunit;

namespace Swdm2.UiTests.Calibration;

/// <summary>
/// D4.8 E sweep:元数据并发对**真 API**(store.steampowered.com storesearch,匿名无 key)。
///
/// 推理起点（先问"能否更大")：1.x=1（串行）。calibration_1 发现 429=请求头指纹+累计天花（~117 次/天级），
/// 并发=更快撞天花 → 预期增益不足 10% 或错误率&gt;2% → 大概率结论=**保持 1**（保守不是无脑放大）。
///
/// 代理：本机系统代理 http://127.0.0.1:7897（Steam fake-IP 出口；calibration_1 同环境）。
/// 环境容忍：网络全失败=记录 ERR 行+标注沙箱阻断（设计对照纪律：网络失败≠不可行，换签复跑）。
/// 输出：TestArtifacts/calibration_2.csv（追加 E 行）。
/// </summary>
public sealed class MetadataApiConcurrencyCalibration
{
    private const string Url = "https://store.steampowered.com/api/storesearch/?term=portal&l=schinese&cc=CN";

    [WpfFact] // 同 B3:避开 xunit.core/v3.core [Fact] 二义
    public async Task E_Metadata_Concurrency_Sweep()
    {
        var proxy = Environment.GetEnvironmentVariable("SWDM2_PROXY") ?? "http://127.0.0.1:7897";
        var candidates = new[] { 1, 2, 4 };
        var rows = new List<string> { "idx,phase,candidate,rep,req,status,ms,len,result,note" };
        var idx = 0;
        foreach (var c in candidates)
        {
            for (var rep = 1; rep <= 2; rep++)
            {
                // 并发 c 路同时发 N=4 个请求（指纹头=Accept-Language,calibration_1 防指纹组合）
                var handler = new SocketsHttpHandler { Proxy = new WebProxy(proxy) };
                using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };
                http.DefaultRequestHeaders.Add("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8");
                var requests = new List<Task<(int status, long ms, long len, string? err)>>();
                for (var n = 0; n < 4; n++) requests.Add(SendOneAsync(http, idx));
                var results = await Task.WhenAll(requests);

                var ok = results.Count(r => r.status == 200);
                var avgMs = results.Where(r => r.ms > 0).Select(r => r.ms).DefaultIfEmpty(0).Average();
                foreach (var (status, ms, len, err) in results)
                {
                    var note = err is null ? "" : err.Replace(",", ";");
                    rows.Add($"{idx++},E-metadataConcurrency,{c},{rep},req,{status},{ms},{len},{(status == 200 ? 1 : 0)},{note}");
                }
                Console.WriteLine($"[B3-E] concurrency={c} rep{rep}: ok={ok}/4 avgMs={avgMs:F0}");
                if (ok == 0)
                {
                    rows.Add($"{idx++},E-metadataConcurrency,{c},{rep},block,0,0,0,0,ALL-FAIL(proxy={proxy};沙箱阻断=换签桌面复跑)");
                }
            }
        }
        await AppendCsvAsync(rows);
    }

    private static async Task<(int status, long ms, long len, string? err)> SendOneAsync(HttpClient http, int _)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            var resp = await http.GetAsync(Url).ConfigureAwait(false);
            var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
            sw.Stop();
            return ((int)resp.StatusCode, sw.ElapsedMilliseconds, body.Length, null);
        }
        catch (Exception ex)
        {
            sw.Stop();
            return (0, sw.ElapsedMilliseconds, 0, ex.GetType().Name + ":" + ex.Message);
        }
    }

    private static async Task AppendCsvAsync(List<string> rows)
    {
        var dir = B3Artifacts.FindArtifactsDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "calibration_2.csv");
        var first = !File.Exists(path);
        await using var stream = new FileStream(path, FileMode.Append, FileAccess.Write,
            FileShare.None, 4096, useAsync: true);
        var wroteHeader = false;
        foreach (var line in rows)
        {
            var isHeader = line.StartsWith("idx,");
            if (isHeader && (!first || wroteHeader)) continue;
            if (isHeader) wroteHeader = true;
            var bytes = System.Text.Encoding.UTF8.GetBytes(line + "\n");
            await stream.WriteAsync(bytes).ConfigureAwait(false);
        }
    }
}

internal static class B3Artifacts
{
    public static string FindArtifactsDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && dir.Name != "swdm2" && dir.Parent is not null) dir = dir.Parent;
        var root = dir?.Parent ?? new DirectoryInfo(Directory.GetCurrentDirectory());
        return Path.Combine(root.FullName, "swdm2", "TestArtifacts");
    }
}
