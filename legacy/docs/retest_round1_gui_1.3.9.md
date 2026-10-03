# SWDM 1.3.9 · 第一轮复测报告（GUI/用户视角）

任务 t18 · 2026-09-29 · gui-tester
复测对象：1.3.9 打包终态（installer\Output\SWDM-Setup-1.3.9.exe 42.67MB，版本号双端 1.3.9）

## 结论

**第一轮复测无异常。** 12 项用户报告 bug（U1-U12）全部从用户操作视角验证通过，全量离线回归零新增失败，与 1.3.8 基线逐项一致。

## 一、用户视角复测（tests/test_rettest_139.py，42 项 ALL PASS）

逐项从「用户会怎么操作」出发，而非只看单元测试桩：

| # | 用户场景 | 验证方式 | 结果 |
|---|---|---|---|
| U1 | 托盘里直接点「退出」能否退出（不先显示窗口） | 窗口 hide() 后调托盘退出路径 `_real_quit()`：直接触发 `QCoreApplication.quit()`、`_force_quit` 置位、AppMutex 已释放（OpenMutex 失败） | ✅ |
| U2 | 游戏框输入字符是否有联想下拉 | 输入 "gar" 即时本地匹配出 "Garry's Mod"，按匹配度排序（精确 > 开头 > 包含） | ✅ |
| U3 | 游戏框输入游戏名能否识别 | 三种输入全覆盖：英文名 "Garry's Mod"→4000、纯 AppID "4000"→4000、模糊输入 "garry" 经 `_best_guess_appid` 回退命中；中文游戏名内置表无则跳过 | ✅ |
| U4 | 搜索框回车是否生效 | 真实链路：本地无匹配 → 触发一次搜索 + 置待选标记 → 结果到达自动选中第一候选（appid 4000），标记清除 | ✅ |
| U5 | 选标签后是否还出现不含该标签的 mod | 3 物品（2 含"生存" 1 不含）：精确交集过滤保留 2 丢 1；端到端 `_on_items_ready` 后卡片只剩含标签的，状态栏提示"已按所选标签精确过滤" | ✅ |
| U6 | 切换游戏后标签栏是否自动切换 | 预选"生存"+ 过滤参数已设 → `_on_game_changed` 后选中清空、过滤参数清空 | ✅ |
| U7 | 下载是否还卡 99% | 字节打满立即 100%（不卡 99）；完成事件 force 通道 100% | ✅ |
| U8 | 速度显示是否平滑（不突跳） | 滚动窗口：匀速 10MB/s 显示 8-13MB/s 准确；10Hz 流中插入 20MB 合并 tick 被摊平到 <50MB/s（不突跳到 200-300MB/s）；停顿超窗口速度回落 | ✅ |
| U9 | 设置页第一行挤压是否消失 | 展开分组标题→首控件间距全部 ≥6px（findChildren 全量扫描）；目录表行高保底 30px、首行实际行高 ≥24px、首行在表头之下 | ✅ |
| U10 | 下载页删除与库页移除是否互通 | 双向：下载页移除已入库成功任务（选"同时移除"）→ 库记录删除 + library_changed 触发库页刷新 + 下载页行清除；库页 records_removed → 下载页旧行清除（走 main_window 真实接线） | ✅ |
| U11 | 库页不同游戏的 mod 是否分类可辨 | 行内显示游戏名（"Garry's Mod"/"Arma 3"），未知 appid 回退 "AppID 999999"；游戏过滤下拉也用游戏名而非裸 AppID | ✅ |
| U12 | 详情页加载是否明显变快 | 缓存命中：不发网络（_NoNetAPI 调用即断言失败）、解析出真实简介、整页 <100ms；用户点击 priority 绕过 3s 端点等待、预取低优先级遵守等待 | ✅ |

## 二、跨功能关联扩展（tests/test_cross_features.py，新增 16 项 ALL PASS）

在 t6 原有关联基础上扩展 1.3.9 新行为：

- **关联5 托盘隐藏态直退**：窗口 hide() 后托盘「退出」直接 quit，不先显示窗口；`_force_quit` 置位
- **关联6 游戏识别→标签过滤→结果链路**：输入纯 AppID 切游戏后旧标签选中与过滤参数被清空；标签精确过滤端到端只剩含标签物品 + 状态栏提示
- **关联7 删除互通双向（真实 main_window 接线）**：下载页移除成功任务 → 库记录删 + 库页刷新 + 下载页行清除；库页 `records_removed.emit` → 下载页旧行清除
- **关联8 导出当前筛选与库分类共存**：导出按当前筛选（关键词 + 游戏过滤联动，只导命中项）；库列表行内含游戏名可区分

## 三、全量离线回归（tests/run_all.ps1 串行）

**56 脚本：54 PASS / 2 FAIL / 0 NORESULT**

- 2 FAIL 为既有非回归，与 1.3.8 基线逐项一致：
  - `test_legacy_format`：真实 mod 字节数漂移（7816 vs 硬编码期望）
  - `test_page_parser`：旧标签结构夹具（已被 Wayback 实证推翻）
- 0 NORESULT（1.3.8 基线的 test_actions_api 实网 429 本次跑通 PASS）
- 1.3.9 两个修复点均 PASS：`test_throttle`（竞态修复 + 7g/7h 守卫）、`test_v136`（固件跨 check 污染修复）
- 新增脚本 PASS：`test_rettest_139`（本轮 42 项）、`test_cross_features`（含新增 16 项）

（进程退出码 -1073740791 为既有 Qt 线程拆卸崩溃，判定标准为 stdout `RESULT: ALL PASS`）

## 四、源码核对（确认打包终态与工作区一致）

逐项读了 t11-t15 + t16 并入项的实现态，确认全部在打包终态中：
- t11：`_do_real_quit()` 公共方法 + `_real_quit` 置 `_force_quit` 后直调（main_window.py:85-98 接线可见）
- t12：`_current_appid` 五层回退（精确 itemData/digit/下拉名/联想缓存/内置表）+ `_on_game_enter` 待选机制
- t13：`_on_game_changed` 开头清选中/过滤；`library_changed`/`records_removed` 双向信号
- t14：`ProgressSmoother` 滚动窗口速度（throttle.py:231-321）；库页 `game_name` 渲染（library_tab.py:183/234）
- t15：`_endpoint_throttle` 优先级礼让 + `_do_prefetch_detail` 守卫
- t16 并入 8 项：A-P3（on_throttle_signal list 订阅）、A-P1 防御、B① 提示柔化、B② 打开数据目录、B③ 导出当前筛选、C① 游戏名渲染、E② 托盘通知、E③ bytes=0 校验

## 五、与交付闸门的关系

本轮（t18 GUI 视角）与 t19（核心视角，40 项全 PASS）共同构成用户规定的「bug 测试员连续两轮复测均无异常」条件。两轮均无异常，闸门测试侧条件满足，待 t20 讨论组交付评审。
