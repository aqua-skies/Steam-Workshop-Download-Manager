using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.Library;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Xunit;

namespace Swdm2.UiTests.Tests.Library;

/// <summary>
/// D5.12 库页逻辑层验收（t51):
/// - 呈现已下载 mod 列表（扫描结果）+分类（按游戏 AppId)+空态诚实
/// - D6.1 库管理接入点=ILibraryScanner 注入（t51 默认 LocalLibraryScanner;
///   D6.1 阶段 6 接真实扫描，VM 不变——开放封闭）
/// </summary>
public sealed class LibraryPageViewModelTests
{
    public LibraryPageViewModelTests()
    {
        if (Application.Current is null)
            new Application();
    }

    private static LibraryPageViewModel NewVm(IReadOnlyList<ModLibraryEntry> entries)
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        return new LibraryPageViewModel(new StubScanner(entries), paths);
    }

    [WpfFact]
    public async Task Library_Rows_Present_Scan_Result_With_Grouping()
    {
        var vm = NewVm(new[]
        {
            new ModLibraryEntry(new(111), new(4000), "Mod A", "4000/111"),
            new ModLibraryEntry(new(222), new(4000), "Mod B", "4000/222"),
            new ModLibraryEntry(new(333), new(440), "Mod C", "440/333"),
        });

        await vm.LoadAsync();

        Assert.Equal(3, vm.Rows.Count);
        Assert.Equal("Mod A", vm.Rows[0].Title);
        Assert.Equal("4000", vm.Rows[0].AppIdText);
        // 分类：两个游戏组
        Assert.Equal(2, vm.Groups.Count);
        Assert.Equal("4000", vm.Groups[0].AppIdText);
        Assert.Equal(2, vm.Groups[0].Rows.Count);
        Assert.Equal("440", vm.Groups[1].AppIdText);
        Assert.Single(vm.Groups[1].Rows);
        Assert.Contains("3 个条目", vm.EmptyHint);
    }

    [WpfFact]
    public async Task Empty_Library_Shows_Honest_Empty_Hint()
    {
        var vm = NewVm(Array.Empty<ModLibraryEntry>());

        await vm.LoadAsync();

        Assert.Empty(vm.Rows);
        Assert.Empty(vm.Groups);
        Assert.Contains("库为空", vm.EmptyHint); // 空态诚实文案，不造假条目
    }

    [WpfFact]
    public async Task Scan_Failure_Degrades_To_Status_Not_Throw()
    {
        var paths = new PathService(PathMode.Portable, AppContext.BaseDirectory);
        var vm = new LibraryPageViewModel(new FailingScanner(), paths);

        await vm.LoadAsync(); // 不抛

        Assert.Empty(vm.Rows);
        Assert.Contains("扫描失败", vm.EmptyHint);
    }

    [WpfFact]
    public async Task Size_Unknown_Shown_Honestly()
    {
        var vm = NewVm(new[]
        {
            new ModLibraryEntry(new(111), new(4000), "Mod", "4000/111"), // FileSize=null
        });

        await vm.LoadAsync();

        Assert.Equal("未知", vm.Rows[0].SizeText); // null=诚实"未知"不造假
    }

    private sealed class StubScanner : ILibraryScanner
    {
        private readonly IReadOnlyList<ModLibraryEntry> _entries;
        public StubScanner(IReadOnlyList<ModLibraryEntry> entries) => _entries = entries;
        public Task<IReadOnlyList<ModLibraryEntry>> ScanAsync(CancellationToken ct = default)
            => Task.FromResult(_entries);
    }

    private sealed class FailingScanner : ILibraryScanner
    {
        public Task<IReadOnlyList<ModLibraryEntry>> ScanAsync(CancellationToken ct = default)
            => throw new IOException("disk unreadable");
    }
}