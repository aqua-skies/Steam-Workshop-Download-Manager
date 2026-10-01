# SWDM 系统架构契约（system_contracts）

> 版次：2.0-pre · 基于 1.4.1 / 1.4.2-m1 代码库事实 · 仅描述 `swdm/` 与 `docs/` 的只读产物
> 用途：2.0 重构决策的输入底料。本文档把「代码现状 + 已付学费的历史教训」固化为契约，使任何重构路线（见 [rewrite_feasibility.md](rewrite_feasibility.md)）都不必重新 discovers 这些不变量。
> 维护规则：契约追随代码事实，不追随主观愿望。每次 core 域变更先改本文档再改代码（讨论组评审依据）。

---

## 0. 系统总览

```
┌─────────────────────────────────────────────────────────┐
│  GUI 层（PySide6，全部可重写，不持核心业务知识）           │
│  app.py → MainWindow → WorkshopTab / DownloadsTab /       │
│  LibraryTab / SettingsTab / DebugTab                      │
│  workers.py：QThread/QThreadPool 桥接层（信号转换器）      │
└───────────────▲ 信号（Qt Signal/Slot，主线程唯一写入口）───┘
                │
┌───────────────┴ 回调（普通 Python 函数，子线程触发）──────┐
│  服务容器 gui/services.py：Services = config/auth/api/     │
│  library/engine/downloader 六个单例，GUI 唯一访问核心的口  │
└───────────────▲ 依赖注入（构造期一次性注入）──────────────┘
                │
┌───────────────┴─────────────────────────────────────────┐
│  核心层 swdm/core（无 GUI 依赖、无 Qt 导入、纯逻辑 + IO）   │
│  ┌──────────┬──────────┬───────────┬───────────────┐    │
│  │ 接入域    │ 下载域    │ 存储域     │ 基础设施       │    │
│  │ steam_api│downloader │ mod_library│ paths/config  │    │
│  │ game_    │providers  │（SQLite）  │ logger/auth   │    │
│  │  search  │steamcmd_  │ detail_   │ circuit/      │    │
│  │ parsers  │  engine   │  cache    │ throttle      │    │
│  └──────────┴──────────┴───────────┴───────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**分层不变量**

1. core 不导入任何 Qt / GUI 模块（事实成立，2.0 必须保持）。
2. GUI 只通过 `Services` 容器访问 core；禁止 tab 直接 new 核心单例（`workers.py` 的 `_ImageTask` 曾自建 `SteamAPI` 实例，属历史逃逸点，见 §6.4）。
3. core → GUI 的数据流只能经回调函数（GUI 侧用 Qt 信号桥接回主线程）；GUI → core 只能经方法调用。
4. core 单例边界：`get_config()`、`get_api_cache()`、`get_detail_cache()`、`get_registry()`、`Services`。2.0 应把这些隐式单例改为显式注入（依赖倒置），这是阶段一的核心工作。

---

## 1. 模块契约（core 域）

每节格式：**职责 / 公共 API / 线程模型 / 不变量（含已付学费）**。

### 1.1 `paths` — 路径解析

- **职责**：应用数据目录、配置、日志、DB、缓存、steamcmd 工作区、mod 仓库的唯一真源；PyInstaller 资源解析。
- **公共 API**：`DATA_DIR / CONFIG_FILE / LOG_DIR / DB_FILE / CACHE_DIR / STEAMCMD_DIR / LIBRARY_DIR / CRASH_FILE`（模块常量）；`ensure_dirs()`；`resource_path(*parts)`；`bundled_steamcmd_zip()` / `deployed_steamcmd_exe()`；`APP_VERSION`（与 `installer/swdm.iss` 双端同步）。
- **线程模型**：模块级常量，import 时求值一次；`ensure_dirs()` 幂等、可任意线程调用。
- **不变量**：
  - 便携模式：可执行文件旁存在 `portable.marker` 时存储改 `<root>/data`，否则 `%APPDATA%/SWDM`。**所有"用户数据在哪"的判断只能走这里，禁止第三方拼路径。**
  - `resource_path` 在打包态走 `sys._MEIPASS`，开发态走项目根；QSS/图标/steamcmd.zip 依赖此解析。
  - 学费：版本号必须在 `paths.py` 与 `swdm.iss` **双端同步**，否则安装器与程序版本漂移（1.4.1 建立了该纪律）。

### 1.2 `logger` — 日志与调试通道

- **职责**：根 logger 初始化（轮转文件 + 内存环形缓冲）；GUI 调试面板实时 tail。
- **公共 API**：`setup_logger(level="INFO")`；`get_logger(name)`；`subscribe(cb)` / `unsubscribe(cb)`；`snapshot()`；`DebugChannel`。
- **线程模型**：模块级环形缓冲 + 订阅者列表均持锁；任意线程可记日志；订阅回调在记录线程同步触发（GUI 侧须自行桥接）。
- **不变量**：
  - 文件 `swdm.log`，2MB × 5 份轮转，UTF-8。
  - 环形缓冲上限 2000 条；订阅回调异常静默吞（日志系统不得二次抛出把业务逻辑打挂）。
  - `get_logger` 首次调用自动 `setup_logger`——所以 **core 模块 import 即日志可用**，无需显式初始化顺序。
  - 安全红线（C3 风控①）：账号名/密码/验证码**永不落日志**（`SteamCMDEngine._redact_secrets` 在 `log.debug` 与 `on_line` 之前执行）。

### 1.3 `config` — 配置管理

- **职责**：分层 JSON 配置（默认值 + 用户文件递归合并），进程级单例。
- **公共 API**：`get_config()` → `Config`；`Config.get(*keys, default=)` / `set(*keys_and_value)` / `save()` / `load()` / `reset()` / `as_dict()`；`DEFAULT_CONFIG`（全部配置项的权威清单）。
- **线程模型**：实例级 `_file_lock` 保护读写；`get` 无锁读（启动后 `_data` 结构只由 `set` 改动，`set` 需调用方自行注意并发——2.0 应把 `_data` 换成不可变快照 + 读写锁）。
- **不变量**：
  - 递归合并三层深：`download.providers.{name}` 块整体合并，**用户部分配置保留新增默认键**（老用户升级不丢配置）。
  - 写入原子化：`CONFIG_FILE + ".tmp"` → `os.replace`。
  - 关键配置语义：`download.channel`（provider 链首选）；`network.max_concurrent_downloads`（并发上限，`services.refresh_engine` 动态生效）；`steamcmd.*`（引擎参数）；`game_dirs.{appid}`（按游戏目录覆盖）；`dependencies.*`（依赖树行为）。
  - **凭据永不进 config**：账号密码走 `AuthManager.keyring`，`config.steamcmd.username` 仅存用户名（密码/验证码不在其中）。

### 1.4 `steam_api` — Steam 接入客户端（核心域，学费最密集）

- **职责**：Web API（无需 key 的元数据端点 + 需 key 的 QueryFiles）+ 社区页面抓取（浏览页/详情页）+ 429/403 对策 + 图片缓存 + 搜索二次处理。
- **公共 API**：
  - `SteamAPI(api_key="", proxy="", timeout=30)`；`set_api_key(k)`；`detect_system_proxy()`（静态）
  - `browse(appid, page, search_text, sort, required_tags, language, numperpage, force_refresh) -> list[WorkshopItem]`
  - `enrich(items) -> list[WorkshopItem]`（**就地修改**）
  - `get_file_details(item_ids) -> dict[str, WorkshopItem]`；`get_collection_details(cid) -> list[str]`
  - `get_dependencies(item_id) -> list[str]`；`resolve_dependency_tree(item, max_depth, skip_installed, library) -> (deps, skipped)`
  - `query_files(...) -> (items, total)`（需 key）
  - `check_updates(records, progress, cancel) -> list[str]`（库更新检查，批 50）
  - `fetch_image(url, size) -> str`（本地路径或原 URL）
  - `ping()`；`resolve_any_url(text) -> (appid, item_id)`
  - 静态：`title_hit_rate` / `filter_items_by_creator` / `filter_items_by_tags` / `apply_browse_search_fallback`
  - `WorkshopItem`（可变 dataclass）；`RateLimitError(retry_after, status)`
- **线程模型**：实例可在多线程共享（`requests.Session` 线程安全 + `_endpoint_lock` 串行化节流 read-sleep-write）；全局 `_throttle` 模块级单例。
- **不变量（每条都是学费）**：
  1. **缓存命中必深拷贝**：`browse()` 返回可变 `WorkshopItem`，`enrich()` 就地改列表——命中路径、hub 回退路径、未命中路径、限流降级路径**四处全部 `[copy.deepcopy(it) ...]`**。少一处即缓存污染（1.3.x 事故）。
  2. **端点差异化节流**：全局 `_Throttle(min_interval=2.0)`（成功衰减 -2s 至下限 2s，`trip/bump` 上限 60s）叠加端点前缀间隔表：`/sharedfiles/` 3.0s（历史 6s，请求头指纹修复后放宽）、`/workshop/browse/` 2.0s、`/ISteamRemoteStorage/` 3.0s。
  3. **节流锁覆盖 read-sleep-write 全程**：并发线程各自读同一 `last` 并一起 sleep 会让实际间隔小于设定值，削弱 429 防护。
  4. **429 = 请求头指纹层**（34 次本机实测）：Chrome UA 缺 `Accept-Language` 即被 Steam 自家 nginx 命中；补 `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8` 后 429→200。`X-Requested-With` 旧结论已被复实测推翻（现为 429），**只保留 Accept-Language 为唯一必需头**——结论可被复验推翻，代码注释必须写清。
  5. **429 响应从不带 Retry-After**（10/10），不能等头判冷却；退避 30s 起渐进 90s 封顶。
  6. **403 = IP/代理边缘层**（不可控），快速失败抛 `RateLimitError(60, 403)`，由上层用过期缓存兜底；重试无用。
  7. **priority 语义**：用户点击（`priority=True`）绕过端点等待；预取等低优先级请求在分片睡眠期间发现 `_priority_pending > 0` 时**让出槽位静默放弃**（返回空串，无副作用）。节流永远不挡用户操作。
  8. **匿名 Web API 的 `referenced_files` 恒为空**（94+ 物品采样），依赖关系只能抓详情页 `RequiredItems` 区块（`deps_parser`），`get_dependencies` 带 30 分钟 TTL 缓存，限流时降级返回过期缓存。
  9. **浏览页双解析**：经典 SSR 卡片正则为主；0 卡片时（游戏迁移到新 hub）解析 React Query 脱水状态（`hub_parser.extract_results`）。
  10. **匿名搜索二次处理**：Steam 搜索只匹配标题，作者搜索返回无关结果 → `apply_browse_search_fallback`（0 命中按作者过滤、低命中提示、空态明确文案）。
  11. **HTML 实体修复**：真实页存在不完整实体（`Kirbin&#x27` 缺分号），`_fix_html_entities` 先修补再 unescape。

### 1.5 `api_cache` — API 响应缓存

- **职责**：TTL + LRU 缓存（browse 结果键化），请求合并，限流降级。
- **公共 API**：`get_api_cache()`；`ApiCache.get(key, allow_expired=False) -> (hit, value)`；`set(key, value, ttl=None)`；`invalidate(predicate="")`；`stats()`；`get_or_compute(key, compute, ttl, allow_expired_fallback=True)`；`make_cache_key(appid, page, sort, search, tags, language, numperpage)`。
- **线程模型**：`RLock` 保护全部操作；请求合并的等待者 `time.sleep(0.02)` 轮询结果盒。
- **不变量**：
  - 默认 TTL 180s、上限 128 条、LRU 淘汰最旧。
  - **深拷贝纪律**：模块 docstring 明文——缓存值离开缓存前必须深拷贝（`WorkshopItem` 可变 + `enrich` 就地改）。
  - 请求合并用「盒模型 + `is_first` 布尔」而非列表真值判定（空盒恒为 falsy，等待者会误以为自己是首个）。
  - `compute` 抛异常时降级返回过期缓存（ `_get_stale`），否则抛出。
  - `invalidate` 三语义：空串清空 / 字符串子串匹配 / 谓词函数。

### 1.6 `circuit` — 共享熔断器

- **职责**：连接级/连续失败熔断（投机请求的共同保护伞：游戏名联想、下一页预取、浏览页）。
- **公共 API**：`CircuitBreaker(cooldown=15.0, threshold=3)`；`in_cooldown()`；`cooldown_remaining()`；`record_failure(e=None)`；`record_success()`；`force_trip(seconds=None)`。
- **线程模型**：锁保护 `_fail_streak` / `_cooldown_until`；`in_cooldown` 无锁读（时间单调， tolerate 精度）。
- **不变量**：`requests.ConnectionError`（如 WinSock 10053）**立即熔断**；否则连续 3 次失败熔断；冷却 15s 后自动半开；成功即重置计数。抽离自 `GameSearchClient`（t22 D），避免每个投机调用点自造熔断。

### 1.7 `game_search` — 游戏名搜索

- **职责**：无 AppID 时按名字找游戏（storesearch 端点）。
- **公共 API**：`GameSearchClient(proxy="")`；`search(term, limit=12) -> list[GameSearchResult]`；`cached(term)`；`is_in_cooldown()` / `cooldown_remaining()`。
- **线程模型**：实例可跨线程共享（`_lock` 保护缓存与 `_last_request`）；由 GUI 的 `_SearchWorker` 在 QThread 内调用。
- **不变量**（实测结论）：
  - 端点 `store.steampowered.com/api/storesearch/?term=&l=schinese&cc=CN`，匿名，`id` 即 AppID；过滤 `type != "app"`（DLC/视频）+ 名称启发式排除 DLC。
  - **中文搜索不可靠**（仅当商店名本身是中文），主搜英文；本地别名表 `games.GAME_ALIASES` 做离线兜底。
  - 最低请求间隔 0.7s（讨论组折中值，非 350ms：匿名接口无速率保障、本机出口被限过）；连接熔断 15s（复用共享 `CircuitBreaker`）。
  - 缓存 5 分钟（`search` 与 `cached` 共用 `_cache`）；联想场景先查缓存再决定是否发请求。
  - 学费：12 次连发请求触发 WinSock 10053 连接熔断（非 429），静置 15s 恢复 → **联想必须去抖 + 在途取消 + 缓存**。

### 1.8 `detail_cache` — 详情页磁盘缓存

- **职责**：详情页 HTML 持久缓存（回看已看过的 mod 零请求秒开）。
- **公共 API**：`get_detail_cache()`；`DetailDiskCache.get(item_id, time_updated=0) -> (hit, html)`；`set(item_id, html, time_updated)`；`invalidate(item_id=None)`。
- **线程模型**：锁内文件 IO；`get`/`set` 可跨线程。
- **不变量**：
  - **双失效**（用户硬约束"缓存及时清除"）：TTL（默认 24h，配置 `network.detail_cache_ttl_hours`，0 关闭）+ `time_updated` 不一致即判 miss 删条目（**过期 mod 比无缓存更糟**）。
  - 损坏容忍：任何解析失败当 miss 并删脏文件（杀软扫描/断电写半）；写入失败不影响主流程。
  - 原子写 `.tmp` + `os.replace`；命中返回深拷贝（与 api_cache 同纪律）。
  - `item_id` 纯数字白名单过滤，防路径穿越。

### 1.9 `downloader` — 下载管理器（状态机，见 §2）

- **职责**：队列 + 并发调度 + provider 链回退 + 取消竞态收口 + 库登记。
- **公共 API**：
  - `DownloadManager(engine, library, max_concurrent, auto_retry, jitter_base, jitter_spread, backoff, concurrency, api)`
  - `enqueue(item, appid)` / `enqueue_high_priority` / `enqueue_many` / `enqueue_with_dependencies(item, appid, api, auto_deps, skip_installed, max_depth)`
  - `cancel(job_id)` / `cancel_all()` / `pause_all()` / `resume_all()` / `retry(job_id)` / `retry_all_failed()` / `clear_completed()` / `clear_history()` / `snapshot()`
  - `add_listener(started, progress, finished, queue_changed)`；`on_throttle`（单订阅）
  - `start()` / `stop()`；`paused`（属性）
  - `DownloadJob`（`id` / `status` / `bytes_done` / `total_bytes` / `percent` / `channel` / `signals` / `attempt_messages` / `failure_bucket` / `_stop`）；`JobStatus` 枚举
- **线程模型**：`_run_loop` 是调度线程（daemon `dl-manager`）；每个 job 在独立 daemon 线程 `_exec_job`；回调（`on_started/progress/finished/queue_changed`）**在 job 线程同步触发**——GUI 侧必须经 Qt 信号桥接（`DownloadEventBridge`）。
- **不变量（学费）**：
  1. **`_cancelling` 标记位**（A-P1）：cancel 与完成登记的微秒竞态由「同锁内 add→set→移出→登记」与 worker 侧「同锁内读 pending→决定终态/入库/重试」严格串行收口。取消语义永远胜出，杜绝"取消后仍成功入库/状态被覆盖回成功/finished 双发/_done 重复登记"。
  2. **一条链 = 一次 attempt**：链内 provider 回退不消耗 `auto_retry`（默认 1）。
  3. **E③ 假成功判定**：`SUCCESS` 但 `bytes_done <= 0` 且未取消 → 改判 `FAILED`（steamcmd 偶发报成功但内容未落地）。
  4. **失败必记退避**：`_backoff.record_failure()` + `_concurrency.on_failure()`（并发立刻降到 1）；成功缓慢回升（连续 3 次 +1）。
  5. **`log_job` 失败不得阻塞状态机**：SQLite "database is locked" 等异常若上抛，工作线程死于 `_active` 未清理，调度循环永久挂起（历史上整队假死的根因）。
  6. **`percent` 以字节为准**（u9/u10）：完成回调被 Qt 合并/延迟时，`bytes_done >= total_bytes` 立即 100%，不卡 99%。
  7. **steamcmd 串行化**：`_engine_lock` 对所有 ENGINE 通道（匿名 + 私人账号）共享，两个 steamcmd 进程永不并发；cancel 因此也只作用于当前唯一任务。
  8. **`percent == -1` = 不确定进度**（steamcmd 无逐字节输出）。
  9. 续传语义：`engine.ensure_partial` 报告已有字节写入 `job.resumed_bytes`/`message`；保留 content 目录即"效果续传"（steamcmd 重下时校验差异）。
  10. `_register_to_library` 与终态判定**在同一锁外但登记前**，成功路径才入库；取消路径永不入库。

### 1.10 `throttle` — 退避/抖动/并发自适应/进度平滑（纯逻辑）

- **职责**：把请求节律去机械化，防止 Steam 拒绝；UI 进度平滑。
- **公共 API**：`jittered(base, spread, rng)`；`Backoff(base=2, factor=2, cap=120, ...)`（`record_failure/nudge/record_success/level/level_delay/reset`）；`AdaptiveConcurrency(max_concurrent, min_concurrent, successes_to_raise=3, step=1)`（`current`/`on_failure/on_success/reset`）；`ProgressSmoother(min_interval=0.1, smoothing, window=3.0)`（`reset(bytes_done)` / `feed(bytes_done, total, force)`）；`classify_steamcmd_line(line) -> "rate_limit"|"timeout"|"retry"|None`。
- **线程模型**：全部有锁；下载任务线程与引擎回调/看门狗线程都会写（`_successes += 1` 无锁会丢计数——已付学费）。
- **不变量**：
  - **测试纪律**：本模块是纯逻辑、无 IO，`tests/test_throttle.py` 直接单测；改 core 三件套不能破坏其公开类行为。
  - `ProgressSmoother`：10Hz 限流（完成事件 `force=True` 绕过）、**字节不倒退**（历史最大值钳制）、**滚动窗口速度**（窗口内字节增量 / 真实经过时间——替代 EMA，同时消除"长期 0 MB/s"与"突跳 300MB/s"两种失真）、ETA = 剩余/速度。
  - `classify_steamcmd_line` 严重度排序：`rate_limit` > `timeout` > `retry`；retry 是软信号（蒸汽命令自己在重试，只 `nudge`）。

### 1.11 `steamcmd_engine` — steamcmd 子进程托管

- **职责**：定位/部署 exe、匿名或账号登录、`workshop_download_item`、输出解析、停滞看门狗、取消。
- **公共 API**：`SteamCMDEngine(exe_path, install_dir, anonymous, username, password, guard_code, validate, stall_timeout=60, min_bytes_per_sec=200_000)`；`resolve_exe()`；`deploy()`；`download_item(appid, item_id, on_progress, on_log, total_hint, install_dir) -> DownloadResult`；`ensure_partial(item_id, appid, install_dir)`；`cancel()`；`test_login() -> (ok, msg)`；`content_path(appid, item_id, install_dir)`；`DownloadStatus` / `DownloadResult`。
- **线程模型**：`_run` 读 stdout 的循环线程即调用线程（`download_item` 阻塞调用者）；看门狗独立 daemon 线程；`cancel()` 从任意线程；`_prog_lock` 串行化进度回调（输出线程 + 看门狗共用）。
- **不变量（学费）**：
  1. **`_proc` 实例字段竞态**（bug7/8）：多任务共享引擎时 `_run` 的 finally 会把 `_proc` 置 None；`cancel()` 与 `_run` 内部**一律用局部快照 `proc`**，否则 `NoneType has no attribute poll`。串行锁是根因治疗，局部快像是双保险。
  2. **steamcmd 同会话不支持并发**：manager 的 `_engine_lock` 保证串行。
  3. **进度来源现实**：`workshop_download_item` 不输出逐字节进度（fixtures 实证），只有 `Downloading item X` → `Success. ... (N bytes)`。实时进度来自 ① 百分比行/Update state 行（部分游戏）② content + downloads 临时目录磁盘增长（看门狗兼做进度源）。三者皆无则不确定进度。
  4. **downloads 临时目录**：`content_dir` 向上剥 3 层到 workshop 再进 `downloads/<appid>/<item>`，只扫 content 会"恒 0% 直到跳 100%"（bug5）。
  5. **停滞看门狗**：静默超过 `stall_timeout`（且无磁盘增长）终止进程判失败；原子落盘物品（GMod .gma）按 `total_hint / min_bytes_per_sec` 放宽上限，避免大文件误杀。
  6. **账号信息过滤**：`_redact_secrets` 在日志与 `on_line` 之前执行；解析正则只匹配固定串（"Logged-in OK" 等），替换不影响解析。
  7. exe 解析优先级：用户指定 > 已部署内置 > 系统安装 > 内置 zip 解压 > 在线下载（最后手段）。
  8. 内容布局：`<install_dir>/steamapps/workshop/content/<appid>/<item_id>/`；legacy 单文件 mod 的 Success 行报告 `_legacy.bin` 路径，`downloader._normalize_content_path` 统一回退到目录。

### 1.12 `providers` — 下载通道抽象与注册表

- **职责**：统一 ENGINE/HTTP/PROXY 三类通道；回退链构造；通道级熔断。
- **公共 API**：
  - `DownloadProvider`（ABC）：`probe(timeout) -> Availability`；`download(item, dest_dir, on_progress, stop_event, total_hint) -> DownloadResult`；`cancel()`；`resolve(item) -> str`；`should_fallback(result) -> bool`；`is_configured() -> bool`；共享件 `http_download(url, dest_path, session, on_progress, stop_event, chunk_size, timeout)` 与 `_report_throttle(kind, line)`。
  - `ProviderMeta`（frozen dataclass）：`name/display_name/kind/requires_key/key_hint/anonymous_ok/priority/supported_appids/config_fields/terminal/supports_account/breaker_exempt`。
  - `get_registry()` → `ProviderRegistry`：`register(cls)`；`get_provider(name, api)`；`build_chain(preferred, api) -> list[DownloadProvider]`；`record_failure/record_success(name)`；`list_channels(api) -> [(name, display_name, availability)]`。
- **线程模型**：`download()` 在 manager 工作线程内同步阻塞；`cancel()` 可能从 GUI 线程调用（须线程安全）；registry 单例锁保护实例缓存。
- **不变量（学费）**：
  1. **terminal 语义**：`meta.terminal=True` 的通道（steamcmd）是链终结者——`build_chain` 到它即停止追加；它**永不熔断**（熔断兜底会让链变空）；`should_fallback()` 恒 False。
  2. **链尾永远是 steamcmd**（除非它自己是首选则不重复）；用户禁用的/熔断中的/缺凭据的通道跳过（**跳过而非报错——匿名可用性是核心卖点**）。
  3. **熔断器** `_Circuit`：连续 3 次失败 → 60s 冷却；半开时保留 `_fail = threshold - 1`（一次失败立即重熔，标准半开语义）。
  4. **`breaker_exempt`**（私人账号通道）：凭据失败不熔断任何通道，尤其不熔断 steamcmd 兜底（t31 风控③）。
  5. **`should_fallback` 结构化判定**（取代旧消息含"回退"字符串判定）；取消永不回退（用户主动行为）。
  6. **实例缓存按 config 快照引用重建**：`get_provider` 比较 `id(cfg)`，配置变更自动重建；api 可晚注入。
  7. **`http_download`**：Range 续传（服务器返回 200 而非 206 时丢弃已有部分重下）；逐 chunk 轮询 `stop_event`；429 上报限流信号；取消时保留已写部分。
  8. 通道元数据（当前）：steamcmd（ENGINE, terminal, priority 100, 匿名）/ account_steamcmd（ENGINE, priority 90, `supports_account`, `breaker_exempt`, 匿名态自动跳过——**默认链不含**）/ cdn（HTTP, priority 10, `anonymous_ok=False`——匿名时 file_url 为空自动回退）/ ggnetwork（PROXY, priority 20, 匿名代理，自律 20 req/min 令牌桶 + 突发 3）。
  9. **GGNetwork 学费**：api 返回的是落地页 URL（`ggntw.com/download/<token>`），真实文件在 `cdn.ggntw.com/<token>`；`queue.position > 0` 且**同时带 url** 时 url 可用（旧守卫把每个真实物品丢弃）；返回 zip 先解压再 .gma 魔数弱校验 + >1% 尺寸差异判坏包（FAILED + 链内回退，t28）；探测物品须轮换（固定 id 下架后后端只回误导文案）。
  10. **账号通道会话级失活**：登录失败一次后 `_auth_dead` 本轮不再尝试（避免轰炸 Steam 登录服务器），用户改凭据时 `reset_auth_state` 重开。

### 1.13 `steamcmd_deploy` — 内置 steamcmd 分发

- **职责**：随程序分发的官方 steamcmd.zip 的解压部署。不变量：仅含 steamcmd.exe，首次运行自更新补齐组件；`has_bundled_zip()` / `deploy()`；解压目标恒为 `STEAMCMD_DIR`。

### 1.14 `mod_library` — 本地 mod 库（SQLite）

- **职责**：mod 记录存储（publishedfileid 主键 + appid）；分类/检索/启停/收藏；任务历史；磁盘组织。
- **公共 API**：`ModLibrary(db_path=DB_FILE)`；`upsert(rec)` / `delete(item_id, remove_files)` / `set_enabled` / `set_category` / `set_favorite` / `set_notes`；`get(item_id)` / `all()` / `search(keyword, appid, category, tag, enabled_only, disabled_only, favorites_only, sort)` / `categories(appid)` / `all_tags(appid)` / `stats()`；`log_job(...)` / `job_history(limit)`；`organize_path` / `write_metadata_sidecar(rec)` / `import_existing(library_dir, appid)`；`ModRecord`。
- **线程模型**：`RLock` 包裹每个公开方法；每次操作新建连接（`sqlite3.connect(timeout=30)`）。
- **不变量（学费）**：
  1. **连接超时 30s**：默认 5s 在并发写/多实例下易抛 "database is locked"。
  2. **每次操作新连接**（不用共享连接对象），锁在应用层；`log_job` 失败被 download 层 catch（不阻塞状态机）。
  3. **`upsert` 的 `ON CONFLICT` 保留用户元数据**：`category/notes/favorite` 重新下载时不覆盖。
  4. tags / dependencies 以 JSON 数组串存储；`tags LIKE '%tag%'` 做标签过滤。
  5. 元数据旁车 `swdm_meta.json` 写在 mod 内容目录旁（legacy 单文件取目录），支持离线检索/迁移。
  6. 迁移纪律：`_MIGRATIONS` 用 `ALTER TABLE ... ADD COLUMN` + OperationalError 跳过兼容旧库。

### 1.15 `failure_reason` — 失败原因归类（纯函数）

- **职责**：把 steamcmd 不区分原因的失败文案保守归一为用户可读桶。
- **公共 API**：`classify_failure(message, *, appid, signals, attempt_messages, restricted_apps=RESTRICTED_APPS) -> FailureBucket`；`render_failure(bucket, raw) -> str`；`FailureBucket` 枚举；`RESTRICTED_APPS`（目前：221100 DayZ、602960 Barotrauma）。
- **线程模型**：纯函数，无状态、无 IO。
- **不变量**：
  - **误报红线（t31 决议）**：通用 I/O 失败**绝不**映射"需正版账号"——误报比不报更伤。只有两条正向信号可提示账号：① 受限 App + 匿名下载未开始；② 重试用尽后仍同一错误且本次无 rate_limit/timeout 信号。
  - 与熔断器正交：熔断管通道健康度，本模块管单物品可读结论。
  - 与 downloader 的契约：`job.signals`（本次运行特征）+ `job.attempt_messages`（历次文案）是入参；输出写回 `job.failure_bucket` 与 `job.message`，原文保留在日志。

### 1.16 `games` / `game_dirs` — 游戏注册表与按游戏目录

- **职责**：appid ↔ 名称（内置 60+ 工坊游戏 + 用户自定义 + 中文别名离线表）；按 appid 覆盖下载目录。
- **公共 API**：`list_builtin()` / `list_custom()` / `add_custom` / `remove_custom` / `all_games()` / `game_name(appid)`；`GAME_ALIASES`；`game_install_dir(appid, cfg)` / `game_content_root` / `set_game_dir` / `clear_game_dir` / `configured_game_dirs` / `game_dir_entries`。
- **不变量**：未知 appid 回退 `AppID N`；别名键经归一化匹配，是 storesearch 的离线兜底；目录配置存 `config.game_dirs.{appid}`，未配置回退全局 `LIBRARY_DIR`。

### 1.17 `auth` — 账号管理

- **职责**：匿名（默认）/ 用户登录（keyring 加密 + Steam Guard）。
- **公共 API**：`AuthManager()`；`account`（属性）；`is_anonymous()`；`login_anonymous()` / `login_user(username, password, guard_code, remember)` / `logout()` / `get_credentials() -> (username, password, guard_code)` / `clear_stored()`。
- **不变量**：keyring 优先、本地 base64 混淆文件弱保护兜底；**凭据永不进 config/日志/导出**；`auth.json` 只存用户名 + 标志位。

### 1.18 解析器三件套（`hub_parser` / `page_parser` / `deps_parser`）

- **职责**：纯函数 HTML 解析——新 hub 页 React Query 脱水状态 / 详情页描述与评论与浏览页标签 / 前置依赖。
- **公共 API**：`extract_results(html) -> (results, total, pages)` / `browse_hub(...)`；`parse_description` / `parse_comments` / `parse_available_tags_with_counts` / `fetch_comments`；`parse_required_items(html)` / `parse_required_items_with_titles(html)` / `parse_required_items_robust(html)`。
- **不变量**：**全部纯函数、无网络、无副作用、fixtures 直接回归测试**；多层转义 JSON 的 `_unescape` 收敛循环；div 配对切片（不能贪心到首个 `</div>`）；依赖链接路径是 `/workshop/filedetails/`（非 sharedfiles）。

---

## 2. 下载状态机（完整状态转移）

两层数据：**`JobStatus`（job 生命周期，UI 可见）** 与 `DownloadStatus`（单次通道结果，内部）。任务描述的 PENDING 状态在实现中为 `QUEUED`（同义，2.0 命名统一建议见 §6.3）。

### 2.1 状态转移图（文字版）

```
                    ┌────────────────────────────────────────────┐
                    │                                            │
   enqueue ──────► QUEUED ──────────► [调度派发] ──────────► RUNNING ──┐
                    │  ▲                    │                    │   │
                    │  │                    │ _paused=True       │   │
                    │  │                    │ 暂停派发（在途      │   │
   cancel(排队中)    │  └ resume_all        │ 任务继续跑完）       │   │
   ──► CANCELLED    │                       │                    │   │
                    │                       │ ┌──────────────────┘   │
                    │                       │ │                      │
                    │                  _exec_job:                   │
                    │                  throttle_wait(抖动+退避)       │
                    │                       │                      │
                    │              [等待期 _stop 已置?] ───► CANCELLED (retire)
                    │                       │                      │
                    │              ensure_partial(续传报告)          │
                    │                       │                      │
                    │              _run_channel_chain               │
                    │              (provider 链: 首选→按 priority→   │
                    │               steamcmd 终端尾)                │
                    │                       │                      │
                    │                       ├── SUCCESS & bytes>0 ─► SUCCESS ──► 入库 upsert
                    │                       │   （0 字节假成功 E③ ─► FAILED 分支）
                    │                       ├── CANCELLED(_stop) ──► CANCELLED
                    │                       │   （_cancelling 已登记?)
                    │                       │      是 → CANCELLED 胜出，不入库
                    │                       │      否 → CANCELLED（worker 登记）
                    │                       └── FAILED ─┬─ attempt < auto_retry
                    │                                   │   且未取消 → 原子重入队
                    │                                   │   （保持 RUNNING，重试中）
                    │                                   └─ 用尽 → FAILED
                    │                                              + failure_reason 归类
                    │                                              + 退避/并发降级
                    │                                                       │
   retry() ◄───────────────────────────────────────────────────────────────┘
   （从 _done 移除旧 job，清 _cancelling 残留标记，重新入队）
```

### 2.2 触发条件与守卫（逐条）

| 转移 | 触发 | 守卫/不变量 |
|---|---|---|
| → QUEUED | `enqueue` / `enqueue_high_priority` / `retry` | 同 id 在 `_queue` 或 `_active` 则跳过（幂等） |
| QUEUED → RUNNING | `_run_loop`：队列非空 && 未暂停 && `len(_active) < _concurrency.current` | `current` 由自适应策略决定，**不是配置的 max** |
| RUNNING → SUCCESS | 链路返回 `SUCCESS` 且 `bytes_done > 0`，且无 pending-cancel | 同锁内判定 + `_register_to_library` |
| RUNNING → FAILED | 链路失败且重试用尽，或"所有通道均不可用" | `failure_reason.classify_failure` 归类；`_backoff` 升级 + 并发降 1 |
| RUNNING → CANCELLED | `cancel()` 抢先登记（`_cancelling.add` + `_stop.set` + 移出 `_active` + 登记 `_done` + fire finished） | 终态 job（SUCCESS/FAILED）不可取消（early-return，真实结果不被抹掉） |
| 运行中完成瞬间被取消 | `_exec_job` 终态判定块见 pending-cancel | 保持 CANCELLED，**不导入库**（取消语义胜出） |
| RUNNING → 重试（保持 RUNNING） | `attempt < auto_retry(=1)` 且未取消 | 判定与重新入队在同一锁内（cancel 无法插在中间复活已取消任务）；重试期间状态保持 RUNNING（轮询方不误判终态） |
| 任意 → CANCELLED(retire) | `_retire_cancelled` / 等待期 `_stop` | `_cancelling.discard` + `_active` 移出原子完成，与 cancel 路径互斥（`_done` 不重复登记、finished 不双发） |
| 队列级 PAUSED | `pause_all()` | 进行中跑完，队列内不派发；`_cond.wait(0.5)` 轮询恢复 |
| 历史 | `clear_completed` / `clear_history` | 只清 `_done` |

**状态机总不变量**：终态（SUCCESS/FAILED/CANCELLED）一旦在锁内确定即不可被另一路径覆盖；`_done` 中每个 job 只被登记一次；`finished` 回调对每个 job 只 fire 一次。

---

## 3. Qt 线程规矩清单（已付学费，2.0 必须继承）

> 每条后面是**事故或回归点**。这些规矩与语言无关——换栈时同样适用。

### 3.1 QThread 生命周期（m1 / SIGSEGV 事故）

- **规矩**：无 C++ parent 的 `QThread`（Python 包装器是唯一持有者）**必须进保活池**（`workshop_tab._BG_THREADS` + `_register_bg_thread`），`finished` 后才移除；进程退出时 `atexit` 有界等待（`requestInterruption` + `wait(2000)`）。
- **学费**：旧实现把 worker 存进单一 `self._xxx_worker` 属性，新请求覆盖属性后旧引用归零 → GC 在 `run()` 尚未返回时析构 C++ 对象 → `QThread: Destroyed while thread is still running` → **SIGSEGV**。覆盖点：`_SearchWorker`、`BrowseWorker`、`_TagsFetchWorker`、`_PrefetchWorker`、`DependencyResolveWorker`。退出阶段 GC 踩同一颗雷（atexit 闸覆盖）。
- **推论**：任何"持有 worker 引用"的属性都只是兼容旧外部引用，真实保活在池里。

### 3.2 跨线程回调必须守卫目标存活

- **规矩**：子线程向主线程发信号 / 回调时，信号源或目标可能已被销毁——`emit` 与回调入口须 `try/except RuntimeError`（'Signal source has been deleted' / deleted QLabel）。
- **学费**：`workers._ImageTask` / `_ImageDownloadTask` 的 `_image_bus.ready.emit`、`workshop_tab._on_image_loaded`（deleted QLabel + 死索引清理）、`detail_dialog.PreviewImageWorker.run` 的全 emit 守卫（m1 修复项）。
- **规矩（更根本的）**：`QPixmap` 只能在主线程构造；子线程只下载原始字节/解析本地路径，经排队信号回主线程解码。**这是 Qt 线程安全的硬约束，不是风格选择。**

### 3.3 core 回调须经 Qt 信号桥接

- **规矩**：`DownloadManager` 的 `on_started/progress/finished/queue_changed` 在 job 线程同步触发；GUI 侧必须经 `DownloadEventBridge`（QObject + Signal）桥接回主线程，否则跨线程操作控件会冻结/崩溃。
- **订阅模型**：`on_throttle_signal` 与 `on_*` 用 **append 订阅**（A-P3：后赋值不覆盖既有订阅者）。

### 3.4 禁止 clear()/popup 竞争（联想下拉）

- **规矩**：`QComboBox.clear()` + `addItem` 会把内部 `currentIndex` 变为 0，`currentText` 与 `lineEdit` 文本不一致（回车/`currentData` 错读）。正确姿势：`blockSignals(True)` → `clear()` → 填充 → `setCurrentIndex(-1)` → `blockSignals(False)` → 恢复 `lineEdit` 文本。
- **规矩**：`_current_appid` 类解析必须容忍**纯名字 / 全格式 `Name  (appid)`** 两种下拉项形态（按 `(` split 取名字部分）——m1 修复的解析恒落空 bug。

### 3.5 弹窗不是真实阻塞（测试纪律）

- **规矩**：单测中把 `QMessageBox.question/information` 换成普通函数后，调用方「询问 → 入队 → 清标红」会**同步执行完**；断言"弹窗时的中间态"必须在桩函数内部捕获（`marked["ids"] = set(...)`），弹窗返回后再查已被清空。
- **通用教训**：Qt 模态弹窗的真实事件循环语义无法被同步函数桩复现，跨"弹窗边界"的状态断言一律在桩内采样。

### 3.6 去抖、代际号与缓存（联想/列表请求）

- **规矩**：storesearch 12 次连发触发 WinSock 10053 连接熔断（15s 恢复）→ 联想必须去抖 + 在途取消（版本号 `_search_version` 过滤旧结果）+ 内存缓存 + 熔断冷却重发待发词。
- **规矩**：快速切游戏/翻页时用**代际号**（`BrowseWorker.generation` / `_worker_gen`）丢弃过期结果，不是锁或取消（网络请求发出了就回不来）。
- **规矩**：图片缓存超上限用 LRU 淘汰最旧条目，**禁止 `_image_cache.clear()` 全清**（O3：全清导致当前可见卡片全部重下、网络请求突刺）。
- **规矩**：禁止主线程同步 HTTP 下载（`_build_pixmap` 旧实现阻塞最长 20s 是"无响应"直接来源）——丢回线程池异步下。

### 3.7 布局与可见性陷阱

- **规矩**：`QTabWidget` 非当前页整页隐藏，页面内子件 `isVisible()` 恒 False；空态/几何断言须先 `setCurrentWidget(tab)` 或用 `isHidden()`。
- **规矩**：`QLabel`（`wordWrap=False`）的 `minimumSizeHint` = 全文宽度，会把卡片布局顶到文本宽度导致裁切——用可压缩 `minimumSizeHint`（`_ElidedLabel`）。
- **规矩**：QSS 无 `box-shadow`，高程用「明度阶梯 + 描边」的 Steam 式路线（`QGraphicsDropShadowEffect` 留给对话框/悬浮卡）。
- **规矩**：动画用 `QPropertyAnimation` 时注意持有关系（animation 的 parent 陷阱，与 §3.1 同源的强引用问题）。

---

## 4. 可保留 vs 需重写清单

### 4.1 本质复杂度（2.0 必须原样保留逻辑，换栈也照搬）

| 复杂度 | 为什么是本质的 | 载体 |
|---|---|---|
| steamcmd 串行化 | steamcmd 同会话不支持并发，共享 `_proc` 会竞态崩溃 | `downloader._engine_lock` + 引擎局部快照 |
| 匿名下载流 | 核心卖点；file_url 匿名为空、CDN 通道自动回退是 Steam 的许可层设计 | providers 链 + `CDNProvider` |
| 429/403 指纹与分层对策 | 34 次实测的请求头指纹知识 + 403 快速失败 + 限流降级缓存兜底，是**经验资产**不是代码债 | `steam_api._community_get` / `_endpoint_throttle` / `RateLimitError` |
| provider 链回退 + terminal 语义 + 熔断 | 通道健康度与回退是分布式系统的本质问题 | `providers/registry.py` + `_Circuit` |
| steamcmd 输出解析 | 无逐字节输出、downloads 临时目录、停滞看门狗、0 字节假成功——全部是 valves 行为的经验事实 | `steamcmd_engine.py` |
| 取消竞态收口 | 微秒级竞态是状态机的本质，`_cancelling` 双方加锁串行是正确解 | `downloader.cancel` / `_exec_job` |
| SQLite 并发写 | "database is locked" 是 SQLite 的本质行为；30s 超时 + 应用层锁 + 失败不阻塞 | `mod_library` |
| 双解析浏览页（经典 SSR + hub 脱水） | Steam 自己在迁移渲染方案，客户端必须双支持 | `steam_api` + `hub_parser` |
| 失败原因保守归类 | steamcmd 不区分权限/网络/限流是 valve 的已知痛点 | `failure_reason.py` |
| 熔断/退避/并发自适应/进度平滑 | 反爬与 UI 频控的通用算法，纯逻辑可单测 | `throttle.py` / `circuit.py` |

### 4.2 意外复杂度（2.0 重写的目标）

| 债 | 现状 | 重写方向 |
|---|---|---|
| **workshop_tab 巨型类** | 1761 行单类：游戏选择器 + 联想 + 标签栏 + 分页 + 卡片容器 + 预取 + 下载接线 + URL 导入 + 冲突徽标 | 按组件拆分（游戏选择器 / 列表容器 / 卡片 / 预取管理器），各带自己的契约测试 |
| **联想 clear() 重建** | 每次输入都 clear+addItem+恢复文本，currentIndex/文本一致性靠手工维护 | 换 model/view：`QStandardItemModel` 或 `QCompleter`，增量更新替代重建 |
| **去抖 + 代际号混用** | `_refresh_timer`(350ms 去抖) + `_worker_gen` + `_search_by_gen`/`_tags_by_gen` 手工字典 + 截断逻辑，四套机制耦合 | 单一"请求代际管理器"：去抖、代际、在途追踪、结果丢弃一站式 |
| **隐式单例群** | `get_config()` / `get_api_cache()` / `get_registry()` / `get_detail_cache()` 全局可取，模块间互相隐式依赖 | 显式依赖注入（Services 容器升级为构造注入 + 生命周期管理） |
| GUI 层自建核心客户端 | `workers._ImageTask` 自建 `SteamAPI` 实例（session/代理配置漂移） | 统一经 Services 取已配置实例 |
| 单一 `self._xxx_worker` 属性引用 | 已用保活池根治，但引用模式散落各处 | 统一后台任务管理器（池 + 代际 + 取消为一体） |
| `on_throttle` 单订阅 vs 列表订阅 | `DownloadManager.on_throttle` 是单值赋值，其余已是 append | 全部统一为 append 订阅 |
| 回调式观察者 | `add_listener` 回调在子线程触发，每个 GUI 侧都要自建桥 | 事件总线（core 发事件、GUI 订阅，边界唯一） |
| core 测试入口混杂 GUI 前提 | 部分 core 测试需先设 APPDATA 临时目录等环境 | 契约测试与环境解耦（fixture 注入临时目录） |

---

## 5. 数据流图（app 启动 → 选游戏 → browse/enrich → 卡片 → 详情 → 下载 → 入库）

### 5.1 启动序列

```
app.main()
  ├─ QApplication 高 DPI 策略（PassThrough）
  ├─ ensure_dirs() → paths：DATA_DIR/cache/logs/steamcmd/mods 五目录
  ├─ get_config() → config：加载 config.json + 三层递归合并默认值
  ├─ setup_logger(level) → logger：轮转文件 + 环形缓冲
  ├─ install_exception_handler()（崩溃落 CRASH_FILE）
  ├─ QApplication；单实例保护（QLocalSocket "swdm-single-instance"）
  ├─ MainWindow()
  │    ├─ build_services()  ← 核心装配点
  │    │    ├─ get_config()（再 load 一次，热重配置）
  │    │    ├─ AuthManager()（keyring / auth.json）
  │    │    ├─ SteamAPI(api_key, proxy, timeout)（注入 truststore + UA + Accept-Language + 系统代理探测）
  │    │    ├─ ModLibrary()（建表 + 迁移）
  │    │    ├─ SteamCMDEngine(匿名共享引擎)
  │    │    ├─ DownloadManager(engine, library, max_concurrent, auto_retry=1, api=api)
  │    │    │    └─ 订阅 engine.on_throttle_signal → 退避/并发自适应
  │    │    └─ Services.refresh_engine()（引擎参数同步 + 账号通道 set_auth_manager/reset_auth_state）
  │    ├─ downloader.start()（dl-manager 调度线程）
  │    ├─ 五个 Tab 构造（WorkshopTab / DownloadsTab / LibraryTab / SettingsTab / DebugTab）
  │    ├─ DownloadEventBridge × 2（main 的 finished→库刷新/托盘通知；workshop 的 progress/finished→卡片）
  │    └─ 跨 Tab 信号接线（library_changed / records_removed / show_downloads / navigate_requested）
  └─ app.exec()
```

### 5.2 选游戏（联想）

```
用户在 game_combo 输入
  ├─ 本地匹配（_local_game_matches：all_games() + 收藏 + 自定义，零网络）
  ├─ 去抖 + 版本号 _search_version+1
  ├─ GameSearchClient.cached(term)（5 分钟缓存优先）
  ├─ 熔断冷却中？ → 记 _pending_search_term，定时器冷却后重发一次
  └─ _SearchWorker(QThread, 进保活池)
       └─ client.search(term)：0.7s 最低间隔 + storesearch + type=app 过滤 + DLC 启发排除
            └─ ready.emit(results, version) → 版本不匹配则丢弃
                 └─ _fill_search_results（clear + currentIndex=-1 姿势）
                      └─ _on_search_ready：本地+网络合并去重排序 → _last_search_pairs 缓存
   选中/回车 → _current_appid()（容忍纯名字/全格式，'(' split 回退 _last_search_pairs）
                → game_combo.currentIndexChanged → _refresh_list()
```

### 5.3 列表加载（browse / enrich / 卡片）

```
_refresh_list()
  ├─ 分页 UI 同步（立即：页码、上一页禁用态）
  └─ _refresh_timer 去抖 350ms → _do_refresh_list()
       ├─ _current_appid() 解析；为空 → 提示"请先选择游戏"
       ├─ 在途 worker？ → _pending_refresh=True，完成后自动重跑（不丢弃请求）
       ├─ _clear_cards()；_nextpage_timer.stop()
       ├─ _worker_gen += 1（旧结果作废）；_search_by_gen/_tags_by_gen 记录本次维度
       └─ BrowseWorker(QThread, 进保活池, generation=gen)
            ├─ api.api_key? → query_files（结构化查询，需 key）
            │                 否 → api.browse(...)
            │                      ├─ api_cache.get(make_cache_key(...))（命中深拷贝、零请求）
            │                      ├─ _community_get（全局节流 + 端点节流 + 429 退避/403 快败）
            │                      ├─ _parse_cards（经典 SSR 正则）→ 0 卡片则 _parse_hub_inline
            │                      └─ cache.set + breaker.record_success + 返回深拷贝
            ├─ progress.emit → status_label
            └─ enrich（分批 50 调 get_file_details，就地补全元数据）
                 └─ items_ready.emit(items)
                      └─ gen != _worker_gen → 丢弃（过期代际）
                           ├─ apply_browse_search_fallback（0 命中按作者过滤/低命中提示）
                           ├─ filter_items_by_tags（客户端精确交集）
                           └─ 渲染卡片（ModCardWidget）
                                 └─ ImageLoader.load(url)
                                      ├─ data: 占位图 → 主线程直接解码
                                      ├<arg_value> _image_cache 命中（LRU move_to_end）
                                      └─ _ImageTask(QRunnable, 线程池)
                                           └─ api.fetch_image → 磁盘缓存 30 天
                                                └─ _image_bus.ready(url, path)（子→主信号）
                                                     └─ _build_pixmap（主线程构造 QPixmap + 缩放）
                                                          └─ loaded.emit(url, pixmap)
                                                               └─ _on_image_loaded（守卫 deleted 目标 + 死索引清理）
   并行投机：悬停 400ms → _PrefetchWorker 预取详情（priority 礼让用户点击）
             渲染完成 800ms → 下一页预取（B2，命中缓存零网络）
```

### 5.4 详情与下载

```
点击卡片 / 双击
  ├─ detail_cache.get(item_id, time_updated)（TTL+双失效，hit 零请求）
  └─ DetailPageWorker(QThread)
       ├─ _community_get(/sharedfiles/filedetails/, priority=True)
       ├─ page_parser：描述/评论/标签；deps_parser：RequiredItems
       └─ 详情就绪 → ModDetailDialog（非模态，可常驻列表旁）
            ├─ 预览图：PreviewImageWorker（emit 全守卫）
            └─ 下载按钮 → downloader.enqueue_with_dependencies(item, appid, api)
                 ├─ DependencyResolveWorker 或直接 api.resolve_dependency_tree
                 │    （BFS + visited 防循环 + 深度截断 + skip_installed）
                 ├─ 依赖在前本物在后逐个 enqueue（幂等去重）
                 └─ show_downloads 信号 → 切到下载页（bug1 即时反馈）
```

### 5.5 下载执行与入库

```
dl-manager 调度循环
  └─ 条件：队列非空 && 未暂停 && len(_active) < _concurrency.current
       └─ _exec_job(job)（独立 daemon 线程）
            ├─ _throttle_wait（抖动 jitter_base + 退避等级延迟）
            ├─ 等待期被取消 → _retire_cancelled
            ├─ fire started；configured_game_dirs() 解析专属目录
            ├─ engine.ensure_partial → resumed_bytes/"续传中（已有 N MB）"
            ├─ ProgressSmoother（10Hz + 不倒退 + 滚动窗口速度/ETA）
            ├─ _run_channel_chain
            │    ├─ build_chain(preferred=config.download.channel)
            │    │    （禁用/熔断/缺凭据跳过，steamcmd 永远链尾）
            │    └─ 逐通道运行：
            │         ENGINE(steamcmd/account_steamcmd) → _run_steamcmd（串行锁）
            │         HTTP/PROXY(cdn/ggnetwork) → provider.download（dest_dir=content/<appid>/<id>）
            │         成功 → record_success；失败（非 terminal/非豁免）→ 熔断计数
            │         should_fallback False 或 stop_event → 返回
            ├─ 进度回调 → job → on_progress → DownloadEventBridge → 主线程 → 卡片迷你进度条
            ├─ 终态判定（A-P1 锁内串行，见 §2.2 表）
            ├─ SUCCESS：_backoff.record_success + 并发回升 + _register_to_library
            │    └─ library.upsert（保留 category/notes/favorite）+ write_metadata_sidecar
            ├─ FAILED：failure_reason 归类 → job.failure_bucket + 用户可读文案
            └─ library.log_job（失败被 catch，不阻塞状态机）
                 └─ fire finished（只一次）→ 库页刷新 / 托盘通知 / 卡片状态更新
```

---

## 6. 2.0 契约级建议（给讨论组的备忘）

1. **§1 的每个不变量都应变成契约测试**：api_cache 深拷贝、节流锁覆盖、terminal 语义、_cancelling 竞态、双失效缓存、30s 锁超时……当前 87+ 回归套件已覆盖大半，缺的是"模块契约"层的显式清单（本文档即清单草稿）。
2. **命名统一**：`QUEUED` ↔ 任务描述中的 `PENDING`；`PENDING` 语义在实现中由 `_pending_refresh`/`_pending_search_term` 承担，2.0 建议把 job 显式 `PENDING` 状态引入状态机，消除"待执行"的隐式标志位。
3. **core 无 Qt 化验证手段**：`python -m swdm.core`（或 pytest 只导入 core）必须在不安装 PySide6 的环境可跑——这是阶段一完成的可验证判据。
4. workers.py 的 `DownloadEventBridge.attach` 用赋值（`mgr.on_started = ...`）而非 append，与 §3.3 的 append 纪律不一致，属待清理项。

---

## 附录：契约与代码的对应索引

| 契约 | 代码位置 |
|---|---|
| api_cache 深拷贝 | `steam_api.browse()` 四处 deepcopy；`api_cache` docstring |
| 端点节流表 | `steam_api._ENDPOINT_INTERVALS`（3s/2s/3s，历史 6s） |
| 429/403 分层 | `steam_api._community_get`；`RateLimitError` |
| terminal 语义 | `providers/base.ProviderMeta.terminal`；`registry.build_chain`；`SteamCMDProvider.should_fallback` |
| 熔断器 | `providers/registry._Circuit`；`circuit.CircuitBreaker` |
| _cancelling 收口 | `downloader.cancel` / `_exec_job` / `_retire_cancelled` |
| E③ 假成功 | `downloader._exec_job`（SUCCESS & bytes<=0） |
| steamcmd 串行 | `downloader._engine_lock` / `_run_steamcmd` |
| _proc 局部快照 | `steamcmd_engine._run` / `cancel` |
| 进度平滑 | `throttle.ProgressSmoother`；`downloader._on_engine_progress` |
| QThread 保活池 | `workshop_tab._BG_THREADS` / `_register_bg_thread` / `atexit` |
| 图片回调守卫 | `workers._ImageTask` / `_ImageDownloadTask`；`workshop_tab._on_image_loaded`；`detail_dialog.PreviewImageWorker` |
| 双失效缓存 | `detail_cache.get`（TTL + time_updated） |
| SQLite 锁 | `mod_library._conn(timeout=30)` |
| 失败归类红线 | `failure_reason.classify_failure` |
| 账号会话级失活 | `providers/account_steamcmd._auth_dead` / `reset_auth_state` |
| 凭据不落盘/日志 | `auth.py`（keyring）；`steamcmd_engine._redact_secrets` |
