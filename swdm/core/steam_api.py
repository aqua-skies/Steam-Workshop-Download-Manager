"""Steam Web API + 社区页面客户端。

设计要点（均经实测，见 research/workshop_api_research.md）：
- GetPublishedFileDetails / GetCollectionDetails 无需 API key
- QueryFiles 需 key（用户可选），作为增强路径
- HTTPS 强制使用系统证书存储（truststore），否则本机 SSL 失败
- 全局浏览器 UA，否则社区页面返回错误
- 浏览页 React 重构后类名混淆，用稳健正则提取 id/标题/预览图
- 429 限流：全局节流 + 指数退避重试（社区页按 IP 限流，实测易触发）
"""
from __future__ import annotations

import copy
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .logger import get_logger
from .paths import CACHE_DIR, ensure_dirs

log = get_logger("swdm.api")


def _detect_system_proxy() -> str:
    """检测系统代理：环境变量优先，其次 Windows 注册表（系统代理设置）。

    用于 Clash/V2Ray 开启"系统代理"后程序自动走代理，无需手动填配置。
    返回形如 http://127.0.0.1:7897 的代理 URL；检测不到返回空串。
    """
    import os as _os

    # 1) 环境变量（requests 原生支持，这里仅为显式化）
    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        val = (_os.environ.get(var) or "").strip()
        if val:
            return val
    # 2) Windows 注册表：IE/系统代理设置
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            if not enabled:
                return ""
            server = str(winreg.QueryValueEx(key, "ProxyServer")[0]).strip()
        if not server:
            return ""
        # ProxyServer 可能是 "127.0.0.1:7897" 或 "http=...;https=..." 形式
        if "=" in server:
            for part in server.split(";"):
                if part.startswith(("https=", "http=")):
                    val = part.split("=", 1)[1].strip()
                    if val:
                        server = val
                        break
        if "://" not in server:
            server = f"http://{server}"
        return server
    except Exception:  # noqa: BLE001
        return ""


class RateLimitError(Exception):
    """Steam 速率限制（429）或 IP/边缘层封禁（403）。携带建议等待秒数。"""

    def __init__(self, retry_after: float = 30.0, status: int = 429) -> None:
        self.retry_after = retry_after
        self.status = status
        kind = "IP/代理层封禁（403）" if status == 403 else "速率限制（429）"
        super().__init__(f"Steam {kind}，建议等待 {retry_after:.0f} 秒后重试")


class _Throttle:
    """全局请求节流器：社区页面请求按 IP 限流，串行化并保证最小间隔。

    O5（net N2）：熔断机制——触发 429 后进入熔断期（实测冷却窗 >24s，
    取 30s），期间新请求快速失败走缓存兜底，而不是全部 sleep 排队
    造成界面假死。熔断窗口过后自动放行。
    """

    def __init__(self, min_interval: float = 2.0) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self._circuit_until = 0.0        # 熔断到期时间戳

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            if now < self._circuit_until:
                # 熔断期：不等最小间隔，直接放行让上层快速失败
                # （上层用过期缓存兜底）；真实请求仍会被服务器挡
                self._last = now
                return
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    @property
    def in_circuit(self) -> bool:
        with self._lock:
            return time.time() < self._circuit_until

    def trip(self, seconds: float) -> None:
        """触发熔断：记录到期时间，延长最小间隔（上限 60s）。"""
        with self._lock:
            self._circuit_until = time.time() + max(10.0, min(float(seconds), 60.0))
            self._min_interval = max(self._min_interval, min(float(seconds), 60.0))

    def bump(self, seconds: float) -> None:
        """触发限流后延长最小间隔（按配额恢复需要，上限 60s）。"""
        with self._lock:
            self._min_interval = max(self._min_interval, min(float(seconds), 60.0))

    def decay(self) -> None:
        """请求成功后逐步回落节流间隔（每次 -2s，下限 2s）。"""
        with self._lock:
            self._min_interval = max(2.0, self._min_interval - 2.0)


_throttle = _Throttle(min_interval=2.0)

# truststore 只注入一次：让 requests 使用操作系统证书存储
try:
    import truststore

    truststore.inject_into_ssl()
    log.debug("truststore 已注入，requests 使用系统证书存储")
except Exception as e:  # noqa: BLE001
    log.warning("truststore 注入失败，回退默认证书: %s", e)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_BASE = "https://api.steampowered.com"
_COMMUNITY = "https://steamcommunity.com"
_IMG_CACHE_DAYS = 30

# QueryFiles query_type 枚举
QUERY_TYPE = {
    "ranked_by_trend": 0,
    "ranked_by_vote": 1,
    "ranked_by_public": 2,
    "most_recent": 3,
    "most_subscribed": 9,
    "most_viewed": 12,
}


@dataclass
class WorkshopItem:
    """工坊物品（列表/详情通用结构）。"""

    publishedfileid: str
    title: str = ""
    description: str = ""
    creator: str = ""               # steamid64
    creator_name: str = ""
    appid: str = ""
    file_size: int = 0
    subscriptions: int = 0          # 热度
    lifetime_subscriptions: int = 0
    favorited: int = 0
    views: int = 0
    preview_url: str = ""
    file_url: str = ""               # CDN 直链（匿名通常为空，登录态才有）
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)   # 前置依赖 mod id
    time_created: int = 0
    time_updated: int = 0
    result: int = 0
    # 本地状态（由库填充）
    installed: bool = False
    local_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "publishedfileid": self.publishedfileid,
            "title": self.title,
            "description": self.description,
            "creator": self.creator,
            "creator_name": self.creator_name,
            "appid": self.appid,
            "file_size": self.file_size,
            "subscriptions": self.subscriptions,
            "lifetime_subscriptions": self.lifetime_subscriptions,
            "favorited": self.favorited,
            "views": self.views,
            "preview_url": self.preview_url,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "time_created": self.time_created,
            "time_updated": self.time_updated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkshopItem":
        return cls(
            publishedfileid=str(d.get("publishedfileid", "")),
            title=d.get("title", ""),
            description=d.get("description", ""),
            creator=str(d.get("creator", "")),
            creator_name=d.get("creator_name", ""),
            appid=str(d.get("appid", "") or d.get("creator_app_id", "") or d.get("consumer_app_id", "")),
            file_size=int(d.get("file_size", 0) or 0),
            subscriptions=int(d.get("subscriptions", 0) or 0),
            lifetime_subscriptions=int(d.get("lifetime_subscriptions", 0) or 0),
            favorited=int(d.get("favorited", 0) or 0),
            views=int(d.get("views", 0) or 0),
            preview_url=d.get("preview_url", ""),
            file_url=d.get("file_url", ""),
            tags=[t.get("tag", "") for t in d.get("tags", []) if t.get("tag")],
            dependencies=[str(x) for x in (d.get("dependencies") or []) if x],
            time_created=int(d.get("time_created", 0) or 0),
            time_updated=int(d.get("time_updated", 0) or 0),
            result=int(d.get("result", 0) or 0),
        )


class SteamAPI:
    """Steam Web API 与社区页面客户端。"""

    def __init__(self, api_key: str = "", proxy: str = "", timeout: int = 30) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self._dep_titles: dict[str, str] = {}
        self._dep_cache: dict[str, tuple[float, list[str]]] = {}
        # 端点节流状态为实例级：多线程并发调用 _endpoint_throttle 时，
        # read-sleep-write 必须串行，否则并发线程各自读到同一个 last
        # 并一起 sleep，实际请求间隔小于设定值（削弱 429 防护）
        self._endpoint_last: dict[str, float] = {}
        self._endpoint_lock = threading.Lock()
        # 高优先级（用户点击）请求计数：预取请求据此礼让槽位
        self._priority_pending = 0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = _UA
        # 实测（本机单 IP，item 3803871160）：steamcommunity 429 由请求头
        # 指纹触发，非纯 IP 限流。Chrome UA 缺 Accept-Language 是典型自动化
        # 指纹，被 Steam 自家 nginx 命中；补该头后 429→200（3/3）。
        # 注：X-Requested-With 旧结论称可豁免 429，复核实测已被推翻（现为
        # 429），故只保留 Accept-Language 为唯一必需头。
        self._session.headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        if not proxy:
            # 未显式配置代理时，自动跟随 Windows 系统代理（Clash/V2Ray
            # 开启"系统代理"后程序无需手动填即可走代理）
            proxy = _detect_system_proxy()
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------ 代理
    @staticmethod
    def detect_system_proxy() -> str:
        """检测系统代理：环境变量优先，其次 Windows 注册表（IE/系统代理设置）。"""
        return _detect_system_proxy()

    # ------------------------------------------------------------------ 基础
    def set_api_key(self, key: str) -> None:
        self.api_key = (key or "").strip()

    def _api_post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{_BASE}{path}"
        try:
            r = self._session.post(url, data=data, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.error("API POST 失败 %s: %s", path, e)
            return {}

    def _api_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{_BASE}{path}"
        if self.api_key:
            params = {**params, "key": self.api_key}
        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.error("API GET 失败 %s: %s", path, e)
            return {}

    # ------------------------------------------- 端点差异化节流
    # 实测：详情页 /sharedfiles/filedetails/ 的 IP 级 429 限流远重于
    # 浏览页 /workshop/browse/。按端点前缀设不同最小间隔，减少撞限流。
    _ENDPOINT_INTERVALS: dict[str, float] = {
        # 详情页：429 已由请求头指纹修复（Accept-Language/X-Requested-With），
        # 实测稳定 200，间隔从 6s 放宽到 3s 提升连续打开详情的响应
        "/sharedfiles/": 3.0,
        "/workshop/browse/": 2.0,    # 浏览页：相对宽松
    }
    _endpoint_last: dict[str, float] = {}

    def _endpoint_throttle(self, path: str, priority: bool = False) -> bool:
        """按端点前缀等待额外间隔（在全局节流之上叠加）。

        锁覆盖 read-sleep-write 全程：同一端点的并发请求串行等待，
        保证最小间隔不被并发读绕过。

        priority=True（用户点击详情）直接绕过等待——节流只约束预取等
        投机请求，永远不挡用户操作；低优先级请求在分片睡眠期间若发现
        高优先级请求排队，则立即让出槽位（返回 False，调用方静默放弃）。
        """
        for prefix, interval in self._ENDPOINT_INTERVALS.items():
            if path.startswith(prefix):
                with self._endpoint_lock:
                    last = self._endpoint_last.get(prefix)
                    now = time.time()
                    if last is not None and not priority:
                        wait = interval - (now - last)
                        if wait > 0:
                            # 分片睡眠：期间可被高优先级请求打断
                            deadline = now + wait
                            while True:
                                remain = deadline - time.time()
                                if remain <= 0:
                                    break
                                if self._priority_pending > 0:
                                    log.debug(
                                        "端点节流礼让：预取请求为用户点击"
                                        "让出槽位 (%s)", prefix,
                                    )
                                    return False
                                time.sleep(min(remain, 0.25))
                    self._endpoint_last[prefix] = time.time()
                return True
        return True

    def _community_get(self, path: str, params: dict[str, Any], max_retries: int = 2, priority: bool = False) -> str:
        """社区页面 GET：全局节流 + 端点差异化节流 + 429/403 差异化退避。

        priority=True 时端点节流直接放行（用户点击优先于悬停预取）；
        低优先级请求被礼让时返回空串，由调用方静默处理。

        实测结论（研究报告 steam_429_403_research.md，34 次本机实测）：
        - 429 = 请求头指纹层（缺 Accept-Language），可控；窗口 >24s，退避 30s 起。
        - 403 = IP/边缘层（代理节点被封），不可控，重试无用 → 快速失败，
          由上层（browse/get_dependencies）用过期缓存兜底。
        """
        url = f"{_COMMUNITY}{path}"
        attempt = 0
        while True:
            attempt += 1
            if priority:
                with self._endpoint_lock:
                    self._priority_pending += 1
            try:
                _throttle.acquire()
                if not self._endpoint_throttle(path, priority=priority):
                    # 被高优先级请求礼让：静默放弃（预取失败无副作用）
                    return ""
            finally:
                if priority:
                    with self._endpoint_lock:
                        self._priority_pending = max(0, self._priority_pending - 1)
            try:
                r = self._session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 403:
                    # IP/边缘层封禁：重试无用，记录响应特征后快速失败。
                    # 判别：403 若来自 Steam 自家 nginx 则体 ~340KB 且带 Server 头；
                    # 来自代理/边缘则无这些特征（报告 §6）。
                    log.warning(
                        "社区页 403（可能为 IP/代理层封禁，重试无用）: %s "
                        "body=%dB server=%s",
                        url, len(r.content or b""), r.headers.get("Server", ""),
                    )
                    raise RateLimitError(60.0, status=403)
                if r.status_code == 429:
                    # 指纹层限流：实测从不带 Retry-After（10/10），冷却窗口 >24s。
                    # 基准退避 30s 起，渐进到 90s 封顶。
                    wait = 30.0
                    try:
                        ra = int(r.headers.get("Retry-After", "30"))
                        wait = max(10.0, min(float(ra), 120.0))
                    except (TypeError, ValueError):
                        pass
                    if attempt <= max_retries:
                        backoff = min(wait * attempt, 90.0)
                        log.warning(
                            "触发 Steam 限流（429），第 %d 次重试，等待 %.0f 秒…",
                            attempt, backoff,
                        )
                        _throttle.trip(backoff)
                        time.sleep(backoff)
                        continue
                    _throttle.trip(wait)
                    raise RateLimitError(wait)
                r.raise_for_status()
                # 请求成功：节流间隔缓慢回落（避免长期高延迟）
                _throttle.decay()
                return r.text
            except requests.RequestException as e:
                if attempt <= max_retries:
                    # 网络错误（代理断连、SSL EOF 等）短退避重试
                    log.warning("社区页请求失败（第 %d 次）: %s", attempt, e)
                    time.sleep(min(3.0 * attempt, 15.0))
                    continue
                raise

    # ------------------------------------------------------- 元数据（无需 key）
    def get_file_details(self, item_ids: list[str]) -> dict[str, WorkshopItem]:
        """批量获取工坊物品详情。返回 {id: WorkshopItem}。"""
        item_ids = [str(i) for i in item_ids if i]
        if not item_ids:
            return {}
        data: dict[str, Any] = {"itemcount": len(item_ids)}
        for i, pid in enumerate(item_ids):
            data[f"publishedfileids[{i}]"] = pid
        resp = self._api_post(
            "/ISteamRemoteStorage/GetPublishedFileDetails/v1/", data
        )
        out: dict[str, WorkshopItem] = {}
        for pf in resp.get("response", {}).get("publishedfiledetails", []):
            item = WorkshopItem.from_dict(pf)
            if item.result == 1:          # 1 = 有效；9 = 不存在
                out[item.publishedfileid] = item
            else:
                log.debug("物品 %s result=%s（不存在或不可用）", pf.get("publishedfileid"), item.result)
        return out

    def get_collection_details(self, collection_id: str) -> list[str]:
        """获取合集内的全部物品 id。"""
        resp = self._api_post(
            "/ISteamRemoteStorage/GetCollectionDetails/v1/",
            {"collectioncount": 1, "publishedfileids[0]": str(collection_id)},
        )
        details = resp.get("response", {}).get("collections", [])
        if not details:
            return []
        return [str(c.get("publishedfileid")) for c in details[0].get("children", []) if c.get("publishedfileid")]

    # ------------------------------------------------------- 前置依赖（网页抓取）
    def get_dependencies(self, item_id: str) -> list[str]:
        """获取物品的前置依赖 mod id 列表（需求：依赖 mod 下载配置）。

        Steam Web API 的 referenced_files 对匿名访问恒为空（实测 94+ 物品采样），
        依赖关系只能从工坊详情页的 "Required items" 区块抓取。
        结果带 TTL 缓存，避免同一物品被重复抓取（限流敏感）。
        """
        from .deps_parser import parse_required_items_with_titles

        item_id = str(item_id)
        # 缓存命中检查（30 分钟 TTL）
        cached = self._dep_cache.get(item_id)
        if cached and time.time() - cached[0] < 1800:
            return list(cached[1])

        try:
            html = self._community_get(
                "/sharedfiles/filedetails/", {"id": item_id},
                priority=True,  # 用户发起的依赖下载同样优先于预取
            )
        except RateLimitError:
            # 限流/IP 封禁时降级返回过期缓存（哪怕过期），
            # 避免依赖下载因 429/403 完全卡死（研究 P0，bug16）
            if cached:
                log.info(
                    "物品 %s 依赖请求被限流，降级使用过期缓存", item_id
                )
                return list(cached[1])
            return []
        items = parse_required_items_with_titles(html)
        # 缓存标题，供 resolve_dependency_tree 复用
        for pid, title in items:
            self._dep_titles[pid] = title
        deps = [pid for pid, _ in items]
        self._dep_cache[item_id] = (time.time(), deps)
        if deps:
            log.info("物品 %s 有 %d 个前置依赖", item_id, len(deps))
        return deps

    def resolve_dependency_tree(
        self,
        item: "WorkshopItem",
        max_depth: int = 10,
        skip_installed: bool = False,
        library: Any = None,
    ) -> tuple[list["WorkshopItem"], list[str]]:
        """递归解析整棵前置依赖树（需求：依赖 mod 下载配置）。

        返回 (待下载依赖列表[依赖在前, 本物在后], 跳过的已安装 id 列表)。
        BFS 遍历，visited 集合防循环引用；深度截断防无限递归。
        每层用 get_file_details 批量补全依赖物品的元数据。
        """
        from collections import deque

        max_depth = max(1, int(max_depth or 10))
        ordered: list[WorkshopItem] = []
        skipped_installed: list[str] = []
        visited: set[str] = {item.publishedfileid}
        # (待解析物品, 当前深度)
        queue: deque[tuple[WorkshopItem, int]] = deque([(item, 0)])

        while queue:
            cur, depth = queue.popleft()
            if depth > max_depth:
                log.warning("依赖树深度超过 %d，已截断于 %s", max_depth, cur.publishedfileid)
                continue
            try:
                dep_ids = self.get_dependencies(cur.publishedfileid)
            except RateLimitError:
                log.warning("解析依赖时触发限流，跳过 %s 的依赖", cur.publishedfileid)
                dep_ids = []
            if not dep_ids:
                continue
            # 批量取元数据（API 不限流）
            details = self.get_file_details(dep_ids)
            child_depth = depth + 1
            for did in dep_ids:
                if did in visited:
                    continue
                # 深度截断：max_depth=1 只解析直接依赖
                if child_depth > max_depth:
                    log.debug("依赖深度超过 %d，截断 %s", max_depth, did)
                    continue
                visited.add(did)
                dep_item = details.get(did) or WorkshopItem(
                    publishedfileid=did, appid=cur.appid
                )
                # 网页抓取的标题优先（API 可能拿不到）
                if not dep_item.title:
                    dep_item.title = getattr(self, "_dep_titles", {}).get(did, "")
                dep_item.appid = dep_item.appid or cur.appid
                if skip_installed and library is not None:
                    rec = library.get(did)
                    if rec and rec.installed:
                        skipped_installed.append(did)
                        continue
                ordered.append(dep_item)
                queue.append((dep_item, child_depth))

        if ordered:
            log.info("依赖树解析完成：%s 依赖 %d 个物品", item.publishedfileid, len(ordered))
        return ordered, skipped_installed

    # ------------------------------------------------- QueryFiles（需要 key）
    def query_files(
        self,
        appid: str,
        query_type: str | int = "ranked_by_trend",
        page: int = 1,
        numperpage: int = 30,
        search_text: str = "",
        tags: list[str] | None = None,
        days: int = -1,
    ) -> tuple[list[WorkshopItem], int]:
        """结构化查询（需 API key）。返回 (物品列表, 总数)。"""
        if not self.api_key:
            return [], 0
        qt = QUERY_TYPE.get(str(query_type), 0) if isinstance(query_type, str) else query_type
        params: dict[str, Any] = {
            "appid": appid,
            "query_type": qt,
            "page": page,
            "numperpage": min(numperpage, 100),
            "return_vote_data": "false",
            "return_tags": "true",
            "return_kv_tags": "false",
            "return_previews": "false",
            "return_children": "false",
            "return_short_description": "true",
            "days": days,
        }
        if search_text:
            params["search_text"] = search_text
        if tags:
            for i, t in enumerate(tags):
                params[f"tagids[{i}]"] = t
        resp = self._api_get("/IPublishedFileService/QueryFiles/v1/", params)
        resp = resp.get("response", {})
        items = [WorkshopItem.from_dict(pf) for pf in resp.get("publishedfiledetails", [])]
        return items, int(resp.get("total", 0))

    # ------------------------------------------------------------ 浏览页抓取
    _CARD_RE = re.compile(
        r'<a href="https://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)"[^>]*>\s*'
        r'<img src="([^"]+)" alt="([^"]*)"'
    )
    # 卡片作者链接：/id/<自定义昵称>/ 或 /profiles/<steamid64>/（修 bug4：
    # GetPublishedFileDetails 不返回 creator_name，仅返回 steamid64，导致
    # 列表卡片把作者显示成一串数字）
    _CARD_AUTHOR_RE = re.compile(
        r'steamcommunity\.com/(?:id/([^/"]+)|profiles/(\d+))/myworkshopfiles'
    )
    # 卡片作者文本（bug3 实证：真实页每张卡都带 "作者：<昵称>" 文本，
    # 即使作者链接是 profiles/<steamid> 也有；旧正则只认 id/ 链接，
    # 导致这类卡片的 creator_name 为空，用户看到作者名缺失/错误）
    _CARD_AUTHOR_TEXT_RE = re.compile(
        r'(?:作者|Author)\s*[：:]\s*([^<]{1,80})'
    )

    @staticmethod
    def _fix_html_entities(text: str) -> str:
        """修复页面上不完整的 HTML 实体（如 Kirbin&#x27 缺分号），
        再统一 unescape。"""
        # 项目自带的 html_unescape 只覆盖 5 个基础实体，这里用标准库
        # 处理所有数字/命名实体（含 &#x27; 撇号）
        from html import unescape as _std_unescape

        out = _std_unescape(text)
        if "&#" in out:
            fixed = re.sub(r'&#(x?[0-9a-fA-F]{1,6})(?!;)', r'&#\1;', out)
            out = _std_unescape(fixed)
        return out

    # ----------------------------------------------------------- 卡片解析
    def _parse_cards(
        self, html: str, appid: str = "",
        card_matches: list | None = None,
    ) -> list[WorkshopItem]:
        """从经典浏览页 HTML 解析卡片列表（含作者名）。

        作者名优先取页面显示的 "作者：<昵称>" 文本（bug3 实证：真实页
        每张卡都带，即使作者链接是 profiles/<steamid>）；myworkshopfiles
        的 id/<昵称> 链接兜底。creator 一律存 steamid64（若有）。
        """
        if card_matches is None:
            card_matches = list(self._CARD_RE.finditer(html))
        items: list[WorkshopItem] = []
        seen: set[str] = set()
        for i, m in enumerate(card_matches):
            pid, img, title = m.group(1), m.group(2), m.group(3)
            if pid in seen:
                continue
            seen.add(pid)
            # 卡片块 = 当前卡片到下一张卡片之间；作者信息在块内
            end = (card_matches[i + 1].start()
                   if i + 1 < len(card_matches) else len(html))
            block = html[m.start():end]
            creator_name = ""
            creator = ""
            tm = self._CARD_AUTHOR_TEXT_RE.search(block)
            if tm:
                creator_name = self._fix_html_entities(tm.group(1).strip())
            am = self._CARD_AUTHOR_RE.search(block)
            if am:
                if not creator_name:
                    creator_name = self._fix_html_entities(am.group(1) or "")
                creator = am.group(2) or ""
            items.append(
                WorkshopItem(
                    publishedfileid=pid,
                    title=html_unescape(title),
                    preview_url=img.replace("&amp;", "&"),
                    appid=str(appid),
                    creator=creator,
                    creator_name=creator_name,
                )
            )
        return items

    def browse(
        self,
        appid: str,
        page: int = 1,
        search_text: str = "",
        sort: str = "trend",
        required_tags: list[str] | None = None,
        language: str = "schinese",
        numperpage: int = 30,
        force_refresh: bool = False,
    ) -> list[WorkshopItem]:
        """抓取经典浏览页，返回 (id, 标题, 预览图) 的轻量物品列表。

        force_refresh=True 时跳过缓存（用于"强制刷新"场景）。
        结果默认缓存 3 分钟：翻页回来 / 重复搜索同条件时零请求命中，
        显著缓解 429 限流。
        """
        from .api_cache import get_api_cache, make_cache_key

        cache = get_api_cache()
        key = make_cache_key(
            appid, page, sort, search_text, required_tags or [], language,
            numperpage,
        )
        if not force_refresh:
            hit, cached = cache.get(key)
            if hit:
                log.debug("browse 缓存命中 appid=%s page=%s", appid, page)
                # WorkshopItem 是可变 dataclass，enrich() 会就地修改列表：
                # 返回深拷贝，避免污染缓存
                return [copy.deepcopy(it) for it in cached]

        params: dict[str, Any] = {
            "appid": appid,
            "p": page,
            "actualsort": sort,
            "browsesort": sort,
            "numperpage": numperpage,
        }
        if search_text:
            params["searchtext"] = search_text
        if required_tags:
            params["requiredtags[]"] = required_tags
        if language:
            params["l"] = language
        try:
            html = self._community_get("/workshop/browse/", params)
        except RateLimitError:
            # 429 耗尽重试：若有（哪怕过期的）缓存，降级返回而非报错
            stale = cache._get_stale(key)
            if stale:
                log.info("browse 触发限流，降级返回缓存 appid=%s page=%s", appid, page)
                return [copy.deepcopy(it) for it in stale]
            raise
        except requests.RequestException as e:
            log.error("抓取浏览页失败 (appid=%s): %s", appid, e)
            return []

        card_matches = list(self._CARD_RE.finditer(html))
        items = self._parse_cards(html, str(appid), card_matches)

        # 经典页 SSR 卡片为空时，页面可能已切换到新 hub 渲染：
        # 数据以 React Query 脱水状态内联在 HTML 里，解析它作为回退。
        if not items:
            hub_items = self._parse_hub_inline(html, appid)
            if hub_items:
                log.info(
                    "经典页 0 卡片，改用 hub 内联数据 appid=%s -> %d 个物品",
                    appid, len(hub_items),
                )
                cache.set(key, hub_items)
                # 与命中路径一致：返回深拷贝，enrich() 就地修改不污染缓存
                return [copy.deepcopy(it) for it in hub_items]

        log.info("浏览页 appid=%s page=%s -> %d 个物品", appid, page, len(items))
        cache.set(key, items)
        # 未命中路径同样必须深拷贝：本列表即缓存内的对象，调用方
        #（BrowseWorker.enrich）就地修改会污染缓存，使命中路径的
        # 深拷贝保护失效
        return [copy.deepcopy(it) for it in items]

    @staticmethod
    def _parse_hub_inline(html: str, appid: str) -> list[WorkshopItem]:
        """解析新 hub 页内联的 React Query 脱水状态（Rust/DST 等）。"""
        from .hub_parser import extract_results

        results, _total, _pages = extract_results(html)
        out: list[WorkshopItem] = []
        for d in results:
            out.append(WorkshopItem(
                publishedfileid=str(d.get("publishedfileid", "")),
                title=d.get("title", ""),
                description=d.get("short_description", ""),
                creator=str(d.get("creator", "")),
                appid=str(d.get("consumer_app_id") or d.get("consumer_appid") or appid),
                file_size=int(d.get("file_size", 0) or 0),
                preview_url=d.get("preview_url", ""),
                file_url=d.get("file_url", ""),
                tags=[t.get("tag", "") for t in d.get("tags", []) if t.get("tag")],
                time_created=int(d.get("time_created", 0) or 0),
                time_updated=int(d.get("time_updated", 0) or 0),
                subscriptions=int(d.get("subscriptions", 0)
                                  or d.get("lifetime_subscriptions", 0) or 0),
                lifetime_subscriptions=int(d.get("lifetime_subscriptions", 0) or 0),
                favorited=int(d.get("favorited", 0) or 0),
                views=int(d.get("views", 0) or 0),
                result=int(d.get("eresult", 1) or 1),
            ))
        return out

    def enrich(self, items: list[WorkshopItem]) -> list[WorkshopItem]:
        """用 API 批量补全物品的完整元数据（订阅数、作者、标签等）。"""
        if not items:
            return items
        ids = [i.publishedfileid for i in items]
        # 分批，每批 50 个
        for start in range(0, len(ids), 50):
            batch = ids[start : start + 50]
            details = self.get_file_details(batch)
            for it in items:
                if it.publishedfileid in details:
                    d = details[it.publishedfileid]
                    it.description = d.description
                    it.creator = d.creator
                    it.file_size = d.file_size
                    it.subscriptions = d.subscriptions
                    it.lifetime_subscriptions = d.lifetime_subscriptions
                    it.favorited = d.favorited
                    it.views = d.views
                    it.tags = d.tags
                    it.time_created = d.time_created
                    it.time_updated = d.time_updated
                    if not it.preview_url:
                        it.preview_url = d.preview_url
                    if not it.title:
                        it.title = d.title
        return items

    # ------------------------------------------------------- 搜索二次处理
    # Steam 浏览页（/workshop/browse/）的搜索只对标题做模糊匹配，
    # 不匹配作者字段：搜作者名会返回一堆标题相近的 mod，对用户来说
    # 就是"结果完全无关"。匿名 browse 模式下在客户端做二次处理：
    # 标题命中率低时给出解释性提示，0 命中时回退到按作者过滤。

    #: 标题命中率低于此阈值即认为"结果看起来无关"，展示提示
    TITLE_HIT_HINT_THRESHOLD = 0.3

    #: 低命中率（非 0）时展示给用户的解释文字（B①：去"API key 模式"黑话，
    #: 指引用户到设置页；与 t12 标签过滤提示同为一套大白话措辞）
    SEARCH_LOW_HIT_HINT = (
        "Steam 搜索只匹配标题；想精确搜索作者，可在设置页填写 Steam API Key"
    )

    @staticmethod
    def title_hit_rate(items: list, search_text: str) -> float:
        """搜索词在物品标题中的命中率（子串匹配、大小写不敏感）。

        无搜索词或无结果时返回 0.0。
        """
        if not items or not search_text:
            return 0.0
        needle = search_text.strip().lower()
        if not needle:
            return 0.0
        hits = sum(1 for it in items if needle in (getattr(it, "title", "") or "").lower())
        return hits / len(items)

    @staticmethod
    def filter_items_by_creator(items: list, search_text: str) -> list:
        """按作者字段过滤（creator_name 优先，回退 creator steamid64）。"""
        needle = search_text.strip().lower()
        if not needle:
            return list(items)
        out = []
        for it in items:
            name = (getattr(it, "creator_name", "") or "")
            sid = (getattr(it, "creator", "") or "")
            if needle in f"{name}\x00{sid}".lower():
                out.append(it)
        return out

    @staticmethod
    def filter_items_by_tags(items: list, tags: list) -> tuple[list, int, bool]:
        """服务端 requiredtags 只是近似匹配（会把不含该标签的物品也返回），
        客户端按选中标签做精确交集过滤：只保留 tags 包含**全部**所选标签的物品。

        返回 (filtered, dropped_count, unverifiable)：
        - unverifiable=True 表示多数物品未返回标签数据（enrich 失败/接口未给），
          此时不过滤，由调用方提示"服务端近似匹配"。
        """
        sel = {t.strip().lower() for t in tags if t and t.strip()}
        if not sel or not items:
            return items, 0, False
        # 元数据缺失占比过高时无法精确判定（enrich 被 429 等情况）
        with_tags = [it for it in items if getattr(it, "tags", None)]
        if len(with_tags) * 2 < len(items):
            return items, 0, True
        out = []
        for it in items:
            its = {str(t).strip().lower() for t in (it.tags or [])}
            if sel <= its:
                out.append(it)
        return out, len(items) - len(out), False

    @staticmethod
    def apply_browse_search_fallback(
        items: list, search_text: str, api_key_mode: bool
    ) -> tuple[list, str]:
        """匿名 browse 搜索的客户端二次处理，返回 (items, hint)。

        - API key 模式走 QueryFiles，搜索本身匹配标题/作者/描述，不做处理。
        - 标题命中率 >= 阈值：结果可信，原样返回、不提示。
        - 命中率低但非 0：原样返回，但附带解释性提示文字。
        - 0 命中：Steam 把搜索词当标题模糊匹配却没命中任何结果，
          几乎可以肯定是作者名——用（enrich 后的）creator 字段过滤；
          过滤后仍有结果则展示并说明；
          过滤后为空则返回空列表 + 明确空态（标题/作者都不含该词），
          避免把一堆无关结果当作"搜索坏了/被限流了"。

        调用时机：enrich 完成之后（creator/creator_name 已被补全）。
        """
        if not search_text or not items or api_key_mode:
            return items, ""
        rate = SteamAPI.title_hit_rate(items, search_text)
        if rate >= SteamAPI.TITLE_HIT_HINT_THRESHOLD:
            return items, ""
        if rate == 0.0:
            by_author = SteamAPI.filter_items_by_creator(items, search_text)
            if by_author:
                return by_author, (
                    f"已按作者名过滤出 {len(by_author)} 个结果"
                    f"（Steam 搜索只认标题）；想更精确，可在设置页填写 Steam API Key"
                )
            # 标题和作者都没命中：返回空列表 + 明确空态，
            # 而不是展示一堆标题模糊匹配的无关结果
            return [], f"没找到标题或作者含「{search_text.strip()}」的 mod"
        return items, SteamAPI.SEARCH_LOW_HIT_HINT

    # ------------------------------------------------------------- 图片缓存
    def fetch_image(self, url: str, size: int = 512) -> str:
        """下载并缓存预览图，返回本地路径。失败返回原 URL。"""
        if not url:
            return ""
        # 内联 base64 占位图：不是 HTTP URL，原样返回由调用方解码
        if url.startswith("data:"):
            return url
        ensure_dirs()
        key = re.sub(r"[^a-zA-Z0-9]", "_", url)[:180]
        path = os.path.join(CACHE_DIR, f"{key}.jpg")
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            if time.time() - mtime < _IMG_CACHE_DAYS * 86400:
                return path
        fetch_url = url
        if "?" not in fetch_url:
            fetch_url += f"?ima=fit&impolicy=Letterbox&imw={size}&imh={size}"
        try:
            r = self._session.get(fetch_url, timeout=self.timeout)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            return path
        except requests.RequestException as e:
            log.warning("图片下载失败 %s: %s", url[:60], e)
            return url

    # --------------------------------------------------------- 连通性/工具
    def ping(self) -> bool:
        resp = self._api_get("/ISteamWebAPIUtil/GetServerInfo/v1/", {})
        # 该端点无 "response" 包裹层，servertime 直接位于顶层
        return bool(resp.get("servertime") or resp.get("response", {}).get("servertime"))

    def resolve_any_url(self, text: str) -> tuple[str, str]:
        """从用户输入的文本中解析 (appid, publishedfileid)。

        支持：
          - 纯数字 publishedfileid
          - https://steamcommunity.com/sharedfiles/filedetails/?id=xxx
          - https://steamcommunity.com/workshop/browse/?appid=yyy&...
          - https://steamcommunity.com/app/yyy/workshop/
        """
        text = (text or "").strip()
        if not text:
            return "", ""
        m = re.search(r"filedetails/\?id=(\d+)", text)
        if m:
            app = re.search(r"appid=(\d+)", text)
            return (app.group(1) if app else ""), m.group(1)
        m = re.search(r"workshop/browse/\?appid=(\d+)", text)
        if m:
            return m.group(1), ""
        m = re.search(r"app/(\d+)/workshop", text)
        if m:
            return m.group(1), ""
        if text.isdigit():
            return "", text
        return "", ""


def html_unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
