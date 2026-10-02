using Swdm2.Core.Domain;
using Swdm2.Core.Paths;

namespace Swdm2.Core.Tests.Paths;

/// <summary>
/// D1.2 路径服务验收：便携=exe 同级 / 安装=%APPDATA%；路径绝对化；切换模式隔离。
/// C3：Root 一经构造确定、运行期不可变；getter 纯函数（无目录 I/O 副作用——EnsureDirectories 是显式一次性动作）。
/// </summary>
public sealed class PathServiceTests
{
    [Fact]
    public void Portable_Mode_Root_Is_Exe_Sibling()
    {
        var svc = new PathService(PathMode.Portable, rootOverride: null);
        Assert.Equal(Path.GetFullPath(AppContext.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar), svc.Root);
        Assert.Equal(PathMode.Portable, svc.Mode);
    }

    [Fact]
    public void Installed_Mode_Root_Is_AppData_Swdm()
    {
        var svc = new PathService(PathMode.Installed, rootOverride: null);
        var expected = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SWDM");
        Assert.Equal(expected, svc.Root);
        Assert.Equal(PathMode.Installed, svc.Mode);
    }

    [Fact]
    public void WorkshopContent_SCA_Structure()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            var content = svc.WorkshopContent(new AppId(440));
            Assert.Equal(Path.Combine(temp, "steamcmd", "steamapps", "workshop", "content", "440"), content);
        }
        finally { Cleanup(temp); }
    }

    [Fact]
    public void DownloadStaging_Is_Per_Task_And_Deterministic()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            var a = DownloadTaskId.New();
            var b = DownloadTaskId.New();
            var stageA = svc.DownloadStaging(a);
            Assert.Equal(Path.Combine(temp, "downloads", "staging", a.Value.ToString("N")), stageA);
            Assert.NotEqual(stageA, svc.DownloadStaging(b));
            Assert.Equal(stageA, svc.DownloadStaging(a)); // 纯函数：同任务同结果
        }
        finally { Cleanup(temp); }
    }

    [Fact]
    public void SteamCmd_Logs_Config_Paths_Are_Under_Root()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            Assert.Equal(Path.Combine(temp, "steamcmd"), svc.SteamCmdDirectory);
            Assert.Equal(Path.Combine(temp, "logs"), svc.LogDirectory);
            Assert.Equal(Path.Combine(temp, "config.json"), svc.ConfigFile);
        }
        finally { Cleanup(temp); }
    }

    /// <summary>验收判据：所有公开路径绝对化（IsPathRooted）且无尾部分隔符。</summary>
    [Fact]
    public void All_Paths_Are_Absolute_Without_Trailing_Separator()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            Assert.True(Path.IsPathRooted(svc.Root));
            Assert.True(Path.IsPathRooted(svc.SteamCmdDirectory));
            Assert.True(Path.IsPathRooted(svc.LogDirectory));
            Assert.True(Path.IsPathRooted(svc.ConfigFile));
            Assert.True(Path.IsPathRooted(svc.WorkshopContent(new AppId(440))));
            Assert.True(Path.IsPathRooted(svc.DownloadStaging(DownloadTaskId.New())));
            Assert.False(svc.Root.EndsWith(Path.DirectorySeparatorChar));
        }
        finally { Cleanup(temp); }
    }

    /// <summary>验收判据：切换模式 → 不同实例、Root 隔离（不互相污染）。</summary>
    [Fact]
    public void Mode_Switch_Isolates_Roots()
    {
        var portableRoot = Path.Combine(Path.GetTempPath(), "swdm2_test_p");
        var installedRoot = Path.Combine(Path.GetTempPath(), "swdm2_test_i");
        try
        {
            var portable = new PathService(PathMode.Portable, rootOverride: portableRoot);
            var installed = new PathService(PathMode.Installed, rootOverride: installedRoot);
            Assert.NotEqual(portable.Root, installed.Root);
            Assert.Equal(portableRoot, portable.Root);
            Assert.Equal(installedRoot, installed.Root);
            Assert.Equal(PathMode.Portable, portable.Mode);
            Assert.Equal(PathMode.Installed, installed.Mode);
        }
        finally
        {
            Cleanup(portableRoot);
            Cleanup(installedRoot);
        }
    }

    /// <summary>C3：Root 构造后不可变（重复读取同值）。</summary>
    [Fact]
    public void Root_Is_Stable_Across_Reads()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            var first = svc.Root;
            Assert.Equal(first, svc.Root);
            Assert.Equal(first, svc.Root);
        }
        finally { Cleanup(temp); }
    }

    [Fact]
    public void EnsureDirectories_Creates_Standard_Dirs_Idempotently()
    {
        var svc = CreateInTempDir(out var temp);
        try
        {
            Assert.False(Directory.Exists(svc.LogDirectory));
            svc.EnsureDirectories(); // 第一次：创建
            Assert.True(Directory.Exists(svc.Root));
            Assert.True(Directory.Exists(svc.SteamCmdDirectory));
            Assert.True(Directory.Exists(Path.Combine(svc.Root, "downloads", "staging")));
            Assert.True(Directory.Exists(svc.LogDirectory));
            svc.EnsureDirectories(); // 幂等：不抛
        }
        finally { Cleanup(temp); }
    }

    [Fact]
    public void Detect_Portable_Marker_File_Controls_Mode()
    {
        var exeDir = AppContext.BaseDirectory;
        var marker = Path.Combine(exeDir, "swdm2.portable");
        var existed = File.Exists(marker);
        try
        {
            File.WriteAllText(marker, "portable");
            Assert.Equal(PathMode.Portable, PathService.Detect().Mode);

            File.Delete(marker);
            Assert.Equal(PathMode.Installed, PathService.Detect().Mode);
        }
        finally
        {
            if (!existed && File.Exists(marker)) File.Delete(marker);
        }
    }

    private static IPathService CreateInTempDir(out string temp)
    {
        temp = Path.Combine(Path.GetTempPath(), "swdm2_d12_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        return new PathService(PathMode.Portable, rootOverride: temp);
    }

    private static void Cleanup(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true); } catch { }
    }
}
