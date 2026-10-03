using System.Windows.Media.Media3D;

namespace Swdm2.App.Ui.Controls.HomeSphere;

/// <summary>
/// 二十面体细分球几何（D5.15;t2 v1.4 §2.8.1 行号级规格）。
/// 二十面体 12 顶点 20 面 → 每次细分每三角形中点分裂（归一化到单位球）。
/// subdivision=3 → 20×4³=1280 三角面（⚠️[参数待标定]：先观测 CPU 顶点量再定，
/// v1.4 规格起点 subdivision=3)。
/// 点/线/三角面三拓扑：Positions（共享顶点）+TriangleIndices+Normals（球径法向）。
/// 顶点共享=同位置顶点唯一（细分中点去重），线刚性约束（§2.8.2）基于 Edges 集合。
/// </summary>
public static class IcosahedronGeometry
{
    /// <summary>生成细分球几何（单位球，半径 1)。</summary>
    /// <param name="subdivision">细分级别（0=正二十面体）。</param>
    /// <returns>Positions（唯一顶点）/TriangleIndices/Edges（无向边去重）。</returns>
    public static SphereGeometry Generate(int subdivision)
    {
        if (subdivision < 0)
            throw new ArgumentOutOfRangeException(nameof(subdivision));

        var phi = (1.0 + Math.Sqrt(5.0)) / 2.0;

        // 二十面体 12 顶点（黄金比例）
        var baseVerts = new[]
        {
            (0.0, 1.0, phi), (0.0, -1.0, phi), (0.0, 1.0, -phi), (0.0, -1.0, -phi),
            (1.0, phi, 0.0), (-1.0, phi, 0.0), (1.0, -phi, 0.0), (-1.0, -phi, 0.0),
            (phi, 0.0, 1.0), (-phi, 0.0, 1.0), (phi, 0.0, -1.0), (-phi, 0.0, -1.0),
        };

        // 20 面（顶点索引，右手系外法向）
        var baseTris = new[]
        {
            (0, 1, 8), (0, 8, 4), (0, 4, 5), (0, 5, 9), (0, 9, 1),
            (1, 7, 6), (1, 6, 8), (8, 6, 10), (8, 10, 4), (4, 10, 2),
            (4, 2, 5), (5, 2, 11), (5, 11, 9), (9, 11, 3), (9, 3, 1),
            (1, 3, 7), (7, 3, 10), (10, 3, 2), (6, 7, 10), (11, 2, 3),
        };

        var positions = new List<Point3D>(baseVerts.Length);
        var indexMap = new Dictionary<(int, int, int), int>();
        for (var i = 0; i < baseVerts.Length; i++)
        {
            var (x, y, z) = baseVerts[i];
            var p = Normalize(x, y, z);
            positions.Add(new Point3D(p.X, p.Y, p.Z));
            indexMap[(i, -1, -1)] = i;
        }

        // 三角形→顶点索引列表（阶段细分用）
        var triangles = new List<int>(baseTris.Length * 3);
        foreach (var t in baseTris)
        {
            triangles.Add(t.Item1);
            triangles.Add(t.Item2);
            triangles.Add(t.Item3);
        }

        for (var level = 0; level < subdivision; level++)
        {
            var newTriangles = new List<int>(triangles.Count * 4);
            var midCache = new Dictionary<(int, int), int>();

            for (var i = 0; i < triangles.Count; i += 3)
            {
                var a = triangles[i];
                var b = triangles[i + 1];
                var c = triangles[i + 2];

                var ab = Midpoint(positions, a, b, positions, midCache);
                var bc = Midpoint(positions, b, c, positions, midCache);
                var ca = Midpoint(positions, c, a, positions, midCache);

                // 一面裂四面（外法向保持）
                newTriangles.Add(a); newTriangles.Add(ab); newTriangles.Add(ca);
                newTriangles.Add(ab); newTriangles.Add(b); newTriangles.Add(bc);
                newTriangles.Add(ca); newTriangles.Add(bc); newTriangles.Add(c);
                newTriangles.Add(ab); newTriangles.Add(bc); newTriangles.Add(ca);
            }

            triangles = newTriangles;
        }

        // 边集合（无向去重；线刚性约束用 §2.8.2)
        var edges = new HashSet<(int, int)>();
        for (var i = 0; i < triangles.Count; i += 3)
        {
            AddEdge(edges, triangles[i], triangles[i + 1]);
            AddEdge(edges, triangles[i + 1], triangles[i + 2]);
            AddEdge(edges, triangles[i + 2], triangles[i]);
        }

        return new SphereGeometry(positions, triangles, edges.OrderBy(e => e).ToArray());
    }

    private static int Midpoint(List<Point3D> target, int i, int j,
        List<Point3D> positions, Dictionary<(int, int), int> midCache)
    {
        var key = i < j ? (i, j) : (j, i);
        if (midCache.TryGetValue(key, out var cached))
            return cached;

        var a = positions[i];
        var b = positions[j];
        var p = Normalize((a.X + b.X) / 2, (a.Y + b.Y) / 2, (a.Z + b.Z) / 2);
        var idx = target.Count;
        target.Add(new Point3D(p.X, p.Y, p.Z));
        midCache[key] = idx;
        return idx;
    }

    private static void AddEdge(HashSet<(int, int)> edges, int i, int j)
    {
        edges.Add(i < j ? (i, j) : (j, i));
    }

    /// <summary>归一化到单位球（法向=球径方向，t2 §2.8.1 规格）。</summary>
    public static (double X, double Y, double Z) Normalize(double x, double y, double z)
    {
        var len = Math.Sqrt(x * x + y * y + z * z);
        if (len < 1e-12)
            return (0, 0, 0);
        return (x / len, y / len, z / len);
    }
}

/// <summary>细分球几何快照（不可变；物理层在其上叠加位移）。</summary>
public sealed record SphereGeometry(
    IReadOnlyList<Point3D> Positions,
    IReadOnlyList<int> TriangleIndices,
    IReadOnlyList<(int A, int B)> Edges)
{
    /// <summary>三角面数（subdivision=3 → 1280)。</summary>
    public int TriangleCount => TriangleIndices.Count / 3;
}
