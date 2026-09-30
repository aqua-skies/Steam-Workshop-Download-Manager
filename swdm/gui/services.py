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
        """根据当前配置重建引擎参数。

        C3（1.4.1）：共享/兜底引擎恒为匿名——账号凭据只进
        AccountSteamCMDProvider 的专属引擎实例，账号问题永远不会
        阻塞链尾兜底下载（t31 风控③）。用户改凭据时重置账号通道的
        会话级失活标记。
        """
        cfg = self.config
        self.engine.anonymous = True
        self.engine.username = ""
        self.engine.password = ""
        self.engine.guard_code = ""
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
        # 账号通道：注入 AuthManager + 清除会话级失活（用户刚保存新凭据）
        try:
            from swdm.core.providers.account_steamcmd import (
                reset_auth_state,
                set_auth_manager,
            )

            set_auth_manager(self.auth)
            reset_auth_state()
        except Exception:  # noqa: BLE001
            log.debug("账号通道状态重置失败", exc_info=True)

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
    # C3：共享引擎恒匿名；账号登录由 AccountSteamCMDProvider 用专属引擎承载
    engine = SteamCMDEngine(
        exe_path=cfg.get("steamcmd", "exe_path") or "",
        install_dir=cfg.get("steamcmd", "force_install_dir")
        or cfg.get("general", "library_dir")
        or "",
        anonymous=True,
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
