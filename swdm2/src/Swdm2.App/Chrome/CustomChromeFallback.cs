using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace Swdm2.App.Chrome;

/// <summary>
/// WM_NCHITTEST 自定义命中区（t2 §2.4 补充场景；**fallback 条款，默认不启用**）。
/// 启用条件：窗口 chrome 不走 WPF-UI FluentWindow/TitleBar 时（例如自绘标题栏方案，
/// 或标题栏内嵌搜索框需要让位拖拽）。当前路线（t42/D5.3)走 WPF-UI TitleBar +
/// WindowChrome（CaptionHeight=48 已覆盖主拖拽路径），本条款不挂。
/// 实现：SourceInitialized 挂 HwndSource.AddHook;命中区宽 8px(PCL2 Resizer 同值，
/// 角 13px);中部 relY&lt;48 返回 HTCAPTION=2（pcl2 §2.4 可粘贴 WndProc 直译）。
/// </summary>
public static class CustomChromeFallback
{
    private const int WM_NCHITTEST = 0x0084;
    private const int HTCLIENT = 1;
    private const int HTCAPTION = 2;
    private const int HTLEFT = 10;
    private const int HTRIGHT = 11;
    private const int HTTOP = 12;
    private const int HTTOPLEFT = 13;
    private const int HTTOPRIGHT = 14;
    private const int HTBOTTOM = 15;
    private const int HTBOTTOMLEFT = 16;
    private const int HTBOTTOMRIGHT = 17;
    private const int ResizeHit = 8;      // PCL2 Resizer 8px
    private const int ResizeCorner = 13;  // PCL2 角 13px
    private const double CaptionHeight = 48; // 标题栏 48（t2 §2.4 表）

    [DllImport("user32.dll")]
    private static extern short GetCursorPos(out POINT lpPoint);

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    /// <summary>
    /// 挂 fallback 命中区（HwndSource hook）。仅 fallback 方案调用；
    /// 走 WPF-UI TitleBar 路线时本方法不被调用（保留条款代码）。
    /// </summary>
    public static void Attach(Window window)
    {
        ArgumentNullException.ThrowIfNull(window);
        var helper = new WindowInteropHelper(window);
        var source = HwndSource.FromHwnd(helper.EnsureHandle())
            ?? throw new InvalidOperationException("无法取得 HwndSource");
        source.AddHook(WndProc);
    }

    private static IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg != WM_NCHITTEST)
            return IntPtr.Zero;

        GetCursorPos(out var p);
        var window = hwnd != IntPtr.Zero
            ? HwndSource.FromHwnd(hwnd)?.RootVisual as Window
            : null;
        if (window is null)
            return IntPtr.Zero;

        var relX = p.X - window.Left;
        var relY = p.Y - window.Top;

        // 角 13px
        if (relX < ResizeCorner && relY < ResizeCorner) return new IntPtr(HTTOPLEFT);
        if (relX > window.ActualWidth - ResizeCorner && relY < ResizeCorner) return new IntPtr(HTTOPRIGHT);
        if (relX < ResizeCorner && relY > window.ActualHeight - ResizeCorner) return new IntPtr(HTBOTTOMLEFT);
        if (relX > window.ActualWidth - ResizeCorner && relY > window.ActualHeight - ResizeCorner) return new IntPtr(HTBOTTOMRIGHT);
        // 边 8px
        if (relX < ResizeHit) return new IntPtr(HTLEFT);
        if (relX > window.ActualWidth - ResizeHit) return new IntPtr(HTRIGHT);
        if (relY < ResizeHit) return new IntPtr(HTTOP);
        if (relY > window.ActualHeight - ResizeHit) return new IntPtr(HTBOTTOM);
        // 中部标题栏 48px → 可拖拽
        if (relY < CaptionHeight)
        {
            handled = true;
            return new IntPtr(HTCAPTION);
        }
        handled = true;
        return new IntPtr(HTCLIENT);
    }
}
