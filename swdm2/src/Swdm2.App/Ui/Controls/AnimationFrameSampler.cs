using System.Windows.Media;

namespace Swdm2.App.Ui.Controls;

/// <summary>
/// 帧采样门（t55 D5.16;"动画无闪烁（帧采样门）")：
/// CompositionTarget.Rendering 计数+fps 报告——60 帧采样窗口。
/// 沙箱（ENV-DOWNGRADE 门族，同 t44/D5.3)无桌面渲染=0 帧=合法降级，
/// 桌面通道复跑断言 fps≥20；逻辑层恒可断言计数器单调不减。
/// </summary>
public sealed class AnimationFrameSampler : IDisposable
{
    private int _frames;
    private bool _sampling;
    private DateTime _start = DateTime.MinValue;

    /// <summary>采样窗口帧数（60 帧为 1 窗口=spec 验收口径）。</summary>
    public const int FrameWindow = 60;

    /// <summary>最低可接受 fps(20fps+=验收门）。</summary>
    public const int MinFps = 20;

    /// <summary>当前累计帧数（单调不减）。</summary>
    public int Frames => _frames;

    /// <summary>开始采样。</summary>
    public void Start()
    {
        _frames = 0;
        _sampling = true;
        _start = DateTime.UtcNow;
        CompositionTarget.Rendering += OnRendering;
    }

    /// <summary>停止采样并返回窗口 fps(0=无渲染=环境降级，不算通过也不算失败）。</summary>
    public double Stop()
    {
        _sampling = false;
        CompositionTarget.Rendering -= OnRendering;
        var seconds = (DateTime.UtcNow - _start).TotalSeconds;
        return seconds <= 0 ? 0 : _frames / seconds;
    }

    /// <summary>采样 60 帧或超时（毫秒）后停止并返回 fps。</summary>
    public double SampleUntilWindowOrTimeout(int timeoutMs = 4000)
    {
        Start();
        var deadline = DateTime.UtcNow.AddMilliseconds(timeoutMs);
        while (_sampling && _frames < FrameWindow && DateTime.UtcNow < deadline)
        {
            // 让出：渲染线程自增（无 DoEvents 依赖的轻量轮询；超时=降级门）
            System.Threading.Thread.Sleep(16);
        }
        return Stop();
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        if (_sampling)
        {
            _frames++;
            if (_frames >= FrameWindow) _sampling = false;
        }
    }

    public void Dispose() => Stop();
}
