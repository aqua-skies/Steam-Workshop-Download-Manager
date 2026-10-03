using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Input;
using Swdm2.App.Ui.Pages;
using Swdm2.Core.Domain;
using Swdm2.Steam.Web;

namespace Swdm2.App.ViewModels;

/// <summary>
/// 游戏选择页 VM（D5.4;t2 §2.5 页面群）。
/// **1.x 三个用户 bug 的内置防呆**（swdm 1.4.2 学费，逐条移植对策）：
/// ① **联想重做（列表整体重建→丢焦点/闪烁）**：候选集合=单一 ObservableCollection
///    实例原地 Clear+Add（ItemsControl 容器复用，无重绘闪烁）；VM 永不替换集合引用。
/// ② **即时反馈缺失（输入后无任何响应直到网络回来）**：输入即刻进入
///    "搜索中…"状态（本地同步候选立即出现）+结果到达即刻更新计数；不等网络。
/// ③ **中英别名不命中（"饥荒"≠"Don't Starve")**：GameAliasTable 归一化匹配
///    （NFKC+小写+仅字母数字，精确→子串），离线兜底；在线 storesearch 到达后合并增强。
/// 附带 1.x 同族第四 bug（回车去重）：Enter 在候选未达时置 _enterPending，
/// 候选到达自动选中首项（词不被静默丢弃）；重复 Enter 同一游戏=幂等不重发。
/// 防抖=DispatcherTimer 350ms(1.x PySide 实测值；参数移植按经验复验纪律先沿用，
/// 落地后按 A9 体感计时复标定）。
/// </summary>
public sealed class GameSelectPageViewModel : ViewModelBase
{
    private readonly IStoreSearchClient? _storeSearch;
    private readonly Action<GameInfo>? _navigateToDetail;
    private readonly System.Windows.Threading.DispatcherTimer _debounce;
    private CancellationTokenSource? _searchCts;

    private string _searchTerm = string.Empty;
    private string _statusHint = "输入游戏名搜索（中英均可）";
    private bool _isSearching;
    private bool _enterPending;           // 1.x 回车去重：候选未到时挂起的 Enter
    private GameInfo? _pendingEnterGame;  // 重复 Enter 幂等：上次确认的游戏

    /// <summary>候选集合=单一实例原地更新（①防呆：替换集合引用=1.x 联想重做 bug)</summary>
    public ObservableCollection<GameInfo> Suggestions { get; } = new();

    public string SearchTerm
    {
        get => _searchTerm;
        set
        {
            if (!SetProperty(ref _searchTerm, value))
                return;
            // ②即时反馈：输入即刻进入搜索态（不等防抖结束）
            IsSearching = true;
            StatusHint = "搜索中…";
            // 保留语义：仅当已存在挂起 Enter 时随输入保留（输入本身不置挂起
            // ——挂起只能由 HandleEnterKey 置，否则任何输入都自动确认=1.x 回车 bug 复发）
            _enterPending = _enterPending && value.Length > 0;
            _debounce.Stop();
            _debounce.Start();
        }
    }

    public string StatusHint
    {
        get => _statusHint;
        private set => SetProperty(ref _statusHint, value);
    }

    public bool IsSearching
    {
        get => _isSearching;
        private set => SetProperty(ref _isSearching, value);
    }

    public ICommand ConfirmCommand { get; }

    public GameSelectPageViewModel(
        IStoreSearchClient? storeSearch = null,
        Action<GameInfo>? navigateToDetail = null)
    {
        _storeSearch = storeSearch;
        _navigateToDetail = navigateToDetail;

        _debounce = new System.Windows.Threading.DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(350),
        };
        _debounce.Tick += OnDebounceTick;

        ConfirmCommand = new RelayCommand(ConfirmSelection,
            () => Suggestions.Count > 0);
    }

    /// <summary>防抖到点：本地候选即刻（同步零网络）+ 在线增强（异步合并）。</summary>
    private async void OnDebounceTick(object? sender, EventArgs e)
    {
        _debounce.Stop();
        _searchCts?.Cancel();
        _searchCts = new CancellationTokenSource();
        var ct = _searchCts.Token;

        var term = _searchTerm;
        if (string.IsNullOrWhiteSpace(term))
        {
            UpdateSuggestions(Array.Empty<GameInfo>());
            IsSearching = false;
            StatusHint = "输入游戏名搜索（中英均可）";
            return;
        }

        // ③防呆：本地别名归一化候选=零网络即时（网络熔断时联想仍可用）
        var local = GameAliasTable.Match(term, maxCount: 12);

        // ②即时反馈：本地候选**立即**原地更新（不等在线结果）
        UpdateSuggestions(local);

        if (_storeSearch is not null)
        {
            try
            {
                var result = await _storeSearch.SearchGamesAsync(term, ct);
                if (!ct.IsCancellationRequested && result is { IsOk: true, Value: not null })
                {
                    // 合并：在线结果在前（权威），本地兜底补位（去重 by AppId)
                    var merged = MergeResults(result.Value, local);
                    UpdateSuggestions(merged);
                }
            }
            catch (OperationCanceledException)
            {
                // 新输入取消旧查询（在途取消，1.x 同族防抖语义）
            }
            catch
            {
                // 网络失败=本地兜底已显示；状态如实提示
                if (!ct.IsCancellationRequested)
                    StatusHint = $"{Suggestions.Count} 条候选（在线源不可达，本地别名兜底）";
            }
        }

        if (!ct.IsCancellationRequested)
        {
            IsSearching = false;
            StatusHint = Suggestions.Count > 0
                ? $"{Suggestions.Count} 条候选 · 回车或点击确认"
                : $"无“{term}”相关游戏（中英别名均未命中）";

            // 1.x 回车去重：候选到达后自动兑现挂起的 Enter（词不被丢弃）
            if (_enterPending && Suggestions.Count > 0)
            {
                _enterPending = false;
                ConfirmSelection();
            }
        }
    }

    /// <summary>原地更新（①防呆核心）：Clear+Add，容器复用=无重绘闪烁。</summary>
    private void UpdateSuggestions(IReadOnlyList<GameInfo> next)
    {
        Suggestions.Clear();
        foreach (var g in next)
            Suggestions.Add(g);
        // 显式刷新命令可用性（CanExecuteChanged 绑定）
        CommandManager.InvalidateRequerySuggested();
    }

    private static IReadOnlyList<GameInfo> MergeResults(
        IReadOnlyList<GameInfo> online, IReadOnlyList<GameInfo> local)
    {
        var merged = new List<GameInfo>(online);
        var ids = new HashSet<int>(online.Select(g => g.Id.Value));
        foreach (var g in local)
        {
            if (ids.Add(g.Id.Value))
                merged.Add(g);
        }
        return merged;
    }

    /// <summary>确认选中（回车/点击/双击同路径；幂等防重复）。</summary>
    public void ConfirmSelection()
    {
        var game = Suggestions.FirstOrDefault();
        if (game is null)
            return;
        if (_pendingEnterGame is not null && _pendingEnterGame.Id == game.Id)
            return;  // 重复 Enter 同一游戏=幂等不重发（1.x 回车去重同族）
        _pendingEnterGame = game;
        StatusHint = $"已选择：{game.Name}（AppId {game.Id.Value}）";
        _navigateToDetail?.Invoke(game);
    }

    /// <summary>列表点击选中项确认（ListBox 双击/单击按钮同入口）。</summary>
    public void ConfirmSelection(GameInfo game)
    {
        if (game is null) return;
        if (_pendingEnterGame is not null && _pendingEnterGame.Id == game.Id)
            return;
        _pendingEnterGame = game;
        StatusHint = $"已选择：{game.Name}（AppId {game.Id.Value}）";
        _navigateToDetail?.Invoke(game);
    }

    /// <summary>供页面 KeyDown 回车调用（不依赖命令焦点）。</summary>
    public void HandleEnterKey()
    {
        if (Suggestions.Count > 0)
            ConfirmSelection();
        else
            _enterPending = true;  // 候选未到：挂起，到达后自动选中（1.x 学费）
    }

    /// <summary>测试钩子（InternalsVisibleTo):直接执行防抖到点逻辑，
    /// 避开 driver STA 无 Dispatcher 帧时 DispatcherTimer 不 tick（D5.3 同族教训）。</summary>
    internal async void RaiseDebounceForTest()
        => await Task.Run(async () =>
        {
            OnDebounceTick(null, EventArgs.Empty);
            await Task.Delay(50);  // 让异步 storesearch（注入时）落到 await 后
        });

    /// <summary>测试钩子：回车挂起状态（确认候选未达时 Enter 不丢弃）。</summary>
    internal bool IsEnterPendingForTest => _enterPending;
}
