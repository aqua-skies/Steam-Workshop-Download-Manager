"""Shared GUI service container: every tab reaches the core layer through this object (GUI 共享服务容器).

Holds the single SteamAPI / DownloadManager / ModLibrary / AuthManager / SteamCMDEngine
instances and the throttle/circuit-breaker handles, so tabs share one source of truth
instead of constructing their own clients. Since 1.4.0 the DownloadManager takes the
SteamAPI instance it needs (services.py:78 injects api=api).
"""
from __future__ import annotations

from dataclasses import dataclass

from swdm.core import (
    AuthManager,
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
    get_config,
)
from swdm.core.logger import get_logger
from swdm.core.paths import LIBRARY_DIR

log = get_logger("swdm.gui.services")


@dataclass
class Services:
    """Container holding the single shared instances of every core service for the GUI."""

    config: object
    api: SteamAPI
    auth: AuthManager
    library: ModLibrary
    engine: SteamCMDEngine
    downloader: DownloadManager

    def refresh_engine(self) -> None:
        """根据当前配置/认证状态重建引擎参数。"""
        cfg = self.config
        user, pw, guard = self.auth.get_credentials()
        anon = self.auth.is_anonymous()
        self.engine.anonymous = anon
        self.engine.username = user
        self.engine.password = pw
        self.engine.guard_code = guard
        self.engine.exe_path = cfg.get("steamcmd", "exe_path") or ""
        # install_dir 必须有值：配置为空时回落默认库目录
        self.engine.install_dir = (
            cfg.get("steamcmd", "force_install_dir")
            or cfg.get("general", "library_dir")
            or LIBRARY_DIR
        )
        self.engine.validate = cfg.get("steamcmd", "validate", False)
        self.downloader.max_concurrent = max(
            1, int(cfg.get("network", "max_concurrent_downloads") or 2)
        )

    def refresh_api(self) -> None:
        cfg = self.config
        self.api.set_api_key(cfg.get("network", "api_key") or "")
        self.api.api_key = cfg.get("network", "api_key") or ""
        self.api.timeout = int(cfg.get("network", "timeout") or 30)
        self.api._session.proxies.clear()
        proxy = cfg.get("network", "proxy") or ""
        if proxy:
            self.api._session.proxies.update({"http": proxy, "https": proxy})


def build_services() -> Services:
    """Construct and wire all core services (config → auth → api → library → engine → downloader)."""
    cfg = get_config()
    cfg.load()
    auth = AuthManager()
    api = SteamAPI(
        api_key=cfg.get("network", "api_key") or "",
        proxy=cfg.get("network", "proxy") or "",
        timeout=int(cfg.get("network", "timeout") or 30),
    )
    library = ModLibrary()
    engine = SteamCMDEngine(
        exe_path=cfg.get("steamcmd", "exe_path") or "",
        install_dir=cfg.get("steamcmd", "force_install_dir")
        or cfg.get("general", "library_dir")
        or "",
        anonymous=auth.is_anonymous(),
    )
    downloader = DownloadManager(
        engine, library,
        max_concurrent=int(cfg.get("network", "max_concurrent_downloads") or 2),
        auto_retry=1,
        api=api,               # provider 链需要：CDN 通道解析 file_url
    )
    svc = Services(config=cfg, api=api, auth=auth, library=library, engine=engine,
                   downloader=downloader)
    svc.refresh_engine()
    return svc
