"""Configuration management: persistent settings with recursive merge and validation (配置管理).

Layered JSON config under the data dir: defaults are merged with the user file
via ``Config._merge`` so partial user configs keep new default keys. Since 1.4.0
the ``download.providers.{name}`` block is merged three levels deep.
"""
from __future__ import annotations

import copy
import json
import os
import threading

from .paths import CONFIG_FILE, ensure_dirs
from .logger import get_logger

log = get_logger("swdm.config")

DEFAULT_CONFIG = {
    "general": {
        "language": "zh_CN",
        "theme": "dark",
        "library_dir": "",            # 空表示用默认 LIBRARY_DIR
        "check_update_on_start": True,
        "close_to_tray": False,
    },
    "network": {
        "api_key": "",                # 可选的 Steam Web API key
        "proxy": "",                  # 如 http://127.0.0.1:7890
        "timeout": 30,
        "max_concurrent_downloads": 3,
        "use_system_cert_store": True,
    },
    "steamcmd": {
        "exe_path": "",               # 空表示自动检测/使用内置
        "force_install_dir": "",      # 空表示用 LIBRARY_DIR/steamapps
        "anonymous": True,            # 匿名登录（无需账号）
        "username": "",
        "remember_password": False,
        "validate": False,            # 下载后验证
    },
    "download": {
        # 下载通道（provider 链的 preferred）：steamcmd（匿名稳定，默认）
        # / cdn（HTTP 直链，需登录态才有 file_url）/ ggnetwork（匿名代理，实验性）
        # 无论选哪个，失败都沿 registry 链回退，steamcmd 永远链尾兜底
        "channel": "steamcmd",
        # 每 provider 独立配置节（enabled 关掉某通道；其余字段由 provider 自取）
        "providers": {
            "steamcmd": {
                "enabled": True,
            },
            "cdn": {
                "enabled": True,
            },
            "ggnetwork": {
                "enabled": True,
                "rate_limit_per_minute": 20,  # 匿名接口自律限速（ToS §5.2.2）
            },
        },
    },
    "dependencies": {
        "auto_download": True,        # 下载时自动带上下递归解析出的前置依赖
        "ask_before_download": True,  # 有依赖时弹窗确认（关闭则静默全部下载）
        "max_depth": 10,              # 依赖树最大递归深度（防循环引用）
        "skip_installed": True,       # 跳过已安装的依赖
    },
    "game_dirs": {
        # 按游戏配置 mod 下载目录：{"<appid>": "<目录路径>"}
        # 未列出的游戏回退到 library_dir
    },
    "library": {
        "organize_by_game": True,     # 按游戏分目录
        "keep_steamcmd_layout": True, # 保留 steamapps/workshop/content/<appid>/<id> 结构
        "auto_write_metadata": True,  # 写入 mod 元数据 JSON
        "auto_import_on_complete": True,
    },
    "logging": {
        "level": "INFO",
        "show_debug_panel": False,
    },
    "favorites_games": [],            # 收藏的游戏 appid
    "custom_games": [],               # 用户自定义游戏 [{appid, name}]
    # F7：标题过滤词——工坊列表中标题含任一关键词的 mod 隐藏
    # （如 "Dead" "废弃" "Outdated"），降低浏览噪音
    "hide_keywords": [],
}


class Config:
    """线程安全的配置单例。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self._file_lock = threading.Lock()
        self.load()

    @classmethod
    def instance(cls) -> "Config":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def load(self) -> None:
        ensure_dirs()
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._merge(data)
                log.info("配置已加载: %s", CONFIG_FILE)
        except Exception as e:  # noqa: BLE001
            log.error("加载配置失败，使用默认配置: %s", e)

    def _merge(self, data: dict) -> None:
        """递归合并：保留默认结构，用用户值覆盖。"""
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(self._data.get(key), dict):
                for k2, v2 in value.items():
                    if isinstance(v2, dict) and isinstance(self._data[key].get(k2), dict):
                        self._data[key][k2].update(v2)
                    else:
                        self._data[key][k2] = v2
            else:
                self._data[key] = value

    def save(self) -> None:
        with self._file_lock:
            try:
                ensure_dirs()
                tmp = CONFIG_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, CONFIG_FILE)
                log.info("配置已保存")
            except Exception as e:  # noqa: BLE001
                log.error("保存配置失败: %s", e)

    def get(self, *keys, default=None):
        node = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def set(self, *keys_and_value) -> None:
        if len(keys_and_value) < 2:
            raise ValueError("need at least one key and a value")
        *keys, value = keys_and_value
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    def as_dict(self) -> dict:
        return copy.deepcopy(self._data)

    def reset(self) -> None:
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self.save()


def get_config() -> Config:
    """Return the process-wide singleton Config instance."""
    return Config.instance()
