"""Path resolution: single entry point for app data dirs, config, logs and the mod repository (路径解析).

Windows default is ``%APPDATA%/SWDM``; a ``portable.marker`` file next to the
executable switches storage to ``<root>/data`` (portable mode / 便携模式).
"""
from __future__ import annotations

import os
import sys

APP_NAME = "SWDM"
APP_DISPLAY = "Steam 工坊下载管理器"
APP_VERSION = "1.4.0"  # bumped per release; mirrors installer/swdm.iss SWDMVersion


def _user_data_root() -> str:
    """User data root dir. Windows: ``%APPDATA%/SWDM``; honors portable mode."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    marker = os.path.join(base, "portable.marker")
    if os.path.exists(marker):
        return os.path.join(base, "data")

    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(root, APP_NAME)
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, APP_NAME)


DATA_DIR = _user_data_root()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")
DB_FILE = os.path.join(DATA_DIR, "library.db")
CACHE_DIR = os.path.join(DATA_DIR, "cache")          # 图片缓存
STEAMCMD_DIR = os.path.join(DATA_DIR, "steamcmd")    # 内置 steamcmd 工作区
LIBRARY_DIR = os.path.join(DATA_DIR, "mods")         # mod 仓库默认根目录
CRASH_FILE = os.path.join(DATA_DIR, "crash.log")


def ensure_dirs() -> None:
    """Create the data / cache / log / steamcmd / library directories if missing."""
    for d in (DATA_DIR, LOG_DIR, CACHE_DIR, STEAMCMD_DIR, LIBRARY_DIR):
        os.makedirs(d, exist_ok=True)


def resource_path(*parts: str) -> str:
    """解析打包后（PyInstaller）与开发态的资源路径。

    约定：parts 从项目根（打包态为 _MEIPASS）开始，如
    resource_path("swdm", "resources", "icon.ico")。
    """
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, *parts)


# 内置 steamcmd：随程序分发的官方 steamcmd.zip（仅含 steamcmd.exe，
# 首次运行会自更新补齐组件）。解压到 STEAMCMD_DIR 后即可使用
BUNDLED_STEAMCMD_ZIP = resource_path("swdm", "resources", "steamcmd.zip")
DEPLOYED_STEAMCMD_EXE = os.path.join(STEAMCMD_DIR, "steamcmd.exe")


def bundled_steamcmd_zip() -> str:
    """随程序分发的 steamcmd.zip 路径（打包态/开发态均可定位）。"""
    return BUNDLED_STEAMCMD_ZIP


def deployed_steamcmd_exe() -> str:
    """内置 steamcmd 解压后的可执行文件路径。"""
    return DEPLOYED_STEAMCMD_EXE
