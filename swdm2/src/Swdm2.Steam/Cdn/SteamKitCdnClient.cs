using SteamKit2;
using SteamKit2.CDN;
using SteamKit2.Internal;
using Swdm2.Core.Domain;
using Swdm2.Core.Results;

namespace Swdm2.Steam.Cdn;

/// <summary>
/// SteamKit2 CDN 客户端默认实现（D4.2):
/// 链路（CR 对照 DepotDownloader/Steam3Session 源码 Verified,SteamKit 3.4.0 API 实测）:
/// pubfile → CM UnifiedMessages PublishedFile.GetDetails → 集合/直链/hcontent 三分支
///  → PICS accessToken+productInfo 选 workshop depot(depots/workshopdepot,缺省=appId)
///  → GetDepotDecryptionKey → GetManifestRequestCode → GetServersForSteamPipe
///  → GetCDNAuthToken → CDN.Client.DownloadManifestAsync → DepotManifest
///  → 文件/chunk 列表映射（SHA-1 hex)。
/// ugc 路径跳过发布物详情（直发 manifest)。
/// 沙箱 CM 阻断→Network/Timeout 环境容忍标注（同 D3.3/D4.1 Online 门模式）。
/// 测试 seam:每个内部步骤可注入（内部 Func 属性，生产=null=真链）。
/// </summary>
public sealed class SteamKitCdnClient : ISteamCdnClient
{
    /// <summary>⚠️[参数待重标定] CDN 步骤超时（秒）。</summary>
    public const int DefaultTimeoutSeconds = 60; // 1.x 无同栈经验值，先保守（C7 方法学）

    private readonly SteamKitSessionManager _session;
    private readonly int _timeoutSeconds;

    // 测试 seam（生产=null=真链）
    internal Func<ulong, uint, CancellationToken, Task<PubFileSummary?>>? DetailsFunc;
    internal Func<uint, CancellationToken, Task<KeyValue?>>? AppDepotsFunc;
    internal Func<uint, uint, CancellationToken, Task<byte[]?>>? DepotKeyFunc;
    internal Func<uint, uint, ulong, CancellationToken, Task<ulong>>? ManifestRequestCodeFunc;
    internal Func<uint, uint, string?, CancellationToken, Task<string?>>? CdnAuthFunc;
    internal Func<uint, ulong, ulong, byte[]?, string?, Server?, CancellationToken, Task<DepotManifest?>>? DownloadManifestFunc;
    internal Func<uint, CancellationToken, Task<Server?>>? ServerFunc;

    public SteamKitCdnClient(SteamKitSessionManager session, int? timeoutSeconds = null)
    {
        _session = session;
        _timeoutSeconds = timeoutSeconds ?? DefaultTimeoutSeconds;
    }

    public async Task<Result<ManifestHandle, SteamError>> ResolveUgcManifestAsync(
        AppId app, PublishedFileId pubfile, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(app);
        ArgumentNullException.ThrowIfNull(pubfile);
        var appId = (uint)app.Value;

        // 1. 发布物详情（CM UnifiedMessages)
        var details = await (DetailsFunc ?? RealGetDetailsAsync)(pubfile.Value, appId, ct).ConfigureAwait(false);
        if (details is null)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.Network); // 查询失败/无结果

        // 2. 直链分支（file_url)
        if (!string.IsNullOrEmpty(details.FileUrl))
            return Result<ManifestHandle, SteamError>.Ok(
                new ManifestHandle(appId, DepotId: 0, ManifestGid: details.HContentFile,
                    DirectFileUrl: details.FileUrl, Files: Array.Empty<ManifestFile>(),
                    TotalUncompressedSize: 0));

        // 3. 集合=多物递归域（D4.x 下载层职责）；单物契约不支持→明确句柄
        if (details.IsCollection)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.InvalidConfiguration);

        var manifestId = details.HContentFile;
        if (manifestId == 0)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.InvalidConfiguration); // 无法定位 manifest

        return await ResolveManifestAsync(appId, manifestId, ct).ConfigureAwait(false);
    }

    public async Task<Result<ManifestHandle, SteamError>> ResolvePubFileManifestAsync(
        AppId app, UgcId ugcId, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(app);
        ArgumentNullException.ThrowIfNull(ugcId);
        return await ResolveManifestAsync((uint)app.Value, ugcId.Value, ct).ConfigureAwait(false);
    }

    /// <summary>公共尾段：PICS 选 depot→key→code→CDN 服务器→auth→下载 manifest→映射。</summary>
    private async Task<Result<ManifestHandle, SteamError>> ResolveManifestAsync(
        uint appId, ulong manifestId, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();

        var depots = await (AppDepotsFunc ?? RealAppDepotsAsync)(appId, ct).ConfigureAwait(false);
        var depotId = SelectWorkshopDepot(depots, appId);

        var depotKey = await (DepotKeyFunc ?? RealDepotKeyAsync)(depotId, appId, ct).ConfigureAwait(false);
        if (depotKey is null || depotKey.Length == 0)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.AuthRequired);

        var requestCode = await (ManifestRequestCodeFunc ?? RealManifestRequestCodeAsync)(depotId, appId, manifestId, ct)
            .ConfigureAwait(false);
        if (requestCode == 0)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.AuthRequired); // 旧 manifest 匿名不可得

        var server = await (ServerFunc ?? RealSelectServerAsync)(appId, ct).ConfigureAwait(false);
        if (server is null)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.Network);

        var cdnAuth = await (CdnAuthFunc ?? RealCdnAuthAsync)(appId, depotId, server.Host, ct).ConfigureAwait(false);

        var manifest = await (DownloadManifestFunc ?? RealDownloadManifestAsync)(
            depotId, manifestId, requestCode, depotKey, cdnAuth, server, ct).ConfigureAwait(false);
        if (manifest is null)
            return Result<ManifestHandle, SteamError>.Fail(SteamError.Network);

        return Result<ManifestHandle, SteamError>.Ok(MapManifest(manifest, appId, depotId, manifestId, null));
    }

    // ---------- 真链步骤（SteamKit 3.4.0 API surface probed) ----------

    private async Task<PubFileSummary?> RealGetDetailsAsync(ulong pubfile, uint appId, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var service = client.GetHandler<SteamUnifiedMessages>()!.CreateService<PublishedFile>();
        var request = new CPublishedFile_GetDetails_Request { appid = appId, includechildren = true };
        request.publishedfileids.Add(new PublishedFileID(pubfile));
        await using var pump = new CallbackPump(manager);
        var job = service.GetDetails(request);
        job.Timeout = TimeSpan.FromSeconds(60);
        var response = await job;
        return response.Result != EResult.OK ? null
            : response.Body.publishedfiledetails.FirstOrDefault() is { } d ? MapDetails(d) : null;
    }

    private async Task<KeyValue?> RealAppDepotsAsync(uint appId, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var apps = client.GetHandler<SteamApps>()!;
        await using var pump = new CallbackPump(manager);

        var tokenJob = apps.PICSGetAccessTokens(appId, null);
        tokenJob.Timeout = TimeSpan.FromSeconds(_timeoutSeconds);
        var tokens = await tokenJob;

        var request = new SteamApps.PICSRequest(appId);
        if (tokens.AppTokens.TryGetValue(appId, out var token)) request.AccessToken = token;

        var infoJob = apps.PICSGetProductInfo(request, null);
        infoJob.Timeout = TimeSpan.FromSeconds(_timeoutSeconds);
        var info = await infoJob;
        var results = (IReadOnlyList<SteamApps.PICSProductInfoCallback>?)info?.Results
                      ?? Array.Empty<SteamApps.PICSProductInfoCallback>();
        foreach (var result in results)
        {
            if (result.Apps.TryGetValue(appId, out var app) && app != null)
                return app.KeyValues.Children.FirstOrDefault(c => c.Name == "depots");
        }
        return null;
    }

    private async Task<byte[]?> RealDepotKeyAsync(uint depotId, uint appId, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var apps = client.GetHandler<SteamApps>()!;
        await using var pump = new CallbackPump(manager);
        var job = apps.GetDepotDecryptionKey(depotId, appId);
        job.Timeout = TimeSpan.FromSeconds(60);
        var key = await job;
        return key.Result == EResult.OK ? key.DepotKey : null;
    }

    private async Task<string?> RealCdnAuthAsync(uint appId, uint depotId, string? host, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var content = client.GetHandler<SteamContent>()!;
        await using var pump = new CallbackPump(manager);
        var auth = await content.GetCDNAuthToken(appId, depotId, host ?? string.Empty)
            .WaitAsync(TimeSpan.FromSeconds(60), ct).ConfigureAwait(false);
        return auth.Result == EResult.OK ? auth.Token : null;
    }

    private async Task<Server?> RealSelectServerAsync(uint appId, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var content = client.GetHandler<SteamContent>()!;
        await using var pump = new CallbackPump(manager);
        var servers = await content.GetServersForSteamPipe(null, 20)
            .WaitAsync(TimeSpan.FromSeconds(60), ct).ConfigureAwait(false);
        return servers.FirstOrDefault(s =>
            s.Protocol.ToString().Contains("Http", StringComparison.OrdinalIgnoreCase));
    }

    private async Task<ulong> RealManifestRequestCodeAsync(uint depotId, uint appId, ulong manifestId, CancellationToken ct)
    {
        var (client, manager) = EnsureSession();
        var content = client.GetHandler<SteamContent>()!;
        await using var pump = new CallbackPump(manager);
        return await content.GetManifestRequestCode(depotId, appId, manifestId, "public")
            .WaitAsync(TimeSpan.FromSeconds(60), ct).ConfigureAwait(false);
    }

    private async Task<DepotManifest?> RealDownloadManifestAsync(
        uint depotId, ulong manifestId, ulong requestCode, byte[]? depotKey, string? cdnAuth,
        Server? server, CancellationToken ct)
    {
        var (client, _) = EnsureSession();
        using var cdn = new Client(client);
        return await cdn.DownloadManifestAsync(depotId, manifestId, requestCode, server!, depotKey, null, cdnAuth)
            .WaitAsync(TimeSpan.FromSeconds(120), ct).ConfigureAwait(false);
    }

    private (SteamClient, CallbackManager) EnsureSession()
        => _session.LiveClient is { } client && _session.LiveManager is { } manager
            ? (client, manager)
            : throw new InvalidOperationException("会话未连接（先 LoginAsync)");

    // ---------- 纯映射（离线可测） ----------

    /// <summary>workshop depot 选择：depots/workshopdepot,缺省=appId(CR 对照 ContentDownloader)。</summary>
    internal static uint SelectWorkshopDepot(KeyValue? depots, uint appId)
    {
        if (depots is null) return appId;
        var ws = depots["workshopdepot"].AsUnsignedInteger();
        return ws != 0 ? ws : appId;
    }

    /// <summary>DepotManifest → ManifestHandle 映射（SHA-1 hex;D4.3 chunk 校验输入）。</summary>
    internal static ManifestHandle MapManifest(DepotManifest m, uint appId, uint depotId, ulong gid, string? fileUrl)
    {
        var files = (m.Files ?? new()).Select(f => new ManifestFile(
            f.FileName, f.TotalSize, Hex(f.FileHash),
            (f.Chunks ?? new()).Select(c => new ManifestChunk(
                Hex(c.ChunkID), c.Offset, c.CompressedLength, c.UncompressedLength)).ToList())).ToList();
        return new ManifestHandle(appId, depotId, gid, fileUrl, files, m.TotalUncompressedSize);
    }

    internal static PubFileSummary MapDetails(PublishedFileDetails d)
        => new(
            PublishedFileId: d.publishedfileid,
            FileType: (int)d.file_type,
            FileName: string.IsNullOrEmpty(d.filename) ? null : d.filename,
            FileUrl: string.IsNullOrEmpty(d.file_url) ? null : d.file_url,
            HContentFile: d.hcontent_file,
            IsCollection: d.file_type == (uint)EWorkshopFileType.Collection,
            ChildIds: d.children.Select(c => c.publishedfileid).ToList());

    private static string Hex(byte[]? b) => b is null ? string.Empty : Convert.ToHexString(b).ToLowerInvariant();

    /// <summary>会话期间回调泵（using 结束自动停；异常隔离同 D3.2 纪律）。</summary>
    private sealed class CallbackPump : IAsyncDisposable
    {
        private readonly CallbackManager _manager;
        private readonly CancellationTokenSource _cts = new();
        private readonly Task _pump;

        public CallbackPump(CallbackManager manager)
        {
            _manager = manager;
            _pump = Task.Run(() =>
            {
                while (!_cts.IsCancellationRequested)
                {
                    try { _manager.RunWaitCallbacks(TimeSpan.FromMilliseconds(100)); }
                    catch (OperationCanceledException) { break; }
                    catch { /* 回调级异常隔离（同 D3.2 纪律） */ }
                }
            }, _cts.Token);
        }

        public async ValueTask DisposeAsync()
        {
            _cts.Cancel();
            try { await _pump.ConfigureAwait(false); } catch { }
            _cts.Dispose();
        }
    }
}
