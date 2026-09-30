"""Workshop browse tab: pick a game → search / tag filter / sort → item cards → download (工坊浏览页).

The largest GUI module: game picker with suggestions (联想下拉) and Enter handling,
tag bar, pagination, mod cards with batch selection, dependency-aware download,
detail dialog, hover prefetch (yielding to user clicks, t15), URL import, and conflict badges.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from swdm.core import all_games, game_name
from swdm.core.game_dirs import game_install_dir, set_game_dir
from swdm.core.games import add_custom
from swdm.core.logger import get_logger
from swdm.core.paths import LIBRARY_DIR
from swdm.core.steam_api import SteamAPI
from swdm.gui.detail_dialog import DetailPageWorker, ModDetailDialog
from swdm.gui.tag_bar import TagBar
from swdm.gui.widgets import LoadingOverlay, SmoothScrollBar
from swdm.gui.workers import BrowseWorker, ImageLoader

log = get_logger("swdm.gui.workshop")


class _TagsFetchWorker(QThread):
    """后台拉取某游戏的可用标签（走浏览页侧栏）。"""

    tags_ready = Signal(list)
    failed = Signal(str)

    def __init__(self, api, appid: str) -> None:
        super().__init__()
        self._api = api
        self._appid = str(appid)

    def run(self) -> None:
        try:
            from swdm.core.page_parser import parse_available_tags_with_counts

            html = self._api._community_get(
                "/workshop/browse/", {"appid": self._appid}
            )
            tags = parse_available_tags_with_counts(html)
            self.tags_ready.emit(tags)
        except Exception as e:  # noqa: BLE001
            log.debug("标签拉取失败", exc_info=True)
            self.failed.emit(f"{type(e).__name__}: {e}")


SORT_OPTIONS = [
    ("trend", "热门趋势"),
    ("mostrecent", "最新发布"),
    ("mostsubscribed", "最多订阅"),
    ("toprated", "评价最高"),
    ("mostviews", "最多浏览"),
    ("favorited", "最多收藏"),
]


class _ElidedLabel(QLabel):
    """单行省略标签（修复字符挤压）。

    根因：QLabel 在 wordWrap=False 时 minimumSizeHint = 全文宽度，
    会把卡片布局顶到文本宽度；当滚动区视口更窄时布局压不下来，
    文本被裁切/挤压。重写 minimumSizeHint 让宽度可压缩，再在
    实际宽度上做右省略（完整文本保留到 tooltip）。
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(False)
        self._full = text
        self._last_w = -1

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize

        h = super().minimumSizeHint().height()
        return QSize(0, h)

    def setFullText(self, text: str) -> None:
        self._full = text
        self._last_w = -1
        self._relide(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relide(event.size().width())

    def _relide(self, w: int) -> None:
        if w <= 0 or w == self._last_w:
            return
        self._last_w = w
        m = self.fontMetrics()
        if m.horizontalAdvance(self._full) <= w:
            if self.text() != self._full:
                self.setText(self._full)
            self.setToolTip("")
            return
        elided = m.elidedText(self._full, Qt.TextElideMode.ElideRight, w)
        if self.text() != elided:
            self.setText(elided)
        self.setToolTip(self._full)


class ModCardWidget(QWidget):
    """单个 mod 卡片：预览图 + 标题 + 元信息 + 下载按钮。"""

    download_requested = Signal(str)          # publishedfileid
    detail_requested = Signal(str)
    check_toggled = Signal(str, bool)         # (publishedfileid, checked)
    hover_entered = Signal(str)               # 鼠标进入卡片（用于预取详情）

    def __init__(self, item, parent=None) -> None:
        super().__init__(parent)
        self.item = item
        self._build(item)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def isChecked(self) -> bool:
        return self.check_box.isChecked()

    def setChecked(self, on: bool) -> None:
        self.check_box.setChecked(on)

    def enterEvent(self, event) -> None:
        """鼠标进入卡片：通知外部可预取详情（停留超过阈值才有意义）。"""
        self.hover_entered.emit(self.item.publishedfileid)
        super().enterEvent(event)

    def _build(self, it) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        # 勾选框内嵌卡片最左侧（修 QListWidgetItem checkbox 被
        # setItemWidget 遮挡、点不到的问题）
        self.check_box = QCheckBox()
        self.check_box.setFixedWidth(20)
        self.check_box.setToolTip("勾选该 mod")
        self.check_box.toggled.connect(
            lambda on: self.check_toggled.emit(self.item.publishedfileid, on)
        )
        lay.addWidget(self.check_box)

        self.thumb = QLabel()
        self.thumb.setFixedSize(96, 96)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("background:#262b32; border-radius:4px;")
        self.thumb.setText("🖼")
        lay.addWidget(self.thumb)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        mid_host = QWidget()
        mid_host.setLayout(mid)
        mid_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title = _ElidedLabel(it.title or f"mod {it.publishedfileid}")
        title.setObjectName("cardTitle")
        title.setStyleSheet("font-weight:600; font-size:13px; color:#e8ecf2;")
        # 字符挤压修复：不换行时必须省略，否则长标题溢出挤压相邻控件
        title.setFixedHeight(20)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        mid.addWidget(title)

        self.meta = _ElidedLabel(self._meta_text(it))
        self.meta.setStyleSheet("color:#8a909a; font-size:11px;")
        self.meta.setTextFormat(Qt.TextFormat.PlainText)
        mid.addWidget(self.meta)

        tags = _ElidedLabel("  ".join(f"[{t}]" for t in it.tags[:5]))
        tags.setStyleSheet("color:#5f8fd0; font-size:10px;")
        tags.setFixedHeight(16)
        tags.setTextFormat(Qt.TextFormat.PlainText)
        mid.addWidget(tags)
        lay.addWidget(mid_host, 1)
        self._mid_layout = mid
        self._mid_widget = mid_host

        right = QVBoxLayout()
        right.setSpacing(6)
        # bug8：下载按钮内嵌迷你进度条，下载中变进度显示
        self.dl_progress = QProgressBar()
        self.dl_progress.setFixedWidth(92)
        self.dl_progress.setFixedHeight(18)
        self.dl_progress.setRange(0, 100)
        self.dl_progress.setValue(0)
        self.dl_progress.setTextVisible(True)
        self.dl_progress.setFormat("下载中 %p%")
        self.dl_progress.setVisible(False)
        self.dl_btn = QPushButton("⬇ 下载")
        self.dl_btn.setFixedWidth(92)
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.item.publishedfileid))
        right.addWidget(self.dl_btn)
        right.addWidget(self.dl_progress)

        info_btn = QPushButton("详情")
        info_btn.setProperty("secondary", True)
        info_btn.setFixedWidth(92)
        info_btn.clicked.connect(lambda: self.detail_requested.emit(self.item.publishedfileid))
        right.addWidget(info_btn)
        lay.addLayout(right)

    @staticmethod
    def _meta_text(it) -> str:
        size_mb = it.file_size / 1024 / 1024
        # 作者：优先自定义昵称；仅有 steamid64 时不显示数字串（避免误认成编号）
        author = it.creator_name or ""
        parts = [
            f"#{it.publishedfileid}",   # mod 编号（bug11）
            f"订阅 {it.subscriptions:,}" if it.subscriptions else "订阅 -",
            f"{size_mb:.1f} MB" if it.file_size else "大小未知",
            f"作者 {author}" if author else "",
        ]
        return "  ·  ".join(p for p in parts if p)

    def set_download_progress(self, pct: int) -> None:
        """卡片内迷你进度条：pct<0 显示不确定忙碌动画（bug8）。"""
        if pct < 0:
            self.dl_progress.setRange(0, 0)
            self.dl_progress.setTextVisible(False)
        else:
            self.dl_progress.setRange(0, 100)
            self.dl_progress.setTextVisible(True)
            self.dl_progress.setValue(pct)
        self.dl_btn.setVisible(False)
        self.dl_progress.setVisible(True)

    def mark_downloaded(self) -> None:
        self.dl_progress.setVisible(False)
        self.dl_btn.setText("✓ 已在库")
        self.dl_btn.setEnabled(False)
        self.dl_btn.setVisible(True)

    def set_thumbnail(self, pixmap) -> None:
        if pixmap is not None and not pixmap.isNull():
            self.thumb.setPixmap(
                pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )

    def resizeEvent(self, event) -> None:
        """窗口缩放时重算文本省略（修复字符挤压）。"""
        super().resizeEvent(event)
        # _ElidedLabel 自身在 resizeEvent 里做省略，这里只需触发一次
        for i in range(self._mid_layout.count()):
            item = self._mid_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, _ElidedLabel):
                w._last_w = -1
                w._relide(w.width())

    def _apply_elide(self) -> None:
        """强制重算所有省略标签（填充后调用一次，确保即时正确）。"""
        for i in range(self._mid_layout.count()):
            item = self._mid_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, _ElidedLabel):
                w._last_w = -1
                w._relide(w.width())


class WorkshopTab(QWidget):
    """工坊浏览主页面。"""

    # 请求主窗口切换到下载页（点击下载后给用户即时反馈，bug1）
    show_downloads = Signal()

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.svc = services
        self._items: list = []
        self._page = 1
        self._worker: BrowseWorker | None = None
        # 在途请求未完成时用户又操作了，标记待执行（手感优化：不丢弃操作）
        self._pending_refresh = False
        self._worker_gen = 0          # O6：当前请求代际号
        # 每代际请求使用的搜索词（_on_items_ready 据此做标题命中率判定）
        self._search_by_gen: dict[int, str] = {}
        # O1：preview_url → (card...) 索引，图片回调 O(1) 定位卡片
        self._url_index: dict[str, list] = {}
        # 勾选的 mod id 集合（左侧勾选框语义，替代高亮选择）
        self._checked_ids: set[str] = set()
        # 详情弹窗与其后台解析 worker（非模态弹窗需防 GC）
        self._detail_dialog: ModDetailDialog | None = None
        self._detail_worker: "DetailPageWorker | None" = None
        # 去抖定时器：快速操作时只执行最后一次列表请求
        from PySide6.QtCore import QTimer

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_list)
        # 悬停预取定时器：鼠标在卡片上停留 400ms 才预取详情页
        # （避免快速划过时狂发请求；预取结果进 5 分钟缓存，点击秒开）
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(400)
        self._prefetch_timer.timeout.connect(self._do_prefetch_detail)
        self._prefetch_id: str | None = None
        self._prefetching: set[str] = set()
        # B2：下一页预取定时器——当前页渲染完后延迟预取下一页，
        # 用户点"下一页"时直接命中缓存（零网络、秒切）
        self._nextpage_timer = QTimer(self)
        self._nextpage_timer.setSingleShot(True)
        self._nextpage_timer.setInterval(800)
        self._nextpage_timer.timeout.connect(self._do_prefetch_next_page)
        self._nextpage_prefetching = False
        self._nextpage_thread: threading.Thread | None = None
        self.image_loader = ImageLoader()
        self.image_loader.bus.loaded.connect(self._on_image_loaded)
        self._build()
        self._load_games()
        # 订阅下载进度：驱动卡片迷你进度条（bug8）；回调在子线程，
        # 经 Qt 信号桥接回主线程
        from swdm.gui.workers import DownloadEventBridge

        self._wt_bridge = DownloadEventBridge()
        self._wt_bridge.progress.connect(self._on_job_progress)
        self._wt_bridge.finished.connect(self._on_job_finished)
        try:
            self.svc.downloader.add_listener(
                progress=self._wt_bridge.progress.emit,
                finished=self._wt_bridge.finished.emit,
            )
        except Exception:  # noqa: BLE001
            pass

    def _on_job_progress(self, job) -> None:
        """下载进度 → 更新对应卡片的迷你进度条（bug8）。"""
        from swdm.core.downloader import JobStatus

        if job.status != JobStatus.RUNNING:
            return
        card = self._card_by_id(job.id)
        if card is not None:
            card.set_download_progress(job.percent)

    def _on_job_finished(self, job) -> None:
        """下载完成/失败 → 卡片按钮恢复或标记已入库（bug8）。"""
        from swdm.core.downloader import JobStatus

        if job.status != JobStatus.SUCCESS:
            card = self._card_by_id(job.id)
            if card is not None:
                card.dl_progress.setVisible(False)
                card.dl_btn.setVisible(True)
            return
        card = self._card_by_id(job.id)
        if card is not None:
            card.mark_downloaded()

    def _card_by_id(self, item_id: str):
        for card in self._cards():
            if card.item.publishedfileid == item_id:
                return card
        return None

    # --------------------------------------------------------------- UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 工具栏第一行：游戏选择 + 收藏
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("游戏:"))
        self.game_combo = QComboBox()
        self.game_combo.setEditable(True)
        self.game_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.game_combo.setMinimumWidth(280)
        self.game_combo.setEditable(True)   # bug8：可输入游戏名搜索（免 AppID）
        self.game_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)
        # 联想输入：防抖 350ms + 在途取消（版本号）
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        # 防抖 350→250ms：本地匹配已即时响应，网络部分再快一点
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._do_game_search)
        self._search_version = 0
        self._search_worker = None
        self._search_client = None
        self._last_search_pairs: list[tuple[str, str]] = []
        # 回车确认游戏时若联想结果尚未到达，置标记等结果到达后自动选中第一项
        self._pending_enter_select = False
        # 技术债：搜索命中熔断冷却时记下待发词，冷却结束后自动重发一次
        # （否则用户输入的词在冷却期内被静默丢弃，联想再无反应）
        self._pending_search_term: str = ""
        self._search_retry_timer = QTimer(self)
        self._search_retry_timer.setSingleShot(True)
        self._search_retry_timer.timeout.connect(self._retry_pending_search)
        # 每代际请求的标签过滤参数：结果到达后据此做客户端精确过滤
        # （服务端 requiredtags 只是近似匹配）
        self._tags_by_gen: dict[int, list[str]] = {}
        ed = self.game_combo.lineEdit()
        if ed is not None:
            ed.textEdited.connect(self._on_search_text_edited)
            # bug2：输入游戏名后按回车，等效于选中下拉项，触发刷新+标签拉取
            ed.returnPressed.connect(self._on_game_enter)
        row1.addWidget(self.game_combo, 1)

        # 低频操作（收藏/添加游戏/导入合集）收进"更多"菜单，
        # 避免工具栏按钮堆砌（按上下级整理，常用操作才占首屏）
        self.more_btn = QPushButton("⋯ 更多")
        self.more_btn.setProperty("secondary", True)
        self.more_btn.setToolTip("收藏游戏 / 添加自定义游戏 / 批量粘贴导入链接或 ID")
        more_menu = QMenu(self.more_btn)
        self.fav_action = more_menu.addAction("☆ 收藏游戏")
        self.fav_action.triggered.connect(self._toggle_favorite)
        act_add = more_menu.addAction("＋ 添加自定义游戏…")
        act_add.triggered.connect(self._add_custom_game)
        act_import = more_menu.addAction("🔗 批量粘贴导入…")
        act_import.triggered.connect(self._import_url)
        self.more_btn.setMenu(more_menu)
        row1.addWidget(self.more_btn)

        # 当前游戏的 mod 下载目录（可单独修改）
        self.game_dir_label = QLabel()
        self.game_dir_label.setStyleSheet("color: #9a9aa5; font-size: 12px;")
        self.game_dir_label.setMaximumWidth(300)
        row1.addWidget(self.game_dir_label)
        self.game_dir_btn = QPushButton("📂 目录…")
        self.game_dir_btn.setProperty("secondary", True)
        self.game_dir_btn.setToolTip("修改该游戏的 mod 下载目录")
        self.game_dir_btn.clicked.connect(self._change_game_dir)
        row1.addWidget(self.game_dir_btn)
        root.addLayout(row1)

        # 工具栏第二行：搜索 + 排序 + 标签
        row2 = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索 mod 关键词或作者名（回车）…")
        self.search_edit.returnPressed.connect(self._refresh_list)
        row2.addWidget(self.search_edit, 2)

        self.sort_combo = QComboBox()
        for v, t in SORT_OPTIONS:
            self.sort_combo.addItem(t, v)
        # B1（UX 审计+QA 双重发现）：切换排序维度后列表不刷新，
        # 用户必须再点搜索。接到 currentIndexChanged 立即刷新。
        self.sort_combo.currentIndexChanged.connect(
            lambda _idx: self._refresh_list())
        row2.addWidget(self.sort_combo)

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("标签过滤（逗号分隔）")
        self.tag_edit.setMaximumWidth(200)
        row2.addWidget(self.tag_edit)

        self.tags_btn = QPushButton("🏷 标签…")
        self.tags_btn.setProperty("secondary", True)
        self.tags_btn.setToolTip("拉取该游戏可供筛选的标签")
        self.tags_btn.clicked.connect(self._pick_tags)
        row2.addWidget(self.tags_btn)

        search_btn = QPushButton("🔍 搜索")
        search_btn.clicked.connect(self._refresh_list)
        row2.addWidget(search_btn)

        self.anon_label = QLabel()
        self.anon_label.setStyleSheet("color:#5f8fd0; font-size:11px;")
        row2.addWidget(self.anon_label)
        root.addLayout(row2)

        # 标签栏：搜索栏下方横向滚动，选游戏时自动拉取，单击多选
        self.tag_bar = TagBar(self)
        self.tag_bar.selection_changed.connect(self._on_tag_selection_changed)
        root.addWidget(self.tag_bar)

        # 列表（QScrollArea + 卡片直插：避免 QListWidget+setItemWidget
        # 的勾选框遮挡、翻页 itemWidget 竞态问题）
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_content = QWidget()
        self.list_layout = QVBoxLayout(self.list_content)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.list_scroll.setWidget(self.list_content)
        # 平滑滚动 + 加载遮罩
        sc_bar = SmoothScrollBar.install_on(self.list_scroll)
        # 滚轮一次只滚约半行（默认一整行，目不暇接）
        sc_bar.setSingleStep(44)
        self._list_overlay = LoadingOverlay(self.list_scroll)
        root.addWidget(self.list_scroll, 1)

        # 分页与批量操作
        row3 = QHBoxLayout()
        self.prev_btn = QPushButton("← 上一页")
        self.prev_btn.setProperty("secondary", True)
        # 第 1 页时上一页禁用（未加载完成前也要保持禁用，
        # 否则点击无反应让用户以为坏了）
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_page)
        row3.addWidget(self.prev_btn)

        self.page_label = QLabel("第 1 页")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(100)
        row3.addWidget(self.page_label)

        self.next_btn = QPushButton("下一页 →")
        self.next_btn.setProperty("secondary", True)
        self.next_btn.clicked.connect(self._next_page)
        row3.addWidget(self.next_btn)

        row3.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setProperty("secondary", True)
        self.select_all_btn.clicked.connect(self._check_all)
        row3.addWidget(self.select_all_btn)

        self.dl_selected_btn = QPushButton("⬇ 下载勾选")
        self.dl_selected_btn.clicked.connect(self._download_selected)
        row3.addWidget(self.dl_selected_btn)
        root.addLayout(row3)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#8a909a; font-size:11px;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------- 游戏列表
    def _load_games(self) -> None:
        favs = set(self.svc.config.get("favorites_games") or [])
        games = all_games()
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        if favs:
            self.game_combo.addItem("★ 收藏", "")
            for appid in favs:
                self.game_combo.addItem(f"★ {game_name(appid)}", appid)
            self.game_combo.insertSeparator(self.game_combo.count())
        for g in games:
            self.game_combo.addItem(g["name"], g["appid"])
        self.game_combo.blockSignals(False)
        # 默认选 Garry's Mod
        idx = self.game_combo.findData("4000")
        if idx >= 0:
            self.game_combo.setCurrentIndex(idx)
        self._update_game_dir_label()

    def _current_appid(self) -> str:
        """解析当前游戏 AppID（bug2：editable combo 输入文字时
        currentData 为空，需多层回退）。"""
        text = self.game_combo.currentText().strip()
        idx = self.game_combo.currentIndex()
        # editable combo：用户输入新文字时 currentIndex 仍指向上一选中项，
        # 其 itemData 与当前输入无关（u2：直接采用会把上一个游戏当成当前
        # 游戏，导致"输入其他游戏一直显示未识别/识别错"）。
        # 只有下拉项文本与输入文本一致时，itemData 才可信。
        if idx >= 0:
            item_text = self.game_combo.itemText(idx).split("(")[0].strip()
            d = self.game_combo.itemData(idx)
            if d and item_text.lower() == text.lower():
                return str(d)
        if text.isdigit():
            return text
        # 下拉项文本形如 "Name  (appid)"：按名字匹配下拉项
        low = text.lower()
        for i in range(self.game_combo.count()):
            if self.game_combo.itemText(i).split("(")[0].strip().lower() == low:
                d = self.game_combo.itemData(i)
                if d:
                    return str(d)
        # 最近一次联想结果缓存
        for appid, name in getattr(self, "_last_search_pairs", []):
            if name.strip().lower() == low:
                return str(appid)
        # 内置游戏表
        for g in all_games():
            if g["name"].lower() == low:
                return g["appid"]
        return ""

    @staticmethod
    def _match_score(name: str, text: str) -> int:
        """名称与输入的匹配度：精确 3 > 开头 2 > 包含 1 > 不匹配 0。"""
        n = (name or "").strip().lower()
        t = text.strip().lower()
        if not n or not t:
            return 0
        if n == t:
            return 3
        if n.startswith(t):
            return 2
        if t in n:
            return 1
        return 0

    def _best_guess_appid(self, text: str) -> str:
        """精确匹配失败后的模糊回退：取联想结果/内置表中最佳匹配项。"""
        pairs = getattr(self, "_last_search_pairs", [])
        best = max(
            ((self._match_score(n, text), str(a)) for a, n in pairs),
            default=(0, ""),
        )
        if best[0] > 0:
            return best[1]
        for g in all_games():
            if self._match_score(g["name"], text) > 0:
                return g["appid"]
        return ""

    def _select_game_by_appid(self, appid: str, name: str = "") -> None:
        """选中某游戏（下拉没有则追加），选中即触发 _on_game_changed。"""
        idx = self.game_combo.findData(appid)
        if idx < 0:
            self.game_combo.addItem(name or appid, appid)
            idx = self.game_combo.count() - 1
        if idx == self.game_combo.currentIndex():
            # 已在该游戏上：仍触发一次刷新（用户回车=重新加载语义）
            self._on_game_changed(idx)
        else:
            self.game_combo.setCurrentIndex(idx)

    def _on_game_enter(self) -> None:
        """输入框回车：解析 AppID 后按"切换游戏"处理（bug1/2：
        editable combo 输入文字不触发 currentIndexChanged，导致
        标签不更新、列表提示"请先输入游戏 AppID"）。"""
        text = self.game_combo.currentText().strip()
        appid = self._current_appid() or self._best_guess_appid(text)
        if appid:
            self._select_game_by_appid(appid, text)
            return
        if text:
            # 联想结果尚未到达（网络慢/熔断）：本地有匹配立即选，
            # 否则触发一次搜索，结果到达后自动选中第一项
            # （回车语义=确认第一个候选）
            local = self._local_game_matches(text)
            if local:
                self._select_game_by_appid(str(local[0][0]), local[0][1])
                return
            self._pending_enter_select = True
            self._search_timer.stop()
            self._do_game_search()
            self.status_label.setText("正在搜索游戏，稍候…")
            return
        self.status_label.setText("未识别该游戏，请从下拉列表选择，或直接输入 AppID")

    # --------------------------------------------------- 游戏名搜索联想（bug8）
    def _ranked_matches(self, text: str, pairs: list) -> list:
        """按匹配度排序（精确 > 开头 > 包含），保证第一项是最佳候选。"""
        return sorted(pairs, key=lambda a_n: -self._match_score(a_n[1], text))

    def _on_search_text_edited(self, text: str) -> None:
        """输入游戏名时：本地匹配立即出结果（零延迟），
        网络搜索防抖 250ms 后跑（storesearch 接口，免 AppID）。"""
        text = (text or "").strip()
        # 即时本地匹配：输入第 1 个字符就有反应（用户反馈：唤醒不及时）
        if text:
            local = self._ranked_matches(text, self._local_game_matches(text))
            if local:
                self._fill_search_results(local[:8], is_local=True)
            else:
                # 无本地匹配：关掉上一次残留的下拉，避免候选与输入不符
                self.game_combo.hidePopup()
        self._search_timer.start()

    def _do_game_search(self) -> None:
        text = self.game_combo.currentText().strip()
        if len(text) < 2:
            return
        # 本地内置游戏优先命中（零请求、即时）
        local = self._ranked_matches(text, self._local_game_matches(text))
        self._fill_search_results(local, is_local=True)
        # 本地有足够结果仍发后台请求补全（热门游戏优先权威结果）
        self._search_version += 1
        version = self._search_version
        if self._search_client is None:
            from swdm.core.game_search import GameSearchClient

            self._search_client = GameSearchClient()
        client = self._search_client

        # 技术债：熔断冷却期内的请求会被静默丢弃。记下待发词，
        # 冷却结束后由 _search_retry_timer 自动重发一次同一词，
        # 避免用户输入石沉大海（本地结果仍在，网络联想会补上）
        try:
            in_cooldown = client.is_in_cooldown()
        except Exception:  # noqa: BLE001
            in_cooldown = False
        if in_cooldown:
            self._pending_search_term = text
            try:
                remaining = client.cooldown_remaining()
            except Exception:  # noqa: BLE001
                remaining = 0.0
            self._search_retry_timer.start(int((remaining + 0.5) * 1000))
            return

        class _SearchWorker(QThread):
            ready = Signal(list, int)

            def __init__(self, c, t, v) -> None:
                super().__init__()
                self._c, self._t, self._v = c, t, v

            def run(self) -> None:
                try:
                    res = self._c.search(self._t)
                    self.ready.emit(res, self._v)
                except Exception:  # noqa: BLE001
                    self.ready.emit([], self._v)

        self._search_worker = _SearchWorker(client, text, version)
        self._search_worker.ready.connect(
            lambda res, v: self._on_search_ready(res, v)
        )
        self._search_worker.start()

    def _retry_pending_search(self) -> None:
        """冷却结束后重发一次待选词（仅当输入框仍是那个词）。"""
        term = self._pending_search_term
        if not term:
            return
        if self.game_combo.currentText().strip() != term:
            # 用户已改词，旧词不再重发（_do_game_search 会处理新词）
            self._pending_search_term = ""
            return
        self._pending_search_term = ""
        self._do_game_search()

    def _local_game_matches(self, text: str) -> list:
        """本地游戏库匹配（内置 + 收藏 + 自定义），零网络请求。"""
        t = text.lower()
        out = []
        for g in all_games():
            appid, name = str(g.get("appid", "")), str(g.get("name", ""))
            if t in name.lower() or t in appid:
                out.append((appid, name))
        for appid in (self.svc.config.get("favorites_games") or []):
            n = game_name(appid)
            if n and (t in n.lower() or t in str(appid)):
                out.append((appid, n))
        seen, uniq = set(), []
        for appid, name in out:
            if appid not in seen:
                seen.add(appid)
                uniq.append((appid, name))
        return uniq[:12]

    def _fill_search_results(self, results, is_local: bool = False) -> None:
        """填充联想候选到下拉框（不清空用户输入，选中状态与输入文本一致）。"""
        ed = self.game_combo.lineEdit()
        if ed is None:
            return
        cur_text = ed.text()
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for appid, name in results:
            self.game_combo.addItem(f"{name}  ({appid})", appid)
        # clear()+addItem 会使 combo 内部 currentIndex 变为 0，
        # currentText 与 lineEdit 文本不一致（回车/currentData 会错读）；
        # 显式置 -1：无选中项，当前游戏仍以 lineEdit 文本为准
        self.game_combo.setCurrentIndex(-1)
        self.game_combo.blockSignals(False)
        ed.setText(cur_text)
        # 本地/网络结果都弹下拉，体感一致（旧逻辑本地结果不弹）
        if results:
            self.game_combo.showPopup()

    def _on_search_ready(self, results, version: int) -> None:
        # 在途取消：版本不匹配说明已有更新的搜索，丢弃本次结果
        if version != self._search_version:
            return
        # 本次搜索已成功送达，冷却重发的待发词（若有）不再需要
        self._pending_search_term = ""
        ed = self.game_combo.lineEdit()
        if ed is None:
            return
        pairs = [(r.appid, r.name) for r in results]
        # 缓存最近联想结果，供 _current_appid 回退解析（bug2）
        self._last_search_pairs = pairs
        # 合并本地结果去重，按匹配度排序：用户正输入的精确匹配始终第一
        text = ed.text().strip()
        local = self._local_game_matches(text)
        seen = set()
        merged = []
        for a, n in self._ranked_matches(text, local + pairs):
            if a not in seen:
                seen.add(a)
                merged.append((a, n))
        # 回车待选：结果到达自动选中第一项（最佳匹配）
        if getattr(self, "_pending_enter_select", False):
            self._pending_enter_select = False
            if merged:
                self._select_game_by_appid(str(merged[0][0]), merged[0][1])
                return
            self.status_label.setText("未找到该游戏，请检查名称或直接输入 AppID")
            return
        self._fill_search_results(merged[:15])

    def _on_game_changed(self, _idx: int) -> None:
        # 标签按游戏不同：切游戏时必须清除旧游戏的标签选中与过滤参数，
        # 否则列表仍按旧标签过滤、且同名标签会被 set_tags 自动重选（u6）
        self.tag_bar.clear_selection()
        self.tag_edit.setText("")
        self._page = 1
        self._refresh_list()
        self._update_fav_button()
        self._update_anon_label()
        self._update_game_dir_label()
        # 选择游戏时自动拉取标签（不再需要手动点按钮）
        self._fetch_tags()

    def _update_game_dir_label(self) -> None:
        """显示当前游戏的 mod 下载目录（需求：开放游戏目录修改接口）。"""
        appid = self._current_appid()
        if not appid:
            self.game_dir_label.setText("")
            self.game_dir_btn.setEnabled(False)
            return
        d = game_install_dir(appid)
        # 省略显示
        label = "📁 " + (d if len(d) <= 42 else "…" + d[-41:])
        self.game_dir_label.setText(label)
        self.game_dir_label.setToolTip(f"{game_name(appid) or appid} 的 mod 下载目录：\n{d}")
        self.game_dir_btn.setEnabled(True)

    def _change_game_dir(self) -> None:
        """修改当前游戏的 mod 下载目录。"""
        appid = self._current_appid()
        if not appid:
            return
        cur = game_install_dir(appid)
        folder = QFileDialog.getExistingDirectory(
            self, f"选择 {game_name(appid) or appid} 的 mod 下载目录",
            cur or LIBRARY_DIR,
        )
        if not folder:
            return
        set_game_dir(appid, folder)
        self._update_game_dir_label()
        QMessageBox.information(
            self, "已更新",
            f"{game_name(appid) or appid} 的 mod 将下载到：\n{folder}\n\n"
            f"（新下载立即生效；已下载的文件不会移动）",
        )

    def _update_fav_button(self) -> None:
        appid = self._current_appid()
        favs = set(self.svc.config.get("favorites_games") or [])
        is_fav = appid in favs
        self.fav_action.setText("★ 已收藏" if is_fav else "☆ 收藏游戏")

    def _toggle_favorite(self) -> None:
        appid = self._current_appid()
        if not appid:
            return
        favs = list(self.svc.config.get("favorites_games") or [])
        if appid in favs:
            favs.remove(appid)
        else:
            favs.append(appid)
        self.svc.config.set("favorites_games", favs)
        self.svc.config.save()
        self._load_games()
        idx = self.game_combo.findData(appid)
        if idx >= 0:
            self.game_combo.setCurrentIndex(idx)

    def _add_custom_game(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        appid, ok = QInputDialog.getText(self, "添加游戏", "输入游戏的 AppID（数字）：")
        if not ok or not appid.strip().isdigit():
            if ok:
                QMessageBox.warning(self, "提示", "AppID 必须是数字")
            return
        name, ok = QInputDialog.getText(self, "添加游戏", "游戏名称：")
        if not ok or not name.strip():
            return
        add_custom(appid.strip(), name.strip())
        self._load_games()
        idx = self.game_combo.findData(appid.strip())
        if idx >= 0:
            self.game_combo.setCurrentIndex(idx)

    def _update_anon_label(self) -> None:
        if self.svc.auth.is_anonymous():
            self.anon_label.setText("🟢 匿名模式（无需账号）")
        else:
            self.anon_label.setText(f"🔵 已登录：{self.svc.auth.account.username}")

    # ------------------------------------------------------------- 列表加载
    def _refresh_list(self) -> None:
        # 分页 UI 同步放在这里（同步执行）：用户点完翻页立刻看到
        # 页码变化与上一页禁用态，不等去抖定时器和网络回包
        self._page = max(1, self._page)
        self.prev_btn.setEnabled(self._page > 1)
        self.page_label.setText(f"第 {self._page} 页")
        # 去抖：用户快速切换游戏/翻页/搜索时，合并为最后一次请求
        # （Steam 社区按 IP 限流，短时间多次请求会触发 429）
        self._refresh_timer.start(350)

    def _do_refresh_list(self) -> None:
        appid = self._current_appid()
        if not appid:
            self.status_label.setText("请先选择或输入游戏 AppID")
            return
        if self._worker and self._worker.isRunning():
            # 手感优化：不丢弃请求，标记"待执行"，当前请求完成后自动重跑
            # （旧逻辑直接 return，用户快速切游戏时看起来"没反应"）
            self._pending_refresh = True
            self.status_label.setText("排队中：上一次请求完成后自动加载…")
            return
        self._pending_refresh = False
        self._clear_cards()
        self._items = []
        # B2：新请求发出，作废待发的下一页预取（代际+1 已使旧预取无效）
        self._nextpage_timer.stop()
        tags = [t.strip() for t in self.tag_edit.text().split(",") if t.strip()]
        self._worker_gen += 1           # O6：新请求代际+1，旧结果作废
        gen = self._worker_gen
        # 记录本次请求的搜索词：结果到达后据此判定标题命中率
        # （用户可能在加载期间又输入了新词，不能回读 search_edit）
        self._search_by_gen[gen] = self.search_edit.text().strip()
        # 代际单调递增，保留最近若干条足够（旧的已永久作废）
        if len(self._search_by_gen) > 16:
            stale = sorted(self._search_by_gen)[: -16]
            for k in stale:
                self._search_by_gen.pop(k, None)
        # 记录本次请求的标签：服务端 requiredtags 只是近似匹配，
        # 结果到达后按所选标签做客户端精确过滤
        self._tags_by_gen[gen] = tags
        if len(self._tags_by_gen) > 16:
            stale = sorted(self._tags_by_gen)[: -16]
            for k in stale:
                self._tags_by_gen.pop(k, None)
        self._worker = BrowseWorker(
            self.svc.api, appid, page=self._page,
            search=self.search_edit.text().strip(),
            sort=self.sort_combo.currentData(),
            tags=tags,
            generation=gen,
        )
        self._worker.progress.connect(self.status_label.setText)
        self._list_overlay.start("正在加载工坊列表…")
        self._worker.failed.connect(self._on_list_failed)
        self._worker.items_ready.connect(
            lambda items, g=gen: self._on_items_ready(items, g))
        self._worker.items_ready.connect(lambda _items: self._list_overlay.stop())
        self._worker.start()

    def _on_items_ready(self, items: list, gen: int) -> None:
        """O6（net N1）：代际过期则丢弃，防止快速操作时旧结果覆盖新结果。"""
        if gen != self._worker_gen:
            log.info("丢弃过期代际 %s 的结果（当前 %s）", gen, self._worker_gen)
            return
        # 匿名 browse 搜索只匹配标题：0 命中时按作者二次过滤、低命中时提示。
        # enrich 在 worker 线程 emit 前已完成，此处 creator/creator_name 已可用。
        # getattr 兜底：子类/测试桩可能未走完整 _do_refresh_list 初始化
        search_text = getattr(self, "_search_by_gen", {}).get(gen, "")
        hint = ""
        if search_text:
            items, hint = SteamAPI.apply_browse_search_fallback(
                items, search_text, bool(getattr(self.svc.api, "api_key", "") or "")
            )
        # 标签精确过滤：服务端 requiredtags 只是近似匹配（或语义），
        # 会混入不含所选标签的物品；enrich 后 tags 已可用，客户端精确交集过滤
        req_tags = getattr(self, "_tags_by_gen", {}).get(gen, [])
        tag_hint = ""
        if req_tags:
            items, dropped, unverifiable = SteamAPI.filter_items_by_tags(
                items, req_tags)
            if unverifiable:
                tag_hint = "标签过滤为服务端近似匹配（物品未返回标签数据）"
            elif dropped and items:
                tag_hint = f"已按所选标签精确过滤掉 {dropped} 个不匹配的物品"
            elif not items:
                tag_hint = "没有同时包含所选标签的物品（试试减少标签）"
        hint = " · ".join(h for h in (hint, tag_hint) if h)
        self._populate(items)
        if hint:
            base = self.status_label.text()
            if not items:
                # 空态：直接展示明确的"没找到"提示，不给"可能触发限流"的误导
                self.status_label.setText(hint)
            else:
                self.status_label.setText(f"{base} · {hint}" if base else hint)
        # B2：当前页渲染完成，调度下一页预取（代际+熔断+满页三重校验）
        self._schedule_prefetch_next_page(gen)

    def _on_list_failed(self, msg: str) -> None:
        self._list_overlay.stop()
        # 若有待执行请求，优先重跑（不弹错误框，避免打扰用户连续操作）
        if getattr(self, "_pending_refresh", False):
            self._pending_refresh = False
            self._refresh_list()
            return
        QMessageBox.critical(self, "加载失败", msg)

    def _cards(self) -> list:
        """当前列表中的全部卡片（跳过末尾 stretch）。"""
        out = []
        for i in range(self.list_layout.count()):
            w = self.list_layout.itemAt(i).widget()
            if isinstance(w, ModCardWidget):
                out.append(w)
        return out

    def _clear_cards(self) -> None:
        """逐个移除卡片（QScrollArea 无 itemWidget 生命周期竞态）。"""
        for w in self._cards():
            self.list_layout.removeWidget(w)
            w.deleteLater()

    def _populate(self, items: list) -> None:
        self._items = items
        # 客户端按所选排序维度重排（保证热度/大小等排序在元数据补全后准确）
        sort_key = self.sort_combo.currentData()
        sort_fns = {
            "mostsubscribed": lambda i: -(i.subscriptions or 0),
            "mostviews": lambda i: -(i.views or 0),
            "favorited": lambda i: -(i.favorited or 0),
        }
        if sort_key in sort_fns:
            items = sorted(items, key=sort_fns[sort_key])
        self._clear_cards()
        self._checked_ids.clear()
        # O1：构建 url→cards 索引（同一预览图可能被多卡引用）
        self._url_index.clear()
        # F7：标题关键词过滤（隐藏废弃/不感兴趣的 mod）
        hide_kw = self.svc.config.get("hide_keywords", default=[]) or []
        hide_kw = [k.strip().lower() for k in hide_kw if k and k.strip()]
        if hide_kw:
            items = [it for it in items
                     if not any(k in (it.title or "").lower() for k in hide_kw)]
        lib = self.svc.library
        # 库查询一次性批量做，避免每张卡片各查一次（减少 N 次同步 IO）
        existing_ids = set()
        try:
            for rec in lib.all():
                existing_ids.add(rec.item_id)
        except Exception:  # noqa: BLE001
            pass
        for it in items:
            card = ModCardWidget(it)
            card.download_requested.connect(self._download_item)
            card.detail_requested.connect(self._show_detail)
            card.check_toggled.connect(self._on_card_check_toggled)
            card.hover_entered.connect(self._on_card_hover)
            if it.publishedfileid in existing_ids:
                card.mark_downloaded()
            # 插在 stretch 之前
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            if it.preview_url:
                self._url_index.setdefault(it.preview_url, []).append(card)
                self.image_loader.load(it.preview_url, 96, 96)
        # 统一应用文本省略（修复字符挤压）
        for card in self._cards():
            card._apply_elide()
        self._update_dl_button()
        # 有待执行请求（用户在加载期间又切了游戏/翻页）：完成后立即重跑
        if getattr(self, "_pending_refresh", False):
            self._pending_refresh = False
            self._refresh_list()
        if items:
            self.status_label.setText(
                f"显示 {len(items)} 个物品 · 当前游戏 {game_name(self._current_appid())}"
            )
        elif self._page > 1:
            # 翻过头了：给用户明确终点提示，而不是误以为限流/出错
            self.status_label.setText("已到最后一页，没有更多物品（试试回到上一页）")
        else:
            self.status_label.setText("没有匹配的物品（该游戏可能暂无可抓取的工坊页，或触发限流）")

    def _on_image_loaded(self, url: str, pixmap) -> None:
        # O1（algo #1）：url→cards 索引替代全表扫描
        # （旧实现每张图片到达都遍历全部卡片，30 图×30 卡=900 次比较）
        for card in self._url_index.get(url, ()):
            card.set_thumbnail(pixmap)

    # ------------------------------------------------------------- 悬停预取
    def _on_card_hover(self, item_id: str) -> None:
        """鼠标进入卡片：重置防抖定时器，停留 400ms 才预取。"""
        self._prefetch_id = item_id
        self._prefetch_timer.start()

    def _do_prefetch_detail(self) -> None:
        """后台预取当前悬停物品的详情页 HTML 进缓存（点击打开时秒开）。

        已在缓存中或正在预取的物品跳过；预取失败静默忽略（点击时会正常重试）。
        """
        from swdm.gui.detail_dialog import DetailPageWorker

        item_id = self._prefetch_id
        if not item_id:
            return
        # 用户点击/依赖下载正在请求时，预取让出网络槽位（投机请求不与用户操作争抢）
        if getattr(self.svc.api, "_priority_pending", 0):
            return
        cached = DetailPageWorker._page_cache.get(item_id)
        if cached:                      # 已有 5 分钟缓存，无需预取
            return
        # B1：磁盘缓存已命中也跳过预取
        from swdm.core.detail_cache import get_detail_cache

        disk_ok, _disk_html = get_detail_cache().get(item_id)
        if disk_ok:
            return
        if item_id in self._prefetching:  # 正在预取
            return
        self._prefetching.add(item_id)

        class _PrefetchWorker(QThread):
            done = Signal(str)

            def __init__(self, api, iid) -> None:
                super().__init__()
                self._api = api
                self._iid = str(iid)

            def run(self):
                import time as _time

                try:
                    html = self._api._community_get(
                        "/sharedfiles/filedetails/", {"id": self._iid}
                    )
                    if html:
                        DetailPageWorker._page_cache[self._iid] = (
                            _time.time(), html
                        )
                        # B1：预取结果同步落磁盘（跨重启命中）
                        get_detail_cache().set(self._iid, html)
                except Exception:  # noqa: BLE001
                    pass
                self.done.emit(self._iid)

        w = _PrefetchWorker(self.svc.api, item_id)
        w.done.connect(
            lambda iid, wr=w: (self._prefetching.discard(iid), wr.deleteLater())
        )
        w.start()

    # ------------------------------------------------- B2 下一页预取
    def _schedule_prefetch_next_page(self, gen: int) -> None:
        """当前页渲染完成：若本页满页，延迟预取下一页。

        只在「有下一页」的可能时预取（本页物品数 < 单页上限说明已到末页）。
        代际过期则不启动；任何用户操作（切游戏/搜索/排序/翻页）都会
        bump _worker_gen，旧预取自然作废。
        """
        if gen != self._worker_gen:
            return
        # 单页上限 30（与 BrowseWorker numperpage 一致）
        if len(self._items) < 30:
            return
        # 熔断冷却期内不预取（连接已断/连续失败，预取只会空打）
        breaker = getattr(self.svc.api, "_browse_breaker", None)
        if breaker is not None and breaker.in_cooldown():
            return
        self._nextpage_timer.start()

    def _do_prefetch_next_page(self) -> None:
        """后台预取下一页列表入 ApiCache（用户翻页时零网络命中）。

        用 daemon 线程而非 QThread：预取只暖缓存、不需要 UI 信号，
        daemon 保证进程退出时不被在途网络请求挂住（实测 QThread 版
        会让测试进程在退出阶段卡死）。

        【硬约束落地】
        1. 熔断退避：复用 GameSearchClient 同一 CircuitBreaker 实现
           （api._browse_breaker），连接错误/连续失败 → 冷却 15s 跳过
        2. 深拷贝：预取只调 browse()，命中/未命中/hub 三条路径均已
           深拷贝，预取不开新返回路径、不自己写缓存
        3. 代际丢弃：请求前后均校验代际，过期则不发包/不处理，
           结果从不触碰 UI，绝不覆盖当前页
        """
        if self._nextpage_prefetching:
            return
        # 用户点击/依赖下载在飞时，预取让出网络槽位（t15 礼让语义）
        if getattr(self.svc.api, "_priority_pending", 0):
            # 稍后重试（用户请求完成后重排）
            self._nextpage_timer.start()
            return
        breaker = getattr(self.svc.api, "_browse_breaker", None)
        if breaker is not None and breaker.in_cooldown():
            return
        appid = self._current_appid()
        if not appid:
            return
        # 预取前再次校验：期间用户可能已切游戏/翻页
        gen = self._worker_gen
        next_page = self._page + 1
        search = self.search_edit.text().strip()
        sort = self.sort_combo.currentData()
        tags = [t.strip() for t in self.tag_edit.text().split(",") if t.strip()]
        # 缓存键必须与 browse() 内部完全一致（language/numperpage），
        # 否则预热的条目与翻页时的查找键不匹配，预取白做
        from swdm.core.api_cache import get_api_cache, make_cache_key

        key = make_cache_key(appid, next_page, sort, search, tags or [],
                             "schinese", 30)
        if get_api_cache().get(key)[0]:
            return
        self._nextpage_prefetching = True

        def _warm() -> None:
            try:
                # 代际已变（用户切游戏/搜索/翻页）→ 静默丢弃，不发包
                if gen != self._worker_gen:
                    log.info("丢弃过期代际 %s 的下一页预取（当前 %s）",
                             gen, self._worker_gen)
                    return
                # 只暖缓存：browse 内部写 ApiCache 并在所有路径深拷贝，
                # 返回值预取不使用（不渲染，绝不动当前页）
                self.svc.api.browse(appid, page=next_page, search_text=search,
                                    sort=sort, required_tags=tags or None)
                self._on_nextpage_prefetched(gen, key)
            except Exception:  # noqa: BLE001
                # 预取失败静默忽略（用户翻页时 browse 内有降级兜底）
                log.debug("下一页预取失败 page=%s", next_page, exc_info=True)
            finally:
                self._nextpage_prefetching = False

        t = threading.Thread(target=_warm, name="swdm-nextpage-prefetch",
                             daemon=True)
        self._nextpage_thread = t
        t.start()

    def _on_nextpage_prefetched(self, gen: int, key: str) -> None:
        """预取完成记账（仅日志，结果已在 browse 内写入 ApiCache）。

        key 由 GUI 线程在调度时预算好传入：worker 线程不读 Qt 控件。
        """
        # 代际过期：静默丢弃，绝不覆盖当前页（照搬 t25 A-U5 已验证机制）
        if gen != self._worker_gen:
            log.info("丢弃过期代际 %s 的下一页预取回包（当前 %s）",
                     gen, self._worker_gen)
            return
        from swdm.core.api_cache import get_api_cache

        hit = get_api_cache().get(key)[0]
        log.debug("下一页预取完成 key=%s 缓存命中=%s", key[:48], hit)

    # ------------------------------------------------------------- 分页
    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._refresh_list()

    def _next_page(self) -> None:
        self._page += 1
        self._refresh_list()

    # ------------------------------------------------------------- 勾选
    def _on_card_check_toggled(self, item_id: str, on: bool) -> None:
        if on:
            self._checked_ids.add(item_id)
        else:
            self._checked_ids.discard(item_id)
        self._update_dl_button()

    def _update_dl_button(self) -> None:
        n = len(self._checked_ids)
        self.dl_selected_btn.setText(
            f"⬇ 下载勾选 ({n})" if n else "⬇ 下载勾选"
        )
        self.dl_selected_btn.setEnabled(n > 0)

    def _check_all(self) -> None:
        """全选/全不选（勾选框语义）。已全勾 → 全部取消；否则全勾。"""
        cards = self._cards()
        if not cards:
            return
        all_checked = all(c.isChecked() for c in cards)
        for c in cards:
            c.setChecked(not all_checked)   # 触发 check_toggled，集合自动同步
        self._update_dl_button()

    # ------------------------------------------------------------- 下载
    def _download_item(self, item_id: str) -> None:
        appid = self._current_appid()
        item = next((i for i in self._items if i.publishedfileid == item_id), None)
        if not item:
            return
        self._download_with_deps([item], appid)

    def _download_selected(self) -> None:
        appid = self._current_appid()
        # 以卡片内嵌勾选框为准
        checked_ids = set(self._checked_ids)
        items = [i for i in self._items if i.publishedfileid in checked_ids]
        if not items:
            QMessageBox.information(self, "提示", "请先勾选要下载的 mod")
            return
        self._download_with_deps(items, appid)

    def _download_with_deps(self, items: list, appid: str) -> None:
        """下载物品，按配置处理前置依赖（需求：依赖 mod 下载配置）。"""
        cfg = self.svc.config
        auto_deps = bool(cfg.get("dependencies", "auto_download", True))
        ask = bool(cfg.get("dependencies", "ask_before_download", True))
        max_depth = int(cfg.get("dependencies", "max_depth") or 10)
        skip_installed = bool(cfg.get("dependencies", "skip_installed", True))

        # bug1/6/13：先把所有选中物品入队并在下载页建立占位行，
        # 用户立刻看到队列与画面反馈，不必等依赖解析（网络慢时队列
        # 会"慢慢出现"）
        for it in items:
            self.svc.downloader.enqueue(it, appid)
        self._refresh_download_ui(items, appid)
        self.show_downloads.emit()
        self.status_label.setText(
            f"已加入下载队列：{len(items)} 个 mod"
            + ("，正在解析前置依赖…" if auto_deps else "")
        )

        if not auto_deps:
            return

        # 异步解析依赖（避免 UI 卡顿）；解析完成后再把依赖插到队首
        from .workers import DependencyResolveWorker

        self._dep_worker = DependencyResolveWorker(
            self.svc.api, items, appid, max_depth=max_depth,
            skip_installed=skip_installed, library=self.svc.library,
        )
        self._dep_worker.result.connect(
            lambda payload: self._on_deps_resolved(items, appid, payload, ask)
        )
        self._dep_worker.start()

    def _refresh_download_ui(self, items: list, appid: str) -> None:
        """让下载页立即出现这些物品的占位行（bug1/13 的即时反馈）。"""
        try:
            self.svc.downloads_tab.add_pending_batch(items, appid)
        except Exception:  # noqa: BLE001
            pass

    def _on_deps_resolved(self, items, appid, payload: dict, ask: bool) -> None:
        """依赖解析完成回调：payload = {deps: [...], skipped: [...]}。
        本物品已先行入队，这里只把依赖插到队首（依赖优先下载）。"""
        deps = payload.get("deps", [])
        skipped = payload.get("skipped", [])
        dep_names = payload.get("dep_names", {})

        if not deps:
            self.status_label.setText(
                f"已加入下载队列：{len(items)} 个 mod（无前置依赖）"
            )
            return

        if ask:
            dep_lines = []
            for d in deps[:15]:
                name = dep_names.get(d, d)
                dep_lines.append(f"  • {name}")
            more = f"\n  …另有 {len(deps) - 15} 个" if len(deps) > 15 else ""
            text = (
                f"这些 mod 共有 {len(deps)} 个前置依赖：\n"
                + "\n".join(dep_lines) + more
                + f"\n（已跳过 {len(skipped)} 个已安装的依赖）\n\n是否一并下载？"
            )
            btn = QMessageBox.question(
                self, "前置依赖", text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if btn != QMessageBox.StandardButton.Yes:
                self.status_label.setText("已加入下载队列（未下载依赖）")
                return

        # 依赖插到队首（依赖在前，本物品在后）
        from swdm.core import WorkshopItem

        for d in deps:
            di = WorkshopItem(publishedfileid=d, appid=appid)
            self.svc.downloader.enqueue_high_priority(di, appid)
        for it in items:
            # 记录依赖关系到本物品，入库时写入 mod 库
            it.dependencies = list(deps)
        self.status_label.setText(
            f"已加入下载队列：{len(items)} 个 mod + {len(deps)} 个前置依赖"
        )

    def _show_detail(self, item_id: str) -> None:
        self._open_detail(item_id)

    def _open_detail(self, item_id: str) -> None:
        """打开 mod 详情弹窗（非模态）：先 show 弹窗，再异步解析详情回填。

        保证"mod 选择页与详情页可同时开启"；网络解析失败时在弹窗内
        显示"加载失败"，不崩 UI。
        """
        it = next((i for i in self._items if i.publishedfileid == item_id), None)
        if not it:
            return

        # 冲突检测：本地库中同名/同 id 的已安装 mod
        conflicts = self._detect_conflicts(it)

        dlg = ModDetailDialog(
            it,
            parent=self,
            comments=None,          # 异步填充
            dependencies=None,      # 异步填充
            conflicts=conflicts,
            library=self.svc.library,
            downloader=self.svc.downloader,
            api=self.svc.api,
        )
        # 非模态：show() 而非 exec()，详情页与选择页可同时操作
        dlg.show()
        # 防止被 GC 回收
        self._detail_dialog = dlg
        dlg.download_requested.connect(self._download_item)
        dlg.queue_requested.connect(self._download_item)
        # 快捷搜索：详情页的标签/作者/依赖标题点击后跳到筛选页搜索
        dlg.search_requested.connect(self._on_quick_search)

        # 异步解析详情数据（描述/评论/依赖），回填弹窗
        worker = DetailPageWorker(
            self.svc.api, item_id, time_updated=it.time_updated or 0, parent=dlg
        )
        worker.description_ready.connect(dlg.set_description)
        worker.creator_ready.connect(dlg.set_creator)
        worker.comments_ready.connect(dlg.set_comments)
        worker.total_ready.connect(dlg.set_comment_count)
        worker.conflicts_ready.connect(
            lambda cs: dlg.set_conflicts([
                {"id": c.mod_id, "title": c.name, "reason": c.statement}
                for c in cs
            ])
        )
        worker.deps_ready.connect(
            lambda deps: dlg.set_dependencies(
                [{"id": pid, "title": title} for pid, title in deps]
            )
        )
        worker.failed.connect(dlg.show_error)
        # 网络受限时在弹窗里显示"加载失败"，并把空态切到"加载完成"
        worker.failed.connect(lambda _msg: dlg.set_comments([]))
        worker.failed.connect(lambda _msg: dlg.set_dependencies([]))
        worker.start()
        self._detail_worker = worker

    def _on_quick_search(self, kind: str, value: str) -> None:
        """详情页快捷搜索：把关键词/标签/作者填入筛选条件并跳到工坊页。

        Steam 工坊浏览页的关键词搜索会同时匹配 mod 标题、描述与作者名，
        因此作者搜索复用关键词输入框。
        标签（kind=="tag"）：在标签栏直接追加该标签 chip（用户需求：
        点击即在标签选择行下加上该标签卡片），而非填入隐藏输入框。
        """
        if not value:
            return
        if kind == "tag":
            # 标签栏已有该标签：选中它；没有则追加一个并选中
            chips = dict(getattr(self.tag_bar, "_chips", {}))
            if value not in chips:
                self.tag_bar.set_tags(
                    list(self.tag_bar._chips.keys()) + [value])
            cur = self.tag_bar.selected()
            if value not in cur:
                self.tag_bar.set_selected(cur + [value])
            # 滚到新标签 chip 所在位置（末尾）
            hsb = self.tag_bar._scroll.horizontalScrollBar()
            hsb.setValue(hsb.maximum())
        else:  # text / author
            self.search_edit.setText(value)
            if kind == "author":
                self.status_label.setText(f"按作者搜索：{value}")
        # 切到工坊页（详情弹窗仍保持打开）
        win = self.window()
        tabs = getattr(win, "_tabs", None)
        if tabs is not None:
            tabs.setCurrentWidget(self)
        self._refresh_list()

    def _detect_conflicts(self, it) -> list[dict]:
        """检测冲突：本地库中同 id（已安装）或同名（疑似重复）的 mod。"""
        conflicts: list[dict] = []
        try:
            rec = self.svc.library.get(it.publishedfileid)
            if rec is not None and rec.installed:
                conflicts.append(
                    {"id": rec.item_id, "title": rec.title,
                     "reason": "本地库已安装此 mod，重复下载会覆盖现有版本"}
                )
            if it.title:
                for rec in self.svc.library.search(it.title):
                    if rec.item_id != it.publishedfileid and rec.installed:
                        conflicts.append(
                            {"id": rec.item_id, "title": rec.title,
                             "reason": "本地库存在同名 mod，可能存在内容冲突"}
                        )
        except Exception:  # noqa: BLE001
            log.debug("冲突检测失败（忽略）", exc_info=True)
        return conflicts

    # ------------------------------------------------------------- 导入
    # ------------------------------------------------------------- 标签查询
    # ------------------------------------------------------------- 标签栏
    # 标签缓存：(appid, tags) —— 5 分钟内不重复请求（修 bug5：反复拉取触发
    # 限流后全部失败；且失败被静默吞掉用户无感知）
    _TAGS_CACHE: dict[str, tuple[float, list]] = {}
    _TAGS_TTL = 300.0

    def _fetch_tags(self) -> None:
        """拉取当前游戏的可用标签填入标签栏（有缓存时零请求）。"""
        appid = self._current_appid()
        if not appid:
            self.tag_bar.set_tags([])
            return
        # 切换游戏时立即清空旧标签 + 显示加载态，
        # 避免"标签不随游戏更新"的错觉（bug17）
        self.tag_bar.set_tags([])
        self.tag_bar.set_loading(True)
        cached = WorkshopTab._TAGS_CACHE.get(appid)
        import time as _time

        if cached and _time.time() - cached[0] < WorkshopTab._TAGS_TTL:
            self.tag_bar.set_loading(False)
            self.tag_bar.set_tags(cached[1])
            return
        self.tags_btn.setEnabled(False)
        worker = _TagsFetchWorker(self.svc.api, appid)
        worker.tags_ready.connect(self._on_tags_ready)
        worker.failed.connect(self._on_tags_failed)
        worker.start()
        self._tags_worker = worker

    def _pick_tags(self) -> None:
        """手动"刷新标签"：清缓存后强制重新拉取。"""
        appid = self._current_appid()
        if not appid:
            QMessageBox.information(self, "提示", "请先选择游戏")
            return
        WorkshopTab._TAGS_CACHE.pop(appid, None)
        self._fetch_tags()

    def _on_tags_ready(self, tags) -> None:
        self.tags_btn.setEnabled(True)
        self.tag_bar.set_loading(False)
        appid = self._current_appid()
        # 兼容旧 worker（返回 list[str]）与新解析（list[tuple]）
        norm = []
        for t in tags or []:
            if isinstance(t, (tuple, list)) and len(t) >= 2:
                norm.append((str(t[0]), int(t[1] or 0)))
            else:
                norm.append((str(t), 0))
        if appid:
            import time as _time

            WorkshopTab._TAGS_CACHE[appid] = (_time.time(), norm)
        self.tag_bar.set_tags(norm)

    def _on_tags_failed(self, msg: str) -> None:
        self.tags_btn.setEnabled(True)
        self.tag_bar.set_loading(False)
        # 修 bug5：失败时给用户明确提示而非静默吞掉
        self.status_label.setText(f"标签拉取失败：{msg}")
        log.warning("标签拉取失败：%s", msg)

    def _on_tag_selection_changed(self, tags: list[str]) -> None:
        """标签栏选择变化 → 同步搜索框的标签过滤参数并刷新列表。"""
        self.tag_edit.setText(",".join(tags))
        self._page = 1
        self._refresh_list()

    def _import_url(self) -> None:
        """B5 批量粘贴导入：多行输入框，一次粘贴任意多个工坊链接/ID。

        与 B3 剪贴板监听共用 resolve_any_url 入口（_import_tokens）；
        这是手动版，可一次处理多个链接、会展开合集、可交互补 AppID。
        用 QInputDialog.getMultiLineText 保持与既有单行导入相同的
        静态方法协议（测试可打桩替换，无需真实交互）。
        """
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getMultiLineText(
            self, "批量粘贴导入",
            "每行一个工坊物品链接或物品 ID（也支持逗号分隔）：\n"
            "支持 https://steamcommunity.com/sharedfiles/filedetails/?id=… 链接",
        )
        if not ok or not text.strip():
            return
        tokens = [t.strip() for t in text.replace("\n", ",").split(",") if t.strip()]
        self._import_tokens(tokens)

    def _import_tokens(self, tokens: list[str]) -> None:
        """解析 token 列表为 (appid, ids) 并入队（B3/B5 共用）。"""
        appid = self._current_appid()
        ids: list[str] = []
        for tok in tokens:
            a, i = self.svc.api.resolve_any_url(tok)
            if i:
                ids.append(i)
                if a:
                    appid = a
        ids = list(dict.fromkeys(ids))
        if not ids:
            QMessageBox.warning(self, "导入", "未能从输入中解析出任何物品 ID")
            return
        if not appid:
            from PySide6.QtWidgets import QInputDialog

            appid, _ok = QInputDialog.getText(self, "AppID", "这些物品属于哪个游戏？输入 AppID：")
            if not _ok or not appid.strip().isdigit():
                return
            appid = appid.strip()

        # 尝试将每个 ID 作为合集展开（非合集返回空列表，安全）
        expanded: list[str] = []
        for cid in list(ids):
            try:
                children = self.svc.api.get_collection_details(cid)
            except Exception as e:  # noqa: BLE001
                log.warning("合集展开失败 %s: %s", cid, e)
                children = []
            if children:
                self.status_label.setText(f"合集 {cid} 展开 {len(children)} 个物品")
                expanded.extend(children)
        if expanded:
            ids = list(dict.fromkeys(ids + expanded))

        # 取元数据后入队
        details = self.svc.api.get_file_details(ids)
        items: list = []
        for k, v in details.items():
            v.appid = appid
            local = next((i for i in self._items if i.publishedfileid == k), None)
            if local:
                v.title = v.title or local.title
                v.preview_url = v.preview_url or local.preview_url
            items.append(v)
        for it in items:
            self.svc.downloader.enqueue(it, appid)
        self.status_label.setText(f"已导入 {len(items)} 个 mod 到下载队列")

    def refresh_login_ui(self) -> None:
        self._update_anon_label()
