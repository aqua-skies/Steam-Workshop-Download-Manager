using System.IO;
using Swdm2.App.Updates;
using Velopack.Locators;
using Xunit;

namespace Swdm2.UiTests.Tests.Updates;

/// <summary>
/// D6.3 真实 releases feed 集成实测（t60 验收"检查+下载+应用升级路径实测"）:
/// - feed=本地 artifacts(t58 双版本索引 0.5.0/0.6.0;SimpleFileSource 内建受理）
/// - TestVelopackLocator 模拟当前安装 0.5.0 → CheckForUpdatesAsync 读 feed
///   得 0.6.0（升级语义：仅向前）
/// - DownloadUpdatesAsync 真包落 packages 目录（74.2MB 全量 nupkg)
/// - ApplyUpdatesAndRestart 不在沙箱调（会退进程+桌面重启；VelopackApp.Run
///   钩子消费=t58 已实测；状态机覆盖见 UpdateServiceTests)
/// feed 为 .gitignore 构建产物：缺失时本测早退（run-only 诚实降级,
/// captain 可用 scripts/pack-velopack.ps1 复现 feed 后复跑）。
/// </summary>
public sealed class VelopackFeedIntegrationTests
{
    /// <summary>向上搜索 artifacts(feed 为 ignored 构建产物，跨 driver 输出层级自适应）。</summary>
    private static readonly string FeedDir = LocateFeed();

    private static string LocateFeed()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var cand = Path.Combine(dir.FullName, "artifacts");
            if (File.Exists(Path.Combine(cand, "RELEASES")))
                return cand;
            dir = dir.Parent;
        }
        return string.Empty;
    }

    [WpfFact]
    public async Task File_Feed_Check_Returns_Upgrade_And_Downloads()
    {
        if (!Directory.Exists(FeedDir))
        {
            // 诚实降级：构架产物 feed 缺失（非代码缺陷）
            Assert.Fail($"feed 缺失={FeedDir};scripts/pack-velopack.ps1 复现");
            return;
        }

        var packages = Path.Combine(Path.GetTempPath(),
            "swdm-t60-packages-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(packages);
        try
        {
            // 模拟当前安装 0.5.0(t58 打包链基线版本）
            var locator = new TestVelopackLocator("Swdm2", "0.5.0", packages);
            var manager = new VelopackUpdateManager(FeedDir, locator);

            Assert.True(manager.IsVelopackInstalled); // locator 生效=升级通道开
            Assert.Equal(new Version(0, 5, 0), manager.CurrentVersion);

            // 检查（读 releases.win.json → 0.6.0 最新版）
            var info = await manager.CheckForUpdatesAsync();
            Assert.NotNull(info);
            Assert.Equal(new Version(0, 6, 0), info!.TargetVersion);

            // 下载（真 nupkg 落 packages 目录）
            await manager.DownloadUpdatesAsync(info);
            var nupkg = Directory.GetFiles(packages, "Swdm2-*.nupkg", SearchOption.TopDirectoryOnly);
            Assert.NotEmpty(nupkg);
        }
        finally
        {
            if (Directory.Exists(packages))
                Directory.Delete(packages, true);
        }
    }
}