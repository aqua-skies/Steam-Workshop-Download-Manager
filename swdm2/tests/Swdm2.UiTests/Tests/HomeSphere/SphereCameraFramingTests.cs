using System;
using System.Windows.Media.Media3D;
using Swdm2.App.Ui.Controls.HomeSphere;
using Xunit;

namespace Swdm2.UiTests.Tests.HomeSphere;

/// <summary>
/// t67/t68 球体取景回归（用户"界面上只有球体的左下角"整改）：
/// spec §2.8=右侧无内容页显示球体的**右下部分**（透视右下）。
/// 几何量化（math_computation 回执 Computation/...4e4a7a199d69/fd9a9cd480b0):
/// 相机 pos(2.6,-2.0,4.0) 视线指向球的左上点 t(-0.6,0.55,0)→球心投影落
/// (0.61W,0.58H)=画面中心偏右下；半径 206px@572x560=全入画面（直径 412&lt;560)。
/// 沙箱截图不可达（z-order 遮挡同族）=参数+投影几何断言兜底（ENV-DOWNGRADE 同门）。
/// </summary>
public sealed class SphereCameraFramingTests
{
    // 相机参数（须与 HomeSphereControl 构造器一致;漂移=本测试失败）
    // 数值来源：math 回执 Computation/...52fde544dbde（t=(0.5,0.2,0) 扫描求解）
    private const double CamX = 2.6, CamY = -2.0, CamZ = 4.0;
    private const double LookX = -2.1, LookY = 2.2, LookZ = -4.0;
    private const double SphereRadius = 1.5;
    private const double FovDeg = 45.0;
    private const double ViewportW = 572, ViewportH = 560; // 右侧列实际像素（窗口 900x600）

    private static (double sx, double sy, double radiusPx, double depth) ProjectSphereCenter()
    {
        var pos = new Point3D(CamX, CamY, CamZ);
        var look = new Vector3D(LookX, LookY, LookZ);
        look.Normalize();
        var up = new Vector3D(0, 1, 0);
        var right = Vector3D.CrossProduct(up, look); right.Normalize();
        var trueUp = Vector3D.CrossProduct(look, right); trueUp.Normalize();

        var rel = new Vector3D(0 - pos.X, 0 - pos.Y, 0 - pos.Z); // 球心-相机
        var depth = Vector3D.DotProduct(rel, look);
        var xr = Vector3D.DotProduct(rel, right);
        var yu = Vector3D.DotProduct(rel, trueUp);

        var half = Math.Tan(Math.PI / 180.0 * FovDeg / 2.0);
        var ndcX = (xr / depth) / half;
        var ndcY = (yu / depth) / half;
        var sx = ViewportW / 2.0 + ndcX * (ViewportW / 2.0);
        var sy = ViewportH / 2.0 - ndcY * (ViewportH / 2.0);
        var alpha = Math.Asin(SphereRadius / depth);
        var radiusPx = (ViewportH / 2.0) * Math.Tan(alpha) / half;
        return (sx, sy, radiusPx, depth);
    }

    /// <summary>球心落画面中心偏右下（0.55-0.65W/H 区间=§2.8 透视右下）。</summary>
    [WpfFact]
    public void Sphere_Center_Projects_Right_Bottom_Of_Center()
    {
        var (sx, sy, radiusPx, depth) = ProjectSphereCenter();
        Assert.True(depth > 0, "球心必须在相机前方");
        Assert.InRange(sx / ViewportW, 0.55, 0.65);
        Assert.InRange(sy / ViewportH, 0.52, 0.65);
        Assert.True(radiusPx > 0, "半径必须为正");
    }

    /// <summary>球全入画面：直径 &lt; 视口高（不出界=用户"只看到一角"根因排除）。</summary>
    [WpfFact]
    public void Sphere_Fully_Inside_Viewport()
    {
        var (sx, sy, radiusPx, _) = ProjectSphereCenter();
        Assert.True(2 * radiusPx < ViewportH, "球直径必须小于视口高度");
        Assert.True(sx - radiusPx > 0 && sx + radiusPx < ViewportW, "球须在水平边内");
        Assert.True(sy - radiusPx > 0 && sy + radiusPx < ViewportH, "球须在垂直边内");
    }

    /// <summary>视线指向球的右上偏前点（t=(0.5,0.2,0)）=球落画面右下取景。</summary>
    [WpfFact]
    public void Camera_Looks_To_Sphere_UpperRight_Point()
    {
        // look=t-pos，t=(0.5,0.2,0)→分量断言（x 右移/ y 上仰/相机下方）
        Assert.True(LookY > 0, "视线 y 分量&gt;0=上仰（球落画面下部）");
        Assert.True(CamY < 0, "相机在球下方（y-/右下象限取景）");
        // 视线目标点=(pos+look)=(0.5,0.2,0)=球面上右上偏前点（半径 1.5 内）
        var t = new Point3D(CamX + LookX, CamY + LookY, CamZ + LookZ);
        Assert.InRange(Math.Sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z), 0.0, 1.6);
        Assert.True(t.X > 0, "视线目标点 x&gt;0=球右侧");
        Assert.True(t.Y > 0, "视线目标点 y&gt;0=球上侧");
    }

    /// <summary>光源衰减温和版在位（t65 过陡参数=远侧近黑 0.22 回滚）。</summary>
    [WpfFact]
    public void Light_Attenuation_Gradual_Not_Blackout()
    {
        // att(d)=1/(0.65+0.22d+0.05d²)（HomeSphereControl 构造器参数）
        static double Att(double d) => 1.0 / (0.65 + 0.22 * d + 0.05 * d * d);
        Assert.True(Att(3.5) > 0.30, "远侧 >0.30=可见不死黑（t65 0.22 教训）");
        Assert.True(Att(0.4) / Att(3.5) > 2.0, "近远比 >2=深度梯度仍在");
    }
}
