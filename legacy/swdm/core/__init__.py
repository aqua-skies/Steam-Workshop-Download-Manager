"""SWDM core layer: Steam Workshop browsing, download and management (核心层)."""
from .auth import Account, AuthManager
from .config import Config, get_config
from .conflict_extractor import ConflictInfo, check_installed_conflicts, extract_conflicts
from .deps_parser import parse_required_items, parse_required_items_robust
from .downloader import DownloadJob, DownloadManager, JobStatus
from .game_dirs import (
    clear_game_dir,
    configured_game_dirs,
    game_content_root,
    game_dir_entries,
    game_install_dir,
    set_game_dir,
)
from .games import all_games, game_name
from .logger import get_logger, setup_logger, subscribe, snapshot
from .mod_library import ModLibrary, ModRecord
from .page_parser import fetch_comments, parse_available_tags, parse_comments, parse_description
from .paths import APP_DISPLAY, APP_NAME, APP_VERSION, ensure_dirs
from .steam_api import RateLimitError, SteamAPI, WorkshopItem
from .steamcmd_deploy import deployment_status, deploy, ensure_steamcmd, is_deployed
from .steamcmd_engine import DownloadResult, DownloadStatus, SteamCMDEngine

__all__ = [
    "Account",
    "AuthManager",
    "APP_DISPLAY",
    "APP_NAME",
    "APP_VERSION",
    "all_games",
    "check_installed_conflicts",
    "clear_game_dir",
    "Config",
    "configured_game_dirs",
    "ConflictInfo",
    "deployment_status",
    "deploy",
    "DownloadJob",
    "DownloadManager",
    "DownloadResult",
    "DownloadStatus",
    "extract_conflicts",
    "fetch_comments",
    "game_content_root",
    "game_dir_entries",
    "game_install_dir",
    "get_config",
    "get_logger",
    "game_name",
    "is_deployed",
    "JobStatus",
    "ModLibrary",
    "ModRecord",
    "parse_available_tags",
    "parse_comments",
    "parse_description",
    "parse_required_items",
    "parse_required_items_robust",
    "RateLimitError",
    "set_game_dir",
    "setup_logger",
    "subscribe",
    "snapshot",
    "SteamAPI",
    "SteamCMDEngine",
    "ensure_dirs",
    "WorkshopItem",
]
