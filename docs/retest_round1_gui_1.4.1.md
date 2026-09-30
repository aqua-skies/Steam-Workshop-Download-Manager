# SWDM 1.4.1 复测第一轮（GUI/用户视角）— 2026-09-30

复测对象：1.4.1 打包终态（`installer\Output\SWDM-Setup-1.4.1.exe` 45.5MB + 源树）。
执行人：gui-checker（t44，attempt 2）。环境：Windows + PySide6 offscreen + 独立 temp APPDATA，
全部网络出站打桩。判定标准：脚本 stdout `RESULT:` 行（退出码 -1073740791 为既有 Qt 拆卸崩溃，同 t3 判定）。

## 一、结论：第一轮复测**通过**（1.4.1 可进入第二轮核心复测）

- 1.4.1 十个主功能的用户视角全部 PASS（详见第三节）。
- **A6 修复经真实线程路径验证通过**（captain 裁决的交付前修复项，见第五节）。
- 两项审计待修项（U3 取消死代码 / P0-4 并发配置静默失败）按 captain 裁决为 1.4.2 修复池内容，
  本轮特征化记录现状、确认与断言一致，**不判为 1.4.1 阻塞项**。
- exe 冒烟（captain 移交项）在 gui-checker 会话通过：进程稳定运行 10 秒+。
- 全量回归与 1.4.1 基线一致（见第六节）。

## 二、打包终态（P0，9 项 ALL PASS）

| 项 | 结果 | 证据 |
|---|---|---|
| 安装包存在 | PASS | `installer\Output\SWDM-Setup-1.4.1.exe` 45.5MB（47756369B，2026-09-30 20:32） |
| 版本号双端 | PASS | `swdm/core/paths.py:13 APP_VERSION="1.4.1"` + `installer/swdm.iss:14 SWDMVersion="1.4.1"` |
| 变更记录 | PASS | `docs/changelog_1.4.1.md`（18.9KB） |
| 运行时版本 | PASS | GUI 标题栏「Steam 工坊下载管理器 v1.4.1」 |
| 帮助>用户手册(F1) | PASS | 菜单项「用户手册(&M)」存在（t43 接线 main_window.py:124-129） |
| 手册随包 | PASS | `build/dist/SWDM/_internal/manual/SWDM-用户手册.html`（140006B）+ PDF |

证据脚本：`tests/test_rettest_141.py` P0 组；来源 t43 构建链报告。

## 三、1.4.1 功能复测（P1–P8 + P5，56 项 ALL PASS）

证据脚本 `tests/test_rettest_141.py`（offscreen，网络打桩）：

| 功能 | 项数 | 覆盖点 |
|---|---|---|
| B1 详情磁盘缓存（P1） | 6 | 磁盘命中零网络；手动刷新强制 bypass；time_updated 前进触发双失效；新页面回写磁盘；损坏缓存文件不崩回退网络；内存缓存命中零网络 |
| B2 翻页预取（P2） | 3 | 满页+代际当前→调度预取定时器；未满页不调度；熔断冷却期不调度 |
| B3 剪贴板自动入队（P3） | 6 | 工坊链接→自动入队+状态栏提示；重复触发去重；非工坊文本静默跳过；配置关闭解绑+重开即连 |
| 关联交互（P8） | 3 | 剪贴板入队→下载页空态切换为表格行（经 Qt 信号桥接，非直调） |
| B5 批量粘贴导入（P4） | 3 | 多链接+纯 ID+垃圾行混合全部解析入队；弹窗路径去重；无效输入弹警告 |
| B6 空态引导（P5a/P5b） | 9 | 下载页空队列→「前往工坊浏览」引导；库页空库→「还没有 mod」+引导按钮；筛选无结果→「没有匹配的 mod」+「清除筛选」 |
| A2 QSS（P6） | 7 | 深浅双主题进度条 done/failed 状态色、表头、滚动条规则存在；auto/dark/light 主题解析；QSS 应用到 MainWindow |
| 设置页新开关（P7） | 6 | 剪贴板监听（默认开）、详情缓存开关（默认开）、TTL 控件、主题三选项（深色/浅色/跟随系统）、「🧹立即清除缓存」实测生效、应用函数回写 config |
| C1 库检查更新 | 专项 | 见第五节 A6/A7（真实线程路径标红+入队+收尾），按钮存在性 P5b7 |

## 四、exe 冒烟（captain 移交的第 4 项）

- 环境：gui-checker 会话（captain 会话沙箱封锁派生进程写 AppData，成员会话无此限制——t43 报告判定依据）。
- 执行：`build\dist\SWDM\SWDM.exe`，offscreen + 干净 temp APPDATA，启动后 8 秒检查 + 10 秒复查。
- 结果：**PASS** — pid=11184 8 秒时 ALIVE，10 秒时 STILL-ALIVE，稳定运行后 kill 收尾。
  （packager 18:11 冒烟 crash.log 另证 exe 可启动到 GUI；teardown 崩溃为既有 Qt 模式，不算 fail。）

## 五、审计必检三项 + A6 修复验证（t44 专项，tests/test_t44_retest_gui.py 30 项 ALL PASS）

### A6（Q_ARG(list) 完成回调失效）→ **1.4.1 打包前已修复，本轮复测验证通过**

- 预检发现：`library_tab.py:398-401` 用 `QMetaObject.invokeMethod(..., Q_ARG(list, updated or []))`，
  bare Python list 在本机 PySide6 无 QMetaType → worker 完成时抛 RuntimeError →
  `_on_check_updates_done` 从未被调用 → 按钮永久卡「检查中」、无标红、无询问窗。
  最小复现：`tests/test_qarg_list_repro.py`（原 buggy 断言，t43 已改为修复态断言并在回归 PASS）。
- 修复（packager 落地，captain 验证）：`library_tab.py:54-58` 新增 `updates_checked = Signal(list)` +
  `check_progress = Signal(int, int)`，worker 直接 emit，`library_tab.py:180` connect 收尾。
- **本轮复测（真实线程路径，不再直调收尾——t37 测试盲区）**：
  - A6a-d：daemon worker 正常结束、无异常；`_on_check_updates_done` 经 Signal(list) 被 GUI 线程调用 1 次；
    列表内容完整透传；
  - A6e-h：按钮恢复可用 + 文本恢复「🔍 检查更新」；标红集合生成；弹出「发现更新」询问窗；
  - A7：**阻塞场景**（长检查完成后）done 回调同样经真实线程路径到达、按钮恢复。
- 结论：C1 端到端链路（按钮→daemon 线程→Signal→GUI 收尾→标红→询问→入队）在 1.4.1 打包终态**完整可用**。

### ① U3 检查更新可取消性 → **确认 bug，captain 裁决 1.4.2 修复池（ux_audit U3）**

- A1 静态：`library_tab.py` `_check_cancel` 仅 2 处赋值、全部 = False，无置 True 路径（死接线）。
- A2/A3/A4 运行时：运行中按钮禁用（防重入）；点击禁用按钮 / 刷新列表均不能中止线程；
  cancel 回调被 worker 轮询 3 次恒 False。**用户无法取消正在进行的检查**。
- A5 契约对照：核心 API 层 cancel 契约真实生效（cancel() 返回 True 后中止后续批次，n=3/out=100），
  契约文档承诺「用户关闭进度对话框中止」——**契约冲突成立，非审计误报**。
- 裁决依据：核心契约层正常，属 UI 可达性增强；A6 修复后不再造成卡死。1.4.2 修复池已收。

### ② 最大并发下载配置静默失败 → **确认 bug，captain 裁决 1.4.2 修复池（core_audit P0-4）**

- B1：`refresh_engine` 后 `downloader.max_concurrent` 3→6（配置值更新），但调度门
  `_concurrency._max`=3/current≤3（`throttle.py:125` 构造时固化）。
- B2 功能级实测（真实派发循环 + 打桩通道链，8 个 job）：实际并发观测上限 **3**（旧值）而非 6 → **调大静默失败**。
- B3 反向：调低（5→1）后 `_concurrency.current` 仍=5，派发门不降。
- 根因链核实：`_run_loop` 派发门读 `self._concurrency.current`（downloader.py:445），
  refresh 只改 `max_concurrent`（services.py:58-60）。
- 说明：B2a/B2b/B3a/B3c 为**特征化断言**（钉死 P0-4 现状，1.4.2 修复后需翻转——docs/research/plan_1.4.2_impl.md 已登记）。

## 六、全量回归（run_all.ps1）

- 统计：**89 脚本 · 87 PASS / 2 FAIL / 0 NORESULT**（t43 基线 88 脚本 87/1，+1 为本轮新增
  `tests/test_rettest_141.py`，PASS）。
- 2 个 FAIL 逐项定性（均非代码回归）：
  1. `test_stress`（RESULT: 1_SLOW）— 性能标记，两次单跑结果一致，t43 已判环境性
     （机器被挂死的实网测试拖慢）。
  2. `test_game_dir_e2e`（RESULT: HAS FAILURES）— 单跑定位：真实 e2e 下载**实际成功**
     （JobStatus.SUCCESS / 已入库 / local_path 在专属目录 / 内容目录 7 个文件），
     唯一失败项是测试自身的 5 分钟看门狗被慢实网触发（300s 超时）；另见测试桩把
     `downloader.on_finished` 误置为函数（而非 list）导致 `_fire_finished` 抛 TypeError
     的线程异常——测试固件缺陷，非产品缺陷。
- key 新增/改动脚本在回归中全 PASS：`test_rettest_141`（56 项）、`test_t44_retest_gui`
  （30 项，A6 真实线程路径）、`test_qarg_list_repro`（Signal 修复态，t43 已验）。
- 零 lib 代码变更（t43 后仅新增/改测试文件），回归基线与交付终态一致。

## 七、offscreen 限制与人工清单（诚实披露）

1. **托盘态 / 真实剪贴板交互**：offscreen 平台 `QClipboard` 不产生 `dataChanged` 事件、托盘不可用。
   本轮剪贴板测试全部经 `_on_clipboard_changed` 直调 + `_clipboard_text` 打桩验证逻辑层；
   真机 5 条人工清单见 `docs/clipboard_watch_notes.md`（浏览器复制/托盘态复制/非工坊内容/合集链接/开关关闭）。
2. **读图工具不可用**：QSS 视觉效果（P6）以规则存在性 + 应用断言验证，未做像素级目检（同历轮）。
3. **exe 冒烟**为进程级存活验证，GUI 画面目检由 packager 18:11 crash.log 的缩略图加载记录佐证。

## 八、交付闸门判定

第一轮（GUI/用户视角）复测：**无异常通过**。1.4.1 打包终态满足交付闸门测试侧第一轮条件，
进入 t45 核心逻辑第二轮复测。三项审计结论（U3 / A6-已修 / P0-4）正式登记为 1.4.1 交付记录：
A6 修复在打包前完成并经真实线程路径复测验证；U3 与 P0-4 归入 1.4.2 修复池（t49 候选清单已收）。
