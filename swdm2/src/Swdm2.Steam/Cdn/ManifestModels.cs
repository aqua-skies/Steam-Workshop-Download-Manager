using Swdm2.Core.Domain;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// manifest 解析模型（D4.2,spec §3.2 ISteamCdnClient 返回契约）:
/// - ManifestHandle=文件/chunk 列表快照（不可变；下游 D4.3 chunk 下载的输入）;
/// - DirectFileUrl!=null=发布物走 HTTP 直链（file_url 路径，非 depot chunk);
/// - chunk Id/FileHash=SHA-1 十六进制（DepotDownloader dump 同构）。
/// </summary>
public sealed record ManifestHandle(
    uint AppId,
    uint DepotId,
    ulong ManifestGid,
    string? DirectFileUrl,
    IReadOnlyList<ManifestFile> Files,
    ulong TotalUncompressedSize)
{
    /// <summary>是否 HTTP 直链文件（非 chunk 路径；UI/下载层需区分提示）。</summary>
    public bool IsDirectLink => !string.IsNullOrEmpty(DirectFileUrl);
}

public sealed record ManifestFile(
    string FileName,
    ulong TotalSize,
    string FileHashHex,
    IReadOnlyList<ManifestChunk> Chunks);

public sealed record ManifestChunk(
    string ChunkIdHex,      // SHA-1（20B)
    ulong Offset,
    uint CompressedLength,
    uint UncompressedLength);

/// <summary>
/// -pubfile/-ugc 区别提示文案（D4.2 acceptance：UI 提示文案；UI 消费在 D5)。
/// 依据 DepotDownloader 源码 Verified 的两条路径（ContentDownloader/Steam3Session):
/// -pubfile: 发布物详情查询路径（CM UnifiedMessages;集合递归/file_url 直链/hcontent→manifest);
/// -ugc: 内容 manifest 直达（跳过发布物详情；匿名账号不可 RequestUGCDetails 走内容路径）。
/// </summary>
public static class UgcKindHint
{
    public const string PubFile =
        "发布物 ID（-pubfile)：先查询 Steam 创意工坊发布物详情；集合类型会递归展开子项，" +
        "直接链文件（file_url）按 HTTP 直链下载，发布物内容（hcontent）转 manifest 下载。";

    public const string Ugc =
        "内容 ID（-ugc)：直接指向内容的 manifest，跳过发布物详情查询；" +
        "匿名账号也能解析（RequestUGCDetails 需账号，匿名直走内容路径）。";

    public const string Difference =
        "区别：-pubfile 是创意工坊页面发布物 ID（可含集合/直链）；-ugc 是底层内容 manifest gid" +
        "（steamcmd 工坊下载同一路径）。两者最终都可能落到同一 manifest 下载。";
}

/// <summary>发布物摘要（CM UnifiedMessages 详情→稳定 record;集合可递归）。</summary>
public sealed record PubFileSummary(
    ulong PublishedFileId,
    int FileType,
    string? FileName,
    string? FileUrl,
    ulong HContentFile,
    bool IsCollection,
    IReadOnlyList<ulong> ChildIds);
