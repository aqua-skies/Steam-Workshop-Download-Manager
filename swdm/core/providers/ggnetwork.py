"""GGNetwork channel — a pilot third-party provider of the anonymous PROXY kind (匿名代理通道).

Empirical research: see research/provider_research.md:
- POST https://api.ggntw.com/steam.request with body {"url": <workshop item page URL>}
- Anonymous, no key required (verified 200); returns an official CDN direct link plus
  id / game / name / size / update
- ToS §5.2.2 forbids excessive server load → self-imposed rate limit (default 20 req/min;
  the limiter only covers the resolve POST, not CDN transfer, so download speed is unaffected)
- If the response body is a zip archive it is extracted before landing; a .gma magic-number
  weak check plus a >1% size discrepancy mark the content bad (t28: FAILED with in-chain
  fallback, not just a warning); a queue.position > 0 response yields an empty URL and a
  clean fallback to steamcmd

Honest disclosure: this channel has only been validated against offline mocks; the real
network path was never exercised end-to-end from this machine (proxy environment).
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


def _safe_remove(path: str) -> None:
    """删坏包残留（文件或目录），失败不致命。"""
    try:
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass

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
    """Anonymous third-party PROXY channel (pilot, experimental): resolves via api.ggntw.com."""

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
            # 服务端排队中（未缓存物品，服务端用自有账号代下）：干净回退，不轮询
            q = data.get("queue") or (data.get("data") or {}).get("queue") or {}
            try:
                if int(q.get("position", 0) or 0) > 0:
                    return ""
            except (TypeError, ValueError):
                pass
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
            note, size_bad = self._verify_content(final_path, item)
            if size_bad:
                # 坏包：清残留后判失败，链内回退到 steamcmd 重下（不消耗 auto_retry）
                _safe_remove(final_path)
                res.status = DownloadStatus.FAILED
                res.message = ("内容大小与 Steam 声明不符（可能下载不完整），"
                               "已回退 SteamCMD 重下")
                return res
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

    def _verify_content(self, path: str, item: WorkshopItem) -> tuple[str, bool]:
        """弱校验：.gma 魔数 + 声明 size 差异 >1%。

        返回 (提示文案, 尺寸严重不符)。尺寸差异 >1% 视为坏包——
        比较的是解压后 .gma 实际字节 vs Steam 声明的原始 .gma 字节数，
        zip 转存不进入该比较（先解压再校验），故误伤面很小。
        """
        notes = []
        size_bad = False
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
                size_bad = True
                notes.append(f"⚠ 实际大小 {actual} 与声明 {declared} 差异 >1%")
        return ("；".join(notes), size_bad)

    # ---------------- 取消 / 回退
    def cancel(self) -> None:
        self._stopping.set()

    def should_fallback(self, result: DownloadResult) -> bool:
        # 失败（含尺寸不符的坏包判定）→ 回退；取消不回退
        return result.status == DownloadStatus.FAILED
