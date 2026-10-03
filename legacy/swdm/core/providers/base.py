"""Download provider abstract base class plus shared HTTP download logic (Provider 抽象基类).

Design: see research/provider_adaptation.md §3.3. The shared pieces (HTTP streaming
download, Range resume, session reuse) were hoisted here from cdn_downloader.py;
subclasses implement only the differing parts (URL resolution, probe, fallback policy).

Key exports: ``DownloadProvider`` (ABC with probe/download/cancel/resolve/
should_fallback/is_configured), ``ProviderMeta``, ``ProviderKind``, ``Availability``,
and ``http_download`` (Range resume + per-chunk stop_event polling + 429 reporting).
"""
from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import requests

from ..logger import get_logger
from ..steam_api import SteamAPI, WorkshopItem
from ..steamcmd_engine import DownloadResult, DownloadStatus

log = get_logger("swdm.core.providers")


class ProviderKind(str, Enum):
    """How a provider talks to Steam: ENGINE (子进程) / HTTP (直链) / PROXY (第三方代理)."""

    ENGINE = "engine"      # 本地引擎型（steamcmd）：子进程、串行、无 URL
    HTTP = "http"          # 直链型：解析 URL 后流式下载
    PROXY = "proxy"        # 第三方代理型：先换源/换 id，再 HTTP 下载


class Availability(str, Enum):
    """Probe outcome for a channel (通道可用性)."""

    OK = "ok"                       # 可用
    NO_KEY = "no_key"               # 需要未配置的凭据（key/登录态）
    UNREACHABLE = "unreachable"     # 探测失败（超时/403/服务下线）
    DISABLED = "disabled"           # 用户在配置里关掉


@dataclass(frozen=True)
class ProviderMeta:
    """Static descriptor of a channel: identity, kind, key requirements and chain placement."""

    name: str                          # 稳定 id，写入 config（"steamcmd"/"cdn"/"ggnetwork"…）
    display_name: str                  # UI 下拉显示名
    kind: ProviderKind
    requires_key: bool = False         # 是否需要在 config 里配 api_key/token
    key_hint: str = ""                 # 未配 key 时的 UI 提示文案
    anonymous_ok: bool = True          # 匿名可用（决定 UI 是否给"推荐"标记）
    priority: int = 0                  # 同级排序（数值小优先）
    supported_appids: tuple = ()       # 只支持部分游戏；空 = 全部
    config_fields: tuple = ()          # 该 provider 在 config 里的独立字段声明
    terminal: bool = False             # 链终结者（steamcmd）：到它不再追加后续通道
    supports_account: bool = False     # 私人账号通道（C3）：用用户自己的 Steam 账号下载
                                       # 自己有权内容；公有账户池接口保留不启用（合规分层）
    breaker_exempt: bool = False       # 失败不计熔断（私人账号通道：凭据问题不应
                                       # 熔断链上其他通道，更不能熔断 steamcmd 兜底）


class DownloadProvider(ABC):
    """所有下载通道的统一抽象。

    生命周期：__init__(config) → probe() → download()（可多次） → cancel()
    线程模型：download() 在 DownloadManager 的工作线程内同步执行（阻塞），
             cancel() 可能从 GUI 线程调用，必须线程安全。
    """

    meta: ProviderMeta                     # 类属性，子类覆盖

    def __init__(self, config: dict, api: SteamAPI | None = None) -> None:
        """config 为该 provider 的独立配置节（已从全局 config 摘出）。"""
        self.config = config or {}
        self.api = api
        self.on_throttle_signal: list = []  # (kind, line) 上报出口（manager 订阅）

    # ---------------- 可用性探测（轻量、可缓存、不下载内容）
    @abstractmethod
    def probe(self, timeout: float = 8.0) -> Availability:
        """探测通道当前是否可用。

        - ENGINE 型：检查 exe 可定位（engine.resolve_exe 不触发在线下载）
        - HTTP/PROXY 型：GET 一个轻量端点
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
        """失败结果是否建议回退到下一通道。

        默认：非取消的失败都回退。子类可收窄：如"key 无效"类配置型失败
        回退也没用，应返回 False 直接让用户看到"请检查 Key"。
        """
        return result.status == DownloadStatus.FAILED

    # ---------------- 可选：凭据完备性（链构造时跳过未配置的通道）
    def is_configured(self) -> bool:
        """requires_key 的 provider 未配置 key 时返回 False，链构造跳过它。

        默认实现：requires_key=False 恒为 True；否则查 config.api_key。
        跳过而非报错——匿名可用性是核心卖点，绝不中断下载。
        """
        if not self.meta.requires_key:
            return True
        return bool((self.config.get("api_key") or "").strip())

    # ---------------- 通用件：HTTP 会话
    def _session(self) -> requests.Session:
        """复用 SteamAPI 的 session（浏览器 UA + 代理 + truststore）。"""
        api = self.api
        if api is not None and getattr(api, "_session", None) is not None:
            return api._session  # type: ignore[no-any-return]
        s = requests.Session()
        s.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        return s

    # ---------------- 通用件：HTTP 流式下载（支持取消 + 续传）
    def http_download(
        self,
        url: str,
        dest_path: str,
        session: requests.Session | None = None,
        on_progress=None,
        stop_event: threading.Event | None = None,
        chunk_size: int = 1 << 16,
        timeout: int = 60,
    ) -> DownloadResult:
        """HTTP 流式下载单个文件，支持 Range 续传与 stop_event 取消。

        返回 DownloadResult（SUCCESS/FAILED/CANCELLED）。
        on_progress(percent, bytes_done, msg)：percent < 0 表示不确定进度。
        """
        item_id = ""
        appid = ""
        sess = session or self._session()
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)

        # 断点续传：已有部分文件时从尾部接续
        resume_from = 0
        if os.path.isfile(dest_path):
            resume_from = os.path.getsize(dest_path)

        headers = {}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"

        r: requests.Response | None = None
        try:
            r = sess.get(url, headers=headers, timeout=timeout, stream=True)
            # 服务器忽略 Range（返回 200 而非 206）→ 丢弃已有部分重下
            if resume_from > 0 and r.status_code == 200:
                resume_from = 0
            if r.status_code not in (200, 206):
                msg = f"HTTP {r.status_code}"
                if r.status_code == 429:
                    self._report_throttle("rate_limit", f"HTTP 429: {url}")
                return DownloadResult(item_id=item_id, appid=appid,
                                      status=DownloadStatus.FAILED,
                                      bytes_done=resume_from, message=msg)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return DownloadResult(item_id=item_id, appid=appid,
                                  status=DownloadStatus.FAILED,
                                  bytes_done=resume_from,
                                  message=f"请求失败: {type(e).__name__}: {e}")

        assert r is not None
        total_header = r.headers.get("Content-Length")
        total = int(total_header) if total_header and total_header.isdigit() else 0
        if r.status_code == 206 and total:
            total += resume_from  # 206 的 Content-Length 是剩余部分

        done = resume_from
        mode = "ab" if r.status_code == 206 and resume_from > 0 else "wb"
        if mode == "wb":
            done = 0
        t0 = time.time()
        cancelled = False
        try:
            with open(dest_path, mode) as f:
                for chunk in r.iter_content(chunk_size):
                    if stop_event is not None and stop_event.is_set():
                        cancelled = True
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        if total:
                            pct = min(99.0, done / total * 100)
                            speed = done / max(time.time() - t0, 1e-6) / 1048576
                            on_progress(pct, done, f"{speed:.1f} MB/s")
                        else:
                            on_progress(-1, done, f"{done / 1048576:.1f} MB")
        except Exception as e:  # noqa: BLE001
            return DownloadResult(item_id=item_id, appid=appid,
                                  status=DownloadStatus.FAILED, bytes_done=done,
                                  message=f"写入失败: {e}")
        finally:
            try:
                r.close()
            except Exception:  # noqa: BLE001
                pass

        if cancelled:
            # 已写入的部分保留（下次重试 Range 接续）
            return DownloadResult(item_id=item_id, appid=appid,
                                  status=DownloadStatus.CANCELLED, bytes_done=done,
                                  message="已取消")
        if on_progress and total:
            on_progress(100.0, done, "完成")
        return DownloadResult(item_id=item_id, appid=appid,
                              status=DownloadStatus.SUCCESS, path=dest_path,
                              bytes_done=done, message="下载完成")

    # ---------------- 通用件：限流信号上报（复用 manager 退避）
    def _report_throttle(self, kind: str, line: str) -> None:
        for cb in list(self.on_throttle_signal):
            try:
                cb(kind, line)
            except Exception:  # noqa: BLE001
                log.debug("on_throttle_signal 订阅者异常", exc_info=True)
