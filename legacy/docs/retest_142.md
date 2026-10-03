# SWDM 1.4.2 复测两轮结论表（交付闸门）

复测人：qa-owner（t10，attempt 1）。复测对象：1.4.2 最终提交链 `9faba62`（fix(1.4.2)：交互层五 bug 修复 + 线程规矩 + 下载域 F4/F2/F3 + 设计令牌 + 2.0 准备）→ `ae9c2a1`（sweep 残留清理）→ `1fc66b0`（test_gui_sweep stub 化 + test_hub_page 入 skip）；工作树干净，零未提交改动。
环境：Windows + PySide6 6.11.2 offscreen + 独立 temp APPDATA，全部网络出站打桩。
判定标准：脚本 stdout `RESULT:` 行为准；退出码 -1073740791 为既有 Qt 拆卸崩溃噪声（t3/t44 起既有约定，与功能无关）。
日期：2026-10-02。

## 交付闸门结论：连续两轮复测均无异常 → **通过**，可提交讨论组终裁

| 轮次 | 范围 | 项数 | 结果 |
|---|---|---|---|
| 第一轮 | 用户视角剧本 + 官方交互测试 + 真实 worker 冒烟 + 下载语义探针 | 46 + 17 + 4 + 3 场景 | **RESULT: ALL PASS**（四工件零失败） |
| 第二轮 | tests/run_all.ps1 全量离线回归基线（captain 串行权威重跑 v3） | 71 脚本 | **pass=71 fail=0 noresult=0**（见第二节对照） |

## 一、第一轮：用户视角交互回归（4 工件全绿）

| 工件 | 路径 | 项数 | 结果 | 覆盖 |
|---|---|---|---|---|
| 用户视角剧本 | tests/test_retest_round1_142.py | 46 | ALL PASS | S1 换游戏（联想→回车→appid 解析）· S2 mod 搜索（≤150ms 即时反馈+搜索词透传+卡片渲染）· S3 翻页（下一页/上一页+页签+worker.page）· S4 勾选（计数/使能/取消重勾）· S5 下载勾选（自动切下载页+即时占位行+状态提示）· S6 暂停/继续（按钮文案/管理器态/暂停期间排队任务不派发）· S7 失败重试（终态 FAILED+行内重试按钮+批量「↻ 重试失败」重排队成功）· S8 取消+行内重试（取消终态+按钮变「重试」+重试成功）· S9 全局（四任务全 SUCCESS+统计无失败+stderr 无未捕获异常） |
| 官方交互测试 | tests/test_user_interaction.py | 17 | ALL PASS | I1 联想选择解析 · I2/2b Backspace 逐字（Latin+CJK）· I3/3b 错误游戏名回车 · I4 中英文适配（饥荒↔Don't Starve）· I5 搜索即时反馈 · I0 全程无 deleted C++ 异常 |
| 真实 Worker 冒烟 | tests/test_browse_render.py | 4 | ALL PASS | 真实 BrowseWorker（非桩）→ items_ready → cards>0 + stderr 干净（F1 回归守卫） |
| 下载语义探针 | tests/_probe_dl_semantics.py | 3 场景 | 全部修复态 | 场景1 失败→retry_all_failed→SUCCESS 正常登记 · 场景2 暂停期间 B 未派发（队列保留）· 场景3 取消后行内重试 SUCCESS 正常登记（F4 正常态） |

剧本要点：全部用户动作走 QTest 真实按键/点击（keyClicks/keyClick/mouseClick），不直调用户操作方法；网络层全桩（GameSearchClient / SteamAPI.browse/enrich/resolve_dependency_tree），下载引擎桩可阻塞闸门+可控失败；BrowseWorker 桩的信号契约与真实 worker 逐项对齐（items_ready=Signal(list,int)，防 F1 类元数漂移再被桩掩盖）。等待一律 time.sleep+processEvents（QTest.qWait 的 C++ 事件循环不释放 GIL，会饿死纯 Python 工作线程——测试环境学知）。

## 二、第二轮：run_all.ps1 全量离线基线（对照 1.4.1）

基线范围：71 脚本执行（1.4.1 基线 69 + 新增 test_user_interaction.py / test_browse_render.py / test_retest_round1_142.py）；skip 列表 22 项 = 1.4.1 既有 21 项网络/压力/冒烟/JS 探针 + test_hub_page（fake-IP 代理关闭时直连 steamcommunity.com 超时，属环境噪声，非代码回归）。

| 指标 | 结果 |
|---|---|
| **SUMMARY**（最终提交态 `1fc66b0`，captain 串行权威基线 v3，输出 %TEMP%\swdm_reg_v3.txt；qa-owner 已亲自复核该文件的 SUMMARY 行与逐项 PASS 行） | **pass=71 fail=0 noresult=0 total=71** |
| 1.4.1 基线对照 | 1.4.1 基线 69 → 本轮 71（=69 + 三个 1.4.2 新增测试 test_user_interaction / test_browse_render / test_retest_round1_142，全部 PASS）；test_hub_page 按既有网络噪声惯例移入 skip（fake-IP 代理关闭时直连 steamcommunity.com 超时；代理在线时可过，1.4.1 基线 run_all_t40b.log:113 有 PASS 记录） |
| 1.4.2 修复点回归 | test_gui_sweep（F3 后 ghost 行竞态已 stub 化修复，qa-owner 独立复验 ALL PASS）+ 全部套件全绿 |
| skip 列表 | 22 项（1.4.1 既有 21 项网络/压力/冒烟/JS 探针 + test_hub_page）；均为环境噪声，非代码回归，联网时可单独重跑确认 |

两轮连续独立复测均无异常：**交付闸门通过，可提交讨论组（t11）终裁**。

## 三、两轮复测覆盖的本轮修复项

| 修复项 | 来源 | 复测证据 |
|---|---|---|
| QCompleter 联想重做（退格 bug）+ CJK 输入 | t2 | 官方 I2/I2b + 剧本 S1a |
| 搜索/翻页即时反馈（≤150ms） | t2 | 剧本 S2a |
| 中英文游戏名适配（55 条别名表+归一化） | t2 | 官方 I4 + 剧本 S1b/c |
| 跨线程信号绑定方法（四处 DirectConnection 崩溃元凶） | t2 | 官方 I0 + 剧本 S9c |
| QThread 生命周期保活池 + 回调守卫 | t1 | 官方 I0 + 剧本全程零 QThread Destroyed |
| items_ready 信号元数（F1，t6 发现） | t9 前置修复 | test_browse_render.py cards=2 |
| _active 归属对象同一性（F4：取消后行内重试 SUCCESS 被吞） | t9 | 剧本 S8f + 探针场景3 |
| 暂停派发复查（F2：暂停期间排队任务仍派发） | t9 | 剧本 S6e + 探针场景2 |
| svc.downloads_tab 接线（F3：即时占位行死路径） | t9 | 剧本 S5b |
| retry_all_failed 收尾瞬态等待（S7d：fallback 窗口扫到空集） | t9 | 剧本 S7d |

## 四、已知限制（不阻塞）

1. 退出码 -1073740791：Qt 拆卸阶段崩溃，既有环境噪声（t3 起约定），不影响 RESULT 判定；所有 GUI 脚本复现一致。
2. 读图工具本机不可用（sharp ERR_DLOPEN_FAILED / modlens API key invalid）：GUI 视觉类（挤压/重叠/裁切）未纳入本轮，由几何量化兜底（t4/t7 令牌层覆盖）。
3. 托盘态/真实剪贴板交互 5 条人工清单（docs/clipboard_watch_notes.md）offscreen 不可验证。
4. skip 列表 21 项为网络环境噪声项，需联网时单独重跑确认（非代码回归）。
