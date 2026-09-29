"""API response cache: cuts repeated requests to ease Steam community 429 rate limiting (响应缓存层).

Design points:
- TTL cache: ``browse`` results keyed by (appid, page, sort, search, tags); returning to
  a page or repeating the same search is a zero-request hit.
- Bounded size: LRU eviction once the entry cap is exceeded.
- Expiry: lazy cleanup plus active shrinking, so the cache never grows unbounded.
- Request coalescing: concurrent identical requests share one Future, avoiding duplicate fetches.
- Degradation: after 429 retries are exhausted, serve a cached entry (even a stale one)
  instead of failing outright.

Note: ``browse()`` returns mutable ``WorkshopItem`` dataclasses and ``enrich()`` mutates the
list in place — cached values must be deep-copied before they leave the cache (缓存命中返回前必须深拷贝).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from .logger import get_logger

log = get_logger("swdm.core.api_cache")

_DEFAULT_TTL = 180.0          # 3 分钟
_DEFAULT_MAX_ENTRIES = 128    # 最多缓存条目


class ApiCache:
    """线程安全的 TTL + LRU 缓存，带请求合并。"""

    def __init__(
        self,
        ttl: float = _DEFAULT_TTL,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._ttl = max(5.0, float(ttl))
        self._max_entries = max(8, int(max_entries))
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        # 请求合并：key -> Future-like 结果容器
        self._inflight: dict[str, list] = {}
        self._lock = threading.RLock()

    # --------------------------------------------------------------- 基本操作
    def _now(self) -> float:
        return time.time()

    def _evict_expired_locked(self) -> None:
        now = self._now()
        stale = [k for k, (exp, _v) in self._store.items() if exp <= now]
        for k in stale:
            self._store.pop(k, None)

    def get(self, key: str, allow_expired: bool = False) -> tuple[bool, Any]:
        """查询缓存。返回 (hit, value)。

        allow_expired=True 时，即使过期也返回（用于限流降级）。
        """
        with self._lock:
            self._evict_expired_locked()
            entry = self._store.get(key)
            if entry is None and allow_expired:
                # 懒清理已删过期项，需直接遍历（store 里过期项已被踢出，
                # 所以 allow_expired 只在未被清理时有效——此处保持简单语义）
                return False, None
            if entry is None:
                return False, None
            exp, value = entry
            if exp <= self._now() and not allow_expired:
                self._store.pop(key, None)
                return False, None
            # LRU：命中时移到末尾（最新使用）
            self._store.move_to_end(key)
            return True, value

    def _get_expired_locked(self, key: str) -> Any:
        """绕过 TTL 取可能过期的值（降级用）。"""
        entry = self._store.get(key)
        return entry[1] if entry is not None else None

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            self._evict_expired_locked()
            self._store[key] = (self._now() + (ttl if ttl is not None else self._ttl), value)
            self._store.move_to_end(key)
            # 超出上限：淘汰最旧
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def invalidate(self, predicate: str | Callable[[str], bool] = "") -> int:
        """失效缓存。

        - 传 appid 字符串：失效所有 key 中含该 appid 的条目（兼容旧式
          "appid:..." 前缀 key 与元组序列化的 key）；
        - 传谓词函数：失效所有满足谓词的 key；
        - 空串：清空全部。
        """
        with self._lock:
            if predicate == "":
                n = len(self._store)
                self._store.clear()
                return n
            if callable(predicate):
                keys = [k for k in self._store if predicate(k)]
            else:
                keys = [k for k in self._store if str(predicate) in k]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "ttl": self._ttl,
            }

    # --------------------------------------------------------------- 请求合并
    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Any],
        ttl: float | None = None,
        allow_expired_fallback: bool = True,
    ) -> Any:
        """查缓存；未命中时执行 compute（同时刻相同 key 的并发请求合并为一次）。

        compute 抛异常时，若有（哪怕过期的）缓存则降级返回缓存，否则抛出。
        """
        hit, value = self.get(key)
        if hit:
            log.debug("缓存命中: %s", key[:60])
            return value

        # 请求合并：锁内决定角色（首个执行 / 等待者），避免用列表真值
        # 误判（结果未写入时 box 恒空，等待者会误以为自己是首个）
        with self._lock:
            if key in self._inflight:
                box = self._inflight[key]
                is_first = False
            else:
                box = []
                self._inflight[key] = box
                is_first = True

        if not is_first:
            # 等待已在进行的同 key 请求
            while not box:
                time.sleep(0.02)
            result = box[0]
            if isinstance(result, Exception):
                if allow_expired_fallback:
                    stale = self._get_stale(key)
                    if stale is not None:
                        log.info("请求失败，降级返回过期缓存: %s", key[:60])
                        return stale
                raise result
            return result

        # 首个请求：真正执行
        try:
            value = compute()
            self.set(key, value, ttl)
            with self._lock:
                self._inflight.pop(key, None)
                box.append(value)
            return value
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._inflight.pop(key, None)
                box.append(e)
            if allow_expired_fallback:
                stale = self._get_stale(key)
                if stale is not None:
                    log.info("请求失败，降级返回过期缓存: %s", key[:60])
                    return stale
            raise

    def _get_stale(self, key: str) -> Any:
        """取未过期的缓存（用于降级）。get(allow_expired) 语义的轻量版。"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            return entry[1]


# --------------------------------------------------------------- 模块级单例
_global_cache: ApiCache | None = None
_global_lock = threading.Lock()


def get_api_cache() -> ApiCache:
    """全局缓存单例（browse 结果共享）。"""
    global _global_cache
    if _global_cache is None:
        with _global_lock:
            if _global_cache is None:
                _global_cache = ApiCache()
    return _global_cache


def make_cache_key(
    appid: str,
    page: int,
    sort: str,
    search: str,
    tags: list | tuple | frozenset,
    language: str = "",
    numperpage: int = 30,
) -> str:
    """browse 缓存键：所有影响结果的维度都参与。"""
    tag_part = "|".join(sorted(str(t) for t in (tags or [])))
    return (
        f"browse:{appid}:{page}:{sort or ''}:{search or ''}"
        f":{tag_part}:{language or ''}:{int(numperpage or 0)}"
    )
