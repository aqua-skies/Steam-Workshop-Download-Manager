namespace Swdm2.Core.Domain;

/// <summary>Steam 游戏标识（WorkshopItem 元数据中的 AppId）。</summary>
/// <remarks>C6：与 <see cref="UgcId"/>/<see cref="PublishedFileId"/> 完全不同的类型，编译期不可互换。</remarks>
public sealed record AppId
{
    /// <summary>AppId 数值。Steam 平台约定为正数。</summary>
    public int Value { get; init; } = Value != 0
        ? Value
        : throw new ArgumentException("AppId 不能为 0。", nameof(Value));

    public AppId(int value) { }

    /// <summary>解析字符串形式（如 "440"）。失败返回 false。</summary>
    public static bool TryParse(string? text, out AppId appId)
    {
        appId = default!;
        if (!int.TryParse(text, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var v) || v <= 0)
            return false;
        appId = new AppId(v);
        return true;
    }

    public override string ToString() => Value.ToString(System.Globalization.CultureInfo.InvariantCulture);

    public static explicit operator int(AppId appId) => appId.Value;
}
