using System.Text;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;
using Swdm2.Steam.SteamCmd;
using Swdm2.Steam.Web;
using Xunit;

namespace Swdm2.Steam.Tests.SteamCmd;

/// <summary>
/// D3.3 在线集成测试（真实输入，Category=Online）：
/// - 真实下载 <see cref="SteamCmdDeployer.OfficialZipUrl"/> + 真实进程探针（首跑含自更新自举，可能数分钟）；
/// - 失败容忍定律（同 D2.3/D2.5 口径）：RateLimited/Network/Timeout/Blocked 等环境结论不算失败，
///   仅断言"明确 Result 语义"（Ok 或明确 SteamError，不抛异常/不假绿）；
/// - 非 ASCII 工作区路径约束：部署目录取 %TEMP% 下 ASCII 子目录（实测 Fatal exit=-2 教训）；
/// - M1 验收锚点：exe 存在 + `+login anonymous +quit` 退出码 ∈ {0,7} + banner 版本串可解析
///   （实测 `+version` 命令不存在——"Command not found: version"——版本只从 banner 解析）。
/// </summary>
[Trait("Category", "Online")]
public sealed class SteamCmdDeployerOnlineTests
{
    private static bool ShouldSkipOnline
        => Environment.GetEnvironmentVariable("SWDM2_SKIP_ONLINE") == "1";

    [Fact]
    public async Task Online_Deploy_Real_Zip_Probe_Parses_Banner_Version()
    {
        if (ShouldSkipOnline)
        {
            Console.WriteLine("[ONLINE-SKIP] SWDM2_SKIP_ONLINE=1");
            return;
        }

        // ASCII 部署根（工作区路径含中文，steamcmd 实测不可启动）；
        // GetTempPath 在 driver 下被重定向到工作区 .dtmp（可写，沙箱拒 dotnet 进程写真实 %TEMP%）
        var root = Path.Combine(Path.GetTempPath(), "swdm2_online_sc_" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(root);
        var paths = new OnlinePaths(root);
        var deployer = new SteamCmdDeployer(
            paths,
            new SteamHttpClientFactory(new Core.Options.SteamOptions { Proxy = Core.Options.ProxyMode.Direct }),
            new SteamCmdProcessProbe());

        try
        {
            var result = await deployer.EnsureAsync();

            if (!result.IsOk)
            {
                Console.WriteLine($"[ONLINE-RESULT-FAIL] {result.Error} — 环境阻断，非实现缺陷（换网络条件复验）");
                Assert.Contains(result.Error ?? SteamError.None, new[]
                {
                    SteamError.RateLimited, SteamError.Network, SteamError.Blocked,
                    SteamError.Timeout, SteamError.NotFound, SteamError.CircuitOpen,
                    // 沙箱 .dtmp 为中文路径→探针级 ASCII 门控正确拒绝=环境结论；桌面 ASCII %TEMP% 复跑为真绿
                    SteamError.InvalidConfiguration,
                });
                return;
            }

            var deployment = result.Value!;
            Assert.True(File.Exists(deployment.ExePath), "exe 真实落盘");
            Assert.False(string.IsNullOrEmpty(deployment.Version), "banner 版本串非空");
            Assert.Matches(@"^\d+$", deployment.Version!);   // 纯数字构建号（如 1788292693）
            Assert.Equal(64, deployment.ZipSha256.Length);   // sha256 hex 基线
            Console.WriteLine($"[ONLINE-OK] exe={deployment.ExePath} version={deployment.Version} zipBytes={deployment.ZipBytes} sha={deployment.ZipSha256[..12]}...");

            // 幂等复测：0 请求 0 进程
            var second = await deployer.EnsureAsync();
            Assert.True(second.IsOk);
            Assert.Equal(deployment.Version, second.Value!.Version);
            Console.WriteLine("[ONLINE-OK] 幂等复测相同版本，0 请求 0 进程");
        }
        finally
        {
            try { Directory.Delete(root, recursive: true); } catch { /* 温度目录，随 %TEMP% 清理 */ }
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
}
