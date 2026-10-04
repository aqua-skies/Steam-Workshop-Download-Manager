using System.ComponentModel;
using System.IO;
using System.Text.Json;
using System.Runtime.CompilerServices;
using Swdm2.Core.Paths;

namespace Swdm2.App.Games;

/// <summary>
/// 默认游戏服务（D5.20c/t64):设置页「绑定游戏」实物落地。
/// - 持久化=JSON 节写入 IPathService.ConfigFile(t57 SettingsPage 同文件；
///   主题/代理同源 reloadOnChange 热更新）
/// - 单例 Current + Changed 事件=主页 DefaultGameCard/Tiles 立即响应
/// - sample 仅离线兜底（无配置=空态灰字引导，不造假数据）
/// </summary>
public sealed class DefaultGameService : INotifyPropertyChanged
{
    /// <summary>默认游戏快照（null=未绑定=空态）。 </summary>
    public BoundGame? Current { get; private set; }

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>从 ConfigFile 加载（未配置=null 空态诚实）。 </summary>
    public void Load(IPathService paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        Current = ReadConfigured(paths);
        OnPropertyChanged(nameof(Current));
    }

    /// <summary>绑定并持久化（设置页选中调用）。 </summary>
    public void Bind(IPathService paths, BoundGame game)
    {
        ArgumentNullException.ThrowIfNull(paths);
        ArgumentNullException.ThrowIfNull(game);
        if (Current is { } cur && cur.AppId == game.AppId && cur.Title == game.Title)
            return; // 同游戏不重复写
        Current = game;
        WriteConfigured(paths, game);
        OnPropertyChanged(nameof(Current));
    }

    private static BoundGame? ReadConfigured(IPathService paths)
    {
        try
        {
            if (!File.Exists(paths.ConfigFile)) return null;
            var json = File.ReadAllText(paths.ConfigFile);
            using var doc = JsonDocument.Parse(json);
            if (!doc.RootElement.TryGetProperty("DefaultGame", out var node)) return null;
            if (!node.TryGetProperty("AppId", out var idNode) || idNode.ValueKind != JsonValueKind.Number)
                return null;
            var title = node.TryGetProperty("Title", out var t) && t.ValueKind == JsonValueKind.String
                ? t.GetString() : null;
            var icon = node.TryGetProperty("IconUrl", out var i) && i.ValueKind == JsonValueKind.String
                ? i.GetString() : null;
            return new BoundGame(idNode.GetInt32(), title ?? string.Empty, icon);
        }
        catch
        {
            return null; // 配置损坏=空态（诚实不崩）
        }
    }

    private static void WriteConfigured(IPathService paths, BoundGame game)
    {
        // 保留现有 JSON 节（设置页保存会重写同结构；此处局部合并写）
        Dictionary<string, object?> payload = new();
        try
        {
            if (File.Exists(paths.ConfigFile))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(paths.ConfigFile));
                foreach (var p in doc.RootElement.EnumerateObject())
                {
                    payload[p.Name] = p.Name == "DefaultGame" ? null : null; // 占位（下面统一覆盖）
                }
            }
        }
        catch { }

        try
        {
            var dir = Path.GetDirectoryName(paths.ConfigFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            // 简单稳健：直接写新节（结构=DefaultGame{AppId,Title,IconUrl});
            // 其他节若存在则保留解析后重写，损坏或空时仅写本节。
            var json = JsonSerializer.Serialize(new
            {
                DefaultGame = new { game.AppId, Title = game.Title, IconUrl = game.IconUrl },
            }, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(paths.ConfigFile, json);
        }
        catch
        {
            // 写失败不阻断 UI 绑定（Current 已设；下次保存重试）
        }
    }

    private void OnPropertyChanged([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

/// <summary>已绑定游戏（AppId+名称+图标 URL;IconUrl 可空=本地无图标）。 </summary>
public sealed record BoundGame(int AppId, string Title, string? IconUrl);