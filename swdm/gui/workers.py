"""Qt worker layer: bridges the core layer's async callbacks into Qt signals (工作线程层).

Principle: every network / download / disk operation runs in QThread or QThreadPool;
the UI only receives signals. Includes a bounded thumbnail cache keyed by item id
(with disk fallback) so repeated card renders do not re-download.
"""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QPixmap

from swdm.core import SteamAPI, WorkshopItem, get_config
from swdm.core.downloader import DownloadManager, DownloadJob
from swdm.core.logger import get_logger

log = get_logger("swdm.gui.workers")


# --------------------------------------------------------------------- 浏览
class BrowseWorker(QThread):
    """浏览/搜索工坊列表。"""

    items_ready = Signal(list)     # list[WorkshopItem]
    progress = Signal(str)
    failed = Signal(str)

    def __init__(self, api: SteamAPI, appid: str, page: int = 1, search: str = "",
                 sort: str = "trend", tags: list[str] | None = None,
                 enrich: bool = True, generation: int = 0) -> None:
        super().__init__()
        self.api = api
        self.appid = appid
        self.page = page
        self.search = search
        self.sort = sort
        self.tags = tags or []
        self.enrich = enrich
        # O6（net N1）：代际号——快速切游戏/翻页时旧请求的结果
        # 到达后若代际已过期则丢弃，防止"结果跳来跳去"
        self.generation = generation

    def run(self) -> None:
        from swdm.core import RateLimitError

        try:
            self.progress.emit("正在查询工坊列表…")
            if self.api.api_key:
                items, total = self.api.query_files(
                    self.appid, page=self.page, numperpage=30, search_text=self.search
                )
                self.progress.emit(f"QueryFiles: 本页 {len(items)} / 共 {total}")
            else:
                items = self.api.browse(
                    self.appid, page=self.page, search_text=self.search,
                    sort=self.sort, required_tags=self.tags or None,
                )
                self.progress.emit(f"抓取到 {len(items)} 个物品，正在补全元数据…")
                if self.enrich and items:
                    self.api.enrich(items)
            # 熔断期内的结果仍可展示（缓存兜底），但代际过期直接丢弃
            self.items_ready.emit(items)
        except RateLimitError as e:
            log.warning("浏览触发限流: %s", e)
            self.failed.emit(
                f"Steam 请求过于频繁（429 限流）。已自动等待重试，若仍失败请稍候 "
                f"{e.retry_after:.0f} 秒后再试。"
            )
        except Exception as e:  # noqa: BLE001
            log.exception("浏览线程失败")
            self.failed.emit(f"加载失败: {e}")


# --------------------------------------------------------------- 图片加载
class _ImageSignalBus(QObject):
    """图片信号总线：ready 用于子线程→主线程传路径；loaded 对外广播 QPixmap。"""

    ready = Signal(str, str)              # (url, local_path) 子线程发出
    loaded = Signal(str, object)          # (url, QPixmap)  主线程发出


_image_bus = _ImageSignalBus()
# O3（algo #2）：LRU 缓存替代全量 clear——旧实现在超 300 张时
# _image_cache.clear() 一次性清空，当前可见卡片全部重新下载，
# 造成网络请求突刺。OrderedDict 淘汰最旧条目，保留当前页常用图。
_image_cache: OrderedDict[str, QPixmap] = OrderedDict()
_pending_sizes: dict[str, tuple[int, int]] = {}


class _ImageTask(QRunnable):
    """在子线程下载/定位预览图（不构造 QPixmap，仅解析本地路径）。"""

    def __init__(self, url: str, width: int, height: int) -> None:
        super().__init__()
        self._url = url
        self._size = (width, height)
        self._api = SteamAPI(
            api_key=get_config().get("network", "api_key"),
            proxy=get_config().get("network", "proxy"),
        )

    def run(self) -> None:
        path = self._api.fetch_image(self._url, max(self._size))
        _pending_sizes[self._url] = self._size
        _image_bus.ready.emit(self._url, path)


class _ImageDownloadTask(QRunnable):
    """O2（algo #3）：主线程同步下载回退移到子线程。

    旧实现在 _build_pixmap 里直接 _session.get(timeout=20)，
    主线程阻塞最长 20s，是"无响应"的直接来源之一。此处把 http
    回退也丢进线程池，下载完再走 ready 信号回主线程构造 QPixmap。
    """

    def __init__(self, url: str, width: int, height: int) -> None:
        super().__init__()
        self._url = url
        self._size = (width, height)

    def run(self) -> None:
        try:
            api = SteamAPI(
                api_key=get_config().get("network", "api_key"),
                proxy=get_config().get("network", "proxy"),
            )
            resp = api._session.get(self._url, timeout=20)
            resp.raise_for_status()
            _pending_sizes[self._url] = self._size
            # 用 data URL 把已下好的字节带回主线程解码
            import base64

            b64 = base64.b64encode(resp.content).decode("ascii")
            mime = resp.headers.get("Content-Type", "image/png").split(";")[0]
            _image_bus.ready.emit(self._url, f"data:{mime};base64,{b64}")
        except Exception:  # noqa: BLE001
            # 失败：发空路径触发占位逻辑（_build_pixmap 对空 path 保留占位图）
            _image_bus.ready.emit(self._url, "")


class ImageLoader:
    """图片加载器：子线程取图 → 主线程构造 QPixmap（Qt 线程安全要求）。"""

    def __init__(self, pool: QThreadPool | None = None) -> None:
        self.pool = pool or QThreadPool.globalInstance()
        self.max_cache = 300
        self.bus = _image_bus
        self.bus.ready.connect(self._build_pixmap)

    def load(self, url: str, width: int = 160, height: int = 160) -> None:
        if not url:
            return
        # 内联 base64 占位图（data:image/...）：不走网络，直接解码
        if url.startswith("data:"):
            if url in _image_cache:
                _image_cache.move_to_end(url)
                self.bus.loaded.emit(url, _image_cache[url])
                return
            _pending_sizes[url] = (width, height)
            _image_bus.ready.emit(url, url)   # 把 data URL 传给主线程解码
            return
        if url in _image_cache:
            _image_cache.move_to_end(url)
            self.bus.loaded.emit(url, _image_cache[url])
            return
        # O3：超限只淘汰最旧的若干条，不清空全部
        while len(_image_cache) >= self.max_cache:
            _image_cache.popitem(last=False)
        self.pool.start(_ImageTask(url, width, height))

    @Slot(str, str)
    def _build_pixmap(self, url: str, local_path: str) -> None:
        """主线程：构造 QPixmap 并广播。"""
        if url in _image_cache:
            self.bus.loaded.emit(url, _image_cache[url])
            return
        pixmap = QPixmap()
        size = _pending_sizes.get(url, (160, 160))
        if local_path.startswith("data:"):
            # 内联 base64 占位图：主线程直接解码（Qt 线程安全要求）
            try:
                import base64

                header, _, b64 = local_path.partition(",")
                raw = base64.b64decode(b64)
                pixmap.loadFromData(raw)
            except Exception:  # noqa: BLE001
                pass
        elif local_path and not local_path.startswith("http"):
            pixmap.load(local_path)
        elif local_path:
            # O2（algo #3）：fetch_image 回退返回了原始 URL——
            # 不在主线程同步下载（会阻塞最长 20s 导致无响应），
            # 改丢回线程池异步下载
            w, h = _pending_sizes.get(url, (160, 160))
            self.pool.start(_ImageDownloadTask(url, w, h))
            return
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                size[0], size[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        _image_cache[url] = pixmap
        _image_cache.move_to_end(url)
        self.bus.loaded.emit(url, pixmap)


# --------------------------------------------------------- 下载事件桥接
class DownloadEventBridge(QObject):
    """把 DownloadManager 的回调桥接为 Qt 信号。"""

    started = Signal(object)       # DownloadJob
    progress = Signal(object)      # DownloadJob
    finished = Signal(object)      # DownloadJob
    queue_changed = Signal()

    def attach(self, mgr: DownloadManager) -> None:
        mgr.on_started = self._on_started
        mgr.on_progress = self._on_progress
        mgr.on_finished = self._on_finished
        mgr.on_queue_changed = self._on_queue_changed

    def _on_started(self, job: DownloadJob) -> None:
        self.started.emit(job)

    def _on_progress(self, job: DownloadJob) -> None:
        self.progress.emit(job)

    def _on_finished(self, job: DownloadJob) -> None:
        self.finished.emit(job)

    def _on_queue_changed(self) -> None:
        self.queue_changed.emit()


# ------------------------------------------------------- 登录连通性测试
class LoginWorker(QThread):
    """测试 steamcmd 登录（匿名或用户）。"""

    result = Signal(bool, str)

    def __init__(self, engine_factory) -> None:
        super().__init__()
        self.engine_factory = engine_factory

    def run(self) -> None:
        try:
            eng = self.engine_factory()
            ok, msg = eng.test_login()
            self.result.emit(ok, msg)
        except Exception as e:  # noqa: BLE001
            log.exception("登录测试失败")
            self.result.emit(False, f"登录异常: {e}")


# ------------------------------------------------------- 前置依赖解析
class DependencyResolveWorker(QThread):
    """解析一批物品的前置依赖树（需求：依赖 mod 下载配置）。

    在后台线程执行网络解析，避免阻塞 UI；完成后通过信号返回
    {deps: [id...], skipped: [id...], dep_names: {id: title}}。
    """

    result = Signal(dict)

    def __init__(
        self,
        api: SteamAPI,
        items: list,
        appid: str,
        max_depth: int = 10,
        skip_installed: bool = True,
        library=None,
    ) -> None:
        super().__init__()
        self._api = api
        self._items = items
        self._appid = str(appid)
        self._max_depth = max_depth
        self._skip_installed = skip_installed
        self._library = library

    def run(self) -> None:
        deps: list[str] = []
        skipped: list[str] = []
        names: dict[str, str] = {}
        try:
            seen: set[str] = set()
            for it in self._items:
                try:
                    sub_deps, sub_skipped = self._api.resolve_dependency_tree(
                        it,
                        max_depth=self._max_depth,
                        skip_installed=self._skip_installed,
                        library=self._library,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("解析 %s 的依赖失败", it.publishedfileid)
                    continue
                skipped.extend(sub_skipped)
                for d in sub_deps:
                    if d.publishedfileid in seen:
                        continue
                    seen.add(d.publishedfileid)
                    deps.append(d.publishedfileid)
                    names[d.publishedfileid] = d.title or d.publishedfileid
        except Exception:  # noqa: BLE001
            log.exception("依赖解析工作线程异常")
        self.result.emit({"deps": deps, "skipped": skipped, "dep_names": names})
