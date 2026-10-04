using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using Swdm2.App.Games;
using Swdm2.App.ViewModels;
using Swdm2.Core.Domain;
using Swdm2.Core.Options;
using Swdm2.Core.Paths;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// D9.1(t67) 浏览页整改逻辑层验收：
/// - 样本标题=mod 名字优先（无"Mod #xxx"前缀）；类别副标题后置
/// - 缩略图槽位（HasPreview=false 样本=占位图，诚实不装真图）
/// - 顶栏当前游戏快切（CurrentGameText 随 DefaultGameService 即时响应+切换命令回调）
/// - 示例数据态（IsSampleData=true=醒目标注 banner;真实源接入后 false)
/// 用户骂点"假数据 Mod #123456·剧情作品""没有快速切换游戏"整改回归闸门。
/// </summary>
public sealed class WorkshopBrowseD9Tests
{
    public WorkshopBrowseD9Tests()
    {
        if (Application.Current is null)
            new Application();
    }

    [WpfFact]
    public void Sample_Titles_Are_Mod_Names_No_Prefix()
    {
        var items = WorkshopBrowseItem.SampleData(20);

        foreach (var item in items)
        {
            Assert.DoesNotContain("Mod #", item.Title); // 无编号前缀（用户骂点①）
            Assert.False(string.IsNullOrWhiteSpace(item.Title));
            Assert.False(string.IsNullOrWhiteSpace(item.CategorySubtitle)); // 类别降副标题
        }
    }

    [WpfFact]
    public void Sample_Items_Have_No_Preview_Placeholder_Honest()
    {
        var items = WorkshopBrowseItem.SampleData(5);

        foreach (var item in items)
        {
            Assert.False(item.HasPreview); // 样本无图=占位槽位（不装真图）
            Assert.Null(item.PreviewImageUrl);
        }
    }

    [WpfFact]
    public void Sample_Ctor_Marks_Sample_Data_True()
    {
        var vm = new WorkshopBrowsePageViewModel(WorkshopBrowseItem.SampleData(5));

        Assert.True(vm.IsSampleData); // 醒目标注 banner 可见
        Assert.Equal("当前游戏：未绑定", vm.CurrentGameText); // 未注入服务=默认文案
    }

    [WpfFact]
    public void Current_Game_Text_Responds_To_Bind_Immediately()
    {
        var tempRoot = Path.Combine(Path.GetTempPath(), $"swdm-d9-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempRoot);
        try
        {
            var paths = new PathService(PathMode.Portable, tempRoot);
            var svc = new DefaultGameService();
            svc.Load(paths); // 无配置=空态
            var switched = false;
            var vm = new WorkshopBrowsePageViewModel(
                WorkshopBrowseItem.SampleData(5),
                openDetail: null, downloadTaskFactory: null, queue: null,
                downloads: null, provider: null, scheduler: null,
                navigateToDownloads: null,
                defaultGame: svc,
                switchGame: () => switched = true,
                isSampleData: true);

            Assert.Equal("当前游戏：未绑定", vm.CurrentGameText);

            // 设置页选中→绑定（落配置）→顶栏即时响应（PropertyChanged 链）
            svc.Bind(paths, new BoundGame(4000, "Garry's Mod", null));
            Assert.Equal("当前游戏：Garry's Mod", vm.CurrentGameText);

            // 切换钮回调（→GameSelect 搜索选择）
            Assert.True(vm.SwitchGameCommand.CanExecute(null));
            vm.SwitchGameCommand.Execute(null);
            Assert.True(switched);
        }
        finally
        {
            try { Directory.Delete(tempRoot, true); } catch { }
        }
    }

    [WpfFact]
    public void Full_Ctor_Sample_Flag_False_For_Real_Source()
    {
        // 真实源装配（D9.2 visual 在做）→ isSampleData=false=banner 隐藏
        var vm = new WorkshopBrowsePageViewModel(
            new[] { new WorkshopBrowseItem(1, "真实条目", "A", Array.Empty<string>(), 1,
                DateTimeOffset.Now, "https://x/p.png", new AppId(4000)) },
            openDetail: null, downloadTaskFactory: null, queue: null,
            downloads: null, provider: null, scheduler: null,
            navigateToDownloads: null,
            defaultGame: null, switchGame: null,
            isSampleData: false);

        Assert.False(vm.IsSampleData);
        Assert.True(vm.PageItems[0].HasPreview); // 有 PreviewUrl=缩略图显
    }
}
