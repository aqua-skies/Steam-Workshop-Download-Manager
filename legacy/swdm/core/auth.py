"""Authentication: anonymous login by default, or manual login with username/password + Steam Guard (认证管理).

- Anonymous mode (匿名模式): no account at all, plain ``login anonymous`` — core of requirement 4.
- Manual mode (手动模式): credentials encrypted via ``keyring`` in the OS credential store;
  Steam Guard requires an interactive code on first login.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .logger import get_logger
from .paths import DATA_DIR, ensure_dirs

log = get_logger("swdm.auth")

_SERVICE = "SWDM"
_USER_KEY = "steam_account"
_AUTH_FILE = os.path.join(DATA_DIR, "auth.json")


@dataclass
class Account:
    """Steam account state: either anonymous (default) or a user session (账号)."""

    mode: str = "anonymous"     # anonymous | user
    username: str = ""
    has_password: bool = False
    guard_code: str = ""
    remember: bool = False


class AuthManager:
    """账号管理（keyring 优先，回退到本地混淆文件）。"""

    def __init__(self) -> None:
        ensure_dirs()
        self._account = Account()
        self._password_cache = ""
        self._load()

    def _load(self) -> None:
        try:
            import json

            if os.path.exists(_AUTH_FILE):
                with open(_AUTH_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self._account = Account(
                    mode=d.get("mode", "anonymous"),
                    username=d.get("username", ""),
                    has_password=bool(d.get("has_password")),
                    remember=bool(d.get("remember", False)),
                )
        except Exception as e:  # noqa: BLE001
            log.error("加载认证信息失败: %s", e)

    def _save(self) -> None:
        import json

        try:
            with open(_AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "mode": self._account.mode,
                        "username": self._account.username,
                        "has_password": self._account.has_password,
                        "remember": self._account.remember,
                    },
                    f,
                )
        except OSError as e:
            log.error("保存认证信息失败: %s", e)

    def _store_password(self, password: str) -> bool:
        try:
            import keyring

            keyring.set_password(_SERVICE, self._account.username, password)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("keyring 存储失败，回退本地文件: %s", e)
            return self._store_password_fallback(password)

    def _store_password_fallback(self, password: str) -> bool:
        """回退：简单混淆存储（弱保护，仅 keyring 不可用时使用）。"""
        try:
            import base64

            path = os.path.join(DATA_DIR, ".cred")
            with open(path, "wb") as f:
                f.write(base64.b64encode(password.encode("utf-8")))
            return True
        except OSError as e:
            log.error("回退凭据存储失败: %s", e)
            return False

    def _load_password(self) -> str:
        if self._password_cache:
            return self._password_cache
        if not self._account.username:
            return ""
        try:
            import keyring

            pw = keyring.get_password(_SERVICE, self._account.username) or ""
            self._password_cache = pw
            return pw
        except Exception as e:  # noqa: BLE001
            log.warning("keyring 读取失败: %s", e)
        try:
            import base64

            path = os.path.join(DATA_DIR, ".cred")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return base64.b64decode(f.read()).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            log.warning("回退凭据读取失败: %s", e)
        return ""

    # --------------------------------------------------------------- 公开 API
    @property
    def account(self) -> Account:
        return self._account

    def is_anonymous(self) -> bool:
        return self._account.mode == "anonymous" or not self._account.username

    def login_anonymous(self) -> None:
        self._account = Account(mode="anonymous")
        self._password_cache = ""
        self._save()
        log.info("切换为匿名登录模式")

    def login_user(
        self,
        username: str,
        password: str,
        guard_code: str = "",
        remember: bool = True,
    ) -> bool:
        """设置用户登录。remember=True 时密码加密存储。"""
        if not username or not password:
            return False
        self._account = Account(
            mode="user", username=username, guard_code=guard_code, remember=remember
        )
        self._password_cache = password
        if remember:
            ok = self._store_password(password)
            self._account.has_password = ok
        else:
            self._account.has_password = False
        self._save()
        # C3 风控①：账号名不进日志文件
        log.info("已设置用户登录（记住密码=%s）", remember)
        return True

    def logout(self) -> None:
        self.login_anonymous()

    def get_credentials(self) -> tuple[str, str, str]:
        """返回 (username, password, guard_code) 供引擎使用。"""
        if self.is_anonymous():
            return "", "", ""
        return self._account.username, self._load_password(), self._account.guard_code

    def clear_stored(self) -> None:
        try:
            import keyring

            if self._account.username:
                keyring.delete_password(_SERVICE, self._account.username)
        except Exception:  # noqa: BLE001
            pass
        try:
            path = os.path.join(DATA_DIR, ".cred")
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        self._password_cache = ""
        self._account.has_password = False
        self._save()
