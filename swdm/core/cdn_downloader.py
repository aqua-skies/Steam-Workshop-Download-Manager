"""Compatibility facade for the CDN direct-link channel (CDN 直链通道兼容门面, 1.4.0 migration).

**This file will be removed in 1.4.1** — new code should use ``swdm.core.providers.cdn``
(``CDNProvider``) directly, or the channel chain via ``ProviderRegistry``.

The implementation has moved to ``swdm/core/providers/cdn.py`` (as a ``DownloadProvider``).
This module keeps the legacy API (``resolve_file_url`` / ``download_file`` /
``download_item_cdn``) so existing callers and tests (test_cdn.py / test_core_sweep.py)
keep working unchanged.
"""
from __future__ import annotations

from .logger import get_logger
from .providers.cdn import CDNProvider, _MIN_FILE_URL_LEN
from .steam_api import SteamAPI, WorkshopItem
from .steamcmd_engine import DownloadResult, DownloadStatus

log = get_logger("swdm.core.cdn")

# 门面共享的 provider 实例（api 每次调用时注入）
_facade = CDNProvider(config={})


def resolve_file_url(item: WorkshopItem, api: SteamAPI | None = None) -> str:
    """解析物品文件的 CDN 直链（旧 API，语义不变）。"""
    _facade.api = api
    return _facade.resolve(item)


def _session(api: SteamAPI | None):
    _facade.api = api
    return _facade._session()


def download_file(
    url: str,
    dest_path: str,
    session=None,
    on_progress=None,
    chunk_size: int = 1 << 16,
) -> dict:
    """HTTP 流式下载（旧 API，返回 {"ok", "bytes", "message"}）。"""
    res = _facade.http_download(
        url, dest_path, session, on_progress=on_progress,
        chunk_size=chunk_size,
    )
    return {
        "ok": res.status == DownloadStatus.SUCCESS,
        "bytes": res.bytes_done,
        "message": res.message if res.status != DownloadStatus.SUCCESS
        else "下载完成",
    }


def download_item_cdn(
    item: WorkshopItem,
    dest_dir: str,
    api: SteamAPI | None = None,
    on_progress=None,
) -> DownloadResult:
    """用 CDN 直链下载工坊物品（旧 API，语义不变）。"""
    _facade.api = api
    return _facade.download(item, dest_dir, on_progress=on_progress)


__all__ = [
    "resolve_file_url",
    "download_file",
    "download_item_cdn",
]
