using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// Workshop 内容传输原语契约（D4.2/D4.3,spec §3.2 原样）:
/// - ResolveUgcManifestAsync: pubfile→PICS→manifest（-pubfile 路径）;
/// - ResolvePubFileManifestAsync: -ugc 路径（内容 manifest 直达，跳过发布物详情）;
/// - DownloadChunksAsync: chunk 级并行下载+SHA/Adler 强校验+损坏重下（D4.3);
/// 失败=Result.Fail（同 D2.3/D3.3/D4.1 风格，不抛）。
/// </summary>
public interface ISteamCdnClient
{
    /// <summary>-pubfile 路径：发布物详情→(集合/直链/hcontent)→PICS 选 depot→manifest 文件/chunk 列表。</summary>
    Task<Result<ManifestHandle, SteamError>> ResolveUgcManifestAsync(
        AppId app, PublishedFileId pubfile, CancellationToken ct = default);

    /// <summary>-ugc 路径：内容 manifest gid 直达（PICS 选 workshop depot→manifest）。</summary>
    Task<Result<ManifestHandle, SteamError>> ResolvePubFileManifestAsync(
        AppId app, UgcId ugcId, CancellationToken ct = default);

    /// <summary>
    /// chunk 并行下载（D4.3):并发上限=构造注入（Options 来源，⚠️[参数待重标定]）真实生效；
    /// 每 chunk=解密+长度+Adler32 三重校验，损坏→InvalidChecksum 重下（上限 MaxChunkRetries);
    /// 单 chunk 重试耗尽→该项枚举为 Result.Fail（InvalidChecksum)，其余继续。
    /// </summary>
    IAsyncEnumerable<Result<ChunkResult, SteamError>> DownloadChunksAsync(
        ManifestHandle manifest, CancellationToken ct = default);
}
