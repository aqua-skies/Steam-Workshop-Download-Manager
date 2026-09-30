# SWDM 1.4.1 C3 变更记录：私人账户 provider（steamcmd `+login`）

> **English summary**: 1.4.1 C3 adds an explicit, risk-isolated private-account download channel
> (`account_steamcmd`). It logs the user's **own** Steam account into steamcmd to download content
> **that account is entitled to** — the single compliant alternative to the "report-confirmed
> blocker" (there is no legitimate way to bypass Steam's license checks for content you don't
> own). The public account-pool interface stays **reserved and disabled**; this is a deliberate
> compliance layering decision. Four risk controls: ① credentials never enter logs (explicit
> redaction of steamcmd output), ② Steam Guard first-login has a code entry point marked
> "only once", ③ account failures are decoupled from the circuit breaker (they can never melt
> the anonymous steamcmd tail), ④ credential storage is keyring-first with a local obfuscated
> fallback and an explicit "stored locally, only for your own use" UI disclosure. Verified by
> 72 new checks; full details below in Chinese.

> 任务：t38（search-fixer，attempt 3 `ac30a39d`）· 2026-09-29
> 评审文档：`docs/feature_review_1.4.1.md`（五方零反对，C3 纳入 5/5）

---

## 一、合规定位（避免日后误读）

**必须先说清的一件事：本通道 ≠ 公有账户池。**

t16/t31 讨论组确认：不存在合规的"绕过正版限制"方案——Valve 在三层设防
（license 检查 / file_url 签名 / depot key）。此前评估过的"公有账户池"
（服务端共享账号替用户下载）被明确列为**保留接口、不启用**：它把账号风险
集中到服务提供方，且实质是代用户访问未授权内容，合规定位为 🔴。

C3 落地的是**合规分层的低风险端**：

| 层级 | 形态 | 定位 | 状态 |
|---|---|---|---|
| 公有账户池 | 服务端共享账号 | 🔴 保留接口不启用 | 不实现 |
| **私人账户（C3）** | **用户自己的账号 + 自己有权的内容** | 🟢 唯一合规方案 | **1.4.1 实现** |
| 匿名通道 | steamcmd `+login anonymous` | 🟢 默认链 | 既有 |

**用户体感**：匿名下载失败、被枚举为「ACCOUNT_NEEDED」（受限应用）时，
C2 的提示引导用户去「设置 → 账号」登录自己的账号；登录后该通道自动加入
回退链（priority 90，位于匿名 steamcmd 兜底之前），重试即用本人账号下载
自己拥有的内容。**匿名用户感知不到任何变化**（默认链不含此通道）。

---

## 二、实现

### 2.1 provider 抽象层扩展

- `swdm/core/providers/base.py`：`ProviderMeta` 新增两个标记
  - `supports_account: bool = False` — 私人账号通道标记（UI/注册表层可识别）
  - `breaker_exempt: bool = False` — 失败不计熔断（仅私人账号通道为 True）
- `swdm/core/providers/account_steamcmd.py`（新）：`AccountSteamCMDProvider`
  - 元数据：`name="account_steamcmd"`，`terminal=False`，`anonymous_ok=False`，
    `priority=90`，`supports_account=True`，`breaker_exempt=True`
  - `is_configured()`：仅当 AuthManager 处于登录态时为 True —— **匿名态自动
    被 `build_chain` 跳过，默认链不含（硬性断言见 §四）**
  - 登录失败一次后会话级失活（`_auth_dead`）：本会话不再尝试登录，避免每个
    任务白等一次登录超时、并避免触发 Steam 登录服务器限流；用户改凭据时
    `Services.refresh_engine → reset_auth_state()` 重开
  - `should_fallback()` 恒为 True — 账号问题永远不阻塞下载，自动回退匿名兜底

### 2.2 风险隔离：兜底引擎恒匿名（架构变化）

1.4.0 时共享引擎在登录态会整体切换成账号引擎（`services.refresh_engine`
直接下发凭据）。1.4.1 起改为**结构性隔离**：

- 共享/兜底 `SteamCMDEngine` **恒为匿名**（`services.py`）；
- 账号凭据只存在于 `AccountSteamCMDProvider` 构造的**专属引擎实例**；
- 两个引擎共用 `DownloadManager._engine_lock` 串行锁（两个 steamcmd 进程
  永不并发），账号路径经 `_run_steamcmd(engine=…)` 路由。

效果：账号配额/凭据问题**在结构上**不可能熔断或阻塞匿名兜底下载
（t31 风控③ 的最强形式）。

### 2.3 配置

`DEFAULT_CONFIG["download"]["providers"]["account_steamcmd"] = {"enabled": True}`。
匿名态由 `is_configured()` 自动跳过；用户可设 `enabled=False` 显式关闭。

---

## 三、四条风控的落地

### ① 账号不得进日志

- `SteamCMDEngine._redact_secrets()`：`_run` 的每行输出在 `log.debug` 与
  `on_line` 回调**之前**过滤用户名/密码/验证码（替换为 `***`）；匿名引擎
  无密钥，零开销。下游解析用的正则（`Logged-in OK` / `Login Failure` /
  `Invalid Password`）均不依赖账号名，过滤不影响解析。
- `AuthManager.login_user` 的日志行不再包含用户名（1.4.0 遗留泄漏）。
- `test_login` 成功返回串由「用户 {username}登录成功」改为「账号登录成功」
  （该串会进诊断日志/UI）。
- 测试：注入含账号名/密码的输出行 → 断言日志环形缓冲、`on_line` 回调、
  `test_login` 返回串中均无明文凭据。

### ② Steam Guard 首登入口

- 设置页「测试登录」失败且消息含 Steam Guard 时，弹出验证码输入框
  （`QInputDialog.getText`，与既有测试打补丁协议一致），文案明确
  **"仅需一次"**：本机验证成功后 steamcmd 缓存 sentry，之后免验证码。
- 输入后自动保存并立即重测一次（复用已存密码）。
- 下载路径的登录失败文案同样提示"验证码仅首登需要一次"。

### ③ 账号失败与通道熔断解耦

- `ProviderMeta.breaker_exempt`：`account_steamcmd` 失败**不计入熔断器**
  （`downloader._run_channel_chain` 的熔断反馈新增豁免分支）。
- 叠加会话级失活：一次登录失败后本会话跳过该通道（而非熔断冷却 60s）。
- 结构性保证：兜底 steamcmd 恒匿名 + 恒 terminal 豁免 → 账号问题不可能
  让链变空、不可能熔断兜底。
- 测试：账号连续失败 3 次后断言账号通道未熔断、链自动回退匿名兜底、
  且重试下载仍成功。

### ④ 凭据本地存储与 api_key 同等对待

- 沿用 `AuthManager`：keyring（系统凭据库）优先 + 本地 base64 混淆回退
  （1.4.0 已有）；**密码不进 config.json、不进 auth.json**（后者只存
  `has_password` 标志）。
- 设置页账号分组新增常驻明示：
  「🔒 账号仅本地存储、仅本人使用：密码经系统凭据库（keyring）加密，
  不上传、不进日志；匿名模式下不收集任何账号信息。」
- 测试：`auth.json` 无明文密码、回退 `.cred` 非明文、ModRecord 导出字段
  无任何凭据键。

---

## 四、验证

`tests/test_account_provider.py`（**72 项 ALL PASS**）：

| 组 | 内容 |
|---|---|
| 元数据 | 注册表含 account_steamcmd；supports_account/terminal/breaker_exempt/anonymous_ok 标记；兜底 steamcmd 恒 `supports_account=False`、恒 terminal |
| 默认链不含（硬性） | 匿名态 `build_chain` 对全部首选组合均不含 account_steamcmd；链尾恒为 steamcmd；`list_channels` 匿名态标 NO_KEY |
| 登录态链 | 首选 account_steamcmd 时链首即账号通道；首选其他通道时按 priority 90 自然扩展进链、位于匿名兜底之前 |
| 日志安全（①） | `_redact_secrets` 三类密钥替换；`on_line` 端到端脱敏；日志缓冲无明文；`login_user` 日志无账号名 |
| 导出安全（④） | auth.json 无明文密码；`.cred` 非明文；ModRecord 导出无凭据字段 |
| 熔断解耦（③） | 3 次账号失败不熔断、链回退成功、会话级失活、`reset_auth_state` 重开 |
| 引擎隔离 | 专属引擎携带账号且 anonymous=False；install_dir 沿用共享引擎；凭据变化自动重建；串行锁路径用专属引擎而非共享引擎 |
| 回退安全 | 失败/取消一律 `should_fallback=True` |
| Guard（②） | 验证码输入框与提示；隐私明示文案；匿名态/登录态登录测试工厂各自正确；Guard 失败触发验证码保存+重测；非 Guard 失败不触发 |
| 零行为变化 | 匿名默认链 `== [steamcmd]` |

其他关键回归：`test_providers` / `test_throttle` / `test_download_fixes` /
`test_rettest_140` / `test_t26_retest` / `test_failure_reason` /
`test_t33` / `test_t34` / `test_gui_sweep` / `test_all_buttons` /
`test_cross_features` / `test_batch3` / `test_b3_clipboard` / `test_139_merge`
全部 ALL PASS。全量 `run_all` 结果见本轮交接账本。

---

## 五、已知限制与后续

- **每任务一次登录**：steamcmd 每次调用都 `+login`（账号登录开销 5-15s）。
  批量队列会对账号做 N 次登录。成功登录后 steamcmd 本地缓存 sentry，
  后续无需验证码。批量场景的"持久会话"（单进程多物品）留待后续优化。
- **凭据变更需重测**：改密码后首次下载会经历一次失败—失活—改凭据重开的
  过渡（已有自动兜底，用户不阻塞）。
- **UI 未加"使用账号通道"复选框**：按讨论组结论，登录态自动扩展进链即
  "低风险层自然扩展"，不新增控件；如需关闭，设
  `config.download.providers.account_steamcmd.enabled=false`。
- 此通道的 `supports_account` 标记为公有账户池"保留接口不启用"的合规分层
  锚点：后续若再评估公有池，必须先经新一轮讨论组重审合规定位
  （t31 结论：🔴，除非业务模型改变否则不启用）。
