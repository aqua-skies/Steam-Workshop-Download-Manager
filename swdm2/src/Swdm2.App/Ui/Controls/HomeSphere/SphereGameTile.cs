using System.Windows.Media;

namespace Swdm2.App.Ui.Controls.HomeSphere;

/// <summary>
/// 球体主页贴图游戏瓦片（D5.15;t2 v1.4 §2.8.1「部分三角面贴游戏图标」）。
/// 图标=方形裁剪贴边（方形 UV 0-1 stretch 到三角形包围盒，贴边对齐）。
/// </summary>
public sealed record SphereGameTile
{
    /// <summary>游戏 AppId（点击跳该游戏的 mod 选择页）。</summary>
    public int AppId { get; init; }

    /// <summary>游戏名（对话泡泡显示文本）。</summary>
    public string Title { get; init; } = string.Empty;

    /// <summary>方形图标位图（贴图源；null=未绑定用纯色占位不贴图）。</summary>
    public ImageSource? Icon { get; init; }

    /// <summary>绑定的三角面索引集合（在 SphereGeometry.TriangleIndices 中的三角形序号）。</summary>
    public IReadOnlyList<int> AssignedTriangles { get; init; } = Array.Empty<int>();
}
