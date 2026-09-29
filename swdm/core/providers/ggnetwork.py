"""GGNetwork 通道（试点第三方 provider，匿名 PROXY 型）。

实测调研见 research/provider_research.md：
- POST https://api.ggntw.com/steam.request，body {"url": 工坊物品页 URL}
- 匿名无需 Key（实测 200），返回官方 CDN 直链 + id/game/name/size/update
- ToS §5.2.2 禁 excessive server load → 自律限速（默认 20 req/min）
- 返回内容若为压缩包则先解压再落地；.gma 魔数弱校验 + size 差异 >1% 给⚠
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import zipfile

from ..logger import get_logger
from ..steam_api import WorkshopItem
from ..steamcmd_engine import DownloadResult, DownloadStatus
from .base import Availability, DownloadProvider, ProviderKind, ProviderMeta

log = get_logger("swdm.core.providers.ggnetwork")

_GG_URL = "https://api.ggntw.com/steam.request"
_DEFAULT_RATE_LIMIT = 20          # req/min，匿名接口自律上限
_PROBE_ITEM = "2537024972"        # 探测用一个稳定存在的物品 id（Garry's Mod）
_GMA_MAGIC = b"GMAD"              # Garry's Mod addon 格式魔数（弱校验）

# 熔断阈值（复用 O5 _Throttle 思路，但 provider 内自管：本接口限速敏感）
_RATE_BURST = 3                   # 允许短时 3 次突发


class _RateLimiter:
    """令牌桶：按 rate_limit_per_minute 自律限速（匿名接口无速率保障）。"""

    def __init__(self, per_minute: float) -> None:
        self._interval = 60.0 / max(1.0, per_minute) if per_minute else 0.0
        self._tokens = _RATE_BURST
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, stop_event: threading.Event | None = None) -> bool:
        """等到有令牌。stop_event 被置则返回 False。"""
        if self._interval <= 0:
            return True
        while True:
            with self._lock:
                now = time.monotonic()
                refill = (now - self._last) / self._interval
                self._tokens = min(_RATE_BURST, self._tokens + refill)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                wait = (1.0 - self._tokens) * self._interval
            if stop_event is not None and stop_event.is_set():
                return False
            time.sleep(min(wait, 0.25))


class GGNetworkProvider(DownloadProvider):
    meta = ProviderMeta(
        name="ggnetwork",
        display_name="GGNetwork 代理（匿名加速，实验性）",
        kind=ProviderKind.PROXY,
        requires_key=False,
        anonymous_ok=True,
        priority=20,              # 优于 cdn（同样匿名且通常更快），劣于 steamcmd 兜底
    )

    def __init__(self, config: dict, api=None) -> None:
        super().__init__(config, api)
        rate = 0.0
        try:
            rate = float(self.config.get("rate_limit_per_minute") or _DEFAULT_RATE_LIMIT)
        except (TypeError, ValueError):  # noqa: BLE001
            rate = _DEFAULT_RATE_LIMIT
        self._limiter = _RateLimiter(rate)
        self._stopping = threading.Event()

    # ---------------- 探测
    def probe(self, timeout: float = 8.0) -> Availability:
        # 匿名接口：发一次轻量请求看是否 200
        try:
            url = self._item_url(_PROBE_ITEM)
            if not self._limiter.acquire():
                return Availability.UNREACHABLE
            sess = self._session()
            r = sess.post(_GG_URL, json={"url": url}, timeout=timeout)
            if r.status_code == 200:
                return Availability.OK
            if r.status_code == 429:
                self._report_throttle("rate_limit", "GGNetwork HTTP 429")
                return Availability.UNREACHABLE
            log.debug("GGNetwork 探测失败：HTTP %s", r.status_code)
            return Availability.UNREACHABLE
        except Exception as e:  # noqa: BLE001
            log.debug("GGNetwork 探测异常: %s", e)
            return Availability.UNREACHABLE

    def _item_url(self, item_id: str) -> str:
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"

    # ---------------- 解析
    def resolve(self, item: WorkshopItem) -> str:
        """POST 换取官方 CDN 直链。失败返回 ''。"""
        if not self._limiter.acquire():
            return ""
        try:
            sess = self._session()
            r = sess.post(_GG_URL, json={"url": self._item_url(str(item.publishedfileid))},
                          timeout=30)
            if r.status_code != 200:
                if r.status_code == 429:
                    self._report_throttle("rate_limit", "GGNetwork HTTP 429")
                return ""
            try:
                data = r.json()
            except json.JSONDecodeError:
                return ""
            # 兼容多种响应形状：直接 url / data.url / 嵌套
            url = (data.get("url") or (data.get("data") or {}).get("url") or "").strip()
            return url
        except Exception:  # noqa: BLE001
            log.debug("GGNetwork resolve 失败", exc_info=True)
            return ""

    # ---------------- 下载
    def download(
        self,
        item: WorkshopItem,
        dest_dir: str,
        on_progress=None,
        stop_event: threading.Event | None = None,
        total_hint: int = 0,
    ) -> DownloadResult:
        item_id = str(item.publishedfileid)
        appid = str(item.appid)
        result = DownloadResult(item_id=item_id, appid=appid,
                                status=DownloadStatus.RUNNING)

        url = self.resolve(item)
        if not url:
            result.status = DownloadStatus.FAILED
            result.message = "GGNetwork 无法解析下载地址（服务不可用或被限流）"
            return result

        filename = os.path.basename(url.split("?")[0]) or f"{item_id}.gma"
        dest_path = os.path.join(dest_dir, filename)
        log.info("GGNetwork 下载 %s → %s", item_id, dest_path)

        res = self.http_download(
            url, dest_path, self._session(),
            on_progress=on_progress, stop_event=stop_event,
        )
        res.item_id = item_id
        res.appid = appid

        if res.status == DownloadStatus.SUCCESS:
            # 压缩包：解压到 content/<appid>/<itemid>
            final_path = self._maybe_extract(dest_path, dest_dir, item_id)
            if final_path != dest_path:
                res.path = final_path
            # .gma 弱校验 + size 差异
            note = self._verify_content(final_path, item)
            res.message = "GGNetwork 下载成功" + (f"（{note}）" if note else "")
        return res

    def _maybe_extract(self, archive_path: str, dest_dir: str, item_id: str) -> str:
        """若是 zip 压缩包则解压，返回最终内容路径。"""
        try:
            if not zipfile.is_zipfile(archive_path):
                return archive_path
            log.info("GGNetwork 返回压缩包，解压 %s", archive_path)
            extracted_dir = os.path.join(dest_dir, "_extracted")
            os.makedirs(extracted_dir, exist_ok=True)
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extracted_dir)
            # 找到 .gma 或唯一内容文件
            for root, _dirs, files in os.walk(extracted_dir):
                for f in sorted(files):
                    if f.lower().endswith(".gma"):
                        final = os.path.join(root, f)
                        # 移到 content 根，保持与 steamcmd 布局一致
                        final_dst = os.path.join(dest_dir, f)
                        if os.path.abspath(final) != os.path.abspath(final_dst):
                            os.replace(final, final_dst)
                        try:
                            os.remove(archive_path)
                        except OSError:
                            pass
                        return final_dst
            # 无 .gma：可能是多文件 mod，整体目录保留
            return extracted_dir
        except Exception:  # noqa: BLE001
            log.debug("GGNetwork 解压失败，保留原始文件", exc_info=True)
            return archive_path

    def _verify_content(self, path: str, item: WorkshopItem) -> str:
        """弱校验：.gma 魔数 + 声明 size 差异 >1% 返回提示。"""
        notes = []
        try:
            if path.lower().endswith(".gma") and os.path.isfile(path):
                with open(path, "rb") as f:
                    magic = f.read(4)
                if magic != _GMA_MAGIC:
                    notes.append("⚠ 内容非标准 .gma 格式")
        except OSError:
            pass
        try:
            declared = int(getattr(item, "file_size", 0) or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > 0 and os.path.isfile(path):
            actual = os.path.getsize(path)
            if abs(actual - declared) / declared > 0.01:
                notes.append(f"⚠ 实际大小 {actual} 与声明 {declared} 差异 >1%")
        return "；".join(notes)

    # ---------------- 取消 / 回退
    def cancel(self) -> None:
        self._stopping.set()

    def should_fallback(self, result: DownloadResult) -> bool:
        # 解析失败/HTTP 错误/限流 → 回退；内容校验⚠只是提示，不回退
        return result.status == DownloadStatus.FAILED
