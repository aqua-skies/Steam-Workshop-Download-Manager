using System.Windows.Media.Media3D;

namespace Swdm2.App.Ui.Controls.HomeSphere;

/// <summary>
/// 球体节点物理（D5.15;t2 v1.4 §2.8.2 行号级规格，用户亲定条款直译）：
/// - **节点沿球径缓振荡**：每顶点沿法向（球径方向）弹簧阻尼振荡
/// - **1/r² 影响**：鼠标（光源）对顶点位移的影响 ∝ 1/r²（r=顶点到光源距离），
///   近处顶点被推/吸位移大，远处几乎不动
/// - **线刚性**：边（Edges) 长度约束=刚性弹簧 k_high，线框保持球拓扑不散架，
///   仅顶点法向自由度软化
/// - **CPU 逐帧顶点更新**（CompositionTarget.Rendering 60fps 调用 Step;
///   单帧预算 &lt;4ms@1080p 起点观测 ⚠️[参数待重标定]）
/// 纯逻辑层（无 WPF 依赖项，可单元测试断言物理不变量）。
/// </summary>
public sealed class SpherePhysics
{
    private readonly SphereGeometry _geometry;
    private readonly Vector3D[] _baseNormals;
    private readonly double[] _displacement; // 沿法向的位移（球半径单位）
    private readonly double[] _velocity; // 沿法向的速度
    private readonly double[] _restEdgeLength;

    /// <summary>弹簧刚度（沿法向；⚠️[待标定] 起点值）。</summary>
    public double SpringK { get; set; } = 28.0;

    /// <summary>阻尼（振荡衰减；⚠️[待标定]）。</summary>
    public double Damping { get; set; } = 4.5;

    /// <summary>1/r² 鼠标场强度（⚠️[待标定]）。</summary>
    public double MouseFieldStrength { get; set; } = 0.045;

    /// <summary>振幅上限（防止 1/r² 奇点近处位移爆炸；⚠️[待标定]）。</summary>
    public double MaxDisplacement { get; set; } = 0.035;

    /// <summary>线刚性边长约束刚度（k_high;⚠️[待标定]）。</summary>
    public double EdgeStiffness { get; set; } = 60.0;

    /// <summary>每顶点累计边修正（线刚性的一次 iterations 投影）。</summary>
    public int EdgeIterations { get; set; } = 2;

    /// <summary>模拟时间缩放（慢动作观测/测试用；1.0=实时）。</summary>
    public double TimeScale { get; set; } = 1.0;

    public SpherePhysics(SphereGeometry geometry)
    {
        ArgumentNullException.ThrowIfNull(geometry);
        _geometry = geometry;
        var n = geometry.Positions.Count;
        _baseNormals = new Vector3D[n];
        _displacement = new double[n];
        _velocity = new double[n];
        _restEdgeLength = new double[geometry.Edges.Count];

        for (var i = 0; i < n; i++)
        {
            var p = geometry.Positions[i];
            _baseNormals[i] = Vector3D.Multiply(1.0, new Vector3D(p.X, p.Y, p.Z));
        }

        for (var e = 0; e < geometry.Edges.Count; e++)
        {
            var (a, b) = geometry.Edges[e];
            _restEdgeLength[e] = Dist(geometry.Positions[a], geometry.Positions[b]);
        }
    }

    /// <summary>单帧物理推进（dt=秒；mouseWorld=光源世界坐标，null=无鼠标场）。</summary>
    public void Step(double dt, Point3D? mouseWorld)
    {
        if (dt <= 0) return;
        dt *= TimeScale;
        var n = _geometry.Positions.Count;

        // ① 沿球径弹簧+1/r² 鼠标场（用户条款直译）
        var accel = new double[n];
        for (var i = 0; i < n; i++)
        {
            // 弹簧回复力 -k*x - c*v
            var a = -SpringK * _displacement[i] - Damping * _velocity[i];

            // 1/r² 鼠标影响（近端大、远端≈0）
            if (mouseWorld is { } mouse)
            {
                var p = CurrentPosition(i);
                var dx = p.X - mouse.X;
                var dy = p.Y - mouse.Y;
                var dz = p.Z - mouse.Z;
                var r2 = dx * dx + dy * dy + dz * dz;
                if (r2 < 1e-6) r2 = 1e-6;
                a += MouseFieldStrength / r2;
            }

            accel[i] = a;
        }

        for (var i = 0; i < n; i++)
        {
            _velocity[i] += accel[i] * dt;
            _displacement[i] += _velocity[i] * dt;
            // 振幅钳制（防奇点爆炸；保护渲染与拓扑）
            if (_displacement[i] > MaxDisplacement) _displacement[i] = MaxDisplacement;
            if (_displacement[i] < -MaxDisplacement) _displacement[i] = -MaxDisplacement;
        }

        // ② 线刚性：边长约束（投影法 iterations 次；线框保持球骨架）
        for (var iter = 0; iter < EdgeIterations; iter++)
        {
            for (var e = 0; e < _geometry.Edges.Count; e++)
            {
                var (a, b) = _geometry.Edges[e];
                var pa = CurrentPosition(a);
                var pb = CurrentPosition(b);
                var dx = pb.X - pa.X;
                var dy = pb.Y - pa.Y;
                var dz = pb.Z - pa.Z;
                var len = Math.Sqrt(dx * dx + dy * dy + dz * dz);
                if (len < 1e-9) continue;

                var rest = _restEdgeLength[e];
                // 线刚性=边长差的比例收缩（单次迭代收回差值的固定比例；
                // 不用增益*dt 复合=避免正反馈爆炸把位移推到 MaxDisplacement
                // 钳值——用户条款是"线刚性骨架不散"，比例收缩是稳定收敛的
                // 投影法，逐帧 iterations 次）
                var diff = (len - rest) / len * 0.5;
                // 单帧边长修正钳制（与位移振幅同量级，不发散）
                var maxStep = MaxDisplacement * 0.25;
                if (diff > maxStep) diff = maxStep;
                if (diff < -maxStep) diff = -maxStep;
                // 沿边方向拉回（位移沿法向投影=不破坏仅法向自由度的软化语义）
                var corr = new Vector3D(dx * diff, dy * diff, dz * diff);
                ProjectToNormal(a, corr, sign: -1);
                ProjectToNormal(b, corr, sign: 1);
            }
        }
    }

    /// <summary>当前顶点位置（基础球面+沿法向位移）。</summary>
    public Point3D CurrentPosition(int index)
    {
        var p = _geometry.Positions[index];
        var normal = _baseNormals[index];
        var d = _displacement[index];
        return new Point3D(
            p.X + normal.X * d,
            p.Y + normal.Y * d,
            p.Z + normal.Z * d);
    }

    /// <summary>位移（测试断言用；沿法向）。</summary>
    public double Displacement(int index) => _displacement[index];

    /// <summary>速度（测试断言用）。</summary>
    public double Velocity(int index) => _velocity[index];

    private void ProjectToNormal(int index, Vector3D correction, double sign)
    {
        var normal = _baseNormals[index];
        var along = correction.X * normal.X + correction.Y * normal.Y + correction.Z * normal.Z;
        _displacement[index] += sign * along;
        if (_displacement[index] > MaxDisplacement) _displacement[index] = MaxDisplacement;
        if (_displacement[index] < -MaxDisplacement) _displacement[index] = -MaxDisplacement;
    }

    private static double Dist(Point3D a, Point3D b)
    {
        var dx = b.X - a.X;
        var dy = b.Y - a.Y;
        var dz = b.Z - a.Z;
        return Math.Sqrt(dx * dx + dy * dy + dz * dz);
    }
}
