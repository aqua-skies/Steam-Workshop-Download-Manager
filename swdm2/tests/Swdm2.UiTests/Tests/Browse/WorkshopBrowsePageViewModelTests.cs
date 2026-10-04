using Swdm2.App.ViewModels;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// D5.5(t44) 工坊浏览页 VM 逻辑测试（离线、确定性）：
/// 筛选链（搜索/标签/作者）→排序→分页 全链正确性+千项基准。
/// </summary>
public sealed class WorkshopBrowsePageViewModelTests
{
    private static IReadOnlyList<WorkshopBrowseItem> Sample(int count = 1000)
        => WorkshopBrowseItem.SampleData(count);

    [WpfFact]
    public void Thousand_Items_Default_Page_Hundred()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        Assert.Equal(1000, vm.SourceCount);
        Assert.Equal(100, vm.PageSize);
        Assert.Equal(100, vm.PageItems.Count);
        Assert.Equal(10, vm.TotalPages);
        Assert.Equal(1, vm.CurrentPage);
        Assert.Equal(1000, vm.FilteredCount);
    }

    [WpfFact]
    public void Search_Filters_Title_Substring_Case_Insensitive()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        var probe = vm.PageItems[7];
        // D9.1:标题改为短中文名（不再"Mod #xxx"长串）=探针截取须钳长度防越界
        var probeText = probe.Title.Length > 4
            ? probe.Title.Substring(1, 3)
            : probe.Title;
        vm.SearchText = probeText;

        Assert.Equal(1000, vm.SourceCount);
        Assert.All(vm.PageItems, i => Assert.Contains(vm.SearchText, i.Title, StringComparison.OrdinalIgnoreCase));
        Assert.Equal(vm.PageItems.Count, vm.FilteredCount);
    }

    [WpfFact]
    public void Tag_Filter_Matches_Tag_Set()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        var item = vm.PageItems[3];
        vm.TagFilter = item.Tags[0];

        Assert.All(vm.PageItems, i => Assert.Contains(item.Tags[0], i.Tags, StringComparer.OrdinalIgnoreCase));
        Assert.True(vm.FilteredCount < 1000);
    }

    [WpfFact]
    public void Author_Filter_Substring()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        var author = vm.PageItems[2].Author;
        var frag = author.Substring(0, 3);
        vm.AuthorFilter = frag;

        Assert.All(vm.PageItems, i => Assert.Contains(frag, i.Author, StringComparison.OrdinalIgnoreCase));
    }

    [WpfFact]
    public void Sort_Subscribers_Descending_Then_Ascending()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample()) { PageSize = 0 };
        vm.SortKey = BrowseSortKey.Subscribers;
        vm.SortDescending = true;
        var desc = vm.PageItems.Select(i => i.Subscribers).ToList();
        Assert.Equal(desc.OrderByDescending(x => x), desc);

        vm.SortDescending = false;
        var asc = vm.PageItems.Select(i => i.Subscribers).ToList();
        Assert.Equal(asc.OrderBy(x => x), asc);
    }

    [WpfFact]
    public void Pagination_Next_Prev_Boundaries()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        Assert.True(vm.NextPageCommand.CanExecute(null));
        vm.NextPageCommand.Execute(null);
        Assert.Equal(2, vm.CurrentPage);

        vm.PrevPageCommand.Execute(null);
        Assert.Equal(1, vm.CurrentPage);

        // 首页 Prev 不可用/末页 Next 不可用（CanExecute 契约；翻到底=连续 Next）
        Assert.False(vm.PrevPageCommand.CanExecute(null));
        while (vm.NextPageCommand.CanExecute(null)) vm.NextPageCommand.Execute(null);
        Assert.Equal(vm.TotalPages, vm.CurrentPage);
        Assert.False(vm.NextPageCommand.CanExecute(null));
    }

    [WpfFact]
    public void Page_Size_All_Disables_Paging()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        vm.PageSizeAsIndex = 3; // 全部
        Assert.Equal(0, vm.PageSize);
        Assert.Equal(1, vm.TotalPages);
        Assert.Equal(1000, vm.PageItems.Count);
        Assert.Equal("全部条目", vm.PageLabelText);
    }

    [WpfFact]
    public void Reset_Filters_Restores_Full_View()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        vm.SearchText = "不存在xyz";
        vm.AuthorFilter = "ghost";
        Assert.Empty(vm.PageItems);
        Assert.Equal(0, vm.FilteredCount);

        vm.ResetFiltersCommand.Execute(null);
        Assert.Equal(1000, vm.FilteredCount);
        Assert.Equal(100, vm.PageItems.Count);
    }

    [WpfFact]
    public void Combined_Filters_Sort_Page_Chain()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample()) { PageSize = 20 };
        var probe = vm.PageItems[0];
        vm.TagFilter = probe.Tags[0];
        vm.SortKey = BrowseSortKey.Title;
        vm.SortDescending = false;
        vm.SearchText = "Mod";

        // 链式校验：标签+搜索双条件+标题升序+单页 20
        Assert.True(vm.PageItems.Count <= 20);
        Assert.All(vm.PageItems, i => Assert.Contains(vm.SearchText, i.Title, StringComparison.OrdinalIgnoreCase));
        Assert.All(vm.PageItems, i => Assert.Contains(probe.Tags[0], i.Tags, StringComparer.OrdinalIgnoreCase));
        var titles = vm.PageItems.Select(i => i.Title).ToList();
        Assert.Equal(titles.OrderBy(t => t), titles);
        // 分页不变量：filtered 落在 [(pages-1)*20, pages*20] 区间（末页允许 <20)
        Assert.True(vm.FilteredCount >= (vm.TotalPages - 1) * 20);
        Assert.True(vm.FilteredCount <= vm.TotalPages * 20);
    }

    [WpfFact]
    public void Items_Are_Immutable_Records()
    {
        // C1:record 不可变+集合只读（1.x 原地更新闪烁学费）
        var item = WorkshopBrowseItem.SampleData(1)[0];
        Assert.True(item.Tags is IReadOnlyList<string>);
        Assert.IsType<string[]>(item.Tags); // 数组=真不可变集合（List 则可 Add=泄漏 C1)
    }

    [WpfFact]
    public void Matches_Predicate_Mirrors_Rebuild()
    {
        var vm = new WorkshopBrowsePageViewModel(Sample());
        vm.SearchText = "Mod";
        vm.AuthorFilter = "A";
        var expected = Sample().Count(i => vm.Matches(i));
        Assert.Equal(expected, vm.FilteredCount);
    }
}
