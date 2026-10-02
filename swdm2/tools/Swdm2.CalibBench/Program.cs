// SWDM 2.0 D2.6 参数重标定基准（t3 §5.1/§5.2 可执行骨架）
// B1: 429 退避曲线（三段法：零延迟裸请求 burst 诱导 429 → 等 t 秒 → 指纹头复测）
// B2: 端点最小安全间隔（指纹头四件套固定间隔连发，统计 200 率）
// 独立控制台程序（不入 sln）：沙箱 dotnet test testhost 崩溃（SP-3），故用 dotnet run 直跑。
// 输出：swdm2/docs/calibration_1.csv（原始逐请求）+ calibration_1.json（机读快照）。
// 环境：代理经环境变量 SWDM2_BENCH_PROXY（默认 http://127.0.0.1:7897）。
// 安全纪律：诱导 429 只用裸请求（无 Accept-Language），复测/连发一律指纹头，不污染生产批次。
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

// ---------- 配置 ----------
const string DetailUrl = "https://steamcommunity.com/sharedfiles/filedetails/?id={0}";
const string BrowseUrl = "https://steamcommunity.com/workshop/browse/?appid=322330"; // 饥荒联机版
const string KnownId = "3808352517"; // 兜底 id（架构 S12 复验过的真实 id）
const string ChromeUa = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
int[] B1Candidates = { 5, 10, 15, 20, 30, 45, 60, 90 };
double[] B2Candidates = { 0.5, 1, 2, 4, 8 };
const int B2ReqsPerRound = 20;
const int Repeats = 3;
const int CooldownLevelSec = 120; // 档间冷却
const int CooldownRoundOkSec = 30; // B2 轮间（无失败）
const int CooldownRoundFailSec = 120; // B2 轮间（有失败， purge 潜在限流态）
const int InduceCap = 80; // 诱导 burst 上限

var phaseArg = args.FirstOrDefault(a => a.StartsWith("--phase="))?["--phase=".Length..] ?? "b1+b2";
var proxy = Environment.GetEnvironmentVariable("SWDM2_BENCH_PROXY") ?? "http://127.0.0.1:7897";
var docsDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "docs"));
Directory.CreateDirectory(docsDir);
var csvPath = Path.Combine(docsDir, "calibration_1.csv");
var jsonPath = Path.Combine(docsDir, "calibration_1.json");

var records = new List<Rec>();
var swAll = Stopwatch.StartNew();
int idx = 0;

// HttpClient：裸（诱导用）与指纹（复测/连发用）各一个；显式代理（S5：HttpClient 不读系统代理）
var handler = new SocketsHttpHandler
{
    Proxy = new System.Net.WebProxy(proxy, false),
    PooledConnectionLifetime = TimeSpan.FromMinutes(2),
    AutomaticDecompression = System.Net.DecompressionMethods.None
};
using var bareHttp = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
using var fpHttp = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
fpHttp.DefaultRequestHeaders.Add("User-Agent", ChromeUa);
fpHttp.DefaultRequestHeaders.Add("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8");
fpHttp.DefaultRequestHeaders.Add("X-Requested-With", "XMLHttpRequest");
fpHttp.DefaultRequestHeaders.Add("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8");

// ---------- 环境标注 ----------
var envExitIp = "(unmeasured)";
try
{
    using var ipProbe = new HttpClient(new SocketsHttpHandler { Proxy = new System.Net.WebProxy(proxy, false) }) { Timeout = TimeSpan.FromSeconds(15) };
    envExitIp = ipProbe.GetStringAsync("https://api.ipify.org").GetAwaiter().GetResult().Trim();
}
catch (Exception ex) { envExitIp = $"probe-failed:{ex.GetType().Name}"; }
Log("env", 0, 0, 0, 200, 0, 0, "env", $"exit-ip={envExitIp}; proxy={proxy}; utc={DateTime.UtcNow:O}");

// ---------- Phase 0: id 池（browse 页 data-publishedfileid，指纹头抓取） ----------
var ids = new List<string> { KnownId };
try
{
    var browse = fpHttp.GetStringAsync(BrowseUrl).GetAwaiter().GetResult();
    var matches = Regex.Matches(browse, @"data-publishedfileid=""(\d{6,})""");
    var collected = matches.Select(m => m.Groups[1].Value).Distinct().Take(40).ToList();
    if (collected.Count > 0) ids = collected;
    Log("env", 0, 0, 0, 200, browse.Length, 1, "ids", $"pool={ids.Count} from browse");
}
catch (Exception ex)
{
    Log("env", 0, 0, 0, 0, 0, 0, "ids", $"browse-failed:{ex.GetType().Name} fallback to KnownId only");
}
int idCursor = 0;
string NextId() => ids[idCursor++ % ids.Count];

// ---------- 请求原语 ----------
async Task<Probe> ReqAsync(HttpClient http, string url, bool bare)
{
    var sw = Stopwatch.StartNew();
    try
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        if (bare) req.Headers.Add("User-Agent", ChromeUa); // 仅 UA，无 Accept-Language
        using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
        var len = (int)(resp.Content.Headers.ContentLength ?? 0);
        if (len == 0) { var b = await resp.Content.ReadAsByteArrayAsync(); len = b.Length; }
        sw.Stop();
        return new Probe((int)resp.StatusCode, len, sw.ElapsedMilliseconds, (string?)null);
    }
    catch (HttpRequestException ex)
    {
        sw.Stop();
        var code = ex.StatusCode.HasValue ? (int)ex.StatusCode : 0;
        return new Probe(code, 0, sw.ElapsedMilliseconds, ex.GetType().Name + ":" + ex.Message);
    }
    catch (Exception ex)
    {
        sw.Stop();
        return new Probe(0, 0, sw.ElapsedMilliseconds, ex.GetType().Name + ":" + ex.Message);
    }
}

// 诱导：零延迟裸请求直到首个非 200（429），返回诱导请求数；-1=未触发
async Task<int> Induce429(string label)
{
    for (var i = 1; i <= InduceCap; i++)
    {
        var p = await ReqAsync(bareHttp, string.Format(DetailUrl, NextId()), bare: true);
        var status = p.StatusCode;
        Log("A-" + label, 0, 0, i, status, (int)p.Ms, p.Len, status == 200 ? "1" : "0", status != 200 ? p.Note ?? "" : "");
        if (status == 429) return i;
        if (status != 200) return -2; // 其他失败（如 403）：非 429，环境异常，按实记录
    }
    return -1;
}

// ---------- B1 ----------
if (phaseArg.Contains('b') && phaseArg.Contains('1'))
{
    Console.WriteLine($"[B1] start {DateTime.Now:O} 诱导探测（裸请求 burst 上限 {InduceCap}）");
    var induced = await Induce429("try1");
    Log("env", 0, 0, 0, 200, 0, 1, "b1-induction", $"first-pass induce result={induced}");
    Console.WriteLine($"[B1] 首次诱导结果：{(induced == -1 ? "未触发（" + InduceCap + " 次裸请求全 200）" : induced == -2 ? "非 429 失败" : $"第 {induced} 次触发 429")}");

    if (induced >= 1)
    {
        foreach (var t in B1Candidates)
        {
            for (var rep = 1; rep <= Repeats; rep++)
            {
                var reInd = await Induce429($"t{t}r{rep}");
                Log("B1", t, rep, 0, 0, 0, 0, "induce", $"reinduce={reInd}");
                if (reInd < 1) { Log("B1", t, rep, 0, 0, 0, 0, "skip", "induction-failed"); continue; }
                await Task.Delay(TimeSpan.FromSeconds(t));
                var p = await ReqAsync(fpHttp, string.Format(DetailUrl, NextId()), bare: false);
                var ok = p.StatusCode == 200 && p.Len > 50000;
                Log("B1", t, rep, 0, p.StatusCode, (int)p.Ms, p.Len, ok ? "1" : "0", p.Note ?? "");
                Console.WriteLine($"[B1] t={t}s rep={rep} -> status={p.StatusCode} len={p.Len} ms={p.Ms} ok={ok}");
                if (rep < Repeats) await Task.Delay(TimeSpan.FromSeconds(15));
            }
            if (t != B1Candidates[^1]) { Console.WriteLine($"[B1] 档间冷却 {CooldownLevelSec}s"); await Task.Delay(TimeSpan.FromSeconds(CooldownLevelSec)); }
        }
    }
    else
    {
        Log("B1", 0, 0, 0, 0, 0, 0, "env-limited", "当前网络环境无法诱导 429；B1 无可测数据，参数建议降级为标注待定（设计对照纪律：探测失败≠端点不可限流）");
        Console.WriteLine("[B1] 环境受限：无法诱导 429，B1 跳过候选档测量（诚实记录，不编造数据）");
    }
}

// ---------- B2 ----------
if (phaseArg.Contains('b') && phaseArg.Contains('2'))
{
    Console.WriteLine($"[B2] start {DateTime.Now:O} 指纹头固定间隔连发（每档 {B2ReqsPerRound} 请求 × {Repeats} 轮）");
    foreach (var c in B2Candidates)
    {
        for (var rep = 1; rep <= Repeats; rep++)
        {
            int okCnt = 0, failCnt = 0;
            for (var i = 1; i <= B2ReqsPerRound; i++)
            {
                await Task.Delay(TimeSpan.FromSeconds(c)); // 锁覆盖 read-sleep-write 全程：间隔后再发
                var p = await ReqAsync(fpHttp, string.Format(DetailUrl, NextId()), bare: false);
                var ok = p.StatusCode == 200 && p.Len > 50000;
                if (ok) okCnt++; else failCnt++;
                Log("B2", c, rep, i, p.StatusCode, (int)p.Ms, p.Len, ok ? "1" : "0", p.Note ?? "");
            }
            Console.WriteLine($"[B2] interval={c}s rep={rep} ok={okCnt} fail={failCnt}");
            var cd = failCnt > 0 ? CooldownRoundFailSec : CooldownRoundOkSec;
            if (!(c == B2Candidates[^1] && rep == Repeats)) await Task.Delay(TimeSpan.FromSeconds(cd));
        }
        if (c != B2Candidates[^1]) { Console.WriteLine($"[B2] 档间冷却 {CooldownLevelSec}s"); await Task.Delay(TimeSpan.FromSeconds(CooldownLevelSec)); }
    }
}

// ---------- 落盘 ----------
swAll.Stop();
File.WriteAllText(csvPath, "idx,phase,candidate,rep,req,status,ms,len,result,note,ts\n" +
    string.Join("\n", records.Select(r => r.ToCsv())));
var summary = new
{
    meta = new { generated = DateTime.Now.ToString("O"), exit_ip = envExitIp, proxy, total_elapsed_sec = swAll.Elapsed.TotalSeconds },
    records
};
var jsonOpts = new JsonSerializerOptions { WriteIndented = true };
File.WriteAllText(jsonPath, JsonSerializer.Serialize(summary, jsonOpts));
Console.WriteLine($"DONE csv={csvPath} json={jsonPath} total={swAll.Elapsed.TotalSeconds:F0}s records={records.Count}");
return 0;

// ---------- 工具 ----------
void Log(string phase, object candidate, int rep, int req, int status, int ms, int len, string result, string note = "")
{
    records.Add(new Rec(idx++, phase, candidate?.ToString() ?? "", rep, req, status, ms, len, result, note,
        DateTime.Now.ToString("O")));
}

public sealed record Rec(int Idx, string Phase, string Candidate, int Rep, int Req, int Status, int Ms, int Len, string Result, string Note, string Ts)
{
    public string ToCsv() => $"{Idx},{Phase},{Candidate},{Rep},{Req},{Status},{Ms},{Len},{Result},{Escape(Note)},{Ts}";
    private static string Escape(string s) => s.Contains(',') || s.Contains('"') ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;
}

public sealed record Probe(int StatusCode, int Len, double Ms, string? Body, string? Note = null);
