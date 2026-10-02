using System.Runtime.InteropServices;
using System.Text;

namespace Swdm2.Downloads.Disk;

/// <summary>
/// 卷能力探测（D4.6):GetVolumeInformation 查 FILE_SUPPORTS_SPARSE_FILES。
/// exFAT/FAT32 不支持→稀疏降级 SetLength（D4.6 验收判据）。
/// </summary>
public interface IVolumeCapabilityProbe
{
    /// <summary>目录所在卷是否支持稀疏文件。</summary>
    bool SupportsSparseFiles(string directoryPath);
}

public sealed class VolumeCapabilityProbe : IVolumeCapabilityProbe
{
    private const uint FILE_SUPPORTS_SPARSE_FILES = 0x00000040;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool GetVolumeInformation(
        string rootPathName, StringBuilder? volumeNameBuffer, int volumeNameSize,
        out uint volumeSerialNumber, out uint maximumComponentLength,
        out uint fileSystemFlags, StringBuilder? fileSystemNameBuffer, int fileSystemNameSize);

    public bool SupportsSparseFiles(string directoryPath)
    {
        var root = Path.GetPathRoot(Path.GetFullPath(directoryPath));
        if (string.IsNullOrEmpty(root)) return false;
        try
        {
            var ok = GetVolumeInformation(root, null, 0, out _, out _, out var flags, null, 0);
            return ok && (flags & FILE_SUPPORTS_SPARSE_FILES) != 0;
        }
        catch
        {
            return false; // 探测失败=保守降级
        }
    }
}
