using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;
using Swdm2.Downloads.Limiter;
using Swdm2.Steam.Cdn;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// SteamKit CDN 主 provider(D4.4):
/// - ExecuteAsync=匿名会话→ResolveUgcManifestAsync→DownloadChunksAsync→逐 chunk 偏移直写
///   （简易装配；D4.6 磁盘域升级为稀疏占位/偏移直写纪律后替换此层）
/// - 进度上报=chunk 累计字节→总线（分段数 null=诚实 N/A;D4.5 分段并发后填充）
/// - 失败=<see cref="DownloadProviderException"/>(SteamError)→LastError 供 <see cref="DownloadProviderRouter"/> 路由
/// - ProcessSlotAcquirer hook(qa-20 t27 同模式：D4.4 多 provider 槽扩展接入点）
/// - 沙箱 CM 阻断→Network 错误→链回退 steamcmd（真路由）
/// </summary>
public sealed class SteamKitCdnProvider : IDownloadProvider, IReportLastError
{
    private readonly ISteamSessionManager _session;
    private readonly ISteamCdnClient _cdn;
    private readonly IDownloadEventBus _bus;
    private readonly int? _loginTimeoutSeconds;
    private readonly ISpeedLimiter? _limiter; // D4.7 chunk 调度点消费

    /// <summary>qa-20 t27 同模式：槽获取 hook（多 provider 槽扩展接入点）。</summary>
    public Func<DownloadTask, CancellationToken, Task>? ProcessSlotAcquirer { get; set; }

    public Exception? LastError { get; private set; }

    public SteamKitCdnProvider(ISteamSessionManager session, ISteamCdnClient cdn,
        IDownloadEventBus bus, int? loginTimeoutSeconds = null, ISpeedLimiter? limiter = null)
    {
        _session = session ?? throw new ArgumentNullException(nameof(session));
        _cdn = cdn ?? throw new ArgumentNullException(nameof(cdn));
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
        _loginTimeoutSeconds = loginTimeoutSeconds;
        _limiter = limiter;
    }

    public async Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(entry);
        LastError = null;
        var task = entry.Task;
        var taskId = task.Id;

        try
        {
            if (ProcessSlotAcquirer is not null)
                await ProcessSlotAcquirer(task, ct).ConfigureAwait(false);

            // 1) 匿名会话（已登录则复用 Current)
            if (_session.Current is null)
            {
                var login = await _session.LoginAsync(
                    new SteamSessionLogin(null, null, null), ct).ConfigureAwait(false);
                if (!login.IsOk)
                    throw new DownloadProviderException(login.Error ?? SteamError.Network,
                        $"SteamKit 匿名会话失败={login.Error}");
            }

            // 2) manifest 解析（-pubfile 路径）
            var resolve = await _cdn.ResolveUgcManifestAsync(task.AppId, task.Item.Id, ct)
                .ConfigureAwait(false);
            if (!resolve.IsOk)
                throw new DownloadProviderException(resolve.Error ?? SteamError.Network,
                    $"manifest 解析失败={resolve.Error}");
            var manifest = resolve.Value!;

            // 3) 直链分支=HTTP provider 域（D4.x HTTP 分段 provider 处理；本 provider 明确不支持）
            if (manifest.IsDirectLink)
                throw new DownloadProviderException(SteamError.InvalidConfiguration,
                    "直链	file_url 路径待 HTTP provider 接入");

            // 4) chunk 下载（并行+校验在 Cdn 客户端内）+偏移直写
            var dir = string.IsNullOrEmpty(task.DestinationDirectory)
                ? Path.GetTempPath()
                : task.DestinationDirectory;
            Directory.CreateDirectory(dir);

            ulong received = 0;
            var total = manifest.TotalUncompressedSize > 0
                ? (ulong?)manifest.TotalUncompressedSize : null;

            // 首文件名装配（多文件 manifest 的简易装配；D4.6 磁盘域接替完整装配纪律）
            var firstFile = manifest.Files.FirstOrDefault(f => f.Chunks.Count > 0);
            if (firstFile is null)
                throw new DownloadProviderException(SteamError.InvalidConfiguration, "manifest 无可下载文件");
            var targetPath = Path.Combine(dir, Path.GetFileName(firstFile.FileName));

            await using var fileStream = new FileStream(targetPath, FileMode.Create, FileAccess.Write,
                FileShare.None, bufferSize: 65536, useAsync: true);
            fileStream.SetLength((long)(total ?? 0));

            await foreach (var chunk in _cdn.DownloadChunksAsync(manifest, ct).ConfigureAwait(false))
            {
                if (!chunk.IsOk)
                    throw new DownloadProviderException(chunk.Error ?? SteamError.InvalidChecksum,
                        $"chunk 失败={chunk.Error}");
                var data = chunk.Value!.Data;
                // D4.7 限速双点之一：chunk 调度点（令牌桶按 chunk 字节消费）
                if (_limiter is not null) await _limiter.WaitAsync(data.Length, ct).ConfigureAwait(false);
                fileStream.Seek((long)chunk.Value.Offset, SeekOrigin.Begin);
                await fileStream.WriteAsync(data, ct).ConfigureAwait(false);
                received += (ulong)data.Length;
                await _bus.ReportProgressAsync(taskId, received, total, ct: ct)
                    .ConfigureAwait(false);
            }

            await fileStream.FlushAsync(ct).ConfigureAwait(false);
            return true;
        }
        catch (OperationCanceledException)
        {
            throw; // 取消语义直达（router 不视为路由错误）
        }
        catch (DownloadProviderException ex)
        {
            LastError = ex;
            return false; // 不报 Failed 状态：链路由（D4.4 router）决策终态；不可路由才由 scheduler 转 Failed
        }
        catch (Exception ex)
        {
            LastError = new DownloadProviderException(SteamError.Network, "SteamKit provider 异常", ex);
            return false;
        }
    }

    public Task PauseAsync(DownloadTaskId taskId)
    {
        // chunk 并行取消语义经 ct 链（D3.1 scheduler linked CTS)；无独立进程句柄
        return Task.CompletedTask;
    }

    public Task CancelAsync(DownloadTaskId taskId)
    {
        return Task.CompletedTask;
    }
}
