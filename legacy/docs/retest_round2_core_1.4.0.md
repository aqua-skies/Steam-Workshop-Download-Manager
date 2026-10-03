# SWDM 1.4.0 · bug 复测第二轮（核心逻辑独立复测）

**复测人**：core-tester（t26，attempt 78ce6f7a）
**复测对象**：1.4.0 打包终态（SWDM-Setup-1.4.0.exe 42.69MB，t24 产出）
**日期**：2026-09-29
**方法**：新建独立复测脚本 `tests/test_t26_retest.py`（独立 mock 数据 + 边界场景，
刻意不重复 t21/t28 自测的用例）+ 离线全量回归。
**结论**：**45 项独立检查全 PASS，全量回归零新增失败，核心逻辑复测无异常。**

与 t25（gui-tester，GUI 视角）共同构成 1.4.0 交付闸门「连续两轮复测无异常」。

---

## 1. 独立复测脚本结果（tests/test_t26_retest.py · 45/45 PASS）

### A. provider 链式回退（6 项）

| 检查 | 结果 |
|---|---|
| should_fallback 不扫描消息文本（SUCCESS 消息含「回退」字样不触发回退） | PASS |
| should_fallback FAILED 触发回退（结构化判定） | PASS |
| 三通道链全失败时每个 provider 都执行过（链确实遍历） | PASS |
| **链内回退不消耗 auto_retry**（三通道全失败后 attempt 仍为 0） | PASS |
| 全失败终态 FAILED | PASS |
| terminal 通道失败不熔断（兜底永不下线） | PASS |

**熔断冷却恢复**（直接操作 `_Circuit` 时间）：

| 检查 | 结果 |
|---|---|
| 连续 3 次失败后熔断 | PASS |
| 冷却过期后半开（is_tripped 返回 False） | PASS |
| 半开期失败重新熔断 | PASS |
| 成功后完全重置 | PASS |
| 熔断通道被 build_chain 跳过 | PASS |
| 半开后 build_chain 重新纳入该通道 | PASS |

**t28 清理在打包终态的验证**（任务书提到「60s 探测缓存」，t28 评审决议已删除该机制，
此处验证删除后系统仍正确）：

| 检查 | 结果 |
|---|---|
| `list_channels()` 签名无 `probe_results` 参数 | PASS |
| registry 无 `probe()` 方法 / 无 `_probe_cache` / 无 `invalidate_probe()` | PASS（3 项） |

### B. 匿名降级（2 项）

| 检查 | 结果 |
|---|---|
| 需 key 且未配置的通道被链构造跳过（不报错） | PASS |
| 匿名降级后链尾仍是 steamcmd | PASS |

### C. services.py:78 修复（1 项）

| 检查 | 结果 |
|---|---|
| manager 构造的链中 provider 拿到 api（登录态 CDN 通道 file_url 补全的前提） | PASS |

### D. GGNetwork（7 项）

| 检查 | 结果 |
|---|---|
| 限速器默认 20/min（间隔 3s） | PASS |
| 突发容量 3（初始令牌） | PASS |
| 突发 3 个令牌立即可用 | PASS |
| 令牌耗尽且 stop_event 置位时 acquire 返回 False 不阻塞（取消语义） | PASS |
| zip 多层目录中的 .gma 被提取到 content 根（独立夹具 item 555） | PASS |
| 解压后原压缩包删除 | PASS |
| 魔数错误带⚠ 但 size 一致**不判坏包**（不误伤合法转存） | PASS |
| 正品（GMAD + size 一致）无⚠ 不判坏包 | PASS |

### E. t22 核心项（7 项）

| 检查 | 结果 |
|---|---|
| cancel 后 job 在 `_cancelling` 集合中（pending 标记先于 _stop 置位） | PASS |
| cancel 后 `_stop` 已置位 | PASS |
| 取消的任务从 `_active` 移除 | PASS |
| GameSearchClient 连接错误立即熔断冷却 15s | PASS |
| 普通失败 2 次不熔断 / 连续 3 次熔断 | PASS（2 项） |
| 搜索词过短返回空不报错 | PASS |
| GameSearch 缓存命中返回副本（不污染缓存） | PASS（2 项） |

### F. 既有核心在 provider 链下（6 项）

| 检查 | 结果 |
|---|---|
| 卡99%：bytes_done=999/total=1000 → percent 99（不以 100 卡住） | PASS |
| bytes_done>=total → percent 100 | PASS |
| browse() 缓存命中返回深拷贝（外部修改不污染 api_cache） | PASS（3 项） |
| 端点节流：无高优先级时低优先级等满间隔放行 | PASS |
| 端点节流：高优先级绕过等待 | PASS |
| 端点节流：高优先级在飞时低优先级立即让槽（返回 False） | PASS |

---

## 2. 离线全量回归

```
run_all.ps1（串行，61 脚本）
SUMMARY: pass=59 fail=2 noresult=0 total=61
FAILED: test_legacy_format, test_page_parser
```

- **2 FAIL 均为 1.3.8 起既有非回归**（test_legacy_format 的 mock 字节数漂移、
  test_page_parser 的旧夹具），与 1.3.8/1.3.9/1.4.0 各轮基线逐项一致。
- **零新增失败、零 NORESULT**。t24 时点的 3 项纯环境网络失败
  （test_bulk_games/test_bundle_ctx/test_bundle_methods）本轮环境恢复后全部 PASS。
- 新增脚本 `tests/test_t26_retest.py` 已自动纳入 run_all（动态枚举 test_*.py），
  本轮在 run_all 内同步 PASS；`tests/test_rettest_140.py`（他方新增）亦 PASS。

---

## 3. 复测发现的问题

**无。** 45 项独立检查 + 61 脚本全量回归均未发现任何核心逻辑缺陷。

**说明一处任务书差异**：任务书重点列「60s 探测缓存」，该机制已由 t23 评审决议
+ t28 执行删除（registry 的 `probe()` / `_probe_cache` / `list_channels(probe_results=)`，
理由：UI 只需配置态、探测缓存引入 60s 延迟且 zero 调用方）。本轮验证删除后
链构造、匿名降级、熔断冷却均正确，未出现依赖该机制的残留路径。

---

## 4. 交付闸门对照

| 条件 | 状态 |
|---|---|
| 讨论组一致认为可交付 | t23 verdict=pass 五方零反对 ✓ |
| 版本号 + 可追溯 changelog | t24：双端 1.4.0 + docs/changelog_1.4.0.md 十节 ✓ |
| 全量回归（不只测改动点） | t24 run_all 57/2 零新增 + 本轮 59/2 零新增 ✓ |
| bug 测试员连续两轮复测无异常 | t25（GUI 视角）+ **t26（核心视角，本报告）** ✓（t25 结论由 gui-tester 出具） |

核心逻辑视角复测通过，待 t27 交付评审。
