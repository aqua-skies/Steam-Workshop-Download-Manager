# SWDM 2.0（WPF）真实用户输入级 UI 测试方案

> 目标：为 SWDM 2.0（C# WPF）建立**模拟真实鼠标点击与键盘输入**的 UI 自动化测试——不走 ViewModel 直调、不打桩、不经 API 层。本文档基于 2025–2026 年人类社区经验（GitHub issues、官方文档、测试博客）多方检索整理，检索日期 2026-10-02。

---

## 0. 结论摘要（TL;DR）

| 决策点 | 结论 |
|---|---|
| 驱动工具 | **FlaUI 5.x（UIA3）** 作为主力；真实鼠标移动用 `Mouse.MoveTo` + 真实点击（SendInput 级），真实键盘用 `Keyboard`（VK/扫描码/Unicode） |
| 中文输入 | WPF TextBox 有 ValuePattern → `Enter("饥荒")` 最稳；**真实键盘路径**用 `VK_RETURN` 真按键 + 剪贴板 `Ctrl+V` 真粘贴（都是真实输入事件，绕开 IME 组合态脆弱性） |
| 测试框架 | xUnit + `Xunit.StaFact`（STA 线程），**进程外启动被测 `SWDM.exe`**（最接近真实用户） |
| 选择器 | 一律 `AutomationProperties.AutomationId` / `x:Name`；禁止显示文本、坐标、层级索引选择器 |
| 等待策略 | `Retry.While` / `Wait.Until` 显式超时；**禁止 `Thread.Sleep`** |
| 组织方式 | Page（Screen）Object 模式，每个窗口一个映射类 |
| 失败证据 | `FlaUI.Core.Capturing.Capture.Element()/Screen()` 截图 + 进程内日志落盘 |
| CI | GitHub Actions 托管 runner 在 Session 0 无交互桌面 → **必须自托管 runner + 自动登录交互会话** |
| 弃用 | WinAppDriver（微软多年未维护）；Appium 生态转向 appium-windows-driver v5（依赖 WinAppDriver）或 NovaWindows（2025 新生，不依赖 WinAppDriver） |
| 视觉校验 | C# 进程内 `Windows.Media.Ocr`（系统自带中文 OCR）+ 像素级参考图对比，作为 UIA 断言的补充 |

---

## 1. 工具对比（含 2025–2026 维护状态）

### 1.1 对比表

| 工具 | 真实鼠标/键盘事件 | 中文支持 | 稳定性 | 维护状态（2025–2026） | 适用场景 |
|---|---|---|---|---|---|
| **FlaUI（UIA3）** | ✅ 鼠标：`Mouse.MoveTo`（SetCursorPos 移动真实光标）+ 点击注入输入事件；键盘：VK / 扫描码 / Unicode 三路 SendInput | ✅ ValuePattern 直设 Unicode；键盘 Unicode 注入可绕 IME | 高（WPF 原生支持 UIA3） | **活跃**：v5.0.0 于 2024-12-08 发布（移除 .NET Core 3.1/5 等旧框架，支持 nullable）；NuGet `FlaUI.Core/UIA3` 5.0.0 | SWDM 2.0 首选 |
| **WinAppDriver + Appium** | ✅ 通过 WebDriver 协议驱动（本质也走 UIA） | 一般（`send_keys` 对 CJK 有已知坑） | 中（常Server 端卡死） | ❌ **微软多年未维护**（官方 npm 警告原文："WinAppDriver server has not been maintained by Microsoft for years"）；迁移指引见 AutomateThePlanet 2025-06-23 迁移指南 | 已有 Appium 栈的团队才考虑 |
| **appium-windows-driver v5+** | ✅（代理到 WinAppDriver） | 同上 | 中 | 活跃，但 v5.0.0 起**仅兼容 Appium 3**，且底层仍是 WinAppDriver | 移动端测试栈统一管理时 |
| **NovaWindows Driver** | ✅ 不依赖 WinAppDriver 的全新实现 | TBD | 新项目，生产案例尚少 | **新生**：2025 年 AppiumConf 展示，已并入 Appium 官方驱动列表（PR #21202）；AutomateThePlanet 2025-05 评测性能优于 WinAppDriver | 观望/备选 |
| **InputSimulator（WindowsInput / InputSimulatorEx）** | ✅ **纯 SendInput 注入**（键盘+鼠标），`SetWindowsHook` 捕获 | ⚠️ 只注入输入事件，**完全不懂 UI 树**——无法找元素、无法读状态、无法断言 | 高（Win32 层极简） | 原仓库（michaelnoonan/inputsimulator）长期低活跃；社区 fork `InputSimulatorEx` 2.1.1 更新 | **作为 FlaUI 的补充**：需要"绝对真实"的裸按键/裸点击时 |
| **MessageBox 的 UIA 弹窗处理** | ✅ FlaUI 直接定位 MessageBox 按钮（见 issue #255） | ✅ | 高 | — | SWDM 弹窗断言路径 |

### 1.2 为什么 FlaUI + UIA3 是 WPF 的最优解

- FlaUI 是 .NET 库，薄包装微软原生 UI Automation（UIA2/UIA3）。WPF 原生暴露 UIA3，兼容性与可靠性最好（KomuraSoft 实践博客：「WPF 用 UIA3、WinForms 用 UIA2」）。[FlaUI/FlaUI](https://github.com/FlaUI/FlaUI) [KomuraSoft](https://comcomponent.com/en/blog/windows-desktop-ui-automation-testing/)
- **真实输入行为**：FlaUI 的输入模拟在 Win32 层走 `SendInput`（键盘支持虚拟键码、扫描码、Unicode 三路；鼠标走真实光标移动+事件注入），被测应用收到的与真人击键/点击同源的输入消息。[DeepWiki-Keyboard](https://deepwiki.com/FlaUI/FlaUI/6.2-keyboard) [DeepWiki-Input Simulation](https://deepwiki.com/FlaUI/FlaUI/6-input-simulation)
- 坑（来自 GitHub issues，必读）：
  - [#323](https://github.com/FlaUI/FlaUI/issues/323)：跨进程真实点击会**夺走本机物理鼠标焦点**——CI 机器不要同时有人用；Qt 等非标准框架可能报 `NoClickablePointException`。
  - [#424](https://github.com/FlaUI/FlaUI/issues/424)：目标控件**不支持 ValuePattern**（如 Win32 控制台）时，`Enter()` 设文本失败——WPF TextBox 一般支持，但混合语言/特殊控件要测一遍。
  - [#440](https://github.com/FlaUI/FlaUI/issues/440)：`Enter()` 报 `Member not found (0x80020003)` 的经典 case——UIA Provider 没实现 Value，回退到键盘路径。
  - [#255](https://github.com/Roemer/FlaUI/issues/255)：MessageBox 按钮定位——MessageBox 本质是 `ControlType.Window`，用 `FindFirstDescendant` 找其内按钮点击即可，**不需要打桩替换 MessageBox**（否则就是"假测试"）。
  - [#168](https://github.com/FlaUI/FlaUI/issues/168)：CI（TeamCity 等）无交互会话时构建挂起——见第 5 节 CI 方案。

### 1.3 为什么不选 WinAppDriver 作主力

- 微软自己已停更（[Microsoft Q&A：Is WinAppDriver dead?](https://learn.microsoft.com/en-us/answers/questions/1455246/is-the-tool-winappdriver-dead-or-not)），Appium 官方 npm 页面给出明确警告并推荐 NovaWindows：[appium-windows-driver](https://www.npmjs.com/package/appium-windows-driver)（"WinAppDriver server has not been maintained by Microsoft for years. Consider trying NovaWindows Driver"）。
- 迁移路线（如果将来要跨语言/跨团队）：[WinAppDriver to Appium Migration Guide](https://www.automatetheplanet.com/winappdriver-to-appium-migration-guide/)（2025-06-23）；NovaWindows 介绍：[Reviving Windows App Automation](https://www.automatetheplanet.com/reviving-windows-app-automation-novawindows-driver-for-appium-2/)。
- SWDM 2.0 是纯 .NET 栈，FlaUI 同语言、无 HTTP 桥（Appium 走 4723 端口 JSON Wire，慢且多一层故障点），断言与测试代码同进程，调试体验更好。

### 1.4 InputSimulator 的定位

InputSimulator 是 Win32 `SendInput` 的薄封装（[michaelnoonan/inputsimulator](https://github.com/michaelnoonan/inputsimulator)、[NuGet WindowsInput](https://www.nuget.org/packages/WindowsInput)、活跃 fork [InputSimulatorEx](https://www.nuget.org/packages/InputSimulatorEx)）。它**只能注入输入、不能查询 UI**——所以不能独立做测试框架，但在两个场景不可替代：

1. **绕过 UIA 点击的边缘 case**：某些控件没有 ClickablePoint（被遮挡、离屏虚拟化）时，用 InputSimulator 对 `element.PointToScreen()` 坐标做裸 `SendInput` 点击，比 UIA 的 `InvokePattern`（那不是真实点击）更真实。
2. **CJK 纯键盘路径**：`KEYEVENTF_UNICODE` 注入 `WM_CHAR`，不经 IME 组合，直接产生中文字符（社区关于 SendInput 非 ASCII 输入的经典讨论：[SO: Simulate input of non-ASCII characters](https://stackoverflow.com/questions/15743053/simulate-input-of-non-ascii-characters)）。

---

## 2. 测试框架：xUnit + WPF 测试宿主

### 2.1 进程外启动（推荐）vs 进程内启动

| 维度 | 进程外（`Application.Launch("SWDM.exe")`） | 进程内（测试进程直接 `new MainWindow().Show()`） |
|---|---|---|
| 真实度 | ✅ 与用户双击 exe 完全一致（独立进程、独立 Dispatcher、真实启动路径） | ❌ 共享测试进程，Dispatcher/资源字典/单实例互斥语义全被改变 |
| 隔离性 | ✅ 崩溃不殃及测试进程 | ❌ 被测崩溃 = 测试宿主崩溃 |
| 输入注入 | ✅ 跨进程 SendInput（真实事件） | ✅ 同样可行 |
| 调试便利 | 稍弱（需附加） | 强 |

**SWDM 2.0 采用进程外**：这是"真实用户输入级"的定义要求——用户点的是 exe，不是测试宿主里的窗口。

### 2.2 STA 线程

xUnit 默认在 MTA 线程跑测试。WPF 与 UIA3 的 COM 交互对 STA 有要求；进程内测试**必须** `[StaFact]`，进程外测试建议同样用 `Xunit.StaFact` 保证 UIA 调用线程语义一致。`Xunit.StaFact` 提供 WPF 专属的 `WpfFact`，带 WPF `SynchronizationContext`。[Xunit.StaFact 文档](http://aarnott.github.io/Xunit.StaFact/docs/getting-started.html)

```xml
<!-- 测试项目 csproj 关键配置 -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="FlaUI.Core" Version="5.0.0" />
    <PackageReference Include="FlaUI.UIA3" Version="5.0.0" />
    <PackageReference Include="xunit" Version="2.*" />
    <PackageReference Include="Xunit.StaFact" Version="1.*" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.*" />
  </ItemGroup>
</Project>
```

### 2.3 被测应用侧必须做的两件事

1. **给每个可交互元素 AutomationId**：WPF 中 `x:Name` 自动成为 AutomationId，或显式 `AutomationProperties.AutomationId="SearchBox"`。这是选择器稳定性的根基（微软官方 [Use the AutomationId Property](https://github.com/dotnet/docs/blob/main/docs/framework/ui-automation/use-the-automationid-property.md)、[Accessibility Best Practices](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/accessibility-best-practices)）。
2. **Debug 构建保留符号**：失败时测试可 attaching/截图对照源码行号。

### 2.4 清理（Fixture 生命周期）

```csharp
public class SwdmAppFixture : IDisposable
{
    public Application App { get; }
    public UIA3Automation Automation { get; } = new();

    public SwdmAppFixture()
    {
        var exe = @"C:\SWDM\SWDM.exe"; // 或 Path.Combine(TestContext.DeployDirectory, ...)
        App = Application.Launch(exe, "--test-mode"); // 关闭自动更新等后台任务
    }

    public void Dispose()
    {
        try { App?.Close(); }         // 优雅关闭
        catch { App?.Kill(); }        // 兜底强杀
        Automation?.Dispose();
        // 兜底：清理任何残留进程，避免下一个测试附着到旧实例
        foreach (var p in Process.GetProcessesByName("SWDM")) { p.Kill(); p.WaitForExit(2000); }
    }
}
```

- xUnit 的 `IClassFixture`/`ICollectionFixture` 控制 App 生命周期；**每个测试方法开新进程**（隔离最强），或每个测试类共享一个进程（速度快 10 倍以上，适合冒烟回归分层）。SWDM 建议：冒烟套件用类级共享，关键流程（下载、搜索）用方法级独立进程。

### 2.5 选择器策略

- **只认 AutomationId**（KomuraSoft 的量化结论：约 80% 的测试鲁棒性来自 AutomationId 命名约定）。禁止：显示文本（本地化即崩）、屏幕坐标、菜单层级索引、ClassName（WPF 通用类名没有区分度）。
- 层级只在"页面级容器 AutomationId"上使用一次，其余一律 `FindFirstDescendant` 深度搜索。社区实践：[Codoid Reqnroll+FlaUI 教程](https://codoid.com/desktop-app-automation-testing/reqnroll-tutorial-flaui-nunit-desktop-automation)、[Medium: Automating WPF with FlaUI](https://medium.com/@sreekanth.parikipandla/automating-wpf-applications-with-flaui-and-reqnroll-in-c-bf6c637f32f2)（要点：AutomationId 优先、WPF 用 UIA3、动态控件加等待、失败截图）。

---

## 3. 人类最佳实践

### 3.1 显式等待（不要 sleep）

`Thread.Sleep(1000)` 是最大的测试不稳定来源：太快=flaky，太慢=浪费时间。FlaUI v2 起移除了内置隐式重试，显式交给开发者用 `Retry` / `Wait`（[FlaUI Wiki: Retry](https://github.com/FlaUI/FlaUI/wiki/Retry)、[DeepWiki: Retry Mechanism](https://deepwiki.com/FlaUI/FlaUI/4.1-retry-mechanism)、SO: [76329611](https://stackoverflow.com/questions/76329611/why-does-flaui-fail-to-find-elements-at-times)、[51026119](https://stackoverflow.com/questions/51026119/wait-for-application-launch-without-using-thread-sleep-using-flaui)）。

```csharp
// 等待列表出现：显式超时 10s，轮询间隔 200ms
var list = Retry.While(
    () => window.FindFirstDescendant(cf => cf.ByAutomationId("ResultList"))?.AsListBox(),
    e => e != null, TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2))
    .Result?.AsListBox();

Assert.NotNull(list);
```

### 3.2 Page（Screen）Object 模式

桌面 UI 的 POM 与 Web 同构：窗口=页面对象，元素=属性，操作=方法，断言留在测试里。FlaUI 官方示例早年就有 WordPad 的 ScreenObjectPattern（[commit](https://github.com/richardsonvix/FlaUI/commit/08e7cb8b844933a540be02747ebc3c075f19a9d5)），微软 Testing 博客也有 [UI Automation POM 设计模式](https://techcommunity.microsoft.com/blog/testingspotblog/ui-automation---page-object-model-and-other-design-patterns/992242)。

```csharp
public class SearchPage
{
    private readonly Window _window;
    public TextBox SearchBox => _window.FindFirstDescendant(cf => cf.ByAutomationId("SearchBox")).AsTextBox();
    public Button SearchButton => _window.FindFirstDescendant(cf => cf.ByAutomationId("SearchButton")).AsButton();
    public ListBox ResultList => _window.FindFirstDescendant(cf => cf.ByAutomationId("ResultList")).AsListBox();

    public SearchPage(Window window) => _window = window;

    public void Search(string keyword)
    {
        SearchBox.Focus();
        SearchBox.Enter(keyword);      // 设置文本（ValuePattern）
        SearchButton.Invoke();         // UIA Invoke（若要"真物理点击"见 3.5)
    }
}
```

### 3.3 稳定性技巧清单

1. **唯一实例互斥**：启动前杀残留进程；测试串行执行（`[Collection]` + `DisableTestParallelization`）。
2. **窗口前置**：`window.Focus()` / `window.SetForeground()` 后再输入，避免输入注入到别的窗口。
3. **输入前 Focus**：TextBox 先 `.Focus()` 再 `Enter/Type`。
4. **弹窗即查即关**：操作后先 `Retry` 找 MessageBox/ContentDialog，点掉再断言主流程（issue #255 的做法）。
5. **失败截图必落盘**：`FlaUI.Core.Capturing`（[源码](https://github.com/FlaUI/FlaUI/blob/main/src/FlaUI.Core/Capturing/Capture.cs)）：`Capture.Screen()` / `Capture.Element(element)`。KomuraSoft 与 Joe Kunk 都强调"无人值守失败时，日志只写 element not found 等于什么没说"（[KomuraSoft §7.3](https://comcomponent.com/en/blog/windows-desktop-ui-automation-testing/)、Joe Kunc 的 FlaUI 演讲：每个失败测试都留一张当时屏幕截图）。
6. **CI 与本地同分辨率**：窗口位置/大小显式设置，避免 DPI/分辨率差异导致 ClickablePoint 偏移。

### 3.4 CI 集成（关键坑）

托管 runner（GitHub Actions `windows-latest`、Azure DevOps 托管 agent、TeamCity 默认 agent）以**服务身份运行在 Session 0**，没有交互桌面——UIA 拿不到窗口、SendInput 注入无处落地。FlaUI issue [#168](https://github.com/FlaUI/FlaUI/issues/168) 就是 TeamCity 下构建挂起的真实记录。方案：

- **自托管 runner + 自动登录**：runner 机器开机自动登录到交互会话（注册表 `AutoAdminLogon` 或 Windows Task Scheduler 登录任务），runner 进程在该会话内运行 `dotnet test`。
- **屏幕锁屏策略**：锁屏时 `SetCursorPos` 与部分 UIA 调用仍工作，但截图校验会黑屏——测试期间保持不锁屏（`SetThreadExecutionState`）。
- **失败产物归档**：`dotnet test` 后 `copy screenshots artifacts`，GitHub Actions 用 `actions/upload-artifact`。

### 3.5 "真实物理点击"什么时候必要

UIA 的 `Invoke()` 是语义级触发，**不是物理点击**——它测不到"按钮被遮挡时点不到""命中区域偏移"这类用户侧 bug。需要真实物理路径时：

```csharp
// 真实物理点击：把光标移过去，注入真实鼠标按下/抬起
var clickable = element.ClickablePoint;   // 屏幕坐标
Mouse.MoveTo(clickable);                  // SetCursorPos 移动真实光标
Mouse.LeftClick.MouseDown();
Mouse.LeftClick.MouseUp();                // 或 Mouse.Click(MouseButtonType.Left);
```

注意 FlaUI 的 `Mouse.Click` 默认就是真光标+真事件路径（[#323](https://github.com/FlaUI/FlaUI/issues/323) 中用户报告"它接管了我的物理鼠标"即为证）；跨进程输入失败诊断可参考社区整理的 [flaui-cross-process-input 技能文档](https://skills.rest/skill/flaui-cross-process-input-parksanghoon-sys)（其中指出 `Mouse.MoveTo` 走 SetCursorPos、不注入 WM_MOUSEMOVE 的细节，解释了"为什么移动后某些 hover 高亮不触发"以及要补真事件）。

---

## 4. 对比"假测试"：为什么真实 UI 点击比 ViewModel 单元测试更能抓用户侧 bug

### 4.1 问题的本质：测试保真度（fidelity）

Google 测试博客 2024 年专文 [Increase Test Fidelity By Avoiding Mocks](https://testing.googleblog.com/2024/02/increase-test-fidelity-by-avoiding-mocks.html)：**保真度 = 测试行为与真实行为的相似程度**；mock 让测试好写、跑得快，但"更容易漏掉 bug"。ViewModel 单元测试正是典型低保真场景：

- 它假设绑定永远正确（`{Binding SearchText}` 拼错、`Mode=TwoWay` 漏写、`UpdateSourceTrigger` 不对——单测全绿，用户输入进不去）。
- 它假设命令真的接上了按钮（`Button.Command` 绑定断开、`IsEnabled` 状态机错——单测看不见）。
- 它假设 Dispatcher/线程规矩（跨线程访问 UI、async void 异常吞掉——只在真实Dispatcher 上才炸）。
- 它假设控件模板/样式没盖住按钮（遮挡、命中区域、虚拟化掉出可视区）。

### 4.2 社区实证

- [When mocks lie](https://romaincoupey.com/posts/when-mocks-lie-integration-test-gap/)：真实事故——**双方各自的单测都通过**，集成时一方 raise 异常 / 另一方期待返回值，gate 才炸。单测给了"两侧契约一致"的假象。
- [The wrong test](https://blog.vnykmshr.com/writing/the-wrong-test/)：CI 全绿 → 部署后直接掉生产：所有能抓住它的测试都对着一个季度没更新的 mock schema。
- [Unit Tests Are Not True Anymore](https://unixy.io/blog/unit-tests-are-not-true-anymore/)、[Your Tests Are Lying to You](https://site.aaronhsyong.com/posts/your-tests-are-lying-to-you/)：同一主题的社区独立复述。
- Martin Fowler [Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html) / [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) 的平衡观点：E2E/UI 测试贵、慢、脆，**但只有它覆盖"用户真实旅程"**；ThoughtWorks [测试结构指南](https://www.thoughtworks.com/en-us/insights/blog/guidelines-structuring-automated-tests)明确指出：验收级 E2E 覆盖"单测无法覆盖的关键用户旅程与失败场景"。

### 4.3 给 SWDM 2.0 的分层结论

| 层 | 工具 | 覆盖什么 |
|---|---|---|
| 单元 | xUnit | 纯逻辑（别名归一化、字符串匹配、数据结构） |
| 集成 | xUnit + 真实子系统 | steamcmd 调用、缓存、HTTP 指纹策略 |
| **UI（本方案）** | **xUnit + FlaUI UIA3 + 真实输入** | 绑定、命令、焦点、弹窗、布局遮挡、中文输入、用户旅程 |

用户明确反对"假测试"（打桩 `QMessageBox`、直调 ViewModel 那类）——记忆中 SWDM 1.4.x 时期踩过同样的坑：**桩函数不是真实阻塞，断言时序被桩改变，测出的是桩的行为**。WPF 2.0 的 UIA 弹窗点击（issue #255 路线）从根本上避免这个问题：MessageBox 该弹还弹，测试像用户一样去点"确定"。

---

## 5. 本机限制与替代：视觉校验

### 5.1 为什么要视觉校验

UIA 能读文本/状态，但读不到**像素**：文字溢出裁切、布局挤压重叠、主题色错误、列表空态图标错位——这类 bug 只看 UI 树全部"正确"。

### 5.2 OCR 方案（推荐：Windows.Media.Ocr，零依赖）

Windows 内置 OCR 引擎，net8.0-windows 可直接调用，**支持中文**（需系统已装中文 OCR 语言包——中文 Windows 默认有）：

```csharp
// 截取目标控件 → OCR → 断言文本（作为 UIA 文本断言的交叉验证）
using System.Windows.Media.Imaging;
using Windows.Media.Ocr;

var bmp = Capture.Element(element);               // FlaUI 截图
using var ms = new MemoryStream(bmp.BitmapData);  // 转 SoftwareBitmap
var softwareBmp = await SoftwareBitmap.CreateAsyncFromStream(
    ms.AsRandomAccessStream(), BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied);
var engine = OcrEngine.TryCreateFromLanguage(new Windows.Globalization.Language("zh-CN"));
var result = await engine.RecognizeAsync(softwareBmp);
Assert.Contains("饥荒", result.Text);
```

参考：[Windows.Media.Ocr 官方示例](https://learn.microsoft.com/en-us/samples/microsoft/windows-universal-samples/ocr/)、[OcrEngine.RecognizeAsync 文档](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.recognizeasync)。更新的 Windows App SDK 文本识别 API：[Windows AI text recognition](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)。C# 备选：Tesseract（Apache 2.0，中文包需另下）。

### 5.3 像素对比方案（几何/视觉断言）

- 基线截图 + 像素 diff（`System.Drawing.Bitmap` 逐像素、或 `ImageHash`/ImageSharp 感知哈希），阈值容忍抗锯齿差异。
- **只对静态区域用**（图标、空态图、固定布局块）；动态列表区域用感知哈希 + 容差。
- 配合本机既有经验：SWDM 1.x 时期因 Python 侧读图工具不可用，视觉断言只能用几何量化（`mapTo` 相对坐标）兜底；**WPF 2.0 在 C# 进程内做 OCR/像素对比，不再依赖外部读图工具**，这是 WPF 路线相对 1.x 的实质收益之一。

### 5.4 视觉校验的定位

视觉断言是**补充**不是替代：UIA 断言优先（快、准、可读），视觉断言用于 UIA 读不到的像素级表现。两者组合在同一测试方法内：先 UIA 断行为，再截图断表现。

---

## 6. 最小可运行示例

场景：启动 SWDM 2.0，在搜索框输入中文"饥荒"，点搜索按钮，断言结果列表出现。

### 6.1 被测 XAML（片段，元素必须有 AutomationId）

```xml
<Window x:Class="SWDM.MainWindow"
        x:Name="MainWindow"                       <!-- → AutomationId="MainWindow" -->
        xmlns:ap="clr-namespace:System.Windows.Automation;assembly=PresentationFramework">
    <StackPanel>
        <TextBox ap:AutomationProperties.AutomationId="SearchBox" Width="300"/>
        <Button ap:AutomationProperties.AutomationId="SearchButton" Content="搜索"/>
        <ListBox ap:AutomationProperties.AutomationId="ResultList" Height="300"/>
    </StackPanel>
</Window>
```

### 6.2 测试代码（xUnit + FlaUI + 显式等待 + 失败截图）

```csharp
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Capturing;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;
using Xunit;
using Xunit.StaFact;

public sealed class SearchFeatureTests : IDisposable
{
    private readonly Application _app;
    private readonly UIA3Automation _automation = new();
    private readonly Window _window;

    public SearchFeatureTests()
    {
        _app = Application.Launch(@"C:\SWDM\SWDM.exe", "--test-mode");
        _window = Retry.While(
            () => _automation.GetDesktop()
                            .FindFirstDescendant(cf => cf.ByAutomationId("MainWindow"))
                            ?.AsWindow(),
            el => el != null,
            TimeSpan.FromSeconds(15),       // 启动等待：显式超时，绝不 Sleep
            TimeSpan.FromSeconds(0.2)).Result.AsWindow();
        Assert.NotNull(_window);
    }

    [WpfFact]
    public void Search_饥荒_ShowsResultsInList()
    {
        var box  = _window.FindFirstDescendant(cf => cf.ByAutomationId("SearchBox")).AsTextBox();
        var btn  = _window.FindFirstDescendant(cf => cf.ByAutomationId("SearchButton")).AsButton();
        Assert.NotNull(box); Assert.NotNull(btn);

        // —— 输入"饥荒" ——
        box.Focus();
        // 路径 A（推荐主路径）：ValuePattern 直设 Unicode，WPF TextBox 原生支持
        box.Enter("饥荒");
        Assert.Equal("饥荒", box.Text);   // 确认值真进了控件

        // —— 真实点击（物理鼠标事件路径，非 Invoke 语义级调用）——
        Mouse.MoveTo(btn.ClickablePoint);
        Mouse.Click(MouseButtonType.Left);

        // —— 显式等待列表（异步搜索结果回来）——
        var list = Retry.While(
            () => _window.FindFirstDescendant(cf => cf.ByAutomationId("ResultList"))?.AsListBox(),
            el => el is { Items.Count: > 0 },
            TimeSpan.FromSeconds(20),
            TimeSpan.FromSeconds(0.2)).Result?.AsListBox();

        Assert.NotNull(list);
        Assert.NotEmpty(list!.Items);
        Assert.Contains(list.Items, i => (i.Name ?? string.Empty).Contains("饥荒"));
    }

    public void Dispose()
    {
        // 失败现场：截图保留（Dispose 在 Assert 失败抛异常后仍会被 xUnit 调用）
        try
        {
            var shot = Capture.Screen();
            shot.ToFile($@"C:\SWDM\TestArtifacts\fail_{DateTime.Now:yyyyMMdd_HHmmss}.png");
        }
        catch { /* 截图失败不影响清理 */ }

        try { _window?.Close(); } catch { }
        try { _app?.Close();    } catch { _app?.Kill(); }
        _automation.Dispose();
    }
}
```

> 截图更精确的位置是包一层 `try/catch` 在测试方法体内、在 `Assert` 失败瞬间捕获**当时**的屏幕（`Capture.Screen()` 或 `Capture.Element(list)`），见 [FlaUI.Core.Capturing](https://github.com/FlaUI/FlaUI/blob/main/src/FlaUI.Core/Capturing/Capture.cs) 与 Medium 实践（`Window.Capture()` 失败即写日志目录）。

### 6.3 中文输入的三条路径与取舍

| 路径 | 是否真实输入事件 | 稳定性 | 说明 |
|---|---|---|---|
| `Enter("饥荒")`（ValuePattern） | ⚠️ 语义级设值（非击键） | ⭐⭐⭐ 最高 | WPF TextBox 原生支持；控件无 ValuePattern 时报错（issue #424/#440） |
| Unicode 键盘注入 `Keyboard.TypeText` | ✅ `KEYEVENTF_UNICODE` → `WM_CHAR`，不经 IME | ⭐⭐ | 真实输入消息流；社区对 SendInput 非 ASCII 的经典结论：VK 无法表示 CJK，Unicode 注入可行（[SO 15743053](https://stackoverflow.com/questions/15743053/simulate-input-of-non-ascii-characters)） |
| 剪贴板 + 真实 Ctrl+V | ✅ 真实击键（VK_CONTROL+VK_V）+ 剪贴板内容 | ⭐⭐⭐ | 兼顾"真实键盘事件"与中文可靠性：`box.Focus(); SetClipboardText("饥荒"); Keyboard.Type(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);` |

**完全模拟 IME 拼音过程（键 pinyin → 候选 → 选词）不要做**：依赖系统 IME 状态、候选框窗体、焦点时序，脆弱到不值得——微软自己的 Q&A 里 IME 状态被 Windows 更新打乱就是常态。测试策略：**"饥荒"这几个字怎么进 TextBox 可以用稳定路径，但"按键触发搜索"这一步必须是真实键盘事件**（如真实回车 `Keyboard.Type(VirtualKeyShort.RETURN)` 而非命令直调）。

### 6.4 MessageBox 断言（不打桩）

```csharp
// 搜索无结果时 SWDM 弹 MessageBox 提示 → 像用户一样点掉它
var dialog = Retry.While(
    () => _window.ModalWindows.FirstOrDefault(w => w.Name == "提示"),
    el => el != null, TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(0.2)).Result;
Assert.NotNull(dialog);

var okBtn = dialog.FindFirstDescendant(cf => cf.ByName("确定") ?? cf.ByAutomationId("OkButton"));
Assert.NotNull(okBtn);
okBtn.AsButton().Invoke();   // 或 Mouse.Click 物理路径
```

依据：[FlaUI #255](https://github.com/Roemer/FlaUI/issues/255)——MessageBox 是 `ControlType.Window`，子按钮可正常定位点击，**无需替换 MessageBox 实现**。

---

## 7. 落地路线建议（SWDM 2.0）

1. **契约前置**：定 UI 自动化 ID 命名规范（`<视图>_<控件>_<语义>`），写进 XAML 模板/lint，从第一个窗口就执行（KomuraSoft：命名约定 ≈ 80% 鲁棒性）。
2. **冒烟套件先行**：启动→搜索→下载→库管理 5 条主旅程，每个迭代全量回归（对齐用户迭代交付纪律）。
3. **自托管 CI runner**：开机自动登录交互会话，定时拉取跑全套，失败截图归档。
4. **分层纪律**：UI 测真实用户旅程与交互接缝；单测只测纯逻辑；绝不在此层重复断言纯逻辑（避免掉进"低价值高成本"的倒金字塔）。

---

## 8. 引用清单

**工具与库**
- [FlaUI/FlaUI（GitHub）](https://github.com/FlaUI/FlaUI) · [v5.0.0 Release](https://github.com/FlaUI/FlaUI/releases/tag/v5.0.0) · [CHANGELOG](https://github.com/FlaUI/FlaUI/blob/main/CHANGELOG.md)
- [FlaUI Wiki: Retry](https://github.com/FlaUI/FlaUI/wiki/Retry) · [DeepWiki: Retry Mechanism](https://deepwiki.com/FlaUI/FlaUI/4.1-retry-mechanism) · [DeepWiki: Keyboard](https://deepwiki.com/FlaUI/FlaUI/6.2-keyboard) · [DeepWiki: Input Simulation](https://deepwiki.com/FlaUI/FlaUI/6-input-simulation)
- [FlaUI.Core/Capturing/Capture.cs](https://github.com/FlaUI/FlaUI/blob/main/src/FlaUI.Core/Capturing/Capture.cs)
- [Xunit.StaFact 文档](http://aarnott.github.io/Xunit.StaFact/docs/getting-started.html)
- [michaelnoonan/inputsimulator](https://github.com/michaelnoonan/inputsimulator) · [NuGet WindowsInput](https://www.nuget.org/packages/WindowsInput) · [InputSimulatorEx](https://www.nuget.org/packages/InputSimulatorEx)
- [appium-windows-driver（npm 警告 WinAppDriver 未维护）](https://www.npmjs.com/package/appium-windows-driver) · [GitHub](https://github.com/appium/appium-windows-driver)
- [Microsoft Q&A: Is WinAppDriver dead?](https://learn.microsoft.com/en-us/answers/questions/1455246/is-the-tool-winappdriver-dead-or-not)
- [WinAppDriver to Appium Migration Guide（AutomateThePlanet, 2025-06）](https://www.automatetheplanet.com/winappdriver-to-appium-migration-guide/)
- [NovaWindows Driver for Appium 2（AutomateThePlanet, 2025-05）](https://www.automatetheplanet.com/reviving-windows-app-automation-novawindows-driver-for-appium-2/) · [npm](https://www.npmjs.com/package/appium-novawindows-driver) · [Appium PR #21202](https://github.com/appium/appium/pull/21202)

**GitHub Issues（坑）**
- [FlaUI #323 真实鼠标/键盘 / NoClickablePointException](https://github.com/FlaUI/FlaUI/issues/323)
- [FlaUI #424 混合语言文本设置](https://github.com/FlaUI/FlaUI/issues/424) · [FlaUI #440 Member not found](https://github.com/FlaUI/FlaUI/issues/440)
- [FlaUI #255 MessageBox 按钮](https://github.com/Roemer/FlaUI/issues/255)
- [FlaUI #168 CI 上运行挂起](https://github.com/FlaUI/FlaUI/issues/168)
- [flaui-cross-process-input 跨进程输入诊断（skills.rest）](https://skills.rest/skill/flaui-cross-process-input-parksanghoon-sys)

**实践与模式**
- [KomuraSoft: UI Automated Testing for Desktop Apps — FlaUI in Practice](https://comcomponent.com/en/blog/windows-desktop-ui-automation-testing/)
- [Codoid: Reqnroll + FlaUI + NUnit 桌面自动化（POM）](https://codoid.com/desktop-app-automation-testing/reqnroll-tutorial-flaui-nunit-desktop-automation)
- [Medium: Automating WPF Applications with FlaUI and Reqnroll](https://medium.com/@sreekanth.parikipandla/automating-wpf-applications-with-flaui-and-reqnroll-in-c-bf6c637f32f2)
- [FlaUI ScreenObjectPattern 示例（WordPad）](https://github.com/richardsonvix/FlaUI/commit/08e7cb8b844933a540be02747ebc3c075f19a9d5)
- [Microsoft: UI Automation — Page Object Model and other Design Patterns](https://techcommunity.microsoft.com/blog/testingspotblog/ui-automation---page-object-model-and-other-design-patterns/992242)
- [Microsoft: Use the AutomationId Property](https://github.com/dotnet/docs/blob/main/docs/framework/ui-automation/use-the-automationid-property.md) · [Accessibility Best Practices](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/accessibility-best-practices)
- [SO: Why does FlaUI fail to find elements at times? 76329611](https://stackoverflow.com/questions/76329611/why-does-flaui-fail-to-find-elements-at-times) · [SO: 51026119 启动等待](https://stackoverflow.com/questions/51026119/wait-for-application-launch-without-using-thread-sleep-using-flaui)
- [SO: Simulate input of non-ASCII characters (CJK SendInput)](https://stackoverflow.com/questions/15743053/simulate-input-of-non-ascii-characters)

**测试哲学（"假测试"讨论）**
- [Google Testing Blog: Increase Test Fidelity By Avoiding Mocks (2024-02)](https://testing.googleblog.com/2024/02/increase-test-fidelity-by-avoiding-mocks.html)
- [When mocks lie（集成测试缺口实证）](https://romaincoupey.com/posts/when-mocks-lie-integration-test-gap/)
- [The wrong test（全绿 CI 掉生产）](https://blog.vnykmshr.com/writing/the-wrong-test/)
- [Unit Tests Are Not True Anymore](https://unixy.io/blog/unit-tests-are-not-true-anymore/) · [Your Tests Are Lying to You](https://site.aaronhsyong.com/posts/your-tests-are-lying-to-you/)
- [Martin Fowler: Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html) · [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
- [ThoughtWorks: Guidelines for Structuring Automated Tests](https://www.thoughtworks.com/en-us/insights/blog/guidelines-structuring-automated-tests)

**视觉校验**
- [Windows.Media.Ocr 官方示例](https://learn.microsoft.com/en-us/samples/microsoft/windows-universal-samples/ocr/) · [OcrEngine.RecognizeAsync 文档](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.recognizeasync)
- [Get started with text recognition (OCR) in the Windows App SDK](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)
