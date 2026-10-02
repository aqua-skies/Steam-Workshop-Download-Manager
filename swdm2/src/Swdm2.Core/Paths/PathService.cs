using System.Globalization;
using Swdm2.Core.Domain;

namespace Swdm2.Core.Paths;

/// <summary>
/// 路径服务实现（C3/C1：构造时确定 Root 与 Mode，getter 纯函数、无锁、无 I/O）。
/// 检测规则（启动时一次）：
/// 1. 显式覆盖（自定义 Root/测试注入）优先；
/// 2. exe 同级存在便携标记文件 <c>swdm2.portable</c> → Portable；
/// 3. 其余 → Installed（Velopack 安装位置可迁移，数据独立于 exe）。
/// </summary>
public sealed class PathService : IPathService
{
    private const string PortableMarkerFileName = "swdm2.portable";
    private const string AppFolderName = "SWDM";

    /// <summary>Root（绝对路径，尾部分隔符已去除）。构造时锁定（C3）。</summary>
    public string Root { get; }

    public PathMode Mode { get; }

    public string SteamCmdDirectory => Path.Combine(Root, "steamcmd");

    public string LogDirectory => Path.Combine(Root, "logs");

    public string ConfigFile => Path.Combine(Root, "config.json");

    public PathService(PathMode mode, string? rootOverride = null)
    {
        Mode = mode;
        Root = NormalizeRoot(rootOverride ?? GetDefaultRoot(mode));
    }

    /// <summary>按 exe 同级便携标记自动检测模式（App 启动入口使用）。</summary>
    public static PathService Detect(string? rootOverride = null)
    {
        if (rootOverride is not null)
            return new PathService(PathMode.Portable, rootOverride);

        var exeDir = AppContext.BaseDirectory;
        var markerExists = File.Exists(Path.Combine(exeDir, PortableMarkerFileName));
        return new PathService(markerExists ? PathMode.Portable : PathMode.Installed);
    }

    public string WorkshopContent(AppId app)
        => Path.Combine(SteamCmdDirectory, "steamapps", "workshop", "content",
                        app.Value.ToString(CultureInfo.InvariantCulture));

    public string DownloadStaging(DownloadTaskId taskId)
        => Path.Combine(Root, "downloads", "staging",
                        taskId.Value.ToString("N", CultureInfo.InvariantCulture));

    /// <summary>启动期一次性创建标准目录。幂等（已存在不抛异常）。</summary>
    public void EnsureDirectories()
    {
        Directory.CreateDirectory(Root);
        Directory.CreateDirectory(SteamCmdDirectory);
        Directory.CreateDirectory(Path.Combine(Root, "downloads", "staging"));
        Directory.CreateDirectory(LogDirectory);
    }

    private static string GetDefaultRoot(PathMode mode) => mode switch
    {
        PathMode.Portable => AppContext.BaseDirectory, // C3：exe 同级，可整目录迁移
        PathMode.Installed => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), AppFolderName),
        _ => throw new ArgumentOutOfRangeException(nameof(mode)),
    };

    /// <summary>绝对化 + 去尾部分隔符（验收判据：路径全部绝对化）。</summary>
    private static string NormalizeRoot(string root)
        => Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
}
