# SWDM 2.0 阶段 1 交付门评审记录（review_2.0_0.1.0）

> 时间：2026-10-02（17:52–18:10） · 主持/执行：visual-20（t13=D1.7 门执行人，captain 指派） · 评审对象：阶段 1 交付 = `swdm2/` v0.1.0（D0.2→D1.6 + D1.5r + 门基础设施）
> 三原则：**精简 / 以用户体感为中心 / 保证基本功能正常运行**
> 依据材料：`swdm2/docs/architecture_2.0.md` §6 DAG v2.3、`swdm2/CHANGELOG.md`（0.1.0）、t6-t14 交付记录、captain 复跑确认函（17:52）
> 门禁状态：四要素全绿 → visual-20 交付门工作完成，**captain 复跑确认后关门**（D1.7 验收条款）

---

## 一、四要素证据

### 1. 全量回归（含新增与功能间关联交互）✅

| 命令 | 结果 |
|---|---|
| `cd swdm2; dotnet build Swdm2.sln -c Debug --nologo -v q` | **0 警告 0 错误** |
| `dotnet run --project tests/CoreTestsDriver` | **pass=72 fail=0 skip=0**（63 [Fact] + 9 [Theory] 行；真数由 captain 17:48 计数口径确立，关闭了"63/63 假绿"） |
| `dotnet run --project tests/UiTestsDriver` | **pass=5 fail=0 skip=0**（4 脱敏管道 + 1 AppLaunch 真实进程冒烟：Application.Launch → UIA3 定位 AutomationId=MainWindow） |
| 环境要点 | SP-3 沙箱驱动模式（testhost `SetParentProcessExitCallback` Win32Exception(5) 崩溃的替代路径）；`%TEMP%`+`%TMP%` 双重重定向 `swdm2/.dtmp` |
| 关联交互回归 | D1.4↔D1.5（凭据明文不入落盘日志）、D1.2↔D1.3（双路径模式 × 选项热更新组合）、D1.6（C5 缓存双向隔离：消费侧+生产侧变异均不污染）、D1.1（C6 类型编译期+反射隔离） |

**假绿闭环**：历史"63/63 全绿"为自写驱动按特性 Type.Name 精确匹配筛方法所致（TheoryAttribute 派生自 FactAttribute 但 Name 不同 → 9 个 [Theory] 行静默跳过，从未执行）；T14 修复 + captain 独立复跑计数对账（69/3→72/0）+ 计数诚实化（72，非凑数 74）构成完整闭环（教训入过程纪律：自写测试驱动必须 IsAssignableFrom 匹配 + Theory/InlineData 展开 + 第二人独立复跑计数对账；本门新建 `UiTestsDriver` 已内化该教训）。

### 2. 讨论组评审（三原则） ✅（本记录=评审载体；四方投票见 §三，arch-20/qa-20 异步回复追加）

**精简**：阶段 1 六任务 + 两基础设施（驱动器/版本 props）无冗余判定——
- 脱敏"双层防线"（策略层 + 渲染器层）在 D1.5r 真回归中实证了必要性（两暗 bug 恰被兜底层抓出），不删；
- 缓存"双向深拷贝"超越 1.x 单侧设计，但生产侧污染路径已实测断言化（1.x enrich() 学费），不降级；
- CoreTestsDriver/UiTestsDriver 双驱动为沙箱 dotnet test 崩溃的必要替代（SP-3 契约），产品回归仍走普通桌面 dotnet test，非双轨重复投入；
- **删减项：无；新增请求：无**。阶段 1 为纯基础设施层，不扩功能面（符合"精简"）。

**以用户体感为中心**：0.1.0 不面向最终用户（无 Velopack 打包/安装器，首版对外交付=2.0.0）。用户侧可感知承诺已由断言锁定：启动不崩溃（AppLaunch 冒烟）、凭据明文不落盘/不进日志/不进异常（D1.4+D1.5 C2 契约断言）、配置热生效。**即时反馈 A9 阈值、视觉数值等参数类全部 ⚠️[参数待重标定]，按经验复验纪律在真实 UI 出现后（D5.10）于真实旅程计时标定，不在基础设施期拍脑袋。**

**保证基本功能正常运行**：77/0 全绿 + build 0-0；领域语言（C6 强类型 id）+ 结果模型 + 路径/配置/凭据/日志/缓存五件基础设施全部上线并互相断言联动；阶段 2（Steam 域）依赖的 Core 契约（Result<T,TErr>、IPathService、IOptionsMonitor、ICredentialStore、IAsyncCache）已全部就绪，无下游阻塞项。

### 3. 版本号 ✅

- `swdm2/Directory.Build.props`：Version=0.1.0（全项目统一；单一事实源，后续阶段升级只改一处）
- 产物验证：`Swdm2.Core.dll` Assembly=`0.1.0.0`、ProductVersion=`0.1.0+25086c0…`（SourceRevisionId 指向当前提交）
- 阶段版本映射入 DAG（0.1.0→0.2.0→…→2.0.0）写定 props 注释

### 4. 变更记录 ✅

- `swdm2/CHANGELOG.md` 0.1.0 条目：D0.2→D1.1..D1.6 + D1.5r 逐条（任务号、交付内容、修复详情、验证数字、环境要点、已知非阻塞项）

---

## 二、技术决议（本门新增/落地）

1. **UiTestsDriver**（`tests/UiTestsDriver/`）：SP-3 同模式反射驱动，STA 线程执行 [WpfFact]；特性匹配走纯反射（名称后缀 + 基类全名 `Xunit.FactAttribute` 双判据）规避 xunit.core 2.9.0 ↔ xunit.v3.core（StaFact 2.1.7 拉入）的 CS0433 二义（D0.2 已知约束的正面解）；未设 SynchronizationContext 以避免测试内 sync-over-async（`Retry.WhileNull(...).Result`）的 STA 重入死锁。**新建测试基础设施，按 captain 指令交 qa-20 审**（审阅维度：与 t3 §2.1/§3.x 契约一致性、特性匹配完备性、计数对账）。
2. **Directory.Build.props 版本单一事实源**：避免五项目分散写 Version；与 Velopack 打包同源（C4 版本号双端同步纪律）。
3. **诚实交付原则**：回归计数以真实执行为准（72+5），不沿用历史口径数字（74/63 均经对账纠正）；计数变更须在评审记录留痕（本节）。

---

## 三、四方投票（三原则口径）

| 成员 | 域 | 投票 | 意见摘要 |
|---|---|---|---|
| visual-20（执行） | App 自绘/主题 | **赞成** | 四要素全绿；阶段 1 范围克制（无删减/新增请求）；基础设施对下游契约齐备；UiTestsDriver 已交 qa-20 审 |
| arch-20 | Core/Downloads/架构 | *（异步投票中，意见追加于此）* | D1.5r 修复已自验并入库（25086c0）；Core 契约下游就绪 |
| qa-20 | UiTests/复测 | *（异步投票中 + UiTestsDriver 审阅待办，意见追加于此）* | |
| captain | 集成/构建/交付 | *（复跑确认后关门，意见追加于此）* | |

> 投票追加约定：本节为 append-only；成员回复直接落"意见"列并标注时间。出现反对票时按 DAG §6 放行门流程升级处置（重开 patch 版本）。

---

## 四、遗留自办项（不阻塞 0.1.0 关门）

- **visual-20**：t2 v1.1 回写（SwdmCard 根 Grid→UserControl、Hint 根 Border→UserControl、§2 通用条款补 A7 载体表、标题栏片段条件化）——D5 前完成（review_2.0_plan.md 遗留项）。
- **qa-20**：t3 v1.x 回写（StaFact 2.1.7 实证约束、Calibration 基准迁 Core.Tests、§7.2 映射同步）；UiTestsDriver 审阅。
- **arch-20**：WPF-UI API 表面 D0/D5 首用前反射实测（A8b，SP-1 两处漂移已知）。

---

> 附：本记录对应的计划版本 `swdm2/docs/architecture_2.0.md` §6 终版 v2.3；基线 10 条锁定决策映射见其 §1。
