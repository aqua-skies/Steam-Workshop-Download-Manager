# SWDM 2.0 视觉实现规格（Visual System Specification）

> 版次：v1.1 · 2026-10-02 · 维护：visual-20（视觉/UI 域 owner）
> **v1.1 变更（A7 同步回写，review_2.0_plan.md P1 自办项）**：① §2 通用条款补 AutomationId 载体限制（可靠载体=Window/内容控件/UserControl/WPF-UI 模板部件固定 id；**禁** Grid/ContentControl/Border 及库提升型容器承载测试锚点——SP-2 实证）；② §2.1 SwdmCard 根声明改 UserControl（pcl2 §1.2 可粘贴片段的 `Grid` 根仅作布局参考，Grid 为 UIA 提升型容器、id 被吞，自绘 UserControl id 完全暴露 type=Custom）；③ §2.2 Hint 根 `Border` → UserControl（Border 无 AutomationPeer）；④ §2.4 标题栏片段条件化（仅不用 WPF-UI TitleBar 时落地；走 TitleBar 按钮用模板部件固定 id）。**视觉数值未动**（90ms/150ms/0.07→0.4 等与 §5 对照表口径不变）。
> 依据：`docs/research2/pcl2_xaml_patterns.md`（可粘贴 XAML + §7 数值速查总表）、`docs/design/visual_language_study.md`（§7 PCL2 数值速查）、`docs/design/design_tokens.md`（令牌定义）、`swdm2/docs/design_baseline_2.0.md`（9 条锁定决策）、`swdm2/docs/architecture_2.0.md`（不变量 A1-A12 + 两项裁决）
> **文档地位：开发前置门（计划先行纪律）**——本文档（视觉）+ t1 架构规格 + t3 测试规格经 captain 认可、t5 讨论组终裁后，才允许开放开发任务（写产品代码）。研究、骨架与环境准备（含 t4 spike）不算开发。
> 数值来源声明：全部动画/阴影/几何数值为 **PCL2 源码实测值**（pcl2_xaml_patterns §7 / visual_language_study §7，含源文件行号），作为**起点值**移植；凡参数类数值一律标 ⚠️[参数待重标定]，按经验复验纪律在 D5.x 视觉标定任务中实测后锁定。

---

## 0. 一句话结论

SWDM 2.0 的「PCL2 皮肤质感」在 WPF 侧 = **自建 Light/Dark/Accent 资源字典作主题真源（明度阶梯 Brush 体系）+ 自绘签名组件层（SwdmCard 三层结构 / Hint / ModListItem / 自定义窗口 / 容器替换导航）+ 90ms 颜色 × 150ms 高度双段动画 × 0.07→0.4 品牌色阴影抬升 + 列表虚拟化路线 A（VSP Recycling + Pixel）**。WPF-UI 4.3.0 仅作窗口/控件基座，**ApplicationThemeManager 不作主题真源**（避免双主题状态，与架构规格 A8 裁决一致）；签名级观感任何库都给不了，必须自绘。视觉验收走 FlaUI 截图 + read_image 读图校验（本机已恢复，基线决策 5）+ 像素断言三件套。

---

## 1. 令牌 → 资源字典映射

### 1.1 字典组织（四文件 + App.xaml 单点合并）

```
swdm2/src/Swdm2.App/Ui/Themes/
  ├─ Light.xaml      ← 亮色：surface 阶梯 / stroke / text / link / semantic
  ├─ Dark.xaml       ← 暗色：同键名同结构（仅值不同）
  ├─ Accent.xaml     ← 强调色族独立文件（未来「换 accent 即换皮肤」只改此文件）
  └─ Common.xaml     ← 不随主题变：几何（radius/spacing）、字体、动画时长/曲线、阴影标量
```

```xml
<!-- App.xaml —— 主题字典只合并一次（架构 A3）；键名一律 swdm- 前缀防第三方冲突 -->
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

**双资源律**（对应 PCL2 `ColorBrush*`/`ColorObject*` 双轨制）：每个颜色令牌落 **两个**资源——`swdm-XxxColor`（`Color`，供 `ColorAnimation` 阴影/前景动画绑定）+ `swdm-XxxBrush`（`SolidColorBrush`，供 Fill/Background）。动画只能动 `Color` 是 WPF 硬约束，不是怪癖。所有消费处**一律 `DynamicResource`**（主题切换即时生效、无闪烁）。

### 1.2 明度阶梯 Brush 完整映射表

**暗色（Dark.xaml）**——明度递进模拟 z 轴（surface 阶梯 = Steam 式「画布深一档」高程地基）：

| 令牌 | 资源键 | 值 | 用途 |
|---|---|---|---|
| surface.canvas | `swdm-SurfaceCanvasColor/Brush` | `#16161C` | 窗口/页面画布（最深，卡片浮起的前提） |
| surface.card | `swdm-SurfaceCardColor/Brush` | `#1E1E24` | 卡片、面板主体 |
| surface.card_hover | `swdm-SurfaceCardHoverColor/Brush` | `#25252D` | 卡片/行悬停 |
| surface.input | `swdm-SurfaceInputColor/Brush` | `#26262E` | 输入框、下拉、菜单、tooltip |
| surface.raised | `swdm-SurfaceRaisedColor/Brush` | `#2B2B34` | 弹出层/对话框 |
| surface.selected | `swdm-SurfaceSelectedColor/Brush` | `#32285E` | 选中态（强调色 24% 观感） |
| stroke.hairline | `swdm-StrokeHairlineColor/Brush` | `#2B2B33` | 卡片/面板分隔线 |
| stroke.card | `swdm-StrokeCardColor/Brush` | `#2E2E37` | 卡片描边（悬停 → stroke.hover） |
| stroke.input | `swdm-StrokeInputColor/Brush` | `#3A3A45` | 输入框描边 |
| stroke.hover | `swdm-StrokeHoverColor/Brush` | `#4A4A57` | 交互描边悬停 |
| text.primary | `swdm-TextPrimaryColor/Brush` | `#E8EAF0` | 主文本、标题（对画布 14.5:1） |
| text.secondary | `swdm-TextSecondaryColor/Brush` | `#9AA3AF` | 元信息、说明（7.0:1） |
| text.tertiary | `swdm-TextTertiaryColor/Brush` | `#6E757F` | 占位、禁用辅助 |
| text.disabled | `swdm-TextDisabledColor/Brush` | `#5A6068` | 禁用 |
| text.on_accent | `swdm-TextOnAccentColor/Brush` | `#FFFFFF` | 强调色上的文本（4.6:1 ✓） |
| link.default | `swdm-LinkDefaultColor/Brush` | `#66C0F4` | 链接/标签/可点文本（Steam 蓝，与操作紫分离语义） |
| link.hover | `swdm-LinkHoverColor/Brush` | `#8CD4FF` | 链接悬停 |
| success.500 | `swdm-Success500Color/Brush` | `#43B581` | 成功/已完成 |
| danger.500 | `swdm-Danger500Color/Brush` | `#F04747` | 错误/删除 |
| warning.500 | `swdm-Warning500Color/Brush` | `#FAA61A` | 警告/限流提示 |

**浅色（Light.xaml）**——同键名，值如下（PCL2「白卡」路线）：

| 令牌 | 值 | 令牌 | 值 |
|---|---|---|---|
| surface.canvas | `#F2F3F6` | surface.card | `#FFFFFF` |
| surface.card_hover | `#F7F8FA` | surface.input | `#FFFFFF` |
| surface.raised | `#FFFFFF` | surface.selected | `#E7E0FB` |
| stroke.hairline / stroke.card | `#DDE1E6` / `#E3E6EB` | stroke.input / stroke.hover | `#C8CCD2` / `#B6BCC5` |
| text.primary / secondary / tertiary | `#23272E` / `#5A6169` / `#8A919A` | link.default / hover | `#1F7EB8` / `#1463A0` |
| success / danger / warning | `#2F9E6B` / `#D63C3C` / `#C77E00` | | |

**强调色族（Accent.xaml）**——dark 与 light 分列于各自主题文件内或 Accent 内分 `x:Key` 区分（实现取后者：`swdm-Accent400Color` 等键在 Light/Dark 两文件各定义一次，Accent.xaml 只放中性阴影色，避免主题切换时 accent 色残留）：

| 令牌 | dark | light |
|---|---|---|
| accent.400（悬停） | `#8F74FF` | `#7D5CFF` |
| accent.500（主强调，品牌延续 1.x 蓝紫） | `#7C5CFF` | `#6D4AFF` |
| accent.600（按下） | `#6A48F0` | `#5B3CE0` |
| 阴影色 `swdm-AccentShadowColor` | = accent.500（阴影用品牌色而非黑色，PCL2 签名） | = accent.500 |

stroke.focus = accent.500；text.on_accent 上白字对比度达标（dark 4.6:1 ✓）；浅色 link 深化至 ≥4.5:1（`#66C0F4` 白底仅 2.4:1 不可用）。**无障碍基线**：正文 ≥4.5:1，大字（≥15px 600）与图标 ≥3:1。

**高程表（dark / light / 手段）**——WPF 侧弹层可加真实阴影，描边阶梯保留：

| 层级 | dark | light | 手段 |
|---|---|---|---|
| z0 画布 | `#16161C` | `#F2F3F6` | 最深/最亮底 |
| z1 卡片 | `#1E1E24` + stroke.card 1px | `#FFFFFF` + stroke.card 1px | +1 明度阶 + 1px 描边 |
| z2 悬停 | `#25252D` + stroke.hover | `#F7F8FA` + stroke.hover | 再 +1 阶 |
| z3 输入/弹层 | `#26262E` + stroke.input | `#FFFFFF` + stroke.input | +2 阶 + 真实阴影（弹层） |
| z4 对话框 | `#2B2B34` + 2px stroke.input | `#FFFFFF` + 2px stroke.hover | 最浮 + `DropShadowEffect` |

**规则**：任何浮层必须与下层至少有 1 个明度阶 + 描边双重分离；等亮无描边的两块区域 = 设计缺陷。

### 1.3 WPF-UI ApplicationThemeManager vs 自建资源字典：论证与建议

| 维度 | 路线 A：WPF-UI `ApplicationThemeManager` | 路线 B：自建 `MergedDictionaries` 换字典 |
|---|---|---|
| 主题真源 | WPF-UI 内置主题资源（Dark/Light 两套，键名由库持有） | `swdm-` 前缀字典，键名/数值完全自主 |
| 自绘签名层 | SwdmCard / Hint / ModListItem 的 `DynamicResource` 仍需自建字典 → **两个真源并存，双主题状态** | 单一真源，自绘层与控件层同源 |
| 主题切换观感 | `ApplicationThemeManager.Apply(...)` 库内行为不透明（含其内部动画/闪烁史） | 换 `MergedDictionaries` 字典，全树 `DynamicResource` 立即重应用，无闪烁（pcl2 §5.3 已验证） |
| 换肤能力 | 只能切换库预设，自定义 accent 需另接 | `Accent.xaml` 独立文件，换 accent 即换皮肤（PCL2 主题色机制的现代版） |
| 数值一致性 | 令牌文档 ↔ 字典两处，需跨库对账 | 令牌文档 ↔ 自建字典一一对应，可写断言测试（§1.5） |
| PCL2 参照 | PCL2 是全自建 `Application.xaml` 资源字典 + HSL 重算（无任何库主题） | 与 PCL2 同构（`ColorBrush*`/`ColorObject*` 双轨 → 本文双资源律） |
| 锁定风险 | WPF-UI 456 开放 issue、API 历史变动大（pcl2 §8 弯路嫌疑） | 自有键名，升级库不连带主题迁移 |
| 代价 | 控件基座开箱即用 | 窗口/控件基座仍需与自建主题对齐（样式覆盖工作） |

**结论与建议：选路线 B（自建字典作主题真源）。**

1. 与架构规格 A8 裁决一致：「主题真源 = 自建 Light/Dark/Accent 字典，**不与 WPF-UI ApplicationThemeManager 并存**（避免双主题状态）；WPF-UI 仅作窗口/控件基座」。
2. 若使用 WPF-UI 控件基座，其主题作**从属刷新**：`ThemeService.Apply` 换字典后，按当前主题调一次 `ApplicationThemeManager.Apply(ApplicationTheme.Dark/Light)` 同步库控件外观——**真源与切换权仍在自建字典**；若实测冲突（库主题覆盖自建样式/闪烁），降级为对所用 WPF-UI 控件逐个 `OverridesDefaultStyle` 走自建模板。
3. **骨架期试装门**（pcl2 §6 末/§8 建议）：t4/D0.1 spike 试装一个页面（WPF-UI 控件 + 自绘 SwdmCard + 自建字典 + Light/Dark 切换），跑 FlaUI 回归后再定版：
   - 通过 → 混合基座定版（WPF-UI 控件 + 自建真源 + 从属刷新）；
   - 冲突 → WPF-UI 降级为纯非主题控件（或退回基线决策 9 的 MahApps.Metro fallback）。
4. 该门同时复验 pcl2 §8 弯路嫌疑（WPF-UI 4.3.0 API 表面：`FluentWindow`/`TitleBar`/`NavigationView`/`ApplicationThemeManager` 命名是否与 4.3.0 一致——换源复验：NuGet README + samples 目录），复验结果写入 spike 报告。

### 1.4 切换机制（ThemeService，App/Services）

```csharp
// ThemeService.cs —— 换字典（无闪烁）；持久化 + 系统主题跟随
public enum SwdmTheme { Light, Dark, FollowSystem }

public sealed class ThemeService
{
    public void Apply(SwdmTheme theme)
    {
        var resolved = theme == SwdmTheme.FollowSystem ? DetectSystemTheme() : theme;
        var path = resolved == SwdmTheme.Light ? "/Ui/Themes/Light.xaml" : "/Ui/Themes/Dark.xaml";
        var dict = new ResourceDictionary { Source = new Uri($"pack://application:,,,{path}", UriKind.Absolute) };
        var themeDict = Application.Current.Resources.MergedDictionaries
            .First(d => d.Source?.OriginalString.Contains("Themes/") == true);
        Application.Current.Resources.MergedDictionaries.Remove(themeDict);
        Application.Current.Resources.MergedDictionaries.Add(dict);
        // WPF-UI 控件基座的从属刷新（若混合基座定版，见 §1.3 第 2 条）
        // ApplicationThemeManager.Apply(resolved == SwdmTheme.Dark ? ApplicationTheme.Dark : ApplicationTheme.Light);
    }
    // FollowSystem 监听：Microsoft.Win32.SystemEvents.UserPreferenceChanged（Category=General/VisualStyle）
    // 持久化：IOptionsMonitor<ThemeOptions>（Light/Dark/FollowSystem），架构 §5.3 配置流
}
```

**不变量**（承接架构 A3）：① 主题字典只在 App.xaml 合并一次，切换 = 换 `MergedDictionaries` 条目；② 键名一律 `swdm-` 前缀；③ 消费处一律 `DynamicResource`（含 `Color`，供动画与阴影绑定）；④ 禁止在控件/页面 XAML 中硬编码颜色字面量（仅 `Ui/Themes/*.xaml` 允许出现 `#`，§1.5 测试断言）。

### 1.5 单一事实来源与一致性测试

1.x design_tokens §8.1 的「文档 = QSS = TOKENS 三副本一致性」在 2.0 的形态：

| 副本 | 位置 | 一致性手段 |
|---|---|---|
| 规范 | 本文档（§1.2 表） | 人工评审 + captain 抽查（§5 对照表） |
| 资源字典 | `Ui/Themes/{Light,Dark,Accent,Common}.xaml` | UiTests 资源断言（下） |
| 消费处 | 控件/页面 XAML 的 `DynamicResource swdm-*` | 静态断言（无硬编码颜色） |

- **资源存在性断言**：Light.xaml 与 Dark.xaml 键集严格相等（`Assert.Equal(lightKeys, darkKeys)`），每个键均为 `swdm-` 前缀、成对出现（Color + Brush）。
- **无硬编码颜色断言**：`Ui/Controls/`、`Ui/Pages/`、`Ui/Dialogs/` 下 XAML 文件中 `#[0-9A-Fa-f]{3,8}` 出现次数 = 0（例外白名单：图标 path 几何、`Transparent`）。
- **对比度抽检**：text.primary / text.secondary / text.on_accent / link.default 对其落点背景的 WCAG 对比值写表断言（计算函数在 UiTests 内，纯逻辑）。

---

## 2. 组件规格

> 通用质量条款（每个组件适用）：① AutomationId 命名 `<视图>_<控件>_<语义>`（架构 A7），可交互元素无 id = 测试任务不通过（T1）；**AutomationId 只设可靠载体**（A7 修正/SP-2：Window / 内容控件 Button·TextBox·ListBox·UserControl / WPF-UI 模板部件固定 id 如 `TitleBarCloseButton`；**禁止**把测试锚点压在 Grid/ContentControl/Border 及库提升型容器上——其 UIA 树提升会吞掉容器自身 id）；② `UseLayoutRounding="True"` + `SnapsToDevicePixels="True"` + 文本 `TextOptions.TextFormattingMode="Display"`（架构 A4）；③ 文字裁切一律 `TextTrimming="CharacterEllipsis"`（PCL2 全局默认）；④ 即时反馈：用户操作 ≤150ms 内有可见反馈 ⚠️[参数待重标定：实测能否更短]（A9）；⑤ 颜色一律 `DynamicResource swdm-*`，禁字面量。

### 2.1 SwdmCard（卡片：三层结构 + 90ms/150ms 双段 + 阴影双路线）

**结构**（对应 PCL2 MyCard 三层；pcl2 §1.2 可粘贴 XAML）：**根元素必须为 `UserControl`**（A7 修正：pcl2 §1.2 粘贴片段的 `Grid` 根仅作内部布局参考——Grid 是 SP-2 实证的 ❌ UIA 提升型容器，容器 AutomationId 会被吞；自绘 UserControl（type=Custom）id 完全暴露、内容控件可达，是自绘签名组件的标准根）：

| 层 | 控件 | 关键属性 |
|---|---|---|
| 0 阴影 | `Border x:Name="ShadowLayer"` | `Margin="-3,-3,-3,-4"`（底部多 1px 模拟自然光）、`CornerRadius="5"`、`Opacity="0.07"`、Background 绑 `swdm-AccentShadowBrush` |
| 1 卡面 | `Border x:Name="CardLayer"` | Background = `swdm-SurfaceCardBrush`（light 为 PCL2「96% 白」的纯白对等 `#FFFFFF`）、`CornerRadius="5"`、`IsHitTestVisible="False"` |
| 2 内容 | `Grid x:Name="MainGrid"` | 标题 `TextBlock`：`Margin="15,12,0,0"` / 13px **Bold** / `swdm-TextPrimaryBrush`；箭头 `Path` 10×6，`RotateTransform`；`ContentPresenter` `Margin="0,40,0,12"` |

**折叠态**：固定高度 40px；右侧箭头 `Data="M2,4 l-2,2 10,10 10,-10 -2,-2 -8,8 -8,-8 z"`，旋转 180°。

**动画时序**（PCL2 实测值起点；⚠️[参数待重标定] 全部，D5.x 实测标定）：

| 行为 | 时长 | 曲线 | 说明 |
|---|---|---|---|
| 悬停颜色过渡（四路并行：标题/箭头/阴影色/阴影 α） | **90ms** | linear | PCL2 `AaColor ... 90`；阴影 α **0.07→0.4**（≈5.7 倍，皮肤感第一签名） |
| 高度动画（折叠/展开） | **150ms** | `QuinticEase EaseOut` ≡ `AniEaseOutFluent(ExtraStrong)=1-(1-t)^5` | \|Δ\|≤800px 直达；>800px 分匀速段（4000-5000 px/s）+ 减速段（PCL2 为 5000px 级超长列表准备，2.0 保留策略不照搬阈值） |
| 箭头旋转 | **250ms** | `QuinticEase EaseOut` | 折叠 ↔ 展开 |
| 退出动画 | **200ms** | In/OutFluent | scale −0.08 + opacity −1；高度收回 150ms |

**双段语义**：90ms（颜色/阴影透明度）与 150ms（高度）构成卡片的双段节奏——悬停抬升 90ms 内完成颜色与阴影感知，展开/折叠 150ms 完成几何变化；二者不叠加同属性。

**阴影双路线选型**（pcl2 §1.5 实测对照）：

| | 路线 A：内置 `DropShadowEffect` | 路线 B：移植 `MyDropShadow` 9-patch |
|---|---|---|
| 实现 | `Border.Effect` 两个 Effect（idle/hover），动画 BlurRadius/Opacity/ShadowDepth 三个标量 | `Decorator.OnRender` 自绘：边 `LinearGradientBrush` + 角 `RadialGradientBrush`，6 级 alpha 阶梯（0.74336/0.38053/0.12389/0.02654），矢量 `DrawRectangle` |
| 适用 | 静态卡片、对话框、弹层 | 滚动列表场景、追求 1:1 复刻 |
| 代价 | 每控件一个位图模糊，滚动重绘成本高 | 约一套自绘类（C# 直译 VB，`DrawingContext` API 逐字对应） |
| 决策 | **2.0 首版采用 A** | 列表卡片若实测掉帧再评估 B（D5.x） |

路线 A 令牌（design_tokens §9 议题 D 方向；⚠️[参数待重标定]）：

```xml
<DropShadowEffect x:Key="swdm-CardShadowIdle" Color="{DynamicResource swdm-AccentShadowColor}"
                  BlurRadius="6" ShadowDepth="2" Opacity="0.07" Direction="270" />
<DropShadowEffect x:Key="swdm-CardShadowHover" Color="{DynamicResource swdm-AccentShadowColor}"
                  BlurRadius="14" ShadowDepth="5" Opacity="0.4" Direction="270" />
```

> 数值说明：PCL2 原版卡片是 ShadowRadius 3 的**极浅**阴影（静止 0.07 几乎不可见）；2.0 令牌（blur 12–16 @30%、offset 4–6）比 PCL2 更浓，方向一致、**数值以 D5.x 实测观感为准**（经验复验纪律：参数移植后实测标定，PCL2 值仅作保底）。悬停时**整体替换 Effect 会重置渲染**，更稳的是动画三个标量。

**颜色动画后置回绑**（PCL2 陷阱已修，pcl2 §1.3 注）：`AniHelper.StartColor` 在 `Completed` 里重新 `SetResourceReference` 回动态资源，否则主题切换不生效。

**阴影与列表的分工**：阴影只给「浮起来的东西」（卡片/弹层/对话框）；列表行无阴影，靠 RectBack 悬停浮层 + 勾选竖条表达状态（visual_language_study §2.2）。

**验收判据**：① 像素断言结构周期（canvas → 描边 → 卡面 → 描边 → 间隙）逐段采样命中令牌色；② idle/hover 两次截图，阴影区像素亮度差 ≥ 阈值（0.07→0.4 可见抬升）；③ 90ms 内标题颜色完成过渡（采样帧序列）；④ AutomationId：`<页面>_Card_<语义>`。

### 2.2 Hint（提示条）

PCL2 `MyHint` 等价（pcl2 §5.4 可粘贴 XAML）：

```xml
<!-- Hint.xaml —— 左 3px 色条 + 圆角 2 + padding 12,9；根 UserControl（Border 无 AutomationPeer，见 A7 修正） -->
<UserControl x:Class="Swdm2.App.Ui.Controls.Hint"
             UseLayoutRounding="True" SnapsToDevicePixels="True">
    <Border BorderThickness="3,0,0,0" CornerRadius="2">
        <Grid>
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*" /><ColumnDefinition Width="Auto" />
            </Grid.ColumnDefinitions>
            <TextBlock x:Name="MessageText" LineHeight="16" Padding="12,9" TextWrapping="Wrap"
                       VerticalAlignment="Center" FontSize="{StaticResource swdm-TextBody}" />
            <Button x:Name="CloseButton" Grid.Column="1" Width="20" Height="20"
                    Margin="0,0,8,0" VerticalAlignment="Center" AutomationId="..._Hint_Close" />
        </Grid>
    </Border>
</UserControl>
```

**语义档位**（色条 + 图标，沿用令牌）：`Info` = link.default / `Success` = success.500 / `Warning` = warning.500（限流提示专用）/ `Error` = danger.500。文字 = `swdm-TextPrimaryBrush`；背景 = `swdm-SurfaceCardBrush` + 左色条 = 对应语义色。**用途**：网络状态横幅（端点探测结果，架构基线 §三「启动期三端点探测 + 状态栏如实显示」）、下载错误提示、429/403 限流提示（错误分类对齐 `SteamError` 枚举）。

**验收判据**：① 像素断言左侧 3px 色条 = 语义令牌色；② 关闭钮点击后 `Visibility=Collapsed`（FlaUI 真实点击）；③ 文本经 Windows.Media.Ocr 读出预期文案。

### 2.3 ModListItem（列表行）

PCL2 `MyListItem` 等价（pcl2 §4.3 可粘贴 XAML；行高/网格/动画实测值）：

- **行高 42**；5 列网格：`[6px 勾选竖条列][Auto padding][4px+34px 图标][* 标题][右 padding]`
- **双行信息层级**：主标题 13px（`swdm-TextTitleSm`，PCL2 主标 14 → SWDM 令牌谱系一致收窄）+ 副标题 11px secondary（PCL2 12@opacity 0.6 → 令牌 `text.secondary` 近似）——信息量靠行高与副标题，不缩字（visual_language_study §4）
- **悬停浮层 RectBack**：`CornerRadius 6`、背景 `swdm-SurfaceCardHoverBrush`、边 `swdm-StrokeHoverBrush`；`ScaleTransform 0.75→1`，时长 = 基础 ×1.6（背景淡入与 scale 并行）
- **整行按下**：scale → 0.98
- **勾选竖条**（左侧 5px 圆角，`swdm-Accent500Brush`）：**双段生长** —— 40% / 200ms `OutFluent(Weak)` + 60% / 300ms `OutBack(Weak)`（2.0 用 `QuadraticEase` + `BackEase Amplitude≈0.5` 近似，⚠️近似警告见 §6），不透明度 30ms；收起 120ms + 70ms 淡出
- **选中前景色** → `swdm-Accent400Brush`（200ms）
- 右侧按钮组（25×25 图标钮）**悬停才淡入**并撑开右 padding（`5 + 按钮数×25`）——低密度默认、按需展开
- 图标三通道：SVG path 矢量（`GeometryConverter`，Fill 绑 `DynamicResource` 换主题即时变色）/ 本地位图 / 网络图（7 天缓存 + 占位 + Fallback）

**行容器**（路线 A 虚拟化下的 ItemContainerStyle）见 §3：`ModListItemStyle`（42px / Transparent / ControlTemplate 含 RectBack + CheckBar + ContentPresenter + Trigger Storyboard）。

**验收判据**：① 42px 行高几何断言（`ActualHeight`）；② 悬停浮层圆角与缩放（截图前后对比）；③ 勾选竖条双段（帧采样或 FlaUI 悬停→选中截图）；④ AutomationId `<页面>_Item_<语义>`；⑤ 1000+ 项数据下滚动帧率与实例化数（虚拟化实测，§3）。

### 2.4 自定义窗口（放弃 AllowsTransparency → WindowChrome / WM_NCHITTEST）

**论证（为什么放弃 PCL2 路线）**：

| | PCL2 原版（`AllowsTransparency="True"` + 8 Resizer + WM_GETMINMAXINFO） | 2.0 建议（`WindowChrome` + `WM_NCHITTEST`） |
|---|---|---|
| 系统集成 | **失去 Aero Snap 与 Win11 贴靠布局**（Snap Layouts）；多 DPI 混接时边缘发虚；系统 DWM 阴影丢失 | 保留系统贴靠/拖拽到边缘/最大化原生行为；DWM 合成阴影 |
| 缩放命中区 | 8 个 Resizer 矩形 + 后台轮询 `GetCursorPos` 改 Left/Top/Width/Height | 声明式 `ResizeBorderThickness` / 或 `WM_NCHITTEST` 返回 HT* 命中区 |
| 圆角 | `Border.Clip = RectangleGeometry RadiusX/Y=6`（剪掉子页面） | `WindowChrome.CornerRadius`（Win11 系统圆角）或内容 Border Clip |
| 时代 | 2018 年技术约束，PCL2 自己的代价 | 2026 更优，**不必继承此债**（pcl2 §2.4 明确结论） |

**推荐实现**（WindowChrome 为主，WM_NCHITTEST 为补充）：

```xml
<!-- MainWindow.xaml —— WindowStyle=None + WindowChrome（保留系统贴靠与 DWM 阴影） -->
<!-- 条件化声明（A7 修正/SP-4 裁决）：本片段的自绘标题栏 + 自定义关闭/最小化钮
     仅当窗口 chrome 不走 WPF-UI FluentWindow/TitleBar 时落地。
     若走 WPF-UI TitleBar：关闭/最小化/最大化钮使用控件模板的部件固定 id
     （TitleBarCloseButton 等，属于 A7 可靠载体"模板部件固定 id"），不再自绘按钮；
     标题栏渐变皮肤（主题色单端线性渐变）仍按本片段令牌落实。 -->
<Window x:Class="Swdm2.App.MainWindow"
        WindowStyle="None" ResizeMode="CanResize" ShowInTaskbar="True"
        MinWidth="810" MinHeight="470"
        UseLayoutRounding="True" SnapsToDevicePixels="True">
    <WindowChrome.WindowChrome>
        <WindowChrome GlassFrameThickness="0" CaptionHeight="48"
                      ResizeBorderThickness="8" CornerRadius="6"
                      UseAeroCaptionButtons="False" />
    </WindowChrome.WindowChrome>
    <Grid x:Name="PanForm">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto" /><RowDefinition Height="*" />
        </Grid.RowDefinitions>
        <!-- 标题栏 48px：PCL2 同高；主题色线性渐变（单端，dark 换暗端 swdm-SurfaceRaisedBrush） -->
        <Grid x:Name="PanTitle" Height="48">
            <Grid.Background>
                <LinearGradientBrush EndPoint="1,0" StartPoint="0,0">
                    <GradientStop Color="{DynamicResource swdm-Accent400Color}" Offset="0" />
                </LinearGradientBrush>
            </Grid.Background>
            <Button x:Name="BtnClose" HorizontalAlignment="Right" Height="28" Width="28"
                    Margin="0,0,12,0" VerticalAlignment="Center"
                    WindowChrome.IsHitTestVisibleInChrome="True"
                    Style="{StaticResource swdm-TitleIconButtonStyle}" AutomationId="Main_Window_Close" />
            <Button x:Name="BtnMin" HorizontalAlignment="Right" Height="28" Width="28"
                    Margin="0,0,44,0" VerticalAlignment="Center"
                    WindowChrome.IsHitTestVisibleInChrome="True"
                    Style="{StaticResource swdm-TitleIconButtonStyle}" AutomationId="Main_Window_Minimize" />
        </Grid>
        <ContentControl x:Name="PageHost" Grid.Row="1" />
    </Grid>
</Window>
```

> **AutomationId 归属提示**：上图 BtnClose/BtnMin 的自定义 id（`Main_Window_Close/Minimize`）仅自绘标题栏方案下成立；走 WPF-UI TitleBar 时 t3 §3.2 保留 id 清单的窗口级按钮锚点应改为模板部件固定 id（`TitleBarCloseButton` 等，SP-2 实证可达），二者在 A7 可靠载体表内同为合法载体。

- 图标钮几何沿用 PCL2 path（X 与横线几何字符串；pcl2 §2.2）。
- **WM_NCHITTEST 补充场景**：若需自绘标题栏内的非 Caption 命中区（例如标题栏内嵌搜索框时的拖拽让位），`SourceInitialized` 挂 `HwndSource.AddHook`，命中区宽 8px（PCL2 同值，其 Resizer 8px/角 13px），中部 `relY < 48` 返回 `HTCAPTION`（pcl2 §2.4 可粘贴 WndProc）。
- **拖拽备选**：`DragMove()`（标题栏 `MouseLeftButtonDown` + `IsMouseDirectlyOver` 判定，pcl2 §2.3 直译）——WindowChrome CaptionHeight 已覆盖主路径，此为回退。
- **最大化约束**：`WM_GETMINMAXINFO` 约束到显示器工作区（`MONITORINFO.rcWork`，处理任务栏遮挡）——PCL2 已验证，2.0 保留。
- **入场动画**（可选，默认开）：旋转 −4°→0 / 500ms + 位移 Y 60→0 / 600ms（均 `OutBack(Weak)`）+ 透明度 250ms，延迟 100ms（pcl2 §7 数值表）。
- **Mica/亚克力**：首版**不做**（纯色 `swdm-SurfaceCanvasBrush` 画布）；后续迭代经讨论组裁决再上 `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE)`（精简原则）。
- **简化通道**：WPF-UI `FluentWindow`/`TitleBar` 内置 Win11 SnapLayout（pcl2 §2.4 核验）；若 §1.3 试装门通过且选用 WPF-UI 窗口基座，标题栏渐变与图标钮仍自绘（主题从属自建字典）。

**验收判据**：① 拖拽标题栏移动窗口（FlaUI 真实拖拽）；② 边缘拖拽缩放；③ 最大化后还原（系统贴靠行为不回归坏）；④ 圆角 6px 像素断言（窗口角采样透明/圆滑）；⑤ 标题栏 48px 几何断言；⑥ 关闭/最小化钮真实点击生效。

### 2.5 页面导航（容器 + 页面基类 + 返回栈）

**不用 `Frame`/`Page`**（PCL2 同构）：`PageHost`（`ContentControl`）容器替换 + `PageBase`（`abstract UserControl`）页面基类 + `PageNavigationService` 返回栈。

- **切换时序**（PCL2 实测）：`StopPreviousAnimations`（命名轨道防重入，≡ `AniStop`）→ 旧页 `RunExit()` → **+110ms** 替换 `PageHost.Content`（新页 `Opacity=0`）→ **+30ms** 新页 `Opacity=1` + `RunEnter()`。
- **返回栈**：`Stack<Func<PageBase>>`；标题栏左侧返回箭头 + 子页面名 15px（PCL2 `BtnTitleInner`/`LabTitleInner` 等价）；`GoBack()` 出栈回到主页。
- **页面进入动画**（`PageBase.RunEnter`，PCL2 交错 + 双段位移）：每元素 opacity 0→1 / 100ms `OutFluent(Weak)`；**双段位移并行**：+5px/250ms 与 +11px/350ms `OutBack`；stagger **25ms**；滚动条 X +10px→0 / 350ms；侧栏从左滑入。
- **页面退出动画**：opacity −1 / 70ms + TranslateY −6px / 70ms，stagger **15ms**。
- **状态机**（PCL2 9 态的 2.0 收敛）：`PageState { Empty, Loading, Content, Exiting }`——内容/加载双通道，切走时加载回来「不打断退出动画」（等退出的等待槽保留）；Loading 态走统一 Loading 组件（百分比文本 + 错误态文本替换，visual_language_study §3 可迁移点）。
- **页面清单**：主页 / 浏览 / 详情 / 下载 / 库 / 设置（架构 §3.4.1；功能基线 §四 对等 + 增强）。

```csharp
// PageNavigationService.cs（pcl2 §3.2 可粘贴实现的骨架）
private readonly Stack<Func<PageBase>> _backStack = new();
public void Navigate<T>(bool keepInStack = true) where T : PageBase, new() { /* 停旧→退出→+110ms 替换→+30ms 进入 */ }
public bool GoBack() { /* 出栈，keepInStack:false */ }
```

**差异化保留**：PCL2 式逐元素 stagger 进入动画必须自写在 `PageBase`（WPF-UI `NavigationView` 只有整页过渡，pcl2 §3.2 注）。

**验收判据**：① 切页时序（110/30ms 帧采样或耗时断言）；② 返回栈深度与 GoBack 语义（FlaUI 点返回箭头断言页面回退）；③ 进入动画交错可见（前后截图对比）；④ AutomationId：`<页面>_Nav_Back` 等；⑤ Loading 态百分比文本 OCR。

### 2.6 侧栏导航形态（design_tokens 议题 A 落地）

**决策**：左侧**可折叠侧栏**（PCL2 / DSH 皮肤质感同款，design_tokens §9 议题 A 推荐）：默认展开 180px，折叠为 56px 图标条；图标 + 文字；选中态品牌色 + 明度阶梯。理由：tab 数增长后标题挤压、扩展性强、皮肤质感最浓。顶 tab 形态不保留（2.0 窗口期实施，经典偏好项经讨论组裁决另行决定）。

### 2.7 静态层模板（滚动条 / 菜单 / 图标）

- **ScrollBar**（pcl2 §5.4 可粘贴模板）：8px 宽 / 拇指圆角 3 / margin 2 / 轨道 = 1% 主题色底（dark `#01` 级 accent 透明 → `swdm-TrackBaseBrush`）；翻页按钮透明但保留点击区域。
- **ContextMenu**（pcl2 §5.4）：圆角 3 / 1px `swdm-Accent400` 边 / `swdm-SurfaceCard` 底 / margin 0,0,4,4 / **弹层真实阴影** `DropShadowEffect` 0.4/4/2（PCL2 `Application.xaml:487` 原值）；MenuItem 行高 26。
- **图标**：SVG path 字符串直接当 `Data` 属性 + `Fill` 绑 `DynamicResource`（PCL2 `<Shapes.Path>` 模式，换主题即时变色）；图标 path 数据库在 `Ui/Icons/`（静态资源）。

---

## 3. 列表虚拟化路线 A 与卡片折叠的取舍

**裁决（承接架构 §8 / A2）**：SWDM 2.0 列表走**路线 A（WPF 原生虚拟化）**，弃 PCL2 的惰性实例化。理由：① 工坊/下载/库三主场景数据量已知可上千（PCL2 列表项被卡片折叠天然限流的前提不成立）；② FlaUI 可测性（虚拟化回收容器仍按 AutomationId 稳定可达）；③ 维护成本（PCL2 路线 B 需自移植 `MyVirtualizingElement` + ScrollChanged 可见性判定）。

```xml
<!-- ModListPage.xaml —— 路线 A 必备属性全集 -->
<ListBox x:Name="ModList" ItemsSource="{Binding Items}"
         VirtualizingPanel.IsVirtualizing="True"
         VirtualizingPanel.VirtualizationMode="Recycling"
         VirtualizingPanel.ScrollUnit="Pixel"
         VirtualizingPanel.IsVirtualizingWhenGrouping="True"
         ScrollViewer.CanContentScroll="True"
         ScrollViewer.PanningMode="VerticalOnly"
         UseLayoutRounding="True" SnapsToDevicePixels="True"
         ItemContainerStyle="{StaticResource swdm-ModListItemStyle}"
         Background="Transparent" BorderThickness="0">
    <ListBox.ItemsPanel>
        <ItemsPanelTemplate>
            <VirtualizingStackPanel Orientation="Vertical" />
        </ItemsPanelTemplate>
    </ListBox.ItemsPanel>
</ListBox>
```

**不变量（架构 A2 + 本次细化）**：
1. `IsVirtualizing="True"` + `Recycling` + `ScrollUnit="Pixel"`（Pixel ≡ PCL2 `CanContentScroll=False` 的像素滚动感）；
2. **永远不把虚拟化列表包在 `ScrollViewer` 里**（虚拟化失效 = 全量实例化）；
3. 分组场景开 `IsVirtualizingWhenGrouping`；
4. `VirtualizingStackPanel` 必须是 ItemsHost 直接子级才能回收；
5. 大数据量绑定的 `ItemsSource` 用 `ICollectionView` 分页/过滤，禁全量 `ObservableCollection` 加载后前端过滤（性能 + A1 事件源生命期）。

**惯性滚轮**（`SmoothScrollViewer`， pcl2 §4.3）：`PreviewMouseWheel` 接管 → 300ms `OutFluent(6)` 缓动（2.0 用 `QuinticEase EaseOut` 近似，⚠️[参数待重标定]）到目标偏移；`ScrollViewer.VerticalOffset` 非动画友好 DP → 走附加属性包装（`ScrollViewerBehavior.VerticalOffsetProperty`）或 `DoubleAnimation` 帧回调调 `ScrollToVerticalOffset`。

**卡片折叠独立于虚拟化的取舍**：
- **PCL2 的折叠承担限流职责**（`MyCard.StackInstall`：展开才把 Tag 数据列表转成控件 + 末尾 18px 下边距）——这是**它不用 VSP 的替代方案**，不是折叠的必要语义。
- **2.0 解耦**：折叠 = 信息架构功能（收纳同类内容、降低首屏信息密度），**不再承担性能限流**；虚拟化 = 性能机制。二者正交：卡片列表同样可虚拟化（`ItemsControl` + `VirtualizingStackPanel` + 卡片 DataTemplate）；折叠展开只改卡片自身高度（150ms 动画），不触发容器级实例化策略。
- **取舍代价**：VSP 回收要求 ItemTemplate 高度可测量（卡片折叠态固定 40px 正满足）；变高内容（详情展开）用 `VirtualizingPanel.CacheLength` 预渲染上下文缓解滚动闪烁 ⚠️[参数待重标定]。
- **预留口子**：若未来某场景（如超长自定义主页）实测 VSP 回收观感不佳，PCL2 路线 B（惰性实例化移植）作为 fallback 评估，属架构变更须走 arch-owner。

---

## 4. 视觉验收方式（截图 + 读图校验 + 像素断言）

**总原则**（基线决策 5 + 架构 §3.5.1）：视觉校验是 FlaUI 真实输入测试的**补充不替代**；分层 = 被测进程内 OCR（中文，断言文本）+ 静态区域像素 diff + 动态区域感知哈希容差；截图读图（modlens 桥，本机 2026-10-02 已恢复）作二次校验。

| 层 | 工具/手段 | 落点 | 用途 |
|---|---|---|---|
| 截图捕获 | `FlaUI.Capturing.Capture.Screen()/Element()` | `TestArtifacts/`（架构 §3.5.1 失败证据） | 每次断言失败自动落盘；回归基线图 |
| **读图校验** | `read_image`（modlens 桥） | 测试内调用 | 语义级断言：卡片是否浮起、阴影是否可见、文字是否裁切/重叠/挤压（1.x 无读图工具时只能几何量化的债，2.0 还清） |
| 进程内 OCR | `Windows.Media.Ocr`（中文） | UiTests | 文本层断言（Hint 文案、Loading 百分比、错误态真实异常文本） |
| **像素断言** | 采样点/区域颜色判定 | UiTests | 令牌色存在性、结构周期、主题切换前后全图 diff |
| 像素 diff | 静态区域严格 diff / 动态区域感知哈希 | UiTests | 回归门（dark + light 双主题） |

**像素断言清单**（1.x `tools/verify_design_shots.py` 模式的 2.0 移植，C# UiTests 实现）：

1. **结构周期采样**：沿列表/卡片中线采样，依次命中 canvas → stroke.card → card → stroke.card → 间隙 的令牌色（验证描边 + 明度阶梯生效）；
2. **令牌色存在性**：关键令牌（surface.canvas/card、stroke.card、text.primary、accent.500）在截图中各自出现（非 0 像素）；
3. **残留色为 0**：断言 `#EFEFEF`（1.x ScrollArea 视口亮灰事故色）及其他非令牌灰为 0 像素；
4. **双主题门**：dark 与 light 两套截图各跑全套断言；
5. **阴影抬升门**：idle/hover 两次截图，卡片阴影区像素差异 ≥ 阈值（验证 0.07→0.4）；
6. **切换无闪烁门**：主题切换前后截图，除令牌色映射外无其他区域变化（超时/帧采样）。

**组件级验收**：见 §2 各组件「验收判据」；全部纳入 FlaUI 冒烟套件（5 条主旅程：启动→搜索→详情→下载→库，架构 §3.5.1），**每次迭代完成后全量回归**（T6，迭代交付四要素）。

**规格自检门（本文档自身的验证方式）**：captain 对照 pcl2 报告数值速查表（pcl2_xaml_patterns §7）抽查 §5 对照表 3 处一致性（任务验证条款）。

---

## 5. 数值速查对照表（PCL2 实测 ↔ 2.0 规格，供 captain 抽查）

> 全部 PCL2 值出处：`docs/research2/pcl2_xaml_patterns.md` §7 数值速查总表（行号级溯源见该表）；SWDM 令牌出处：`docs/design/design_tokens.md`、本文档。参数类数值 ⚠️[参数待重标定]，D5.x 实测后锁定。

| 项 | PCL2 实测 | 2.0 规格（本文档） | 一致性 |
|---|---|---|---|
| 悬停颜色过渡 | **90ms 线性**（`MyCard.vb:181`） | `swdm-MotionColor` 90ms linear（§2.1） | ✓ |
| 高度动画 | ≤800px **150ms ExtraStrong**（>800 分匀速+减速段） | `swdm-MotionFast` 150ms `QuinticEase EaseOut`（§2.1） | ✓ |
| 阴影抬升 | α **0.07→0.4**，色 = 主题色，radius 3，margin `(-3,-3,-3,-4)`（`MyCard.vb:67/176`） | 品牌色阴影 + α 0.07→0.4（§2.1，DropShadowEffect 标量值待标定） | ✓（方向 + α 值） |
| 卡片几何 | 圆角 5 / 折叠高 40px / 标题 13 Bold @15,12（`MyCard.vb:81`） | `radius.sm` 5 / 40px / 13px Bold @15,12（§2.1） | ✓ |
| 卡片背景 | `#F5FFFFFF`（96% 白） | light `#FFFFFF`、dark `#1E1E24`（§1.2） | ✓（微透留待 D5.x 观感定夺） |
| 箭头旋转 | **250ms** ExtraStrong | `swdm-MotionSlow` 250ms（§2.1） | ✓ |
| 退出动画 | scale −0.08 + opacity −1 / **200ms**；高度 150ms | `swdm-MotionBase` 200ms（§2.1） | ✓ |
| 列表行高 / 主标 / 副标题 | 42 / 14 / 12px@0.6（`MyListItem.xaml:5`） | 42 / 13（`swdm-TextTitleSm`）/ 11 secondary（§2.3） | ✓（谱系一致，SWDM 令牌收窄一档，visual_language_study §7 同口径） |
| 悬停浮层 RectBack | CornerRadius 6，scale 0.75→1，1.6× 时长 | 同（§2.3） | ✓ |
| 勾选竖条 | 双段 40%/200ms Weak + 60%/300ms OutBack | 同（§2.3） | ✓ |
| 标题栏 | 48px 渐变（单端 ColorObject4），图标钮 28×28（`FormMain.xaml:100`） | 48px 渐变（单端 accent.400），28×28 @12/44（§2.4） | ✓ |
| 窗口圆角 / 沟 | Clip RadiusX/Y=6，根 Margin 10 | `WindowChrome.CornerRadius=6`（§2.4，改路线不改值） | ✓（几何等价） |
| 页面切换时序 | 110ms 退出 → 替换 → 30ms 进入（`FormMain.xaml.vb:1513`） | 同（§2.5） | ✓ |
| 页面进入 | stagger 25ms：opacity 100ms + Y 5px/250 + 11px/350 OutBack | 同（§2.5） | ✓ |
| 页面退出 | opacity 70ms + Y −6px/70ms，stagger 15ms | 同（§2.5） | ✓ |
| 平滑滚动 | 300ms `OutFluent(6)`（`MyScrollViewer.vb:28`） | `swdm-MotionSmoothScroll` 300ms `QuinticEase`（§3，⚠️近似） | ✓（曲线近似见 §6） |
| 滚动条 | 8px / 圆角 3 / margin 2 / 1% 底色 | 同（§2.7） | ✓ |
| 菜单阴影 | `DropShadowEffect` 0.4/4/2（`Application.xaml:487`） | 弹层真实阴影同值（§2.7） | ✓ |
| 按钮颜色 | 进 100ms / 出 200ms（`MyButton.xaml.vb:72`） | `swdm-MotionButtonIn/Out` 100/200（§Common） | ✓ |
| 入场动画 | 旋转 −4°→0 / 500ms + 位移 60→0 / 600ms，延迟 100ms | 同（可选开）（§2.4） | ✓ |
| 字体 | PCL English + 雅黑 UI，11–16 谱 | 雅黑 UI + Segoe UI，10–22 谱令牌（§Common） | ✓（SWDM 略宽，保留） |

**Common.xaml 静态令牌**（不随主题变）：`swdm-RadiusXs/Sm/Md/Lg/Pill` = 3/5/6/8/999；`swdm-Space1..8` = 4/8/12/16/20/24/32；字号 `swdm-TextCaption/BodySm/Body/TitleSm/Title/TitleLg/Hero` = 10/11/12/13/15/18/22；字重 400/600/700；字体族 `"Microsoft YaHei UI, Microsoft YaHei, Segoe UI"`；时长 `swdm-MotionColor/Fast/Base/Slow/Spring` = 90/150/200/250/300；曲线资源 `swdm-EaseFluentOut`（`QuinticEase EaseOut`）/ `swdm-EaseSpring`（`BackEase EaseOut`）。

---

## 6. 对照基线结论（按 `design_baseline_2.0.md` §五 协议）

**与基线一致的部分**：
- 决策 5（视觉校验：OCR + 像素 diff + modlens 二次校验）→ §4 全部落地，且细化出像素断言六清单（结构周期/令牌存在性/残留色 0/双主题/阴影抬升/无闪烁）。
- 决策 9（WPF-UI 4.3.0 底座 + 自绘 Card/Hint）→ §1.3/§2 论证与基线「任何控件库都给不了 PCL2 脸」同向；§1.3 试装门即基线「锁版本 + 回归把关」的落地。
- §四增强项「PCL2 级视觉（卡片/阴影/双段缓动/明度阶梯）」→ §1.2 明度阶梯、§2.1 卡片双段、阴影抬升逐条有 PCL2 源码级数值支撑。
- 1.x 学费：即时反馈 ≤150ms（A9，§2 通用条款）、弹窗不打桩（A12，§4 验收一律 FlaUI 真实交互）、读图工具教训（1.x 期不可用 → 2.0 双通道：像素断言为主 + 读图为二次校验，不单点依赖）。

**与基线冲突/超出的发现**：
- **超出**：主题真源二选一（pcl2 §8 提交项）——本文档给出完整论证（§1.3 八维对照）并建议自建字典，与 arch-20 A8 裁决一致；超出基线决策 9 的「底座」表述，落实为「真源/切换权归自建字典 + WPF-UI 从属刷新 + 冲突降级路径」。
- **超出**：design_tokens §9 六项开放议题（A-F）在 2.0 的处置逐条落定：A 侧栏（§2.6，采纳推荐）、B 密度（comfortable 12 为默认、compact 偏好项，§Common 令牌）、C 强调色（accent.500 蓝紫 + link 蒸汽蓝分离，§1.2）、D 阴影（弹层 DropShadowEffect + 列表描边，§2.1/§2.7）、E 动效（WPF 原生 Storyboard/BeginAnimation + AniHelper 命名轨道，§2 + 架构 §3.4.2）、F 技术形态（用户已裁定 WPF）。
- **冲突**：design_tokens 是 1.x Qt/QSS 产物（QSS 无 transition/box-shadow 的约束条目）——2.0 全部解除（DropShadowEffect / Storyboard 原生可用），令牌值原样继承、实现路线全部换 WPF 机制；本文档是令牌的 WPF 落地层，design_tokens 保留为**令牌定义层**（单一事实来源_CHAIN：令牌定义层 → 本文 WPF 映射层 → Themes/*.xaml）。

**弯路嫌疑（可能因网络不稳误读）**：
- WPF-UI 4.3.0 API 表面（`ApplicationThemeManager`/`FluentWindow`/`TitleBar`/`NavigationView`）取自 README 实读，未逐版核验（pcl2 §8 已标注）→ §1.3 试装门强制在 D0.1/t4 以实际 NuGet 4.3.0 复验 API 名称与并存行为（换源：NuGet README + GitHub samples 目录），复验前本文涉及 WPF-UI 的条款均标 [待 spike 复验]。
- 缓动近似：`BackEase`/`ElasticEase`/`QuinticEase` 内置参数化与 PCL2 闭式（`OutFluent(6)`、`OutBack(Weak)`）不逐点一致（pcl2 §5.1 近似警告）→ 数值表标 ⚠️近似，D5.x 以实测观感标定（经验复验纪律：观感为准，不为公式保真牺牲可维护性）。

**采信/搁置/复验的决定**：
- 采信：PCL2 行号级数值全部（pcl2 §7 / visual_language_study §7 二次复核无冲突）；design_tokens 令牌体系（值与谱系，1.x 试点已验证的部分：明度阶梯浮起、描边高程、令牌色像素断言套路）。
- 搁置：PCL2 HSL 主题编辑器与隐藏主题（运营功能，2.0 不继承；换肤能力经 Accent.xaml 保留）；镐子加载动画关键帧（低优先级债务，Loading 组件先上百分比文本 + 错误态文本替换，§2.5）；Mica/亚克力（§2.4，讨论组后议）。
- 复验中：D0.1 WPF-UI API + 主题并存（§1.3 试装门）；D5.x 全部 ⚠️ 参数（阴影 blur/α/offset、动画时长、CacheLength、即时反馈阈值、平滑滚动曲线）；t3 测试规格将把 §4 验收方式转写为具体断言代码与基线图管理。

---

## 7. 与架构规格 / 测试规格的接口

- **执行落点**（架构 DAG 域 owner=visual-20，即本文档持有者）：`Ui/Themes/*`（§1.1）、`Ui/Controls/{SwdmCard,Hint,ModListItem,SmoothScrollViewer}`（§2.1-2.3）、`Ui/Themes` 切换 `ThemeService`（§1.4）、`MainWindow` + `PageNavigationService` + `PageBase`（§2.4-2.5）属 D5.x 阶段（架构阶段 5「App UI 主体」），视觉标定任务对接 t2/t3（架构 §7 第 2 条）。
- **对架构的反馈**：`Common.xaml` 的动画时长令牌须与 `AniHelper`（命名轨道，架构 §3.4.2）共用同一资源源；`ModListItem` 的 ItemContainerStyle 依赖 A2 不变量的 ScrollUnit=Pixel（已在 §3 重申）。
- **对 t3 测试规格的输入**：§4 验收方式（六清单像素断言、OCR 断言、读图校验流程、TestArtifacts 基线图管理、双主题门）+ §2 各组件「验收判据」+ AutomationId 命名（A7）——t3 转写为 FlaUI/xUnit 代码契约。
- **对 t4 spike 的输入**：§1.3 试装门（一个页面 = WPF-UI 控件 + 自绘 SwdmCard + 自建字典 + Light/Dark 切换 + FlaUI 回归）是 spike 的验收判据之一。

---

> **门禁状态**：本文档（视觉）+ t1 架构规格 + t3 测试规格提交 captain；captain 对照基线 9 条核验一致性 + 抽查 §5 对照表 3 处数值一致性 → t5 讨论组终裁后开放 D0-D7 开发任务。本文档未决项：WPF-UI 主题并存（待 D0.1/t4 spike 复验）、全部 ⚠️ 参数（待 D5.x 标定）。
