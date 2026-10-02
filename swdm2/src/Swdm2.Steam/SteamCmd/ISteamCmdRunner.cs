using Swdm2.Core.Domain;
using Swdm2.Core.Logging;
using Swdm2.Core.Paths;
using Swdm2.Core.Results;

namespace Swdm2.Steam.SteamCmd;

/// <summary>
/// steamcmd runner 契约（D3.4，1.x steamcmd_engine.py 移植）：
/// 批拼命令（+force_install_dir +login anonymous +workshop_download_item [+validate] +quit）
/// + 1.x 正则成功三元判定 + Sweep 校验 + 失败清空目录 + stdin 关闭
/// + 三段式收割看门狗（输出停滞+磁盘停滞→终止；取消→杀全树；自然退出）+ 输出脱敏（Core D1.5）。
/// </summary>
public interface ISteamCmdRunner
{
    /// <summary>
    /// 下载单个工坊物品（阻塞至进程退出；D3.5 provider 按队列驱动）。
    /// 成功判定=三元（Success 正则匹配 **且** Sweep 产物目录递归非空 **且** 退出码 ∈ {0,7}）。
    /// 失败=清空该物品 content+downloads 目录（防半成品残留；1.x 重下幂等同义）。
    /// </summary>
    Task<Result<SteamCmdRunResult, SteamError>> DownloadAsync(SteamCmdRunRequest request,
        IProgress<SteamCmdProgress>? progress = null, CancellationToken ct = default,
        ISteamCmdLineObserver? observer = null);
}

/// <summary>运行请求（不可变）。</summary>
public sealed record SteamCmdRunRequest(
    PublishedFileId ItemId,
    AppId App,
    string ExePath,
    string InstallDir,
    long TotalHintBytes = 0,
    bool Validate = false,
    string? Username = null,
    string? Password = null,
    string? GuardCode = null)
{
    /// <summary>匿名模式判定（1.x 语义：anonymous 或无用户名）。</summary>
    public bool IsAnonymous => string.IsNullOrEmpty(Username);
}

/// <summary>运行结果（1.x DownloadResult 对应）。</summary>
public sealed record SteamCmdRunResult(
    SteamCmdOutcome Outcome,
    string ProductPath,
    long BytesDone,          // Success 正则报告的字节数（真值）
    long EstimatedBytes,     // 完成点 Sweep 估算字节（M2：与 BytesDone 偏差&lt;10%）
    string Message,
    double ElapsedSeconds);

public enum SteamCmdOutcome { Success, LoginFailure, ItemNotFound, Failed, Cancelled, StallKilled }

/// <summary>实时进度报告（1.x on_progress 对应；-1 百分比=不确定）。</summary>
public sealed record SteamCmdProgress(int Percent, long BytesEstimated, string Message);

/// <summary>
/// runner 级可观测接口（D3.5 provider 节流信号桥接预留；1.x on_throttle_signal 同义）。
/// </summary>
public interface ISteamCmdLineObserver
{
    void OnLine(string redactedLine);
    void OnThrottleSignal(string kind, string line);
}
