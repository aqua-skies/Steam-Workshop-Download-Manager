"""Backoff / jitter / adaptive concurrency / progress smoothing strategies (退避/抖动/并发自适应/进度平滑).

Goal (requirements 1 and 3): keep SWDM's request pattern from looking robotic so Steam
does not refuse us:
- ``jittered`` — randomized inter-task jitter that breaks up regular request cadence
- ``Backoff`` — global exponential backoff on consecutive failures (capped), recovering
  slowly after successes
- ``AdaptiveConcurrency`` — drop concurrency to 1 the moment a rejection/failure signature
  appears, and ramp back up only after sustained success
- ``classify_steamcmd_line`` — recognize RateLimit / Timeout / TimeoutException / Retrying
  signatures in steamcmd output (samples in tests/fixtures/steamcmd_*.txt)
- ``ProgressSmoother`` — UI progress throttling (~10Hz) with monotonic bytes plus
  speed/ETA estimation (deque rolling window, 滚动窗口速度采样)

All pure logic, no IO, thread-safe — directly unit-testable (tests/test_throttle.py).
"""
from __future__ import annotations

import random
import re
import threading
import time
from collections import deque
from typing import Optional

__all__ = [
    "jittered",
    "Backoff",
    "AdaptiveConcurrency",
    "ProgressSmoother",
    "classify_steamcmd_line",
]

_MB = 1024 * 1024


def jittered(base: float, spread: float = 0.3, rng: Optional[random.Random] = None) -> float:
    """在 base 周围做随机抖动：base * (1 ± spread)。base <= 0 时返回 0。

    随机化任务间隔，避免固定的、可被识别为自动化的请求节律。
    """
    if base <= 0:
        return 0.0
    r = rng if rng is not None else random
    spread = max(0.0, min(1.0, spread))
    return max(0.0, base * (1.0 + r.uniform(-spread, spread)))


class Backoff:
    """全局指数退避（带上限与抖动）。

    - 失败：退避等级 +1，等待 base * factor ** level（上限 cap）
    - 成功：退避等级 -1，缓慢回落到基线
    - 软信号（如 steamcmd 内部 Retrying）：nudge() 只小幅抬升等级

    线程安全：下载任务线程与引擎回调线程都可能写入。
    """

    def __init__(
        self,
        base: float = 2.0,
        factor: float = 2.0,
        cap: float = 120.0,
        jitter_spread: float = 0.3,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.base = max(0.0, float(base))
        self.factor = max(1.0, float(factor))
        self.cap = max(self.base, float(cap))
        self.jitter_spread = max(0.0, min(1.0, float(jitter_spread)))
        self._rng = rng
        self._level = 0
        self._lock = threading.Lock()

    @property
    def level(self) -> int:
        with self._lock:
            return self._level

    @property
    def level_delay(self) -> float:
        """当前退避等级对应的基准等待秒数（不含抖动）。"""
        with self._lock:
            return self._delay_unlocked(self._level)

    def _delay_unlocked(self, level: int) -> float:
        return min(self.cap, self.base * (self.factor ** level))

    def record_failure(self, reason: str = "") -> float:
        """记录一次失败：等级 +1，返回建议等待秒数（含抖动）。"""
        with self._lock:
            self._level += 1
            delay = self._delay_unlocked(self._level)
        return jittered(delay, self.jitter_spread, self._rng)

    def nudge(self, max_level: int = 3) -> None:
        """软信号：等级 +1，但永不超过 max_level（也不会下调已有等级）。"""
        with self._lock:
            self._level = min(self._level + 1, max(self._level, max_level))

    def record_success(self) -> None:
        """记录一次成功：等级 -1（缓慢恢复到基线）。"""
        with self._lock:
            self._level = max(0, self._level - 1)

    def reset(self) -> None:
        with self._lock:
            self._level = 0


class AdaptiveConcurrency:
    """并发数自适应：失败特征 -> 立刻降到下限；持续成功 -> 逐步回升到上限。

    - ``on_failure`` 出现拒绝/失败特征时立刻降到 min（通常 1），并清零成功计数
    - ``on_success``  连续 ``successes_to_raise`` 次成功后提升 ``step``，不超过上限
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        min_concurrent: int = 1,
        successes_to_raise: int = 3,
        step: int = 1,
    ) -> None:
        self._max = max(1, int(max_concurrent))
        self._min = max(1, int(min_concurrent))
        self._min = min(self._min, self._max)
        self._successes_to_raise = max(1, int(successes_to_raise))
        self._step = max(1, int(step))
        self._current = self._max
        self._successes = 0
        # 下载任务线程与引擎输出线程都会调用 on_success/on_failure：
        # `_successes += 1` 是 read-modify-write，无锁会丢失计数
        # （并发回升延迟）；current 的读写同样需要保护
        self._lock = threading.Lock()

    @property
    def max_concurrent(self) -> int:
        return self._max

    @property
    def min_concurrent(self) -> int:
        return self._min

    @property
    def current(self) -> int:
        """当前生效并发上限（调度器读这个值而非固定的 max）。"""
        return self._current

    def on_failure(self, reason: str = "") -> int:
        with self._lock:
            self._current = self._min
            self._successes = 0
            return self._current

    def on_success(self) -> int:
        with self._lock:
            self._successes += 1
            if (self._successes >= self._successes_to_raise
                    and self._current < self._max):
                self._current = min(self._max, self._current + self._step)
                self._successes = 0
            return self._current

    def reset(self) -> None:
        with self._lock:
            self._current = self._max
            self._successes = 0


# ------------------------------------------------------------------ steamcmd 特征
# 实测 steamcmd 匿名下载输出（tests/fixtures/steamcmd_success.txt）：
#   Connecting anonymously to Steam Public...OK
#   Downloading item 3802244270 ...
#   Success. Downloaded item 3802244270 to "..." (1816113 bytes)
# 限流/故障时会出现（社区反馈 + 与 steam_api 429 同源）：
#   RateLimit / RateLimitExceeded / 429 too many requests
#   Timeout / TimeoutException / Connection timed out
#   Retrying...（连接重试，实测在 "Connecting anonymously..." 后出现过）
_RATE_LIMIT_RE = re.compile(
    r"rate[\s_-]?limit|429\s+too\s+many|too\s+many\s+requests|exceeded\s+(?:the\s+)?rate",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"timeout|timed\s+out", re.IGNORECASE)
_RETRY_RE = re.compile(r"\bRetrying\s*\.{2,}", re.IGNORECASE)

# 特征严重度排序：越靠前越严重。rate_limit 优先于 timeout（更明确可操作）。
_SIGNAL_ORDER = ("rate_limit", "timeout", "retry")


def classify_steamcmd_line(line: str) -> Optional[str]:
    """识别 steamcmd 输出行中的限流/超时/重试特征。

    返回 ``"rate_limit"`` / ``"timeout"`` / ``"retry"`` / ``None``。
    rate_limit 与 timeout 是硬信号（触发退避 + 并发降级），
    retry 是软信号（仅小幅退避，steamcmd 自己已在重试）。
    """
    if not line:
        return None
    if _RATE_LIMIT_RE.search(line):
        return "rate_limit"
    if _TIMEOUT_RE.search(line):
        return "timeout"
    if _RETRY_RE.search(line):
        return "retry"
    return None


# ------------------------------------------------------------------ 进度平滑
def _format_eta(seconds: float) -> str:
    s = int(max(0.0, seconds))
    if s < 60:
        return f"{s} 秒"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {s} 秒"
    h, m = divmod(m, 60)
    return f"{h} 时 {m} 分"


def _render_label(percent: int, speed_mbps: float, eta: float, total: int) -> str:
    """把一次进度快照渲染成人类可读的短消息（写入 job.message）。"""
    parts: list[str] = []
    if percent >= 0:
        parts.append(f"{percent}%")
    if speed_mbps > 0:
        parts.append(f"{speed_mbps:.1f} MB/s")
        if eta > 0:
            parts.append(f"剩余 {_format_eta(eta)}")
    if not parts:
        return "下载中…"
    return " · ".join(parts)


class ProgressSmoother:
    """UI 进度平滑器。

    - 限流：同一时刻最多每 ``min_interval`` 秒下发一次（默认 0.1s ≈ 10Hz），
      避免 steamcmd 高频输出刷爆 UI；完成时强制下发。
    - 不倒退：记录历史最大字节数，后到的更小观测被钳制（进度条绝不回退）。
    - 速度：**滚动窗口**——保留最近 ``window`` 秒的 (时间, 字节) 样本，
      速度 = 窗口内字节增量 / 窗口真实经过时间。旧实现用相邻两次观测的
      瞬时增量做 EMA，当上报频率与下发频率不匹配时会两类失真：
      ① dt 内增量为 0 → 长期显示 0 MB/s；② 一次合并 tick 携带多秒增量
      → 突跳到 2-300MB/s 的假速度。滚动窗口用真实经过时间作分母，
      且天然把突发增量摊薄到整个窗口，两种失真同时消失。
      停顿超过窗口后速度平滑衰减到 0（而非卡在旧值）。
    - ETA：剩余字节 / 当前速度。
    """

    # 窗口内最多保留的样本数（防爆内存：10Hz×3s≈30，留充裕上限）
    _MAX_SAMPLES = 64

    def __init__(self, min_interval: float = 0.1, smoothing: float = 0.5,
                 window: float = 3.0) -> None:
        self.min_interval = max(0.0, float(min_interval))
        # smoothing 保留给老调用方（窗口模式不再使用 EMA）
        self.smoothing = max(0.0, min(1.0, float(smoothing)))
        self.window = max(0.5, float(window))
        self._lock = threading.Lock()
        self._last_emit = 0.0
        self._last_bytes = 0
        self._speed = 0.0  # MB/s（最近一次下发的窗口速度）
        self._samples: deque = deque()

    def reset(self, bytes_done: int = 0, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._last_emit = now
            self._last_bytes = max(0, int(bytes_done))
            self._speed = 0.0
            self._samples.clear()
            self._samples.append((now, self._last_bytes))

    def feed(
        self,
        bytes_done: int,
        total: int = 0,
        force: bool = False,
        now: Optional[float] = None,
    ) -> Optional[dict]:
        """喂入一次原始观测。

        返回 ``None`` 表示被限流（调用方应跳过，不要刷新 UI）；
        否则返回展示快照 dict：bytes/total/percent/speed_mbps/eta/label。
        ``force=True`` 用于完成事件，绕过限流。
        """
        now = time.time() if now is None else now
        b = max(0, int(bytes_done or 0))
        with self._lock:
            b = max(b, self._last_bytes)  # 进度不倒退
            self._last_bytes = b
            self._samples.append((now, b))
            # 滚动窗口：丢弃窗口外的旧样本（始终保留最新样本 + 一个窗口内锚点）
            cutoff = now - self.window
            while len(self._samples) > 2 and self._samples[0][0] < cutoff:
                self._samples.popleft()
            while len(self._samples) > self._MAX_SAMPLES:
                self._samples.popleft()

            throttled = (not force) and (now - self._last_emit) < self.min_interval
            if throttled:
                return None
            self._last_emit = now

            total = max(0, int(total or 0))
            percent = int(b / total * 100) if total > 0 else -1
            percent = max(-1, min(100, percent))
            # 窗口速度：窗口首样本到当前的真实增量 / 真实经过时间
            self._speed = 0.0
            if len(self._samples) >= 2:
                t0, b0 = self._samples[0]
                dt = now - t0
                if dt > 1e-6:
                    self._speed = max(0.0, (b - b0) / _MB / dt)
            eta = 0.0
            if 0 < b < total and self._speed > 0:
                eta = (total - b) / _MB / self._speed
            return {
                "bytes": b,
                "total": total,
                "percent": percent,
                "speed_mbps": self._speed,
                "eta": eta,
                "label": _render_label(percent, self._speed, eta, total),
            }
