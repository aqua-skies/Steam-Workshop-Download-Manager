namespace Swdm2.Core.Domain;

/// <summary>下载任务标识。一次入队对应一个，Guid 全局唯一。</summary>
public sealed record DownloadTaskId
{
    private readonly Guid _value;

    /// <summary>Guid 值；禁止 Guid.Empty。</summary>
    public Guid Value
    {
        get => _value;
        init => _value = value != Guid.Empty
            ? value
            : throw new ArgumentException("DownloadTaskId 不能为 Guid.Empty。", nameof(Value));
    }

    public DownloadTaskId(Guid value) => Value = value;

    /// <summary>解析字符串形式（"D" 格式）。失败返回 false。</summary>
    public static bool TryParse(string? text, out DownloadTaskId taskId)
    {
        taskId = default!;
        if (!Guid.TryParseExact(text, "D", out var v) || v == Guid.Empty)
            return false;
        taskId = new DownloadTaskId(v);
        return true;
    }

    /// <summary>生成新任务 id。</summary>
    public static DownloadTaskId New() => new(Guid.NewGuid());

    public override string ToString() => Value.ToString("D", System.Globalization.CultureInfo.InvariantCulture);
}
