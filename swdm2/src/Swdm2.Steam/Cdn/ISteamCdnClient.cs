using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// Workshop 内容传输原语契约（D4.2,spec §3.2 原样）:
/// - ResolveUgcManifestAsync: pubfile→PICS→manifest（-pubfile 路径）;
/// - ResolvePubFileManifestAsync: -ugc 路径（内容 manifest 直达，跳过发布物详情）;
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
}
