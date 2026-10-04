using Swdm2.App.Ui.Controls;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Swdm2.App.ViewModels;

namespace Swdm2.App.Ui.Pages;

/// <summary>
/// D5.5 工坊浏览页（t44):
/// - 帧计数（流畅性度量）：滚动期间 CompositionTarget.Rendering 帧数+生成容器数，
///   暴露 ScrollMetrics 供桌面通道/真实输入断言（头less 无渲染=沙箱降级门同族）
/// - 索引桥接 VM(MainShell 注入；设计时 DataContext=合成千项）
/// </summary>
public partial class WorkshopBrowsePage
{
    private int _renderFrames;
    private bool _counting;
    private int _generatedContainers;

    /// <summary>最近一次滚动的渲染帧数（流畅性度量=帧计数验收口径）。</summary>
    public int LastScrollRenderFrames { get; private set; }

    /// <summary>上一帧末已生成容器数（虚拟化有效性：&lt;总条目数）。</summary>
    public int GeneratedContainers => _generatedContainers;

    public WorkshopBrowsePage()
    {
        InitializeComponent();
        // t68(D9.2):SampleData 兜底删除=空起步（生产路径由 MainShellVM 注入真源 VM;
        // 设计器/headless 无注入=空 VM 不造假；虚拟化测试显式注入合成源）
        if (DataContext is null)
            DataContext = new WorkshopBrowsePageViewModel(Array.Empty<WorkshopBrowseItem>());
        CompositionTarget.Rendering += OnRendering;
        Unloaded += Page_Unloaded;
        ItemList.ItemContainerGenerator.ItemsChanged += (_, _) => UpdateGeneratedCount();
    }

    /// <summary>构造后/导航进入时打开帧计数窗口（沙箱降级门兼容）。</summary>
    public void StartFrameCounting()
    {
        _counting = true;
        _renderFrames = 0;
    }

    /// <summary>滚动到指定偏移（测试钩子；平滑链路同滚轮）。</summary>
    public void SmoothScrollForTest(double targetOffset)
    {
        StartFrameCounting();
        var scroller = SmoothScrollAttach.FindInternalScrollViewer(ItemList);
        if (scroller is null)
        {
            // 头less 未布局：直接计同步偏移（逻辑等价；降级门同族）
            LastScrollRenderFrames = 0;
            return;
        }
        SmoothScrollAttach.SmoothTo(scroller, targetOffset);
    }

    public void StopFrameCounting()
    {
        _counting = false;
        LastScrollRenderFrames = _renderFrames;
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        if (_counting) _renderFrames++;
    }

    private void UpdateGeneratedCount()
    {
        _generatedContainers = ItemList.ItemContainerGenerator.Items.Count;
    }

    /// <summary>卸载钩子：解绑渲染计数（防泄漏；PageBase 无 OnVisualParentChanged 可重写）。</summary>
    private void Page_Unloaded(object sender, RoutedEventArgs e)
        => CompositionTarget.Rendering -= OnRendering;
}
