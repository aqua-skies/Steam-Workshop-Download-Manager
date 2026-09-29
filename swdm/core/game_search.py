"""游戏名搜索（免 AppID）：接入 steampowered storesearch 接口。

实测结论（research/steam_game_search.md）：
- store.steampowered.com/api/storesearch/?term=&l=schinese&cc=CN 匿名可用，
  相关性最好（gmod→Garry's Mod 4000、csgo→CS2 730、l4d2→L4D2 550），
  返回 {total, items:[{type,name,id,tiny_image,...}]}，id 即 AppID。
- 结果混有 DLC/视频，需 type=="app" 过滤。
- 12 连发触发连接熔断（WinSock 10053，非 429），静置 15s 恢复
  → 联想必须防抖 + 在途取消 + 缓存。
- 中文名不可靠（仅当商店名本身是中文时有效），以英文搜索为主。
- 封面图优先用返回的 tiny_image 完整 URL（shared.akamai.steamstatic.com）。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests

from .logger import get_logger

log = get_logger("swdm.game_search")

_STORESEARCH = "https://store.steampowered.com/api/storesearch/"
_TIMEOUT = 8.0


@dataclass
class GameSearchResult:
    appid: str
    name: str
    image_url: str = ""


class GameSearchClient:
    """游戏名搜索客户端：带内存缓存 + 速率自护。"""

    def __init__(self, proxy: str = "") -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self._session.headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
        self._cache: dict[str, tuple[float, list[GameSearchResult]]] = {}
        self._lock = threading.Lock()
        self._last_request = 0.0
        # 非官方 Storefront API 限流比官方更狠（研究结论）；
        # D：t16 讨论组取保守中间值 0.7s（不直接 350ms：
        # storesearch 匿名接口无速率保障、本机出口 IP 已被限过）
        self._min_interval = 0.7
        # D：熔断退避——连续失败/连接熔断（10053）后冷却期内跳过请求
        self._fail_streak = 0
        self._cooldown_until = 0.0

    def _in_cooldown(self) -> bool:
        return time.time() < self._cooldown_until

    def _record_failure(self, e: BaseException) -> None:
        """连接级失败（如 WinSock 10053 熔断）或连续 3 次失败 → 冷却 15s。"""
        self._fail_streak += 1
        if isinstance(e, requests.ConnectionError) or self._fail_streak >= 3:
            self._cooldown_until = time.time() + 15.0
            log.warning("游戏搜索熔断，冷却 15s：%s", e)

    def search(self, term: str, limit: int = 12) -> list[GameSearchResult]:
        """搜索游戏名，返回 AppID 候选列表。走缓存，失败返回空列表。"""
        term = (term or "").strip()
        if len(term) < 2:
            return []
        key = term.lower()
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < 300.0:
                return list(hit[1])
        # D：熔断冷却期内直接跳过（连接熔断需静置恢复）
        if self._in_cooldown():
            return []
        # 最低请求间隔保护（避免联想打字时连发触发连接熔断）
        gap = self._last_request + self._min_interval - now
        if gap > 0:
            time.sleep(gap)
        try:
            self._last_request = time.time()
            r = self._session.get(
                _STORESEARCH,
                params={"term": term, "l": "schinese", "cc": "CN"},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            self._record_failure(e)
            log.debug("游戏搜索失败（term=%s）: %s", term, e)
            return []
        out: list[GameSearchResult] = []
        for it in data.get("items", []):
            if it.get("type") != "app":     # 过滤 DLC/视频
                continue
            name = str(it.get("name", ""))
            # bug15：DLC 有时也标 type=app，按名称启发式排除明显 DLC
            low = name.lower()
            if any(kw in low for kw in ("dlc", "add-on", "addon", "扩展包", "季票", "season pass")):
                continue
            out.append(GameSearchResult(
                appid=str(it.get("id", "")),
                name=name,
                image_url=str(it.get("tiny_image", "")),
            ))
            if len(out) >= limit:
                break
        with self._lock:
            self._fail_streak = 0
            self._cache[key] = (time.time(), list(out))
        return out

    def cached(self, term: str) -> list[GameSearchResult] | None:
        """仅查缓存（联想框即时填充本地结果用）。"""
        key = (term or "").strip().lower()
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < 300.0:
                return list(hit[1])
        return None
