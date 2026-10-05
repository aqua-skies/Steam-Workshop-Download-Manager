# 球体取景修复（t71 · 2026-10-05 白天复核）

## 问题
用户反馈：界面（右侧页面）只显示球体的左下角。要求：右侧页面显示球体**右下部分**（§2.8 透视右下）。

## 根因（两次迭代归纳）
1. **几何**：t54 相机取景角度使球心偏出画面中心、球大部分越界（用户只见一角）。
2. **光照**：t65 光衰减过陡（`0.35/0.55/0.18`，远侧衰减到 0.22≈近黑）→ 球面可见亮区只剩一小块，用户误读为"取景只拍到角落"。
3. **尺寸**：t68 修正后球心虽落 0.62W/0.57H，但半径 206px → 右缘 901 > 视口 890，**被裁 11px**（真实截图像素证据见下）。

## 交付参数（HomeSphereControl.xaml.cs）
```csharp
_camera = new PerspectiveCamera(
    new Point3D(3.46, -2.66, 5.32),
    new Vector3D(-2.81, 3.11, -5.52),   // 视线目标点 t=(0.65,0.45,-0.2)
    new Vector3D(0, 1, 0), 45);

_mouseLight = new PointLight
{
    Color = "#3ED598",
    Range = 10.0,
    ConstantAttenuation = 0.55,
    LinearAttenuation = 0.18,
    QuadraticAttenuation = 0.02,
};
// AmbientLight 0.4 白
```
数学求解回执：`Computation/...3111e44503a0`（扫描 t 使球心=右栏 0.62W/0.58H 且半径≈150）。
'|pos|' 5.72（t68)→7.6（t71)。

## 投影量化（视口 572x560，右栏起点 x=308）
| 项 | t68 旧 | t71 新 |
|---|---|---|
| 球心屏幕 | (695,335) | (662,325) |
| 球心占比 | 0.62W/0.57H | **0.618W/0.58H（右下）** |
| 半径 px | 206 | **152（直径 304<560)** |
| 右缘 | 901>890 **裁 11px** | 814 **完整入画** |
| 近/远亮度 | 1.26/0.49 | **1.0/0.57** |

## 真实截图证据（白天交互桌面）
- 工具：FlaUI 5.0.0 `Capture.Element(window)`（窗口级，避免全屏 z-order 遮挡）。
  临时工具：`swdm2/.dtmp/SphereCapture/`（`dotnet run` → 启动 App → 等 3.5s 编排稳帧 → 截 MainShell）。
- **旧（t68 参数）** `docs/process/shots/sphere_framing_day_1607.png`：行跨度分析球左缘 487-547 迁移、右缘恒贴 889；采样球面 lum 仅 24-88（暗）。
- **新（t71 参数）** `docs/process/shots/sphere_framing_day_1629.png`：
  - 以预测球心 (662,325) 8 方向径向采样：**45°（右下）r60-140 持续 59-70 偏亮、r160 降到 51、r200 到背景 45**=右下方向**亮区半径≈150 与数学预测 152 吻合**；
  - 0°（正右）r60-200 全为背景 43-48=**球右缘在视口内未被裁切**（右缘 814<890);
  - 135-225°（左侧）暗（32-39)=球背光面，立体朝向正确（光从右上 PointLight 来）。
- 读图工具本机不可用（`read_image` sharp ERR_DLOPEN_FAILED、`modlens` key invalid)=像素分布/径向采样量化兜底（同族几何量化方法论）。

## 契约测试
`tests/Swdm2.UiTests/Tests/HomeSphere/SphereCameraFramingTests.cs`（常量与构造器一致性；漂移即失败）：
- 球心投影落 0.55-0.65W / 0.52-0.65H（右下取景）；
- 球全入画面（直径 < 视口高、四边在内）；
- 视线目标点=t 在球半径内且 x>0/y>0（右上点）；
- 光衰减近远比 >2、远侧 >0.30（不死黑=t65 教训）。
HomeSphere 套件 15/0。

## 复跑方法（白天交互桌面）
```pwsh
dotnet build swdm2\src\Swdm2.App -warnaserror
swdm2\.dtmp\SphereCapture\bin\Debug\net8.0-windows\SphereCapture.exe
# 像素复核（pwsh）:径向采样以 (662,325) 为心,45° 方向亮区应在 r≈140-150 衰减到背景
```

## 版本足迹
t54 初版取景 → t65 光衰减过陡（近黑）→ t68 相机 t=(0.5,0.2,0)（右缘裁切）→ **t71 拉远取景 + 光提亮（完整无裁 + 明亮立体）**。
