# SWDM 多 Provider 下载架构适配设计

> 状态：纯设计文档，不含代码改动。
> 目标：在不破坏现有 steamcmd/CDN 双通道的前提下，引入可扩展的下载 provider 抽象，为新增的 steamwebapi / GGNetwork / Nether / SWD 四个第三方 provider 铺路。
> 配套调研：`research/provider_research.md`（4 个第三方 provider 的 API / 认证 / 匿名可用性 / 速率限制）。

---

## 1. 现有下载调用链（文件:行号）

### 1.1 完整链路图

```
UI 点击下载
  workshop_tab.py:1007   card.download_requested  ──► _download_item
  workshop_tab.py:1133   _download_item(item_id) ──► _download_with_deps
  workshop_tab.py:1140   _download_selected（批量勾选）
  workshop_tab.py:1150   _download_with_deps
  workshop_tab.py:1162   svc.downloader.enqueue(it, appid)      ← 入队点
  detail_dialog.py:1085/1103/1105/1122  详情页下载（同 enqueue）
  workshop_tab.py:1230   enqueue_high_priority（依赖插队首）
  workshop_tab.py:1475   批量对话框下载

队列与调度（core/downloader.py）
  :162  enqueue()              构造 DownloadJob → _queue.append → _cond.notify
  :381  _run_loop()            持锁等待队列 → 并发闸门（_concurrency.current）
  :397  queue.popleft          → _active[job.id]
  :399  threading.Thread(_exec_job)
  :439  _exec_job(job)         单任务执行（核心）
     :441  _throttle_wait       抖动 + 退避等待（throttle.py jittered/Backoff）
     :450-456  install_dir      configured_game_dirs() 按游戏解析目录
     :461  engine.ensure_partial  续传探测（已有字节数）
     :473-474  ProgressSmoother(min_interval=0.1).reset(resumed_bytes)
     :476-484  读 config download.channel（默认 "steamcmd"）
     :487  if channel == "cdn" → _download_via_cdn  → 失败且消息含"回退" → _run_steamcmd
            else               → _run_steamcmd
     :504-512  0 字节假成功改判失败
     :513-543  状态判定 / 退避 / 自动重试（再入队）
     :524  _register_to_library
     :550  library.log_job（SQLite 历史）
     :562  _fire_finished

通道实现
  downloader.py:403  _run_steamcmd   持 _engine_lock 串行 → engine.download_item
  downloader.py:418  _download_via_cdn
     :425  from .cdn_downloader import download_item_cdn
     :428-431  dest_dir = <install_dir>/steamapps/workshop/content/<appid>/<itemid>
     :432  download_item_cdn(job.item, dest_dir, api=self.api, on_progress=_on_engine_progress)
  steamcmd_engine.py:286  download_item  → _run() 子进程 → on_line 解析 → :463 emit(100,...)
  cdn_downloader.py:131  download_item_cdn → :148 resolve_file_url → :163 download_file（Range 续传）

进度上报（统一协议 on_progress(pct, done, msg)）
  downloader.py:568  _on_engine_progress(job, smoother, pct, done, msg)
     :578  smoother.feed(done, total, force=(pct>=100))   10Hz 限流 + 字节不倒退 + 速度/ETA
     :581-591  写 job.bytes_done / speed_mbps / eta_seconds / message
     :592  _fire_progress(job)

GUI 桥接（子线程 → 主线程，Qt 信号）
  downloads_tab.py:113  mgr.add_listener(started/progress/finished/queue_changed)
  workshop_tab.py:327   svc.downloader.add_listener(progress/finished)  ← 卡片迷你进度条
  gui/workers.py        DownloadEventBridge（Qt 信号）

完成入库
  downloader.py:595  _register_to_library  → ModLibrary.upsert + write_metadata_sidecar
  downloader.py:629  _normalize_content_path  统一规范化到 content/<appid>/<itemid>

取消
  downloads_tab.py:146  mgr.cancel(job_id)
  downloader.py:250  cancel() → job._stop.set() + engine.cancel()
  steamcmd_engine.py:496  cancel() → _cancel_flag + stdin "quit" + terminate

服务装配
  gui/services.py:61  build_services() → :71 SteamCMDEngine → :78 DownloadManager(engine, library, ...)
  gui/services.py:29  refresh_engine()：账号态 / exe 路径 / install_dir / 并发数热更新
```

### 1.2 关键结论

- **通道选择只在一处**：`downloader.py:476-494` 的 `_exec_job` 内部读 `download.channel`，做 `if channel == "cdn"` 二选一。通道执行结果统一汇成 `DownloadResult`，后续状态机（重试/退避/入库/0 字节改判）与通道无关——**这是好消息：provider 抽象的插入点只有一个**。
- **内容落地由通道负责**：CDN 通道在 `_download_via_cdn:428-431` 显式拼出与 steamcmd 完全相同的 `steamapps/workshop/content/<appid>/<itemid>` 布局，`_register_to_library` 和 `_normalize_content_path` 对通道无感知。新 provider 只要落地到同一布局，入库链路零改动。
- **进度协议已统一**：steamcmd 引擎与 cdn_downloader 都回调 `on_progress(pct, done, msg)`（pct<0 表示不确定进度），经同一个 `_on_engine_progress` → `ProgressSmoother`。新 provider 只需实现同样的回调签名。
- **现存缺陷**：`services.py:78` 构造 `DownloadManager` 时**没有传 `api`**（`downloader.py:88` 的 `self.api` 实际为 `None`）。导致 cdn 通道的 `resolve_file_url` 无法调用 `api.get_file_details` 补全 file_url，只能用 item 自带（浏览列表时通常为空）——CDN 通道目前几乎必然回退 steamcmd。接入新 provider 时必须一并修复 api 注入（provider 需要 api 解析直链）。

---

## 2. 硬编码通道名清单（新增 provider 必须改的点）

| # | 位置 | 当前代码 | 说明 |
|---|---|---|---|
| 1 | `config.py:40` | `"channel": "steamcmd"` | DEFAULT_CONFIG 中唯一通道字段；只支持单值，无回退链概念 |
| 2 | `settings_tab.py:148` | `self.channel_combo.addItem("SteamCMD（匿名下载，推荐）", "steamcmd")` | 下拉项硬编码第 1 项 |
| 3 | `settings_tab.py:149` | `self.channel_combo.addItem("CDN 直链（需登录态，不可用时自动回退）", "cdn")` | 下拉项硬编码第 2 项 |
| 4 | `settings_tab.py:150-153` | `setToolTip(...)` | 通道说明文字写死为 CDN 的匿名回退提示 |
| 5 | `settings_tab.py:294-296` | `ch = cfg.get("download", "channel", default="steamcmd") or "steamcmd"` | 加载时回退值写死 |
| 6 | `settings_tab.py:420` | `cfg.set("download", "channel", self.channel_combo.currentData())` | 保存单值 |
| 7 | `downloader.py:477` | `channel = "steamcmd"` | 读取失败时的默认通道写死 |
| 8 | `downloader.py:481-482` | `get_config().get("download", "channel", default="steamcmd") or "steamcmd"` | 默认值写死（出现 2 次） |
| 9 | `downloader.py:487` | `if channel == "cdn":` | **通道分发分支**——字符串比较，新增通道必须加 elif |
| 10 | `downloader.py:489-492` | `if result.status != SUCCESS and result.message and "回退" in result.message:` | **用消息文本判断是否该回退**（脆：依赖中文"回退"二字；见 §5.1） |
| 11 | `downloader.py:494` | `result = self._run_steamcmd(...)` | 回退目标硬编码为 steamcmd |
| 12 | `downloader.py:418-437` | `_download_via_cdn()` 整个方法 | 通道实现内联在 manager 里，新通道照抄会无限膨胀 |
| 13 | `services.py:78-82` | `DownloadManager(engine, library, max_concurrent=..., auto_retry=1)` | 未传 api（缺陷）；也无 provider 注册入口 |
| 14 | `downloader.py:74-85` | `DownloadManager.__init__(self, engine, library, ...)` | 构造参数绑定单一 engine；多 provider 需要传入 registry |
| 15 | `downloader.py:256` | `self.engine.cancel()` | 取消只认 steamcmd engine（HTTP 型 provider 需要自己的取消） |

测试侧的通道断言（改动需同步，非阻塞）：
- `tests/test_core_sweep.py:231`、`:711`：断言 `download.channel == "steamcmd"`（默认值回归）
- `tests/test_engine_concurrency.py:185-191`：注释「强制走 steamcmd 通道（默认配置可能是 cdn，会绕过引擎）」，并在 fixture 里 set `download.channel`——说明**测试已预期 channel 可能变化**，新通道接入后这类夹具要按新配置 schema 对齐。
- `tests/test_cdn.py:104-119`、`test_core_sweep.py:534-599`：直接调 `download_item_cdn` / `download_file` 的单测——改造为 provider 后这些入口要保持可独立调用（见 §3.3 兼容层）。

---

## 3. Provider 抽象设计

### 3.1 是否引入接口/基类：**引入，用 ABC 基类而非纯 Protocol**

理由：
- provider 有大量**共享实现**（HTTP 流式下载、Range 续传、会话/代理/UA 复用、错误归一化），纯 Protocol 无法复用；ABC 基类 `BaseProvider` 放通用逻辑，子类只实现差异部分。
- 现有 `cdn_downloader.py` 的 `download_file` / `resolve_file_url` 已经是「HTTP 型 provider」的通用件，应下沉为基类方法。

### 3.2 目录结构

```
swdm/core/providers/
├── __init__.py          # 导出 DownloadProvider、BaseProvider、registry 入口
├── base.py              # 抽象基类 + 通用 HTTP 下载逻辑（从 cdn_downloader 下沉）
├── registry.py          # ProviderRegistry：发现/构造/排序/可用性缓存
├── steamcmd.py          # 引擎型 provider（包装现有 SteamCMDEngine）
├── cdn.py               # Steam 官方 CDN 直链（cdn_downloader.py 改造）
├── steamwebapi.py       # 第三方：steamwebapi
├── ggnetwork.py         # 第三方：GGNetwork
├── nether.py            # 第三方：Nether
└── swd.py               # 第三方：SWD
```

保留 `swdm/core/cdn_downloader.py` 为**兼容门面**（re-export `download_item_cdn` / `download_file` / `resolve_file_url`，内部委托 providers/cdn.py），现有 `test_cdn.py` / `test_core_sweep.py` 零改动继续通过。`steamcmd_engine.py` **不动**，由 `providers/steamcmd.py` 包装。

### 3.3 接口草稿

```python
# swdm/core/providers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import threading

from swdm.core.steam_api import WorkshopItem, SteamAPI
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus


class ProviderKind(str, Enum):
    ENGINE = "engine"      # 本地引擎型（steamcmd）：子进程、串行、无 URL
    HTTP = "http"          # 直链型：解析 URL 后流式下载
    PROXY = "proxy"        # 第三方代理型：先换源/换 id，再 HTTP 下载（4 个新 provider 多属此类）


class Availability(str, Enum):
    OK = "ok"              # 可用
    NO_KEY = "no_key"      # 需要未配置的凭据（key/登录态）
    UNREACHABLE = "unreachable"   # 探测失败（超时/403/服务下线）
    DISABLED = "disabled"  # 用户在配置里关掉


@dataclass
class ProviderMeta:
    name: str              # 稳定 id，写入 config（"steamcmd" / "cdn" / "steamwebapi" …）
    display_name: str      # UI 下拉显示名
    kind: ProviderKind
    requires_key: bool = False        # 是否需要在 config 里配 api_key/token
    key_hint: str = ""                # 未配 key 时的 UI 提示文案
    anonymous_ok: bool = True         # 匿名可用（决定 UI 是否给"推荐"标记）
    priority: int = 0                 # 同级排序（数值小优先）
    config_fields: tuple = ()         # 该 provider 在 config 里的独立字段声明


class DownloadProvider(ABC):
    """所有下载通道的统一抽象。

    生命周期：build() → probe() → download()（可多次） → cancel()
    线程模型：download() 在 DownloadManager 的工作线程内同步执行（阻塞），
             cancel() 可能从 GUI 线程调用，必须线程安全。
    """

    meta: ProviderMeta                     # 类属性，子类覆盖

    @abstractmethod
    def __init__(self, config: dict, api: SteamAPI | None) -> None:
        """config 为该 provider 的独立配置节（已从全局 config 摘出）。"""

    # ---------------- 可用性探测（轻量、可缓存、不下载内容）
    @abstractmethod
    def probe(self, timeout: float = 8.0) -> Availability:
        """探测通道当前是否可用。

        - ENGINE 型：检查 exe 可定位（engine.resolve_exe 不触发在线下载）
        - HTTP/PROXY 型：GET 一个轻量端点（如服务健康检查 / 小文件 HEAD）
        - 需 key 的 provider：key 缺失时直接返回 NO_KEY，不发请求
        """

    # ---------------- 下载
    @abstractmethod
    def download(
        self,
        item: WorkshopItem,
        dest_dir: str,                     # 必须落地到 content/<appid>/<itemid>
        on_progress=None,                  # on_progress(pct:int, done:int, msg:str)
        stop_event: threading.Event | None = None,   # 统一取消语义
        total_hint: int = 0,
    ) -> DownloadResult:
        """阻塞式下载单个物品。取消时用 stop_event 轮询，返回 CANCELLED。"""

    @abstractmethod
    def cancel(self) -> None:
        """中断当前进行中的 download()（尽力而为）。"""

    # ---------------- 可选：解析（HTTP/PROXY 型）
    def resolve(self, item: WorkshopItem) -> str:
        """解析出最终下载 URL；不可用时返回 ''。默认实现用 item.file_url。"""
        return (getattr(item, "file_url", "") or "").strip()

    # ---------------- 可选：回退建议
    def should_fallback(self, result: DownloadResult) -> bool:
        """失败结果是否建议回退到下一通道（默认：非取消的失败都回退）。

        子类可收窄：如 CDN 的"匿名无 file_url"是可回退的配置型失败，
        而"磁盘写满"不应回退（回退也一样失败）。
        """
        return result.status == DownloadStatus.FAILED
```

### 3.4 三个具体 provider 形态

```python
# providers/steamcmd.py —— 引擎型（包装现有 SteamCMDEngine，零行为改动）
class SteamcmdProvider(DownloadProvider):
    meta = ProviderMeta(
        name="steamcmd", display_name="SteamCMD（匿名下载，推荐）",
        kind=ProviderKind.ENGINE, anonymous_ok=True, priority=0,
    )
    def __init__(self, config, api):
        self.engine = config["_engine"]      # 复用单例 SteamCMDEngine（services 注入）
    def probe(self, timeout=8.0):
        try:
            self.engine.resolve_exe(); return Availability.OK
        except Exception: return Availability.UNREACHABLE
    def download(self, item, dest_dir, on_progress, stop_event, total_hint=0):
        # stop_event → 桥接 engine.cancel()（轮询线程，见 §5.3）
        return self.engine.download_item(
            appid=item.appid, item_id=item.publishedfileid,
            on_progress=on_progress, total_hint=total_hint or item.file_size,
            install_dir=...,   # 由 dest_dir 反推
        )
    def cancel(self): self.engine.cancel()
```

```python
# providers/cdn.py —— 官方 CDN 直链（cdn_downloader.py 平迁）
class CdnProvider(DownloadProvider):
    meta = ProviderMeta(
        name="cdn", display_name="Steam CDN 直链（需登录态）",
        kind=ProviderKind.HTTP, requires_key=False, anonymous_ok=False, priority=10,
        key_hint="CDN 直链需要登录态才有 file_url；匿名会自动回退 SteamCMD。",
    )
    # resolve() 沿用 resolve_file_url（item.file_url → api.get_file_details 补全）
    # download() 沿用 download_item_cdn → download_file（Range 续传）
```

```python
# providers/steamwebapi.py —— 第三方代理型（模板，4 个新 provider 同构）
class SteamwebapiProvider(DownloadProvider):
    meta = ProviderMeta(
        name="steamwebapi", display_name="steamwebapi（第三方）",
        kind=ProviderKind.PROXY, requires_key=True, anonymous_ok=False, priority=20,
        key_hint="在下方填写 steamwebapi 的 API Key 后启用。",
        config_fields=("api_key", "base_url"),
    )
    def probe(self, timeout=8.0):
        if not self._api_key: return Availability.NO_KEY
        # GET {base_url}/health 或最小付费校验端点；失败 → UNREACHABLE
    def resolve(self, item):
        # 调第三方接口把 publishedfileid 换成该服务的下载直链
    # download() 复用基类的 http_download（与 cdn 同一套 Range/进度逻辑）
```

### 3.5 DownloadManager 如何调度多 provider（链式回退）

**新增 `ProviderRegistry`**（`providers/registry.py`）：

```python
class ProviderRegistry:
    def __init__(self, api, engine): ...

    def discover(self) -> dict[str, DownloadProvider]:
        """静态表 + 可选入口点扫描，构造全部已注册 provider 实例。"""

    def chain(self) -> list[DownloadProvider]:
        """按 config 生成有序通道链：
        [config.download.channel（主通道）]
        + [config.download.fallback_chain 中可用且非主通道者]
        + [兜底 steamcmd（若未在链中且 probe OK）]
        """

    def availability(self, name) -> Availability:
        """带 TTL 缓存的探测结果（避免每个任务都探测；缓存 60s）"""
```

**`_exec_job` 改造**（替换 §2 的 #7~#12 六处硬编码）：

```python
# downloader.py:476-494 现状 → 改造后伪码
chain = self._registry.chain()          # [主, 回退1, 回退2, ..., steamcmd 兜底]
result = DownloadResult(..., status=FAILED, message="无可用通道")
used_channel = ""
for provider in chain:
    if job._stop.is_set():
        result.status = DownloadStatus.CANCELLED
        break
    avail = self._registry.availability(provider.meta.name)
    if avail is not Availability.OK:
        continue                        # 跳过不可用通道（不消耗重试次数）
    used_channel = provider.meta.name
    result = provider.download(job.item, dest_dir, on_progress, job._stop, job.total_bytes)
    if result.status == DownloadStatus.SUCCESS or not provider.should_fallback(result):
        break                           # 成功，或该 provider 判定不该回退
    log.info("物品 %s 通道 %s 失败(%s)，回退下一通道", job.id, provider.meta.name, result.message)
job.channel = used_channel              # 新字段：记录实际用上的通道（供 UI 展示）
```

关键设计点：
- **回退不消耗 `auto_retry` 次数**：回退是通道切换，`job.attempt` 只在整条链都失败后、由现有自动重试逻辑（downloader.py:531-541）递增。一条链 = 一次 attempt。
- **0 字节假成功判定保留**（downloader.py:504-512）：对所有 provider 通用，第三方代理服务也可能"返回成功但空文件"。
- **退避/并发自适应按通道失败归因**：`_on_throttle_signal` 目前只桥接 steamcmd 输出（downloader.py:122-143）。HTTP/PROXY 型 provider 的 429 应通过同样的 `on_throttle_signal` 出口上报（provider 内部把 HTTP 429 / Retry-After 转成 `("rate_limit", ...)`），复用现有 Backoff + AdaptiveConcurrency，**不要新写一套**。
- **steamcmd 串行锁保留**：`_engine_lock`（downloader.py:403-416）下沉到 `SteamcmdProvider` 内部（或 registry 保证 engine 型 provider 全局单例 + 内部锁），多通道并存时仍只有 steamcmd 需要串行，HTTP 型可真并发。

---

## 4. 配置与 UI 适配

### 4.1 config 扩展（`config.py` DEFAULT_CONFIG）

```python
"download": {
    "channel": "steamcmd",          # 主通道（保持兼容，旧配置直接读得到）
    "fallback_chain": ["steamcmd"], # 显式回退链（主通道失败后依次尝试）
    "auto_fallback": True,          # 总开关：False 时主通道失败即失败，不切换
},
"providers": {
    # 每 provider 一个独立子节，键名 = ProviderMeta.name
    "steamwebapi": {
        "enabled": True,
        "api_key": "",              # 独立 key（与 network.api_key 分开，避免混用）
        "base_url": "",             # 可自托管/镜像的填这里
        "timeout": 60,
    },
    "ggnetwork": {"enabled": True, "api_key": "", "base_url": "", "timeout": 60},
    "nether":     {"enabled": True, "api_key": "", "base_url": "", "timeout": 60},
    "swd":        {"enabled": True, "api_key": "", "base_url": "", "timeout": 60},
},
```

注意：
- 现有 `Config._merge`（config.py:99-109）只做**两层**递归合并，`providers.steamwebapi.api_key` 这类三层结构在旧配置里不存在（缺省即默认值，无合并问题）；但**新 config 的 providers 子节会整体被旧配置文件覆盖**——需确认 `_merge` 对完全缺失的新键走默认分支（当前：`self._data["providers"]` 保留默认全量，安全）。
- key 属于敏感信息：`api_key` 不应写进日志/崩溃报告（现有 `network.api_key` 亦然，保持一致策略）；落盘明文与现状相同，后续可考虑 keyring（auth 模块已有 keyring 依赖）。

### 4.2 settings_tab 动态化

| 改动 | 说明 |
|---|---|
| `settings_tab.py:147-154` | 删除两个 `addItem` 硬编码；改为 `for p in registry.all_providers(): self.channel_combo.addItem(p.display_name + 状态后缀, p.meta.name)`，后缀按 probe 结果显示「✓可用 / 需 Key / 不可用」 |
| 下拉项动态生成时机 | `_load_values`（:287）之前先调 `registry.discover()` + 异步 probe（QThread，避免设置页打开卡顿——第三方端点可能慢） |
| provider 配置区（新增） | 下拉切换通道时，按 `ProviderMeta.config_fields` 动态生成表单（QStackedWidget 每 provider 一页：api_key QLineEdit（密码模式 EchoMode::Password）、base_url QLineEdit、timeout QSpinBox）。参考现有「Steam 账号」分区（settings_tab.py:118-120 CollapsibleSection）的组织方式 |
| 「测试通道」按钮（新增） | 手动触发 `provider.probe()` + 一个真实小文件下载冒烟（只对 HTTP/PROXY 型），结果写 `login_status` 样式的状态 Label（复用 `_on_login_result` 模式，settings_tab.py:374-378） |
| `settings_tab.py:294-296` | 加载逻辑不变（读 `download.channel`）；新增回退链多选（QListWidget 勾选，顺序即链序） |
| `settings_tab.py:420` | 保存 `download.channel` + `download.fallback_chain` + `providers.<name>.*`；调 `svc.refresh_providers()`（services 新方法，重建 registry 并让 downloader 热更新链） |

### 4.3 下载页显示当前通道（任务 5 相关）

- `DownloadJob` 新增 `channel: str = ""` 字段（downloader.py:39-54 的 dataclass）。
- `downloads_tab.py` 的 `_HEADERS` 在「状态」列后插一列「通道」，`_update_row`（:157）显示 `job.channel` 或 provider display_name 短称。
- 卡片迷你进度（workshop_tab.py:334-343）的 message 已携带通道信息时（如「CDN 直链下载中…」），无需额外列。
- 失败行的 message 追加「（经 N 通道均失败）」便于排障。

---

## 5. 进度 / 状态 / 取消适配

### 5.1 进度统一：全部归一到 `on_progress(pct, done, msg)` + ProgressSmoother

| provider kind | 原生进度来源 | 归一方式 |
|---|---|---|
| ENGINE（steamcmd） | 输出行百分比 / Update state / 磁盘落盘增长 | 现有逻辑（steamcmd_engine.py:336-371 + watchdog :398-425）原样保留 |
| HTTP（cdn） | Content-Length + 已写字节 | 现有 `download_file`（cdn_downloader.py:111-128）原样保留 |
| PROXY（4 个新 provider） | 第三方接口的轮询进度 / 或直链的 Content-Length | 有直链→走基类 HTTP 逻辑；无逐字节进度→`on_progress(-1, done, "已下载 X MB")` 不确定进度模式（smoother 已支持，downloader.py:586-589） |

要点：
- **pct<0（不确定进度）路径已存在且已被 UI 正确处理**（throttle.py ProgressSmoother 的 percent=-1 分支 + `_render_label`），新 provider 的"只能轮询不能逐字节"场景不用新造 UI 状态。
- **总字节数以 `job.total_bytes`（工坊元数据 file_size）为锚**，provider 的 Content-Length 不可信时（第三方可能压缩/转码）也用 total_hint 换算百分比，保证 UI 不跳变。
- **速度/ETA 的滚动窗口（throttle.py:231-322）对 provider 透明**——provider 只管喂原始 (done, total)，平滑、限流、不倒退全在 `_on_engine_progress`。

### 5.2 结果状态归一

所有 provider 返回同一个 `DownloadResult`（steamcmd_engine.py:86-94，已在 core/__init__.py:22 导出）：

- `SUCCESS` / `FAILED` / `CANCELLED` 三态足够（`QUEUED`/`RUNNING` 为内部态）。
- **回退判定从"消息含'回退'二字"改为 `provider.should_fallback(result)`**（§3.3）——消除 §2 #10 的脆弱字符串判定。兼容性：`cdn_downloader.py:151-155` 的"已自动回退"提示文案保留在 message 里（测试 test_cdn.py:107 断言 "回退" in message，不能删），但**调度层不再 parse 它**。
- 第三方特有失败（余额不足/Key 过期/服务限流）在 provider 内部归一为 `FAILED + 明确 message`，`should_fallback` 对「Key 无效」类返回 `False`（回退也没用，直接让用户看到"请检查 Key"）。

### 5.3 取消语义统一

现状两种取消路径：`job._stop.set()`（manager 层标记）+ `engine.cancel()`（进程级）。统一为：

```python
# manager 层（downloader.py:250 cancel() 改造）
job._stop.set()
try: provider = self._registry.active_provider(job.id)   # 新：记录当前通道实例
except Exception: ...
if provider: provider.cancel()    # 替代硬编码的 self.engine.cancel()
```

- **ENGINE 型**：`SteamcmdProvider.cancel()` → `engine.cancel()`（:496 现有实现：stdin quit + terminate）。额外加一个 stop_event 轮询线程：在 `download()` 里启 daemon 定时检查 `stop_event`，触发即 `engine.cancel()`——因为 engine.download_item 本身不接收 stop_event（其内部只认 `_cancel_flag`）。
- **HTTP/PROXY 型**：基类 `http_download()` 在每个 chunk 写入循环里检查 `stop_event.is_set()`，关闭 response stream（`r.close()`），返回 `CANCELLED`；已写入的部分文件保留（与现有断点续传一致：下次重试 Range 接续）。
- 取消后的 `_active` 清理（downloader.py:259-267）与 `_exec_job` 的 `_stop` 判定（:513）保持不变，对 provider 透明。

---

## 6. 风险与开放问题

### 6.1 匿名可用性探测（无 key 时的优雅提示）

- **现状参照**：cdn 通道在匿名下由 `download_item_cdn` 返回 FAILED + "回退"提示（cdn_downloader.py:149-157）。新 provider 需要 key 时不能等下载失败才说——应在**链构造阶段**用 `probe()` 返回 `NO_KEY` 直接跳过。
- **UI 提示分级**：
  - 下拉项后缀「需 Key」+ tooltip 说明（复用 settings_tab.py:150-153 的 tooltip 模式）；
  - 用户选中需 key 但未配置的通道为主通道时，保存按钮旁给黄色警告条（非阻断，允许保存——链里有 steamcmd 兜底）；
  - 下载页失败行 message 明确「steamwebapi：未配置 API Key（已跳过，使用 SteamCMD 完成）」。
- **探测缓存**：`probe()` 结果带 60s TTL 缓存，避免每个任务探测一次（第三方端点慢会拖垮队列）。探测失败不阻断：`UNREACHABLE` 通道被跳过，链继续。
- **隐私**：探测请求的 UA / 代理沿用 SteamAPI session（cdn_downloader.py:52-61 的 `_session` 复用策略），不暴露用户 IP 给第三方以外的指纹。

### 6.2 provider 失效的降级策略

| 场景 | 降级动作 |
|---|---|
| 主通道 probe 不可用 | 静默跳过，链的下一通道顶上；UI 下拉项标灰但不报错 |
| 主通道下载中途失败 | `should_fallback` 判定可回退 → 下一通道（**不消耗 auto_retry**） |
| 整条链失败 | 走现有失败路径：退避升级 + 并发降到 1（downloader.py:527-529）+ auto_retry 重试整条链 |
| 连续 N 次某通道失败 | （建议）registry 熔断：该通道进入 5 分钟冷却，probe 直接返回 UNREACHABLE，避免每次下载都等超时。可复用 `Backoff` 思路或 gui/workers.py 已有的 `_Throttle` 熔断器模式 |
| 第三方服务返回错误内容 | §6.3 完整性校验 + 0 字节假成功判定（已有，downloader.py:504-512）兜底 |
| 全部第三方不可用 | steamcmd 永远在链尾兜底（匿名可用），保证「基本功能正常运行」 |

### 6.3 下载内容完整性校验（各 provider 文件是否与 steamcmd 一致）

这是**最大的风险点**，分三层：

1. **布局一致性（已解决）**：所有 provider 必须落地到 `<root>/steamapps/workshop/content/<appid>/<itemid>/`（downloader.py:428-431 已为 cdn 这么做）。`_normalize_content_path`（:629-650）对 legacy 单文件 mod（L4D2/KF/Civ）有目录化回退——**第三方 provider 若返回的是压缩包（zip/7z）而非原始 .gma，必须先解压再按布局落地**，否则入库的 local_path 与游戏实际读取路径不一致。这是 PROXY 型 provider 最可能出问题的地方，需逐个 provider 在调研阶段确认其输出格式（见 `provider_research.md`）。
2. **内容一致性（需新增）**：steamcmd 下下来的 .gma 与第三方服务转存的可能存在：
   - 版本漂移（第三方缓存旧版本，`time_updated` 不一致）；
   - 重打包（去除了 .gma 头的某些字段、或重新压缩）；
   - 损坏（传输中断但第三方接口报成功）。
   
   **建议（不强制本轮做）**：
   - 落地后做 `.gma` 头解析（GMod 的 .gma 有魔数 `GMAD` + 版本 + steamid + 时间戳 + 预览 + 文件清单），能解即认为结构完整；
   - 与工坊元数据的 `file_size` 比对（job.total_bytes）：差异 > 1% 时在下载页给⚠提示（不阻断入库——重打包可能合法改变大小）；
   - 长期：Web API 的 `hcontent_file` / `file_url` 签名里带 hash 时可做强校验，匿名拿不到就只做弱校验。
3. **依赖一致性**：`enqueue_with_dependencies`（downloader.py:201-230）解析依赖用的是工坊元数据的 dependencies 列表，与通道无关——第三方 provider 若只支持部分游戏（如只服务 GMod），依赖链里的其他游戏物品会失败。**建议 provider 声明 `supported_appids`（或 `supported_games`）**，链构造时按 appid 过滤，不支持的物品直接走 steamcmd，不要让整批依赖因一个不支持的物品卡住。

### 6.4 开放问题（需讨论组或进一步调研确认）

1. **4 个第三方 provider 的真实 API 形态**（端点 / 认证 / 是否返回原始 .gma / 限流）——依赖 `research/provider_research.md`；若其中某个是"网页服务无 API"，则该 provider 只能做"复制链接到浏览器"的引导型，不能进统一链（需在 ProviderKind 里再加 `EXTERNAL` 型，download() 直接返回 FAILED + 打开浏览器）。
2. **base_url 自托管的合法性与免责**：允许用户填 base_url 会把程序变成"可配置下载源"的工具，需在设置页加免责声明（第三方服务与本程序无关）。
3. **key 的存储**：明文 config.json（现状）vs keyring（auth 模块已用 keyring 存 Steam 密码，可复用）。倾向 keyring，但会增加测试复杂度（CI 无 keyring 环境）。
4. **回退链与自动重试的交互边界**：一条链全失败 = 1 次 attempt（本设计）；是否需要"第二次 attempt 时换链序"（如把失败过的主通道降权）？倾向先不做，保持简单。
5. **并发模型**：steamcmd 串行（`_engine_lock`），HTTP 型可并发。多 provider 混用时，`AdaptiveConcurrency`（throttle.py:107）的降级是全局的——某个第三方 provider 触发 429 会把全局并发降到 1，拖慢 steamcmd 任务。**建议把退避/并发状态按通道分桶**（`Backoff`/`AdaptiveConcurrency` 实例 per provider），失败只影响同类通道。这是对现有架构的显著改动，建议作为 provider 落地后的独立优化项。
6. **测试策略**：新增 `tests/test_providers.py`——用 `http.server` 本地 mock（复用 test_cdn.py:55-73 的 _Handler 模式）覆盖每个 provider 的 probe/resolve/download/取消/回退；`test_registry.py` 覆盖链构造与缓存。回归必须覆盖：config 默认值仍为 steamcmd（test_core_sweep.py:711 依赖）、cdn_downloader 兼容门面仍可导入（test_cdn.py 全量）、_exec_job 的回退路径（test_engine_concurrency.py 的 fixture 要更新到新 schema）。
7. **版本与交付**：按迭代四要素，provider 架构属 1.4.0 级改动（新增 config schema + UI 结构变化），需先在讨论组评审"是否一次接 4 个 provider，还是先接架构 + 1 个试点 provider（steamwebapi）验证链路再铺开"。倾向后者：架构 + steamcmd/cdn 迁移 + 1 个第三方 provider 试点，剩余 3 个照模板复制。

---

## 7. 落地步骤建议（供实施参考，非本设计文档执行项）

1. `swdm/core/providers/` 骨架：base.py（ABC + 从 cdn_downloader 下沉的 http_download/resolve）+ registry.py。
2. 迁移：cdn_downloader.py → providers/cdn.py（保留兼容门面）；新增 providers/steamcmd.py（包装现有 engine，行为不变）。
3. DownloadManager 改造：`_exec_job` 的通道分发换成链式回退（§3.5 伪码）；`DownloadJob.channel` 字段；`cancel()` 走当前 provider；修复 api 注入（services.py:78 传 api）。
4. config schema 扩展 + settings_tab 动态下拉 + provider 配置区。
5. 试点接入 1 个第三方 provider（待 provider_research.md 结论选定）。
6. 测试：test_providers.py / test_registry.py + 全量回归（48 脚本基线）。
7. 讨论组评审 + 版本号升级（1.4.0）+ 变更记录。
