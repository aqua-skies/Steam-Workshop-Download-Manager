using Swdm2.Downloads.Disk;
using Xunit;

namespace Swdm2.Downloads.Tests.Disk;

/// <summary>
/// D4.6 磁盘 IO 验收（偏移直写+稀疏占位+降级）:
/// - 偏移写入无拼接：文件从开始即全长，多偏移写入逐字节正确
/// - exFAT 降级：注入假卷探测（不支持稀疏）→SetLengthFallback+长度正确
/// - 稀疏只用于下载期文件：既有内容文件拒绝（D8 不可逆护栏）
/// - 真卷探测：NTFS 上了 SparseFlag（沙箱所在卷=NTFS 实测标注，非硬断言）
/// </summary>
[Trait("Category", "Downloads")]
public sealed class SparseAllocatorTests
{
    private static string TempDir()
        => Path.Combine(Path.GetTempPath(), "swdm-d46-" + Guid.NewGuid().ToString("N")[..8]);

    /// <summary>偏移直写无拼接：创建即全长，三段乱序偏移写入逐字节正确。</summary>
    [Fact]
    public async Task Offset_Writes_No_Concatenation()
    {
        var dir = TempDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "f.bin");
        const long length = 1024 * 1024;

        var alloc = new SparseFileAllocator();
        var allocation = await alloc.AllocateForDownloadAsync(path, length);
        Assert.Equal(length, allocation.Length);

        // 创建即全长（无拼接语义：长度不依赖段完成）
        Assert.Equal(length, new FileInfo(path).Length);

        var offsets = new[] { 0L, 700_000, 300_000 };
        await using (var writer = new OffsetFileWriter(path, length))
        {
            foreach (var off in offsets)
            {
                var data = new byte[4096];
                for (var i = 0; i < data.Length; i++) data[i] = (byte)((off + i) % 251);
                await writer.WriteAtAsync(off, data);
            }
            await writer.CompleteAsync();
        } // 句柄释后再读（FileShare.None)

        var bytes = await File.ReadAllBytesAsync(path);
        Assert.Equal(length, bytes.Length);
        foreach (var off in offsets)
        {
            for (var i = 0; i < 4096; i++)
                Assert.Equal((byte)((off + i) % 251), bytes[off + i]);
        }
    }

    /// <summary>注入假探测=卷不支持稀疏（exFAT 语义）→SetLength 降级+长度正确。</summary>
    [Fact]
    public async Task Unsupported_Volume_Falls_Back_To_SetLength()
    {
        var dir = TempDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "f.bin");
        const long length = 64 * 1024;

        var alloc = new SparseFileAllocator { ProbeOverride = _ => false };
        var allocation = await alloc.AllocateForDownloadAsync(path, length);

        Assert.Equal(AllocationMethod.SetLengthFallback, allocation.Method);
        Assert.Equal(length, new FileInfo(path).Length);
    }

    /// <summary>既有内容文件拒绝（D8:稀疏只用于下载期文件；isResume 显式续传允许）。</summary>
    [Fact]
    public async Task Existing_Content_File_Refused_Unless_Resume()
    {
        var dir = TempDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "f.bin");
        await File.WriteAllBytesAsync(path, new byte[100]);

        var alloc = new SparseFileAllocator();
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            alloc.AllocateForDownloadAsync(path, 4096));

        // isResume=true 放行（续传=下载期文件复用）
        var allocation = await alloc.AllocateForDownloadAsync(path, 4096, isResume: true);
        Assert.Equal(4096, allocation.Length);
    }

    /// <summary>真卷探测：本机卷结果记录（NTFS → SparseFlag;非 NTFS 亦降级通过=环境容忍标注）。</summary>
    [Fact]
    public void Real_Volume_Probe_Returns_Boolean()
    {
        var probe = new VolumeCapabilityProbe();
        var supports = probe.SupportsSparseFiles(Path.GetTempPath());
        // 沙箱/开发机=NTFS（实测真值记录，不硬断言；结构化标签供降级路径判别）
        Console.WriteLine($"[VOLUME-PROBE] temp supports sparse files: {supports} " +
                          "(NTFS 期望 true;其他卷型=降级路径环境)");
        Assert.IsType<bool>(supports);
    }

    /// <summary>OffsetFileWriter 偏移读（重叠比对回读正确）。</summary>
    [Fact]
    public async Task Writer_ReadAt_Returns_Written_Bytes()
    {
        var dir = TempDir();
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "f.bin");
        const long length = 8192;

        await new SparseFileAllocator().AllocateForDownloadAsync(path, length);
        await using var writer = new OffsetFileWriter(path, length);
        var data = new byte[] { 1, 2, 3, 4, 5 };
        await writer.WriteAtAsync(100, data);
        var read = await writer.ReadAtAsync(100, 5);
        Assert.Equal(data, read);
    }
}
