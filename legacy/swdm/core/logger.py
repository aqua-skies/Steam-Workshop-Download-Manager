"""Logging: rotating file logs plus an in-memory ring buffer subscribed by the GUI debug panel (调试/日志系统).

The ring buffer lets the Debug tab (调试页) stream a live tail without re-reading files.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from collections import deque
from logging.handlers import RotatingFileHandler

from .paths import LOG_DIR, ensure_dirs

_MAX_BUFFER = 2000
_logger: logging.Logger | None = None
_ring: deque[dict] = deque(maxlen=_MAX_BUFFER)
_ring_lock = threading.Lock()
_subscribers: list = []          # GUI 订阅者回调
_sub_lock = threading.Lock()
_init_once = False


class _RingHandler(logging.Handler):
    """把每条记录存入环形缓冲并广播给 GUI 订阅者。"""

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "time": self.format_time(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["message"] += "\n" + self.format(record).split("\n", 1)[-1]
        with _ring_lock:
            _ring.append(entry)
        with _sub_lock:
            for cb in list(_subscribers):
                try:
                    cb(entry)
                except Exception:
                    pass

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        return logging.Formatter.formatTime(logging.Formatter(), record)


def subscribe(callback) -> None:
    """注册实时日志回调（GUI Debug 面板）。"""
    with _sub_lock:
        if callback not in _subscribers:
            _subscribers.append(callback)


def unsubscribe(callback) -> None:
    """Stop a previously subscribed callback from receiving ring-buffer records."""
    with _sub_lock:
        if callback in _subscribers:
            _subscribers.remove(callback)


def snapshot() -> list[dict]:
    """Copy of the current in-memory ring buffer (most recent records)."""
    with _ring_lock:
        return list(_ring)


def setup_logger(level: str = "INFO") -> logging.Logger:
    """初始化根 logger。可重复调用（运行时调整级别）。"""
    global _logger, _init_once
    ensure_dirs()

    numeric = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "swdm.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(numeric)
    root.addHandler(file_handler)

    ring = _RingHandler()
    ring.setLevel(numeric)
    root.addHandler(ring)

    if not _init_once:
        logging.getLogger("swdm").info(
            "==== %s 日志系统启动 (level=%s) ====", "SWDM", level.upper()
        )
        _init_once = True
    _logger = root
    return root


def get_logger(name: str = "swdm") -> logging.Logger:
    """Named logger attached to the configured root (auto-initializes on first call)."""
    if _logger is None:
        setup_logger()
    return logging.getLogger(name)


class DebugChannel:
    """给 GUI 用的双向调试通道：可注入命令、读取队列。"""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()

    def push(self, item) -> None:
        self._queue.put(item)

    def get(self, timeout: float = 0.1):
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
