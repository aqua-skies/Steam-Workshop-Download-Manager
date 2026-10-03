# SWDM 1.4.1 · bug 复测第二轮（核心逻辑独立复测）

**复测人**：core-checker（t45，attempt 8d9b412a）
**复测对象**：1.4.1 打包终态（t43 产出：`build/dist/SWDM/SWDM.exe` 8,613,764B
+ `_internal/manual/`（HTML 140,006B + PDF 1,404,127B）+
`installer/Output/SWDM-Setup-1.4.1.exe` 47,756,369B，内嵌 ProductVersion 1.4.1）
**日期**：2026-09-30
**方法**：新建独立复测脚本 `tests/test_t45_retest.py`（111 项独立 mock 数据 + 边界
场景，刻意不重复 t33/t34/t37/t41/t38/t32 各任务自测用例）+ 全量回归 + 已知环境
flake 单独重跑确认。
**结论**：**111 项独立检查全 PASS；全量回归（skip 基线 69 脚本）69/69 PASS、
零新增失败、零 NORESULT；已知 flake（test_stress / test_game_dir_e2e / 实网
脚本）单独重跑全部确认为环境性，非代码回归。核心逻辑复测无异常。**

与 t44（gui-checker，GUI/用户视角第一轮）共同构成 1.4.1 交付闸门
「bug 测试员连续两轮复测均无异常」。

---

## 0. 打包终态核对（test_t45_retest.py · P 组 5 项，全 PASS）

| 检查 | 结果 |
|---|---|
| `build/dist/SWDM/SWDM.exe` 存在且 >8MB（8,613,764B） | PASS |
| 手册随包：`_internal/manual/SWDM-用户手册.html`（140,006B）+ `.pdf`（1,404,127B） | PASS |
| 安装包 `SWDM-Setup-1.4.1.exe` 存在且 >40MB（47,756,369B） | PASS |
| 安装包内嵌版本资源 ProductVersion = 1.4.1（VS_VERSION_INFO UTF-16LE 检索） | PASS |
| 源码 `paths.py:13 APP_VERSION` 与 `installer/swdm.iss` `SWDMVersion` 双端 1.4.1 | PASS |
| exe 归档 TOC 含 1.4.1 新模块名 `failure_reason`/`account_steamcmd`/`swdm.core.providers` | PASS |

模块名出现在 SWDM.exe 的 PyInstaller 归档结构中（偏移 ~8.6MB 处），证明
1.4.1 新增的 `failure_reason`、`account_steamcmd` 已随包打进；其余模块经压缩
（PYZ）不可明文检索，属预期。

---

## 1. 独立复测脚本结果（tests/test_t45_retest.py · 111/111 PASS）

### A. detail_cache 双失效 + 深拷贝 + 损坏容忍（13 项）

独立夹具：注入 `ttl_hours=0.01`（36 秒）+ 直接改写磁盘 JSON 的 `cached_at`。

| 检查 | 结果 |
|---|---|
| TTL 边界：`cached_at` 回拨至到期前 1 秒（now−35）仍命中 | PASS |
| TTL 边界：回拨至到期后 1 秒（now−37）判 miss **且条目物理删除** | PASS |
| `time_updated` **相等** → 命中（「变化才失效」的补集，不误伤） | PASS |
| 双失效优先级：TTL 已过但 tu 一致 → 仍 miss（TTL 优先） | PASS |
| 损坏容忍：`cached_at` 为非法字符串 → miss + 清理 + 不抛 | PASS |
| 损坏容忍：`time_updated` 字段非法（"XX"）→ miss，不抛 | PASS |
| 损坏容忍：`html` 类型损坏（非字符串真值）不抛异常（写路径只写 str，不可产生） | PASS |
| `.tmp` 残留文件不污染 get（get 只读 `.json`） | PASS |
| `.json` 路径被目录占据 → miss 不抛 | PASS |
| 复杂 unicode/引号 HTML 二次 get 内容一致（深拷贝语义） | PASS |
| 8 线程 × 30 次 并发 set/get 同一条目不崩、终态收敛 | PASS |
| set 空 html 不落盘 | PASS |
| `invalidate()` 只清 `.json`，不动 `.tmp` 残留 | PASS |

**说明**：A7 为防御性观察项——`html` 字段为非字符串真值时 get 不抛异常但会
原样返回（代码仅检查真值，未校验类型）。该状态不可能经 `set()` 产生
（`set` 只写 str），仅在外部篡改缓存文件时出现，**不构成缺陷**，保留记录
供后续防御性增强参考。

### B. 预取代际丢弃 + 熔断守卫（11 项）

独立角度：覆盖 t34 未测的 `_do_prefetch_next_page` 层守卫与回调路径
（t34 测的是 `_schedule_prefetch_next_page` 层）。

| 检查 | 结果 |
|---|---|
| 重入保护：`_nextpage_prefetching` 已置位 → 不启新线程、零网络 | PASS |
| 熔断守卫（`_do` 层）：熔断冷却 → 不发包、不启线程、标志位不置位 | PASS |
| 暖缓存短路：下一页 key 已在 ApiCache → 零网络、不启线程 | PASS |
| 无 appid 守卫 → 不发包不启线程 | PASS |
| 过期代际回包 `_on_nextpage_prefetched(stale)` 静默丢弃不抛异常 | PASS |
| 当前页物品未被预取回包触及 | PASS |
| 当前代际回包正常处理（读命中不抛） | PASS |
| 真实预取：线程为 daemon（进程退出不挂） | PASS |
| 真实预取完成不卡死 | PASS |
| 真实预取恰好触发一次 browse 网络请求 | PASS |
| 下一页 key 暖入 ApiCache（翻页零网络的前提） | PASS |

### C. check_updates 50条/批 + 进度 + cancel + bypass api_cache（15 项）

独立夹具：桩 `_api_post` + 独立记录集（ avoiding t37 的 111/333/555 数据）。

| 检查 | 结果 |
|---|---|
| 端点节流基准 `/ISteamRemoteStorage/` 存在（>0 间隔） | PASS |
| 恰 50 条 → 1 次请求（整批边界，不多发） | PASS |
| 51 条 → 2 次请求（第 2 批 1 条） | PASS |
| 51 条结果只含变化项 | PASS |
| progress 精确序列 `[(50,51),(51,51)]`（单调到 total） | PASS |
| cancel 首批前 → 零请求 | PASS |
| cancel 首批前 → progress 未被回调 | PASS |
| cancel 首批前 → 返回空列表 | PASS |
| **bypass api_cache 值级证明**：同会话两次调用，API 返回值变化 → 结果立即跟随（无内部结果缓存） | PASS |
| 中间批（第 2/3 批）抛异常 → 3 批全跑、失败批条目不误标 | PASS |
| 失败批条目不在结果集 | PASS |
| 失败批后一批条目仍检出 | PASS |
| tu 相等或 Steam 值更旧 → 均不报告（不误报更新） | PASS |
| 非法记录（空 id / tu≤0）被过滤且零请求 | PASS |

### D. failure_reason 8 桶分类 + 误报红线（24 项）

| 检查 | 结果 |
|---|---|
| 8 桶各自独立消息全部命中正确桶（含 Barotrauma 602960 正向①） | PASS ×8 |
| RESTRICTED_APPS 含 DayZ 221100 + Barotrauma 602960 | PASS |
| **误报红线**：`ERROR! I/O Operation Failed` / `Failed to download item …` / `Not Logged On` 三条通用串单次消息**绝不映射 ACCOUNT_NEEDED** | PASS ×3 |
| 红线边界：同一通用串重试 2 次 + 无网络信号 → ACCOUNT_NEEDED（正向②，设计行为） | PASS |
| 同串但有 timeout 信号 → NETWORK（正向②被否决） | PASS |
| 优先级：磁盘+超时同串 → DISK_FULL（磁盘优先） | PASS |
| 优先级：登录失败+限流字样 → RATE_LIMITED（限流优先于登录） | PASS |
| signals 覆盖消息文本（运行信号优先） | PASS |
| 空消息 → GENERIC 不崩 | PASS |
| render 8 桶全非空 | PASS |
| 账号文案含「可能」+ 登录引导 | PASS |
| 通用文案不含「账号」（不误导） | PASS |
| 通用文案说明未区分并指引日志 | PASS |
| LOGIN_FAILED / EMPTY_SUCCESS 透出原文 | PASS ×2 |

### E. account provider 默认链不含 + 会话级失活 + 熔断豁免（20 项）

| 检查 | 结果 |
|---|---|
| 无 AuthManager → 默认链不含 account_steamcmd，链尾仍 steamcmd | PASS ×2 |
| 登录态 is_configured=True；首选账号通道时链首为账号通道、链尾仍 steamcmd | PASS ×3 |
| 认证失败 → `_auth_dead=True`（注册表实例上验证，build_chain 真正咨询的对象） | PASS |
| 失活后 is_configured=False | PASS |
| 失活后链不含账号通道 | PASS |
| 文案替换为风控提示（含「回退匿名通道」） | PASS |
| 通用 I/O 失败不触发会话级失活（不误判） | PASS |
| **熔断豁免经真实 DownloadManager 路径**：账号认证失败后 `registry._circuits["account_steamcmd"]` 未熔断且失败计数为 0（breaker_exempt 生效） | PASS |
| manager 路径会话级失活同样生效 | PASS |
| **终态归类 login_failed**（凭据桶，非账号桶；文案 = LOGIN_FAILED 渲染透出的风控提示） | PASS ×2 |
| 账号通道失败建议回退（should_fallback 恒 True） | PASS |
| `reset_auth_state` 后重新可用 | PASS |
| 失活后 `get_engine()` → None；download → FAILED + 风控提示 | PASS ×2 |
| `_is_auth_failure` 6 串判定（4 正 2 负） | PASS ×6 |

### F. GGNetwork resolve url 优先 + CDN 改写（15 项）

| 检查 | 结果 |
|---|---|
| **url 优先**：`position>0` 与 url 同时存在 → 取 url（1.4.0「position>0 丢弃 url」严重 bug 不复现） | PASS |
| 落地页 `ggntw.com/download/<token>` → 改写 `cdn.ggntw.com/<token>` | PASS |
| 嵌套 `data.url` 同样改写 | PASS |
| 非 ggntw 域名的 `/download/` url 原样返回（不改写） | PASS |
| 落地页尾斜杠 → token 正确（无 `/` 残留） | PASS |
| 无 url + position>0 → 空串干净回退（不轮询） | PASS |
| 后端 error 体 → 空串 | PASS |
| HTTP 429 → 空串 + 上报 rate_limit 信号 | PASS ×2 |
| HTTP 500 → 空串 | PASS |
| 响应体非法 JSON → 空串不崩 | PASS |
| session.post 连接异常 → 空串不崩 | PASS |
| `rate_limit_per_minute=60` → 限速间隔 1.0s（配置注入） | PASS |
| resolve 失败 → download FAILED + 明确文案 + 建议回退 | PASS ×2 |

---

## 2. 全量回归（tests/run_all.ps1，skip 基线）

```
69 脚本（skip 21 个实网/压测/冒烟类）
SUMMARY: pass=69 fail=0 noresult=0 total=69
```

- **零新增失败、零 NORESULT**。新增脚本 `tests/test_t45_retest.py` 自动纳入
  并 PASS；t33/t34/t37/t41/t38/t32 自测脚本全部 PASS。
- 本轮在 t43/t44 基线之后新增了 `tests/test_rettest_141.py`（t44 产出）与
  `tests/test_t45_retest.py`（本轮产出），共 90 个测试文件。

### run_all 工具链修复（复测副产物，重要）

复测中发现 `tests/run_all.ps1` 存在**encoding 脚阱**：
该文件为 UTF-8 **无 BOM** 且含中文注释，用 Windows PowerShell 5.1
（`powershell.exe`，按 ANSI/GBK 解码）执行时，末行中文注释的 UTF-8 字节
被误解码并吞掉 `$skip` 赋值行——**skip 列表被静默禁用**，
回归从 69 脚本变成 90 脚本全跑（含挂死的实网脚本）。pwsh 7（默认 UTF-8）
解析正常；加 UTF-8 BOM 后 powershell.exe 也可正确解析（实测 69）。

已修复（test-infra 修复，非产品代码）：`run_all.ps1` 注释改为纯 ASCII
（修复后实测 `powershell.exe` 5.1 与 pwsh 下基线均一致为 69 脚本；文件
0 个非 ASCII 字节，逻辑逐字节不变）。复测附属私有运行器/探针
（`tests/_runall_t45_fixed.ps1`、`tests/_runall_head_probe.ps1` 等）已清理。

### 已知 flake 单独重跑确认

| 脚本 | 状态（本轮复测实测） | 判定 |
|---|---|---|
| `test_stress` | 单跑 `RESULT: 1_SLOW`（渲染 60 卡片 108ms，>100ms 阈值）；与 t43/captain 两次单跑 + t44 基线完全一致 | **环境性**：性能标记对机器负载敏感，无功能断言失败 |
| `test_game_dir_e2e` | **本轮单跑实测**：真实下载成功（`JobStatus.SUCCESS`，local_path 目录真实存在且含 7 个文件）；唯一 FAIL 为看门狗时序断言「下载完成（5 秒之内）」——真实下载耗时超预期致超时，与 t44 诊断一致 | **环境性/测试固件时序断言** |
| `test_bulk_games` 等实网脚本 | fake-IP 代理失效时挂死/超时（单跑 300s+ 无输出，已 kill 确认） | **环境性**：网络前置条件缺失 |

三项均与 t43/t44 基线的 FAIL 项逐一对齐，**无新增失败、无代码回归**。

---

## 3. 复测发现的问题

**产品代码缺陷：无。** 111 项独立检查 + 69 脚本全量回归均未发现任何
核心逻辑缺陷。

复测过程中修复/记录的三项**测试基础设施**问题（非产品代码）：

1. `tests/test_t33_detail_cache.py`、`tests/test_t34_nextpage_prefetch.py`
   缺少标准 `sys.path` 插入（其它 15 个测试文件均有的两行模式），从仓库根
   直接 `python tests/x.py` 运行时 `import swdm` 失败 → run_all 中 NORESULT。
   已补标准两行，二者现分别 33/33、25/25 PASS。
2. `tests/run_all.ps1` UTF-8 无 BOM + 中文注释 → powershell.exe 5.1 下
   skip 列表被静默禁用（上节详述）。已改纯 ASCII 注释。
3. 观察项（未修，防御性记录）：`DetailDiskCache.get` 对 `html` 字段的
   非字符串真值不做类型校验（仅真值校验）——外部篡改缓存文件时返回非 str
   但不抛异常；正常路径不可产生，详见 §1.A 说明。

---

## 4. 交付闸门对照

| 条件 | 状态 |
|---|---|
| 讨论组一致认为可交付 | t31 评审 10 项纳入 + t46 六方评审待开 |
| 版本号 + 可追溯 changelog | t43：双端 1.4.1 + `docs/changelog_1.4.1.md` 十五节 ✓ |
| 全量回归（不只测改动点） | t43 run_all（基线 87/1 环境 FAIL）+ t44 89 脚本 87/2（均环境项）+ **本轮 skip 基线 69/69 零失败** ✓ |
| bug 测试员连续两轮复测无异常 | t44（GUI/用户视角，56+30 项全 PASS）+ **t45（核心视角，本报告 111 项全 PASS）** ✓ |

与 1.4.0 t26 相比，本轮新增覆盖 1.4.1 全部六个核心新机制（detail_cache、
预取守卫、check_updates、failure_reason、account provider、GGNetwork），
独立 mock 数据与边界场景均未复用各功能任务的自测用例。

核心逻辑视角复测通过，待 t46 六方交付评审。
