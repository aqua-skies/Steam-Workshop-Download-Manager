"""Per-game mod download directory configuration (按游戏配置 mod 下载目录).

Each game (appid) may override steamcmd's ``force_install_dir``; games without
an override fall back to the global library dir (``LIBRARY_DIR``). Persisted in
the ``game_dirs`` section of config.json, keyed by appid.
"""
from __future__ import annotations

import os

from .config import Config, get_config
from .games import game_name
from .paths import LIBRARY_DIR

SECTION = "game_dirs"


def game_install_dir(appid: str, cfg: Config | None = None) -> str:
    """返回指定游戏的 mod 下载根目录；未单独配置则回退全局库目录。"""
    cfg = cfg or get_config()
    d = (cfg.get(SECTION, str(appid), default="") or "").strip()
    return d or str(LIBRARY_DIR)


def game_content_root(appid: str, cfg: Config | None = None) -> str:
    """mod 内容实际落地目录：<游戏目录>/steamapps/workshop/content/<appid>。"""
    return os.path.join(
        game_install_dir(appid, cfg), "steamapps", "workshop", "content", str(appid)
    )


def set_game_dir(appid: str, path: str, cfg: Config | None = None) -> str:
    """为游戏设置专属下载目录；空串表示清除（回退全局）。返回生效目录。"""
    cfg = cfg or get_config()
    path = (path or "").strip().rstrip("\\/")
    cfg.set(SECTION, str(appid), path)
    cfg.save()
    return path or str(LIBRARY_DIR)


def clear_game_dir(appid: str, cfg: Config | None = None) -> None:
    """清除某游戏的专属目录配置（回退到全局库目录）。"""
    set_game_dir(appid, "", cfg)


def configured_game_dirs(cfg: Config | None = None) -> dict[str, str]:
    """返回所有已单独配置的游戏目录 {appid: path}。"""
    cfg = cfg or get_config()
    section = cfg.get(SECTION, default={}) or {}
    return {str(k): str(v) for k, v in section.items() if v}


def game_dir_entries(cfg: Config | None = None) -> list[dict]:
    """供 GUI 表格展示：[{appid, name, dir}]，按游戏名排序。"""
    out = []
    for appid, d in configured_game_dirs(cfg).items():
        out.append({"appid": appid, "name": game_name(appid) or appid, "dir": d})
    out.sort(key=lambda e: e["name"])
    return out
