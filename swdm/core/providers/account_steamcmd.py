"""Private-account SteamCMD channel — the only compliant way past the report-confirm blocker (C3 私人账号通道).

Compliance layering (t31 决议 C3): there is **no** compliant way to bypass Steam's license
checks for content the user does not own (three layers: license check, signed file_url,
depot key). This channel is the one legitimate path: it logs the user's **own** Steam
account into steamcmd and downloads content **that account is entitled to**. The public
account-pool interface stays reserved and disabled — this module never shares or pools
credentials with any third party.

Chain placement (priority 90, before the anonymous ``steamcmd`` terminal tail):
- ``is_configured()`` is True only while an account is actually logged in, so the
  **default chain (anonymous) never contains this channel** — build_chain assertion.
- Failures are ``breaker_exempt`` (t31 风控③): a bad password / expired Guard code must
  not melt any channel, and especially not the anonymous steamcmd tail.
- After the first auth failure the channel self-disables for the session
  (``_auth_dead``) so subsequent jobs skip the login attempt instead of spamming the
  Steam login server (which rate-limits fast). It re-arms the moment the user changes
  credentials in Settings (``Services.refresh_engine`` → ``reset_auth_state``).

Credentials never enter config, logs or exports (see ``SteamCMDEngine._redact_secrets``
for the output filter and ``AuthManager`` keyring storage).
"""
from __future__ import annotations

import threading

from ..logger import get_logger
from ..steam_api import WorkshopItem
from ..steamcmd_engine import DownloadResult, DownloadStatus, SteamCMDEngine
from .base import Availability, DownloadProvider, ProviderKind, ProviderMeta

log = get_logger("swdm.core.providers.account_steamcmd")

# AuthManager 引用由 GUI 服务容器注入（services.build_services 一次）。
# provider 实例由 registry 按 config 快照懒重建，故凭据在 download 时实时读取，
# 而不是在 __init__ 时固化（否则配置变更后会用到旧凭据）。
_auth_manager = None
_auth_lock = threading.Lock()
_instances: list["AccountSteamCMDProvider"] = []   # 会话级失活重置用


def set_auth_manager(mgr) -> None:
    """注入 AuthManager 单例（GUI 层启动时调用一次）。"""
    global _auth_manager
    with _auth_lock:
        _auth_manager = mgr


def get_auth_manager():
    with _auth_lock:
        return _auth_manager


def reset_auth_state() -> None:
    """用户改了凭据：清除全部账号通道实例的会话级失活标记，允许重新尝试登录。"""
    with _auth_lock:
        instances = list(_instances)
    for prov in instances:
        prov._auth_dead = False


_ACCOUNT_FAIL_HINT = (
    "账号登录失败（用户名/密码错误，或需要 Steam Guard 验证码）。"
    "本次下载已自动回退匿名通道；如要使用账号通道，请在「设置 → 账号」"
    "核对凭据——验证码仅首登需要一次。"
)


class AccountSteamCMDProvider(DownloadProvider):
    """Private-account ENGINE channel: user's own account + own entitled content."""

    meta = ProviderMeta(
        name="account_steamcmd",
        display_name="SteamCMD（私人账号·自己有权内容）",
        kind=ProviderKind.ENGINE,
        requires_key=False,          # 凭据走 AuthManager（keyring），不在 config 里
        anonymous_ok=False,          # 必须登录账号才能用
        priority=90,                 # 在匿名 steamcmd 兜底之前
        terminal=False,              # 失败继续回退到匿名 steamcmd
        supports_account=True,       # C3 标记：私人账号通道
        breaker_exempt=True,         # 风控③：凭据失败不熔断任何通道
    )

    def __init__(self, config: dict, api=None, engine: SteamCMDEngine | None = None) -> None:
        super().__init__(config, api)
        self._engine = engine                # 由 DownloadManager 注入共享引擎（借用其 exe/install_dir 配置）
        self._acct_engine: SteamCMDEngine | None = None
        self._acct_creds: tuple = ()
        self._auth_dead = False              # 会话级失活：一次登录失败后本轮不再尝试
        # 登记到模块清单：reset_auth_state（用户改凭据时）遍历重开
        if self not in _instances:
            _instances.append(self)

    # --------------------------------------------------------------- 凭据判定
    def _credentials(self) -> tuple[str, str, str]:
        """实时读取账号凭据（匿名时返回空串三元组）。"""
        mgr = get_auth_manager()
        if mgr is None or mgr.is_anonymous():
            return "", "", ""
        try:
            return mgr.get_credentials()
        except Exception:  # noqa: BLE001
            log.debug("读取账号凭据失败", exc_info=True)
            return "", "", ""

    def is_configured(self) -> bool:
        # 默认链不含：匿名态 / 会话级失活 → 与"未配置凭据"同等待遇被 build_chain 跳过
        user, _pw, _guard = self._credentials()
        return bool(user) and not self._auth_dead

    # --------------------------------------------------------------- 引擎
    def set_engine(self, engine: SteamCMDEngine) -> None:
        self._engine = engine

    @property
    def engine(self) -> SteamCMDEngine | None:
        return self._engine

    def get_engine(self) -> SteamCMDEngine | None:
        """构造（并缓存）账号引擎：沿用共享引擎的 exe/目录配置，覆盖登录参数。

        共享引擎恒为匿名（services.refresh_engine 不再下发账号凭据），
        所以账号路径必须用自己的引擎实例——两个引擎不会同时运行：
        DownloadManager 的 _engine_lock 对所有 ENGINE 通道串行。
        凭据变化时自动重建（缓存按 (user, pw, guard) 签名校验）。
        """
        if self._auth_dead:
            return None
        user, pw, guard = self._credentials()
        base = self._engine
        if not user or base is None:
            return None
        creds_sig = (user, pw or "", guard or "")
        if self._acct_engine is None or self._acct_creds != creds_sig:
            self._acct_engine = SteamCMDEngine(
                exe_path=getattr(base, "exe_path", "") or "",
                install_dir=getattr(base, "install_dir", "") or "",
                anonymous=False,
                username=user,
                password=pw or "",
                guard_code=guard or "",
                validate=bool(getattr(base, "validate", False)),
                stall_timeout=getattr(base, "stall_timeout", 60.0),
                min_bytes_per_sec=getattr(base, "min_bytes_per_sec", 200_000.0),
            )
            # 限流信号出口复用基类订阅（manager 已订阅本 provider）
            self._acct_engine.on_throttle_signal = self.on_throttle_signal
            self._acct_creds = creds_sig
        return self._acct_engine

    # --------------------------------------------------------------- 生命周期
    def probe(self, timeout: float = 8.0) -> Availability:
        if not self.is_configured():
            return Availability.NO_KEY
        base = self._engine
        if base is None:
            return Availability.UNREACHABLE
        return Availability.OK

    def _note_outcome(self, result: DownloadResult) -> None:
        """登录失败 → 会话级失活（风控③：不熔断，只是本会话不再用账号通道，
        避免每个任务都白等一次登录超时；用户改凭据时 reset_auth_state 重开）。"""
        if result.status == DownloadStatus.FAILED and self._is_auth_failure(result):
            if not self._auth_dead:
                log.info("账号通道登录失败，本会话停用账号通道，回退匿名 steamcmd")
            self._auth_dead = True
            result.message = _ACCOUNT_FAIL_HINT

    def note_result(self, result: DownloadResult) -> None:
        """下载管理器钩子：串行锁路径执行完后回报结果，供会话级失活判定。

        manager 对 ENGINE 通道走 ``_run_steamcmd`` 专属引擎路径（install_dir
        语义与终端 steamcmd 一致），provider.download() 的自检逻辑收敛到这里。
        """
        self._note_outcome(result)

    def download(
        self,
        item: WorkshopItem,
        dest_dir: str,
        on_progress=None,
        stop_event: threading.Event | None = None,
        total_hint: int = 0,
    ) -> DownloadResult:
        eng = self.get_engine()
        if eng is None:
            return DownloadResult(
                item_id=str(item.publishedfileid), appid=str(item.appid),
                status=DownloadStatus.FAILED, message=_ACCOUNT_FAIL_HINT,
            )
        result = eng.download_item(
            appid=str(item.appid),
            item_id=str(item.publishedfileid),
            total_hint=total_hint,
            install_dir="",           # 用账号引擎自己的 install_dir（构造时对齐共享引擎）
            on_progress=on_progress,
        )
        self._note_outcome(result)
        return result

    @staticmethod
    def _is_auth_failure(result: DownloadResult) -> bool:
        msg = (result.message or "")
        return any(s in msg for s in ("登录失败", "Login Failure", "Invalid Password",
                                      "Not Logged On", "rate limit", "RateLimit"))

    def cancel(self) -> None:
        eng = self._acct_engine
        if eng is not None:
            try:
                eng.cancel()
            except Exception:  # noqa: BLE001
                log.debug("账号引擎 cancel 异常", exc_info=True)

    def should_fallback(self, result: DownloadResult) -> bool:
        # 账号问题永远不阻塞下载：失败即回退匿名 steamcmd 兜底（安全属性）
        return True
