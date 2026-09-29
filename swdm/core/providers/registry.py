"""Provider registry: chain construction + circuit-breaker cooldown (Provider 注册表).

Design: see research/provider_adaptation.md §3.4. Responsibilities:
- Build the fallback chain in the user's configured channel order (steamcmd is always
  the terminal tail fallback, 链尾兜底)
- Circuit-breaker cooldown: a channel that fails consecutively is skipped while cooling
  down (3 failures → 60s, half-open re-melt on one failure), reusing the t14 _Throttle idea
- Providers requiring a key are skipped when unconfigured; the UI list reflects only the
  configuration state (no network-probing path — that cache was deleted in t28)
"""
from __future__ import annotations

import threading
import time

from ..config import get_config
from ..logger import get_logger
from .base import Availability, DownloadProvider, ProviderKind

log = get_logger("swdm.core.providers.registry")


class _Circuit:
    """单通道熔断器：连续失败 N 次后熔断，冷却期内不可用。"""

    def __init__(self, fail_threshold: int = 3, cooldown: float = 60.0) -> None:
        self._fail = 0
        self._tripped = False
        self._open_at = 0.0
        self._fail_threshold = fail_threshold
        self._cooldown = cooldown
        self._lock = threading.Lock()

    def is_tripped(self) -> bool:
        with self._lock:
            if not self._tripped:
                return False
            if time.time() - self._open_at >= self._cooldown:
                # 半开：给一次机会。_fail 保留在阈值-1，
                # 这样一次失败立即重新熔断（标准半开语义）
                self._tripped = False
                self._fail = max(0, self._fail_threshold - 1)
                return False
            return True

    def record_failure(self) -> None:
        with self._lock:
            self._fail += 1
            if self._fail >= self._fail_threshold and not self._tripped:
                self._tripped = True
                self._open_at = time.time()
                log.warning("通道熔断：连续失败 %d 次，冷却 %.0fs", self._fail, self._cooldown)

    def record_success(self) -> None:
        with self._lock:
            self._fail = 0
            self._tripped = False


class ProviderRegistry:
    """provider 注册 + 回退链构造（单例，进程内共享）。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._classes: dict[str, type[DownloadProvider]] = {}
        self._instances: dict[str, DownloadProvider] = {}
        self._circuits: dict[str, _Circuit] = {}
        self._instance_lock = threading.RLock()

    # ---------------- 注册（启动期）
    def register(self, provider_cls: type[DownloadProvider]) -> None:
        meta = provider_cls.meta
        with self._instance_lock:
            self._classes[meta.name] = provider_cls
            self._circuits.setdefault(meta.name, _Circuit())
            log.debug("注册 provider: %s (%s)", meta.name, meta.display_name)

    # ---------------- 单例获取
    def get_provider(self, name: str, api=None) -> DownloadProvider | None:
        """按名取实例（懒构造，config 读实时值）。"""
        with self._instance_lock:
            if name not in self._classes:
                return None
            cfg = self._provider_config(name)
            # config 变了就重建实例（config 节是不可变快照，比较引用即可）
            key = (id(cfg),)
            inst = self._instances.get(name)
            if inst is None or getattr(inst, "_cfg_key", None) != key:
                inst = self._classes[name](cfg, api=api)
                inst._cfg_key = key  # type: ignore[attr-defined]
                self._instances[name] = inst
            # api 可能晚注入（services 重建后）
            if inst.api is not api:
                inst.api = api
            return inst

    def _provider_config(self, name: str) -> dict:
        """读 config.providers.<name> 节，不存在则空 dict。"""
        try:
            return get_config().get("download", "providers", name, default={}) or {}
        except Exception:  # noqa: BLE001
            return {}

    # ---------------- 熔断反馈
    def record_failure(self, name: str) -> None:
        c = self._circuits.get(name)
        if c is not None:
            c.record_failure()

    def record_success(self, name: str) -> None:
        c = self._circuits.get(name)
        if c is not None:
            c.record_success()

    # ---------------- 链构造
    def build_chain(self, preferred: str = "", api=None) -> list[DownloadProvider]:
        """构造回退链。顺序：用户首选 → 其余启用的通道（按 priority）→ steamcmd 兜底。

        - 用户在 config 里明确禁用的通道（enabled=False）排除
        - 熔断中的通道跳过（冷却期过后会重新加入）
        - 需 key 但未配置的通道跳过（不报错）
        - 链尾永远是 steamcmd（除非 steamcmd 本身就是首选，则不重复）
        """
        chain: list[DownloadProvider] = []
        seen: set[str] = set()

        def _try_add(name: str) -> bool:
            """加入通道；返回 True 表示它是 terminal，应停止追加。"""
            if name in seen or name not in self._classes:
                return False
            seen.add(name)
            inst = self.get_provider(name, api)
            if inst is None:
                return False
            if not self._is_enabled(name):
                return False
            if not inst.is_configured():
                log.info("通道 %s 未配置凭据，跳过（匿名降级）", name)
                return False
            if self._circuits.get(name) and self._circuits[name].is_tripped():
                log.info("通道 %s 熔断中，跳过", name)
                return False
            chain.append(inst)
            return inst.meta.terminal

        if preferred and _try_add(preferred):
            return chain
        # 其余通道按 priority 排序
        others = sorted(
            (n for n in self._classes if n not in seen),
            key=lambda n: self._classes[n].meta.priority,
        )
        for n in others:
            if _try_add(n):
                break
        # steamcmd 永远兜底
        if "steamcmd" in self._classes and "steamcmd" not in seen:
            _try_add("steamcmd")
        return chain

    def _is_enabled(self, name: str) -> bool:
        """用户在 config.providers.<name>.enabled 里可关掉某通道。"""
        try:
            cfg = self._provider_config(name)
            return bool(cfg.get("enabled", True))
        except Exception:  # noqa: BLE001
            return True

    # ---------------- 可用通道清单（UI 下拉用）
    def list_channels(self, api=None) -> list[tuple[str, str, Availability]]:
        """[(name, display_name, availability)] 按 priority 排序。

        只反映"是否被用户禁用"（配置态，无网络请求）。
        """
        out = []
        for name, cls in sorted(self._classes.items(),
                                key=lambda kv: kv[1].meta.priority):
            avail = Availability.DISABLED if not self._is_enabled(name) \
                else Availability.OK
            out.append((name, cls.meta.display_name, avail))
        return out


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Process-wide singleton registry with built-in channels registered."""
    global _registry
    if _registry is None:
        with threading.Lock():
            if _registry is None:
                _registry = ProviderRegistry()
                _register_builtin(_registry)
    return _registry


def _register_builtin(reg: ProviderRegistry) -> None:
    """注册内置通道。导入失败不致命（依赖缺失时降级为不可用）。"""
    from .steamcmd import SteamCMDProvider

    reg.register(SteamCMDProvider)
    try:
        from .cdn import CDNProvider

        reg.register(CDNProvider)
    except Exception:  # noqa: BLE001
        log.warning("CDN provider 注册失败", exc_info=True)
    try:
        from .ggnetwork import GGNetworkProvider

        reg.register(GGNetworkProvider)
    except Exception:  # noqa: BLE001
        log.warning("GGNetwork provider 注册失败", exc_info=True)
