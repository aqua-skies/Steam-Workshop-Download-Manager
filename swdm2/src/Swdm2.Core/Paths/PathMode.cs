namespace Swdm2.Core.Paths;

/// <summary>
/// 根目录模式。C3：便携=exe 同级目录（可整目录迁移）；安装=%APPDATA%\SWDM（Velopack 安装位置可迁移）。
/// </summary>
public enum PathMode
{
    /// <summary>便携模式：Root = exe 所在目录，可整目录拷贝迁移。</summary>
    Portable,

    /// <summary>安装模式：Root = %APPDATA%\SWDM。</summary>
    Installed,
}
