using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Input;
using System.Windows.Controls;
using System.Windows.Threading;
using Swdm2.App.Ui.Pages;

namespace Swdm2.App.Navigation;

/// <summary>
/// 页面导航服务（t2 §2.5;pcl2 §3.2 可粘贴实现的 2.0 等价）。
/// 容器替换：PageHost(ContentControl).Content = 页面（不用 Frame/Page)。
/// 返回栈：Stack&lt;Func&lt;PageBase&gt;&gt;（工厂，重复进入刷新实例）。
/// 切换时序（PCL2 实测 110→30ms;⚠️[参数待重标定]，Common.xaml swdm-MotionPageOut/In)：
/// StopPreviousAnimations → 旧页 RunExit() → +110ms 替换 Content（新页 Opacity=0)
/// → +30ms 新页 Opacity=1 + RunEnter()。
/// 时序推进=DispatcherTimer（消息循环驱动，headless 测试可断言时间戳区间）。
/// </summary>
public sealed class PageNavigationService
{
    private readonly Stack<Func<PageBase>> _backStack = new();
    private ContentControl? _host;
    private PageBase? _current;
    private bool _navigating;

    /// <summary>绑定页面容器（MainWindow 构造时调用）。</summary>
    public void Attach(ContentControl host)
    {
        _host = host ?? throw new ArgumentNullException(nameof(host));
    }

    /// <summary>当前页（无则 null)。</summary>
    public PageBase? Current => _current;

    /// <summary>返回栈深度。</summary>
    public int BackStackDepth => _backStack.Count;

    /// <summary>
    /// 导航到页面（factory 在前，keepInStack=true 推入返回栈，主页入口传 false)。
    /// factory 为空时 new T()。
    /// </summary>
    public void Navigate<T>(Func<T>? factory = null, bool keepInStack = true) where T : PageBase, new()
    {
        if (_host is null)
            throw new InvalidOperationException("PageNavigationService 未 Attach 页面容器");

        if (_navigating)
            return; // 时序内重入直接吞（按钮连点）

        _navigating = true;
        try
        {
            var pageOut = ((Duration)_host.FindResource("swdm-MotionPageOut")).TimeSpan;
            var pageIn = ((Duration)_host.FindResource("swdm-MotionPageIn")).TimeSpan;

            // 工厂闭包必须在 push 时求值（否则捕获可变 _current,GoBack 回到错误页）
            if (keepInStack && _current is not null)
            {
                var snapshot = _current;
                _backStack.Push(() => snapshot);
            }

            // ① 停旧页全部命名轨道（防重入）
            _current?.StopAnimations();
            // ② 旧页退出动画
            _current?.RunExit();

            // ③ +110ms：替换 Content（新页 Opacity=0)
            var swapTimer = new DispatcherTimer(DispatcherPriority.Render) { Interval = pageOut };
            swapTimer.Tick += (_, _) =>
            {
                swapTimer.Stop();
                var next = factory is null ? new T() : factory();
                next.Opacity = 0;
                _current = next;
                _host.Content = next;

                // ④ +30ms：抬升 Opacity + RunEnter（交错进入）
                var enterTimer = new DispatcherTimer(DispatcherPriority.Render) { Interval = pageIn };
                enterTimer.Tick += (_, _) =>
                {
                    enterTimer.Stop();
                    next.Opacity = 1;
                    next.RunEnter();
                    _navigating = false;
                    // t62 死钮修复：计时器式切页结束后传播 CanExecute 重查
                    // （GoBack 等依赖 BackStackDepth 的命令否则停在旧禁用态）
                    CommandManager.InvalidateRequerySuggested();
                };
                enterTimer.Start();
            };
            swapTimer.Start();
        }
        catch
        {
            _navigating = false;
            throw;
        }
    }

    /// <summary>返回上一页（出栈；栈空返回 false)。导航到主页用 keepInStack=false。</summary>
    public bool GoBack()
    {
        if (_backStack.Count == 0)
            return false;
        var factory = _backStack.Pop();
        var page = factory();
        PushContentDirect(page);
        return true;
    }

    /// <summary>直接替换内容（无时序，GoBack/初始化路径）。</summary>
    private void PushContentDirect(PageBase page)
    {
        if (_host is null)
            throw new InvalidOperationException("PageNavigationService 未 Attach 页面容器");
        _current?.StopAnimations();
        _current = page;
        page.Opacity = 1;
        _host.Content = page;
        // t62 死钮修复：栈深度变化后必须传播 CanExecute 重查（DispatcherTimer
        // 切页不触发 CommandManager.RequerySuggested → GoBack 钮停在初始禁用态）
        CommandManager.InvalidateRequerySuggested();
    }

    /// <summary>初始化首页（无退出动画，直接放置）。</summary>
    public void Initialize<T>(Func<T>? factory = null) where T : PageBase, new()
    {
        var page = factory is null ? new T() : factory();
        PushContentDirect(page);
    }
}
