# SWDM 2.0 基座实证 Spike 报告（t4）

> 时间：2026-10-02 15:41 · 负责：arch-20 · 依据：pcl2_xaml_patterns §6.3 建议的实证门（经验复验纪律）
> 状态：**✅ 5/5 冒烟全绿**（`spike_result.md` 15:41:28）
> 产物：`swdm2/spike/SpikeWpf/`（被测试装页：WPF-UI 4.3.0 + 自绘 Card）+ `swdm2/spike/SpikeFlaUiTests/`（FlaUI 5.0.0 真实输入冒烟 + 反射控制台驱动）+ `swdm2/docs/architecture_2.0.md` 附录 SP（契约补丁）
> 性质：技术验证 spike（"骨架/环境准备不算开发"，不违反计划先行纪律）；spike 代码不进产品路径。

---

## 0. 验证命令与结果

```bash
dotnet build swdm2/spike/SpikeWpf/SpikeWpf.csproj -c Debug      # 0 警告 0 错误（WPF-UI 4.3.0）
dotnet run --project swdm2/spike/SpikeFlaUiTests/SpikeFlaUiTests.csproj -c Debug
# → exit 0；spike_result.md：共 5 项：5 通过 / 0 失败
```

冒烟明细（进程外启动 + 真实鼠标/键盘注入，无打桩）：

| # | 用例 | 结果 | 覆盖 |
|---|---|---|---|
| 1 | 启动被测 exe + 定位主窗口（AutomationId=MainWindow） | ✅ | WPF-UI 初始化/主题 |
| 2 | AutomationId 清单可达性（TitleBar 部件/Box/Button/List/两种 Card） | ✅ | Q2 可达性 |
| 3 | 搜索_饥荒：ValuePattern 中文输入 + 真实物理点击 → 列表出现结果 | ✅ | Q2 输入链路 |
| 4 | 真实回车键触发搜索（VK_RETURN 注入，非命令直调） | ✅ | Q2 键盘事件 |
| 5 | MessageBox 弹窗：真实点击自绘卡片按钮 → 模态窗 → 真实点确定关闭（#255 路径，无打桩） | ✅ | Q2 弹窗路径 |
| 6 | 截图链路：Capture.Element + MainScreen → PNG 落盘非空 + read_image 转写 | ✅ | Q3 |

---

## 1. Q1 — WPF-UI 4.3.0 在 net8.0-windows 可用性

**✅ 可用（包还原/初始化/主题全链路通）**，有两处 API 表面弯路被 spike 抓实：

- **还原**：nuget.org 直连 200（2.1s，亦走 7897 代理 0.9s）；`WPF-UI 4.3.0` restore 成功（冷启 42.8s）；lib/net8.0-windows7.0；XAML 命名空间 `http://schemas.lepo.co/wpfui/2022/xaml`（DLL 二进制扫描确认）。
- **初始化/主题**：`ui:ThemesDictionary(Light)` + `ui:ControlsDictionary` + 自建 `swdm-` 前键字典三者 MergedDictionaries 共存加载成功；FluentWindow + TitleBar + Mica + 无边框 ExtendsContentIntoTitleBar 正常渲染。
- **弯路 ①（启动级崩溃）**：`SymbolRegular` 枚举**无 Regular 后缀**——`"Apps24Regular"` 为非法值 → `XamlParseException → FormatException`，主窗口永不出现（早 15:29 那轮 "20s 未出现" 的真因）。正名 `Apps24`（本机反射 `typeof(Symbol regular).GetEnumNames()` dump 出 9235 名中含 Apps24；captain 同步核验 main 分支源码）。⇒ pcl2 §8"WPF-UI API 表面未逐版核验"弯路嫌疑实证成立。
- **弯路 ②（属性漂移）**：`ui:Card` **无 `Header` 属性**（pcl2 §6.1 表假定存在；4.3.0 实际仅 `Footer`/`HasFooter`）。

**落账**：architecture_2.0.md 附录 SP-1 + 契约 **A8b**（所有 WPF-UI API/图标名首次使用前反射实测）。

## 2. Q2 — FlaUI 5.0.0 对 WPF-UI 控件的 UIA3 可达性

**✅ 高（8/9 期望命中 + 1 处结构性例外）**，UIA 树 dump 证据（`TestArtifacts/spike_tree.txt`）：

| 元素 | 可达性 | 备注 |
|---|---|---|
| Window（AutomationId=MainWindow） | ✅ | 窗口级 id 完全暴露 |
| ui:Button / ui:TextBox(Edit) / ui:ListView(List) | ✅ | id+Name+ControlType 全 |
| 自绘 UserControl（SwdmCard） | ✅ type=Custom | id 完全暴露，内容控件可达 |
| 自绘卡片内 Button | ⚠️ | **无 ClickablePoint** → 退到包围矩形中心点击（wpf_ui_testing §1.4 教训实证） |
| **ui:TitleBar / ui:Card / Grid / ContentControl** | ❌ | **UIA 树提升（hoisting）**：容器不在树中，内容直接挂窗口下，XAML 设的 AutomationId 被"吞" |

输入路径实测：

- `Enter("饥荒")` ValuePattern CJK **完美**（断言值真进控件）✅
- `Enter()` 对含**空格/撇号的 ASCII 会被吞**（实测 `"Don't Starve"` → `"Don'tStarve"`）⇒ 含空格/标点走剪贴板 Ctrl+V 路径
- 真实回车 `Press/Release(VK_RETURN)` 触发 TextBox PreviewKeyDown（真实键盘事件生效），但需**先物理点击**获得焦点（程序化 Focus/SetForeground 不可靠——Windows 前台锁定）

**落账**：契约 **A7 修正**——AutomationId 只设在可靠载体（Window / 内容控件 / UserControl / WPF-UI 模板部件固定 id 如 `TitleBarCloseButton`），禁止压在 TitleBar/Card/Grid/ContentControl 等提升型容器上；测试顺序契约"先点击 → 再注入按键"。

## 3. Q3 — 截图 + read_image 读图链路

**✅ 完全可用**：

- `Capture.Element(list)` 138.7KB / `Capture.MainScreen()` 1443KB PNG 落盘成功。
- `read_image`（modlens 桥）**完整转写中文 UI**：搜索框 CaveStory、列表项时间戳、WPF-UI Card 文案、自绘卡片描述、弹窗正文与"确定"按钮全部 OCR 可读。
- ⇒ 记忆中"读图工具本机全不可用"**被推翻**（标 superseded）：基线决策 5 的视觉仲裁链（UIA 断言 → 截图 → OCR/像素 diff）对 WPF 进程成立。

**xUnit 运行器基础设施发现（重要，输入 t3 执行方案）**：本机 harness 沙箱内 `dotnet test` 的 testhost **启动即崩**（`SetParentProcessExitCallback` → `Win32Exception(5)` 拒绝跨进程句柄；Test SDK 17.8/17.13、x86/x64 同崩）。spike 期间改用**控制台驱动反射执行同一批 [WpfFact] 方法**（`dotnet run`，真实输入链路完全一致；UseWPF=true 的 Exe 为 Windows 子系统无控制台 → 输出落盘 `spike_result.md`）。产品回归仍在普通交互桌面用 `dotnet test`（t3 契约不变；基线决策 6：本机交互会话/自托管 runner）。

## 4. Q4 — 裁决：**混合策略**（WPF-UI 基座 + 签名级自绘）

与 t1 §3.4 裁决一致，spike 提供实测双重加固：

1. **窗口 chrome / 基础控件 = WPF-UI 4.3.0**（FluentWindow/TitleBar/Button/TextBox/ListView 实测可用且 UIA 友好）。
2. **签名级观感 = 自绘 UserControl**（SwdmCard/Hint/ListItem）：PCL2 三层结构 + 90ms 阴影 0.07→0.4 悬停动画实测渲染且 **UIA 天然暴露 id（Custom）**——**比 WPF-UI Card 更可测**（Card 不可达 + 无 Header）。
3. **裁决依据增量**：WPF-UI 结构性控件（TitleBar/Card）在 API 与 UIA 两层都有版本漂移/提升现象 ⇒ 自绘不只为了"脸"，也为了测试纪律。
4. 与基线决策 9 + pcl2 §6 结论（模块 1/2/3/5 免写，4/6/7/8/9/10 自绘）完全对齐。

## 5. 对既定计划的具体修正（已写入 architecture_2.0.md 附录 SP）

- **A7 修正**：AutomationId 可靠载体表 + "先点击后注入按键"顺序契约（SP-2）。
- **A8 追加 A8b**：WPF-UI API 名（图标/枚举优先）首次使用前反射实测（SP-1）。
- **t3 输入规则补丁**：CJK→Enter；含空格/标点 ASCII→Ctrl+V 或纯字母词（SP-2）。
- **FlaUI 5.0.0 全量落实**：architecture_2.0.md 的 FlaUI 6.0.0 引用已全部改 5.0.0（captain NuGet 权威复验 + 本机 restore 实证：6.0.0 不存在于 NuGet）。
- **阶段 0 压缩**：D0.1/D0.3 的验证内容已由本 spike 完成；t5 DAG 定稿时阶段 0 压缩为接线任务（D0.2 补 Downloads→Steam 引用 + 产品 UiTests 引 FlaUI 5.0.0）。

## 6. 证据索引

- `swdm2/spike/SpikeFlaUiTests/bin/Debug/net8.0-windows/spike_result.md` — 冒烟 5/5 日志
- `…/TestArtifacts/spike_tree.txt` — UIA 树 dump（TitleBar/Card 提升证据）
- `…/TestArtifacts/spike_return_diag.txt` — 回车注入重试诊断
- `…/TestArtifacts/spike_screen_full.png` — 全屏截图（read_image 转写成功）
- 产品计划回写：`swdm2/docs/architecture_2.0.md` 附录 SP（SP-1…SP-5）

**结论**：基座实证门通过。WPF-UI 4.3.0 底座 + 自绘签名层 + FlaUI 5.0.0 真实输入测试三条链路全部实证可用，契约修正已回写计划，不阻塞 t5 终裁。
