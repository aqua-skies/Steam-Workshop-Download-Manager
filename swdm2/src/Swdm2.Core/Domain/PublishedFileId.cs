namespace Swdm2.Core.Domain;

/// <summary>工坊物品 id（与 Steam Web API 一致，ulong）。</summary>
/// <remarks>
/// C6：与 <see cref="UgcId"/> 是**不同类型**，禁止隐式互换
/// （DepotDownloader #713 学费：换错 id 得 "A task was cancelled"，UI 必须区分提示）。
/// </remarks>
public sealed record PublishedFileId
{
    private readonly ulong _value;

    /// <summary>工坊物品 id。Steam 平台约定为非零正数；引入与 <c>with</c> 克隆时强制校验。</summary>
    public ulong Value
    {
        get => _value;
        init => _value = value != 0
            ? value
            : throw new ArgumentException("PublishedFileId 不能为 0。", nameof(Value));
    }

    public PublishedFileId(ulong value) => Value = value;

    /// <summary>解析字符串形式（如 "3808352517"）。失败返回 false。</summary>
    public static bool TryParse(string? text, out PublishedFileId id)
    {
        id = default!;
        if (!ulong.TryParse(text, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var v) || v == 0)
            return false;
        id = new PublishedFileId(v);
        return true;
    }

    public override string ToString() => Value.ToString(System.Globalization.CultureInfo.InvariantCulture);

    public static explicit operator ulong(PublishedFileId id) => id.Value;
}
