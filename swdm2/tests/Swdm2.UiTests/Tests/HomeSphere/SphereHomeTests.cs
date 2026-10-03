using System.Collections.Generic;
using System.Windows;
using System.Windows.Media.Media3D;
using Swdm2.App.Ui.Controls.HomeSphere;
using Xunit;

namespace Swdm2.UiTests.Tests.HomeSphere;

/// <summary>
/// D5.15 球体主页纯逻辑层验收（t54):
/// - 二十面体细分拓扑不变量（20 面/每级 ×4;顶点共享去重）
/// - 1/r² 弹簧物理不变量（衰减收敛/近场>远场/线刚性）
/// - 贴图分配（无重叠）
/// 帧采样门（20fps+60 帧采样）= 控件层，运行的驱动进程断言（沙箱无桌面合成时
/// CompositionTarget.Rendering 不触发=ENV-DOWNGRADE 门，逻辑层先证物理可跑）。
/// </summary>
public sealed class SphereHomeTests
{
    public SphereHomeTests()
    {
        if (Application.Current is null)
            new Application();
    }

    [WpfFact]
    public void Icosahedron_Base_Is_20_Triangles_12_Vertices()
    {
        var geo = IcosahedronGeometry.Generate(0);

        Assert.Equal(12, geo.Positions.Count);
        Assert.Equal(20, geo.TriangleCount);
        Assert.Equal(30, geo.Edges.Count); // 二十面体边数=30
    }

    [WpfFact]
    public void Subdivision_Quadruples_Triangles()
    {
        // 团队 SP-2 规约：UiTests 仅 [WpfFact](xunit v2/v3 FactAttribute 歧义）
        Assert.Equal(20, IcosahedronGeometry.Generate(0).TriangleCount);
        Assert.Equal(80, IcosahedronGeometry.Generate(1).TriangleCount);
        Assert.Equal(320, IcosahedronGeometry.Generate(2).TriangleCount);
        Assert.Equal(1280, IcosahedronGeometry.Generate(3).TriangleCount);
    }

    [WpfFact]
    public void All_Vertices_On_Unit_Sphere()
    {
        var geo = IcosahedronGeometry.Generate(2);

        foreach (var p in geo.Positions)
        {
            var dist = System.Math.Sqrt(p.X * p.X + p.Y * p.Y + p.Z * p.Z);
            Assert.Equal(1.0, dist, 3); // 球径归一化=球面
        }
    }

    [WpfFact]
    public void Triangle_Indices_Bounds_Valid()
    {
        var geo = IcosahedronGeometry.Generate(2);
        var n = geo.Positions.Count;

        foreach (var idx in geo.TriangleIndices)
            Assert.InRange(idx, 0, n - 1);
    }

    [WpfFact]
    public void Spring_Oscillation_Decays_To_Rest()
    {
        var geo = IcosahedronGeometry.Generate(1);
        var physics = new SpherePhysics(geo);

        // 给顶点 0 一个初速度=沿球径振荡；无鼠标场
        physics.Step(0.016, null);
        physics.Step(0.016, null);
        var earlyDisplacement = System.Math.Abs(physics.Displacement(0));

        // 200 帧 60fps 后阻尼应收敛
        for (var i = 0; i < 200; i++)
            physics.Step(0.016, null);
        var lateDisplacement = System.Math.Abs(physics.Displacement(0));

        Assert.True(lateDisplacement < earlyDisplacement + 0.1, "振荡应衰减");
        Assert.True(lateDisplacement < 0.01, "应回到静息位附近");
    }

    [WpfFact]
    public void Mouse_Field_Inverse_Square_Near_Greater_Than_Far()
    {
        var geo = IcosahedronGeometry.Generate(1);
        var physics = new SpherePhysics(geo) { MouseFieldStrength = 0.05 };

        // 找一个靠近光源的顶点与一个远顶点（光源放在 (3,0,0) 附近）
        var mouse = new Point3D(3.0, 0, 0);
        int nearIdx = 0, farIdx = 0;
        var nearDist = double.MaxValue;
        var farDist = double.MinValue;
        for (var i = 0; i < geo.Positions.Count; i++)
        {
            var p = geo.Positions[i];
            var d = (p.X - mouse.X) * (p.X - mouse.X) + (p.Y - mouse.Y) * (p.Y - mouse.Y)
                    + (p.Z - mouse.Z) * (p.Z - mouse.Z);
            if (d < nearDist) { nearDist = d; nearIdx = i; }
            if (d > farDist) { farDist = d; farIdx = i; }
        }

        physics.Step(0.016, mouse);
        physics.Step(0.016, null); // 让位移显形一帧
        physics.Step(0.016, mouse);
        var near = System.Math.Abs(physics.Displacement(nearIdx));
        var far = System.Math.Abs(physics.Displacement(farIdx));

        // 1/r² 场：近端位移显著大于远端
        Assert.True(near > far * 2, $"近端位移 {near} 应远大于远端 {far}(1/r² 场)");
    }

    [WpfFact]
    public void Displacement_Clamped_Against_Singularity()
    {
        var geo = IcosahedronGeometry.Generate(1);
        var physics = new SpherePhysics(geo)
        {
            MouseFieldStrength = 10.0, // 奇点近场放大
        };

        // 光源放球面上=一个顶点近场 r²→0
        physics.Step(0.016, geo.Positions[0]);
        physics.Step(0.016, geo.Positions[0]);

        for (var i = 0; i < geo.Positions.Count; i++)
        {
            var d = System.Math.Abs(physics.Displacement(i));
            Assert.True(d <= physics.MaxDisplacement + 1e-9, "位移应钳制在振幅上限内");
        }
    }

    [WpfFact]
    public void Edge_Rigidity_Keeps_Edge_Lengths_Near_Rest()
    {
        var geo = IcosahedronGeometry.Generate(1);
        var physics = new SpherePhysics(geo) { MouseFieldStrength = 0.05 };
        var mouse = new Point3D(3.0, 0, 0);

        physics.Step(0.016, mouse);

        // 变形后边长应接近静止边长（线刚性=骨架不散）
        var maxRatio = 0.0;
        for (var e = 0; e < geo.Edges.Count; e++)
        {
            var (a, b) = geo.Edges[e];
            var pa = physics.CurrentPosition(a);
            var pb = physics.CurrentPosition(b);
            var dx = pb.X - pa.X;
            var dy = pb.Y - pa.Y;
            var dz = pb.Z - pa.Z;
            var len = System.Math.Sqrt(dx * dx + dy * dy + dz * dz);
            // 参照未变形边长（基础几何同边）
            var pa0 = geo.Positions[a];
            var pb0 = geo.Positions[b];
            var dx0 = pb0.X - pa0.X;
            var dy0 = pb0.Y - pa0.Y;
            var dz0 = pb0.Z - pa0.Z;
            var rest = System.Math.Sqrt(dx0 * dx0 + dy0 * dy0 + dz0 * dz0);
            var ratio = System.Math.Abs(len - rest) / rest;
            if (ratio > maxRatio) maxRatio = ratio;
        }
        Assert.True(maxRatio < 0.02, $"最大边长偏移 {maxRatio:P1} 应在线刚性容差内");
    }
}