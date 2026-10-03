# SWDM 1.3.9 · bug 复测第二轮（核心逻辑独立复测）

- 复测人：core-tester（AgentTeams swdm-138，t19）
- 复测对象：1.3.9 打包终态（installer\Output\SWDM-Setup-1.3.9.exe 42.67MB）
- 日期：2026-09-28
- 与 t18（GUI 视角复测）互补，构成交付闸门的「连续两轮复测」第二轮

## 结论：全部通过

核心逻辑复测 40 项检查全部 PASS；全量离线回归 56 脚本 54 PASS / 2 既有非回归
（与 1.3.8 基线逐项一致，零新增失败）。**第二轮复测无异常。**

## 复测方式

刻意不重复 t14/t15 的既有用例，而是新写两套独立复测脚本，用独立构造的 mock
数据与边界场景从另一角度验证：

- tests/test_t19_retest.py — 28 项
- tests/test_t19_retest2.py — 12 项

## 重点逐项结论

### 1. 下载速度采样（t14 ProgressSmoother deque 滚动窗口）

| 检查 | 结论 |
|---|---|
| 滚动窗口淘汰窗口外样本（5s 前样本不参与当前速度） | PASS — speed=0.0 |
| 窗口速度=真实增量/真实经过时间（非 tick 数×平均，无突跳） | PASS — speed=10.0 MB/s（20MB/2s） |
| 长停顿（9.5s）后速度归 0，不残留历史突跳 | PASS — speed=0.0 |
| 样本数封顶 _MAX_SAMPLES=64，不无限增长 | PASS — n=64 |
| bytes_done>=total → percent=100（完成判定以字节数为准） | PASS |
| bytes 99% 时 percent<100（不假完成，卡 99% 修复确认） | PASS — pct=99 |
| total=0 除零保护（percent=-1 而非 100） | PASS |

### 2. mod 库按游戏分类（schema 与查询）

| 检查 | 结论 |
|---|---|
| appid 落库可按 appid 精确过滤（4000→2，730→1） | PASS |
| 跨游戏查询互不污染 | PASS |
| upsert 同 item_id 换 appid 是更新而非新增 | PASS |
| 总记录数无重复（4 条） | PASS |
| sort=appid 升序有序（SQLite TEXT 语义，空串最前） | PASS |

### 3. 详情页解析正确性（mock HTML，字段提取齐全）

| 检查 | 结论 |
|---|---|
| 描述提取（workshopItemDescription 锚点） | PASS — 多段保留 |
| 作者名提取（creatorName 正则） | PASS |
| 依赖提取含 id 与标题、按页面顺序 | PASS — [(99001,依赖甲),(99002,依赖乙)] |
| 空依赖页不崩 | PASS |
| RequiredItems 容器外的 requiredItem 链接不被误抓（精确区块定位） | PASS |
| 兜底解析（robust，锚点缺失时 sharedfiles 路径） | PASS |

t15 的优先级礼让优化只改节流层，解析链路零改动，解析正确性不受影响。

### 4. 并入的 1.3.8 遗留项

| 项 | 检查 | 结论 |
|---|---|---|
| A-P3 on_throttle_signal 订阅化 | 是列表、append 生效、第二订阅者共存不覆盖 | PASS |
| A-P3 接线 | DownloadManager 构造即 append 订阅者（n=3） | PASS |
| E③ steamcmd bytes=0 校验 | SUCCESS+0 字节 → 改判 FAILED（假成功拦截） | PASS |
| E③ 对照 | SUCCESS+1MB → 仍 SUCCESS（不误杀） | PASS |
| t15 端点节流 priority 礼让 | priority=True 绕过等待；低优先级遇 _priority_pending 立即让槽返回 False；无积压时正常放行；计数器归零无泄漏 | PASS |
| 缓存深拷贝（用户级硬规则） | browse() 命中缓存返回深拷贝，外部修改（title/tags）不污染缓存 | PASS |
| 缓存 TTL | 过期自动失效 | PASS |
| 下载状态机竞态修复（core-tester 本轮修） | test_throttle 7g/7h 守卫 + 全量回归 test_throttle PASS | PASS |

### 5. 全量离线回归（与 1.3.8 基线逐项比对）

run_all.ps1 串行（QT_QPA_PLATFORM=offscreen + PYTHONUTF8=1）：

```
SUMMARY: pass=54 fail=2 noresult=0 total=56
FAILED: test_legacy_format, test_page_parser
```

- 新增 2 脚本为本轮复测脚本（test_t19_retest / test_t19_retest2），均 PASS。
- 2 FAIL 与 1.3.8 基线完全一致，均为既有非回归：
  - test_legacy_format：mock 数据字节数漂移（7816 vs 18434，非真实下载），夹具问题。
  - test_page_parser：旧版标签夹具结构（无 RequiredItems 容器），夹具未随解析器升级。
- 零新增失败，零 NORESULT。

## 核心状态机稳定性

test_throttle（含竞态修复 + 7g/7h 确定性守卫）全量回归 PASS；此前 15 轮采样 0 失败
（修复前 5/8）。test_v136（gui-tester 固件修复）PASS。

## 交付闸门状态

- 第一轮复测（t18，GUI 视角）：gui-tester 完成
- 第二轮复测（t19，核心视角，本文）：**无异常**
- 连续两轮复测条件满足，待 t20 交付评审（讨论组结论已汇总于 docs/feature_review_1.3.9.md）
