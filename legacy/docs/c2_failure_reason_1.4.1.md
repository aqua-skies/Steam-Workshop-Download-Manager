# C2 · item 级失败原因枚举 + 受限物品提示登录（t41）

> 执行人：search-fixer（t41，attempt 1） · 日期：2026-09-29 · 前置：t31 评审（C2 纳入 + 误报红线）、t32（C5 结论：GGNetwork 维持 🟡，不改变本任务启发式）

## 1. 痛点

steamcmd 对工坊下载失败只给通用错误串（`ERROR! I/O Operation Failed`、`Failed to download item …`、`Not Logged On`），**不区分**：

- entitlement（账号无该游戏所有权）
- auth（未登录 / Steam Guard）
- 限流
- 网络故障
- 物品不存在

Valve issue steam-for-linux#13474（scoped server token 提案）是公认痛点：在官方区分这些原因之前，任何把通用 I/O 失败翻译成「需正版账号」的做法都会产生误报——用户会被误导以为必须先买游戏，**误报比不报更伤**。

## 2. 设计：保守分类 + 误报红线

新增纯函数模块 `swdm/core/failure_reason.py`（无 Qt 依赖、不触碰任何全局状态，与熔断器**正交**）：

| 桶 | 触发条件 | 用户文案 |
|---|---|---|
| `DISK_FULL` | `No space left` / `磁盘空间不足` | 磁盘空间不足，请清理后重试 |
| `EMPTY_SUCCESS` | 本程序自产的「下载内容为空」（E③ 0 字节假成功） | 透出原文 |
| `RATE_LIMITED` | 运行期 `rate_limit` 信号，或消息含「限流 / rate limit」 | 触发 Steam 限流，请稍后重试 |
| `NETWORK` | 运行期 `timeout` 信号，或消息含「超时 / timeout」 | 网络超时或无法连接 Steam 服务器，请检查网络后重试 |
| `LOGIN_FAILED` | 「登录失败」开头 / Steam Guard / 密码错误（**凭据问题，与所有权严格区分**） | 透出引擎原文 |
| `ITEM_GONE` | 「物品不存在 / 下架 / result=9」 | 物品不存在或已从 Steam 工坊下架 |
| `ACCOUNT_NEEDED` | **仅两条正向信号**（见下） | 该游戏可能需要正版 Steam 账号才能下载（受限应用）。可在「设置 → 账号」登录 Steam 账号后重试；若你已拥有该游戏，失败原因可能并非权限问题——详见日志 |
| `GENERIC` | 兜底 | 下载失败：steamcmd 未区分权限/网络/限流等原因，建议重试。详见日志 |

**误报红线**：桶判定顺序保证 `ERROR! I/O Operation Failed`、`Failed to download item …`、`Not Logged On`、`下载未完成（可能超时）` 等**通用串一律落入 GENERIC 或 NETWORK，绝不落入 ACCOUNT_NEEDED**（42 项测试中 5 项专门钉这条红线）。

**ACCOUNT_NEEDED 的两条正向信号**（t31 决议的保守口径）：

1. **受限 App + 匿名下载未开始**：appid 在 `RESTRICTED_APPS`（DayZ 221100、Barotrauma 602960，依据 `research/bypass_ownership_research_1.4.1.md`）且引擎报「未开始下载（…不支持匿名下载）」——即匿名登录成功但无任何下载行，等价于「匿名 file_url 为空」的观测。
2. **重试后仍同一错误且本次运行无网络信号**：历次 attempt 的失败文案完全相同（≥2 次）且本次运行未出现 rate_limit / timeout 特征。

账号文案刻意三重不误导：用「可能」、明示「若你已拥有该游戏，失败原因可能并非权限问题」、末尾指引日志。

## 3. 接线（`swdm/core/downloader.py`）

- `DownloadJob` 新增三字段：`signals`（本次运行的特征集合）、`attempt_messages`（历次失败文案）、`failure_bucket`（归类结果，供 GUI/t38 使用）。
- `_on_throttle_signal` 用 thread-local `self._local.job` 把信号归到**当前线程正在跑的 job**（manager 级退避/熔断行为不变）。
- `_exec_job` 在 E③ 检查后把任何 FAILED 的 `result.message` 追加进 `attempt_messages`（重试与终态两条路径共享完整历史）。
- 终态 FAILED 分支调用 `classify_failure(...)` + `render_failure(...)` 写入 `job.message`；**原文完整保留在日志与 `attempt_messages`**，非 GENERIC 桶额外记录一行归类日志。
- 熔断器（`_reg.record_failure` / `Backoff.record_failure` / 并发降级）路径**完全不变**：枚举管单物品可读结论，熔断管通道健康度，二者正交。

## 4. t32（C5）输入的落实

t32 结论「GGNetwork 维持 🟡、不上调 🔴」**不改变**本任务启发式，且强化了两条约束：

- GGNetwork 的后端错误串**不可信**（`"need login to account"` 出现在一个已被 Steam 删除的物品上）——失败原因枚举只吃 **steamcmd 侧**的确定性信号，不吃任何第三方代理文案。
- 通用 steamcmd I/O 失败不得映射「需正版账号」——本模块的 GENERIC 桶就是这条红线的代码体现。

受限 App 提示登录的**确定性来源只能是 steamcmd 侧**（匿名下载未开始 + 受限名单），第三方代理行为不参与判定。

## 5. 测试

- 新增 `tests/test_failure_reason.py`：**42 项 ALL PASS**——分类表正例（8 桶）、误报红线 5 串、正向信号 ①② 及其否决条件（timeout 信号否决②、消息不一致否决②、未重试否决②）、文案不误导性、与熔断器正交（纯函数 + 失败仍记退避）、downloader 集成（终态文案归类、thread-local 信号采集、job 默认字段）。
- 关键回归：`test_throttle`（含 7a/7g/7h）ALL PASS、`test_ap1_cancel_race`（16 项 cancel 竞态）ALL PASS、`test_download_fixes` ALL PASS、`test_providers` 89/89 ALL PASS、`test_core_sweep` RESULT ALL PASS。
- 全量回归：见 t41 commandsRun。

## 6. 局限与后续

- `RESTRICTED_APPS` 是硬编码名单（新证据在 `failure_reason.py` 扩展）；待 Valve #13474 落地后，受限 App 的匿名下载若被官方解决，本模块的 ACCOUNT_NEEDED 桶会自然闲置（每轮迭代复查）。
- 正向信号 ② 的「网络正常」判据是「本次运行无 hard signal」，是代理观测而非端到端连通性检查——故意保守，网络疑似问题时优先归 NETWORK 让用户重试。
- 账号失败与熔断解耦已覆盖；t38（C3 私人账户 provider）可直接消费 `job.failure_bucket == "account"` 做登录引导入口。
