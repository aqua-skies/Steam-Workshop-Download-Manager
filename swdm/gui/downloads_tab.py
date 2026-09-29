"""Downloads tab: live download queue, progress, logs and history (下载页).

Batch buttons: pause/resume merged into a single toggle since t22 (C②), retry-failed,
clear-completed, cancel-all. Removing an already-imported successful task prompts whether
to also remove it from the mod library (t13 删除互通); ``records_removed`` from the library
tab removes the corresponding row here.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from swdm.core.downloader import DownloadJob, DownloadManager, JobStatus
from swdm.core.logger import get_logger
from swdm.core.mod_library import ModLibrary
from swdm.gui.workers import DownloadEventBridge

log = get_logger("swdm.gui.downloads")


class DownloadsTab(QWidget):
    """下载管理页。"""

    _HEADERS = ["物品 ID", "标题", "状态", "进度", "大小", "信息", "操作"]

    # 移除已入库任务时发出，主窗口据此刷新库页（u10 互通）
    library_changed = Signal()

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.svc = services
        self.mgr: DownloadManager = services.downloader
        self.library: ModLibrary = services.library
        self._row_map: dict[str, int] = {}   # job_id -> row index
        self._build()
        self._attach_manager()
        self._refresh_status()

    # ------------------------------------------------------------- 布局
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.stat_label = QLabel("队列：0  进行中：0  完成：0")
        top.addWidget(self.stat_label)
        top.addStretch()
        self.clear_done_btn = QPushButton("清除已完成")
        self.clear_done_btn.setProperty("secondary", True)
        self.clear_done_btn.clicked.connect(self._clear_done)
        top.addWidget(self.clear_done_btn)
        # F1：批量队列管理（暂停/继续/重试失败）
        # C②：暂停/继续合并为单按钮，按队列状态切换文案与行为
        self.pause_all_btn = QPushButton("⏸ 全部暂停")
        self.pause_all_btn.setProperty("secondary", True)
        self.pause_all_btn.clicked.connect(self._toggle_pause_all)
        top.addWidget(self.pause_all_btn)
        self.retry_failed_btn = QPushButton("↻ 重试失败")
        self.retry_failed_btn.setProperty("secondary", True)
        self.retry_failed_btn.clicked.connect(self._retry_failed)
        top.addWidget(self.retry_failed_btn)
        self.cancel_all_btn = QPushButton("取消全部")
        self.cancel_all_btn.setProperty("danger", True)
        self.cancel_all_btn.clicked.connect(self._cancel_all)
        top.addWidget(self.cancel_all_btn)
        root.addLayout(top)

        self.table = QTableWidget(0, len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        hdr = self.table.horizontalHeader()
        # bug4：显式设定每列宽度策略，避免"进度/大小"等列被拉伸挤压重叠
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 物品 ID
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # 标题
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)             # 状态
        hdr.resizeSection(2, 72)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)             # 进度
        hdr.resizeSection(3, 150)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)             # 大小
        hdr.resizeSection(4, 84)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)           # 信息
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)             # 操作
        hdr.resizeSection(6, 88)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.hint = QLabel("下载完成后会自动登记到「我的模组库」；元数据 JSON 与文件同目录。")
        self.hint.setStyleSheet("color:#8a909a; font-size:11px;")
        bottom.addWidget(self.hint)
        root.addLayout(bottom)

    # ------------------------------------------------------------- 绑定
    def _attach_manager(self) -> None:
        # manager 回调来自下载子线程，必须经 Qt 信号桥接回主线程，
        # 否则跨线程操作 QTableWidget 会导致 GUI 冻结（Qt 硬性要求）
        self._bridge = DownloadEventBridge()
        self._bridge.started.connect(self._on_started)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.finished.connect(self._on_finished)
        self._bridge.queue_changed.connect(self._refresh_status)
        self.mgr.add_listener(
            started=self._bridge.started.emit,
            progress=self._bridge.progress.emit,
            finished=self._bridge.finished.emit,
            queue_changed=self._bridge.queue_changed.emit,
        )

    # ------------------------------------------------------------- 任务行
    def _ensure_row(self, job: DownloadJob) -> int:
        if job.id in self._row_map:
            return self._row_map[job.id]
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_map[job.id] = row
        for col in range(len(self._HEADERS) - 1):
            self.table.setItem(row, col, QTableWidgetItem(""))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setMinimumWidth(110)
        self.table.setCellWidget(row, 3, bar)
        cancel = QPushButton("取消")
        cancel.setProperty("danger", True)
        cancel.setFixedWidth(72)

        def _do_cancel(_checked: bool = False, _jid: str = job.id,
                       _btn: QPushButton = cancel) -> None:
            # bug8：取消按钮加异常防护 + 立即禁用，防止重复点击与
            # 跨线程 terminate 引发的连锁崩溃
            _btn.setEnabled(False)
            _btn.setText("取消中…")
            try:
                self.mgr.cancel(_jid)
            except Exception:  # noqa: BLE001
                _btn.setEnabled(True)
                _btn.setText("取消")

        cancel.clicked.connect(_do_cancel)
        self.table.setCellWidget(row, 6, cancel)
        self.table.item(row, 0).setText(job.id)
        self.table.item(row, 1).setText(job.item.title or f"mod {job.id}")
        return row

    def _update_row(self, job: DownloadJob) -> None:
        row = self._ensure_row(job)
        status_text = {
            JobStatus.QUEUED: "排队中",
            JobStatus.RUNNING: "下载中",
            JobStatus.SUCCESS: "✓ 成功",
            JobStatus.FAILED: "✗ 失败",
            JobStatus.CANCELLED: "已取消",
        }.get(job.status, str(job.status.value))
        item = self.table.item(row, 2)
        if item:
            item.setText(status_text)
        bar = self.table.cellWidget(row, 3)
        if bar:
            pct = job.percent
            if pct < 0:
                # steamcmd 不输出逐字节进度：显示忙碌动画 + 明确文案，
                # 避免用户误以为卡在 0%（bug3）
                bar.setRange(0, 0)
                bar.setTextVisible(False)
                bar.setFormat("")
            else:
                bar.setRange(0, 100)
                bar.setTextVisible(True)
                bar.setFormat("%p%")
                bar.setValue(pct if job.status != JobStatus.SUCCESS else 100)
        size_item = self.table.item(row, 4)
        if size_item:
            mb = (job.bytes_done or job.item.file_size) / 1024 / 1024
            size_item.setText(f"{mb:.1f} MB")
        msg_item = self.table.item(row, 5)
        if msg_item:
            msg_item.setText(job.message or "")
        cancel_btn = self.table.cellWidget(row, 6)
        if cancel_btn:
            if job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                # B3（UX 审计+QA）：失败/取消行提供"重试"，
                # 调用 mgr.retry 移除旧记录并重新入队；
                # 无需回工坊页重找卡片
                cancel_btn.setText("重试")
                try:
                    cancel_btn.clicked.disconnect()
                except RuntimeError:
                    pass
                cancel_btn.setProperty("danger", False)
                cancel_btn.setProperty("secondary", False)
                cancel_btn.clicked.connect(
                    lambda _c=False, _jid=job.id: self._retry_job(_jid))
            elif job.status == JobStatus.SUCCESS:
                cancel_btn.setText("移除")
                try:
                    cancel_btn.clicked.disconnect()
                except RuntimeError:
                    pass
                cancel_btn.setProperty("danger", False)
                cancel_btn.setProperty("secondary", True)
                cancel_btn.clicked.connect(lambda: self._remove_row(job.id))
            else:
                cancel_btn.setText("取消")
                try:
                    cancel_btn.clicked.disconnect()
                except RuntimeError:
                    pass
                cancel_btn.setProperty("secondary", False)
                cancel_btn.setProperty("danger", True)
                cancel_btn.clicked.connect(lambda: self.mgr.cancel(job.id))
        self._refresh_status()

    def _retry_job(self, job_id: str) -> None:
        """B3：失败/取消任务一键重新入队。"""
        try:
            self.mgr.retry(job_id)
        except Exception:  # noqa: BLE001
            log.exception("重试任务失败: %s", job_id)

    def _remove_row(self, job_id: str) -> None:
        if job_id not in self._row_map:
            return
        # 已入库的成功任务：移除行时询问是否同时移除库记录（u10 互通）
        job = self._job_by_id(job_id)
        if (job is not None and job.status == JobStatus.SUCCESS
                and self.library.get(job_id) is not None):
            ans = QMessageBox.question(
                self, "移除已下载的 mod",
                f"「{job.item.title or job_id}」已入库。\n"
                "是否同时从 mod 库移除（含文件）？",
                (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No),
                QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    self.library.delete(job_id, remove_files=True)
                except Exception:  # noqa: BLE001
                    log.exception("移除库记录失败: %s", job_id)
                self.library_changed.emit()
        self._delete_row(job_id)

    def remove_rows_for(self, item_ids) -> None:
        """库页移除记录后同步清除下载页对应的已完成行（u10 反向联动）。"""
        for i in list(item_ids or []):
            self._delete_row(i)

    def _delete_row(self, job_id: str) -> None:
        if job_id not in self._row_map:
            return
        row = self._row_map.pop(job_id)
        self.table.removeRow(row)
        # 行下移：重建索引
        for jid, r in list(self._row_map.items()):
            if r > row:
                self._row_map[jid] = r - 1
        self._refresh_status()

    def _clear_done(self) -> None:
        done_rows: list[int] = []
        for job_id, row in list(self._row_map.items()):
            job = self._job_by_id(job_id)
            if job is None:
                continue
            if job.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
                done_rows.append(row)
                self._row_map.pop(job_id, None)
        # 必须从大行号往小删：removeRow 后下面的行会整体上移，
        # 按旧索引升序删会删错行，残留本应清除的记录（test_gui_sweep 发现）
        for row in sorted(done_rows, reverse=True):
            self.table.removeRow(row)
        # 行删除后整体下移：按表格第 0 列文本（job id）重建映射，
        # 避免错位导致后续取消/移除按钮失效（bug4 根因）
        self._row_map = {}
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 0)
            if cell is not None:
                self._row_map[cell.text()] = row
        self._refresh_status()

    def _job_by_id(self, job_id: str):
        snap = self.mgr.snapshot()
        for j in list(snap["queued"]) + list(snap["active"]) + list(snap["done"]):
            if j.id == job_id:
                return j
        return None

    # ------------------------------------------------------------- 回调
    def add_pending(self, item, appid: str) -> None:
        """物品入队时立即在表格中建立占位行（bug1/13：点击下载后立刻有
        画面反馈，不必等下载真正开始）。"""
        job = DownloadJob(item=item, appid=str(appid))
        self._update_row(job)

    def add_pending_batch(self, items, appid: str) -> None:
        """批量建立占位行（多选下载时队列立刻全部出现，bug6）。"""
        for it in items:
            self.add_pending(it, appid)
        self._refresh_status()

    def _on_started(self, job: DownloadJob) -> None:
        self._update_row(job)

    def _on_progress(self, job: DownloadJob) -> None:
        self._update_row(job)

    def _on_finished(self, job: DownloadJob) -> None:
        self._update_row(job)

    # ------------------------------------------------------------- 统计
    def _refresh_status(self) -> None:
        snap = self.mgr.snapshot()
        active = len(snap["active"])
        queued = len(snap["queued"])
        done_ok = sum(1 for j in snap["done"] if j.status == JobStatus.SUCCESS)
        done_fail = sum(1 for j in snap["done"] if j.status != JobStatus.SUCCESS)
        total_mb = sum(j.bytes_done for j in snap["done"] if j.status == JobStatus.SUCCESS) / 1024 / 1024
        self.stat_label.setText(
            f"队列：{queued}   进行中：{active}   "
            f"✓成功：{done_ok}   ✗失败：{done_fail}   累计下载：{total_mb:.1f} MB"
            + ("   ⏸ 已暂停" if getattr(self.mgr, "paused", False) else "")
        )
        self._sync_batch_buttons()

    def _cancel_all(self) -> None:
        # B4（UX 审计+QA）：危险操作须二次确认，避免误触清空整个队列
        reply = QMessageBox.question(
            self, "取消全部下载",
            "将取消队列中所有未完成的下载任务（已完成的保留）。\n\n确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mgr.cancel_all()

    # ----------------------------------------------------- F1：批量管理
    def _toggle_pause_all(self) -> None:
        """C②：单按钮在暂停/继续之间切换。"""
        if getattr(self.mgr, "paused", False):
            self.mgr.resume_all()
        else:
            self.mgr.pause_all()

    def _retry_failed(self) -> None:
        n = self.mgr.retry_all_failed()
        if n:
            # DownloadsTab 自身没有状态栏，借用主窗口状态栏反馈；
            # 旧代码直接用 self.status_bar（不存在）→ 有失败任务时
            # 点「重试失败」必崩 AttributeError（test_gui_sweep 发现）
            try:
                self.window().statusBar().showMessage(
                    f"已重新排队 {n} 个失败任务", 3000)
            except Exception:  # noqa: BLE001
                log.debug("重试反馈显示失败（忽略）", exc_info=True)

    def _sync_batch_buttons(self) -> None:
        """C②：单按钮反映暂停状态（切换文案，始终可用）。"""
        paused = getattr(self.mgr, "paused", False)
        self.pause_all_btn.setText("▶ 全部继续" if paused else "⏸ 全部暂停")

    def on_engine_log(self, line: str) -> None:
        # steamcmd 逐行日志可在此展示（debug 页统一处理，这里只记日志）
        log.debug("[下载页] %s", line)
