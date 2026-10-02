namespace Swdm2.Core.Domain;

/// <summary>UGC id（DepotDownloader -ugc 参数语义；与工坊物品 id 数值域重叠但语义不同）。</summary>
/// <remarks>
/// C6：与 <see cref="PublishedFileId"/> 是**不同类型**，禁止隐式互换
/// （DepotDownloader #713 学费：换错 id 得 "A task was cancelled"，UI 必须区分提示）。
/// 同一数值的 UgcId 与 PublishedFileId 在领域语义上代表不同实体，永远不应互相代入。
/// </remarks>
public sealed record UgcId
{
    private readonly ulong _value;

    /// <summary>UGC id。Steam 平台约定为非零正数；引入与 <c>with</c> 克隆时强制校验。</summary>
    public ulong Value
    {
        get => _value;
        init => _value = value != 0
            ? value
            : throw new ArgumentException("UgcId 不能为 0。", nameof(Value));
    }

    public UgcId(ulong value) => Value = value;

    /// <summary>解析字符串形式。失败返回 false。</summary>
    public static bool TryParse(string? text, out UgcId id)
    {
        id = default!;
        if (!ulong.TryParse(text, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var v) || v == 0)
            return false;
        id = new UgcId(v);
        return true;
    }

    public override string ToString() => Value.ToString(System.Globalization.CultureInfo.InvariantCulture);

    public static explicit operator ulong(UgcId id) => id.Value;
}
