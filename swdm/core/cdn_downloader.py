"""CDN 直链通道的兼容门面（1.4.0 平迁）。

**1.4.1 将移除本文件**——新代码请直接用 swdm.core.providers.cdn
（CDNProvider）或通过 ProviderRegistry 使用通道链。

实现已迁移到 swdm/core/providers/cdn.py（DownloadProvider 抽象）。
本文件保留旧 API（resolve_file_url / download_file / download_item_cdn）
供既有调用方与测试（test_cdn.py / test_core_sweep.py）零改动使用。
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
