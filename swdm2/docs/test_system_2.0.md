# SWDM 2.0 测试体系规格（真实输入 + 参数重标定）

> 版次：v1.1 · 2026-10-02 · 维护：qa-20（UiTests / 复测域 owner）
> 依据：`docs/research2/wpf_ui_testing.md`（451 行，FlaUI 方案研究）、`swdm2/docs/architecture_2.0.md`（§3.5 UiTests 契约 / §4 学费清单 / §6 DAG v2.0 + 附录 SP spike 实证）、1.x 既有基准脚本 `tests/_bench_steam_rate.ps1`（Steam 限流基准的三段法原型）
> **v1.0 → v1.1 变更（落实 t4 spike SP-2/SP-5 落账清单）**：
> - **输入路径三规则**（SP-2 实测）：CJK→`Enter()`；含空格/标点的 ASCII 词→剪贴板真实 `Ctrl+V`（`Enter()` 会吞空格/撇号，实测 `"Don't Starve"`→`"Don'tStarve"`）；**注入按键前必须先物理点击使窗口/控件获得焦点**（程序化 `Focus()`/`SetForeground()` 不可靠，Windows 前台锁定）。
> - **载体规则（A7 修正）**：AutomationId 只设在可靠载体（Window / 内容控件 / UserControl / WPF-UI 模板部件固定 id）；**禁止**锚定 UIA 提升型容器（`ui:TitleBar`/`ui:Card`/`Grid`/`ContentControl`，id 被"吞"）（SP-2 实证 8/9 可达）。
> - **无 ClickablePoint 兜底**：自绘卡片内容 Button 实测无 ClickablePoint → 退到包围矩形中心点击（SP-2 实证），InputSimulator 裸 SendInput 作第二兜底。
> - **SP-3 双通道**：本机 DSH 沙箱内 `dotnet test` testhost 崩溃 → 沙箱内用控制台驱动模式（`dotnet run` 反射执行同一批 `[WpfFact]`）；产品回归在普通交互桌面用 `dotnet test`（§6.2）。
> - §7.2 映射表同步 DAG v2.0（D0.3→D0.2 spike 收编；补 D5.11/D5.12）。
> **文档地位：开发前置门（计划先行纪律）**——本文档与 t1 架构规格、t2 视觉规格并列，经 captain 核对（与 `wpf_ui_testing.md` 结论一致性 + 重标定方案可执行性）+ t5 讨论组终裁后，才允许开放 D0-D7 开发任务。研究、骨架与环境准备（含 t4 spike）不算开发。

---

## 0. 结论摘要（TL;DR）

| 决策点 | 结论 |
|---|---|
| 驱动工具 | **FlaUI 5.0.0（UIA3）**；真实鼠标 `Mouse.MoveTo` + `Mouse.Click`（SetCursorPos + SendInput 真实事件），真实键盘 `Keyboard.Type`（VK / 扫描码 / Unicode 三路） |
| 测试框架 | xUnit 2.9.x + `Xunit.StaFact`（`[WpfFact]`），**进程外** `Application.Launch(被测 exe, "--test-mode")` |
| 包清单 | `FlaUI.Core` 5.0.0、`FlaUI.UIA3` 5.0.0、`xunit`、`Xunit.StaFact`、`xunit.runner.visualstudio`、`coverlet.collector`、`Microsoft.NET.Test.Sdk`（§2.1，锁版本 + D0.3 restore 复验条款） |
| 选择器 | **一律 `AutomationId`**；禁止显示文本、坐标、层级索引、ClassName；页面级容器 id 只用一次，其余 `FindFirstDescendant` |
| 命名约定 | `<视图>_<控件>_<语义>`（如 `GameSelectPage_SearchBox_Input`）；数据模板项 = `<列表>_Item`；详见 §3 保留 id 清单（App 侧契约） |
| 等待策略 | `Retry.While` / `Wait.Until` 显式超时；**禁止 `Thread.Sleep`**（测试代码里出现即 review 不通过） |
| 组织方式 | Screen Object 模式（窗口/页面一个映射类），目录骨架见 §2.4 |
| 中文输入 | 主路径 ValuePattern `Enter("饥荒")`；真实键盘路径 = 真实 `Ctrl+V` 或 Unicode 键注入；**IME 拼音模拟不做**；按键触发类操作（回车搜索）**必须真实键盘事件** `VK_RETURN` |
| 弹窗 | MessageBox 该弹还弹，按 FlaUI #255 路径定位按钮点击；**禁止打桩替换弹窗实现**（1.x 桩函数学费） |
| 失败证据 | `FlaUI.Core.Capturing.Capture.Screen()/Element()` 截图 + 被测进程 Serilog 日志，统一落 `swdm2/TestArtifacts/` |
| 参数重标定 | 三个可执行基准（B1 429 退避曲线 / B2 端点节流最小间隔 / B3 并发上限），xUnit `Category=Calibration`，输出「参数候选 → 实测成功率 → 用时」表（§5），结果锁定 `SteamOptions` / `DownloadOptions` 默认值 |
| CI | **本机交互会话运行 `dotnet test`**（FlaUI #168：托管 runner Session 0 无交互桌面）；自托管 runner + 自动登录在 D6/D7 发布前落地 |
| 视觉校验 | 补充不替代：UIA 断言优先；被测进程内 `Windows.Media.Ocr`（中文）+ 静态区域像素 diff / 动态区域感知哈希容差 |
| 分层纪律 | 单元=纯逻辑（Core）／集成=真实子系统（Steam/Downloads）／UI=真实用户旅程（本规格）；禁止在本层重复断言纯逻辑（倒金字塔） |

---

## 1. 测试分层（保真度纪律）

| 层 | 工具 | 覆盖什么 | 归属 |
|---|---|---|---|
| 单元 | xUnit（纯 BCL） | 纯逻辑：别名归一化、字符串匹配、Result 组合、状态机转移表、路径计算 | arch-20 |
| 集成 | xUnit + 真实子系统 | steamcmd 调用、缓存深拷贝、HTTP 指纹策略、本地 Kestrel 分段 fixture、真实在线 id（`--filter Category=Online`，可跳过） | arch-20 |
| **UI（本规格）** | **xUnit + FlaUI 5.0.0 UIA3 + 真实输入** | 绑定、命令、焦点、弹窗、布局遮挡、中文输入、**用户旅程** | **qa-20** |
| **校准（本规格 §5）** | **xUnit + 裸 HttpClient** | 参数类经验的重标定实测（退避/节流/并发） | **qa-20** |

依据（wpf_ui_testing §4）：保真度 = 测试行为与真实行为的相似程度；Mock/ViewModel 直调让单测好写但更易漏用户侧 bug（绑定拼错、命令断开、IsEnabled 状态机错、遮挡/命中区域、async void 吞异常——这些只有真实旅程才炸）。1.x 时期同款学费：桩函数替换 `QMessageBox` 导致断言时序被桩改变（架构 §4 教训 #12），2.0 从根上避免：**不打桩、不直调 ViewModel、不经 API 层**。

**禁止事项**：
- 禁止在 UI 层重复断言纯逻辑（别名归一化等）——归 Core 单测（T5）；
- 禁止用 `Category=Calibration` 的网络基准冒充 UI 测试（两类在同一程序集，但 trait 与串行集合完全隔离）；
- 禁止「为让测试绿」给被测代码加测试专用分支（`--test-mode` 只允许关闭后台副作用，见 §2.3）。

---

## 2. 接线规格：FlaUI 5.0.0 + xUnit + Xunit.StaFact

### 2.1 NuGet 包清单（锁版本）

| 包 | 版本 | 用途 | 备注 |
|---|---|---|---|
| `FlaUI.Core` | **5.0.0** | Application / AutomationElement / Mouse / Keyboard / Retry / Capturing | NuGet flatcontainer 权威复验（captain 经 7897 代理直查）：**5.0.0 为 flaui.core/flaui.uia3/flaui.uia2 三包共同最新版**；5.0.0（2024-12-08）移除 .NET Core 3.1/5 等旧框架并支持 nullable，net8.0-windows 目标兼容 |
| `FlaUI.UIA3` | **5.0.0** | `UIA3Automation`（WPF 原生 UIA3 通路） | 与 FlaUI.Core 同版本（5.0.0） |
| `xunit` | 2.9.x | 测试框架 | 骨架现为 2.5.3，D0.3 顺带升到 2.9.x；**不跳 xunit 3.x**（StaFact 兼容链未经实证） |
| `Xunit.StaFact` | 1.2.1 | `[StaFact]` / `[WpfFact]`（STA 线程 + WPF SynchronizationContext） | 进程外测试建议同样标注（UIA3 的 COM 调用线程语义一致） |
| `xunit.runner.visualstudio` | 2.8.x | VSTest 适配器（`dotnet test` 可见） | 随 xunit 版本对齐 |
| `Microsoft.NET.Test.Sdk` | 17.8.0 | 测试宿主 | 骨架现状保持 |
| `coverlet.collector` | 6.0.0 | 覆盖率 | 骨架现状保持 |

**版本事实的复验记录（设计对照纪律）**：FlaUI 的 NuGet 最新版为 **5.0.0**（captain 经 7897 代理直查 flatcontainer 实证，三包共同顶版）。早期一度出现的"6.0.0"系对 GitHub main 分支 CHANGELOG 未发布条目的误读，**已撤回**——包版本一律以 NuGet flatcontainer 为权威源，不以搜索片段或仓库 changelog 为准。
**复验条款（经验复验）**：本机默认网络下 NuGet feed 直连不可达（DNS 被 fake-IP 代理接管），版本存在性已由 flatcontainer 复验闭环，但 API 表面（命名空间/类成员）仍需在 D0.3 restore 时实证：
1. **D0.3（FlaUI 冒烟链）restore 时实证**：5.0.0 包在 net8.0-windows 目标下可还原、可编译、可启动；`FlaUI.Core.Application` / `FlaUI.Core.Input.Mouse` / `FlaUI.Core.Input.Keyboard` / `FlaUI.Core.Retry` / `FlaUI.Core.Capturing.Capture` / `FlaUI.UIA3.UIA3Automation` 命名空间与 wpf_ui_testing.md 示例一致。
2. 若实证中发现 API 表面与研究文档不符，把差异写入 `swdm2/docs/` 复验记录并同步本规格（弯路嫌疑处置通道）。
3. 版本锁死后，`FlaUI.Core`/`FlaUI.UIA3` 升级 = 全量回归门（对齐 A8 的 WPF-UI 同款风险对冲逻辑）。

### 2.2 目标 csproj（`swdm2/tests/Swdm2.UiTests/Swdm2.UiTests.csproj`）

骨架现状已有 xunit 2.5.3 / TestSdk / coverlet / `UseWPF`，需补 FlaUI 三包 + StaFact + 串行 runner 配置：

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0-windows</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>
    <IsTestProject>true</IsTestProject>
    <UseWPF>true</UseWPF>
    <RootNamespace>Swdm2.UiTests</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="coverlet.collector" Version="6.0.0" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" />
    <PackageReference Include="Xunit.StaFact" Version="1.2.1" />
    <PackageReference Include="FlaUI.Core" Version="5.0.0" />
    <PackageReference Include="FlaUI.UIA3" Version="5.0.0" />
  </ItemGroup>
  <ItemGroup>
    <Using Include="Xunit" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="..\..\src\Swdm2.App\Swdm2.App.csproj" />
    <ProjectReference Include="..\..\src\Swdm2.Core\Swdm2.Core.csproj" />   <!-- 只读断言辅助（架构 §0）-->
  </ItemGroup>
  <ItemGroup>
    <None Update="xunit.runner.json" CopyToOutputDirectory="PreserveNewest" />
  </ItemGroup>
</Project>
```

`swdm2/tests/Swdm2.UiTests/xunit.runner.json`（**强制串行**：跨进程真实输入 + 单实例互斥）：

```json
{
  "$schema": "https://xunit.net/schema/current/xunit.runner.schema.json",
  "parallelizeAssembly": false,
  "parallelizeTestCollections": false,
  "methodDisplay": "method",
  "diagnosticMessages": false
}
```

### 2.3 进程外启动规约

- 被测 exe 路径解析：`App` 的构建输出 `swdm2/src/Swdm2.App/bin/$(Configuration)/net8.0-windows/Swdm2.App.exe`；测试启动前先 `dotnet build`（本地脚本门）。
- `Application.Launch(exePath, "--test-mode")`：与用户双击 exe 完全一致（独立进程 / 独立 Dispatcher / 真实启动路径）。
- `--test-mode` **只允许**做三件事（由 App 侧实现，D0.1 落地）：
  1. 关闭自动更新检查与版本提示（消除后台网络噪声对断言的干扰）；
  2. 固定窗口位置/大小（左上角 0,0、1280×800，DPI/分辨率一致，wpf_ui_testing §3.3.6）；
  3. 把 Serilog 日志写到 `--log-dir` 指定目录（失败时与截图同卷归档）。
- **禁止** `--test-mode` 改变任何业务路径（假数据、桩服务、跳过校验）——一经发现即测试体系 review 失败。
- Debug 构建保留符号（PDB），失败截图对照源码行号（wpf_ui_testing §2.3.2）。

### 2.4 Screen Object 骨架目录结构

```
swdm2/tests/Swdm2.UiTests/
├─ Screens/                          # Screen Object 映射层（每窗口/页面一个类）
│  ├─ MainShellScreen.cs             #   主窗口 + 导航 + 状态栏
│  ├─ GameSelectScreen.cs            #   游戏选择（搜索/联想/回车）
│  ├─ WorkshopBrowseScreen.cs        #   工坊浏览（搜索/翻页/筛选/勾选/批量）
│  ├─ ModDetailScreen.cs             #   mod 详情（依赖/下载入口）
│  ├─ DownloadsScreen.cs             #   下载页（行级字段 + 暂停/继续/重试/取消）
│  ├─ LibraryScreen.cs               #   库管理（扫描/分类/导入导出/更新检查）
│  ├─ SettingsScreen.cs              #   设置（目录/账号/引擎参数/主题）
│  └─ Dialogs/
│     ├─ MessageBoxScreen.cs         #   原生 MessageBox（#255 路径，禁打桩）
│     └─ SteamGuardDialogScreen.cs   #   Steam Guard 收码弹窗
├─ Fixtures/
│  ├─ SwdmAppFixture.cs              #   类级共享进程（冒烟套件）
│  ├─ SwdmAppFixturePerTest.cs       #   方法级独立进程（下载/搜索关键流程）
│  └─ UiTestCollection.cs            #   [Collection("Ui")] + DisableTestParallelization
├─ Input/
│  ├─ KeyboardPaths.cs               #   真实键盘路径常量（VK_RETURN / Ctrl+V / Tab）
│  ├─ ClipboardHelper.cs             #   SetClipboardText（中文 Ctrl+V 路径）
│  └─ PhysicalClick.cs               #   Mouse.MoveTo + Mouse.Click 封装 + 无 ClickablePoint 时的 InputSimulator 裸 SendInput 兜底（T4）
├─ Vision/
│  ├─ OcrChecker.cs                  #   Windows.Media.Ocr（zh-CN）文本断言
│  └─ PixelDiff.cs                   #   静态区域基线 diff / 动态区域感知哈希容差
├─ Calibration/                      #   §5 参数重标定基准（Category=Calibration，不涉 UI）
│  ├─ B1BackoffCurveTests.cs
│  ├─ B2EndpointThrottleTests.cs
│  ├─ B3ConcurrencyCeilingTests.cs
│  └─ CalibrationReport.cs           #   CSV + Markdown + JSON 输出
├─ Support/
│  ├─ UiTestSettings.cs              #   exe 路径 / 超时 / 工件目录（环境变量可覆盖）
│  ├─ RetryHelper.cs                 #   Retry.While 超时预设（启动 15s / 列表 20s / 完成 120s）
│  └─ ArtifactSink.cs                #   失败截图 + 被测日志拷贝到 TestArtifacts/
└─ Tests/
   ├─ Smoke/                         #   P0 五条主旅程（D5.10）
   ├─ Feature/                       #   P1/P2 场景矩阵（§4.2）
   └─ Regression/                    #   已修 bug 的回归固化（每个用户侧 bug 修复留一条真实输入测试）
```

### 2.5 Fixture 生命周期与清理

```csharp
public sealed class SwdmAppFixture : IDisposable
{
    public Application App { get; }
    public UIA3Automation Automation { get; } = new();

    public SwdmAppFixture()
    {
        KillResidualInstances();                        // 单实例互斥：先杀残留进程
        var exe = UiTestSettings.TargetExePath;         // §2.3 解析规则
        App = Application.Launch(exe, "--test-mode", $"--log-dir={UiTestSettings.LogDir}");
    }

    public Window WaitForMainWindow() =>                // 启动等待：显式超时，绝不 Sleep
        Retry.While(() => Automation.GetDesktop()
                .FindFirstDescendant(cf => cf.ByAutomationId("MainShell"))?.AsWindow(),
            el => el != null, TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(0.2))
            .Result?.AsWindow() ?? throw new InvalidOperationException("主窗口 15s 内未出现");

    public void Dispose()
    {
        try { App?.Close(); } catch { try { App?.Kill(); } catch { } }
        Automation?.Dispose();
        KillResidualInstances();                        // 兜底：清理残留，避免下一个测试附着旧实例
    }

    private static void KillResidualInstances()
    {
        foreach (var p in Process.GetProcessesByName("Swdm2.App")) { try { p.Kill(); p.WaitForExit(2000); } catch { } }
    }
}
```

- **冒烟套件（P0）**：`IClassFixture<SwdmAppFixture>`，类级共享进程（快 10 倍以上）；
- **关键流程（下载/搜索，P0 内）**：`IClassFixture<SwdmAppFixturePerTest>`，每测试方法新进程（隔离最强，崩溃不殃及下一个测试）；
- Dispose 内先截图后关进程（失败现场保留，见 §4.3 示例）。

### 2.6 串行集合

```csharp
[CollectionDefinition("Ui", DisableParallelization = true)]
public sealed class UiCollection : ICollectionFixture<SwdmAppFixture> { }
```

所有 UI 测试类标注 `[Collection("Ui")]`；Calibration 类标注 `[Collection("Calibration")]`（同样禁并行：网络基准互相污染）。

### 2.7 失败证据工件

```
swdm2/TestArtifacts/
├─ screenshots/  fail_<类>_<方法>_<yyyyMMdd_HHmmss>.png   # Capture.Screen() / Capture.Element(el)
├─ logs/         被测进程 Serilog 日志副本（--log-dir 指定）
├─ ocr/          OCR 断言命中的文本快照
├─ calibration/  §5 基准输出（csv / md / json）
└─ regressions/  bug 复测记录附件
```

纪律：**无人值守失败时，日志只写 "element not found" 等于什么没说**——每条失败测试必须留当时屏幕截图 + 被测日志（wpf_ui_testing §3.3.5）。

---

## 3. 被测 XAML 的 AutomationId 命名约定（选择器鲁棒性）

### 3.1 命名规则

- 格式：`<视图>_<控件>_<语义>`，PascalCase，纯 ASCII，不带空格/特殊字符。
- 例：`GameSelectPage_SearchBox_Input`、`DownloadsPage_TaskList_Item_PauseButton`。
- `x:Name` 自动成为 AutomationId（WPF 原生映射），两者等价可用；**同一元素禁止同时给两种语义不同的值**。
- 数量约束：**每个可交互元素一个 id**；纯展示元素（标题文本块）可用 `<视图>_<语义>Text` 便于断言读取（如 `DownloadsPage_TaskList_Item_SpeedText`）。
- 新增可交互元素不带 id = 所在任务不通过（T1）；视觉/架构 review 时逐 XAML 文件核对。

### 3.2 保留 id 清单（App 侧契约，与 t2 视觉规格对齐）

> 本表是 **App 与 UiTests 的接口契约**：visual-20 实现 XAML 时逐条落实；qa-20 写 Screen Object 时逐条引用。新增控件必须先扩本表再写代码。
> **载体合规（A7 修正 / SP-2 实证，强制）**：AutomationId 只设在**可靠载体**上 = Window / 内容控件（Button·TextBox·ListBox·CheckBox·ComboBox·TextBlock）/ 自绘 UserControl / WPF-UI 模板部件固定 id（如 `TitleBarMinimizeButton/MaximizeButton/CloseButton`）。**禁止**把测试锚点压在 UIA 提升型容器上：`ui:TitleBar`、`ui:Card`、`Grid`、`ContentControl`——这些容器自身不在 UIA 树中，XAML 上设的 AutomationId 会被"吞"（SP-2 实测：8/9 期望元素可达，唯一缺失即此类容器）。下表所有 id 均落在可靠载体上。

| 视图 | AutomationId | 控件 | 说明 |
|---|---|---|---|
| 主窗口 | `MainShell` | Window | 启动断言锚点 |
| 主窗口 | `MainShell_Nav_<页面>` | 导航按钮 | 导航主旅程 |
| 主窗口 | `MainShell_StatusBar_ConnectivityText` | Text | 端点可达性状态（D5.9） |
| 游戏选择 | `GameSelectPage_SearchBox_Input` | TextBox | 中文输入主路径 |
| 游戏选择 | `GameSelectPage_SuggestionList_Items` | ListBox | 联想候选（原地更新，A10） |
| 游戏选择 | `GameSelectPage_SuggestionList_Item` | ItemTemplate 根 | 每项复用同一 id（§3.4） |
| 游坊浏览 | `WorkshopBrowsePage_SearchBox_Input` / `_SearchButton_Action` | TextBox / Button | 搜索 |
| 工坊浏览 | `WorkshopBrowsePage_ResultList_Items` / `_Item` | ListBox + 模板项 | 虚拟化路线 A |
| 工坊浏览 | `WorkshopBrowsePage_ResultList_Item_SelectCheckBox` | CheckBox | 行级勾选 |
| 工坊浏览 | `WorkshopBrowsePage_PagePrevButton` / `_PageNextButton` / `_PageNumberText` | Button / Text | 翻页 |
| 工坊浏览 | `WorkshopBrowsePage_Filter_<标签名>_CheckBox` | CheckBox | 筛选勾选 |
| 工坊浏览 | `WorkshopBrowsePage_SortComboBox` | ComboBox | 排序（真实点击展开 + 键盘↑↓选择） |
| 工坊浏览 | `WorkshopBrowsePage_SelectAllCheckBox` | CheckBox | 全选 |
| 工坊浏览 | `WorkshopBrowsePage_BatchDownloadButton` | Button | 批量入队（启用态随勾选变化） |
| mod 详情 | `ModDetailPage_TitleText` / `_DependencyList_Items` / `_DownloadButton` | Text / ListBox / Button | 详情与依赖 |
| 下载页 | `DownloadsPage_TaskList_Items` / `_Item` | ListBox + 行模板 | 任务行 |
| 下载页 | `DownloadsPage_TaskList_Item_<字段>` | `_FileNameText` `_StateText` `_SpeedText` `_EtaText` `_SegmentsText` `_SizeText` | IDM 体感字段（D5.7） |
| 下载页 | `DownloadsPage_TaskList_Item_<动作>` | `_PauseButton` `_ResumeButton` `_RetryButton` `_CancelButton` `_PriorityButton` | 行级动作按钮，启用态=状态机驱动 |
| 库管理 | `LibraryPage_ScanButton` / `_CategoryTree` / `_EntryList_Items` | Button / TreeView / ListBox | 扫描与分类 |
| 库管理 | `LibraryPage_ImportButton` / `_ExportButton` / `_UpdateCheckButton` | Button | 导入导出与更新检查 |
| 设置 | `SettingsPage_RootDirBox_Input` / `_BrowseButton` | TextBox / Button | 目录 |
| 设置 | `SettingsPage_AccountBox_Input` / `_PasswordBox_Input` / `_RememberPasswordCheckBox` | TextBox / PasswordBox / CheckBox | 账号（DPAPI，密码不回显） |
| 设置 | `SettingsPage_<选项名>Box_Input` | TextBox/Slider/CheckBox | 引擎参数（Options 全暴露 + 热生效，D5.8） |
| 设置 | `SettingsPage_ThemeToggle` | Toggle | 主题切换 |
| 弹窗 | `SteamGuardDialog_CodeBox_Input` / `_ConfirmButton` | TextBox / Button | 收码弹窗（A11） |
| 弹窗 | 原生 MessageBox | — | 按 #255：`ModalWindows` + `FindFirstDescendant(OkButton / 确定性文本仅作兜底)` |

### 3.3 选择器规则

| 规则 | 允许 | 禁止 |
|---|---|---|
| 定位 | `ByAutomationId`（≈80% 鲁棒性来源，wpf_ui_testing §2.5/§7.1） | 显示文本（本地化即崩）、屏幕坐标、菜单层级索引、ClassName（WPF 通用类名无区分度） |
| 层级 | 页面级容器 id 至多用一次，其余一律 `FindFirstDescendant` 深度搜索 | 长链 `FindChild(...).FindChild(...)`（脆弱） |
| 弹窗 | `window.ModalWindows` → 按钮按 id / 且仅当 id 缺失时按本地化文本兜底 | 用 `ByName` 作为主选择器 |
| 等待 | `Retry.While` + 显式超时 | `Thread.Sleep` |

### 3.4 数据模板与虚拟化列表

- 列表容器 id = `<视图>_<列表>_Items`；**项模板根元素**给 `<容器>_Item`（所有行复用同一 id），行内控件 = `<容器>_Item_<控件>`。行级定位走 `list.Items[i]` 再向下找——**禁止**按行索引拼 id（数据增删即崩）。
- 虚拟化采用架构裁决的**路线 A**（VSP Recycling + `ScrollUnit="Pixel"`）：虚拟化回收项仍完整暴露 UIA 树，对 FlaUI 友好；**这也是放弃 PCL2 惰性实例化（路线 B）的裁决依据之一**（架构 §4 末段）。
- 翻页/滚动断言用按钮 + `PageNumberText`；滚轮场景先物理点击列表区域获焦再注入 wheel（wpf_ui_testing 未覆盖 wheel 注入细节 → §9 待复验项）。

### 3.5 鲁棒性检查清单（每条 UI 测试 PR 自检）

1. 所有断言元素均按 §3.2 保留 id 定位？是。
2. 全程无 `Thread.Sleep`？是。
3. 键盘注入前先**物理点击**目标控件获焦（SP-2 顺序契约，程序化 Focus/SetForeground 不可靠）？是（Q3）。
4. 失败路径有截图 + 日志归档？是。
5. 新增可交互元素有 id 并已扩 §3.2 表？是（T1）。

---

## 4. 真实输入覆盖矩阵（1.x 对等场景全映射）

### 4.0 真实输入路径速查

| 输入 | API | 说明 |
|---|---|---|
| 中文进 TextBox（主） | `box.Enter("饥荒")` | ValuePattern 语义级设值，WPF TextBox 原生支持；先断言 `box.Text == "饥荒"` 确认值真进控件 |
| 中文进 TextBox（真键盘备选 A） | `Keyboard.TypeText("饥荒")` | `KEYEVENTF_UNICODE` → `WM_CHAR`，不经 IME，真实输入消息流 |
| 中文进 TextBox（真键盘备选 B） | `ClipboardHelper.SetText("饥荒"); Keyboard.Type(VK_CONTROL, VK_V)` | 真实击键 + 剪贴板，兼顾真实性与中文可靠性 |
| **回车触发类操作** | `Keyboard.Type(VirtualKeyShort.RETURN)` | **强制真实键盘事件**（搜索/确认/默认按钮），禁止命令直调；**按键前必须先物理点击使窗口/控件获得焦点**（SP-2 实证：程序化 `Focus()`/`SetForeground()` 不可靠，Windows 前台锁定） |
| 中文/纯 CJK 文本 | `box.Enter("饥荒")`（ValuePattern） | **CJK 主路径**（SP-2 实测完美，断言值真进控件） |
| 含空格/标点的 ASCII 文本 | 剪贴板 + 真实 `Ctrl+V`；或换纯字母词 | **SP-2 实证 `Enter()` 吞 ASCII 空格/撇号**（`"Don't Starve"`→`"Don'tStarve"`）；游戏名等含标点场景必须 Ctrl+V 路径 |
| 鼠标点击（默认） | `Mouse.MoveTo(el.ClickablePoint); Mouse.Click(MouseButtonType.Left)` | 真实光标 + 真实事件（#323 证据：会夺物理鼠标焦点 → 本机运行时 CI 机器不得同时有人用）；**同时是"获焦点"的标准手段**（上条） |
| 语义级 Invoke（仅只读场景） | `el.AsButton().Invoke()` | 仅用于**断言只读触发**的场景；用户旅程主路径必须物理点击（测"遮挡/命中区域"类用户侧 bug） |
| 无 ClickablePoint 兜底 | ① 退到包围矩形中心点击（`el.BoundingRectangle.Center()`，SP-2 实测自绘卡片内容 Button 走此路）；② InputSimulator 裸 `SendInput` 到 `element.PointToScreen()` 坐标 | T4；被遮挡/虚拟化离屏/自绘卡片按钮时使用（比 InvokePattern 更真实） |

> **输入顺序契约（SP-2，强制）**：任何键盘注入（Enter/Ctrl+V/VK_RETURN/Unicode）之前，**先真实点击目标控件或其容器使窗口/控件获得焦点**；禁止依赖程序化 `box.Focus()` / `win.Focus()` / `SetForeground()` 作为唯一获焦手段（spike 实测真实回车在未获焦时不触发 TextBox 的 PreviewKeyDown 处理器）。

### 4.1 冒烟主旅程（P0，D5.10 交付，5 条）

1. **启动** → `MainShell` 出现（15s 显式等待）→ 版本号/标题正确 → 状态栏连通性文本可见。
2. **搜索**（游戏选择）→ 输入"饥荒"（或 "Don't Starve"）→ 真实回车 → 命中同一游戏（中英别名归一化，A10/Core 职责，UI 层只断言呈现）。
3. **详情** → 双击/回车打开 mod 详情 → 依赖列表非空（来自 Web API）。
4. **下载** → 入队 → 等待完成（`Category=Online` 环境下）→ 状态 `Completed` + 产物文件存在。
5. **库** → 扫描 → 分类树/列表呈现刚才的产物（原子认领 D10）。

### 4.2 全量覆盖矩阵

> 列：1.x 场景（1.x 模块）｜2.0 视图/控件 id｜真实输入路径｜断言点｜覆盖不变量｜优先级/DAG 任务

| # | 1.x 场景（1.x 模块） | 2.0 视图 / 控件 | 真实输入路径 | 断言点 | 不变量 | P / 任务 |
|---|---|---|---|---|---|---|
| 1 | 启动与主窗口（`main_window.py`） | `MainShell` | `Application.Launch` | 主窗口 15s 内出现；标题含版本号；状态栏连通文本可见 | T3 | P0 / D0.2（spike 已冒烟覆盖，产品接线回归） |
| 2 | 游戏搜索（`main_window.py` 搜索框） | `GameSelectPage_SearchBox_Input` + `_SearchButton_Action` | 物理点击 SearchBox 获焦 → `Enter("饥荒")`（CJK 主路径）→ 断言文本 → `Mouse.MoveTo` 搜索按钮 + `Mouse.Click` | 结果列表出现且 `Items.Count > 0`；首项名称含"饥荒"（或双语等价命中） | A10 | P0 / D5.4 |
| 3 | 搜索联想（1.x 联想重做 bug） | `GameSelectPage_SuggestionList_Items` | 物理点击获焦 → 键入前缀 "don"（纯字母，Unicode 键注入；含空格/标点词用 Ctrl+V）→ 停 300ms | 联想列表原地更新（`Items` 引用不变、内容变化），无重建闪烁；中英别名命中同一游戏 | A10（原地更新） | P0 / D5.4 |
| 4 | 回车确认（1.x 回车去重 bug） | 同上 | 真实 `Keyboard.Type(VK_RETURN)` | 回车触发搜索且**不重复触发**（一次请求一个结果集）；联想列表在选中后收敛 | A9 即时反馈 | P0 / D5.4 |
| 5 | 翻页（`workshop_tab.py` 分页） | `WorkshopBrowsePage_PageNextButton` / `_PagePrevButton` / `_PageNumberText` | 真实点击下一页 → 等结果 → 上一页 | 页号文本随点击递增/递减；列表内容变化（首项名称变化）；翻页期间按钮禁用态出现 | A9 | P1 / D5.5 |
| 6 | 筛选勾选（`tag_bar.py` 标签筛选） | `WorkshopBrowsePage_Filter_<标签>_CheckBox` / `_SelectAllCheckBox` | 真实点击复选框 | 列表按筛选收敛（`Items.Count` 变化）；全选 → 行级 CheckBox 全部勾选态 | 无 | P1 / D5.5 |
| 7 | 列表勾选 + 批量下载 | `WorkshopBrowsePage_ResultList_Item_SelectCheckBox` + `_BatchDownloadButton` | 真实点击 2 行 CheckBox → 批量按钮 | 批量按钮由禁用→启用；点击后下载页出现 2 条 `Queued` 任务 | D3 | P1 / D5.5→D5.7 |
| 8 | 列表滚动/虚拟化（路线 A） | `WorkshopBrowsePage_ResultList_Items` | 预置千项数据 → 真实点击滚动条/翻页到达尾部 | 滚动期间无元素丢失（首尾项均可定位）；帧计数（视觉域另测） | A2 | P2 / D5.5 |
| 9 | mod 详情（`detail_dialog.py`） | `ModDetailPage_*` | 列表项**真实双击**或选中后真实回车 | 详情页出现；`_DependencyList_Items` 非空；返回栈回浏览页（PageStack 语义） | 无 | P0 / D5.6 |
| 10 | 下载启动（`downloads_tab.py` 入队） | `DownloadsPage_TaskList_Item` | 详情页真实点击 `_DownloadButton` | 任务行出现；状态 `Queued→Preparing→Downloading`（显式等待序列，不轮询 sleep） | D1/D2 | P0 / D3.7 |
| 11 | 下载暂停 | `DownloadsPage_TaskList_Item_PauseButton` | 真实点击 Pause | 状态转 `Paused`；按钮组切换（Resume 启用 / Pause 禁用）；**暂停任务不占并发槽**（入队第二个任务立即开始） | D4 | P0 / D3.7 |
| 12 | 下载继续 | `_ResumeButton` | 真实点击 Resume | 状态回 `Downloading`；续传从已下字节继续（下载页字段或暂存区文件大小断言） | D7 | P0 / D3.7 |
| 13 | 下载失败重试 | `_RetryButton` | 构造失败（离线/断服务）→ 真实点击 Retry | 状态回 `Queued/Preparing`；失败→重试闭环存在；**provider 回退时 UI 出现"已切换引擎"提示** | D2（链回退） | P0 / D4.4 |
| 14 | 下载取消 | `_CancelButton` | 真实点击 Cancel | 状态 `Cancelled`；槽位立即释放（后续任务顶上）；steamcmd 场景下**无僵尸进程**（任务管理器进程计数断言） | D4 | P0 / D3.7 |
| 15 | 下载体感字段（IDM 对标） | `_SpeedText` `_EtaText` `_SegmentsText` | 下载中观察（轮询 `Retry.While` 断言字段变化） | 速度/ETA 真实刷新；SteamKit 场景分段数 > 1；**steamcmd 场景分段数 = N/A**（诚实降级，D9） | D9 | P1 / D4.9 |
| 16 | 库扫描与分类（`library_tab.py`） | `LibraryPage_ScanButton` / `_CategoryTree` / `_EntryList_Items` | 真实点击扫描 → 等待完成 | 分类树节点数与扫描产物一致；**未完成任务产物不被认领**（暂存区文件不在库中） | D10 | P1 / D6.1 |
| 17 | 库导入导出 | `_ImportButton` / `_ExportButton` | 真实点击导出 → 选目录对话框（真实路径填写）→ 导入 | 导出文件存在且非空；导入后库条目数一致 | 无 | P2 / D6.1 |
| 18 | 更新检查弹窗（1.x 桩函数学费现场） | `LibraryPage_UpdateCheckButton` + 原生 MessageBox | 真实点击更新检查 → **弹窗打开时**在 UIA 树中读取标红态 | 弹窗出现（`ModalWindows` 非空）；**弹窗打开期间**标红集合非空（在弹窗按钮被点掉之前读取，正是 1.x 桩函数教训的 C# 正解）；点击"确定"后弹窗关闭 | A12 / T2 | P0 / D6.2 |
| 19 | 设置：目录（`settings_tab.py`） | `SettingsPage_RootDirBox_Input` / `_BrowseButton` | 真实输入新路径 → Tab 失焦 | 路径持久化（重启被测进程后仍是新值）；非法路径给出错误提示（Snackbar 可见） | 无 | P1 / D5.8 |
| 20 | 设置：账号 + 记住密码 | `SettingsPage_AccountBox_Input` / `_PasswordBox_Input` / `_RememberPasswordCheckBox` | 真实输入账号密码 → 勾选 → 保存 → **重启被测进程** | 密码框**不回显明文**（UIA 读取 PasswordBox 的值恒为空/掩码）；账号字段已填；DPAPI 文件存在且为密文（二进制不含明文字节，D1.4 的延伸断言） | C2 | P0 / D5.8 |
| 21 | 设置：引擎参数热生效 | `SettingsPage_MaxConcurrentDownloadsBox_Input` 等 | 真实改成 2 → 下载中观察 | **不重启**即生效（并发数变化在下载页观察到）；超范围值被拒绝并提示 | 无 | P1 / D5.8 |
| 22 | 设置：主题切换 | `SettingsPage_ThemeToggle` | 真实点击 | 主题字典切换无闪烁；OCR/像素 diff 断言配色变化（§视觉校验） | A3 | P2 / D5.1 |
| 23 | Steam Guard 收码 | `SteamGuardDialog_CodeBox_Input` / `_ConfirmButton` | 账号路径触发 2FA → 弹窗 → **真实键盘输入验证码** → 真实回车 | 弹窗模态阻塞主窗口；收码后命令继续（登录成功或进入下载） | A11 | P1 / D4.1 |
| 24 | 错误横幅 | Snackbar（`MainShell` 内） | 触发 403/离线场景 | 错误横幅出现且含可读文案 + 日志关联号；不阻塞主流程 | S3/S4 | P1 / D5.9 |
| 25 | 状态栏端点可达性 | `MainShell_StatusBar_ConnectivityText` | 切换代理模式（设置页真实点击）→ 等待探测 | 状态文本如实更新（直连/代理/不可达三态）；不可达时引导文案出现 | S4 | P1 / D5.9 |
| 26 | 视觉校验补充 | 任意 | — | OCR（zh-CN）断言列表项中文标题；静态区域（空态图/Logo）像素 diff；动态列表感知哈希容差 | 视觉 §5 定位 | P2 / D5.2 |

- **每条场景**的失败路径必须留截图 + 被测日志（§2.7）。
- **P0 全部进 Smoke/，P1/P2 进 Feature/**；P2 视觉校验项与 t2 视觉规格的数值令牌对接（阈值由 t2 定）。
- **全量回归**（迭代四要素）：每阶段交付门跑 P0+P1 全绿；每轮迭代新增功能必须**同时新增矩阵行**并在交付门回归（T6）。

### 4.3 测试代码骨架（三例，覆盖矩阵三种典型形态）

**例 1：搜索 + 联想 + 回车（#2/#3/#4）——真实键盘 + 显式等待**

```csharp
public sealed class GameSelectTests : IClassFixture<SwdmAppFixture>
{
    private readonly SwdmAppFixture _f;
    public GameSelectTests(SwdmAppFixture f) => _f = f;

    [WpfFact]
    public void Search_饥荒_回车_命中同一游戏()
    {
        var win = _f.WaitForMainWindow();
        var box = win.FindFirstDescendant(cf => cf.ByAutomationId("GameSelectPage_SearchBox_Input")).AsTextBox();
        Assert.NotNull(box);
        // SP-2 顺序契约：先物理点击获焦点，再注入按键（程序化 Focus/SetForeground 不可靠）
        Mouse.MoveTo(box.ClickablePoint);
        Mouse.Click(MouseButtonType.Left);
        box.Enter("饥荒");                             // CJK 主路径：ValuePattern
        Assert.Equal("饥荒", box.Text);                // 值真进控件

        Keyboard.Type(VirtualKeyShort.RETURN);         // 强制真实回车，禁止命令直调（焦点已在 box 上）

        var list = RetryHelper.WaitForNonEmptyList(win, "GameSelectPage_SuggestionList_Items");
        Assert.Contains(list.Items, i => (i.Name ?? string.Empty).Contains("饥荒"));
    }

    [WpfFact]
    public void Suggestion_前缀输入_原地更新不重建()
    {
        var win = _f.WaitForMainWindow();
        var box = win.FindFirstDescendant(cf => cf.ByAutomationId("GameSelectPage_SearchBox_Input")).AsTextBox();
        Mouse.MoveTo(box.ClickablePoint);              // SP-2：先物理点击获焦点
        Mouse.Click(MouseButtonType.Left);
        Keyboard.TypeText("don");                      // 纯字母 Unicode 键注入（不经 IME）；含空格/标点词改 Ctrl+V
        var list = RetryHelper.WaitForList(win, "GameSelectPage_SuggestionList_Items");
        var firstNames = list.Items.Select(i => i.Name).ToList();
        Assert.NotEmpty(firstNames);
        Assert.Contains(firstNames, n => n.Contains("Don't Starve", StringComparison.OrdinalIgnoreCase));
        // 原地更新断言：联想出现期间再输入一个字符，列表对象引用不变
        var handleBefore = list.Properties.NativeWindowHandle;
        Keyboard.TypeText("n");
        Assert.Equal(handleBefore, list.Properties.NativeWindowHandle);
    }
}
```

**例 2：下载暂停/继续/取消（#11/#12/#14）——方法级独立进程 + 无僵尸进程断言**

```csharp
[Collection("Ui")]
public sealed class DownloadLifecycleTests : IClassFixture<SwdmAppFixturePerTest>
{
    [WpfFact]
    public void 暂停_不占槽_继续_取消_无僵尸进程()
    {
        var fixture = new SwdmAppFixturePerTest();      // 每方法新进程（隔离最强）
        try
        {
            var win = fixture.WaitForMainWindow();
            EnqueueTwoTasks(win);                       // 走真实 UI 入队（#7 路径）
            var row = RetryHelper.WaitForRow(win, state: "Downloading");

            Mouse.ClickOn(row, "DownloadsPage_TaskList_Item_PauseButton");
            AssertState(row, "Paused");                 // D4：暂停不占槽 → 第二任务立即开始
            var row2 = RetryHelper.WaitForRow(win, state: "Downloading", skipFirst: true);

            Mouse.ClickOn(row, "DownloadsPage_TaskList_Item_ResumeButton");
            AssertState(row, "Downloading");            // 续传继续（D7）

            Mouse.ClickOn(row, "DownloadsPage_TaskList_Item_CancelButton");
            AssertState(row, "Cancelled");
        }
        finally
        {
            ArtifactSink.CaptureOnFailure(fixture);     // 失败截图 + 日志（Dispose 前在断言失败瞬间捕获）
            fixture.Dispose();
        }
        Assert.NoZombieProcesses("Swdm2.App", "steamcmd");   // 取消后无僵尸进程（D4 三段式收尾）
    }
}
```

**例 3：更新检查弹窗（#18）——#255 路径，弹窗打开时读标红态（1.x 桩函数学费的 C# 正解）**

```csharp
[WpfFact]
public void 更新检查_弹窗期间_标红态存在()
{
    var win = _f.WaitForMainWindow();
    Mouse.ClickOn(win, "LibraryPage_UpdateCheckButton");

    var dialog = Retry.While(() => win.ModalWindows.FirstOrDefault(),
        el => el != null, TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
    Assert.NotNull(dialog);                             // MessageBox 该弹还弹（禁打桩，A12/T2）

    // 关键：在弹窗按钮被点掉之前读取标红集合 —— 1.x 桩函数教训的复现点
    var marked = win.FindFirstDescendant(cf => cf.ByAutomationId("LibraryPage_UpdateMarkList_Items"));
    Assert.NotNull(marked);
    Assert.NotEmpty(marked.AsListBox().Items);

    var ok = dialog.FindFirstDescendant(cf => cf.ByAutomationId("OkButton")) ??
             dialog.FindFirstDescendant(cf => cf.ByName("确定"));   // id 优先，文本仅兜底
    Assert.NotNull(ok);
    Mouse.Click(ok.AsButton());
}
```

---

## 5. 参数重标定基准实测方案（经验复验纪律）

### 5.0 纪律与闭环流程

> 用户纪律：既往经验（含本团队自己得出的结论）不得照单全收——参数类经验移植到新栈/新环境**必须实测重新标定**；具体争议点先问"**能否缩短/能否更小**"再验证采纳。

闭环流程（自qa-20 起，arch-20 / captain 协同）：

```
qa-20 执行基准（双网络环境）
  → 原始数据 csv/json + Markdown 报告（swdm2/TestArtifacts/calibration/）
  → 汇总报告 swdm2/docs/calibration_1.md（B1/B2）/ calibration_2.md（B3）
  → arch-20 按实测锁定 SteamOptions / DownloadOptions 默认值
  → captain 采信确认 → architecture_2.0.md §4 学费表去除对应 ⚠️ 标注
  → 下一轮交付门回归验证（重跑基准复现）
```

- **落点**：D2.6（退避/节流，首次）与 D4.8（并发/超时/重叠字节）。
- **网络不稳处置（设计对照纪律）**：基准失败/空结果**不得**读作"该参数不可行"；重跑或换网络条件重取后再下结论；两次以上同条件失败才归档为"当前网络不可测"。
- **保证数据可信度**：每档候选重复 n≥3（成功率取置信区间下界），单次结果一律不采信。

### 5.1 基准 B1：429 退避曲线

- **问题**：1.x 退避 30s 起 / 90s 封顶是否可以更短？（先问"能否更短"）429 响应从不带 `Retry-After`（1.x 实测，响应体 334KB，架构 S2），必须客户端自退避。
- **目标端点**：`api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/`（POST，匿名可用，主源）。
- **方法（三段法，继承 1.x `tests/_bench_steam_rate.ps1` 的 Phase A/B/C 结构）**：
  - **Phase A（进入限流态）**：用**限流指纹**（裸 Chrome UA **不带** Accept-Language，1.x 实测必 429，3/3 校验）连续请求，记录首个非 200 的序号——确认端点当前处于可复现的限流行为下。
  - **Phase B（恢复曲线探测）**：触发 429 后，按候选档 **[5, 10, 15, 20, 30, 45, 60, 90]s** 依次等待后探测一次（正确指纹头四件套），每档 n=3，记录首个 200 出现的等待时长；**档间冷却 120s** 防上一档 429 污染下一档。
  - **Phase C（复核）**：对满足"成功率 ≥95%"的候选最小档，再连续 10 次正常请求（正确指纹 + 目标间隔）验证稳定恢复。
- **输入**：固定 publishedfileids 列表（含真实 id `3808352517` 与同集合其他 id ≥30 个，1.x 脚本沿用 `$env:TEMP\bench_ids.txt` 同源数据文件，2.0 转为 `TestArtifacts/calibration/bench_ids.txt`）。
- **输出表**（每行一个候选档 × 环境）：

| 参数候选（退避等待 s） | 环境 | 尝试次数 | 实测成功率（200/总数） | 首次恢复用时中位数（s） | 过程中 429 命中次数 | 备注 |
|---|---|---|---|---|---|---|
| 5 | fake-IP | 3 | … | … | … | … |
| 10 | fake-IP | 3 | … | … | … | … |
| … | … | … | … | … | … | … |
| 90 | 直连 | 3 | … | … | … | 1.x 封顶值复核 |

- **判定规则**：`SteamOptions.BackoffInitialMs` ← **成功率 ≥95%（n≥3）的最短等待档**（若 5s 档即成功，先问"是否为指纹未真正触发限流"——Phase A 校验失败则该轮数据作废重跑）；`BackoffMaxMs` ← 100% 成功的最小档。写入报告并给出与 1.x 旧值的差异说明。
- **安全纪律**：基准期间串行执行（Calibration 集合禁并行）；只对**匿名公开端点**施压；触发 429 后立即停止加压转入恢复探测（不做长时间高压）。

### 5.2 基准 B2：端点节流最小间隔

- **问题**：1.x 口径分歧——详情页 3s（基线）vs 6s（csharp_steam_workshop §3.3）/ browse 2s / api 1-2s，**不采信任一旧值**，实测裁决（架构 §8 参数分歧项）。
- **方法**：正确指纹头四件套（S1）下，对目标端点按候选档 **[0.5, 1, 2, 3, 4, 6, 8]s** 串行连发 N=20 请求（锁覆盖 read-sleep-write 全程，对齐 IThrottler 语义），每档 n=2 组，记录 429 率与延迟。
- **端点清单**：`/sharedfiles/` 详情页（Community）、`/workshop/browse/`（Community）、`GetPublishedFileDetails`（API）、`storesearch`（Store）。
- **隔离**：档间冷却 120s（一旦 429 触发会污染后续档的测量）；两组环境（fake-IP 代理 / 直连家庭宽带）。
- **输出表**：

| 参数候选（间隔 s） | 端点 | 环境 | 请求数 | 429 次数 | 429 率 | 平均延迟（ms） | 吞吐（req/min） |
|---|---|---|---|---|---|---|---|
| 0.5 | sharedfiles | fake-IP | 20 | … | … | … | … |
| 3 | sharedfiles | fake-IP | 20 | … | … | … | … |
| 6 | sharedfiles | fake-IP | 20 | … | … | … | … |
| … | … | … | … | … | … | … | … |

- **判定规则**：`IThrottler` 默认间隔 ← **429 率 = 0 的最短间隔档**；若 3s 档与 6s 档 429 率同为 0，取 3s（"能否更短"优先）；若 0.5s 也为 0，记录"当前环境下无节流触达"，但仍保守取 1s 作为默认并标注"实测环境可能不代表全部用户网络"。

### 5.3 基准 B3：并发上限

- **问题**：`MaxConcurrentMetadataQueries`（元数据并发）、`MaxChunkParallelism`（起点 8=DepotDownloader）、`MaxConnectionsPerServer`（起点 8=IDM）、`MaxConcurrentDownloads`（起点 1，问"能否更大"）——问"能否更大/更小"。
- **方法分两类**（**禁止**用真实公网 CDN 测分段并发——家里宽带上下行会伪装成并发拐点）：
  - **B3a 元数据并发**（真实 API）：阶梯 **[1, 2, 4, 8, 16, 32]** 并发拉 `GetPublishedFileDetails` batch（itemcount=官方上限），每档持续 30s，记录吞吐与错误率（429/超时）。
  - **B3b 分段并发**（本地 Kestrel fixture，架构 D4.5 同款）：控速的可 Range 本地服务器（loopback 千兆），阶梯 **[2, 4, 8, 16, 32]** 分段下大文件（≥500MB 稀疏占位），记录带宽增益拐点；同时验证重叠字节比对（`OverlapBytes` 候选 [16, 32, 64]）的续传正确性。
- **错误率门槛**：< 2%（高于则该档不可用）。
- **输出表**：

| 参数候选（并发数） | 场景 | 环境 | 持续（s） | 完成量（字节/请求） | 吞吐（MB/s 或 req/s） | 错误率 | 相对前一档增益 | 拐点判定 |
|---|---|---|---|---|---|---|---|---|
| 1 | 元数据 | 真实 API | 30 | … | … | … | — | 基线 |
| 8 | 元数据 | 真实 API | 30 | … | … | … | … | … |
| 2 | 分段 | 本地 Kestrel | 30 | … | … | … | — | 基线 |
| 16 | 分段 | 本地 Kestrel | 30 | … | … | … | … | 增益 <10% → 拐点 |
| … | … | … | … | … | … | … | … | … |

- **判定规则**：取**增益 ≥10% 的最大档**为默认值（超过后增益 <10% 视为拐点，不浪费连接/内存）；错误率优先于吞吐（任何档错误率 ≥2% 直接排除）。

### 5.4 可执行骨架（xUnit `Category=Calibration`，裸 HttpClient）

> 基准是**网络测量程序**，不依赖 FlaUI / 不启动被测 App，用 BCL `HttpClient` 直测，避免被测客户端实现的二次影响（客户端实现正确性由集成测试管）。放在 `Swdm2.UiTests/Calibration/` 的理由：复用唯一测试项目和 `dotnet test --filter Category=Calibration` 命令（D2.6/D4.8 验证命令一致），无需新项目（对齐架构五项目骨架）；副作用隔离：独立集合 + 默认 `Skip`（无网络时）。

```csharp
[Trait("Category", "Calibration")]
[Collection("Calibration")]                       // 禁并行：网络基准互相污染
public sealed class B1BackoffCurveTests
{
    private static readonly HttpClient Http = new(new SocketsHttpHandler
    {
        Proxy = CalibrationEnv.Proxy,             // 环境变量 SWDM2_BENCH_PROXY：null=直连 / http://127.0.0.1:7897=fake-IP
        PooledConnectionLifetime = TimeSpan.FromMinutes(2)
    });

    public static IEnumerable<object[]> Candidates() =>
        new[] { 5, 10, 15, 20, 30, 45, 60, 90 }.Select(s => new object[] { s });

    [Theory]
    [MemberData(nameof(Candidates))]
    public async Task Backoff_候选档_实测成功率(int waitSeconds)
    {
        var ids = CalibrationFixtures.LoadIds();              // ≥30 个真实 publishedfileid
        var results = new List<ProbeResult>();
        for (var i = 0; i < CalibrationEnv.Repeats; i++)      // n≥3
        {
            await Task.Delay(TimeSpan.FromSeconds(120));      // 档间冷却（防上一档 429 污染）
            await PhaseA.EnterLimitedStateAsync(Http, ids);  // 限流指纹确认可复现（失败则 Assert.Skip 重跑）
            await Task.Delay(TimeSpan.FromSeconds(waitSeconds));
            results.Add(await PhaseB.ProbeOnceAsync(Http, ids, fingerprints: RequestFingerprints.All));
        }
        var success = results.Count(r => r.StatusCode == 200 && r.ResultCode == 1);
        CalibrationReport.Append("B1",
            row: new { 候选 = waitSeconds, 环境 = CalibrationEnv.Env, 尝试 = results.Count,
                       成功率 = $"{success}/{results.Count} ({success * 100.0 / results.Count:F0}%)",
                       首次恢复中位数s = results.MedianRecovery(), 过程429 = results.Count429 });
        Assert.True(success * 100.0 / results.Count >= 0, "基准记录不按 Assert 成败判定，只看输出表");
    }
}
```

- 执行：`dotnet test swdm2/tests/Swdm2.UiTests --filter Category=Calibration`（加 `SWDM2_BENCH_PROXY=http://127.0.0.1:7897` 环境变量跑 fake-IP 组；不设为直连组）。
- **网络不稳重跑**：单 Theory 档失败（超时/异常）→ 该档标 `EXC` 写入 CSV，重跑命令仅跑该档（`--filter "FullyQualifiedName~B1BackoffCurveTests.Backoff_候选档_实测成功率(waitSeconds:30)"`）。

### 5.5 输出格式规范

- CSV（原始逐请求）：`calibration/<基准>_<日期>.csv`，列：`idx,phase,status,ms,result,len,candidate,env`（继承 1.x 脚本列结构，加 candidate/env）。
- Markdown（汇总）：`calibration/<基准>_<日期>.md`，含 §5.1-§5.3 三张输出表的实测值 + 判定结论 + 与旧值（1.x）对照差异说明。
- JSON（机读快照）：`calibration/<基准>_<日期>.json`，供 arch-20 脚本校验"实测值已写入 appsettings.json 默认值"。
- 最终归档：`swdm2/docs/calibration_1.md` / `calibration_2.md`（D2.6 / D4.8 交付物）。

### 5.6 与 1.x 既有脚本的对照继承

| 1.x `tests/_bench_steam_rate.ps1` 元素 | 2.0 继承方式 |
|---|---|
| 三段法（A 进入限流 → B 恢复探测 → C 间隔扫描） | B1 = A+B；B2 = C 的升级（候选档扩展 + 档间冷却 + 端点矩阵） |
| CSV 日志 `idx,phase,status,ms,result,len` | 原样继承，加 `candidate,env` 两列 |
| 单线程串行 | xUnit Calibration 集合禁并行 |
| 代理固定 `http://127.0.0.1:7897` | 环境变量化（双网络环境矩阵） |
| 探测 id 列表 | 同源真实 id 列表文件 |
| 手工跑、结果只回控台 | 落盘 csv/md/json + 报告文档 + Options 锁定闭环 |

---

## 6. CI：本机交互会话运行（FlaUI #168 结论）

### 6.1 为什么托管 runner 不可用

FlaUI issue #168：CI（TeamCity / GitHub Actions 托管 runner / Azure DevOps 托管 agent）以**服务身份运行在 Session 0**，没有交互桌面——UIA 拿不到窗口、`SendInput` 注入无处落地，构建直接挂起。**任何在无交互会话环境跑 UI 测试的尝试都会得到假失败或挂死，不是"测试不可行"**（设计对照纪律：这是环境限制，不读作方案问题）。

### 6.2 现阶段（开发期）命令清单

| 场景 | 命令 | 频率 |
|---|---|---|
| 日常开发 | `dotnet build swdm2/Swdm2.sln -c Debug -warnaserror` | 每次提交前（0 警告 0 错误） |
| UI 冒烟（P0） | `dotnet test swdm2/tests/Swdm2.UiTests --filter "Category=FlaUI&Category=Smoke"` | 每日 / 每次 UI 改动 |
| 全量 UI | `dotnet test swdm2/tests/Swdm2.UiTests --filter Category=FlaUI` | **每阶段交付门**（迭代四要素：全量回归含新增与关联交互） |
| 参数基准 | `dotnet test swdm2/tests/Swdm2.UiTests --filter Category=Calibration` | D2.6 / D4.8 节点 + 每次默认值变更后复测 |
| 全量方案回归 | `dotnet test swdm2/Swdm2.sln` | D7.1（发布冲刺） |

- 一律在**本机交互会话**运行（用户登录的桌面会话，非 Session 0）。
- 测试期间机器不得同时有人操作物理鼠标（#323 夺焦点）。
- **SP-3 双通道（本机 DSH 沙箱例外）**：本机 harness 沙箱内 `dotnet test` 的 testhost 启动即崩（`SetParentProcessExitCallback` → `Win32Exception(5)` 跨进程句柄拒；Test SDK 17.8/17.13、x64/AnyCPU 同崩），spike 期间改用**控制台驱动模式**（`dotnet run` 反射执行同一批 `[WpfFact]`，真实输入链路完全一致，输出落盘 md）。规则：**产品回归用桌面 `dotnet test`（t3 契约）**，沙箱内临时回归用驱动模式——两通道断言同源，切换不改测试代码。

### 6.3 自托管 runner（D6/D7 发布前落地，不在本轮范围）

1. **自动登录**：注册表 `AutoAdminLogon` 或 Windows Task Scheduler 登录任务，开机即进入交互会话；runner 进程在该会话内跑 §6.2 命令。
2. **防锁屏**：测试期间 `SetThreadExecutionState`（`ES_CONTINUOUS | ES_DISPLAY_REQUIRED`）；锁屏时 `SetCursorPos` 与部分 UIA 调用仍可用但**截图会黑屏**——截图/视觉断言必须有亮屏保证。
3. **窗口几何一致**：`--test-mode` 固定 0,0 + 1280×800，DPI 感知（A4），避免分辨率差异导致 ClickablePoint 偏移。
4. **串行 + 单实例**：xunit.runner.json 禁并行 + fixture 启动前杀残留进程。
5. **失败产物归档**：`TestArtifacts/` 全量上传（截图 + 被测日志 + OCR/校准输出）。
6. **触发策略**：定时（每夜全量回归）+ 手动（发布前）；失败通知到 captain。

---

## 7. 测试侧不变量与任务映射

### 7.1 不变量（Q1-Q14，含架构 T1-T6 的展开）

| # | 不变量 | 来源 |
|---|---|---|
| Q1 | 被测元素必须有 AutomationId（§3.2 保留表）；新增可交互元素无 id = 任务不通过 | 架构 T1 / wpf_ui_testing §7.1 |
| Q2 | 弹窗按 #255 真实点击；**禁止打桩替换弹窗实现**；弹窗打开期间的 UI 状态必须在点掉之前读取 | 架构 T2 / A12 / 1.x 桩函数学费 |
| Q3 | 窗口/控件**先物理点击获焦点**再注入按键（程序化 `Focus()`/`SetForeground()` 不可靠，SP-2 实证）；窗口几何显式固定 | 架构 T3 + SP-2 顺序契约 |
| Q4 | 跨进程真实点击注意 #323（夺物理鼠标焦点）；无 ClickablePoint 时先退包围矩形中心点击（SP-2 实证自绘卡片按钮），再 InputSimulator 裸 SendInput 到 `PointToScreen()` 坐标 | 架构 T4 / wpf_ui_testing §1.4 / SP-2 |
| Q5 | UI 层只测真实用户旅程与交互接缝；纯逻辑归 Core 单测；不重复断言（倒金字塔） | 架构 T5 |
| Q6 | 每次迭代完成后 FlaUI 冒烟套件**全量回归**（含新增功能与功能间关联交互） | 架构 T6 / 迭代四要素 |
| Q7 | 等待一律 `Retry.While`/`Wait.Until` 显式超时；禁止 `Thread.Sleep` | wpf_ui_testing §3.1 |
| Q8 | 中文输入主路径 ValuePattern；按键触发类操作必须真实键盘事件；IME 拼音模拟禁止 | 基线决策 4 / §3.5.2 |
| Q9 | 选择器一律 AutomationId；显示文本/坐标/层级索引/ClassName 禁止 | 基线决策 3 / §3.3 |
| Q10 | 失败必有截图 + 被测日志落盘 `TestArtifacts/` | wpf_ui_testing §3.3.5 |
| Q11 | 参数类经验移植必须实测重标定（§5）；未标定前 Options 默认值标 ⚠️，标定后锁定并更新文档 | 经验复验纪律 / 架构 C7/S11 |
| Q12 | `--test-mode` 只关后台副作用 + 固定几何 + 日志目录；禁止改变业务路径 | §2.3 |
| Q13 | Calibration 不用真实公网测分段并发（本地 Kestrel fixture）；元数据并发对真实 API 测 | §5.3 |
| Q14 | 基准空结果/失败不采信为"不可行"（设计对照纪律）；档间隔离 + n≥3 重复 | §5.0 |

### 7.2 场景 × DAG 任务映射（交付门回归清单）

| DAG 任务 | 主责 | 本规格交付物 | 验证命令 |
|---|---|---|---|
| D0.2 | arch-20/captain | 骨架接线：产品 UiTests 引 t3 §2.1 包清单（FlaUI 5.0.0）+ App 空白窗口 AutomationId（spike 已冒烟覆盖，本任务回归到产品工程） | `dotnet build -warnaserror` + UiTests 冒烟（SP-3 驱动/桌面两通道） |
| D3.7 | qa-20 | 下载主旅程（#10-#14 真实输入路径） | `--filter Category=FlaUI` |
| D4.9 | qa-20 | 分段体感（#15：分段数/速度/ETA/按钮态） | `--filter Category=FlaUI` |
| D5.10 | qa-20/V | P0 五条主旅程全量（§4.1，输入三规则落实） | `--filter Category=FlaUI&Category=Smoke` |
| D5.11 | V/qa-20 | 视觉终检：t2 §4 像素断言六清单（与 t2 视觉规格联测） | UiTests + 截图读图 |
| D5.12 | qa-20 | 即时反馈重标定：A9 ≤150ms 按键→可见反馈延迟计时断言（若 t5 合并入 D5.10，则随 P0 冒烟真实旅程计时） | UiTests 计时断言 |
| D6.2 | qa-20 | 更新检查弹窗（#18，#255 路径 + 标红态） | `--filter Category=FlaUI` |
| D6.4 | qa-20 | 复测矩阵：双网络（fake-IP/直连）× 匿名/账号 × 双 provider 全组合 | 矩阵执行表（docs） |
| D2.6 / D4.8 | arch-20/qa-20 | 基准 B1/B2、B3 报告（t3 §5.5 输出格式）+ Options 锁定 | `--filter Category=Calibration` |
| D7.1 | qa-20 | 全量回归（全部 P0/P1/P2 + 单元 + 集成 + 双网络矩阵） | `dotnet test swdm2/Swdm2.sln` |
| D7.2 | qa-20 | bug 测试员连续两轮复测无异常（第二轮直接复用 D6.4 矩阵执行表，不重设计） | 复测表 |

### 7.3 迭代四要素落实

1. **全量回归**：每阶段交付门执行 §7.2 对应任务的全部场景（不是只跑改动点）+ 新增矩阵行同步加入。
2. **讨论组评审**：测试矩阵的新增/删减（场景去留）进 t5 讨论组评审（精简 / 以用户体感为中心 / 基本功能正常运行三原则）。
3. **版本号 + 变更记录**：测试体系变更随阶段版本号（0.1.0→…→2.0.0）记录在 `swdm2/docs/CHANGELOG.md`。
4. **最终交付双条件**：讨论组一致通过 + bug 测试员连续两轮 FlaUI 复测全绿。

---

## 8. 与 `wpf_ui_testing.md` 结论逐条对照（设计对照纪律）

| 研究结论（wpf_ui_testing） | 本规格落点 | 状态 |
|---|---|---|
| FlaUI 5.x（UIA3）为主力 | §0/§2 锁 **5.0.0**（NuGet flatcontainer 实证=三包共同最新版） | 一致（早期"6.0.0"系对 main 分支 CHANGELOG 未发布条目的误读，已撤回；包版本一律以 flatcontainer 为权威源） |
| 真实输入：`Mouse.MoveTo` + SendInput 三路键盘 | §4.0 输入路径速查；主旅程物理点击 | 一致 |
| 中文输入：ValuePattern 主 + 真实 Ctrl+V/Unicode；IME 拼音不做 | §4.0 / Q8 | 一致 |
| xUnit + Xunit.StaFact + 进程外 Application.Launch | §2.1-2.3（`[WpfFact]`、`--test-mode` 三条限定） | 一致 |
| 选择器只 AutomationId；AutomationId 命名 ≈80% 鲁棒性 | §3（保留 id 表 + 禁止项） | 一致（细化为可执行契约表） |
| 显式等待禁 Sleep | Q7 | 一致 |
| Page/Screen Object | §2.4 目录骨架 | 一致 |
| 失败截图 + 日志 | §2.7 TestArtifacts/ | 一致 |
| CI 自托管 runner + 自动登录（#168 Session 0） | §6（现期本机交互会话；D6/D7 落地自托管） | 一致（分阶段） |
| WinAppDriver/Appium 弃用；NovaWindows 观望 | 不引入；仅在 §9 留观测项 | 一致 |
| InputSimulator 作补充（无 ClickablePoint / CJK 裸按键） | Q4 + §2.4 Input/PhysicalClick | 一致 |
| MessageBox #255 不打桩点击 | Q2 + §4.3 例 3 | 一致（并落到具体场景 #18） |
| 视觉校验：Windows.Media.Ocr（zh-CN）+ 像素 diff 兜底 | §2.4 Vision/ + 矩阵 #26 | 一致（定位为补充） |
| 测试分层（单元/集成/UI 三层，倒金字塔禁止） | §1 | 一致（加第四层 Calibration） |
| #323 夺物理鼠标 / #424 #440 ValuePattern 边缘 | §6.2 运行纪律 / §4.0 备选路径 | 一致 |
| 2.2 进程内 vs 进程外（选进程外） | §2.3（`--test-mode` 三条限定是新增细化） | 一致 + 细化 |

---

## 9. 弯路嫌疑与待复验清单

| 项 | 状态 | 复验通道 |
|---|---|---|
| FlaUI 5.0.0 包在 net8.0-windows 目标下的 restore/编译/启动 + 命名空间与 wpf_ui_testing 示例一致 | 包版本**已实证**（captain 经 7897 代理直查 NuGet flatcontainer：flaui.core/flaui.uia3/flaui.uia2 最新均为 5.0.0，"6.0.0"为误读已撤回）；API 表面待 restore 实证 | D0.3 restore 实证；发现差异写入 `swdm2/docs/` 复验记录 |
| `Xunit.StaFact` 1.2.1 × xunit 2.9.x 组合 | 未实证 | D0.3 同上 |
| WPF-UI 4.3.0 控件（FluentWindow/TitleBar/NavigationView）的 UIA 暴露与是否需补 AutomationId | 未实证（架构 §8 弯路嫌疑项） | D0.1 spike 记录 |
| `Windows.Media.Ocr` 中文语言包可用性（zh-CN） | 依赖系统镜像 | D5.2（视觉控件任务）首跑时校验，缺包则降级几何断言（1.x 经验兜底） |
| 滚轮注入（wheel）在 FlaUI 5.0.0 的 API 表面 | 研究文档未覆盖 | 矩阵 #8 滚动场景实现时确认；必要时 InputSimulator 补 |
| 1.x 节流口径 3s vs 6s | 分歧未裁决 | B2 实测裁决（D2.6） |
| 429 退避 30s/90s 旧值 | 未在本网络环境复测 | B1 实测（D2.6） |
| 并发上限 8（DepotDownloader/IDM 起点） | 未复测 | B3 实测（D4.8） |

---

## 10. 附录：引用速查

- 研究：`docs/research2/wpf_ui_testing.md`（FlaUI 方案全量引用清单在其 §8）
- 架构：`swdm2/docs/architecture_2.0.md`（§3.5 UiTests 契约、§4 学费表、§6 DAG、§8 对照协议）
- 基线：`swdm2/docs/design_baseline_2.0.md`（9 条锁定决策）
- 1.x 基准原型：`tests/_bench_steam_rate.ps1`（三段法 + CSV 结构，§5.6 继承表）
- 真实在线测试 fixture：publishedfileid `3808352517`（Web API 匿名可用，架构 S12 复验结论）
- [FlaUI CHANGELOG](https://github.com/FlaUI/FlaUI/blob/main/CHANGELOG.md)（main 分支条目，**非包版本权威源**；包版本以 NuGet flatcontainer 为准：当前 5.0.0，2024-12-08 发布）
- [FlaUI issue #168](https://github.com/FlaUI/FlaUI/issues/168)（CI Session 0 无交互桌面）
- [FlaUI issue #323](https://github.com/FlaUI/FlaUI/issues/323)（跨进程真实点击夺物理鼠标焦点）
- [FlaUI issue #255](https://github.com/Roemer/FlaUI/issues/255)（MessageBox 按钮定位，不打桩）
- [FlaUI Wiki: Retry](https://github.com/FlaUI/FlaUI/wiki/Retry) / [Xunit.StaFact](http://aarnott.github.io/Xunit.StaFact/docs/getting-started.html)
- [NuGet FlaUI.Core](https://www.nuget.org/packages/FlaUI.Core/) / [FlaUI.UIA3](https://www.nuget.org/packages/FlaUI.UIA3/)（flatcontainer = 包版本权威源，5.0.0 为最新）
- [Microsoft: Use the AutomationId Property](https://github.com/dotnet/docs/blob/main/docs/framework/ui-automation/use-the-automationid-property.md)

---

> **门禁状态**：本文档提交 captain 核对（① 与 `wpf_ui_testing.md` 结论逐条一致性——§8 对照表；② 重标定方案可执行性——§5 含可运行骨架、输出表与判定规则）。核对通过后与 t1/t2 合并提交 t5 讨论组终裁，终裁后开放 D0-D7 开发任务。
