"""Shared circuit breaker: consecutive failures or connection errors trigger a cooldown (共享熔断退避).

Extracted from ``GameSearchClient`` (t22 D) so speculative work — game-name suggestions,
next-page prefetch — shares one protective mechanism instead of each call site
reimplementing it. Without it, a broken network makes speculative threads spin
endlessly burning CPU.

Semantics (identical to the GameSearchClient t22 behavior):
- Connection-level failures (``requests.ConnectionError``, e.g. WinSock 10053)
  trip the breaker immediately.
- Otherwise, 3 consecutive failures trip it.
- While tripped, callers skip their request for a 15s cooldown; the breaker
  half-opens after the cooldown and a success resets the failure streak.
"""
from __future__ import annotations

import threading
import time

try:  # requests is a hard dependency of the app; keep the import local-safe for tests
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from .logger import get_logger

log = get_logger("swdm.core.circuit")

_COOLDOWN_SECONDS = 15.0
_FAIL_STREAK_THRESHOLD = 3


class CircuitBreaker:
    """连接级熔断退避：连续失败或连接错误 → 冷却期内跳过请求。"""

    def __init__(self, cooldown: float = _COOLDOWN_SECONDS,
                 threshold: int = _FAIL_STREAK_THRESHOLD) -> None:
        self._cooldown = max(1.0, float(cooldown))
        self._threshold = max(1, int(threshold))
        self._fail_streak = 0
        self._cooldown_until = 0.0
        self._lock = threading.Lock()

    def in_cooldown(self) -> bool:
        """是否处于熔断冷却期（冷却过后自动半开）。"""
        return time.time() < self._cooldown_until

    def cooldown_remaining(self) -> float:
        return max(0.0, self._cooldown_until - time.time())

    def record_failure(self, e: BaseException | None = None) -> None:
        """记录一次失败：连接级错误或连续达到阈值即熔断。"""
        with self._lock:
            self._fail_streak += 1
            is_conn_err = (
                requests is not None
                and isinstance(e, requests.ConnectionError)
            )
            if is_conn_err or self._fail_streak >= self._threshold:
                self._cooldown_until = time.time() + self._cooldown
                log.warning(
                    "熔断，冷却 %.0fs：%s（连续失败 %d 次）",
                    self._cooldown, e, self._fail_streak,
                )

    def record_success(self) -> None:
        """成功：重置连续失败计数（熔断期内的成功也立即半开恢复）。"""
        with self._lock:
            self._fail_streak = 0

    def force_trip(self, seconds: float | None = None) -> None:
        """测试/手动强制熔断。"""
        with self._lock:
            self._cooldown_until = time.time() + (
                self._cooldown if seconds is None else max(1.0, float(seconds))
            )
