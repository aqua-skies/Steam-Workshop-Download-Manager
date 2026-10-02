using System.Text.Json;

namespace Swdm2.Downloads.Segments;

/// <summary>
/// `.download` 尾部元数据续存（D4.5,spec §3.3 IResumeStore/D7):
/// - 文件=&lt;产物路径&gt;.download,JSON 体（ResumeMetadata)
/// - 写=原子（临时文件+移动，防 kill 中损坏——kill 后续传门的核心不变量）
/// - 读=不存在/损坏→null（损坏元数据=重新下载，不报错）
/// </summary>
public interface IResumeStore
{
    /// <summary>读元数据（不存在/损坏→null)。</summary>
    ResumeMetadata? Load(string destinationPath);

    /// <summary>原子写元数据。</summary>
    Task SaveAsync(string destinationPath, ResumeMetadata metadata, CancellationToken ct = default);

    /// <summary>全部完成后删除续存。</summary>
    void Delete(string destinationPath);
}

public sealed class JsonResumeStore : IResumeStore
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>.download 续存路径约定。</summary>
    public static string StorePathFor(string destinationPath) => destinationPath + ".download";

    public ResumeMetadata? Load(string destinationPath)
    {
        var path = StorePathFor(destinationPath);
        if (!File.Exists(path)) return null;
        try
        {
            using var stream = File.OpenRead(path);
            return JsonSerializer.Deserialize<ResumeMetadata>(stream, Options);
        }
        catch
        {
            return null; // 损坏=重下（D7:不直接报错）
        }
    }

    public async Task SaveAsync(string destinationPath, ResumeMetadata metadata, CancellationToken ct = default)
    {
        var path = StorePathFor(destinationPath);
        var tmp = path + ".tmp";
        await using (var stream = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None,
                         bufferSize: 4096, useAsync: true))
        {
            await JsonSerializer.SerializeAsync(stream, metadata, Options, ct).ConfigureAwait(false);
        }
        File.Move(tmp, path, overwrite: true); // 原子（同卷）
    }

    public void Delete(string destinationPath)
    {
        var path = StorePathFor(destinationPath);
        if (File.Exists(path)) File.Delete(path);
    }
}
