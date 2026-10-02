using Swdm2.Core.Results;

namespace Swdm2.Steam.SteamCmd;

/// <summary>
/// steamcmd 部署器契约（D3.3）：
/// - zip 下载（走 D2.1 IHttpClientFactory+指纹头）+ 解压 + exe 校验；
/// - **幂等**：已部署且指纹基线一致时直接返回，不重复网络/进程操作；
/// - 校验语义（M1 定案，2026-10-02 实证锚定）：
///   ① exe 存在；
///   ② 运行 `steamcmd.exe +login anonymous +quit` 退出码 ∈ {0, 7}（7=自更新后重启语义，实测）；
///   ③ **版本串可解析**：banner 行 `Steam Console Client (c) Valve Corporation - version &lt;数字&gt;`
///     （实测 `+version` 命令不存在——"Command not found: version"——版本只能从 banner 解析）；
///   ④ 哈希=**自记录基线**（Valve 不发布 steamcmd.zip 官方签名）：
///      首次部署成功后把 zip sha256/版本/字节写入 `steamcmd.fingerprint.json`，
///      二次部署比对——防二次下载的 zip 被掉包/损坏，**不是**权威完整性验证。
/// - 已知环境约束（实测 2026-10-02）：
///   steamcmd.exe **不能从含非 ASCII 字符的路径启动**（Fatal Error exit=-2，
///   "cannot run from a folder path that includes non-English characters"）。
///   门控在 <see cref="ISteamCmdVersionProbe"/> 真实探针级（不启动进程→InvalidConfiguration）；
///   沙箱无 ASCII 可写目录时桩探针路径不受影响（约束本质=真进程启动行为）。
/// </summary>
public interface ISteamCmdDeployer
{
    /// <summary>
    /// 确保 steamcmd 已部署并可用（幂等）。失败语义 Fail 而非抛异常（D2.3 同构）。
    /// 成功返回部署信息（exe 路径 + 解析到的版本串 + zip sha256 基线）。
    /// </summary>
    Task<Result<SteamCmdDeployment, SteamError>> EnsureAsync(CancellationToken ct = default);

    /// <summary>当前部署状态（不发请求、不启动进程；供 UI 展示/探测）。</summary>
    SteamCmdDeployment? Current { get; }
}

/// <summary>部署结果（不可变记录；字段为自记录基线值，非权威签名）。</summary>
public sealed record SteamCmdDeployment(
    string ExePath,
    string Version,
    string ZipSha256,
    long ZipBytes,
    DateTimeOffset RecordedAtUtc);
