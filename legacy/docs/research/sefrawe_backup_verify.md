# 竞品精读：sefrawe/Steam-Workshop-Mod-Assistant-Management-Tool

> 竞品仓库：https://github.com/sefrawe/Steam-Workshop-Mod-Assistant-Management-Tool
> 默认分支 `master` · Python 3.12 + PySide6 · MIT · README 自述"三句话原理"：检测更新（API 远端时间 vs acf 本地时间）→ 下载（steamcmd 命令）→ 确认（扫 acf 回写账本）。
> 调研日期：2026-09-30 · 只读调研，未修改任何代码。

## 0. 仓库结构速览（与本报告相关者）

| 层 | 文件 | 职责 |
|---|---|---|
| core | `backupManager.py` | 备份/恢复/删除引擎（robocopy、保留策略、R4-R10 红线） |
| core | `modVerifier.py` | 账实核验：`verify()`（账↔盘）+ `verify_junctions()`（账↔游戏侧链接） |
| core | `localScanner.py` | acf 解析 → 本地版本三件套回填 |
| core | `steamPaths.py` | steamcmd 目录布局推导、junction 拓扑判定 |
| core | `commandBuilder.py` | steamcmd 命令生成（含 validate 修复命令） |
| core | `appSettings.py` / `models.py` / `schema.sql` | 配置（保留份数/配额）、数据模型、backups 表 |
| gui | `backupPage.py` / `backupOverviewPage.py` | 备份管理页（钉住、恢复、重定位、搬家） |
| gui | `batchDownloadController.py` | **更新前自动备份**（决策 40：备份阶段 → 下载批次） |
| gui | `verifyPage.py` | 核验页 UI：三差集展示、修复三选、账外收录 |
| tests | `test_backupManager*.py` / `test_modVerifier.py` / `samples/appworkshop_3117820.acf` | 测试与 acf 样本 |

架构要点：core 纯逻辑零 Qt；GUI 只做"勾选、确认、线程、把报告翻成人话"；`ModRepository`（sqliteRepository）是唯一写库点；引擎按次构造、参数注入（`BackupManager(repo, keep_per_mod=…, quota_bytes=…, steamcmd_path=…, runner=…)`）。

---

## 功能一：更新前自动备份 + 一键恢复

### 1.1 关键文件与核心函数

| 函数 | 位置 | 作用 |
|---|---|---|
| `BackupManager.backup_mod(mod_id, note=)` | `core/backupManager.py` | 备份一个 mod：前置校验 → robocopy 复制 → 登记 → 保留策略清理 |
| `BackupManager.restore_backup(backup_id)` | 同上 | 一键恢复：五步全程可退流程 |
| `BackupManager._prune(exclude_id=)` | 同上 | 保留策略：每 mod 份数 + 全局配额，钉住豁免 |
| `BackupManager._run_robocopy(src, dst)` | 同上 | 真 robocopy 调用（测试可注入 `runner`） |
| `steamcmd_running()` | 同上 | psutil 进程检测（备份页/核验页/扫描横幅共用） |
| `_BackupPhaseWorker`（QThread） | `gui/batchDownloadController.py` | **更新前自动备份**：下载批次前逐个备份"备份+更新"条目 |
| `BatchDownloadController.start_batch(…, backup_first=[…])` | 同上 | 备份阶段 → 备完自动开下载批次；备份失败条目剔除下载 |
| `_BackupWorker` / `_CallWorker` | `gui/backupPage.py` | 手动备份/恢复后台线程 |
| `BackupManager.delete_backup(backup_id)` | core | 手动删除（先盘后账） |
| `_BackupPhaseWorker` 停止协议 | gui | 批间停止（当前这个备完就停），不打断进行中的 robocopy |

### 1.2 数据结构

```python
@dataclass
class Backup:                 # models.py，对应 backups 表
    mod_id: int
    backup_path: str          # ★存相对 game.backup_dir 的目录名（R1），不存绝对路径
    size_bytes: int           # 备份完成后 _dir_size() 实测，不用预估值
    version_timeupdated: int  # 备份时 mod.local_timeupdated（acf 本地版本）
    manifest: str | None      # acf manifest（str，无符号64位逼近 SQLite 上限）
    note: str | None          # 如 "恢复前自动备份"
    pinned: bool = False      # 豁免自动清理
    created_at / id

@dataclass
class BackupReport:           # 备份返回：ok / backup / warnings / error / cleaned
@dataclass
class RestoreReport:          # 恢复返回：ok / pre_backup(R8 强制备份) / warnings / error
```

**backups 表**（schema.sql）：`backup_path TEXT NOT NULL UNIQUE`（防同一目录重复登记）、`pinned INTEGER CHECK(0,1)`、`version_timeupdated INTEGER NOT NULL`、外键 `ON DELETE RESTRICT`（备份代表磁盘文件，不随 mod 记录级联消失，须显式处理）。索引 `idx_backups_mod(mod_id, created_at)`。

Game 模型新增 `backup_dir: str | None`（NULL = 首次备份时按 steamcmd 位置推导并**回写档案**）。

### 1.3 备份目录布局与命名

- 默认根目录（`steamPaths.backup_root_default`，决策 21⑥）：`<steamcmd根的上一级>\mod_backups\<appid>\`
  - 上一级而非 steamcmd 树内：避开 steamcmd 自更新/重装；同盘拷贝快。
- 备份子目录命名（`_fresh_target`）：`<modid>_v<本地版本>_<时间戳：%Y%m%d_%H%M%S>`；同秒冲突追加 `_2`、`_3`。
- 推导兜底：档案未设 `backup_dir` → 用 steamcmd 路径推导 → **回写档案** + 加 warning"已按 steamcmd 位置推导并写入档案"，下次不再推导。
- 已知限制（R1）：用户日后改 `backup_dir`，旧记录按新位置解析而失联 → 备份管理页提供【重定位备份目录】（只改档案字段，不动文件）与【备份搬家】（物理搬运 + 旧位置建 junction，记录一个不动）。

### 1.4 robocopy 具体参数

```python
cmd = ["robocopy", src, dst, "/E", "/MT", "/XJ", "/R:2", "/W:2", "/NFL", "/NDL", "/NP"]
```

| 参数 | 用途 |
|---|---|
| `/E` | 连子目录一起拷（含空目录） |
| `/MT` | 多线程（默认 8 线程，不指定数字） |
| `/XJ` | **排除 junction/符号链接**（R10）：防止链接成环无限递归 |
| `/R:2 /W:2` | 失败重试 2 次、每次等 2 秒——**必须掐掉** robocopy 默认的 100 万次重试 × 30 秒 |
| `/NFL /NDL /NP` | 不逐文件/目录/进度刷屏（`/MT` 下进度条本就不可用） |

**退出码判定（R5，全文件最容易踩的坑）**：`is_success_rc(rc) = rc < 8`。**rc 0-7 全部算成功；rc 1 = "有文件被拷贝"，是最常见的正常成功码**——判错会把每次成功的备份都报成失败。只有 `>= 8` 才是失败。错误信息取 `out[-800:]`（robocopy 输出尾部，截 800 字符防弹窗撑爆）。

**解码（仅诊断用，不参与判定）**：先试 UTF-8 再试 GBK，坏字节 `errors="replace"`——中文 Windows 控制台输出是 GBK。

**调用方式纪律**：命令一律**列表形式**传 `subprocess.run(cmd, capture_output=True)`，永不手拼 shell 字符串（含空格路径的引号由 subprocess 自动处理）。

### 1.5 备份前置校验链（backup_mod 顺序）

1. `mod.version_unknown`（`local_timeupdated` 不 > 0）→ 拒绝。文案区分两种：`downloaded` 但版本未知（手动确认入账，acf 里永远没有）→ 指引"重新下载 + 扫描本地"；否则 → "先扫描本地再备份"。
2. 确定备份根目录（档案值优先，缺省推导 + 回写）→ 推不出（无 steamcmd 路径）则拒绝。
3. 源目录 `download_dir/<mod_id>` 不存在 → 拒绝。
4. **环境检查只警告不拦截**：`steamcmd_running()` → warning"可能拿到不完整副本"（备份引擎的警告在批次前备份阶段必然出现且必然失真——此刻批次未开始、steamcmd 停在提示符，控制器统一过滤不转述）；路径 > 240 字符 → warning（robocopy 能处理长路径，这正是选它不用 shutil 的原因）。
5. **磁盘空间预检（R9）**：`free < mod.local_size` → 拒绝；`free < local_size * 1.1` → warning"偏紧"；无 local_size → 跳过预检 + warning。
6. robocopy 复制；失败 → 删半成品目录（刚创建的备份根内，走 R4 保险丝）。
7. **登记**：`add_backup(backup_path=dst.name, size_bytes=_dir_size(dst), version_timeupdated=…, manifest=…, note=…)`。
8. **保留策略**（清腾时机 = 新备份成功落盘之后）：① 每 mod 保留最新 N 份（按 mod 分组、旧→新排、尾部 N 条保留，其余清掉，钉住与本次备份豁免）；② 全局总量 `sum_backup_bytes() > quota_bytes` → 从最旧的非钉住备份清起，直到达标或无可清（`quota_tight=True` → warning"可清理的都已钉住或只剩本次"）。

保留策略配置（`appSettings.DEFAULTS`，字符串存放，`get_int` 读）：
- `backup_keep_per_mod = "3"`（每 mod 保留份数）
- `backup_total_quota_gb = "10"`（全局容量上限 GB；**0 = 不限**；GB→字节只在边界换算一次 `quota_gb * 1024**3`）

### 1.6 R4 路径保险丝（所有删除动作必过）

```python
def _assert_inside(target, expected_root):
    if _is_link_or_junction(target): raise RuntimeError("拒绝操作链接/junction…")
    real = _norm(os.path.realpath(target)); root = _norm(realpath(expected_root)).rstrip(sep)
    if not real.startswith(root + os.sep): raise RuntimeError("路径越界…")
```

- **junction 检测必须 `os.path.islink() or os.path.isjunction()` 两个都查**——`islink` 对 junction 一律 False（Python 3.12 新增 `isjunction`），只查 islink 等于没查。
- `_norm` = `normcase(abspath())`：Windows 路径比较一律大小写/斜杠归一。
- `_safe_rmtree(target, expected_root)` 是唯一删除入口；对外别名 `safe_rmtree` 供 core 之外调用。
- 删除顺序"先盘后账"：`delete_backup` 磁盘目录已不在 → 只删记录并说明；保险丝拦下 → 账不动并说明（残留交核验页非数字桶暴露）。

### 1.7 一键恢复流程（R8 原案，全程可退）

```
① 恢复入口前置：steamcmd 在跑 → 直接拒绝（恢复会与下载争用同一目录，两边一起坏；
   与备份的"只警告"故意不对称——备份顶多拿到不完整副本，恢复会覆盖写一半的下载目录）
② 强制先备份当前版本（R8）：dest.is_dir() → backup_mod(note="恢复前自动备份")；
   备份失败 → 中止恢复（要求先备份当前版本）；无本地内容 → 跳过并警告
③ 当前文件夹改名挪走（同盘 rename = 原子操作）：dest → <modid>_restore_old_<时间戳>；
   无现状时 aside=None（修复了"无内容路径却无条件 rename → WinError 2"的旧 bug）
④ robocopy 备份 → 原位
⑤ 失败回退：删半成品新目录 → 旧目录 rename 回原名（回退失败也只警告"请手动改回"）
⑥ 成功：删掉挪走的旧目录（删除失败只警告，恢复本身已成功）
```

GUI：`backupPage._start_restore` 仅允许**恰好勾 1 份**（批量恢复要求每份先备份当前版本，交互又重又危险，首版不做）；确认框列明 mod/备份版本/大小；恢复结果经 `_CallWorker` 单任务线程；`report.pre_backup` 非 None → 提示"恢复前已自动备份当前版本"。恢复没有停止点（停在中途=危险），等它跑完；`shutdown()` 对恢复线程只 wait。

### 1.8 更新前自动备份（决策 40，`batchDownloadController`）

- 触发入口：`start_batch(app_id, mod_ids, backup_first=[……])`——`backup_first` = 用户在确认清单（`updateSelectDialog`）里选了"备份+更新"的条目；`dailyUpdatePage` 日常更新一条龙（检测→勾选→备份+下载→复扫）串起全流程；mod 库页手动批次不传 `backup_first`（那边有右键手动备份兜底）。
- 执行：`_BackupPhaseWorker`（QThread）逐个调 `backup_mod`，进度写运行日志（one_done 信号）；**逐个顺序执行**——robocopy 自带 `/MT` 多线程，外层再并行只会互抢磁盘。
- 时机安全性：此刻批次未开始、steamcmd 停在提示符空闲、无下载写盘，robocopy 读到稳定文件——引擎 R7 的"steamcmd 在跑"警告在本阶段必然失真，控制器统一过滤不逐条转述。
- 备份失败条目**不参与下载（保护原内容）**，计入 `batch_done` 汇总的 `backup_failed`；全部失败 → 不开批次；手动停止 → 批次没有开始。
- 备份阶段也算 `is_active()`（主窗口关窗确认/导入拒绝都算上）；`shutdown()` 批间停止并 wait。
- 保留份数/配额在控制器里与备份管理页**同一组装**：`keep = get_int("backup_keep_per_mod", 1)`，`quota = get_int("backup_total_quota_gb", 100)`，`>0` 才换算字节。

---

## 功能二：账实核验（acf 解析 + 三差集 + 修复命令生成）

### 2.1 关键文件与核心函数

| 函数 | 位置 | 作用 |
|---|---|---|
| `locate_acf(base_path, app_id)` | `core/localScanner.py` | 定位 `appworkshop_<appid>.acf`（三种填写口径容错） |
| `scan_acf(path)` | 同上 | VDF 解析 → `LocalItem` 清单 + 跳过清单（质量谓词） |
| `diff_plan(items, existing_status)` | 同上 | 扫描结果 ↔ 库现状对表，产出回填/补录计划（纯函数） |
| `apply(repo, plan)` | 同上 | 一个事务落库（update_local_state / add_mod） |
| `modVerifier.verify(download_dir, status_by_id)` | `core/modVerifier.py` | **账↔盘对账**：missing/empty/untracked/non_numeric/dead_root/healthy |
| `modVerifier.verify_junctions(...)` | 同上 | **账↔游戏侧链接**：link_missing/wrong_target/real_dir/extra |
| `commandBuilder.build_validate_commands` | `core/commandBuilder.py` | `workshop_download_item <appid> <modid> validate` |
| `verifyPage._repair_row` / `_show_validate_dialog` / `_mark_removed` | `gui/verifyPage.py` | 修复三选 UI |
| `steamPaths.refresh_download_dir` / `junction_state` | core | 死路径重推导 / junction 拓扑判定 |

### 2.2 acf 文件解析

**定位**（`locate_acf`）：认三种填写口径——填 steamcmd 根 → `<根>/steamapps/workshop/appworkshop_<appid>.acf`；填 steamapps 层 → `<层>/workshop/name`；填 workshop 层 → `<层>/name`。找不到返回 None（不是错误）。

**VDF 解析**（用 `vdf` 库，ValvePython）：
- `read_text(encoding="utf-8-sig")`——**吃 BOM**，否则 vdf 第一个键就解析坏。
- `vdf.loads` 失败 → 统一转 `ValueError("acf 解析失败（文件损坏或不是 VDF 格式）")`（保留异常链）；无 `AppWorkshop` 根区块 → ValueError（"可能选错了文件"）。页面层只需接一种异常。
- `WorkshopItemsInstalled` 缺失 → 合法空态（`installed = {}`）。
- **顶层字段与 `WorkshopItemDetails` 区块一律忽略**——不是事实源（`latest_*` 是 steamcmd 上次联网的缓存）；远端唯一事实源是 Steam Web API。

**字段清单**（实测样本 `tests/samples/appworkshop_3117820.acf`）：

```
"AppWorkshop"
{   "appid" "3117820"
    "SizeOnDisk"      "229413662"     ← 忽略（对账不认，WorkshopItemsInstalled 的 size 才是逐条事实）
    "NeedsUpdate"     "0"             ← 忽略
    "NeedsDownload"   "0"             ← 忽略
    "TimeLastUpdated" "1787113682"    ← 忽略
    "TimeLastAppRan"  "0"             ← 忽略
    "LastBuildID"     "0"             ← 忽略
    "WorkshopItemsInstalled"
    {   "<publishedfileid>"
        {   "size"       "<字节>"        ★采信
            "timeupdated" "<Unix秒>"     ★采信（本地版本）
            "manifest"   "<4632…>"       ★采信（str）
        } …
    }
    "WorkshopItemDetails"                          ← 整块忽略（含 latest_* 缓存）
    {   "<id>" { "manifest" "timeupdated" "timetouched" "latest_timeupdated" "latest_manifest" } }
}
```

**质量谓词（决策 23：账本只记"确信下载成功"的条目）**：
- `timeupdated` 缺失或 ≤ 0 → "疑似下载中断"跳过（steamcmd 中断时账本留 0）
- `manifest` 缺失/空串/`"-1"` → 同上（`-1` 是 steamcmd 下载中断的标志值，无法定位具体版本）
- `size` 缺失/0 → **不拦**（只影响展示与备份空间预检），聚合一条 warning（编号列表超 10 个截断）
- 条目级问题跳过记原因；`ScanResult.interrupted` 属性靠原因前缀"疑似下载中断"把中断类与格式类（不是键值块/编号非数字）分开——**修法不同**：中断类 = 重新下载，格式类 = 排查工具。

**diff_plan + apply**：库中已有 → 三件套全量回填（幂等重写，刻意不与旧值差异比较）；状态只允许 `tracked → downloaded` 一个跃迁方向，`deleted/failed` 只补本地证据状态不动；库中没有 → `add_mod(status="downloaded", url=现拼不联网, 远端字段留 NULL)` 待更新检测补全。整个计划一个事务，跨游戏撞主键 `IntegrityError` 显式爆炸整体回滚。

### 2.3 "账上有/盘上有/版本一致"三差集算法

README 宣传语"「账上有 / 盘上有 / 版本一致」三差集报告"在代码里落在**三处互补的单源对账**上：

**(a) 账上有（DB ↔ acf）= `localScanner`**：steamcmd 的账本里有没有、版本三件套回填。回答"steamcmd 认为装了什么"。

**(b) 盘上有（DB ↔ 磁盘）= `modVerifier.verify(download_dir, status_by_id)`**：`status_by_id` 调用方用 `list_mods` 取全后传字典（**要含 deleted/failed**——它们决定"盘上有目录"算不算异常）。算法：

```
1. download_dir 为空/不存在 → dead_root 短路返回（逐条对账全是噪音误报）
2. root.iterdir() 分桶：entry.name.isdigit() → numeric[id] = name（保留原名防前导零错位）；
   其余（非数字目录 + content 下不该有的散文件）→ non_numeric 桶
3. 遍历 status_by_id：status != "downloaded" 跳过；
   numeric 无 → missing（建议重下，决策 23：异常修复动作全项目统一 = 重新下载）；
   有但 _dir_is_empty（一层 scandir，目录里有任何子目录就算非空）→ empty（疑似中断残留）；
   其余 → healthy++
4. untracked_content = 盘上有数字目录但账本非 downloaded（状态原样携带：None=库外、
   tracked=可能手动下过/已收录待确认、deleted/failed=软删保留文件属正常）
5. 所有清单 sorted()，展示顺序稳定
```

**(c) 版本一致（远端 ↔ 本地）= 更新检测 + `commandBuilder.group_mods`**：`time_updated > local_timeupdated` 即需更新；本地有文件但从没查过远端（`time_updated <= 0`）保守归 needs_update。核验页不重算版本，只消费这把尺子（如收录提示"版本留空=版本未知"、确认入账后"备份将拒"）。

**(d) 链接对（DB ↔ 游戏侧）= `verify_junctions(download_dir, game_mod_dir, status_by_id)`**：已下载 mod 在游戏侧 mods 目录是否正确建了 junction（未配置 game_mod_dir → 返回 None = 未启用，不是错误；同目录布局 `_same_path(root, content_root)` → 返回 None）。分桶：`link_missing`（游戏里看不到此 mod，**修法=重建链接，重下无效！**重下只恢复 content 侧）/ `link_wrong_target` / `link_real_dir`（真实目录，R4 只报不动）/ `extra`。**刻意不设"悬空链接"桶**——链接对但实体没了和 verify() 的 missing 是同一问题，同页报两遍只会混乱。

**Windows 三个已知坑**（比对前必须处理）：
1. "链接"不只 junction：符号链接对游戏完全等价，`os.path.islink() or os.path.isjunction()` 两个都查（互有盲区）。
2. `os.readlink` 对 junction/symlink 可能返回 `\\?\` 扩展前缀 → `_strip_extended_prefix` 剥掉（UNC 的 `\\?\UNC\` 顺带还原成 `\\server\share`）再比对。
3. 路径比对一律 casefold（`_same_path` = resolve + as_posix + casefold；resolve 失败退回原样字符串）。

### 2.4 一键修复命令生成

核验页修复三选（`verifyPage._repair_row`，missing/empty 行的行内【修复…】按钮或右键菜单）：

| 选项 | 动作 |
|---|---|
| ① 重新下载（增量） | `command_gen_requested.emit([mod_id])` 信号 → MainWindow 跳命令生成页并勾选；双击缺失/空目录行 = 快捷走① |
| ② 校验重下（validate） | `_show_validate_dialog`：页内弹窗展示 `workshop_download_item <appid> <modid> validate` + 【复制命令】按钮（复制到剪贴板，粘贴进 steamcmd 终端执行） |
| ③ 标记为已移除 | `_mark_removed`：走 `repo.mark_deleted` 正门（写 deleted_at + 删除前快照快照 dict），不动磁盘文件 |

**validate 语义**（记事本查证）：校验盘上文件与 manifest 一致性，只补缺失/损坏文件；**被用户改动过的文件会被冲回原版**；整个文件夹缺失（或为空）时 = 完整重下。使用边界：日常更新命令**不加** validate（增量由 manifest 保证，加了更慢且可能冲掉 mod 内自定义文件）；validate 只在核验页"怀疑文件损坏"的修复场景用。

命令文本拼装单源在 `core/commandBuilder`：`build_validate_copy_text(app_id, mod_ids)` 每行一条、结尾留一个换行（粘贴进 steamcmd 直接回车）；空清单返回空串不返回孤零零换行。普通下载命令 `build_plain_commands` 格式与旧脚本逐字一致；**有意不做**：登录命令（用户自己在 steamcmd 登录）、`force_install_dir`、`.bat`/`+runscript`/`+quit`（手动粘贴覆盖全部场景，一行一条命令碰不到 Windows 8191 字符上限）。

核验页其他写库动作（全部经确认弹窗，默认保守"取消"）：账外条目收录（`_claim_flow`：入库为 tracked/"已收录"，盘上文件一个字节不动、版本三件套留空；插入前 `filter_existing_ids` **全库**二次对表防撞主键整批回滚；整批一个事务；可选手动确认走 `confirm_batch` 且**必须在插入事务提交之后调用**——repo 事务不支持嵌套）、确认勾选的已下载、设置游戏侧目录、死路径重推导（`refresh_download_dir`：存在即健康不二次猜疑，手填自定义路径天然豁免）。

### 2.5 核验页 UI 要点（可迁移）

- 7 列表（选/编号/标题/账本状态/盘上情况/建议/操作）+ 桶筛选下拉 + 关键词过滤（**即时只隐藏行、不清勾选**；隐藏行不参与批量动作——反"隐形操作"纪律）+ 重灌式排序（勾选状态按编号收割还原）。
- 行类别 kinds（missing/empty/claim/confirm/keep）决定一切分流：勾选框（claim/confirm 可勾）、修复按钮（missing/empty）、右键菜单项、筛选桶。
- **排序重灌会复用行**：原来带按钮的行现在可能不带——不摘除的话旧按钮会残留在新内容上（`removeCellWidget`）。
- 摘要分段计数零值省略：untracked_content 混着两种人（st=None 账没登记 vs st='tracked' 已收录待确认），分段才不冤枉后者。
- 三个折叠节（问题明细/非数字明细/链接巡检）收展状态 `QSettings` 持久化；空桶自动收起。
- 只读对账毫秒级，不开线程； junction 巡检前先用 `junction_state` 认拓扑：反向拓扑健康 → 一行绿字收工（逐条查会把每个已下载 mod 都报成"实为目录"，满屏同一句误报）。

---

## 可迁移到 SWDM 的实现要点

1. **robocopy 参数直接照抄**：`/E /MT /XJ /R:2 /W:2 /NFL /NDL /NP`，列表调用。退出码 `< 8` 算成功（rc=1 是正常成功）——这是最大的坑，必须有测试钉死。
2. **恢复五步法**（先备份当前 → 改名挪走 → robocopy 回写 → 失败回退 → 成功删旧）是经过实战的原子化设计：同盘 rename 原子、崩溃残留（挪走的旧目录+半成品新目录）可被核验页非数字桶暴露。
3. **保留策略两档 + 钉住**：每 mod 份数 + 全局配额（GB 存配置、字节只在边界换算一次、0=不限）；清腾时机 = 新备份落盘之后；钉住豁免自动清理但不挡手动删除。
4. **R4 保险丝**：删除前 `realpath` + 判断落在预期根内 + 拒绝操作链接/junction；`islink` 与 `isjunction` 必须双查（islink 对 junction 返回 False）。
5. **更新前自动备份**作为下载批次的前置阶段（独立 QThread、逐个顺序、备份失败剔除下载并计入汇总 `backup_failed`），而非耦合进下载流程本身；时机选在批次未开始时，规避"steamcmd 在跑"警告的失真问题，控制器统一过滤警告。
6. **版本三件套 + 质量谓词**是账实核验的数据基础：`timeupdated ≤ 0` 或 `manifest ∈ {空, "-1"}` 一律不入账（"疑似下载中断"），否则账本会被中断残留污染，核验永远对不齐。
7. **三差集拆成三个单源对账**（acf↔DB / 磁盘↔DB / 远端↔本地）+ 第四份链接对账，每份有明确分工与"刻意不报"清单（悬空链接、deleted/failed 保留文件等），避免同页重复报警。
8. **修复命令生成单源 core 纯函数**：validate 命令只在此场景使用，日常更新不带 validate（会冲掉用户改过的文件）——文案要把后果写清。
9. **死根短路**：download_dir 不存在时逐条对账全是误报，一行红字说清原因 + 指引（检查 steamcmd 路径/是否下载过）比满屏 missing 友好得多。
10. **GUI 纪律**：勾选记 id 不记行号（排序/重建后行号漂）；重建表格先关排序灌完再开；批量动作只作用于显示行；危险操作确认框默认按钮"否"；长路径标签开换行。

## 坑点清单（竞品用注释/决策号钉死的教训）

- **robocopy rc=1 是成功**（R5）——判错会把每次成功备份报成失败。
- **`os.path.islink()` 对 junction 返回 False**（踩坑⑩）——只查 islink 等于没查；`isjunction` 对 symlink 也返回 False，必须双查。
- **robocopy 默认重试 100 万次 × 等 30 秒**——一个坏文件能挂一天，`/R:2 /W:2` 必须显式掐掉。
- **链接成环无限递归**（R10）——`/XJ` 排除 junction 挂载点；反向拓扑检查必须排在"建议正向建链"之前，否则会造出链接→链接的环（NTFS 照单全收，遍历无底洞）。
- **`os.readlink` 返回 `\\?\` 扩展前缀**——不剥掉无法与普通 Path 比对；UNC 扩展形式要还原。
- **Windows 路径大小写不敏感**（R14）——所有路径比较 normcase/casefold；正反斜杠差异不算不同。
- **acf 文件 BOM**——`utf-8-sig` 读取，否则 vdf 第一个键解析坏。
- **vdf 库对半截文件抛自己的异常类型**——统一转 ValueError 但保留异常链，页面层只接一种异常。
- **无本地内容时恢复流程无条件 rename → WinError 2**——aside 要随"有没有现状"置 None。
- **"steamcmd 在跑"警告在批次前备份阶段必然失真**——控制器统一过滤，不逐条转述给用户。
- ** programmaic setCheckState 触发 itemChanged 空跑**——灌表期间 `_filling` 开关挡住。
- **重灌式表格不摘旧按钮**——排序后行复用，带按钮的行可能变成不该带按钮的行。
- **manifest 存 TEXT 不存 INTEGER**——无符号 64 位（实测最大 8.7e18）逼近 SQLite 上限 9.22e18。
- **confirm_batch 必须在收录插入事务提交之后调用**——repo 事务不支持嵌套。
- **mod 备份根放 steamcmd 树的上一级**——放树内会被 steamcmd 自更新/重装误删；放别的盘又损失同盘拷贝速度。

## 与 SWDM 现状的差异提示（供 1.4.2 规划参考）

- 竞品无 Steam 客户端依赖、纯 steamcmd + acf 单源；SWDM 已有匿名 API 浏览/下载链与自己的库模型，备份/核验若落地需对接 SWDM 的 download 目录与版本字段（`local_timeupdated` 等价物），acf 解析层（`localScanner` + 质量谓词）可几乎原样移植（依赖 `vdf` 库）。
- 竞品的"三差集"强依赖 acf 存在；SWDM 若走 steamcmd 下载链路同样具备 acf，可直接复用；对非 steamcmd 来源的 mod，核验口径要重新设计（竞品用"收录/手动确认"兜底，即账上承认但版本留空、备份拒绝）。
- 保留策略（份数/配额/钉住）与 robocopy 参数、R4 保险丝、恢复五步法是纯工程模块，与 SWDM 架构无冲突，迁移成本主要在 DB schema（backups 表）与 GUI 页面。
