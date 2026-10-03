using System.IO;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;

namespace Swdm2.App.Library;

/// <summary>
/// 本地库默认扫描器（t51 D5.12 期间的轻量实现；D6.1 阶段 6 替换为真实库管理）。
/// 扫描逻辑=WorkshopContent 根下按游戏目录（数字名=AppId)→item 目录（数字名=PublishedFileId)。
/// 目录不存在/无条目=空列表（诚实降级，不抛）。
/// </summary>
public sealed class LocalLibraryScanner : ILibraryScanner
{
    private readonly IPathService _paths;
    private readonly string[] _knownAppIds;

    /// <param name="knownAppIds">已知游戏 AppId 列表（用户绑定过的游戏；空=扫根目录全部数字子目录）。</param>
    public LocalLibraryScanner(IPathService paths, IEnumerable<int>? knownAppIds = null)
    {
        ArgumentNullException.ThrowIfNull(paths);
        _paths = paths;
        _knownAppIds = (knownAppIds ?? Array.Empty<int>()).Select(v => v.ToString()).ToArray();
    }

    public Task<IReadOnlyList<ModLibraryEntry>> ScanAsync(CancellationToken ct = default)
    {
        var entries = new List<ModLibraryEntry>();
        var contentRoot = Path.GetDirectoryName(_paths.WorkshopContent(new AppId(0)))
            ?? _paths.SteamCmdDirectory;
        if (!Directory.Exists(contentRoot))
            return Task.FromResult<IReadOnlyList<ModLibraryEntry>>(entries);

        foreach (var gameDir in Directory.EnumerateDirectories(contentRoot))
        {
            var gameName = Path.GetFileName(gameDir);
            if (!int.TryParse(gameName, out var appId) || appId <= 0)
                continue;
            if (_knownAppIds.Length > 0 && !_knownAppIds.Contains(gameName))
                continue;

            foreach (var itemDir in Directory.EnumerateDirectories(gameDir))
            {
                ct.ThrowIfCancellationRequested();
                var itemIdRaw = Path.GetFileName(itemDir);
                if (!ulong.TryParse(itemIdRaw, out var itemId) || itemId == 0)
                    continue;

                var info = new DirectoryInfo(itemDir);
                entries.Add(new ModLibraryEntry(new(itemId), new(appId),
                    title: itemIdRaw, // 无元数据=标题用 id（D6.1 富化）
                    relativePath: Path.Combine(gameName, itemIdRaw))
                {
                    InstalledAtUtc = info.CreationTimeUtc,
                    FileSize = SafeDirectorySize(itemDir),
                });
            }
        }

        return Task.FromResult<IReadOnlyList<ModLibraryEntry>>(entries);
    }

    private static ulong? SafeDirectorySize(string dir)
    {
        try
        {
            ulong sum = 0;
            foreach (var f in Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories))
            {
                sum += (ulong)new FileInfo(f).Length;
            }
            return sum;
        }
        catch (UnauthorizedAccessException)
        {
            return null; // 权限不足=未知（诚实 null，不造假）
        }
    }
}
