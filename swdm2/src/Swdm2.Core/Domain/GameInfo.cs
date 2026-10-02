namespace Swdm2.Core.Domain;

/// <summary>
/// 游戏信息。名称/别名归一化在搜索服务（D2/D5）完成——此处仅记录原始值（C1：不可变）。
/// DS AppID 回退（WorkshopDL 经验）：部分 mod 的 content 属于 DS AppID，下载时回退使用。
/// </summary>
public sealed record GameInfo
{
    /// <summary>游戏 AppId。</summary>
    public AppId Id { get; init; }

    /// <summary>游戏显示名（如 "Don't Starve"）。</summary>
    public string Name { get; init; } = string.Empty;

    /// <summary>搜索别名（只读；构造时防御性拷贝，C5）。如 "饥荒" / "Don't Starve Together"。</summary>
    public IReadOnlyList<string> Aliases { get; init; } = Array.Empty<string>();

    /// <summary>专用服务器 AppId 回退（可空）。</summary>
    public AppId? DsAppIdFallback { get; init; }

    /// <summary>主构造：别名防御性拷贝。</summary>
    public GameInfo(AppId id, string name, IEnumerable<string>? aliases = null, AppId? dsAppIdFallback = null)
    {
        Id = id;
        Name = name;
        Aliases = (aliases ?? Enumerable.Empty<string>()).ToArray();
        DsAppIdFallback = dsAppIdFallback;
    }

    /// <summary>结构性相等：别名逐元素比较（C5，同 <see cref="WorkshopItem"/>）。</summary>
    public bool Equals(GameInfo? other)
        => other is not null
           && Id == other.Id
           && Name == other.Name
           && Aliases.SequenceEqual(other.Aliases)
           && DsAppIdFallback == other.DsAppIdFallback;

    /// <summary>与 <see cref="Equals(GameInfo)"/> 一致的结构性哈希。</summary>
    public override int GetHashCode()
    {
        var hash = new HashCode();
        hash.Add(Id);
        hash.Add(Name);
        hash.Add(DsAppIdFallback);
        foreach (var alias in Aliases)
            hash.Add(alias);
        return hash.ToHashCode();
    }
}
