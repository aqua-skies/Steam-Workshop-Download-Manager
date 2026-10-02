namespace Swdm2.Core.Results;

/// <summary>
/// 下载域错误码。InvalidChecksum 是 chunk 校验失败（D4.3，重下而非续传）；
/// RangeNotSupported 是服务器不支持分段（D4.5 回退单流）。
/// </summary>
public enum DownloadError
{
    /// <summary>无错误（不应表示成功；成功走 Result.Ok）。</summary>
    None,

    /// <summary>provider 执行失败（链回退已尝试或不可回退，D4.4）。</summary>
    ProviderFailed,

    /// <summary>chunk SHA 校验失败（D4.3 重下）。</summary>
    InvalidChecksum,

    /// <summary>磁盘空间不足（D4.6 稀疏占位前置检查）。</summary>
    DiskSpace,

    /// <summary>服务器不支持 Range 分段（回退单流，D4.5）。</summary>
    RangeNotSupported,

    /// <summary>用户取消（杀进程路径 D3.4 看门狗）。</summary>
    Cancelled,

    /// <summary>分段写入失败（偏移直写/稀疏文件问题，D4.6）。</summary>
    PartialWriteFailed,

    /// <summary>manifest 解析失败（pubfile→PICS→manifest 链路，D4.2）。</summary>
    ManifestResolution,

    /// <summary>steamcmd 三元判定失败（成功/假成功被拒，D3.4）。</summary>
    SteamCmdFailed,

    /// <summary>任务状态非法转移（D3.1 状态表断言）。</summary>
    IllegalTransition,
}
