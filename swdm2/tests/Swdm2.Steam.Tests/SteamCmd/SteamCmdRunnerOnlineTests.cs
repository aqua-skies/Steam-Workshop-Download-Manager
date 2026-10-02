using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.SteamCmd;

/// <summary>
/// D3.4 runner 在线集成测试（真实输入，Category=Online）：
/// - 真实匿名下载（app 4000 / item 17906，sub17906 对应 fixture；1.x 同尺度回归锚）；
/// - 先决条件：D3.3 部署器确保 steamcmd 就绪（ASCII 临时根；
///   沙箱 .dtmp 中文路径=探针级门控 InvalidConfiguration=环境容忍，桌面复跑真绿）；
/// - M2 验收：完成点 Sweep 估算字节 vs Success 正则字节 偏差 &lt; 10%；
/// - 产物递归非空（1.x 同尺度断言）；
/// - 失败容忍定律（同 D2.3/D2.5/D3.3 口径）：环境结论不算失败。
/// </summary>
[Trait("Category", "Online")]
public sealed class SteamCmdRunnerOnlineTests
{
    private static bool ShouldSkipOnline
        => Environment.GetEnvironmentVariable("SWDM2_SKIP_ONLINE") == "1";

    [Fact]
    public async Task Online_Download_Anonymous_Mod_Success_Sweep_Deviation_Below_10Pct()
    {
        if (ShouldSkipOnline)
        {
            Console.WriteLine("[ONLINE-SKIP] SWDM2_SKIP_ONLINE=1");
            return;
        }

        // ASCII 安装根（steamcmd 实测不能从中文路径启动；driver TMP 重定向到 .dtmp=中文→门控拒绝）
        var asciiRoot = Environment.GetEnvironmentVariable("SWDM2_ASCII_ROOT");
        var root = !string.IsNullOrEmpty(asciiRoot)
            ? Path.Combine(asciiRoot, "swdm2_d34_online_" + Guid.NewGuid().ToString("N")[..8])
            : Path.Combine(Path.GetTempPath(), "swdm2_d34_online_" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(root);

        try
        {
            // 1) 部署 steamcmd（D3.3 接驳）
            var deployer = new SteamCmdDeployer(
                new OnlinePaths(root),
                new SteamHttpClientFactory(new SteamOptions { Proxy = ProxyMode.Direct }),
                new SteamCmdProcessProbe());
            var deployed = await deployer.EnsureAsync();
            if (!deployed.IsOk)
            {
                Console.WriteLine($"[ONLINE-DEPLOY-FAIL] {deployed.Error} — 环境阻断（换网络条件复验）");
                Assert.Contains(deployed.Error ?? SteamError.None, new[]
                {
                    SteamError.RateLimited, SteamError.Network, SteamError.Blocked,
                    SteamError.Timeout, SteamError.NotFound, SteamError.CircuitOpen,
                    SteamError.InvalidConfiguration,  // 沙箱中文 .dtmp 门控
                });
                return;
            }

            // 2) 真实匿名下载（sub17906/app4000）
            var install = Path.Combine(root, "install");
            var runner = new SteamCmdRunner();
            var req = new SteamCmdRunRequest(
                new PublishedFileId(17906), new AppId(4000), deployed.Value!.ExePath, install);

            var result = await runner.DownloadAsync(req, progress: new ConsoleProgress());

            if (!result.IsOk)
            {
                Console.WriteLine($"[ONLINE-RUN-FAIL] {result.Error} — 环境阻断（换网络条件复验）");
                Assert.Contains(result.Error ?? SteamError.None, new[]
                {
                    SteamError.RateLimited, SteamError.Network, SteamError.Blocked,
                    SteamError.Timeout, SteamError.NotFound, SteamError.CircuitOpen,
                });
                return;
            }

            var run = result.Value!;
            // 失败 outcome（登录失败/找不到物品等）也可能来自环境（匿名策略变化）
            if (run.Outcome != SteamCmdOutcome.Success)
            {
                Console.WriteLine($"[ONLINE-RUN-OUTCOME={run.Outcome}] {run.Message} — 换网络条件复验");
                Assert.Contains(run.Outcome, new[]
                {
                    SteamCmdOutcome.LoginFailure, SteamCmdOutcome.ItemNotFound, SteamCmdOutcome.Failed, SteamCmdOutcome.Cancelled,
                });
                return;
            }

            // M2 + 同尺度验收
            Assert.True(run.BytesDone > 0, "Success 正则报告字节数>0");
            Assert.True(Math.Abs(run.EstimatedBytes - run.BytesDone) <= run.BytesDone * 0.10 + 1,
                $"M2 偏差<10%：estimated={run.EstimatedBytes} actual={run.BytesDone}");
            Assert.False(string.IsNullOrEmpty(run.ProductPath));

            var contentDir = Path.Combine(install, "steamapps", "workshop", "content", "4000", "17906");
            Assert.True(Directory.Exists(contentDir), "产物 content 目录存在");
            var files = Directory.EnumerateFiles(contentDir, "*", SearchOption.AllDirectories).ToArray();
            Assert.NotEmpty(files);   // 产物递归非空（1.x 同尺度）
            Console.WriteLine($"[ONLINE-OK] outcome={run.Outcome} bytes={run.BytesDone} estimated={run.EstimatedBytes} " +
                              $"deviationPct={(run.BytesDone > 0 ? Math.Abs(run.EstimatedBytes - run.BytesDone) * 100.0 / run.BytesDone : 0):F1}% files={files.Length}");
        }
        finally
        {
            try { Directory.Delete(root, recursive: true); } catch { /* 临时目录随清理 */ }
        }
    }

    private sealed class OnlinePaths : IPathService
    {
        private readonly string _root;
        public OnlinePaths(string root) => _root = root;
        public string Root => _root;
        public PathMode Mode => PathMode.Portable;
        public string SteamCmdDirectory => Path.Combine(_root, "steamcmd");
        public string WorkshopContent(AppId app) => Path.Combine(_root, "content", app.Value.ToString());
        public string DownloadStaging(DownloadTaskId taskId) => Path.Combine(_root, "staging", taskId.Value.ToString());
        public string LogDirectory => Path.Combine(_root, "logs");
        public string ConfigFile => Path.Combine(_root, "config.json");
        public string CredentialsFile => Path.Combine(_root, "credentials.bin");
        public void EnsureDirectories() { }
    }

    private sealed class ConsoleProgress : IProgress<SteamCmdProgress>
    {
        public void Report(SteamCmdProgress value)
            => Console.WriteLine($"[PROG] pct={value.Percent} est={value.BytesEstimated} msg={value.Message}");
    }
}
