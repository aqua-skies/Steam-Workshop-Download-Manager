using Swdm2.Core.Domain;
using Swdm2.Core.Results;
using Swdm2.Downloads.Events;
using Swdm2.Downloads.Queue;
using Swdm2.Downloads.Segments;

namespace Swdm2.Downloads.Providers;

/// <summary>
/// HTTP 直链 provider(D4.5;spec DownloadProviderKind.HttpDirect):
/// - 直链资源（预览图/直链 CDN/发布物 file_url 分支）
/// - 分段下载器+续存+单流回退全在 Segments 域；本层=IDownloadProvider 适配+进度上报
/// - 失败=DownloadProviderException(SteamError)→链路由（D4.4)
/// 用法：路由层在 file_url 直链场景路由到本 provider（D5/D6 集成）。
/// </summary>
public sealed class HttpDirectProvider : IDownloadProvider, IReportLastError
{
    private readonly Func<HttpSegmentDownloader> _downloaderFactory;
    private readonly IDownloadEventBus _bus;

    public Exception? LastError { get; private set; }

    public HttpDirectProvider(Func<HttpSegmentDownloader> downloaderFactory, IDownloadEventBus bus)
    {
        _downloaderFactory = downloaderFactory ?? throw new ArgumentNullException(nameof(downloaderFactory));
        _bus = bus ?? throw new ArgumentNullException(nameof(bus));
    }

    public async Task<bool> ExecuteAsync(DownloadTaskEntry entry, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(entry);
        LastError = null;
        var task = entry.Task;
        var taskId = task.Id;

        // 直链 URL 来源：任务 Item 的 FileUrl?（WorkshopItem 无 FileUrl 字段 = D4.5 以 Url 形态注入）
        // D4.5 契约：DownloadTask 不含 Url 直链字段，本 provider 由集成侧以 SourceUrl 注入。
        // 保守策略：DestinationDirectory 作产物目录+固定文件名（集成层决定 URL 语义）。
        var url = GetDirectUrl(task);
        if (string.IsNullOrEmpty(url))
        {
            LastError = new DownloadProviderException(SteamError.InvalidConfiguration, "无直链 URL");
            return false;
        }

        var destPath = Path.Combine(string.IsNullOrEmpty(task.DestinationDirectory) ? Path.GetTempPath() : task.DestinationDirectory,
            Path.GetFileName(url) is { } fn && !string.IsNullOrEmpty(fn) ? fn : $"{task.Item.Id.Value}.bin");

        var downloader = _downloaderFactory();
        var progress = new Progress<long>(bytes =>
        {
            _ = _bus.ReportProgressAsync(taskId, (ulong)bytes, task.TotalBytes, segments: new List<int> { 1 }, ct: ct);
        });
        try
        {
            var result = await downloader.DownloadAsync(
                new HttpDownloadRequest(url!, destPath), progress, ct).ConfigureAwait(false);
            if (!result.IsOk)
            {
                LastError = new DownloadProviderException(result.Error ?? SteamError.Network,
                    $"HTTP 直链失败={result.Error}");
                return false;
            }
            return true;
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            LastError = new DownloadProviderException(SteamError.Network, "HTTP 直链异常", ex);
            return false;
        }
    }

    /// <summary>直链 URL 解析：任务携带的直链来源（D5 集成时由来源页注入）。</summary>
    private static string? GetDirectUrl(DownloadTask task)
        => task.Item.PreviewUrl; // 过渡：预览图直链（file_url 正式字段由 D5 metadata 扩展接入）

    public Task PauseAsync(DownloadTaskId taskId) => Task.CompletedTask;
    public Task CancelAsync(DownloadTaskId taskId) => Task.CompletedTask;
}
