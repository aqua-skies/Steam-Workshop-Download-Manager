using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Swdm2.Downloads.Disk;

/// <summary>
/// 稀疏文件分配器（D4.6,spec §3.3+基线决策 8/D8):
/// - NTFS 支持→FSCTL_SET_SPARSE 打标记 + SetLength（真稀疏占位，免零填充分配）
/// - exFAT/FAT32 或探测失败→SetLength 降级（预分配零填充； honesty: 返回 Method 标注降级）
/// - ⚠️**不可逆警告**：稀疏标记不可移除（spec D8:稀疏只用于**下载期文件**，
///   禁止对用户既有库文件操作）——本分配器仅接受下载期路径（调用方证明 isResume/isDownloadLifecycle）
/// </summary>
public enum AllocationMethod
{
    /// <summary>FSCTL_SET_SPARSE 真稀疏占位。</summary>
    SparseFlag,
    /// <summary>exFAT 等不支持稀疏的卷：SetLength 预分配降级。</summary>
    SetLengthFallback,
}

public sealed record SparseAllocation(AllocationMethod Method, long Length, string Path);

public interface ISparseFileAllocator
{
    /// <summary>
    /// 为**下载期文件**分配占位（不可逆稀疏警告：禁止用户既有库文件）。
    /// isResume=true=续传场景（已有部分内容的下载期文件，允许）。
    /// </summary>
    Task<SparseAllocation> AllocateForDownloadAsync(string path, long length,
        bool isResume = false, CancellationToken ct = default);
}

public sealed class SparseFileAllocator : ISparseFileAllocator
{
    private const uint FSCTL_SET_SPARSE = 0x000900C4;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool DeviceIoControl(
        SafeFileHandle hDevice, uint dwIoControlCode,
        IntPtr lpInBuffer, int nInBufferSize,
        IntPtr lpOutBuffer, int nOutBufferSize,
        out int lpBytesReturned, IntPtr lpOverlapped);

    private readonly IVolumeCapabilityProbe _probe;

    /// <summary>测试 seam：注入假卷探测（模拟 exFAT 不支持场景）。</summary>
    internal Func<string, bool>? ProbeOverride { get; set; }

    public SparseFileAllocator(IVolumeCapabilityProbe? probe = null)
    {
        _probe = probe ?? new VolumeCapabilityProbe();
    }

    public async Task<SparseAllocation> AllocateForDownloadAsync(string path, long length,
        bool isResume = false, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (length <= 0) throw new ArgumentOutOfRangeException(nameof(length));

        // 既有库文件护栏（D8:稀疏只用于下载期文件；非续传场景已有内容的文件=拒绝）
        if (!isResume && File.Exists(path) && new FileInfo(path).Length > 0)
            throw new InvalidOperationException(
                $"拒绝为已有内容的文件分配稀疏占位（D8 不可逆护栏）: {path}");

        Directory.CreateDirectory(Path.GetDirectoryName(path)!);

        var supports = ProbeOverride?.Invoke(path) ?? _probe.SupportsSparseFiles(path);

        await using var file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.Write,
            FileShare.None, bufferSize: 64 * 1024, useAsync: true);
        if (supports)
        {
            try
            {
                var handle = file.SafeFileHandle;
                if (handle is null || !DeviceIoControl(handle, FSCTL_SET_SPARSE, IntPtr.Zero, 0,
                        IntPtr.Zero, 0, out _, IntPtr.Zero))
                {
                    // DeviceIoControl 失败=降级（覆盖：句柄无效/权限不足等）
                    supports = false;
                }
            }
            catch
            {
                supports = false;
            }
        }

        // 稀疏或降级路径统一 SetLength（稀疏卷上=真稀疏逻辑长度增长；exFAT=预分配降级）
        file.SetLength(length);
        await file.FlushAsync(ct).ConfigureAwait(false);

        return new SparseAllocation(
            supports ? AllocationMethod.SparseFlag : AllocationMethod.SetLengthFallback,
            length, path);
    }
}
