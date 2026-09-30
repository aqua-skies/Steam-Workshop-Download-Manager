# SWDM 1.4.2「建议纳入池」实现预研（impl research）

日期 2026-09-30 · 职责：方案预研（细化技术方案与工作量，**不写代码**）。
输入：docs/plan_1.4.2_draft.md（建议纳入 10 项）、docs/core_audit_1.4.2.md、docs/ux_audit_1.4.2.md、
docs/competitor_research_1.4.2.md，以及**已落地的竞品源码精读 docs/research/sefrawe_backup_verify.md**
（该文件正是 plan 草案议程 C 要求的「S1/S2 实现前派源码精读 subagent」产物，robocopy 参数细节与
acf 解析字段细节已备齐，本预研直接引用，不重复调研）。
约束达成：全程只读分析 swdm/ 与 tests/，未修改任何代码；仅新增本文件（docs/research/ 下）。

工作量单位：人时（1 人日 = 8 人时）。行号均经逐行核实（基于当前 1.4.1 代码树）。

---

## 0. 预研结论速览

| 项 | 类别 | 涉及核心文件 | 改动性质 | 工时 | 建议时序 |
|---|---|---|---|---|---|
| P0-1 | 核心修复 | throttle.py / downloader.py | 纯逻辑 clamp + 防御 | 1.0 h | 第 1 批 |
| P0-2 | 核心修复 | downloader.py | job→provider 映射 | 3.0 h | 第 1 批 |
| P0-3 | 核心修复 | settings_tab.py / debug_tab.py / workers.py | 独立引擎工厂 | 2.0 h | 第 1 批 |
| P0-4 | 核心修复 | throttle.py / downloader.py | set_max 同步 | 2.0 h | 第 1 批 |
| U1 | UX | workshop_tab.py | 仿库页空态 | 4.0 h | 第 2 批（与 P0 并行） |
| U2 | UX | downloads_tab.py | 行过滤 + 确认 | 1.5 h | 第 2 批 |
| U3 | UX | library_tab.py | 接通已有 cancel | 3.0 h | 第 2 批 |
| U4 | UX | workshop_tab.py | 清空勾选 | 1.0 h | 第 2 批 |
| S1 | 竞品新增 | update_backup.py(新) / mod_library.py / downloader.py / settings_tab.py / library_tab.py | 旁路备份管线 | 17 h | 第 3 批（S2 之后） |
| S2 | 竞品新增 | integrity.py(新) / integrity_dialog.py(新) / library_tab.py | 只读差集报告 | 12.5 h | 第 3 批（先于 S1） |

核心 P0×4 ≈ 8 h ≈ 1 人日（与草案「1-1.5 人日」一致，含单测）；
UX P0×4 ≈ 9.5 h ≈ 1.2 人日（与草案 ≈1.3 一致）；
S1 ≈ 2.1 人日、S2 ≈ 1.6 人日（草案「中 / 中低」，S2 若把修复动作二阶段化可压到 ≈1 人日）。
合计 ≈ 5.9 人日——略超草案 4-5.5 人日上限，超出来源是 S1 的一键恢复 UI（4 h），
讨论组可将「自动备份+保留策略+配置 UI」与「一键恢复」拆两期交付（压到 ≈4.6 人日）。

时序（与草案 §四一致，细化依赖）：
```
第 1 批  P0-1/2/3/4（核心修复，稳定性地基；两两无冲突可并行）
   ‖（并行）
第 2 批  U1-U4（纯 GUI，不碰 core；U3 依赖 steam_api 已有 cancel 回调，零核心改动）
   ↓
第 3 批  S2 账实核验（只读复用库数据，无状态机侵入）→ S1 更新前备份（下载管线插入点 + 新模块）
   ↓
收尾    run_all 全量回归 + 手册再版（E3 随 U2、E5/E14 随 U1 落地同步修订）+ 版本号 bump + changelog
```

---

## 1. 核心 P0×4

### P0-1 退避 level clamp 防溢出 → 防队列死锁

**涉及文件:行号**
- swdm/core/throttle.py:59-71（`Backoff.__init__`，需加 `_max_level`）
- swdm/core/throttle.py:86-87（`_delay_unlocked`，clamp 落点）
- swdm/core/downloader.py:765-769（`_exec_job` 收尾段，`record_failure` 未包 try 的击穿点，审计点名 767 行）
- swdm/core/downloader.py:153-178（`_on_throttle_signal`，引擎输出线程的第二处未防御 `record_failure`，顺带加固）

**问题链（已实机验证）**：`base * factor ** level` 先于 `min(cap, ...)` 求值 → 连续约 1024 次失败
（夜间挂机+死网可达：auto_retry 与队列循环每轮贡献 2 次）时 `2.0**1024` 抛 `OverflowError` →
downloader.py:767 击穿 `_exec_job` 工作线程 → job 卡在 `_active` → `_run_loop` 的
`while len(self._active) >= self._concurrency.current`（downloader.py:445）永久挂起 → 队列死锁。

**改动草图**
```python
# throttle.py __init__（import math）
self._max_level = (
    int(math.ceil(math.log(self.cap / self.base) / math.log(self.factor))) + 1
    if (self.base > 0 and self.factor > 1) else 2**31
)   # cap >= base 由构造保证，log 恒非负；factor<=1 时指数永不溢出，哨兵即可

def _delay_unlocked(self, level: int) -> float:
    if self.base <= 0:
        return 0.0
    lvl = min(max(0, int(level)), self._max_level)
    if self.factor <= 1:
        return min(self.cap, self.base)
    return min(self.cap, self.base * (self.factor ** lvl))
```
```python
# downloader.py:765-769（失败记账整体包防御——任何记账异常都不能杀工作线程）
if needs_backoff:
    try:
        self._backoff.record_failure(result.message or "failed")
        cur = self._concurrency.on_failure(result.message or "failed")
        log.info("失败退避：并发上限 -> %d（退避等级 %d）", cur, self._backoff.level)
    except Exception:  # noqa: BLE001
        log.exception("退避记账异常（忽略，不影响下载状态机）%s", job.id)
```
同构加固 `_on_throttle_signal` 内的 record_failure/on_failure（downloader.py:164-170）。

**依赖**：无。**与其他项零耦合**，可作为 1.4.2 第一个合入项。

**风险**：极低。默认参数（base=2, factor=2, cap=120）下 `_max_level≈7`，level≤7 的 delay 值与
旧实现逐位相同——clamp 只在旧实现会溢出的区间生效，test_throttle 7a/7g/7h 语义零变化。
`level_delay`（downloader.py:185 `_throttle_wait`）与 `record_failure` 共用同一 clamp 路径，一并覆盖。

**工作量**：clamp 本体 0.4 h；两处防御 + 单测（`record_failure` 循环 20000 次不抛 +
"record_failure 抛异常时 job 仍达终态且 `_active` 被清理"死锁回归）0.6 h → **1.0 h**（草案 S）。

**建议时序**：第 1 批最先；合入后立即跑 test_throttle 全量。

---

### P0-2 cancel() 按 job→实际 provider 路由

**涉及文件:行号**
- swdm/core/downloader.py:285-330（`cancel`，305 行 `self.engine.cancel()` 恒指共享匿名引擎）
- swdm/core/downloader.py:484-511（`_run_provider`，映射写入点）
- swdm/core/downloader.py:612-633（`_retire_cancelled`）、793-802（`_exec_job` 终态登记段，两处映射清理点）
- swdm/core/downloader.py:98-151（`__init__`，新增 `_job_provider` 字段）
- 旁证：swdm/core/providers/account_steamcmd.py:119-149（`get_engine` 造专属引擎）、207-213（`cancel` 已存在但从未被 manager 调用）

**问题**：C3 账号通道在专属引擎（account_steamcmd.py:135）上跑 `workshop_download_item` 时，
`cancel()` 仍 terminate 共享匿名引擎的 `_proc`（可能为 None 或无关进程）——账号 steamcmd 子进程
不被中断、继续下载落盘，job 已标 CANCELLED；取消契约失效。

**改动草图**
```python
# __init__
self._job_provider: dict[str, object] = {}  # job_id → 正在执行的 provider（取消路由）

# _run_provider 入口（provider 真正执行前；链内回退时覆盖 = 始终是"当前 provider"）
def _run_provider(self, provider, job, install_dir, smoother):
    with self._lock:
        self._job_provider[job.id] = provider
    ...  # 其余不变

# cancel()（保持现有 _lock 全程持有与 A-P1 时序不变）
prov = self._job_provider.get(job_id)
try:
    if prov is not None and hasattr(prov, "cancel"):
        prov.cancel()            # steamcmd→共享引擎（与今天等价）；account→专属账号引擎（修复）
    else:
        self.engine.cancel()      # 映射缺失（等待期/未入链）回退旧行为
except Exception:  # noqa: BLE001
    log.debug("通道取消异常（忽略，强制标记）", exc_info=True)

# 清理（两处，均在 self._lock 内）：_retire_cancelled 与 _exec_job 终态登记段
self._job_provider.pop(job.id, None)
```

**路由正确性**（按 provider 类型核验）：
- `steamcmd`（链尾）：`SteamCMDProvider.cancel()`（providers/steamcmd.py:81-86）→ 共享 `engine.cancel()`，与现有行为逐字一致。
- `account_steamcmd`：`AccountSteamCMDProvider.cancel()` → `self._acct_engine.cancel()`——正是实际执行下载的引擎对象（`get_engine` 缓存按凭据签名复用），**这是本项的唯一行为变更**。
- `cdn` / `ggnetwork`（HTTP）：`job._stop.set()` 已在 http_download chunk 循环（base.py:211）生效；`provider.cancel()` 分别是空实现 / `_stopping` 死状态（P2-7），调用无害。

**依赖**：无新依赖；须与 P0-3 一起回归账号通道下载（两者共同保证"取消打中正确引擎"）。

**风险**：
- 锁序：`cancel()` 持 `_lock` 调 `provider.cancel()` → `engine._cancel_flag.set()` + `_proc_lock`；
  引擎侧不存在 `_proc_lock` → manager `_lock` 的反向获取（throttle 回调在 `_proc_lock` 外触发），
  无死锁。映射读写都在 `_lock` 内，与 A-P1 的 `_cancelling` 时序天然串行。
- 映射泄露：`_exec_job` 异常路径（如 `_throttle_wait` 后的链路抛出）目前无 finally——
  两处清理点覆盖正常与取消收尾；对"worker 线程意外死亡"场景映射残留仅占内存（job 不再被调度），
  不影响正确性。如需绝对兜底可在 `_run_loop` 派发新 job 前清孤儿键（可选，不进 1.4.2 首版）。

**工作量**：映射字段 + 写入/清理 4 点 + cancel 分支 1.5 h；单测（伪 provider 链记录 cancel 落点 +
账号引擎路由断言 + 映射清理断言）1.0 h；test_ap1_cancel_race 16 项复跑对齐 0.5 h → **3.0 h**（草案 M）。

**建议时序**：第 1 批；与 P0-3 同周合入并联合回归账号通道取消。

---

### P0-3 匿名态「测试登录」走独立引擎

**涉及文件:行号**
- swdm/gui/settings_tab.py:425-444（`_login_engine_factory`：431-432 匿名分支 `return self.svc.engine` 直接复用共享引擎 ← 病根）
- swdm/gui/settings_tab.py:446-452（`_test_login` → LoginWorker）
- swdm/gui/workers.py:247-263（`LoginWorker`，工厂模式已就绪，无需改）
- swdm/gui/debug_tab.py:157-188（`_run_diagnostics`：178 行 `self.svc.engine.test_login()` **在 GUI 线程同步调共享引擎**——同一竞态的第二调用点）
- 竞态机制：swdm/core/steamcmd_engine.py:241-306（`_run`：267-269 覆盖 `self._proc`、269 `self._cancel_flag.clear()` 解除下载的挂起取消、261-263 启动参数污染）

**问题**：匿名态点「测试登录」时，`test_login` → `_run` 直接在共享引擎上写 `_proc`（下载
`cancel()` 会 terminate 错进程）、`clear()` 掉挂起的取消（进行中的下载从此无法取消）、
与下载流量交叉竞争 `_activity`。

**改动草图**（遵守硬约束：复用现有模式，**不新造第二条引擎管理路径**——现场造独立引擎正是
`AccountSteamCMDProvider.get_engine`（account_steamcmd.py:135-145）与现有登录态分支
（settings_tab.py:433-444）已确立的模式，此处把匿名分支对齐到同一模式）
```python
# settings_tab.py _login_engine_factory
def _login_engine_factory(self):
    """登录测试引擎：匿名与登录态均现场构造、测完即弃。

    复用共享引擎会在 _run 中覆盖 _proc / clear 挂起的取消（steamcmd_engine.py:267-269），
    与并发下载互污染；独立实例零共享状态。
    """
    from swdm.core.steamcmd_engine import SteamCMDEngine
    base = self.svc.engine
    if self.auth.is_anonymous():
        return SteamCMDEngine(
            exe_path=getattr(base, "exe_path", "") or "",
            install_dir=getattr(base, "install_dir", "") or "",
            anonymous=True,
            validate=bool(getattr(base, "validate", False)),
        )
    user, pw, guard = self.auth.get_credentials()
    return SteamCMDEngine(... 现有账号分支不变 ...)
```
```python
# debug_tab.py _run_diagnostics（同一工厂，消除第二调用点）
ok2, msg2 = build_login_test_engine(self.svc).test_login()   # workers.py 提供模块级工厂
```
把 settings_tab 的工厂逻辑抽成 `swdm/gui/workers.py` 模块函数 `build_login_test_engine(svc)`
（与 LoginWorker 同邻），settings_tab 与 debug_tab 共用——一个工厂、两个调用点，零第二条路径。
`exe_path` 在 `Services.refresh_engine`（services.py:50）每次保存即刷新，新引擎总能拿到当前配置。
debug_tab 的 GUI 线程同步阻塞是既有行为（手动触发、罕见），本项只修竞态不修阻塞；
如顺手改为 LoginWorker 异步属可选增量（0.5 h，建议同样并入以消除主线程冻结）。

**依赖**：无；`refresh_engine` 已保证 base 字段最新。

**风险**：低。匿名测试登录的 steamcmd 进程会与下载的 steamcmd 并发存在片刻——匿名
`+login anonymous +quit` 是轻量只读运行（不写 acf、不占 content 目录、无账号会话争抢），
与 C3 设计_deps"两个 steamcmd 进程永不并发"（downloader.py:460 注释，指下载侧 `_engine_lock`）
不冲突。替代方案（串行锁排队）会让测试登录排在分钟级下载之后，且要伸手到 manager 私有
`_engine_lock`，体感与分层都更差——讨论组已给二选一硬约束，本预研选独立引擎。

**工作量**：工厂抽取 + 两调用点 1.0 h；单测（匿名态测试登录不动共享引擎 `_proc`/`_cancel_flag`；
并发下载中点测试登录后下载仍可被 cancel）1.0 h → **2.0 h**（草案 M）。

**建议时序**：第 1 批；须回归 test_engine_concurrency、test_account_provider、设置页 GUI 断言。

---

### P0-4 AdaptiveConcurrency.set_max 与 refresh_engine 同步

**涉及文件:行号**
- swdm/core/throttle.py:118-135（`AdaptiveConcurrency.__init__`：125 行 `self._max` 构造时固化）
- swdm/core/throttle.py:137-168（`max_concurrent` 只读 property / `on_success` 161 行以 `_max` 为天花板）
- swdm/core/downloader.py:98-121（`__init__`：113 `self.max_concurrent`、119-121 `AdaptiveConcurrency(self.max_concurrent)`）
- swdm/core/downloader.py:445（`_run_loop` 调度闸门读 `self._concurrency.current`）、424/781（日志读 `max_concurrent`）
- swdm/gui/services.py:58-60（`refresh_engine` 赋值 `downloader.max_concurrent`——**代码不变，赋值从此真正生效**）
- tests/test_t44_retest_gui.py:233-302（B1b/B3a/B3c **钉死当前 bug 的特征测试，须翻转**）

**问题**：`_max` 构造时固化；`refresh_engine` 只改 `downloader.max_concurrent`（普通属性），
调度闸门 `_concurrency.current` 的天花板恒为旧值——「最大并发下载」调大永不生效、调低也不立即降，
配置静默失败。test_t44 的 B3a「调低后 `_concurrency._max` 仍为 5」正是该 bug 的特征化断言。

**改动草图**
```python
# throttle.py AdaptiveConcurrency 新增
def set_max(self, max_concurrent: int) -> None:
    """运行时调整并发上限（设置页保存后立即生效）。

    调低：current 立即钳到新上限，_run_loop 闸门（0.5s 轮询）下一刻停止新派发；
    调高：current 保持不变，靠后续 on_success 逐级回升（避免突然放开并发冲击）。
    """
    with self._lock:
        self._max = max(1, int(max_concurrent))
        self._min = min(self._min, self._max)
        if self._current > self._max:
            self._current = self._max
```
```python
# downloader.py：max_concurrent 由普通属性改为 property（对外 API 不变）
# __init__ 内：先建 self._concurrency（119-121 上移），再 self._max_concurrent = max(1, max_concurrent)
# 直接写 backing field 绕过 setter——避免构造时把调用方传入的 concurrency 实例的 _max 覆盖
@property
def max_concurrent(self) -> int:
    return self._max_concurrent

@max_concurrent.setter
def max_concurrent(self, value: int) -> None:
    self._max_concurrent = max(1, int(value))
    self._concurrency.set_max(self._max_concurrent)   # services.py:58 的赋值由此同步到闸门
```
services.py 无需改码（既有赋值即触发 setter）；`_run_loop` 闸门、7a 回升逻辑、日志全不改。
硬约束"set_max() 不破坏现有并发断言"达成：7a/7g/7h 测试中从不调 set_max，行为逐位不变。

**依赖**：无。

**风险**：
- t44 特征测试翻转（B3a/B3c 改为断言"调低后 `_max` 同步为 1 且 `current ≤ 1`"，
  B1b 保留）——这是**有意的契约变更**，须在 t44 文件头注明"1.4.2 P0-4 行为翻转"。
- 调高语义（保持 current 让 on_success 爬升）是预研建议：与 pause_all「进行中的跑完」
  同一保守哲学；若讨论组要求调高立即跳满，`set_max` 加一行 `self._current = self._max` 即可，
  二者都自洽，选哪个由讨论组定（本预研推荐爬升）。

**工作量**：set_max + property + `__init__` 重排 0.8 h；t44 翻转 + 新测（调高铁轨不突变 +
on_success 爬满 + refresh_engine 端到端生效）+ test_throttle 7a 复跑 1.2 h → **2.0 h**（草案 S）。

**建议时序**：第 1 批；合入后跑 test_throttle + test_t44_retest_gui + test_core_sweep。

---

## 2. 竞品 S1 / S2

> 设计参考：docs/research/sefrawe_backup_verify.md（竞品 backupManager.py / localScanner.py /
> modVerifier.py 精读）。关键可复用参数已在该文件钉死，本节直接引用并在"SWDM 化"处注明差异。

### S1 更新前自动备份（robocopy）+ 一键恢复

**涉及文件:行号**
- 新增 swdm/core/update_backup.py（备份/恢复/保留策略引擎，纯逻辑、runner 可注入）
- swdm/core/mod_library.py:26-64（`_SCHEMA` 加 `backups` 表——**复用 library.db 单库，不新建数据库文件**）
- swdm/core/downloader.py:662-682（`_exec_job` 插入点：`ensure_partial`（665-674）之后、`_run_channel_chain`（682）之前）
- swdm/core/config.py:19-99（`DEFAULT_CONFIG` 新增 `backup` 节）
- swdm/gui/settings_tab.py（新增「更新前备份」分组：开关 + 每mod份数 + 全局配额）
- swdm/gui/library_tab.py:486-497（右键菜单新增「⧉ 备份与恢复…」入口）
- DB 读写复用 mod_library 既有 `_conn()` 风格（与 P2-5 技术债同风格，不恶化）

**插入点论证**（硬约束：robocopy 在现有下载管线的插入点，纯旁路增量）：
- 候选 A（UI 入队时批量备份，竞品 `_BackupPhaseWorker` 模式）：**否决**——SWDM 队列入队即自动
  开始派发（downloader.py:449 `_run_loop` 无 UI 门控），UI 侧备份阶段会与已开始的下载 race，
  只适用于竞品"命令手粘、下载由人触发"的架构。
- 候选 B（provider 链内）：**否决**——备份与传输通道无关，属调度层关注点。
- **选定：`_exec_job` worker 线程内钩子**——`install_dir` 已解析（656-660）、内容目录确定，
  链路执行（682）之前完成备份，是 SWDM 自动管线中唯一无竞态的插入点；串行锁下该 job 的
  备份耗时计入其墙钟（用 `job.message = "更新前备份中…"` + `_fire_progress` 给 UI 反馈）。

**改动草图**
```python
# downloader.py _exec_job（ensure_partial 之后、smoother/链路之前）
# S1：更新前备份（库中已有且盘上有内容 → 视为更新，先备份旧版；失败永不阻断下载）
try:
    self._maybe_backup_update(job, install_dir)
except Exception:  # noqa: BLE001
    log.exception("更新前备份失败（不阻断下载）%s", job.id)

def _maybe_backup_update(self, job, install_dir):
    if not get_config().get("backup", "enabled", True):
        return
    rec = self.library.get(job.id)
    if rec is None or not rec.installed:
        return                                    # 新下载：无旧版可备
    content = os.path.join(install_dir or self.engine.install_dir,
                           "steamapps", "workshop", "content", str(job.appid), str(job.id))
    if not os.path.isdir(content) or _dir_empty(content):
        return
    job.message = "更新前备份中…"
    self._fire_progress(job)
    self._backup_mgr.backup_mod(job.appid, job.id, content)   # 失败内部已捕获或上抛被钩子吞掉
```
```python
# update_backup.py 核心（参数照抄竞品精读结论）
cmd = ["robocopy", src, dst, "/E", "/MT", "/XJ", "/R:2", "/W:2", "/NFL", "/NDL", "/NP"]
# /XJ 防链接成环；/R:2 /W:2 必须显式掐掉 robocopy 默认 100 万次×30s 重试
# 退出码：rc < 8 全部成功（rc=1 = "有文件被拷贝"，最常见正常成功码）——必须有测试钉死
# 删除入口 _safe_rmtree：realpath 落在备份根内 + os.path.islink/isjunction 双查
# 保留策略（新备份落盘后清腾）：每 mod 最新 N 份（钉住豁免）→ 全局配额 GB→B 只换算一次（0=不限）
# 恢复五步法：steamcmd 运行中拒绝 → 强制备份当前版 → 同盘 rename 挪走 → robocopy 回写 → 失败回退/成功删旧
```
备份根目录：`<DATA_DIR>/backups/<appid>/<item_id>/<item_id>_v<version>_<时间戳>/`
（不进 steamcmd 树——steamcmd 自更新/重装会误删；DATA_DIR 与库同卷时同盘拷贝快。
`version` 取 `rec.time_updated`，无则 0）。
非 Windows 回退 `shutil.copytree`（开发/CI 可测）。
SWDM 与竞品的架构差异：竞品"备份失败剔除下载"（保护原内容，其下载由人触发）；
SWDM 自动哲学下取**失败不阻断下载**（plan 草案硬约束），备份失败仅记日志 + 下次核验（S2）兜底。

**依赖**：config schema 变更（`_init_db` 既有 `_MIGRATIONS` 先例，加 `CREATE TABLE IF NOT EXISTS
backups` 无迁移风险）；S2 的核验页可把"备份"作为修复建议入口（S2 先行时不强依赖 S1）。

**风险**：
- robocopy rc 判定坑（rc<8、rc=1 成功）：单测钉死，mock runner 注入。
- 大 mod（GB 级）备份延长 job 墙钟：UI 文案反馈 + 默认开（可关）+ 配额兜底；
  讨论组须确认默认开（草案初判默认开）。
- 磁盘占用：默认每 mod 3 份 + 全局 10 GB（对齐竞品 `backup_keep_per_mod=3`，
  配额取 10 GB 而非竞品 100 GB——SWDM 数据目录在 `%APPDATA%`，保守）。
- backups 表入 library.db 是预研建议（避免第二数据库文件 + 第二套连接），
  若讨论组倾向独立 `backups.db` 或旁车 JSON 索引，核心模块零改动可切换。

**工作量**：core 引擎（robocopy/保留策略/R4 保险丝/恢复五步法）5.0 h；downloader 钩子 1.0 h；
config schema + 设置页 UI 2.0 h；库页右键「备份与恢复」对话框（版本列表 + 恢复确认）4.0 h；
单测（rc 判定、保留策略、保险丝、恢复回退、钩子不阻断）5.0 h → **17 h ≈ 2.1 人日**（草案"中"）。
若拆期：自动备份+保留策略+配置（10 h）先交付，一键恢复（7 h）快速跟进 → 首期压到 ≈1.3 人日。

**建议时序**：第 3 批（S2 之后——S2 用现有库先建信任，S1 再动下载管线与库 schema）。

---

### S2 账实核验（三差集报告）

**涉及文件:行号**
- 新增 swdm/core/integrity.py（acf 解析 + 三差集，纯函数、只读）
- 新增 swdm/gui/integrity_dialog.py（报告对话框：分桶计数 + 明细表 + 行内修复入口）
- swdm/gui/library_tab.py:159-182（底部操作栏新增「🧾 账实核验」按钮，紧邻「🔍 检查更新」）
- 复用：swdm/core/mod_library.py:247-250（`all()`）、:175-204（`upsert`，仅修复动作用）、
  swdm/core/game_dirs.py:25-50（`game_content_root` / `configured_game_dirs`）、
  swdm/core/paths.py:38（`LIBRARY_DIR`）、swdm/core/downloader.py:839-871（`_register_to_library`
  的 WorkshopItem 重建模式，修复动作「重新下载」复用 library_tab.py:445-463 的一键入队模式）
- vdf 依赖：requirements.txt:4 已声明 `vdf>=3.4`、swdm.spec:31/51 已收 hiddenimports——
  **零新增依赖、零打包成本**（注：vdf 当前在 swdm/ 内无 import，属已声明未用；本项首次启用）

**改动草图**
```python
# integrity.py（引用竞品精读的 acf 字段口径）
def parse_acf(path) -> dict[str, AcfItem]:
    # vdf.loads(open(path, encoding="utf-8-sig"))  ← 必须吃 BOM
    # 只采信 WorkshopItemsInstalled.<id>.{size, timeupdated, manifest}（str 存 manifest，防 u64 溢 SQLite）
    # 顶层字段与 WorkshopItemDetails 整块忽略（latest_* 是 steamcmd 上次联网缓存，非事实源）
    # 质量谓词：timeupdated ≤ 0 或 manifest ∈ {"", "-1"} → interrupted（疑似下载中断，不入账不报警）

def locate_acf(install_root, appid) -> str | None:
    # 三层口径容错：<root>/steamapps/workshop/appworkshop_<appid>.acf
    #               <root>/workshop/appworkshop_<appid>.acf（填到 steamapps 层）
    #               <root>/appworkshop_<appid>.acf（填到 workshop 层）

def verify(library, cfg) -> IntegrityReport:
    roots = {game_content_root(a) for a in 库内 appids} | {默认 LIBRARY_DIR/...}
    # (a) 账↔盘：rec.installed 且 local_path 目录缺失/空 → missing_on_disk（建议重下）
    #     content/<appid>/<id> 有目录但库无记录 → untracked（建议登记入册）
    #     content root 不存在 → 死根短路：一行红字说明，不逐条报 missing（防满屏误报）
    # (b) 账↔acf：acf 有而库无 → acf_only；acf.timeupdated ≠ rec.time_updated → version_mismatch
    #     （口径注明：acf timeupdated 是 steamcmd 本地版本，与库内工坊元数据 time_updated 语义相近
    #      但不保证逐位同步——报告标"建议核对"而非"错误"）；rec.time_updated=0 → 版本未知
    # (c) size 汇总提示（acf.size vs rec.file_size 差异聚合一行，不逐行报）
```
UI：library_tab 按钮 → daemon 线程跑 `verify`（只读对账毫秒-秒级，大库仍走线程防卡）→
`IntegrityDialog`：分桶计数（零值桶省略）+ 明细表 + 关键字过滤；行内动作（全部经确认弹窗）：
`missing_on_disk`/`version_mismatch` →「重新下载」（复用 _on_check_updates_done 的
WorkshopItem 重建 + `downloader.enqueue`）；`untracked` →「登记入册」（upsert ModRecord，
title 取 `未命名 mod {id}`，走 library.import_existing 同款记录创建 + `library_changed` 通知刷新）。
**不造第二套账本**：差集全部对 `ModLibrary` 现有记录算，无任何新持久存储（报告对象纯内存）。
SWDM 与竞品的修复范式差异：竞品生成 steamcmd 命令文本给用户手粘（其哲学是"绝不代你执行"）；
SWDM 自动路线下直接走下载队列——差异点而非缺口，符合计划草案"全自动批量省心"定位。

**依赖**：mod_library / game_dirs / config 只读；独立于 S1（S2 先行不依赖备份表）。

**风险**：
- version_mismatch 假阳性（Steam 侧 time_updated 与 manifest 更新偶不同步）→ 降级为
  "建议核对"口径 + 时间戳并列展示（acf 值 / 库值），不当错误计数。
- 多 install root（per-game 目录 + 默认库 + 用户库目录配置 general.library_dir）：
  collect 时取全量根，acf 缺失的根只跳过不报错。
- 非 steamcmd 来源（导入的目录、CDN 通道落地）无 acf：报告注明"按盘上事实核对，无 acf 版本信息"。
- 修复动作"登记入册"的库去重：`library.get()` 先查（import_existing 同款防重）。

**工作量**：core（parse_acf + locate_acf + verify 三差集）5.0 h；dialog UI（分桶计数 + 表 + 过滤 +
两动作）4.0 h；library_tab 接线 0.5 h；单测（自造 acf fixture：正常/含 BOM/interrupted/损坏、
三差集分支、死根短路）3.0 h → **12.5 h ≈ 1.6 人日**（草案"中低"；修复动作二阶段化可压到 ≈1.0 人日）。

**建议时序**：第 3 批最先（只读、零状态机侵入，失败面最小）；为 S1 铺路（核验页后续可承载
备份状态的展示）。

---

## 3. UX P0×4

### U1 工坊页中央空态

**涉及文件:行号**
- swdm/gui/workshop_tab.py:491-507（列表区构建：`list_scroll`/`list_layout`（497-500，尾部 addStretch））
- swdm/gui/workshop_tab.py:1042-1089（`_populate` 尾部：1043 清勾选、1076 `_update_dl_button()`、
  1081-1089 三分支状态小字 ← 空态落点）
- swdm/gui/workshop_tab.py:1016-1028（`_cards`/`_clear_cards`，空态 widget 需随卡片生命周期管理）
- 复用模式：swdm/gui/library_tab.py:284-344（`_build_empty_state`/`_refresh_empty_state` 两态双按钮）、
  swdm/gui/downloads_tab.py:397-423（B6 空态）
- 联动手册：E5（§3.5 承诺了不存在的空态）、E14（标签栏交互）——落地时同批修订

**改动草图**
```python
# _build 列表区（list_layout 尾部 stretch 之前插空态面板）
self._ws_empty = self._build_empty_state()
self.list_layout.insertWidget(self.list_layout.count() - 1, self._ws_empty)
self._ws_empty.setVisible(False)

# _populate 尾部（_update_dl_button() 之后，status_label 分支并入）
self._refresh_empty_state(items)

def _refresh_empty_state(self, items) -> None:
    show = not items
    self._ws_empty.setVisible(show)
    if not show:
        return
    has_filter = bool(self.search_edit.text().strip()) or bool(self.tag_bar.selected())
    if self._page > 1:          # 末页：回上一页
        title, hint, btn, act = "没有更多物品了", "已到最后一页。", "← 回到上一页", self._prev_page
    elif has_filter:            # 有筛选：清除搜索与标签
        title, hint, btn, act = "没有匹配的物品",
            "换个关键词，或用搜索栏下方的标签栏筛选；也可能触发了限流。",
            "清除搜索与标签", self._clear_search_and_tags
    else:                       # 无筛选空结果：重试
        title, hint, btn, act = "这个游戏暂无工坊物品",
            "该游戏可能暂无可抓取的工坊页，或触发了限流；稍后重试。",
            "↻ 重试", self._refresh_list
    ...（三个按钮按态显隐，仿 library_tab.py:327-333）
```
`_clear_search_and_tags()`（新助手）：`search_edit.clear()` + `tag_bar.set_selected([])` +
`_refresh_list()`；`_prev_page` 已存在（workshop_tab.py:1262）。
加载中不显示空态：`_populate` 只在结果到达时跑，`_list_overlay`（LoadingOverlay，506 行）覆盖加载态，
两者不冲突。11px 状态小字保留（老用户与调试信息），引导职责移交中央面板。

**依赖**：无（`tag_bar.set_selected`/`selected` 已有，见 _on_quick_search:1479-1481）。

**风险**：
- 空态在 `list_layout`（卡片纵列布局）内作"一张大卡片"插入，顶部对齐 + 内部居中；
  面板最小高度给足避免矮条状。本机零视觉验证能力 → 用几何量化兜底（mapTo(ref, QPointF(0,0))
  相对坐标 + 显式 isHidden()，QTabWidget 非当前页 isVisible() 恒 False 的既有坑）。
- E5/E14 手册同批修订（t48 已把 E5 改述为"仅状态小字"，U1 落地后手册再版回写新行为）。
- 回归 test_gui_sweep / test_page_switch / test_toolbar_layout（断言可能涉及列表可见性与状态文案）。

**工作量**：空态面板 + _refresh_empty_state 三态 + 两助手 2.5 h；几何断言 + 回归 1.5 h → **4.0 h**
（草案 0.5-1 人日）。

**建议时序**：第 2 批。

---

### U2 「清除已完成」只清成功行

**涉及文件:行号**
- swdm/gui/downloads_tab.py:289-309（`_clear_done`：295 行清三类终态 ← 改为只清 SUCCESS）
- swdm/gui/downloads_tab.py:62-65（按钮 + tooltip）
- 交给承接的失败入口：downloads_tab.py:72-75（「↻ 重试失败」→ `retry_all_failed`）与
  行内「重试」（downloads_tab.py:215-223）
- 旁证：swdm/core/downloader.py:373-379（`mgr.clear_completed()` 清 `_done` ——
  UI 从未调用，属死代码；本项不动它，仅记录为 P3 观察项）
- 联动手册：E3（§4.2 已被 t48 改述为实际行为，U2 改代码后手册再版同步）

**改动草图**
```python
def _clear_done(self) -> None:
    success_rows: list[int] = []
    kept = 0
    for job_id, row in list(self._row_map.items()):
        job = self._job_by_id(job_id)
        if job is None:
            continue
        if job.status == JobStatus.SUCCESS:        # U2：只清成功行
            success_rows.append(row)
            self._row_map.pop(job_id, None)
        elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
            kept += 1                              # 失败/已取消保留给「↻ 重试失败」
    if not success_rows:
        QMessageBox.information(self, "清除已完成", "没有可清除的成功记录。")
        return
    ans = QMessageBox.question(
        self, "清除已完成",
        f"将清除 {len(success_rows)} 条成功记录（仅列表行，文件与库记录不动）。"
        + (f"\n保留 {kept} 条失败/已取消记录，可用「↻ 重试失败」处理。" if kept else ""),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,                      # 危险操作默认"否"
    )
    if ans != QMessageBox.StandardButton.Yes:
        return
    for row in sorted(success_rows, reverse=True):        # 既有从大行号往小删逻辑不变
        self.table.removeRow(row)
    self._row_map = {}                                     # 既有索引重建逻辑不变
    for row in range(self.table.rowCount()):
        ...（复用 304-308）
    self._refresh_status()
```
按钮 tooltip 改"只清除成功的记录；失败/已取消行保留供重试"。

**依赖**：无（纯 UI 行过滤；`_done` 快照不动）。

**风险**：低；须回归 test_gui_sweep / test_t44_retest_gui 中涉及 `_clear_done` 的断言
（旧断言若断"失败行也被清"需同步翻转为新契约）。

**工作量**：过滤 + 确认弹窗 + tooltip 1.0 h；断言同步 0.5 h → **1.5 h**（草案 0.3 人日）。

**建议时序**：第 2 批。

---

### U3 检查更新取消按钮接线

**涉及文件:行号**
- swdm/gui/library_tab.py:177-181（`_check_cancel` 初始化恒 False ← 死代码根因）、
  366-417（`_check_updates`：377-378 防重入、389-392 置位/禁用按钮、399 行 cancel 回调已接线）
- swdm/gui/library_tab.py:419-424（`_set_check_progress` 按钮文本）、425-434（`_on_check_updates_done` 恢复按钮）
- swdm/core/steam_api.py:446-493（`check_updates`：476 `if cancel and cancel(): break`、
  每批 50 条粒度中止——**核心层零改动**，纯 UI 接通兑现 t37 契约）
- 回归测试：tests/test_t37_lib_updates.py:197-238、tests/test_a6_check_updates_thread.py:83-98

**改动草图**
```python
# library_tab.py
def _check_updates(self) -> None:
    if self._check_running:                  # 运行中再点 = 取消（复用同一按钮）
        self._check_cancel = True
        self.check_updates_btn.setEnabled(False)
        self.check_updates_btn.setText("🔍 取消中…")
        return
    if self._check_thread is not None and self._check_thread.is_alive():
        return
    ...（既有启动逻辑）
    self._check_running = True
    self._check_cancel = False
    self.check_updates_btn.setEnabled(True)          # 保持可点 = 取消入口（原 setEnabled(False) 删除）
    self.check_updates_btn.setText("⏹ 检查中…")
    self.check_updates_btn.setToolTip("点击中止本次检查（当前 50 条批次结束后停止）")
    # worker 的 cancel=lambda: self._check_cancel（399 行）已就绪——核心层不动

def _set_check_progress(self, done, total):
    if total > 0:
        self.check_updates_btn.setText(f"⏹ 检查中 {done}/{total}")   # 进度+取消双语义

def _on_check_updates_done(self, updated):
    cancelled = self._check_cancel
    self._check_running = False
    self.check_updates_btn.setEnabled(True)
    self.check_updates_btn.setText("🔍 检查更新")
    self.check_updates_btn.setToolTip("")
    if cancelled:
        # 部分结果不吞：标红已比对出的更新，消息如实说明
        if updated:
            self._updated_ids = set(updated); self.refresh()
        QMessageBox.information(
            self, "检查已取消",
            f"已取消检查{f'：已比对条目中发现 {len(updated)} 个更新' if updated else '（尚未比对出更新）'}。")
        return
    ...（既有 "没有发现需要更新的 mod" / 标红 + 询问一键入队 不变）
```
取消粒度：批间（每批 50 条 API 调用约数百 ms-数 s），当前批跑完即停——大库可中止契约达成；
按钮单元素承担「启动 / 进度 / 取消」三态，与「↻ 刷新」等既有按钮风格一致。

**依赖**：无核心改动（steam_api.check_updates 的 cancel 参数 1.4.1 t37 已实现）。

**风险**：
- 既有测试的点击语义变化：test_a6 单击启动（_fast_check 快速完成）兼容；
  若任何回归脚本在运行中二次 click 按钮，将被解释为取消——需审计全部 click() 调用点
  （test_t37 line 197-198 直接设 `_check_cancel = False` + setEnabled(False)，须按新流程改造）。
- 模拟弹窗非真阻塞的既有教训（记忆条目）：断言取消态须在桩函数内捕获，不依赖弹窗时序。

**工作量**：三态按钮 + done 分支 1.5 h；t37/a6 改造 + 新取消断言 1.5 h → **3.0 h**（草案 0.3 人日，
本预研含测试改造成本后偏高——实现本身约 0.2 人日）。

**建议时序**：第 2 批。

---

### U4 勾选入队后清空 _checked_ids

**涉及文件:行号**
- swdm/gui/workshop_tab.py:1304-1332（`_download_selected` → `_download_with_deps`，
  1326 行入队循环后无清空 ← 病根；按钮仍显示「⬇ 下载勾选 (n)」）
- swdm/gui/workshop_tab.py:1272-1284（`_on_card_check_toggled`/`_update_dl_button`，复位路径）
- swdm/gui/workshop_tab.py:1286-1294（`_check_all`，复用 setChecked 触发模式）
- 回归：tests/test_checkboxes.py:49-76（现有断言覆盖勾选/全选/重填，需加"入队后清空"）

**改动草图**
```python
def _download_selected(self) -> None:
    appid = self._current_appid()
    checked_ids = set(self._checked_ids)
    items = [i for i in self._items if i.publishedfileid in checked_ids]
    if not items:
        QMessageBox.information(self, "提示", "请先勾选要下载的 mod")
        return
    self._download_with_deps(items, appid)
    # U4：入队即清空勾选 + 复位按钮，消除"重复下载"误解
    # （核心层去重 enqueue 只记日志，UI 侧必须自证已入队）
    self._checked_ids.clear()
    for c in self._cards():
        c.setChecked(False)      # 触发 check_toggled→discard（集合已空，幂等无回路）
    self._update_dl_button()     # 文本回「⬇ 下载勾选」、禁用
    # 状态栏"已加入下载队列：N 个 mod"（1329-1332）保留
```
`_download_with_deps` 的异步依赖解析（`_on_deps_resolved`，1356+）持有局部 `items` 引用，
与清空 `self._checked_ids` 互不影响。单卡下载 `_download_item`（1297-1302）不经勾选路径，
保持现状（其卡片随后 mark_downloaded）。

**依赖**：无。

**风险**：极低；`_populate` 已在 1043 行清勾选，新增清空点与之同语义。
test_checkboxes 加断言"点「下载勾选」后 `_checked_ids` 为空且按钮文本无 (n)"。
（注：`_download_with_deps` 会 `show_downloads` 切页，清空发生在切页前同帧，无可见闪烁。）

**工作量**：清空 + 复位 0.5 h；断言 0.5 h → **1.0 h**（草案 0.2 人日）。

**建议时序**：第 2 批。

---

## 4. 汇总与闸门

### 4.1 依赖矩阵

| 项 | 依赖（必须先行/配合） | 被依赖 |
|---|---|---|
| P0-1 | 无 | 无（独立） |
| P0-2 | 无（与 P0-3 联合回归账号通道取消） | — |
| P0-3 | 无 | 强化 P0-2 的取消正确性 |
| P0-4 | 无（t44 测试翻转是唯一契约变更） | — |
| U1-U4 | 无核心依赖 | 手册再版（E5/E14←U1、E3←U2） |
| S2 | 无（mod_library 只读） | 可为 S1 报告备份状态 |
| S1 | config schema + mod_library schema（`_init_db` 既有迁移机制） | 手册新增备份章节 |

### 4.2 回归要求（用户规则：全量回归，不只测改动点）

必跑清单（改动点直接关联）：
- tests/test_throttle.py（7a/7g/7h 语义不得退化；新增溢出/死锁回归）
- tests/test_ap1_cancel_race.py（16 项全过——cancel 路由改动的高危面）
- tests/test_engine_concurrency.py、tests/test_account_provider.py（P0-2/P0-3）
- tests/test_t44_retest_gui.py（P0-4 契约翻转后重跑；B3a/B3c 已按新行为断言）
- tests/test_t37_lib_updates.py、tests/test_a6_check_updates_thread.py（U3）
- tests/test_checkboxes.py、tests/test_gui_sweep.py、tests/test_core_sweep.py、
  tests/test_download_fixes.py、tests/test_providers.py（U1/U2/U4 与既有行为面）
- 新增：update_backup / integrity 各自单测（含自造 acf fixture 与 robocopy mock runner）
收尾：run_all 全量（当前 ~64 脚本）+ GUI 复测轮 + 核心复测轮（交付四要素），版本号 bump
（paths.py:13 + swdm.iss），docs/changelog_1.4.2.md。

### 4.3 硬约束合规自检（plan 草案 §三约束逐条）

- P0-2 记 job→实际 provider 映射（含链内回退后的当前 provider）：✅ `_run_provider` 入口写、
  链循环每 provider 覆盖、两处清理。
- P0-3 不新造第二条引擎管理路径：✅ 复用 `AccountSteamCMDProvider.get_engine` 与既有登录态分支
  的"现场构造"模式，单一工厂两调用点。
- P0-4 set_max 立即生效且不破坏 test_throttle 7a：✅ set_max 从未在 7a 路径调用；调低调高
  语义文档化。
- U2 失败行交由「↻ 重试失败」承接：✅ 过滤改 SUCCESS-only + 确认弹窗引导。
- U3 复用 steam_api.check_updates 已有 cancel 回调，核心零改：✅ 476 行回调已接线，
  本项纯 UI 三态按钮。
- U4 清空后按钮文案与状态栏提示同步：✅ `_update_dl_button` 复位 + 1329 状态栏保留。
- U1 消除 E5 并与 E14 同批修订：✅ 空态面板 + 手册再版联动。
- S1 默认开 + 失败不阻断主流程 + robocopy /MT /XJ（照搬 `/E /MT /XJ /R:2 /W:2 /NFL /NDL /NP`）
  + 按 mod 份数与全局容量上限 + 恢复前强制先备份当前版：✅ 全部落草图。
- S2 不造第二套账本：✅ 差集对 ModLibrary 现有记录算，报告对象纯内存，零新持久存储。
- 无误报保护项（A-P1 竞态闭环 / 深拷贝三路径 / 零除 guards / 路径穿越防御 / 凭据四风控）：
  ✅ 本批改动不触及这些路径；P0-2 的 cancel 分支保持 A-P1 的 `_cancelling` 时序与终态守卫不变。

### 4.4 交付拆分建议（供讨论组裁决）

- 主交付（1.4.2）：P0×4 + U1-U4 + S2 + S1 自动备份/保留/配置（S1 一键恢复可选拆期）。
- 讨论组须裁决的三点：① S1 备份元数据存 library.db（单库）or 独立存储（预研建议单库）；
  ② P0-4 调高并发是"立即跳满"还是"逐级爬升"（预研建议爬升）；③ S1 默认开（草案初判默认开）。
- 1.4.2 收尾手册再版联动段：E3（随 U2）、E5/E14（随 U1）、E8（随 U8，若 U8 纳入）、
  新增 S1/S2 章节（与 t42 手册基建的「帮助 > 用户手册」HTML 链同批重建）。

## 5. 互链

- 输入：docs/plan_1.4.2_draft.md（候选清单与议程）· docs/core_audit_1.4.2.md ·
  docs/ux_audit_1.4.2.md · docs/competitor_research_1.4.2.md
- S1/S2 设计参数源：docs/research/sefrawe_backup_verify.md（竞品源码精读，plan 草案议程 C
  要求的"robocopy 参数细节与 acf 解析字段细节"已在该文件闭环，无需再派 subagent）
- 本预研生效路径：1.4.2 讨论组决议 → docs/feature_review_1.4.2.md → docs/plan_1.4.2.md（去 draft 后缀）
  → 任务拆分（按本文件第 0 节时序）
