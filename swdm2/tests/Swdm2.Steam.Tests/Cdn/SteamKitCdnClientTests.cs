using SteamKit2;
using SteamKit2.CDN;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Steam.Cdn;
using Xunit;

namespace Swdm2.Steam.Tests.Cdn;

/// <summary>
/// D4.2 manifest 解析与 isUgc 路径验收（离线=注入 seam 链全断言）:
/// - depot 选择（workshopdepot/缺省）;DepotManifest→ManifestHandle 映射（SHA-1 hex)
/// - pubfile 链路三分支（直链 file_url/集合/hcontent→manifest)
/// - 故障类映射（无 key→AuthRequired;无服务器/manifest→Network 等）
/// - -pubfile/-ugc 区别文案（UI 提示 acceptance）
/// 真链（CM 阻断=环境容忍）见 SteamKitCdnClientOnlineTests。
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SteamKitCdnClientTests
{
    private static readonly byte[] ChunkSha = { 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14 };

    // ---------- workshop depot 选择（CR 对照 ContentDownloader) ----------

    [Fact]
    public void WorkshopDepot_Selection_Prefers_Workshopdepot()
    {
        var depots = new KeyValue("depots");
        depots.Children.Add(new KeyValue("workshopdepot") { Value = "4001" });
        Assert.Equal(4001u, SteamKitCdnClient.SelectWorkshopDepot(depots, 4000u));
    }

    [Fact]
    public void WorkshopDepot_Selection_Falls_Back_To_AppId_When_Missing()
    {
        var depots = new KeyValue("depots");
        depots.Children.Add(new KeyValue("branches") { Value = "public" }); // 无 workshopdepot
        Assert.Equal(4000u, SteamKitCdnClient.SelectWorkshopDepot(depots, 4000u));
    }
    [Fact]
    public void WorkshopDepot_Selection_Null_Depots_Returns_AppId()
        => Assert.Equal(4000u, SteamKitCdnClient.SelectWorkshopDepot(null, 4000u));

    // ---------- DepotManifest → ManifestHandle 映射 ----------

    [Fact]
    public void MapManifest_Produces_File_And_Chunk_List_With_Sha_Hex()
    {
        var manifest = new DepotManifest
        {
            Files =
            [
                new DepotManifest.FileData("maps/kfc.bsp", filenameHash: [], (EDepotFileFlag)0, size: 1234, hash: ChunkSha, linkTarget: string.Empty, encrypted: false, numChunks: 2) { Chunks =
                    [
                        new DepotManifest.ChunkData(id: ChunkSha, checksum: 0, offset: 0, comp_length: 100, uncomp_length: 200),
                        new DepotManifest.ChunkData(id: ChunkSha, checksum: 0, offset: 200, comp_length: 300, uncomp_length: 1034),
                    ]
                }
            ],
            TotalUncompressedSize = 1234
        };

        var handle = SteamKitCdnClient.MapManifest(manifest, appId: 4000, depotId: 4001, gid: 8888888, fileUrl: null);

        Assert.Equal(4000u, handle.AppId);
        Assert.Equal(4001u, handle.DepotId);
        Assert.Equal(8888888UL, handle.ManifestGid);
        Assert.False(handle.IsDirectLink);
        Assert.Equal(1234UL, handle.TotalUncompressedSize);
        var file = Assert.Single(handle.Files);
        Assert.Equal("maps\\kfc.bsp", file.FileName); // FileData 路径归一化（/→\)——SteamKit 行为实证
        Assert.Equal(1234UL, file.TotalSize);
        Assert.Equal("0102030405060708090a0b0c0d0e0f1011121314", file.FileHashHex);
        Assert.Equal(2, file.Chunks.Count);
        Assert.Equal("0102030405060708090a0b0c0d0e0f1011121314", file.Chunks[0].ChunkIdHex);
        Assert.Equal(200u, file.Chunks[0].UncompressedLength);
        Assert.Equal(1034u, file.Chunks[1].UncompressedLength);
    }

    // ---------- ResolveUgcManifestAsync 链路（全 seam 桩） ----------

    private sealed class SeamChain
    {
        public Func<ulong, uint, CancellationToken, Task<PubFileSummary?>> Details { get; set; } = null!;
        public Func<uint, CancellationToken, Task<KeyValue?>> AppDepots { get; set; } = null!;
        public Func<uint, uint, CancellationToken, Task<byte[]?>> DepotKey { get; set; } = null!;
        public Func<uint, uint, ulong, CancellationToken, Task<ulong>> ManifestRequestCode { get; set; } = null!;
        public Func<uint, uint, string?, CancellationToken, Task<string?>> CdnAuth { get; set; } = null!;
        public Func<uint, ulong, ulong, byte[]?, string?, Server?, CancellationToken, Task<DepotManifest?>> DownloadManifest { get; set; } = null!;
        public Func<uint, CancellationToken, Task<Server?>> Server { get; set; } = null!;
    }

    private static KeyValue CreateDepotsWithWorkshop(uint workshopDepot)
    {
        var depots = new KeyValue("depots");
        depots.Children.Add(new KeyValue("workshopdepot") { Value = workshopDepot.ToString() });
        return depots;
    }

    private static SteamKitCdnClient CreateClient(SeamChain seam)
    {
        var session = new SteamKitSessionManager();
        var client = new SteamKitCdnClient(session)
        {
            DetailsFunc = seam.Details,
            AppDepotsFunc = seam.AppDepots,
            DepotKeyFunc = seam.DepotKey,
            ManifestRequestCodeFunc = seam.ManifestRequestCode,
            CdnAuthFunc = seam.CdnAuth,
            DownloadManifestFunc = seam.DownloadManifest,
            ServerFunc = seam.Server
        };
        return client;
    }

    private static SeamChain GreenChain()
        => new()
        {
            Details = (_, _, _) => Task.FromResult<PubFileSummary?>(
                new PubFileSummary(3808352517, 0, null, null, 99999999, false, [])),
            AppDepots = (_, _) => Task.FromResult<KeyValue?>(CreateDepotsWithWorkshop(4001)),
            DepotKey = (_, _, _) => Task.FromResult<byte[]?>(new byte[32]),
            ManifestRequestCode = (_, _, _, _) => Task.FromResult(777UL),
            CdnAuth = (_, _, _, _) => Task.FromResult<string?>("token"),
            Server = (_, _) => Task.FromResult<Server?>(new Server()), // 桩：server 非空即可（下载桩不消费）
            DownloadManifest = (_, _, _, _, _, _, _) =>
            {
                var dm = new DepotManifest
                {
                    Files = [new DepotManifest.FileData("addon.txt", filenameHash: [], (EDepotFileFlag)0, size: 10, hash: ChunkSha, linkTarget: string.Empty, encrypted: false, numChunks: 1) {
                        Chunks = [new DepotManifest.ChunkData(id: ChunkSha, checksum: 0, offset: 0, comp_length: 5, uncomp_length: 10)] }],
                    TotalUncompressedSize = 10
                };
                return Task.FromResult<DepotManifest?>(dm);
            }
        };

    /// <summary>-pubfile 全链绿（hcontent→manifest):文件/chunk 列表+depot=workshopdepot。</summary>
    [Fact]
    public async Task Resolve_Pubfile_Green_Chain_Returns_Files_And_Chunks()
    {
        var client = CreateClient(GreenChain());

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(3808352517));

        Assert.True(result.IsOk);
        Assert.Equal(4001u, result.Value!.DepotId);
        Assert.Equal(99999999UL, result.Value.ManifestGid);
        Assert.False(result.Value.IsDirectLink);
        var file = Assert.Single(result.Value.Files);
        Assert.Equal("addon.txt", file.FileName);
        Assert.Single(file.Chunks);
    }

    /// <summary>file_url 直链分支=IsDirectLink 句柄（零 chunk)。</summary>
    [Fact]
    public async Task Resolve_Pubfile_Direct_File_Url_Returns_Direct_Link()
    {
        var seam = GreenChain();
        seam.Details = (_, _, _) => Task.FromResult<PubFileSummary?>(
            new PubFileSummary(3808352517, 0, "addon.txt", "https://cdn.steamcontent.com/kfc.txt", 0, false, []));
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(3808352517));

        Assert.True(result.IsOk);
        Assert.True(result.Value!.IsDirectLink);
        Assert.Equal("https://cdn.steamcontent.com/kfc.txt", result.Value.DirectFileUrl);
        Assert.Empty(result.Value.Files);
    }

    /// <summary>集合类型=单物契约不支持→InvalidConfiguration（集合扩展属下载层递归域）。</summary>
    [Fact]
    public async Task Resolve_Pubfile_Collection_Returns_InvalidConfiguration()
    {
        var seam = GreenChain();
        seam.Details = (_, _, _) => Task.FromResult<PubFileSummary?>(
            new PubFileSummary(1, (int)SteamKit2.EWorkshopFileType.Collection, null, null, 0, true, [2, 3]));
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.False(result.IsOk);
        Assert.Equal(SteamError.InvalidConfiguration, result.Error);
    }

    /// <summary>无 hcontent 且无 file_url=无法定位→InvalidConfiguration。</summary>
    [Fact]
    public async Task Resolve_Pubfile_No_Content_Location_Returns_InvalidConfiguration()
    {
        var seam = GreenChain();
        seam.Details = (_, _, _) => Task.FromResult<PubFileSummary?>(
            new PubFileSummary(1, 0, null, null, 0, false, []));
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.InvalidConfiguration, result.Error);
    }

    /// <summary>详情查询失败/null→Network。</summary>
    [Fact]
    public async Task Resolve_Pubfile_Details_Failure_Returns_Network()
    {
        var seam = GreenChain();
        seam.Details = (_, _, _) => Task.FromResult<PubFileSummary?>(null);
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.Network, result.Error);
    }

    /// <summary>depot 密钥缺失→AuthRequired（匿名无权）。</summary>
    [Fact]
    public async Task Resolve_No_Depot_Key_Returns_AuthRequired()
    {
        var seam = GreenChain();
        seam.DepotKey = (_, _, _) => Task.FromResult<byte[]?>(null);
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    /// <summary>manifest request code=0→AuthRequired（旧 manifest 匿名不可得，CR 同义）。</summary>
    [Fact]
    public async Task Resolve_No_Manifest_Request_Code_Returns_AuthRequired()
    {
        var seam = GreenChain();
        seam.ManifestRequestCode = (_, _, _, _) => Task.FromResult(0UL);
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.AuthRequired, result.Error);
    }

    /// <summary>无 CDN 服务器→Network。</summary>
    [Fact]
    public async Task Resolve_No_Cdn_Server_Returns_Network()
    {
        var seam = GreenChain();
        seam.Server = (_, _) => Task.FromResult<Server?>(null);
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.Network, result.Error);
    }

    /// <summary>manifest 下载失败→Network。</summary>
    [Fact]
    public async Task Resolve_Manifest_Download_Failure_Returns_Network()
    {
        var seam = GreenChain();
        seam.DownloadManifest = (_, _, _, _, _, _, _) => Task.FromResult<DepotManifest?>(null);
        var client = CreateClient(seam);

        var result = await client.ResolveUgcManifestAsync(new AppId(4000), new PublishedFileId(1));

        Assert.Equal(SteamError.Network, result.Error);
    }

    /// <summary>-ugc 路径：直发 manifest（跳过详情凭证链）。</summary>
    [Fact]
    public async Task Resolve_Ugc_Path_Skips_Details()
    {
        var detailsCalled = false;
        var seam = GreenChain();
        seam.Details = (_, _, _) => { detailsCalled = true; return Task.FromResult<PubFileSummary?>(null); };
        var client = CreateClient(seam);

        var result = await client.ResolvePubFileManifestAsync(new AppId(4000), new UgcId(99999999));

        Assert.True(result.IsOk);
        Assert.False(detailsCalled); // ugc 路径不经详情
        Assert.Equal(4001u, result.Value!.DepotId);
    }

    /// <summary>-pubfile/-ugc 区别文案（UI 提示 acceptance）。</summary>
    [Fact]
    public void Ugc_Kind_Hint_Texts_Describe_Path_Difference()
    {
        Assert.All(new[] { UgcKindHint.PubFile, UgcKindHint.Ugc, UgcKindHint.Difference },
            text => Assert.False(string.IsNullOrWhiteSpace(text)));
        Assert.Contains("pubfile", UgcKindHint.PubFile);
        Assert.Contains("manifest", UgcKindHint.PubFile);
        Assert.Contains("ugc", UgcKindHint.Ugc);
        Assert.Contains("manifest", UgcKindHint.Ugc);
        Assert.Contains("pubfile", UgcKindHint.Difference);
        Assert.Contains("ugc", UgcKindHint.Difference);
    }
}
