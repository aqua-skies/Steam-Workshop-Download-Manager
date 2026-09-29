"""SteamCMD channel provider — wraps the existing SteamCMDEngine, behavior unchanged (链尾兜底).

The terminal tail of every chain: anonymous-capable and stable. It is the only ENGINE-kind
provider that needs no URL resolution at all — the download is performed by the steamcmd
subprocess; the provider only assembles parameters and bridges stop_event → engine.cancel.
``should_fallback()`` is always False: when the chain reaches this provider, it ends here.
"""
from __future__ import annotations

import threading

from ..logger import get_logger
from ..steam_api import WorkshopItem
from ..steamcmd_engine import DownloadResult, DownloadStatus, SteamCMDEngine
from .base import Availability, DownloadProvider, ProviderKind, ProviderMeta

log = get_logger("swdm.core.providers.steamcmd")


class SteamCMDProvider(DownloadProvider):
    """Terminal ENGINE channel: wraps SteamCMDEngine; always the last fallback in a chain."""

    meta = ProviderMeta(
        name="steamcmd",
        display_name="SteamCMD（内置，匿名稳定）",
        kind=ProviderKind.ENGINE,
        requires_key=False,
        anonymous_ok=True,
        priority=100,          # 数值大=链尾兜底
        terminal=True,         # 链终结者：到 steamcmd 不再追加后续通道
    )

    def __init__(self, config: dict, api=None, engine: SteamCMDEngine | None = None) -> None:
        super().__init__(config, api)
        # engine 由 DownloadManager 注入（共享单例，串行锁在 manager 侧）
        self._engine = engine

    @property
    def engine(self) -> SteamCMDEngine | None:
        return self._engine

    def set_engine(self, engine: SteamCMDEngine) -> None:
        self._engine = engine

    def probe(self, timeout: float = 8.0) -> Availability:
        if self._engine is None:
            return Availability.UNREACHABLE
        try:
            exe = self._engine.resolve_exe()
        except Exception:  # noqa: BLE001
            exe = ""
        # exe 为空表示自动检测模式（运行时才定位内置/用户路径），
        # 不判不可用——保持与 1.3.9 相同的"启动时宽松"行为。
        return Availability.OK

    def download(
        self,
        item: WorkshopItem,
        dest_dir: str,
        on_progress=None,
        stop_event: threading.Event | None = None,
        total_hint: int = 0,
    ) -> DownloadResult:
        if self._engine is None:
            return DownloadResult(
                item_id=str(item.publishedfileid), appid=str(item.appid),
                status=DownloadStatus.FAILED, message="SteamCMD 引擎未初始化",
            )
        # engine.download_item 不接受 stop_event；取消由 manager 在 cancel()
        # 时调 engine.cancel() 触发（_cancel_flag 在引擎内部生效）。
        # 此处不在入口拦截 stop_event：保持 1.3.9 语义——引擎自己跑完并
        # 返回 CANCELLED/FAILED，由 _exec_job 的取消路径判定状态。
        return self._engine.download_item(
            appid=str(item.appid),
            item_id=str(item.publishedfileid),
            total_hint=total_hint,
            install_dir=dest_dir or "",
            on_progress=on_progress,
        )

    def cancel(self) -> None:
        if self._engine is not None:
            try:
                self._engine.cancel()
            except Exception:  # noqa: BLE001
                log.debug("engine.cancel 异常", exc_info=True)

    def should_fallback(self, result: DownloadResult) -> bool:
        # steamcmd 是链尾：任何失败都不再回退（无下一通道）
        return False
