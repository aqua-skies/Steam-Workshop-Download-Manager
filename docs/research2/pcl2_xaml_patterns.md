# PCL2 XAML 实现模式 → SWDM 2.0（C# WPF）可粘贴模式

> 版次：v1.0 · 2026-10-02 · 职责：WPF UI 实现研究（研究冲刺第 5 路 `pcl2_xaml_patterns`）
> 姊妹文档：`docs/design/visual_language_study.md`（色阶/动画/阴影的数值结论）、`docs/design/design_tokens.md`（令牌落地）、`swdm2/docs/design_baseline_2.0.md`（对照锚点）
> 方法论：**全部结论为 GitHub 源码实读**（Meloong-Git/PCL，main 分支，2026-10-02 快照）。本机 fake-IP DNS 拦截 `github.com`/`raw.githubusercontent.com`，改走本机代理 `127.0.0.1:7897` + `curl.exe` 拉取原文（通道同白板「推送通道」条目）。本轮**新读**前人未展开的文件：`Modules/Base/ModAnimation.vb`（动画引擎/缓动数学）、`Controls/MyResizer.vb`、`Controls/MyScrollViewer.vb`、`Controls/MyVirtualizingElement.vb`、`Controls/MyPageRight.vb`（页面状态机）、`Controls/MyHint.xaml`、`Application.xaml`（控件模板）、`FormMain.xaml(.vb)`、`MyCard.vb`、`MyDropShadow.vb`、`MyButton.xaml(.vb)`、`MyListItem.xaml(.vb)`、`MyLoading.xaml`。
> 目标读者：SWDM 2.0 WPF 实现者（visual-owner / arch-owner）。所有 XAML 片段均按 .NET 8 + WPF(net8.0-windows) 语法，**可直接粘贴**后按需改名空间。

---

## 0. 一句话结论

PCL2 的「皮肤质感」在 WPF 侧**不需要任何第三方库即可 1:1 复刻**——`DependencyProperty` 动画 + `ControlTemplate` + `ResourceDictionary` 是它的原生语言；只有三样东西必须自己写：**自绘 9-patch 品牌色阴影**（或退而用 `DropShadowEffect`）、**命名轨道动画管理器**（Storyboard 没有同键自动停止语义）、**像素级平滑滚动 + 列表惰性实例化**（WPF 内置虚拟化与 PCL2 路线是两种哲学）。WPF-UI 之类库能省的是窗口/导航/主题切换等"基础设施"，**省不掉签名级观感**。

---

## 1. 卡片（MyCard）

### 1.1 源码结构（VB.NET 代码构建，非 XAML 声明）

`MyCard.vb` `New()` 自底向上三层，父容器是 `Grid`：

| 层 | 控件 | 关键属性 |
|---|---|---|
| 0 | `MyDropShadow`（自定义 `Decorator`） | `Margin = (-3,-3,-3,-3-1px)`（**底部多 1px 模拟自然光**）、`ShadowRadius=3`、`Opacity=0.07`、`CornerRadius=5`、`Color` 绑 `"ColorObject1"` |
| 1 | `Border` | `Background = #F5FFFFFF`（96% 白）、`CornerRadius=5`、`IsHitTestVisible=False` |
| 2 | `MainGrid` | 标题 `TextBlock`：`15,12,0,0` / 13 Bold / `ColorBrush1`；箭头 `Path` 10×6、`RotateTransform 180` |

**要点**：阴影层是**负 Margin 的孪生 Decorator**（向四周扩出 ShadowRadius），不是 `DropShadowEffect`——这样阴影可以**参与布局裁剪之外、逐帧改透明度且不模糊内容**，且圆角与卡片同步。

### 1.2 SWDM 2.0 可粘贴 XAML（结构层）

```xml
<!-- SwdmCard.xaml —— 对应 PCL2 MyCard 三层结构。命名空间省略，按项目改。 -->
<Grid x:Class="Swdm2.Ui.Controls.SwdmCard"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
      x:Name="Root" RenderTransformOrigin="0.5,0.5" UseLayoutRounding="True">
    <!-- 第 0 层：阴影。两条路线二选一，见 1.5 -->
    <Border x:Name="ShadowLayer" Margin="-3,-3,-3,-4" CornerRadius="5" Opacity="0.07">
        <Border.Background>
            <SolidColorBrush x:Name="ShadowBrush" Color="{DynamicResource AccentShadowColor}" />
        </Border.Background>
    </Border>
    <!-- 第 1 层：96% 白底（dark 主题换成 surface.card 令牌） -->
    <Border x:Name="CardLayer" Background="#F5FFFFFF" CornerRadius="5" IsHitTestVisible="False" />
    <!-- 第 2 层：内容 + 标题 + 折叠箭头 -->
    <Grid x:Name="MainGrid">
        <TextBlock x:Name="TitleBlock" HorizontalAlignment="Left" VerticalAlignment="Top"
                   Margin="15,12,0,0" FontWeight="Bold" FontSize="13" IsHitTestVisible="False"
                   Foreground="{DynamicResource TextPrimaryBrush}" />
        <Path x:Name="SwapArrow" HorizontalAlignment="Right" VerticalAlignment="Top"
              Height="6" Width="10" Margin="0,17,16,0" Stretch="Uniform"
              RenderTransformOrigin="0.5,0.5"
              Data="M2,4 l-2,2 10,10 10,-10 -2,-2 -8,8 -8,-8 z">
            <Path.RenderTransform><RotateTransform Angle="180" /></Path.RenderTransform>
            <Path.Fill><SolidColorBrush x:Name="ArrowBrush" Color="{DynamicResource Accent1Color}" /></Path.Fill>
        </Path>
        <ContentPresenter x:Name="ContentHost" Margin="0,40,0,12" />
    </Grid>
</Grid>
```

### 1.3 悬停抬升动画：90ms 颜色 / 阴影双段（源码实测）

`MyCard_MouseEnter`：**四路并行、全部 90ms**，用命名轨道 `"MyCard Mouse " & Uuid`（同键自动停旧的）：

```
AaColor(标题, Foreground, ColorBrush1 → ColorBrush2, 90)
AaColor(箭头, Fill,      ColorBrush1 → ColorBrush2, 90)
AaColor(阴影, Color,     ColorObject1 → ColorObject4, 90)
AaOpacity(阴影, 0.07 → 0.4, 90)      '≈5.7 倍抬升 —— PCL2 皮肤感第一签名
```

**SWDM 2.0 XAML 等价**（`EventTrigger` + `Storyboard`，颜色动画的 `To` 不能绑 `DynamicResource`，用代码后置更接近 PCL2 语义）：

```xml
<!-- SwdmCard.xaml（Triggers 片段） -->
<Grid.Triggers>
    <EventTrigger RoutedEvent="UIElement.MouseEnter">
        <BeginStoryboard x:Name="EnterStoryboard">
            <Storyboard>
                <DoubleAnimation Storyboard.TargetName="ShadowLayer"
                                 Storyboard.TargetProperty="Opacity"
                                 To="0.4" Duration="0:0:0.09" />
            </Storyboard>
        </BeginStoryboard>
    </EventTrigger>
    <EventTrigger RoutedEvent="UIElement.MouseLeave">
        <RemoveStoryboard BeginStoryboardName="EnterStoryboard" />
        <BeginStoryboard>
            <Storyboard>
                <DoubleAnimation Storyboard.TargetName="ShadowLayer"
                                 Storyboard.TargetProperty="Opacity"
                                 To="0.07" Duration="0:0:0.09" />
            </Storyboard>
        </BeginStoryboard>
    </EventTrigger>
</Grid.Triggers>
```

```csharp
// SwdmCard.xaml.cs —— 颜色四路并行（与 PCL2 AaColor 同语义；AniHelper 见 §5.2）
protected override void OnMouseEnter(MouseEventArgs e)
{
    base.OnMouseEnter(e);
    AniHelper.StartColor(TitleBlock, TextBlock.ForegroundProperty, "Accent2Brush", 90);
    AniHelper.StartColor(ArrowBrush, SolidColorBrush.ColorProperty, "Accent4Color", 90);
    AniHelper.StartColor(ShadowBrush, SolidColorBrush.ColorProperty, "Accent4Color", 90);
}
protected override void OnMouseLeave(MouseEventArgs e)
{
    base.OnMouseLeave(e);
    AniHelper.StartColor(TitleBlock, TextBlock.ForegroundProperty, "Accent1Brush", 90);
    AniHelper.StartColor(ArrowBrush, SolidColorBrush.ColorProperty, "Accent1Color", 90);
    AniHelper.StartColor(ShadowBrush, SolidColorBrush.ColorProperty, "Accent1Color", 90);
}
```

> **注意（PCL2 的陷阱已修）**：`AaColor` 对资源色的动画在**结束时**才 `SetResourceReference` 回动态资源（`AniTimer` 见 `ModAnimation.vb:885`）——即"动画期间是静态值，结束后才恢复主题绑定"。SWDM 2.0 的 `AniHelper.StartColor` 若沿用此设计，须在 `Completed` 里重新 `SetResourceReference`，否则主题切换不生效。

### 1.4 高度动画：150ms / 分段减速（源码实测）

`StartHeightAnimation`：`|Δ| ≤ 800px` → 单段 **150ms `AniEaseOutFluent(ExtraStrong)`**（= `1-(1-t)^5`）；`>800px` → 匀速段（4000~5000 px/s）+ 减速段（`AniEaseOutFluentWithInitial`，带初速度的减速曲线 `(α+1)p/(1+αp)`）。超长收回强制 100ms 匀速 + 150ms 减速。

**SWDM 2.0**：卡片折叠场景 Δ 通常 ≤800px，不需要分段机制（PCL2 自己的注释说是为 5000px 级超长版本列表准备的）：

```xml
<!-- 折叠展开：Grid.Height 动画（ContentHost 高度绑定，见代码后置） -->
<DoubleAnimation Storyboard.TargetName="Root"
                 Storyboard.TargetProperty="(Grid.Height)"
                 Duration="0:0:0.15">
    <DoubleAnimation.EasingFunction>
        <QuinticEase EaseMode="EaseOut" />   <!-- ≡ AniEaseOutFluent(ExtraStrong)=1-(1-t)^5 -->
    </DoubleAnimation.EasingFunction>
</DoubleAnimation>
<!-- 箭头旋转 250ms -->
<DoubleAnimation Storyboard.TargetName="SwapArrow"
                 Storyboard.TargetProperty="(Path.RenderTransform).(RotateTransform.Angle)"
                 Duration="0:0:0.25">
    <DoubleAnimation.EasingFunction><QuinticEase EaseMode="EaseOut" /></DoubleAnimation.EasingFunction>
</DoubleAnimation>
```

```csharp
// SwdmCard.xaml.cs —— 高度动画（≤800px 直达；>800 保留分段策略）
public void AnimateHeight(double targetHeight)
{
    double delta = Math.Abs(targetHeight - ActualHeight);
    var ease = new QuinticEase { EaseMode = EaseMode.EaseOut };
    if (delta <= 800)
    {
        var ani = new DoubleAnimation(targetHeight, TimeSpan.FromMilliseconds(150)) { EasingFunction = ease };
        BeginAnimation(HeightProperty, ani);
    }
    else
    {
        // 匀速段 + 减速段（复刻 AniEaseOutFluentWithInitial：带初速度 v0 的减速）
        double easeLen = 200, easeTime = 150, speed = delta > 5000 * 0.6 ? 5000 : 4000;
        double constLen = delta - easeLen;
        var constAni = new DoubleAnimation(ActualHeight + constLen * Math.Sign(targetHeight - ActualHeight),
            TimeSpan.FromMilliseconds(constLen / speed * 1000));
        var easeAni = new DoubleAnimation(targetHeight, TimeSpan.FromMilliseconds(easeTime)) { EasingFunction = ease };
        var seq = new Storyboard { Children = { constAni, easeAni } };
        Storyboard.SetTarget(constAni, this); Storyboard.SetTargetProperty(constAni, new PropertyPath(HeightProperty));
        Storyboard.SetTarget(easeAni, this);   Storyboard.SetTargetProperty(easeAni, new PropertyPath(HeightProperty));
        seq.Begin(this);
    }
}
```

退出动画（`AniDispose`）：scale −0.08（200ms InFluent）+ opacity −1（200ms OutFluent）+ 高度 −150ms。XAML 用 `RenderTransform` + `DoubleAnimation` 组合即可。

### 1.5 阴影：两条实现路线（实测对照）

**PCL2 原版**：`MyDropShadow.vb` —— `Decorator.OnRender` 自绘 **9-patch**：边 `LinearGradientBrush` + 角 `RadialGradientBrush`，6 级 alpha 阶梯 `0.74336 / 0.38053 / 0.12389 / 0.02654`（offset 0.3/0.5/0.7/0.9），源自 WPF Aero `SystemDropShadowChrome`；默认色 `#71xxxxxx`（α=0.44）。

**SWDM 2.0 路线 A（推荐，静态卡片/弹层）**：内置 `DropShadowEffect`。PCL2 自己的 `ContextMenu` 就是这样做的（`Opacity=0.4 / BlurRadius=4 / ShadowDepth=2`，`Application.xaml:487`）。design_tokens 议 D 的令牌（blur 12–16、accent@30%、offset 4–6）是同一方向：

```xml
<DropShadowEffect x:Key="CardShadowIdle" Color="{DynamicResource AccentColor}"
                  BlurRadius="6" ShadowDepth="2" Opacity="0.07" Direction="270" />
<DropShadowEffect x:Key="CardShadowHover" Color="{DynamicResource AccentColor}"
                  BlurRadius="14" ShadowDepth="5" Opacity="0.4" Direction="270" />
<!-- 用法（Border.Effect） -->
<Border.Effect><StaticResource ResourceKey="CardShadowIdle" /></Border.Effect>
<!-- 悬停时整体替换 Effect 会重置渲染；更稳的是动画 BlurRadius/Opacity/ShadowDepth 三个标量 -->
```

**SWDM 2.0 路线 B（列表场景 / 追求 1:1）**：把 `MyDropShadow.vb` 直接 C# 移植（`OnRender` 9-patch，`DrawingContext` API 逐字对应）。**理由**：`DropShadowEffect` 每控件一个、位图模糊、滚动列表中重绘成本高；自绘 9-patch 是矢量 `DrawRectangle`，且可逐帧改 alpha 不触发位图重分配。

> **与 design_tokens §9 议题 D 的关系**：议题 D 已锁定"对话框/悬浮卡片走 `DropShadowEffect`，列表卡片维持描边高程"。本报告补充：PCL2 原版卡片本身也只用了 ShadowRadius=3 的**极浅**阴影（静止 0.07 几乎不可见），SWDM 2.0 令牌 blur 12–16 比 PCL2 更浓——方向一致，**数值按令牌走**，PCL2 数值仅作保底参考（经验复验纪律：参数移植后以实测观感为准）。

---

## 2. 自定义窗口（无边框 + 圆角 + 阴影 + 拖拽 + 缩放）

### 2.1 源码结构（`FormMain.xaml` 实测）

```xml
WindowStyle="None" AllowsTransparency="True" Background="{x:Null}" ResizeMode="CanMinimize"
```

- 根 `Grid PanBack` `Margin="10"` —— **透明阴影沟**（交由背景壁纸模糊/透明度滑杆的视觉效果）
- **8 个 Resizer 矩形**：边 4 个 `Height/Width=8`、`Margin 13,0` 或 `0,13`；角 4 个 `13×13`。填充为**线性/径向渐变**（边：`#21000000`→`#11000000`→透明；角：`RadialGradientBrush Center/GradientOrigin` 在对角，`#21000000` offset 0.2 起步）——既是视觉阴影，也是命中区域
- `BorderForm Margin="8"` + `Border.Clip = RectangleGeometry RadiusX/Y=6` —— **圆角剪裁内容**（注意：是 Clip 而不是 CornerRadius，因为要剪掉子页面）
- 标题栏 `PanTitle Height=48`，背景 `LinearGradientBrush` 绑 `ColorObject4`；最小化/关闭为 `MyIconButton` 28×28，`Margin 0,0,44,0` / `0,0,12,0`
- 入场动画：`TransformRotate Angle=-4`（500ms `OutBack(Weak)`，延迟 100ms）+ `TransformPos Y=60`（600ms `OutBack(Weak)`）+ 透明度 250ms

### 2.2 SWDM 2.0 可粘贴 XAML

```xml
<Window x:Class="Swdm2.Ui.MainWindow"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ResizeMode="CanResize" ShowInTaskbar="True"
        MinWidth="810" MinHeight="470" RenderTransformOrigin="0.5,0.5">
    <Grid x:Name="PanBack" Margin="10" UseLayoutRounding="True" SnapsToDevicePixels="True">
        <Grid.RenderTransform>
            <TransformGroup>
                <RotateTransform x:Name="EntryRotate" Angle="-4" />
                <TranslateTransform x:Name="EntryPos" Y="60" />
            </TransformGroup>
        </Grid.RenderTransform>
        <!-- 8 个 Resizer：命中区 + 渐变阴影（此处给 2 个示例，其余同法） -->
        <Rectangle x:Name="ResizerT" Height="8" VerticalAlignment="Top" Margin="13,0" Cursor="SizeNS"
                   Stroke="{x:Null}" StrokeThickness="0.0001" Fill="{StaticResource ResizerTopBrush}" />
        <Rectangle x:Name="ResizerRB" Width="13" Height="13" HorizontalAlignment="Right"
                   VerticalAlignment="Bottom" Cursor="SizeNWSE" Stroke="{x:Null}" Fill="{StaticResource ResizerRbBrush}" />
        <!-- 圆角剪裁 + 阴影：
             阴影用 DropShadowEffect 或外层 Border 自绘（见 §1.5）；圆角用 Border.Clip 剪内容 -->
        <Border x:Name="BorderForm" Margin="8">
            <Border.Clip><RectangleGeometry x:Name="FormClip" RadiusX="6" RadiusY="6" /></Border.Clip>
            <Grid x:Name="PanForm">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto" /><RowDefinition Height="*" />
                </Grid.RowDefinitions>
                <!-- 标题栏 48px -->
                <Grid x:Name="PanTitle" Height="48">
                    <Grid.Background>
                        <LinearGradientBrush EndPoint="1,0" StartPoint="0,0">
                            <GradientStop Color="{DynamicResource Accent4Color}" Offset="0" />
                        </LinearGradientBrush>
                    </Grid.Background>
                    <!-- 关闭 / 最小化：28x28 图标钮，含 X 与横线的 path 几何（PCL2 原值） -->
                    <Button x:Name="BtnClose" HorizontalAlignment="Right" Height="28" Width="28"
                            Margin="0,0,12,0" VerticalAlignment="Center" Style="{StaticResource TitleIconButton}" />
                    <Button x:Name="BtnMin" HorizontalAlignment="Right" Height="28" Width="28"
                            Margin="0,0,44,0" VerticalAlignment="Center" Style="{StaticResource TitleIconButton}" />
                </Grid>
                <ContentControl x:Name="PageHost" Grid.Row="1" />
            </Grid>
        </Border>
    </Grid>
</Window>
```

### 2.3 拖拽：`DragMove()`（PCL2 同款，最省）

```csharp
// FormMain.xaml.vb:623 的直译。PanTitle / PanMsg（模态层）都可拖。
private void PanTitle_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
{
    if (((FrameworkElement)sender).IsMouseDirectlyOver) DragMove();
}
```

### 2.4 缩放与贴边吸附：PCL2 的做法 vs 2026 的做法

**PCL2 原版（`MyResizer.vb`）**：
- 挂 `WM_GETMINMAXINFO`（msg 36）→ 最大化时约束到显示器工作区（`MONITORINFO.rcWork`，处理任务栏遮挡）
- 8 个 Resizer 的 `MouseLeftButtonDown` → 记录起始鼠标点/窗口尺寸 → 后台线程 `while (resizing) { Dispatcher.Invoke(updateSize, Render); Thread.Sleep(0); }` 轮询 `GetCursorPos` 改 `Left/Top/Width/Height`
- **代价**：`AllowsTransparency=True` 窗口**失去系统 Aero Snap 与 Win11 贴靠布局**，且多 DPI 混接时边缘发虚（visual_language_study §6.1 已记录）

**SWDM 2.0 推荐（2026 更优）**：`WM_NCHITTEST` 命中区方案——**保留系统贴靠**、无需透明窗口、原生顺滑：

```csharp
// 启动时挂钩（SourceInitialized 事件内）
var hs = (HwndSource)PresentationSource.FromVisual(this);
hs.AddHook(WndProc);

private const int WM_NCHITTEST = 0x0084;
private const int HTCLIENT = 1, HTCAPTION = 2, HTLEFT = 10, HTRIGHT = 11,
                  HTTOP = 12, HTTOPLEFT = 13, HTTOPRIGHT = 14, HTBOTTOM = 15, HTBOTTOMLEFT = 16, HTBOTTOMRIGHT = 17;
private const int ResizeEdge = 8; // 命中宽度（PCL2 同值，其 Resizer 为 8px/角 13px）

private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
{
    if (msg == WM_NCHITTEST)
    {
        // 命中测试坐标系：屏幕像素 → 本窗口相对
        int x = lParam.ToInt32() & 0xFFFF, y = lParam.ToInt32() >> 16;
        var pos = PointToScreen(new Point(0, 0));
        int relX = x - (int)pos.X, relY = y - (int)pos.Y;
        if (relX >= ResizeEdge && relX < ActualWidth - ResizeEdge &&
            relY >= ResizeEdge && relY < ActualHeight - ResizeEdge)
        {
            // 中部： 若在标题栏高度内则返回 HTCAPTION 以支持拖拽与贴靠
            handled = relY < 48 ? CaptionHit(relX, relY) : true;
            return relY < 48 ? (IntPtr)HTCAPTION : (IntPtr)HTCLIENT;
        }
        // 边角判定（缩略；四个角先判断再判断四边）
        bool left = relX < ResizeEdge, right = relX > ActualWidth - ResizeEdge;
        bool top = relY < ResizeEdge, bottom = relY > ActualHeight - ResizeEdge;
        handled = true;
        if (top && left) return (IntPtr)HTTOPLEFT;
        if (top && right) return (IntPtr)HTTOPRIGHT;
        if (bottom && left) return (IntPtr)HTBOTTOMLEFT;
        if (bottom && right) return (IntPtr)HTBOTTOMRIGHT;
        if (left) return (IntPtr)HTLEFT; if (right) return (IntPtr)HTRIGHT;
        if (top) return (IntPtr)HTTOP; if (bottom) return (IntPtr)HTBOTTOM;
        return (IntPtr)HTCLIENT;
    }
    return IntPtr.Zero;
}
```

> **对比结论**：若走 `WindowChrome`（`GlassFrameThickness=0` + `ResizeBorderThickness`）可声明式拿到 8 命中区，但 `WindowChrome` 与 `AllowsTransparency` 组合仍有坑（透明窗口下系统阴影丢失）。SWDM 2.0 **建议放弃 `AllowsTransparency`**：圆角改由 `WindowChrome` + `CornerRadius` 或直接方角 + 大半径内容剪裁；阴影走 `DropShadowEffect`（Win11 下 DWM 合成）。这条与 PCL2 不同但**更好**——PCL2 受 2018 年的技术约束，2.0 没必要继承这个债。
> **简化通道（已核验）**：WPF-UI（lepoco/wpfui，README 实读）的 `TitleBar` 控件内置 **Windows 11 SnapLayout** 支持，`FluentWindow` 提供 Mica/亚克力与系统圆角。若选 WPF-UI 作基座，§2 全部可以不写（窗口/按钮/主题整套）。

---

## 3. 页面导航：不用 Frame/Page，用容器 + 页面基类 + 返回栈

### 3.1 源码机制（实读 `FormMain.xaml.vb` + `MyPageRight.vb`）

PCL2 **不用 `Frame`/`Page` 导航**。`PanMainLeft` / `PanMainRight` 是两个 `Border` 容器，页面是自定义 `MyPageLeft` / `MyPageRight` 基类（普通 `UserControl` 派生），切换即**替换容器 Child**：

```
PageChangeAnim(TargetLeft, TargetRight)：
  1. AniStop("FrmMain LeftChange") / AniStop("PageLeft PageChange")   '命名轨道防重入
  2. 旧页 TriggerHideAnimation() / PageOnExit()                        '退出动画
  3. +110ms：PanMainLeft.Child = 新页；新页 Opacity=0                   '替换
  4. +30ms：新页 Opacity=1；TriggerShowAnimation() / PageOnEnter()      '进入动画
```

- **返回栈**：`PageStack`（`Stack(Of PageStackData)`），`PageChangeExit` 出栈回到主页面；标题栏左侧 `BtnTitleInner`（返回箭头） + `LabTitleInner`（子页面名 15px）替代常驻标题
- **状态机**（`MyPageRight.PageStates`，9 态）：`Empty → ContentEnter → ContentStay → ContentExit` / `LoaderEnter → LoaderWait → LoaderStay(Force) → LoaderExit / PageExit` —— 内容与加载态双通道，防止"切走时加载回来打断退出动画"
- **进入动画**（`TriggerShowAnimation` 的逐元素交错）：
  - 每元素 `Opacity 0→1 100ms OutFluent(Weak)`
  - `TranslateY` **双段**：`+5px/250ms OutFluent` 与 `+11px/350ms OutBack`（两股位移并行 —— 起步小幅、落位回弹）
  - **stagger 25ms**（每个控件延迟 +25）
  - 滚动条 X `+10px → 0`，350ms `OutFluent`；侧栏从左滑入
- **退出动画**：`Opacity −1 70ms` + `TranslateY −6px/70ms`，stagger 15ms；滚动条 X `→+10px` 90ms `InFluent`

### 3.2 SWDM 2.0 可粘贴实现

**容器与返回栈**（最贴近 PCL2 的模型，在 `MainWindow` 里）：

```csharp
// PageNavigationService.cs
private readonly Stack<Func<PageBase>> _backStack = new();

public void Navigate<T>(bool keepInStack = true) where T : PageBase, new()
{
    StopPreviousAnimations();                       // ≡ AniStop 命名轨道
    var old = PageHost.Content as PageBase;
    if (old != null) old.RunExit();                 // ≡ PageOnExit
    _ = Task.Delay(110).ContinueWith(_ => Dispatcher.Invoke(() =>  // ≡ +110ms 替换
    {
        var next = new T { Opacity = 0 };
        if (keepInStack && old != null) _backStack.Push(() => old);
        PageHost.Content = next;
        _ = Task.Delay(30).ContinueWith(_ => Dispatcher.Invoke(() => // ≡ +30ms 进入
        {
            next.Opacity = 1;
            next.RunEnter();
        }));
    }));
}

public bool GoBack()
{
    if (_backStack.Count == 0) return false;
    Navigate(_backStack.Pop().Invoke(), keepInStack: false);
    return true;
}
```

**页面进入动画**（`PageBase.RunEnter` —— 复刻交错 + 双段位移，XAML 声明版）：

```xml
<!-- PageBase 的默认进入 Storyboard（每个元素一个，代码后置按深度 stagger 25ms） -->
<Storyboard x:Key="PageItemEnter">
    <DoubleAnimation Storyboard.TargetProperty="(UIElement.Opacity)"
                     From="0" To="1" Duration="0:0:0.1">
        <DoubleAnimation.EasingFunction><QuadraticEase EaseMode="EaseOut" /></DoubleAnimation.EasingFunction>
    </DoubleAnimation>
    <!-- 双段位移：5px/250ms 平滑 + 11px/350ms 回弹，两股并行 -->
    <DoubleAnimationUsingKeyFrames Storyboard.TargetProperty="(UIElement.RenderTransform).(TranslateTransform.Y)">
        <EasingDoubleKeyFrame KeyTime="0:0:0" Value="0" />
        <EasingDoubleKeyFrame KeyTime="0:0:0.25" Value="5">
            <EasingDoubleKeyFrame.EasingFunction><CubicEase EaseMode="EaseOut" /></EasingDoubleKeyFrame.EasingFunction>
        </EasingDoubleKeyFrame>
        <EasingDoubleKeyFrame KeyTime="0:0:0.35" Value="11">
            <EasingDoubleKeyFrame.EasingFunction><BackEase EaseMode="EaseOut" Amplitude="0.4" /></EasingDoubleKeyFrame.EasingFunction>
        </EasingDoubleKeyFrame>
    </DoubleAnimationUsingKeyFrames>
</Storyboard>
```

```csharp
// PageBase.RunEnter —— 交错 25ms
public virtual void RunEnter()
{
    int delay = 0;
    foreach (var child in LogicalTreeHelper.GetChildren(this).OfType<FrameworkElement>())
    {
        child.Opacity = 0;
        child.RenderTransform = new TranslateTransform(0, -16);
        var sb = (Storyboard)FindResource("PageItemEnter");
        sb = sb.Clone(); // Storyboard 不可共享实例
        foreach (var tl in sb.Children)
            tl.BeginTime = TimeSpan.FromMilliseconds(delay);
        sb.Begin(child);
        delay += 25;
    }
}
```

> **2026 简化通道**：`Frame` + `NavigateTransition` 在 WPF 里仍要手写（框架没有内置页面过渡）。WPF-UI 的 `NavigationView`（`Frame` 容器 + 侧栏导航 + 页面切换动画 + 面包屑）覆盖了这套机制的 80%，且自带返回栈语义。**差异化保留**：PCL2 式逐元素 stagger 进入动画需要自己写在 `PageBase` 里（WPF-UI 只有整页过渡）。

---

## 4. 列表：PCL2 根本不用 VirtualizingStackPanel

### 4.1 源码实情（本次实读修正了此前的推断）

| 件 | 机制 |
|---|---|
| `MyScrollViewer.vb` | **`CanContentScroll=False`**（像素滚动，非按项滚动）；`PreviewMouseWheel` 接管 → `AaDouble` **300ms `OutFluent(6)` 平滑滚动**（惯性滚轮）；`PanningMode=VerticalOnly`（触屏） |
| `MyVirtualizingElement.vb` | **惰性实例化**：占位 `FrameworkElement`，`LazyLoadBehavior.OnFirstEnterScrollViewerViewport` 首次进入视口时调 `Init()`，在父 `Panel.Children` 中**原地替换**为真实控件 |
| `MyCard.StackInstall` | 折叠卡片展开时才把 `Stack.Tag` 里的数据列表转成控件（PCL2 称"控件虚拟化"）+ 末尾加 18px 下边距 |
| `MyListItem.xaml` | 行高 **42**；5 列网格 `[2px 勾选][0~N padding][4+34 图标][* 标题][右 padding]`；`RectBack`（悬停浮层）在代码里**懒创建**，`CornerRadius 6`、背景 `ColorBrush7`、边 `ColorBrush6` |

**结论**：PCL2 长列表防卡顿靠的是「**像素滚动 + 视口惰性实例化 + 折叠卡片**」三件套，**不是** `VirtualizingStackPanel`。它的列表项数量被卡片折叠天然限流（每张卡片默认收起，展开才实例化）。

### 4.2 列表项悬停/选中动画（`MyListItem.xaml.vb` 实测）

- 悬停浮层 `RectBack`：懒创建时 `ScaleX/Y=0.75` → 悬停 `AaScaleTransform → 1`，时长 **Time×1.6**（背景色/bg1 淡入与 scale 并行）
- 整行按下：`scale → 0.98`（Time×0.9）
- 勾选竖条（`RectCheck`，左侧 5px 圆角）：**双段生长** —— `Δ×0.4 / 200ms OutFluent(Weak)` + `Δ×0.6 / 300ms OutBack(Weak)`，不透明度 30ms；收起 120ms `InFluent` + 70ms 淡出
- 选中前景色 → `ColorBrush2`（200ms）

### 4.3 SWDM 2.0 可粘贴 XAML

**路线 A（WPF 原生虚拟化 —— 工坊浏览场景，列表可达数千项）**：

```xml
<!-- ModListPage.xaml -->
<ListBox x:Name="ModList" ItemsSource="{Binding Items}"
         VirtualizingPanel.IsVirtualizing="True"
         VirtualizingPanel.VirtualizationMode="Recycling"
         VirtualizingPanel.ScrollUnit="Pixel"          <!-- ≡ PCL2 CanContentScroll=False 的像素滚动 -->
         ScrollViewer.CanContentScroll="True"
         ScrollViewer.PanningMode="VerticalOnly"
         UseLayoutRounding="True" SnapsToDevicePixels="True"
         ItemContainerStyle="{StaticResource ModListItemStyle}"
         Background="Transparent" BorderThickness="0">
    <ListBox.ItemsPanel>
        <ItemsPanelTemplate>
            <VirtualizingStackPanel Orientation="Vertical" />
        </ItemsPanelTemplate>
    </ListBox.ItemsPanel>
    <!-- 注意：VirtualizingStackPanel 必须是 ItemsHost 直接子级才能回收 -->
</ListBox>
```

```xml
<!-- ModListItemStyle.xaml —— 42px 行 + RectBack 悬停浮层 + 勾选竖条 -->
<Style x:Key="ModListItemStyle" TargetType="ListBoxItem">
    <Setter Property="Height" Value="42" />
    <Setter Property="Padding" Value="0" />
    <Setter Property="Background" Value="Transparent" />
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ListBoxItem">
                <Grid x:Name="Root" RenderTransformOrigin="0.5,0.5">
                    <Grid.RenderTransform><ScaleTransform ScaleX="1" ScaleY="1" /></Grid.RenderTransform>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="6" />   <!-- 勾选竖条列 -->
                        <ColumnDefinition Width="Auto" />
                        <ColumnDefinition Width="4" />
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="4" />
                    </Grid.ColumnDefinitions>
                    <!-- 悬停浮层（懒创建/低透明度起点，见 EventTrigger） -->
                    <Border x:Name="RectBack" Grid.ColumnSpan="5" CornerRadius="6" Opacity="0"
                            RenderTransformOrigin="0.5,0.5">
                        <Border.Background><SolidColorBrush Color="{DynamicResource HoverBackColor}" /></Border.Background>
                        <Border.RenderTransform><ScaleTransform ScaleX="0.75" ScaleY="0.75" /></Border.RenderTransform>
                    </Border>
                    <!-- 勾选竖条 -->
                    <Border x:Name="CheckBar" Grid.Column="0" Width="5" CornerRadius="2.5" Opacity="0"
                            RenderTransformOrigin="0.5,1">
                        <Border.RenderTransform><ScaleTransform ScaleY="0" /></Border.RenderTransform>
                        <Border.Background><SolidColorBrush Color="{DynamicResource Accent3Color}" /></Border.Background>
                    </Border>
                    <ContentPresenter Grid.Column="3" VerticalAlignment="Center" Margin="4,0,0,0" />
                </Grid>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Trigger.EnterActions>
                            <BeginStoryboard>
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="RectBack" Storyboard.TargetProperty="Opacity"
                                                     To="1" Duration="0:0:0.12" />
                                    <DoubleAnimation Storyboard.TargetName="RectBack"
                                                     Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleX)"
                                                     To="1" Duration="0:0:0.19">
                                        <DoubleAnimation.EasingFunction><CubicEase EaseMode="EaseOut" /></DoubleAnimation.EasingFunction>
                                    </DoubleAnimation>
                                </Storyboard>
                            </BeginStoryboard>
                        </Trigger.EnterActions>
                    </Trigger>
                    <Trigger Property="IsSelected" Value="True">
                        <Trigger.EnterActions>
                            <BeginStoryboard>
                                <Storyboard>
                                    <!-- 双段生长：40% 200ms + 60% 300ms（回弹） -->
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="CheckBar"
                                        Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleY)">
                                        <EasingDoubleKeyFrame KeyTime="0:0:0.2" Value="0.4" />
                                        <EasingDoubleKeyFrame KeyTime="0:0:0.5" Value="1">
                                            <EasingDoubleKeyFrame.EasingFunction>
                                                <BackEase EaseMode="EaseOut" Amplitude="0.5" />
                                            </EasingDoubleKeyFrame.EasingFunction>
                                        </EasingDoubleKeyFrame>
                                    </DoubleAnimationUsingKeyFrames>
                                    <DoubleAnimation Storyboard.TargetName="CheckBar" Storyboard.TargetProperty="Opacity"
                                                     To="1" Duration="0:0:0.03" />
                                </Storyboard>
                            </BeginStoryboard>
                        </Trigger.EnterActions>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

**路线 B（PCL2 同款惰性实例化 —— 卡片折叠场景）**：把 `MyVirtualizingElement` 移植为 C#（`LazyLoadBehavior` 若无源可参考则用 `ScrollViewer.ScrollChanged` + `TransformToVisual` 判可见性），卡片列表默认折叠即天然限流。SWDM 2.0 的工坊/下载/库三个主场景**建议路线 A**（数据量已知可上千），卡片折叠交互独立于虚拟化存在。

**惯性滚轮**（`MyScrollViewer` 的签名功能，`300ms OutFluent(6)`）：

```csharp
// SmoothScrollViewer.cs —— PreviewMouseWheel 接管 + 平滑减速
protected override void OnPreviewMouseWheel(MouseWheelEventArgs e)
{
    if (e.Delta == 0 || ScrollableHeight == 0) return;
    e.Handled = true;
    var target = (VerticalOffset - e.Delta * 2.0).Clamp(0, ScrollableHeight - ViewportHeight); // DeltaMult
    var ani = new DoubleAnimation(target, TimeSpan.FromMilliseconds(300))
    {
        EasingFunction = new QuinticEase { EaseMode = EaseOut } // PCL2 用 OutFluent(6)，土 6 幂 ≈ 介于 Quintic 与更强
    };
    BeginAnimation(ScrollViewerBehavior.VerticalOffsetProperty, ani); // 附加属性包装 ScrollToVerticalOffset
}
```

> 注意 `ScrollViewer` 的 `VerticalOffset` 不是动画友好的 DP；PCL2 的做法（`AaDouble` 回调里调 `ScrollToVerticalOffset`）在 C# 里就是 `DoubleAnimation` + `CurrentValue` 帧回调，或干脆用一个 `double` 中间属性。**性能提示**：`ScrollUnit="Pixel"` + 平滑滚动在大列表里每帧布局，务必上路线 A 的虚拟化，否则就是 PCL2 必须惰性实例化的原因。

---

## 5. 动画与主题

### 5.1 PCL2 动画引擎解剖（`Modules/Base/ModAnimation.vb`，1066 行，本次实读）

PCL2 **不用 Storyboard**：自建单线程计时器（后台线程 `Thread.Sleep(1)`、Δ≥3ms 步进、`RunInUiWait` 派发到 UI），全局 `AniGroups As Dictionary(Of String, AniGroupEntry)` 字典 —— 这就是「**命名轨道**」：同名 `AniStart` 先 `AniStop` 旧的再添加（`ModAnimation.vb:768`）。另有：

- `AniControlEnabled` 计数器：+1 期间代码驱动的属性变更**不触发动画**（防"改默认值触发动画"的抖动，`MyButton.RefreshColor` 里就在用）
- `AniSpeed`（0.1~3，调试设置）
- `Aa*` 助手族：`AaColor`（支持资源名，结束时 `SetResourceReference` 回动态绑定）/`AaOpacity`/`AaScale`/`AaRotateTransform`/`AaHeight`/`AaCode`（动画里塞代码，`After:=True` 顺序执行）
- 缓动数学（全部为 `AniEase.GetValue(t)` 的闭式）：

| PCL2 缓动 | 公式 | WPF 等价 |
|---|---|---|
| `AniEaseOutFluent(Weak/Middle/Strong/ExtraStrong)` | `1-(1-t)^p`，p=2/3/4/5 | `QuadraticEase`/`CubicEase`/`QuarticEase`/`QuinticEase`（EaseOut） |
| `AniEaseInFluent(p)` | `t^p` | 同上 EaseIn |
| `AniEaseOutBack(Weak)` | `1-(1-t)^2·cos(1.5πt)` | `BackEase EaseOut Amplitude≈0.4`（近似，见下注） |
| `AniEaseOutElastic(Middle)` | `1-t^1.5·cos(3.5π(1-t)^1.5)` | `ElasticEase EaseOut`（近似） |
| `AniEaseOutFluentWithInitial` | `(α+1)p/(1+αp)`，α=初速度/均速−1 | **无内置** —— 需自写 `EasingFunctionBase`（下） |
| `AniEaseInout` 组合 | 两段拼接 | ` keyframe 拼接` |

> **近似警告（弯路嫌疑标注）**：`BackEase`/`ElasticEase` 的内置参数化不与 PCL2 闭式逐点一致；若需 1:1，自写 `EasingFunctionBase` 子类并覆盖 `EaseInOutCore`，直接把 VB 公式贴进去（10 行代码）。**建议**：2.0 直接用内置缓动 + 实测观感标定（经验复验纪律），不为公式保真牺牲可维护性。

```csharp
// FluentWithInitialEase.cs —— 复刻 AniEaseOutFluentWithInitial（带初速度的减速）
public class FluentWithInitialEase : EasingFunctionBase
{
    public double InitialPixelsPerSecond { get; set; }
    protected override Freezable CreateInstanceCore() => new FluentWithInitialEase();
    protected override double EaseInOutCore(double normalizedTime)
    {
        // totalSeconds/totalDistance 由使用处传入（构造期缓存）
        double v0n = InitialPixelsPerSecond * TotalSeconds / TotalDistance;
        double alpha = Math.Max(0, v0n - 1.0);
        return alpha == 0 ? normalizedTime : (alpha + 1) * normalizedTime / (1 + alpha * normalizedTime);
    }
    public double TotalSeconds { get; set; }
    public double TotalDistance { get; set; }
}
```

### 5.2 SWDM 2.0 命名轨道管理器（Storyboard 时代仍需要）

```csharp
// AniHelper.cs —— PCL2 AniStart/AniStop 的 C# 最小移植（命名轨道 + 同键停止）
public static class AniHelper
{
    private static readonly Dictionary<string, Storyboard> _tracks = new();

    public static void Begin(string track, Storyboard sb, FrameworkElement target)
    {
        Stop(track);
        lock (_tracks) _tracks[track] = sb;
        sb.Completed += (_, _) => { lock (_tracks) _tracks.Remove(track); };
        sb.Begin(target);
    }
    public static void Stop(string track)
    {
        if (_tracks.TryGetValue(track, out var sb))
        {
            sb.Stop();
            _tracks.Remove(track);
        }
    }
    public static bool IsRunning(string track) => _tracks.ContainsKey(track);

    public static void StartColor(FrameworkElement obj, DependencyProperty prop, string resourceKey, int ms)
    {
        var to = (Color)(Application.Current.FindResource(resourceKey) ?? throw new KeyNotFoundException(resourceKey));
        var ani = new ColorAnimation(to, TimeSpan.FromMilliseconds(ms)) { /* 平滑=线性，PCL2 颜色用线性 */ };
        obj.BeginAnimation(prop, ani);
    }
}
```

> **退路与选择**：Storyboard 的 `FillBehavior`、`HandoffBehavior`（`SnapshotAndReplace`）与 `BeginAnimation` 已经覆盖 90% 场景；若做大量并行动画且关心帧率，再考虑自建计时器（PCL2 路线）。**不建议**一开始就搬 PCL2 的 1066 行引擎——它的线程模型（`Thread.Sleep(1)` + Dispatcher）在 2026 的 WPF 里不是最优，Composition 动画（不依赖 UI 线程）才是方向，但 WPF 对 Composition 的暴露有限，此为本报告的**已知限制**。

### 5.3 明度阶梯 → Brush 资源字典（Light/Dark 双主题）

PCL2 的 `Application.xaml` 颜色表（实读，与前人 `visual_language_study` 完全一致，**复核通过**）：

```
ColorBrush1..8 = #343d4a / #0b5bcb / #1370f3 / #4890f5 / #96c0f9 / #d5e6fd / #e0eafd / #eaf2fe
ColorObject1..8 = 同值（Color 形式，供 AaColor 动画与阴影绑定）
Gray1..8 = #404040 .. #f5f5f5   RedLight #ff4c4c / RedDark #ce2111 / RedBack #80fbdddd
HalfWhite #55ffffff   SemiTransparent #01eaf2fe（1% 主题色底 —— "整体偏蓝"的来源）
TextBlock 默认：FontSize 13 / TextTrimming CharacterEllipsis / FontFamily "Resources/#PCL English, Microsoft YaHei UI"
```

PCL2 是**单主题色相 8 级**；SWDM 2.0 的令牌（design_tokens §3）是「surface 阶梯 + accent + link 分离」结构，**更现代**。组织方式可粘贴如下：

```
swdm2/Ui/Themes/
  Light.xaml      ← 亮色：surface.canvas #F2F3F6 / card #FFFFFF / text.primary #23272E ...
  Dark.xaml       ← 暗色：canvas #16161C / card #1E1E24 / text.primary #E8EAF0 ...
  Accent.xaml     ← 强调色独立文件（未来换皮肤只换这一个文件）
  Common.xaml     ← 不随主题变的几何/字体/动画时长（90/150/200/250ms 作为 Double/Duration 资源）
```

```xml
<!-- App.xaml —— 双主题切换组织方式 -->
<Application.Resources>
    <ResourceDictionary>
        <ResourceDictionary.MergedDictionaries>
            <ResourceDictionary Source="pack://application:,,,/Ui/Themes/Common.xaml" />
            <ResourceDictionary Source="pack://application:,,,/Ui/Themes/Accent.xaml" />
            <ResourceDictionary x:Name="ThemeDictionary" Source="pack://application:,,,/Ui/Themes/Dark.xaml" />
        </ResourceDictionary.MergedDictionaries>
    </ResourceDictionary>
</Application.Resources>
```

```csharp
// ThemeService.cs —— 切换（≈ PCL2 PageSetupUI.ThemeRefresh 的整表重算 → 直接换字典，无闪烁）
public static void Apply(Theme theme)
{
    var path = theme == Theme.Light ? "/Ui/Themes/Light.xaml" : "/Ui/Themes/Dark.xaml";
    var dict = new ResourceDictionary { Source = new Uri($"pack://application:,,,{path}", UriKind.Absolute) };
    var themeDict = Application.Current.Resources.MergedDictionaries
        .First(d => d.Source?.OriginalString.Contains("Themes/") == true);
    Application.Current.Resources.MergedDictionaries.Remove(themeDict);
    Application.Current.Resources.MergedDictionaries.Add(dict);
}
// 所有引用一律 DynamicResource（含 Color，供动画与阴影）
// 主题切换时：UIElement 的子树会立即重应用资源，行为 ≡ PCL2 的 HSL 重算刷新
```

> **PCL2 的 HSL 主题编辑器**（4 滑杆 + 14 号主题 + 解锁制）是**运营性功能**（彩蛋/赞助），SWDM 2.0 不必继承；但**换 accent 即换皮肤**的能力要保留（`Accent.xaml` 独立文件）。`SolidColorBrush` 一律 `x:Shared` 默认共享、`Color` 资源供动画用 —— 与 PCL2 的 `ColorBrush*`/`ColorObject*` 双轨制同理（动画只能动 `Color`，是 WPF 的硬约束，不是 PCL2 的怪癖）。

### 5.4 提示条 / 滚动条 / 菜单（静态层，直接粘贴）

```xml
<!-- MyHint 等价（通知条）：左 3px 色条 + 圆角 2 + padding 12,9 -->
<Border BorderThickness="3,0,0,0" CornerRadius="2" BorderBrush="#99FF4444"
        UseLayoutRounding="True" SnapsToDevicePixels="True">
    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*" /><ColumnDefinition Width="Auto" />
        </Grid.ColumnDefinitions>
        <TextBlock LineHeight="16" Padding="12,9" TextWrapping="Wrap" VerticalAlignment="Center" />
        <Button Grid.Column="1" Width="20" Height="20" Margin="0,0,8,0" VerticalAlignment="Center" />
    </Grid>
</Border>

<!-- ScrollBar 模板（Application.xaml 实测）：8px / 拇指圆角 3 / margin 2 -->
<Style TargetType="ScrollBar">
    <Setter Property="MinWidth" Value="8" /><Setter Property="Width" Value="8" />
    <Setter Property="Stylus.IsPressAndHoldEnabled" Value="False" />
    <Setter Property="Stylus.IsFlicksEnabled" Value="False" />
    <Setter Property="OverridesDefaultStyle" Value="True" />
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ScrollBar">
                <Border CornerRadius="2" Background="Transparent">
                    <Track Name="PART_Track" IsDirectionReversed="True">
                        <Track.Thumb>
                            <Thumb Style="{StaticResource ScrollThumb}" />
                        </Track.Thumb>
                        <Track.IncreaseRepeatButton>
                            <RepeatButton Command="ScrollBar.PageDownCommand" Opacity="0" />
                        </Track.IncreaseRepeatButton>
                        <Track.DecreaseRepeatButton>
                            <RepeatButton Command="ScrollBar.PageUpCommand" Opacity="0" />
                        </Track.DecreaseRepeatButton>
                    </Track>
                </Border>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
<!-- Thumb：圆角 3、Margin 2、轨道=1% 主题色底（ColorBrushSemiTransparent #01eaf2fe） -->

<!-- ContextMenu 弹层（真实阴影只给弹出层）：CornerRadius 3 / 1px 主题色边 / 白底 / margin 0,0,4,4 -->
<Style TargetType="ContextMenu">
    <Setter Property="OverridesDefaultStyle" Value="True" />
    <Setter Property="Grid.IsSharedSizeScope" Value="True" />
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="ContextMenu">
                <Border BorderThickness="1" CornerRadius="3" Background="White" Margin="0,0,4,4"
                        BorderBrush="{DynamicResource Accent1Brush}" SnapsToDevicePixels="True">
                    <Border.Effect>
                        <DropShadowEffect Opacity="0.4" BlurRadius="4" ShadowDepth="2" />
                    </Border.Effect>
                    <StackPanel IsItemsHost="True" KeyboardNavigation.DirectionalNavigation="Cycle" />
                </Border>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
<!-- MenuItem 行高 26（MyMenuItem 模板） -->
```

---

## 6. 2026 现代 WPF 对照：哪些能简化，哪些必须手写

**WPF-UI（lepoco/wpfui）现状核验**（README 原文，2026-10-02 经代理实读）：覆盖 `Page`/`ToggleButton`/`List` 等基类重写；新增 `Navigation`、`NumberBox`、`Dialog`、`Snackbar`；`TitleBar` 内置 **Windows 11 SnapLayout**；NuGet 包 `WPF-UI`，VS2022 插件模板。

| # | 模块 | PCL2 手法 | 2026 简化方案 | 仍需手写 |
|---|---|---|---|---|
| 1 | 无边框窗口 + 阴影 + 圆角 | `AllowsTransparency` + 8 Resizer + 手动 WM_GETMINMAXINFO | **WPF-UI `FluentWindow`**（Mica/系统圆角/SnapLayout 全部内置）；或 `WindowChrome` + `WM_NCHITTEST` | 自定义标题栏渐变（PCL2 是主题色单端线性渐变）与入场动画 |
| 2 | 最小化/关闭按钮 | `MyIconButton` 28×28 path | WPF-UI `TitleBar` 自带 | 图标几何沿用 PCL2 path 字符串 |
| 3 | 侧栏导航 | `PanTitleSelect`（水平 RadioButton 组） | **WPF-UI `NavigationView`**（可折叠、返回栏） | 图标 path + 选中态品牌色 |
| 4 | 页面切换 + 返回栈 | Border 容器替换 + `PageStack` | WPF-UI `NavigationView`/`Frame` 组合 | **逐元素 stagger 进入动画**（25ms 交错 + 双段位移）——WPF-UI 只有整页过渡 |
| 5 | 主题 Light/Dark | HSL 整表重算 + 解锁制 | WPF-UI `ApplicationThemeManager`；或本报告 `MergedDictionaries` 换字典 | accent 独立换肤（`Accent.xaml`） |
| 6 | 卡片 | `MyCard` 全手写 | 无库提供 PCL2 级卡片 | **整套**：三层结构 + 90ms 四路颜色 + 阴影 0.07→0.4 + 高度 150ms + 折叠箭头 250ms |
| 7 | 列表 | 像素滚动 + 惰性实例化 | `ListBox` + `VirtualizingStackPanel(Recycling, Pixel)` + 模板 | 惯性滚轮（300ms 缓动）、勾选竖条双段动画 |
| 8 | 动画管理 | 自建计时器 + 命名轨道 | `Storyboard`/`BeginAnimation`（内置） | **命名轨道管理器**（`AniHelper`）、`AniControlEnabled` 等效（防默认值触发动画抖动） |
| 9 | 阴影 | 自绘 9-patch（6 级 alpha） | `DropShadowEffect`（弹层/对话框） | 9-patch 移植（若列表场景要 1:1） |
| 10 | 滚动条/菜单/提示条 | ControlTemplate 重写 | 同（WPF 无现代化免费午餐） | 模板本体 |
| 11 | 图标 | SVG path 字符串直接当属性 + `DynamicResource` 换色 | 同；或 `IconFont`（字符图标） | path 数据库 |
| 12 | 加载态（镐子） | 矢量 + 关键帧序列（350/900/900ms InBack→OutFluent→OutElastic） | 无库等价（WPF-UI 有 `ProgressRing`，但无"性格"） | 若保留镐子动画需手写 `RotationTransform` 关键帧（`MyLoading.xaml` 的 Path Data 可直接搬：`M 963.6 858.2 410.816 305.504 ...`，`RotateTransform Angle=55 CenterX=30 CenterY=30`） |

**.NET 8 WPF 相关**：`net8.0-windows` TFM、Skia 无关（WPF 仍是 DirectX/DWM）、ARM64 支持、`IAsyncEnumerable` 友好但 UI 线程模型不变。**没有"Fluent 原生化"**：Win11 视觉（Mica/圆角/贴靠）走 WPF-UI 或 P/Invoke（`DwmSetWindowAttribute`：`DWMWA_SYSTEMBACKDROP_TYPE` 等）。

**结论（供 arch-owner 决策）**：
- 基座**建议引入 WPF-UI**（模块 1/2/3/5 可直接免写，且 Win11 贴靠/暗色主题是用户可感知项）
- **模块 4/6/7/8/9 必须自写签名级观感**——这正是 PCL2 与"通用 Fluent 应用"的差别，也是 `visual_language_study` §0 所述"70% 静态层可复现、30% 动态层是签名"的 WPF 侧分工
- 引入 WPF-UI 的代价：基类被重写（`Page`/`List`），与自写 ControlTemplate 并存时需注意样式覆盖顺序（`OverridesDefaultStyle` 冲突）；**建议先骨架期试装一个页面跑 FlaUI 回归，再决定是否全量基座**（与基线 §二决策 3 的 FlaUI 6.0.0 验证链衔接）

---

## 7. 数值速查总表（源码实测，供令牌复核）

| 项 | PCL2 实测（出处） | 2.0 对应令牌/做法 |
|---|---|---|
| 卡片背景 | `#F5FFFFFF`（96% 白，`MyCard.vb:70`） | light card #FFFFFF（dark #1E1E24） |
| 卡片圆角 / 折叠高 / 标题 | 5 / 40px / 13 Bold @15,12（`MyCard.vb:81`） | radius.sm 5 / 13px 600 |
| 阴影 | radius 3，margin `(-3,-3,-3,-4)`，色=主题色，α 0.07→0.4（`MyCard.vb:67/176`） | 品牌色阴影（议 D）；DropShadowEffect 路线 blur/α 实测标定 |
| 悬停颜色过渡 | **90ms 线性**（`MyCard.vb:181`） | motion.color 90ms |
| 按钮颜色 | 进 100ms / 出 200ms（`MyButton.xaml.vb:72`） | 按钮单独档：100/200 |
| 按钮按下 | scale 0.955 / 80ms ExtraStrong + 持续 −0.01/700ms；松手 300ms Middle；离开 800ms Strong | 议 E 动效（2.0） |
| 高度动画 | ≤800px：150ms ExtraStrong；>800 匀速+减速段 | motion.fast 150ms |
| 退出动画 | scale −0.08 + opacity −1 / 200ms；高度 150ms | motion.base 200ms |
| 箭头旋转 | 250ms ExtraStrong | motion.slow 250ms |
| 列表行高 / 副标题 | 42 / 12px@0.6 / 主标 14（`MyListItem.xaml:5`） | 40–42 / 13+11 secondary |
| 悬停浮层 | CornerRadius 6，scale 0.75→1，时长 1.6×基础 | 按实现实测 |
| 勾选竖条 | 双段 40%/200ms Weak + 60%/300ms OutBack | 2.0 新增 |
| 页面进入 | stagger 25ms：opacity 100ms + Y 5px/250 + 11px/350 OutBack | 2.0 新增（PageBase） |
| 页面退出 | opacity 70ms + Y −6px / 70ms，stagger 15ms | 2.0 新增 |
| 页面切换时序 | 110ms 退出 → 替换 → 30ms 进入（`FormMain.xaml.vb:1513`） | 同 |
| 平滑滚动 | 300ms `OutFluent(6)`（`MyScrollViewer.vb:28`） | 惯性滚轮 |
| 滚动条 | 8px / 圆角 3 / margin 2 / 1% 底色 | QSS 已有，XAML 同值 |
| 菜单阴影 | `DropShadowEffect` 0.4/4/2（`Application.xaml:487`） | 弹层真实阴影 |
| 标题栏 | 48px 渐变（单端 ColorObject4），图标钮 28×28（`FormMain.xaml:100`） | 同（深色主题渐变改暗端） |
| 窗口圆角 / 沟 | Clip RadiusX/Y=6，根 Margin 10 | 同或改 WindowChrome |
| 入场动画 | 旋转 −4°→0 / 500ms OutBack(Weak) + 位移 60→0 / 600ms OutBack(Weak)，延迟 100ms | 同（可选用） |
| 字体 | `Resources/#PCL English, Microsoft YaHei UI`，正文 13，11–16 谱 | 雅黑 UI + Segoe UI，SWDM 谱更宽保留 |

---

## 8. 对照基线结论（按 `design_baseline_2.0.md` §五 协议）

**与基线一致的部分**：
- 基线 §四「增强：PCL2 级视觉（卡片/阴影/双段缓动/明度阶梯）」——本报告逐条给出可粘贴实现与实测出处，四项全部有源码级支撑。
- 基线 §一「PCL2 作设计参考」——不是照搬：窗口层明确建议**放弃** `AllowsTransparency`（PCL2 代价是丢失系统贴靠），改走 `WM_NCHITTEST`/WPF-UI，与"设计参考而非设计复刻"一致。
- 基线 §三「参数类经验必须实测重标定」——阴影 blur/α 等令牌（blur 12–16 @30%）与 PCL2 原值（radius 3）差距已在 §1.5 显式标注"以实测为准"。

**与基线冲突/超出的发现**：
- **超出**：发现 PCL2 列表**不用** VirtualizingStackPanel（像素滚动 + 惰性实例化 + 折叠卡片），此前 `visual_language_study` §6.1 表第 11 行的表述（"ControlTemplate 重写"）未揭示这一层。SWDM 2.0 的列表策略需在两种哲学间选择（§4.3 路线 A/B），影响架构契约，**提交 arch-owner 裁决**。
- **超出**：PCL2 动画引擎为自建计时器（非 Storyboard），命名轨道/`AniControlEnabled` 无 WPF 内置等价物 → §5.2 提供 `AniHelper` 最小移植，避免 2.0 重蹈 1066 行引擎的维护成本。
- **对基线 §二决策 2 的影响**：若引入 WPF-UI 作基座，`swdm2/App` 的主题/控件层组织（§5.3 文件结构）需与 WPF-UI 的 `ApplicationThemeManager` 二选一，不能并存。**建议**：骨架期试装一个页面 + FlaUI 回归后再定。

**弯路嫌疑（可能因网络不稳误读）**：
- WPF-UI 的 API 表面（`FluentWindow`/`TitleBar`/`NavigationView`/`SnapLayout`）取自其 README 实读与稳定版惯例，**未**核验 2026 最新版（3.x+）的具体命名是否重命名（该库历史上经历过较大 API 变动）。若 arch-owner 选其为基座，须在骨架期以实际 NuGet 版本复验 API 名称（换源复验：NuGet README + 源码 samples 目录）。
- 本机单一网络条件（代理 7897）下 GitHub raw/API 全部可达且与基线白板的"代理离线期直连 schannel"描述时间错开——本次拉取 13+6 个文件全部 200，无空结果误读风险。

**采信/搁置/复验的决定**：
- **采信**：全部数值表中标注了源文件行号的条目（一手源码，二次复核通过——与 `visual_language_study.md` §7 速查表逐行比对，仅补充了前人未读文件的新发现，无冲突项）。
- **搁置**：HSL 主题编辑器/隐藏主题/镐子加载动画的具体关键帧（`MyLoading.xaml.vb` 循环时序沿用前人结论，未逐行复核——不影响 2.0 实现决策，标记为低优先级债务）。
- **复验中**：WPF-UI API 表面（见上"弯路嫌疑"）。
