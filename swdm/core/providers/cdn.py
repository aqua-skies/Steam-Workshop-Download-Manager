"""CDN 直链通道（从 cdn_downloader.py 平迁为 provider）。

匿名场景 file_url 为空（Steam 限制）→ FAILED + should_fallback=True，
由 registry 链回退到 steamcmd。登录态下返回带签名的 CDN 直链，
HTTP 流式 + Range 续传。
"""
from __future__ import annotations

import os
import threading

from ..logger import get_logger
from ..steam_api import SteamAPI, WorkshopItem
from ..steamcmd_engine import DownloadResult, DownloadStatus
from .base import Availability, DownloadProvider, ProviderKind, ProviderMeta

log = get_logger("swdm.core.providers.cdn")

# 匿名 Web API 的 file_url 通常为空；登录态下才返回带签名的 CDN 直链
_MIN_FILE_URL_LEN = 16

_FALLBACK_HINT = (
    "CDN 直链不可用：Steam 不向匿名会话开放文件下载（file_url 为空）。"
    "已自动回退到内置 SteamCMD 通道。如需使用 CDN 通道，请在设置中"
    "登录账号后重试。"
)


class CDNProvider(DownloadProvider):
    meta = ProviderMeta(
        name="cdn",
        display_name="CDN 直链（HTTP 高速，需登录）",
        kind=ProviderKind.HTTP,
        requires_key=False,
        anonymous_ok=False,
        priority=10,
    )

    def probe(self, timeout: float = 8.0) -> Availability:
        # CDN 通道可用性取决于 file_url 是否可解析：匿名时 NO_KEY 语义
        # （"缺凭据"），登录态由 resolve() 在下载时实时判定。
        if self.api is None:
            return Availability.NO_KEY
        try:
            anonymous = getattr(self.api, "api_key", "") == ""
        except Exception:  # noqa: BLE001
            anonymous = True
        return Availability.NO_KEY if anonymous else Availability.OK

    def resolve(self, item: WorkshopItem) -> str:
        """优先用物品已携带的 file_url；否则查 Web API 补全。"""
        url = (getattr(item, "file_url", "") or "").strip()
        if len(url) >= _MIN_FILE_URL_LEN:
            return url
        if self.api is None or not item.publishedfileid:
            return ""
        try:
            details = self.api.get_file_details([str(item.publishedfileid)])
            rec = details.get(str(item.publishedfileid))
            if rec:
                url = (getattr(rec, "file_url", "") or "").strip()
        except Exception:  # noqa: BLE001
            log.debug("CDN 直链解析失败", exc_info=True)
            return ""
        return url if len(url) >= _MIN_FILE_URL_LEN else ""

    def download(
        self,
        item: WorkshopItem,
        dest_dir: str,
        on_progress=None,
        stop_event: threading.Event | None = None,
        total_hint: int = 0,
    ) -> DownloadResult:
        result = DownloadResult(
            item_id=str(item.publishedfileid),
            appid=str(item.appid),
            status=DownloadStatus.RUNNING,
        )

        url = self.resolve(item)
        if not url:
            result.status = DownloadStatus.FAILED
            result.message = _FALLBACK_HINT
            log.info("物品 %s 无可用 CDN 直链（匿名），将回退 SteamCMD",
                     item.publishedfileid)
            return result

        filename = os.path.basename(url.split("?")[0]) or f"{item.publishedfileid}.gma"
        dest_path = os.path.join(dest_dir, filename)
        log.info("CDN 直链下载 %s → %s", item.publishedfileid, dest_path)

        res = self.http_download(
            url, dest_path, self._session(),
            on_progress=on_progress, stop_event=stop_event,
        )
        res.item_id = result.item_id
        res.appid = result.appid
        if res.status == DownloadStatus.SUCCESS:
            res.message = "CDN 下载成功"
        return res

    def should_fallback(self, result: DownloadResult) -> bool:
        # 匿名无直链、HTTP 4xx/5xx、写入失败都回退 steamcmd。
        # 取消不回退（用户主动行为）。
        return result.status == DownloadStatus.FAILED

    def cancel(self) -> None:
        # http_download 靠 stop_event 轮询取消，无需额外动作
        pass
