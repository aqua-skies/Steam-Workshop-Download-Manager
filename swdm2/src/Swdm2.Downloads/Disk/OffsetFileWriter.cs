namespace Swdm2.Downloads.Disk;

/// <summary>
/// 偏移直写器（D4.6,spec D8:单文件偏移直写免拼接）:
/// - 并发段/worker 共享同文件句柄：写位置锁内 Seek+Write（串行化磁盘写入=避免交错损坏）
/// - 拼接策略（A 策略=网络盘/AV 冲突回退）不在本类（D4.6 只提供直写；A 策略标记为下游）
/// </summary>
public interface IOffsetFileWriter : IAsyncDisposable
{
    /// <summary>偏移直写（无拼接）。</summary>
    Task WriteAtAsync(long offset, ReadOnlyMemory<byte> data, CancellationToken ct = default);

    /// <summary>完成：刷新+关闭（产物路径在任务完成前不能被库扫描=D10,下游职责）。</summary>
    Task CompleteAsync(CancellationToken ct = default);

    /// <summary>偏移读（重叠字节比对/续传起点校验用）。</summary>
    Task<byte[]> ReadAtAsync(long offset, int count, CancellationToken ct = default);

    /// <summary>当前文件长度（快照）。</summary>
    long Length { get; }
}

public sealed class OffsetFileWriter : IOffsetFileWriter
{
    private readonly FileStream _file;
    private readonly SemaphoreSlim _writeGate = new(1, 1);

    public long Length => _file.Length;

    /// <summary>测试 seam: 写入观察（断言落点）。</summary>
    internal Action<long, ReadOnlyMemory<byte>>? OnWrite { get; set; }

    public OffsetFileWriter(string path, long length, bool isResume = false)
    {
        // 偏移直写文件（下载期；D8 稀疏/降级由 ISparseFileAllocator 先行分配；ReadWrite=重叠比对读）
        _file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite,
            FileShare.None, bufferSize: 64 * 1024, useAsync: true);
        if (_file.Length != length) _file.SetLength(length);
    }

    public async Task WriteAtAsync(long offset, ReadOnlyMemory<byte> data, CancellationToken ct = default)
    {
        await _writeGate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            _file.Seek(offset, SeekOrigin.Begin);
            await _file.WriteAsync(data, ct).ConfigureAwait(false);
            OnWrite?.Invoke(offset, data);
        }
        finally
        {
            _writeGate.Release();
        }
    }

    /// <summary>偏移读（重叠字节比对/续传起点校验用；ReadWrite 句柄支持）。</summary>
    public async Task<byte[]> ReadAtAsync(long offset, int count, CancellationToken ct = default)
    {
        await _writeGate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            _file.Seek(offset, SeekOrigin.Begin);
            var buffer = new byte[count];
            var read = 0;
            while (read < count)
            {
                var n = await _file.ReadAsync(buffer.AsMemory(read), ct).ConfigureAwait(false);
                if (n <= 0) break;
                read += n;
            }
            Array.Resize(ref buffer, read);
            return buffer;
        }
        finally
        {
            _writeGate.Release();
        }
    }

    public async Task CompleteAsync(CancellationToken ct = default)
    {
        await _writeGate.WaitAsync(ct).ConfigureAwait(false);
        try { await _file.FlushAsync(ct).ConfigureAwait(false); }
        finally { _writeGate.Release(); }
    }

    public async ValueTask DisposeAsync()
    {
        await _writeGate.WaitAsync().ConfigureAwait(false);
        try { await _file.DisposeAsync().ConfigureAwait(false); }
        finally
        {
            _writeGate.Release();
            _writeGate.Dispose();
        }
    }
}
