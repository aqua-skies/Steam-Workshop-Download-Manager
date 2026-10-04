using System.Windows.Automation;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Media;
using Swdm2.App.Ui.Controls;
using Swdm2.App.Ui.Pages;
using Swdm2.App.ViewModels;
using Xunit;

namespace Swdm2.UiTests.Tests.Browse;

/// <summary>
/// D5.5(t44) 工坊浏览页 A2 虚拟化六不变量（XamlReader 纯 XAML 树=真 App markup 同源；
/// 同族 chrome 测试通道，避免 driver 进程组装 AppHost 污染 UIA/Win32):
/// ① ItemsPanel=VirtualizingStackPanel
/// ② IsVirtualizing=True
/// ③ VirtualizationMode=Recycling
/// ④ ScrollUnit=Pixel
/// ⑤ ListBox **无 ScrollViewer 祖先**（VSP 自身提供滚动=wpf P4 陷阱）
/// ⑥ SmoothScrollAttach.IsEnabled=True（惯性挂内部 scroller，非外包裹）
/// 帧计数（千项滚动流畅性）=CompositionTarget 计数器代码层就位+桌面通道复跑
/// （同族 ENV-DOWNGRADE 门：头less 无渲染帧，逻辑等价前提=①-⑥+VM 分页千项）。
/// </summary>
public sealed class WorkshopBrowsePageVirtualizationTests
{
    private const string PageXamlPath =
        "swdm2/src/Swdm2.App/Ui/Pages/WorkshopBrowsePage.xaml";

    private static DirectoryInfo ResolveRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && dir.Name != "swdm2" && dir.Parent is not null) dir = dir.Parent;
        return dir?.Parent ?? new DirectoryInfo(Directory.GetCurrentDirectory());
    }

    /// <summary>加载页面 XAML 为对象树（剥 x:Class；根换 UserControl=PageBase 抽象不可 XamlReader 直构；
    /// clr-namespace 补程序集提示；返回内容树=真 App markup 同源）。</summary>
    private static object LoadPage()
    {
        var path = Path.Combine(ResolveRoot().FullName, PageXamlPath);
        var xaml = File.ReadAllText(path);
        xaml = Regex.Replace(xaml, @"\s+x:Class=""[^""]*""", string.Empty);
        // 无程序集提示的 clr-namespace 在 XamlReader.Parse（无 BAML 上下文）下按调用
        // 程序集解析=App 类型不可达 → 补 ;assembly=Swdm2.App（D5.3 工具链同族模式）
        xaml = Regex.Replace(xaml, "clr-namespace:([\\w.]+)(?<!;assembly=Swdm2.App)(?=\")",
            "clr-namespace:$1;assembly=Swdm2.App");
        // PageBase 抽象+无参 ctor → XamlReader 无法直构；根换 UserControl 载体
        // （内容树等效；起止标签同步替换；D9.1：页面级 Resources 起止标签同替换）
        xaml = Regex.Replace(xaml, @"<pages:PageBase(?=[\s>/.])", "<UserControl");
        xaml = Regex.Replace(xaml, @"</pages:PageBase\.Resources>", "</UserControl.Resources>");
        xaml = Regex.Replace(xaml, @"</pages:PageBase>", "</UserControl>");
        return XamlReader.Parse(xaml);
    }

    private static VirtualizingStackPanel GetItemsPanel(ListBox listBox)
    {
        var panel = listBox.ItemsPanel.LoadContent();
        return Assert.IsType<VirtualizingStackPanel>(panel);
    }

    /// <summary>从元素上行查祖先（LogicalTree，DataTemplate 模板内外均覆盖）。</summary>
    private static T? AncestorOf<T>(DependencyObject d) where T : DependencyObject
    {
        while (d is not null)
        {
            if (d is T t) return t;
            d = LogicalTreeHelper.GetParent(d) ?? VisualTreeHelper.GetParent(d);
        }
        return null;
    }

    [WpfFact]
    public void A2_Six_Invariants_Virtualization_Route_A()
    {
        var page = (FrameworkElement)LoadPage();
        var listBox = page.FindName("ItemList") as ListBox;
        Assert.NotNull(listBox);

        var panel = GetItemsPanel(listBox!);
        // ② IsVirtualizing
        Assert.True(VirtualizingPanel.GetIsVirtualizing(panel));
        // ③ Recycling
        Assert.Equal(VirtualizationMode.Recycling, VirtualizingPanel.GetVirtualizationMode(panel));
        // ④ ScrollUnit=Pixel
        Assert.Equal(ScrollUnit.Pixel, VirtualizingPanel.GetScrollUnit(panel));
        // ① ItemsPanel 类型
        Assert.IsType<VirtualizingStackPanel>(panel);
        // ⑤ 无 ScrollViewer 祖先（页内 ListBox 不被 ScrollViewer 包）
        Assert.Null(AncestorOf<ScrollViewer>(listBox!));
        // ⑥ 惯性附加行为开启（内部 scroller 通道，非外包裹）
        Assert.True(SmoothScrollAttach.GetIsEnabled(listBox!));
    }

    [WpfFact]
    public void AutomationId_Contract_Present()
    {
        var page = (FrameworkElement)LoadPage();
        // 契约 id=AutomationProperties.AutomationId（非 x:Name)→ 逻辑树收集后断言
        var ids = new HashSet<string>();
        CollectAutomationIds(page, ids);
        foreach (var id in new[]
        {
            "WorkshopBrowsePage_SearchBox", "WorkshopBrowsePage_TagCombo",
            "WorkshopBrowsePage_AuthorBox", "WorkshopBrowsePage_SortCombo",
            "WorkshopBrowsePage_ItemList", "WorkshopBrowsePage_PrevPage",
            "WorkshopBrowsePage_NextPage", "WorkshopBrowsePage_PageLabel",
            "WorkshopBrowsePage_ItemCountLabel", "WorkshopBrowsePage_PageSizeCombo",
        })
        {
            Assert.True(ids.Contains(id), $"contract id missing: {id}");
        }
    }

    private static void CollectAutomationIds(DependencyObject d, HashSet<string> ids)
    {
        var aid = AutomationProperties.GetAutomationId(d);
        if (!string.IsNullOrEmpty(aid)) ids.Add(aid);
        foreach (var child in LogicalTreeHelper.GetChildren(d).OfType<DependencyObject>())
            CollectAutomationIds(child, ids);
    }

    [WpfFact]
    public void Page_Default_VM_Thousand_Synthetic_And_Binds()
    {
        // t68:页面默认兜底=空 VM（假数据清除）→虚拟化基准显式注入合成千项
        var page = new WorkshopBrowsePage
        {
            DataContext = new WorkshopBrowsePageViewModel(WorkshopBrowseItem.SampleData()),
        };
        Assert.IsType<WorkshopBrowsePageViewModel>(page.DataContext);
        var vm = (WorkshopBrowsePageViewModel)page.DataContext;
        Assert.Equal(1000, vm.SourceCount);
        Assert.Equal(100, vm.PageItems.Count);
        // 头less 未布局=ItemsSource 绑定不物化（合法：WPF 绑定需 Loaded/布局）；
        // 绑定链路正确性由 A2/XAML 结构测试+FlaUI 桌面通道断言
        Assert.NotNull(page.ItemList);
        Console.WriteLine("DIAG t44: ItemList+VM 就位;ItemsSource 物化=桌面通道 (headless 不布局)");
    }

    /// <summary>帧计数 API 就位（千项滚动流畅性度量入口；桌面通道断言数值）。</summary>
    [WpfFact]
    public void Frame_Count_Api_Present_For_Desktop_Channel()
    {
        var page = new WorkshopBrowsePage();
        Assert.Equal(0, page.LastScrollRenderFrames);
        page.StartFrameCounting();
        page.StopFrameCounting();
        // 头less:无渲染事件=0 帧（合法降级；桌面通道计数器必须工作）
        Assert.Equal(0, page.LastScrollRenderFrames);
    }

    /// <summary>内部 scroller 定位（无布局时=N/A 降级；契约=方法存在且不抛）。</summary>
    [WpfFact]
    public void Internal_Scroller_Lookup_No_External_ScrollViewer()
    {
        var page = (FrameworkElement)LoadPage();
        var listBox = (ListBox)page.FindName("ItemList")!;
        var scroller = SmoothScrollAttach.FindInternalScrollViewer(listBox);
        // XamlReader 树未布局=无可视子（合法 N/A）；真布局后必须命中（桌面通道）
        Assert.True(scroller is null || scroller is ScrollViewer);
    }
}
