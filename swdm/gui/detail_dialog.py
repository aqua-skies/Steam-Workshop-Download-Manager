"""Mod detail dialog (non-modal): can stay open alongside the workshop list (Mod 详情页对话框).

Layout:
    Top:    preview image (left, scaled to a fixed width) + title / author / subscribers /
            size / update time (right)
    Tag chips (FlowLayout, wrapping horizontally)
    Description (read-only rich text, newlines preserved)
    Conflict warning (hidden by default; yellow/red background when a conflict list is passed)
    Required items (前置依赖: id + title, each downloadable individually)
    Comments (scrollable list: author / time / body, with a friendly empty state)
    Buttons: Download (with dependencies) / Add to queue / Close

Conventions:
    - PySide6 enums always spelled out in full (Qt.WindowModality.NonModal …)
    - QPixmap is constructed only on the main thread: worker threads download raw bytes and
      hand them back via a queued signal
    - Network runs in QThread; the UI only receives signals
"""
from __future__ import annotations

import html as html_module
import os
import re
from dataclasses import dataclass
from datetime import datetime
from collections import OrderedDict

from PySide6.QtCore import (
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from swdm.core import WorkshopItem
from swdm.core.deps_parser import parse_required_items_with_titles
from swdm.core.logger import get_logger
from swdm.gui.widgets import CollapsibleSection

log = get_logger("swdm.gui.detail")


# ============================================================ 数据结构
@dataclass
class Comment:
    """一条工坊评论。"""

    author: str = ""
    time: str = ""
    content: str = ""


# ============================================================ HTML 解析
_DESC_RE = re.compile(
    r'<div[^>]*class="[^"]*workshopItemDescription[^"]*"[^>]*id="highlightContent"[^>]*>',
    re.IGNORECASE,
)
_AUTHOR_RE = re.compile(
    r'commentthread_author_link"[^>]*>(?:\s*<bdi>)?(.*?)(?:</bdi>)?\s*</a>',
    re.DOTALL,
)
_TS_RE = re.compile(r'data-timestamp="(\d+)"')
_COMMENT_START_RE = re.compile(
    r'<div[^>]*class="[^"]*commentthread_comment[^"]*"[^>]*id="comment_(\d+)"',
    re.IGNORECASE,
)
_COMMENT_TOTAL_RE = re.compile(r'id="commentthread_[^"]*_totalcount">\s*(\d+)', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _slice_balanced_div(html: str, start: int) -> str:
    """从 start（<div ...> 之后）开始，按 div 配对截取到匹配的 </div>。"""
    depth = 1
    i = start
    while i < len(html) and depth > 0:
        nxt_open = html.find("<div", i)
        nxt_close = html.find("</div>", i)
        if nxt_close == -1:
            break
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            i = nxt_close + 6
    return html[start:i]


def _strip_tags(s: str) -> str:
    return html_module.unescape(_TAG_RE.sub("", s or "")).strip()


def _clean_content(s: str) -> str:
    """评论正文：保留换行、去标签、还原实体。"""
    s = s or ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p>|</div>|</li>", "\n", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)
    return html_module.unescape(s).strip()


def _fmt_timestamp(ts: str) -> str:
    """unix 时间戳 → 'YYYY-MM-DD HH:MM'，失败返回空串。"""
    try:
        val = int(ts)
    except (TypeError, ValueError):
        return ""
    if val <= 0:
        return ""
    try:
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def parse_description(html: str) -> str:
    """从详情页 HTML 解析简介（富文本，保留原始标签）。"""
    if not html:
        return ""
    m = _DESC_RE.search(html)
    if not m:
        return ""
    return _slice_balanced_div(html, m.end()).strip()


def comment_total(html: str) -> int:
    """评论总数（页面头部计数）。"""
    m = _COMMENT_TOTAL_RE.search(html or "")
    try:
        return int(m.group(1)) if m else 0
    except (TypeError, ValueError):
        return 0


def parse_comments(html: str) -> list[Comment]:
    """从详情页 HTML 解析评论列表。空页面返回 []。"""
    if not html or "commentthread_comment" not in html:
        return []
    starts = list(_COMMENT_START_RE.finditer(html))
    out: list[Comment] = []
    for idx, m in enumerate(starts):
        end = starts[idx + 1].start() if idx + 1 < len(starts) else len(html)
        block = html[m.start():end]

        author = ""
        am = _AUTHOR_RE.search(block)
        if am:
            author = _strip_tags(am.group(1))

        ts = ""
        tm = _TS_RE.search(block)
        if tm:
            ts = _fmt_timestamp(tm.group(1))

        content = ""
        cm = re.search(
            r'id="comment_content_' + re.escape(m.group(1)) + r'"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if cm:
            content = _clean_content(cm.group(1))

        out.append(Comment(author=author, time=ts, content=content))
    return out


# ============================================================ 输入归一化
def _norm_comment(c) -> Comment:
    """兼容 Comment / dict / tuple 等外部传入格式。"""
    if isinstance(c, Comment):
        return c
    if isinstance(c, dict):
        return Comment(
            author=str(c.get("author", "")),
            time=str(c.get("time") or c.get("date") or c.get("timestamp") or ""),
            content=str(c.get("content") or c.get("text") or ""),
        )
    if isinstance(c, (tuple, list)):
        if len(c) >= 3:
            return Comment(str(c[0]), str(c[1]), str(c[2]))
        if len(c) == 2:
            return Comment(str(c[0]), "", str(c[1]))
        return Comment("", "", str(c[0]) if c else "")
    return Comment("", "", str(c))


def _norm_dep(d) -> tuple[str, str]:
    """归一化依赖项为 (id, title)。兼容 WorkshopItem / dict / tuple。"""
    if isinstance(d, WorkshopItem):
        return (d.publishedfileid, d.title or d.publishedfileid)
    if isinstance(d, dict):
        pid = str(d.get("id") or d.get("publishedfileid") or "")
        title = str(d.get("title") or d.get("name") or pid)
        return (pid, title)
    if isinstance(d, (tuple, list)):
        if len(d) >= 2:
            return (str(d[0]), str(d[1]))
        if len(d) == 1:
            return (str(d[0]), "")
        return ("", "")
    return (str(d or ""), "")


def _norm_conflict(c) -> tuple[str, str, str]:
    """归一化冲突项为 (id, title, reason)。兼容 dict / tuple / str。"""
    if isinstance(c, dict):
        return (
            str(c.get("id", "")),
            str(c.get("title") or c.get("name") or ""),
            str(c.get("reason") or c.get("detail") or ""),
        )
    if isinstance(c, (tuple, list)):
        if len(c) >= 3:
            return (str(c[0]), str(c[1]), str(c[2]))
        if len(c) == 2:
            return ("", str(c[0]), str(c[1]))
        return ("", str(c[0]) if c else "", "")
    return ("", str(c), "")


def _to_html(text: str) -> str:
    """普通文本 → HTML（保留换行）；已是 HTML 则原样保留。"""
    text = text or ""
    if "<" in text and ">" in text:
        return text.replace("\r\n", "\n").replace("\n", "<br>")
    return html_module.escape(text).replace("\n", "<br>")


# ============================================================ 线程
class PreviewImageWorker(QThread):
    """预览图加载线程：子线程下载字节 → 主线程构造 QPixmap（Qt 线程安全要求）。

    信号：
        pixmap_ready(QPixmap) 主线程发出，可直接用于 UI
        failed(str)           加载失败原因
    """

    pixmap_ready = Signal(QPixmap)
    failed = Signal(str)
    _raw_ready = Signal(object)   # 子线程 → 主线程的原始字节中转

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, url: str, width: int = 320, height: int = 180,
                 api=None, parent=None) -> None:
        super().__init__(parent)
        self._url = url or ""
        self._width = max(32, int(width))
        self._height = max(32, int(height))
        self._api = api
        # 队列连接：run() 在子线程发射，槽在主线程执行（QPixmap 只能在主线程构造）
        self._raw_ready.connect(
            self._on_raw_ready, Qt.ConnectionType.QueuedConnection
        )

    # ---------------------------------------------------------- 子线程
    def run(self) -> None:
        try:
            data = self._fetch_bytes()
            if data:
                self._raw_ready.emit(data)
            else:
                self.failed.emit("预览图为空")
        except Exception as e:  # noqa: BLE001
            log.warning("预览图加载失败 %s: %s", (self._url or "")[:80], e)
            self.failed.emit("预览图加载失败")

    def _fetch_bytes(self) -> bytes | None:
        """子线程：下载图片原始字节。优先复用 api 的缓存与代理。"""
        if self._api is not None and hasattr(self._api, "fetch_image"):
            path = self._api.fetch_image(self._url, max(self._width, self._height))
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
            if path and path.startswith("http"):
                resp = self._api._session.get(path, timeout=20)
                resp.raise_for_status()
                return resp.content
            return None

        import requests

        resp = requests.get(
            self._url, headers={"User-Agent": self._UA}, timeout=20
        )
        resp.raise_for_status()
        return resp.content

    # ---------------------------------------------------------- 主线程
    @Slot(object)
    def _on_raw_ready(self, data) -> None:
        """主线程：构造 QPixmap 并按比例缩放后广播。"""
        if not data:
            self.failed.emit("预览图数据为空")
            return
        pixmap = QPixmap()
        try:
            pixmap.loadFromData(bytes(data))
        except Exception:  # noqa: BLE001
            pixmap = QPixmap()
        if pixmap.isNull():
            self.failed.emit("预览图解析失败")
            return
        pixmap = pixmap.scaled(
            self._width, self._height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.pixmap_ready.emit(pixmap)


class DetailPageWorker(QThread):
    """详情页数据解析线程：抓取工坊详情页并解析简介/评论/前置依赖。

    信号：
        description_ready(str)  富文本简介
        comments_ready(list)    list[Comment]
        deps_ready(list)        list[(id, title)]
        conflicts_ready(list)   list[ConflictInfo]（从简介提取的冲突声明）
        total_ready(int)        评论总数
        failed(str)             失败原因
    """

    description_ready = Signal(str)
    creator_ready = Signal(str)
    comments_ready = Signal(list)
    deps_ready = Signal(list)
    conflicts_ready = Signal(list)
    total_ready = Signal(int)
    failed = Signal(str)

    def __init__(self, api, item_id: str, parent=None) -> None:
        super().__init__(parent)
        self._api = api
        self._item_id = str(item_id)

    # 进程级详情页缓存：同一物品 5 分钟内不重复请求（缓解 429 限流）
    # O4（algo #4）：加上限，避免长会话浏览大量 mod 时字典无限增长
    # （每个详情页 HTML 约 100-300KB，1000 个 = 100-300MB 常驻）
    _page_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
    _PAGE_CACHE_TTL = 300.0
    _PAGE_CACHE_MAX = 100

    def run(self) -> None:
        try:
            import time as _time

            cached = DetailPageWorker._page_cache.get(self._item_id)
            if cached and _time.time() - cached[0] < DetailPageWorker._PAGE_CACHE_TTL:
                html = cached[1]
            else:
                html = self._api._community_get(
                    "/sharedfiles/filedetails/", {"id": self._item_id},
                    priority=True,  # 用户点击永远优先于悬停预取
                )
                if html:
                    DetailPageWorker._page_cache[self._item_id] = (
                        _time.time(), html
                    )
                    # O4：超上限淘汰最旧条目
                    while len(DetailPageWorker._page_cache) > \
                            DetailPageWorker._PAGE_CACHE_MAX:
                        DetailPageWorker._page_cache.popitem(last=False)
            if not html:
                self.failed.emit("详情页内容为空")
                return
            from swdm.core.page_parser import parse_description

            desc = parse_description(html)
            if desc:
                self.description_ready.emit(desc)
            # 作者昵称（bug9：列表只有 steamid64，详情页才有真名）
            from swdm.core.page_parser import parse_creator_name

            creator = parse_creator_name(html)
            if creator:
                self.creator_ready.emit(creator)
            # 从简介提取作者声明的冲突 mod
            try:
                from swdm.core.conflict_extractor import extract_conflicts

                conflicts = extract_conflicts(desc, str(self._item_id))
                if conflicts:
                    self.conflicts_ready.emit(conflicts)
            except Exception:  # noqa: BLE001
                log.debug("冲突提取失败，忽略")
            self.total_ready.emit(comment_total(html))
            self.comments_ready.emit(parse_comments(html))
            self.deps_ready.emit(parse_required_items_with_titles(html))
        except Exception as e:  # noqa: BLE001
            log.exception("详情页解析失败 (item=%s)", self._item_id)
            self.failed.emit(f"详情加载失败: {e}")


# ============================================================ 辅助控件
class FlowLayout(QLayout):
    """简易流式布局：子控件横向排列、自动换行（用于标签 chips）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is not None:
            parent.setLayout(self)
        self._items: list = []

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def clear(self) -> None:
        """移除并删除全部子控件。"""
        while self._items:
            item = self._items.pop()
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        for item in self._items:
            wid = item.widget()
            if wid is None:
                continue
            hint = wid.sizeHint()
            if x + hint.width() > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class CommentWidget(QWidget):
    """单条评论：作者/时间（头部富文本）+ 内容（自动换行）。"""

    def __init__(self, comment: Comment, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(3)

        author = html_module.escape(comment.author or "匿名用户")
        when = html_module.escape(comment.time or "")
        head = QLabel(
            f"<b style='color:#e8ecf2;'>{author}</b>"
            f"<span style='color:#8a909a; font-size:11px;'>"
            f"{'  ·  ' + when if when else ''}</span>"
        )
        head.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(head)

        body = QLabel(comment.content or "（内容为空）")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setStyleSheet("color:#c6ccd4; font-size:12px;")
        lay.addWidget(body)

        self.setObjectName("commentWidget")
        self.setStyleSheet(
            "QWidget#commentWidget { background:#262b32; "
            "border:1px solid #2d3138; border-radius:6px; }"
        )


class DepRowWidget(QWidget):
    """单个前置依赖行：id + 标题 + 独立下载按钮。"""

    download_clicked = Signal(str, str)   # (dep_id, title)
    search_clicked = Signal(str)          # title（点击标题快捷搜索）

    def __init__(self, dep_id: str, title: str, installed: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(10)

        self.dep_id = dep_id
        self.title = title

        self.id_label = QLabel(
            f"<span style='color:#8a909a; font-size:11px;'>{html_module.escape(dep_id)}</span>"
        )
        self.id_label.setTextFormat(Qt.TextFormat.RichText)
        self.id_label.setFixedWidth(120)
        self.id_label.setWordWrap(False)
        lay.addWidget(self.id_label)

        # 标题可点击：跳到筛选页按名字搜索该依赖 mod
        self.title_label = QLabel(
            f"<a href='dep' style='color:#d5dae2;text-decoration:none;'>"
            f"{html_module.escape(title or dep_id)}</a>"
        )
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setWordWrap(True)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.setToolTip(f"点击搜索「{title or dep_id}」")
        self.title_label.setStyleSheet("color:#d5dae2; font-size:12px;")
        self.title_label.linkActivated.connect(
            lambda _l: self.search_clicked.emit(self.title or self.dep_id)
        )
        lay.addWidget(self.title_label, 1)

        self.btn = QPushButton("✓ 已在库" if installed else "⬇ 下载")
        self.btn.setProperty("secondary", bool(installed))
        self.btn.setFixedWidth(84)
        self.btn.setEnabled(not installed)
        self.btn.clicked.connect(
            lambda: self.download_clicked.emit(self.dep_id, self.title)
        )
        lay.addWidget(self.btn)

        self.setStyleSheet(
            "QWidget { background:#23272e; border-radius:5px; }"
            "QWidget:hover { background:#2a2f37; }"
        )


# ============================================================ 主对话框
class ModDetailDialog(QDialog):
    """Mod 详情页对话框（非模态）。

    可与工坊选择页同时开启：windowModality=NonModal，使用 show() 而非 exec()。
    """

    download_requested = Signal(str)   # publishedfileid（含依赖下载）
    queue_requested = Signal(str)      # publishedfileid（仅加入队列）
    search_requested = Signal(str, str)  # (kind, value) 快捷搜索跳转：tag/text/author

    PREVIEW_W = 320
    PREVIEW_H = 180

    def __init__(
        self,
        item: WorkshopItem,
        parent=None,
        comments=None,
        dependencies=None,
        conflicts=None,
        library=None,
        downloader=None,
        api=None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.library = library
        self.downloader = downloader
        self.api = api

        self._comments: list[Comment] = []
        self._deps: list[tuple[str, str]] = []
        self._conflicts: list[tuple[str, str, str]] = []
        self._comments_loaded = comments is not None
        self._deps_loaded = dependencies is not None

        self._image_worker: PreviewImageWorker | None = None

        self.setWindowTitle(f"Mod 详情 - {item.title or item.publishedfileid}")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(760, 580)
        self.resize(820, 660)
        self._apply_qss()
        self._build_ui()

        # 初始数据（item 自带的部分）
        if item.description:
            self.set_description(item.description)
        if comments is not None:
            self.set_comments(comments)
        if dependencies is not None:
            self.set_dependencies(dependencies)
        if conflicts is not None:
            self.set_conflicts(conflicts)

        # 预览图（单独 QThread）
        self._start_image_load()

    # --------------------------------------------------------------- 样式
    def _apply_qss(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #1e2126; }
            QLabel { color: #d5dae2; }
            QTextEdit, QTextBrowser {
                background: #262b32; color: #d5dae2;
                border: 1px solid #343a44; border-radius: 5px;
            }
            QPushButton {
                background: #2f6fd0; color: white; border: none;
                padding: 7px 16px; border-radius: 5px; font-weight: 500;
            }
            QPushButton:hover { background: #3d80e6; }
            QPushButton:pressed { background: #255bb0; }
            QPushButton:disabled { background: #3a4048; color: #6a7078; }
            QPushButton[secondary="true"] { background: #343a44; color: #d5dae2; }
            QPushButton[secondary="true"]:hover { background: #40474f; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1d22; width: 10px; }
            QScrollBar::handle:vertical {
                background: #343a44; border-radius: 4px; min-height: 20px;
            }
            """
        )

    # --------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ---- 顶部：预览图（左） + 标题/作者/订阅/大小/更新时间（右）
        header = QHBoxLayout()
        header.setSpacing(12)

        self.preview_label = QLabel("图片加载中…")
        self.preview_label.setFixedSize(self.PREVIEW_W, self.PREVIEW_H)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background:#262b32; border:1px solid #2d3138; border-radius:6px;"
            "color:#8a909a; font-size:12px;"
        )
        header.addWidget(self.preview_label, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)

        self.title_label = QLabel(
            f"<span style='font-size:18px; font-weight:700; color:#e8ecf2;'>"
            f"{html_module.escape(self.item.title or self.item.publishedfileid)}</span>"
        )
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setWordWrap(True)
        info.addWidget(self.title_label)

        author_name = (
            self.item.creator_name or self.item.creator or "未知"
        )
        if author_name and author_name != "未知":
            self.author_label = QLabel(
                f"<span style='color:#9aa0aa;'>作者：</span>"
                f"<a href='author:{html_module.escape(str(author_name))}' "
                f"style='color:#7c5cff;text-decoration:none;'>"
                f"{html_module.escape(str(author_name))}</a>"
            )
            self.author_label.setToolTip(
                f"点击搜索作者「{author_name}」的其他 mod"
            )
            self.author_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.author_label.linkActivated.connect(
                lambda _l, n=str(author_name): self.search_requested.emit("author", n)
            )
        else:
            self.author_label = QLabel(
                "<span style='color:#9aa0aa;'>作者：</span>"
                "<span style='color:#d5dae2;'>未知</span>"
            )
        self.author_label.setTextFormat(Qt.TextFormat.RichText)
        info.addWidget(self.author_label)

        self.meta_label = QLabel(self._meta_html())
        self.meta_label.setTextFormat(Qt.TextFormat.RichText)
        self.meta_label.setWordWrap(True)
        info.addWidget(self.meta_label)
        info.addStretch()
        header.addLayout(info, 1)
        root.addLayout(header)

        # ---- 错误提示（默认隐藏）
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            "color:#ffb4b4; background:#3a2222; border:1px solid #6e3030;"
            "border-radius:5px; padding:6px 10px;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        # ---- 标签 chips
        self.tags_host = QWidget()
        self.tags_layout = FlowLayout(self.tags_host)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(6)
        self._render_tags(self.item.tags)
        root.addWidget(self.tags_host)

        # ---- 简介
        root.addWidget(self._section_title("📝 简介"))
        self.desc_edit = QTextBrowser()
        self.desc_edit.setReadOnly(True)
        self.desc_edit.setAcceptRichText(True)
        # 简介里的链接可直接点击打开（bug12）
        self.desc_edit.setOpenExternalLinks(True)
        self.desc_edit.setPlaceholderText("暂无简介")
        self.desc_edit.setMinimumHeight(110)
        self.desc_edit.setMaximumHeight(180)
        root.addWidget(self.desc_edit)

        # ---- 冲突警告（默认隐藏）
        self.conflict_frame = QFrame()
        self.conflict_frame.setVisible(False)
        cl = QVBoxLayout(self.conflict_frame)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(4)
        self.conflict_title = QLabel("⚠ 冲突警告")
        self.conflict_title.setStyleSheet(
            "color:#ffd166; font-weight:700; font-size:13px; border:none;"
        )
        cl.addWidget(self.conflict_title)
        self.conflict_list_host = QWidget()
        self.conflict_list_layout = QVBoxLayout(self.conflict_list_host)
        self.conflict_list_layout.setContentsMargins(0, 0, 0, 0)
        self.conflict_list_layout.setSpacing(2)
        cl.addWidget(self.conflict_list_host)
        root.addWidget(self.conflict_frame)

        # ---- 前置依赖
        root.addWidget(self._section_title("🔗 前置依赖"))
        self.deps_scroll, self.deps_host, self.deps_layout = self._make_scroll_area()
        self.deps_placeholder = QLabel("前置依赖加载中…")
        self.deps_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.deps_placeholder.setStyleSheet("color:#8a909a; padding:12px;")
        self.deps_layout.addWidget(self.deps_placeholder)
        root.addWidget(self.deps_scroll)

        # ---- 评论（量大次要，默认收起；点击标题展开）
        self.comments_scroll, self.comments_host, self.comments_layout = self._make_scroll_area()
        # 展开后给足最小高度，避免"显示过小"（bug10）
        self.comments_scroll.setMinimumHeight(300)
        self.comments_placeholder = QLabel("评论加载中…")
        self.comments_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.comments_placeholder.setStyleSheet("color:#8a909a; padding:12px;")
        self.comments_layout.addWidget(self.comments_placeholder)
        self.comments_section = CollapsibleSection("💬 评论", expanded=False)
        self.comments_section.addWidget(self.comments_scroll)
        root.addWidget(self.comments_section, 1)

        # ---- 底部按钮
        buttons = QHBoxLayout()
        buttons.addStretch()

        self.dl_btn = QPushButton("⬇ 下载（含依赖）")
        self.dl_btn.clicked.connect(self._on_download_with_deps)
        buttons.addWidget(self.dl_btn)

        self.queue_btn = QPushButton("＋ 加入队列")
        self.queue_btn.setProperty("secondary", True)
        self.queue_btn.clicked.connect(self._on_queue)
        buttons.addWidget(self.queue_btn)

        close_btn = QPushButton("关闭")
        close_btn.setProperty("secondary", True)
        close_btn.clicked.connect(self.close)
        buttons.addWidget(close_btn)

        # Steam 社区详情页链接（需求：详情页尾端加上具体网址）
        self.web_link = QLabel(
            f'<a href="https://steamcommunity.com/sharedfiles/filedetails/'
            f'?id={self.item.publishedfileid}">🌐 在 Steam 社区查看</a>'
        )
        self.web_link.setOpenExternalLinks(True)
        self.web_link.setStyleSheet("color:#7c5cff;")
        self.web_link.setToolTip(
            "https://steamcommunity.com/sharedfiles/filedetails/"
            f"?id={self.item.publishedfileid}"
        )
        buttons.addWidget(self.web_link)
        root.addLayout(buttons)

        # 已安装则禁用下载按钮
        if self._installed(self.item.publishedfileid):
            self.dl_btn.setText("✓ 已在库")
            self.dl_btn.setEnabled(False)

    def _make_scroll_area(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        scroll.setWidget(host)
        return scroll, host, layout

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#9aa0aa; font-size:12px; font-weight:600; border:none; padding:2px 0;"
        )
        return lbl

    def _meta_html(self) -> str:
        it = self.item
        parts = [
            f"订阅 <b>{it.subscriptions:,}</b>" if it.subscriptions else "订阅 -",
            f"大小 <b>{it.file_size / 1024 / 1024:.1f} MB</b>" if it.file_size else "大小未知",
        ]
        ts = it.time_updated or it.time_created
        when = _fmt_timestamp(str(ts)) if ts else ""
        parts.append(f"更新 <b>{when}</b>" if when else "更新时间未知")
        if it.appid:
            parts.append(f"AppID <b>{html_module.escape(str(it.appid))}</b>")
        return (
            "<span style='color:#9aa0aa;'>"
            + "  ·  ".join(parts)
            + "</span>"
        )

    def _render_tags(self, tags: list[str]) -> None:
        self.tags_layout.clear()
        for tag in (tags or [])[:16]:
            chip = QFrame()
            chip.setStyleSheet(
                "QFrame { background:#2d333b; border:1px solid #343a44;"
                " border-radius:9px; }"
                "QFrame:hover { border-color:#7c5cff; }"
            )
            cl = QHBoxLayout(chip)
            cl.setContentsMargins(8, 2, 8, 2)
            cl.setSpacing(0)
            lbl = QLabel(
                f'<a href="tag:{html_module.escape(tag)}" '
                f'style="color:#9cc0f0;text-decoration:none;">'
                f'#{html_module.escape(tag)}</a>'
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.setToolTip(f"点击按标签「{tag}」筛选该游戏的 mod")
            lbl.linkActivated.connect(
                lambda link, t=tag: self.search_requested.emit("tag", t)
            )
            lbl.setStyleSheet(
                "color:#9cc0f0; font-size:11px; border:none; background:transparent;"
            )
            cl.addWidget(lbl)
            self.tags_layout.addWidget(chip)
        if not tags:
            hint = QLabel("暂无标签")
            hint.setStyleSheet("color:#8a909a; font-size:11px; border:none;")
            self.tags_layout.addWidget(hint)

    # --------------------------------------------------------------- 数据填充
    def set_description(self, text: str) -> None:
        """填充简介（普通文本或富文本，保留换行）。"""
        self.desc_edit.setHtml(_to_html(text))

    def set_creator(self, name: str) -> None:
        """详情页解析出真实作者昵称后回填（bug9）。"""
        name = (name or "").strip()
        if not name:
            return
        self.item.creator_name = name
        # 刷新作者标签（点击仍可搜索该作者的其他 mod）
        from PySide6.QtWidgets import QLabel as _QLabel

        self.author_label.setText(
            f"<span style='color:#9aa0aa;'>作者：</span>"
            f"<a href='author:{html_module.escape(name)}' "
            f"style='color:#7c5cff;text-decoration:none;'>"
            f"{html_module.escape(name)}</a>"
        )
        self.author_label.setToolTip(f"点击搜索作者「{name}」的其他 mod")
        self.author_label.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            self.author_label.linkActivated.disconnect()
        except RuntimeError:
            pass
        self.author_label.linkActivated.connect(
            lambda _l, n=str(name): self.search_requested.emit("author", n)
        )

    def set_comments(self, comments) -> None:
        """填充评论列表；空列表显示友好占位。"""
        self._comments = [_norm_comment(c) for c in (comments or [])]
        self._comments_loaded = True
        self._render_comments()

    def set_comment_count(self, total: int) -> None:
        """在折叠区标题上显示评论总数（收起状态下也能看到计数）。"""
        if total > 0:
            self.comments_section.set_title(f"💬 评论（{total}）")

    def set_dependencies(self, dependencies) -> None:
        """填充前置依赖（每项 (id, title) / dict / WorkshopItem 皆可）。"""
        self._deps = [_norm_dep(d) for d in (dependencies or [])]
        self._deps_loaded = True
        self._render_deps()

    def set_conflicts(self, conflicts) -> None:
        """填充冲突列表；非空时显示黄/红警告区。"""
        self._conflicts = [_norm_conflict(c) for c in (conflicts or [])]
        self._render_conflicts()

    def show_error(self, msg: str) -> None:
        """显示加载失败提示（不崩 UI）。"""
        self.error_label.setText(f"⚠ {msg}")
        self.error_label.setVisible(True)

    # --------------------------------------------------------------- 渲染
    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_comments(self) -> None:
        self._clear_layout(self.comments_layout)
        if not self._comments:
            self.comments_placeholder.setText(
                "暂无评论" if self._comments_loaded else "评论加载中…"
            )
            self.comments_placeholder.setStyleSheet("color:#8a909a; padding:12px;")
            self.comments_layout.addWidget(self.comments_placeholder)
            return
        for c in self._comments:
            self.comments_layout.addWidget(CommentWidget(c))
        self.comments_layout.addStretch()

    def _render_deps(self) -> None:
        self._clear_layout(self.deps_layout)
        if not self._deps:
            self.deps_placeholder.setText(
                "暂无前置依赖" if self._deps_loaded else "前置依赖加载中…"
            )
            self.deps_placeholder.setStyleSheet("color:#8a909a; padding:12px;")
            self.deps_layout.addWidget(self.deps_placeholder)
            return
        for dep_id, title in self._deps:
            row = DepRowWidget(dep_id, title, installed=self._installed(dep_id))
            row.download_clicked.connect(self._download_dep)
            row.search_clicked.connect(
                lambda t: self.search_requested.emit("text", t)
            )
            self.deps_layout.addWidget(row)
        self.deps_layout.addStretch()

    def _render_conflicts(self) -> None:
        self._clear_layout(self.conflict_list_layout)
        if not self._conflicts:
            self.conflict_frame.setVisible(False)
            return
        severe = any((cid or title) and "冲突" in reason for _cid, title, reason
                     in self._conflicts for cid in [_cid])
        self.conflict_frame.setStyleSheet(
            "QFrame { background:#3a2c12; border:1px solid #8a6d1f; border-radius:6px; }"
            if not severe else
            "QFrame { background:#3d1c1c; border:1px solid #a04040; border-radius:6px; }"
        )
        for cid, title, reason in self._conflicts:
            line = QLabel(
                f"<b style='color:#ffd166;'>{html_module.escape(title or cid)}</b>"
                + (f"<span style='color:#cbb27a;'> — {html_module.escape(reason)}</span>"
                   if reason else "")
            )
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setWordWrap(True)
            line.setStyleSheet("border:none; background:transparent;")
            self.conflict_list_layout.addWidget(line)
        self.conflict_frame.setVisible(True)

    # --------------------------------------------------------------- 图片
    def _start_image_load(self) -> None:
        url = self.item.preview_url or ""
        if not url:
            self._show_image_placeholder("暂无预览图")
            return
        self._show_image_placeholder("图片加载中…")
        self._image_worker = PreviewImageWorker(
            url, width=self.PREVIEW_W, height=self.PREVIEW_H,
            api=self.api, parent=self,
        )
        self._image_worker.pixmap_ready.connect(self.set_preview_pixmap)
        self._image_worker.failed.connect(self._on_image_failed)
        self._image_worker.start()

    def _show_image_placeholder(self, text: str) -> None:
        # 先清空 pixmap（QLabel 设空 pixmap 会同时清掉文本），再设置占位文字
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(text)

    @Slot(QPixmap)
    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        """主线程：设置预览图（按比例缩放）。"""
        if pixmap is None or pixmap.isNull():
            self._on_image_failed("图片为空")
            return
        scaled = pixmap.scaled(
            self.PREVIEW_W, self.PREVIEW_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    @Slot(str)
    def _on_image_failed(self, reason: str) -> None:
        log.debug("详情页预览图占位: %s", reason)
        self._show_image_placeholder("预览图加载失败")

    # --------------------------------------------------------------- 下载
    def _installed(self, item_id: str) -> bool:
        if self.library is None or not item_id:
            return False
        try:
            return self.library.get(item_id) is not None
        except Exception:  # noqa: BLE001
            return False

    @Slot(str, str)
    def _download_dep(self, dep_id: str, title: str) -> None:
        """下载单个前置依赖。"""
        if not dep_id:
            return
        try:
            appid = self.item.appid or ""
            di = WorkshopItem(publishedfileid=dep_id, appid=appid, title=title)
            if self.downloader is not None:
                self.downloader.enqueue(di, appid)
            self.queue_requested.emit(dep_id)
        except Exception as e:  # noqa: BLE001
            log.exception("下载依赖失败")
            self.show_error(f"下载依赖失败: {e}")

    @Slot()
    def _on_download_with_deps(self) -> None:
        """下载本 mod 及其全部前置依赖（依赖在前）。"""
        try:
            appid = self.item.appid or ""
            skipped = 0
            if self.downloader is not None:
                for dep_id, title in self._deps:
                    if self._installed(dep_id):
                        skipped += 1
                        continue
                    di = WorkshopItem(publishedfileid=dep_id, appid=appid, title=title)
                    self.downloader.enqueue(di, appid)
                self.item.dependencies = [d[0] for d in self._deps]
                self.downloader.enqueue(self.item, appid)
            self.download_requested.emit(self.item.publishedfileid)
            self.dl_btn.setText("✓ 已加入队列")
            self.dl_btn.setEnabled(False)
            log.info(
                "详情页下载（含依赖）：%s + %d 依赖（跳过已安装 %d）",
                self.item.publishedfileid, len(self._deps), skipped,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("详情页下载失败")
            self.show_error(f"下载失败: {e}")

    @Slot()
    def _on_queue(self) -> None:
        """仅把本 mod 加入下载队列。"""
        try:
            if self.downloader is not None:
                self.downloader.enqueue(self.item, self.item.appid or "")
            self.queue_requested.emit(self.item.publishedfileid)
        except Exception as e:  # noqa: BLE001
            log.exception("加入队列失败")
            self.show_error(f"加入队列失败: {e}")

    # --------------------------------------------------------------- 生命周期
    def closeEvent(self, event) -> None:
        try:
            if self._image_worker is not None and self._image_worker.isRunning():
                self._image_worker.wait(1500)
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
