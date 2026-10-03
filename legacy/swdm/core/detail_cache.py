"""Detail page disk cache: persistent HTML cache with TTL + time_updated double invalidation (详情页磁盘缓存).

Design points:
- ``DetailDiskCache`` stores the rendered detail-page HTML per item id under the
  data dir ``cache/detail/``. A cache hit avoids a ``/sharedfiles/filedetails/``
  round trip entirely, so returning to a previously viewed mod (回退) reloads
  instantly and costs zero requests.
- Double invalidation (用户硬约束 "缓存及时清除"):
  1. TTL: entries older than the configured TTL (default 24h) are discarded.
  2. time_updated: entries whose recorded ``time_updated`` differs from the
     caller's fresh value are dropped immediately, so a mod that was updated on
     Steam is never shown from stale cache (过期 mod 比无缓存更糟).
- Corruption tolerant: any read/parse failure is treated as a miss (杀软扫描、
  用户手改、断电写半都可能损坏文件); the bad file is removed so the next write
  can repair it. Nothing here may raise into the UI thread.
- Deep-copy discipline: the cached HTML string is deep-copied on return so a
  caller cannot mutate the cached payload in place (与 api_cache 的深拷贝纪律一致).
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time

from .logger import get_logger
from .paths import CACHE_DIR

log = get_logger("swdm.core.detail_cache")

_DEFAULT_TTL_HOURS = 24.0
_DIR_NAME = "detail"


class DetailDiskCache:
    """线程安全的详情页 HTML 磁盘缓存（TTL + time_updated 双失效）。"""

    def __init__(self, root_dir: str | None = None, ttl_hours: float | None = None) -> None:
        self._dir = os.path.join(root_dir or CACHE_DIR, _DIR_NAME)
        # ttl_hours=None → 从配置读取（延迟到首次使用，测试可直接注入）
        self._ttl_hours = ttl_hours
        self._lock = threading.Lock()

    # --------------------------------------------------------------- 配置
    def _resolved_ttl_hours(self) -> float:
        if self._ttl_hours is not None:
            return max(0.0, float(self._ttl_hours))
        try:
            from .config import get_config

            hours = get_config().get("network", "detail_cache_ttl_hours",
                                     default=_DEFAULT_TTL_HOURS)
            return max(0.0, float(hours or 0.0))
        except Exception:  # noqa: BLE001
            return _DEFAULT_TTL_HOURS

    def _enabled(self) -> bool:
        if self._ttl_hours is not None:
            return self._ttl_hours > 0
        try:
            from .config import get_config

            return bool(get_config().get("network", "detail_cache_enabled",
                                         default=True))
        except Exception:  # noqa: BLE001
            return True

    # --------------------------------------------------------------- 路径
    def _path(self, item_id: str) -> str:
        # item_id 来自 Steam，是纯数字；防御性过滤路径穿越
        safe = "".join(c for c in str(item_id) if c.isalnum() or c in "-_")
        return os.path.join(self._dir, f"{safe}.json")

    def _ensure_dir(self) -> None:
        os.makedirs(self._dir, exist_ok=True)

    # --------------------------------------------------------------- 读写
    def get(self, item_id: str, time_updated: int = 0) -> tuple[bool, str]:
        """读取详情页 HTML。返回 (hit, html)。

        - time_updated>0 时参与双失效比对：与缓存记录值不一致立即判 miss
          并删除该条目（"及时清除"硬约束）。
        - 任何损坏（文件缺失/JSON 非法/结构缺字段）当 miss 并清理。
        - 命中返回深拷贝，调用方修改不污染缓存。
        """
        if not self._enabled():
            return False, ""
        path = self._path(item_id)
        try:
            with self._lock:
                if not os.path.exists(path):
                    return False, ""
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                html = data.get("html")
                cached_at = float(data.get("cached_at", 0) or 0)
                stored_tu = int(data.get("time_updated", 0) or 0)
                if not html or not cached_at:
                    raise ValueError("incomplete cache entry")
        except Exception as e:  # noqa: BLE001
            # 损坏容忍：当 miss，并尝试清理脏文件
            log.debug("详情缓存读取失败(当 miss): %s %s", item_id, e)
            self._try_remove(path)
            return False, ""
        # TTL 失效
        ttl_sec = self._resolved_ttl_hours() * 3600.0
        if ttl_sec <= 0 or (time.time() - cached_at) >= ttl_sec:
            self._try_remove(path)
            return False, ""
        # time_updated 失效（调用方提供新值且与缓存不一致 → 立即丢弃）
        if time_updated and stored_tu and int(time_updated) != stored_tu:
            log.info("详情缓存因 time_updated 变化失效: %s", item_id)
            self._try_remove(path)
            return False, ""
        return True, copy.deepcopy(html)

    def set(self, item_id: str, html: str, time_updated: int = 0) -> None:
        """写入详情页 HTML（原子写）。空 html 不写。"""
        if not self._enabled() or not html:
            return
        path = self._path(item_id)
        payload = {
            "html": html,
            "time_updated": int(time_updated or 0),
            "cached_at": time.time(),
        }
        try:
            with self._lock:
                self._ensure_dir()
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp, path)  # 原子替换：防写半损坏
        except Exception as e:  # noqa: BLE001
            # 磁盘满/只读/杀软锁定：缓存写入失败不得影响主流程
            log.debug("详情缓存写入失败(忽略): %s %s", item_id, e)

    def invalidate(self, item_id: str | None = None) -> int:
        """失效缓存。传 item_id 删单条；不传删全部。返回删除条数。"""
        n = 0
        with self._lock:
            if item_id is not None:
                n += self._try_remove(self._path(item_id))
                return n
            if not os.path.isdir(self._dir):
                return 0
            for name in os.listdir(self._dir):
                if name.endswith(".json"):
                    n += self._try_remove(os.path.join(self._dir, name))
        return n

    def _try_remove(self, path: str) -> int:
        try:
            if os.path.exists(path):
                os.remove(path)
                return 1
        except OSError as e:  # noqa: BLE001
            log.debug("删除缓存文件失败(忽略): %s %s", path, e)
        return 0


# --------------------------------------------------------------- 模块级单例
_global: DetailDiskCache | None = None
_global_lock = threading.Lock()


def get_detail_cache() -> DetailDiskCache:
    """全局详情页磁盘缓存单例。"""
    global _global
    if _global is None:
        with _global_lock:
            if _global is None:
                _global = DetailDiskCache()
    return _global
