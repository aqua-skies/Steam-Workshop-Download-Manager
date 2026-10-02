using Swdm2.Core.Paths;

namespace Swdm2.Core.Options;

/// <summary>
/// 路径选项（与 D1.2 PathService 配合）。C7：模式选择非数值参数，无重标定需求。
/// </summary>
public sealed class PathOptions
{
    /// <summary>
    /// 强制模式。null=自动检测（exe 同级 swdm2.portable 标记 → Portable，否则 Installed，D1.2 语义）；
    /// 显式值=强制覆盖（设置页 D5.8 写入）。
    /// 注：契约摘要写作 PathMode，此处用可空表达"未强制"——null 是唯一诚实的默认态。
    /// </summary>
    public PathMode? ForceMode { get; set; }

    /// <summary>自定义 Root（绝对路径；null=按模式取默认：便携=exe 同级，安装=%APPDATA%\SWDM）。</summary>
    public string? CustomRoot { get; set; }
}
