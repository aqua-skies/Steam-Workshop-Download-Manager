using Swdm2.Core.Domain;

namespace Swdm2.Core.Paths;

/// <summary>
/// 路径服务契约（§3.1.1）：全部路径绝对化；计算为纯函数（无锁、无 I/O 副作用）。
/// C3：Root 一经启动确定，运行期不可变；目录创建见 <see cref="EnsureDirectories"/>。
/// </summary>
public interface IPathService
{
    /// <summary>根目录（绝对路径，无尾部分隔符）。便携=exe 同级；安装=%APPDATA%\SWDM。</summary>
    string Root { get; }

    /// <summary>模式（Portable / Installed），运行期不可变。</summary>
    PathMode Mode { get; }

    /// <summary>steamcmd 安装目录：<c>&lt;Root&gt;/steamcmd</c>。</summary>
    string SteamCmdDirectory { get; }

    /// <summary>Workshop 内容目录：<c>&lt;Root&gt;/steamcmd/steamapps/workshop/content/&lt;appid&gt;</c>（与 SCA/1.x 同构）。</summary>
    string WorkshopContent(AppId app);

    /// <summary>未完成下载的暂存区（含 .download 尾部元数据文件）： <c>&lt;Root&gt;/downloads/staging/&lt;taskId&gt;</c>。</summary>
    string DownloadStaging(DownloadTaskId taskId);

    /// <summary>日志目录：<c>&lt;Root&gt;/logs</c>。</summary>
    string LogDirectory { get; }

    /// <summary>配置文件路径：<c>&lt;Root&gt;/config.json</c>。</summary>
    string ConfigFile { get; }

    /// <summary>启动期一次性创建 Root 及其标准子目录（steamcmd / downloads/staging / logs）。幂等。</summary>
    void EnsureDirectories();
}
