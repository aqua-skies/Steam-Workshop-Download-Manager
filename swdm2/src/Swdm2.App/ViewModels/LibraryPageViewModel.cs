using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Windows.Input;
using Swdm2.App.Library;
using Swdm2.Core.Domain;
using Swdm2.Core.Paths;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 库页 VM(D5.12;P0 旅程 5「下载→库」载体）。
/// 呈现契约：已下载 mod 列表（分类/扫描结果）+打开目录。
/// 数据源=ILibraryScanner（t51 默认 LocalLibraryScanner 轻扫；D6.1 阶段 6
/// 接入真实库管理扫描/导入导出——依赖时延后，本 VM 不变）。
/// 空库=诚实空态文案，不造假条目（1.x 学费同族）。
/// </summary>
public sealed class LibraryPageViewModel : ViewModelBase
{
    private readonly ILibraryScanner _scanner;
    private readonly IPathService _paths;
    private bool _isLoading;
    private string _emptyHint = "库为空——下载完成的 mod 会自动出现在这里";
    private LibraryRow? _selectedRow;

    /// <summary>库条目行（标题/AppId/路径/大小；分类=按游戏 AppId 分组）。</summary>
    public ObservableCollection<LibraryRow> Rows { get; } = new();

    /// <summary>按游戏分组的分类视图（键=AppId 显示名）。</summary>
    public ObservableCollection<LibraryGroup> Groups { get; } = new();

    public bool IsLoading
    {
        get => _isLoading;
        private set => SetProperty(ref _isLoading, value);
    }

    /// <summary>空态提示（无库条目时；诚实文案）。</summary>
    public string EmptyHint
    {
        get => _emptyHint;
        private set => SetProperty(ref _emptyHint, value);
    }

    public LibraryRow? SelectedRow
    {
        get => _selectedRow;
        set => SetProperty(ref _selectedRow, value);
    }

    public ICommand RefreshCommand { get; }
    public ICommand OpenDirectoryCommand { get; }

    public LibraryPageViewModel(ILibraryScanner scanner, IPathService paths)
    {
        _scanner = scanner ?? throw new ArgumentNullException(nameof(scanner));
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));

        RefreshCommand = new RelayCommand(async () => await LoadAsync(), () => !IsLoading);
        OpenDirectoryCommand = new RelayCommand(OpenDirectory, () => SelectedRow is not null);
    }

    /// <summary>加载库（扫描；失败=空态提示带错误信息，不抛）。</summary>
    public async Task LoadAsync()
    {
        IsLoading = true;
        try
        {
            var entries = await _scanner.ScanAsync().ConfigureAwait(true);
            Rows.Clear();
            Groups.Clear();
            foreach (var e in entries)
                Rows.Add(new LibraryRow(e));

            // 分类=按游戏 AppId 分组
            foreach (var g in Rows.GroupBy(r => r.AppIdText)
                         .Select(g => new LibraryGroup(g.Key, g.ToList())))
                Groups.Add(g);

            EmptyHint = Rows.Count > 0
                ? $"{Rows.Count} 个条目 · {Groups.Count} 个游戏"
                : "库为空——下载完成的 mod 会自动出现在这里";
        }
        catch (Exception)
        {
            EmptyHint = "库扫描失败（目录不可读）——请检查库目录权限";
            // 诚实降级：扫描失败不抛到 UI，空态文案说明
        }
        finally
        {
            IsLoading = false;
        }
    }

    private void OpenDirectory()
    {
        if (SelectedRow is null) return;
        var abs = Path.Combine(_paths.SteamCmdDirectory, "steamapps", "workshop",
            "content", SelectedRow.AppIdText, SelectedRow.ItemIdText);
        if (!Directory.Exists(abs))
        {
            EmptyHint = "目录不存在（可能已被移动或删除）";
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo("explorer.exe", abs) { UseShellExecute = true });
        }
        catch (Exception)
        {
            // 打开失败=状态文案（不崩）
            EmptyHint = "打开目录失败（explorer 启动失败）";
        }
    }
}

/// <summary>库行 VM（呈现契约：标题/AppId/路径/大小）。</summary>
public sealed class LibraryRow
{
    public string Title { get; }
    public string AppIdText { get; }
    public string ItemIdText { get; }
    public string RelativePath { get; }
    public string SizeText { get; }
    public DateTime InstalledAtUtc { get; }

    public LibraryRow(ModLibraryEntry entry)
    {
        Title = string.IsNullOrWhiteSpace(entry.Title) ? entry.ItemId.Value.ToString() : entry.Title;
        AppIdText = entry.AppId.Value.ToString();
        ItemIdText = entry.ItemId.Value.ToString();
        RelativePath = entry.RelativePath;
        SizeText = entry.FileSize is null ? "未知" : HumanBytes(entry.FileSize.Value);
        InstalledAtUtc = entry.InstalledAtUtc;
    }

    private static string HumanBytes(ulong bytes) => bytes switch
    {
        < 1024UL => $"{bytes} B",
        < 1024UL * 1024UL => $"{bytes / 1024.0:F1} KB",
        < 1024UL * 1024UL * 1024UL => $"{bytes / (1024.0 * 1024.0):F1} MB",
        _ => $"{bytes / (1024.0 * 1024.0 * 1024.0):F2} GB",
    };

    public override string ToString() => $"{Title} ({AppIdText}/{ItemIdText})";
}

/// <summary>库分类组（按游戏 AppId)。</summary>
public sealed class LibraryGroup
{
    public string AppIdText { get; }
    public IReadOnlyList<LibraryRow> Rows { get; }

    public LibraryGroup(string appIdText, IReadOnlyList<LibraryRow> rows)
    {
        AppIdText = appIdText;
        Rows = rows;
    }
}