"""Library tab: categorize, search, enable/disable and import/export local mods (模组库页).

Multi-dimensional filters (game / category / tag / status / keyword) with selection
restored on refresh; batch enable/disable/categorize/delete via context menu; open folder;
export the currently filtered results (t16 决议 B③). Deleting emits ``records_removed`` so
the downloads tab stays in sync (t13 双向互通).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from swdm.core.games import game_name
from swdm.core.logger import get_logger
from swdm.core.mod_library import ModLibrary, ModRecord
from swdm.core.paths import LIBRARY_DIR
from swdm.gui.workers import ImageLoader

log = get_logger("swdm.gui.library")


def _restore_combo(combo: QComboBox, data) -> None:
    """下拉重建后按 userData 恢复旧选择；数据已不存在则回到首项。"""
    if data is None:
        return
    idx = combo.findData(data)
    if idx >= 0:
        combo.setCurrentIndex(idx)


class LibraryTab(QWidget):
    """本地模组库管理（需求 2：分类/检索）。"""

    # 移除记录后发出（item_id 列表），主窗口据此同步下载页（u10 互通）
    records_removed = Signal(list)
    # P5：空状态按钮请求跳到工坊浏览页
    navigate_requested = Signal()
    # C1：工作线程完成回 GUI 线程（A6：Signal(list) 替代 Q_ARG(list)，
    # bare list 在 PySide6 无 QMetaType，invokeMethod 会抛 RuntimeError）
    updates_checked = Signal(list)
    # C1：工作线程进度回 GUI 线程（同样用 Signal，避免 bare 类型 Q_ARG）
    check_progress = Signal(int, int)

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.svc = services
        self.library: ModLibrary = services.library
        self.image_loader = ImageLoader()
        self.image_loader.bus.loaded.connect(self._on_image_loaded)
        self._build()
        self.refresh()

    # ------------------------------------------------------------- 布局
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 统计栏
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(
            "background:#23272e; color:#9aa0aa; padding:8px; border-radius:5px;"
        )
        root.addWidget(self.stats_label)

        # 过滤工具栏
        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("检索：标题 / 作者 / 备注 / ID…")
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit, 2)

        self.appid_combo = QComboBox()
        self.appid_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(QLabel("游戏:"))
        toolbar.addWidget(self.appid_combo)

        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(QLabel("分类:"))
        toolbar.addWidget(self.category_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("按下载时间", "time")
        self.sort_combo.addItem("按标题", "title")
        self.sort_combo.addItem("按大小", "size")
        self.sort_combo.addItem("按订阅数", "subs")
        self.sort_combo.addItem("按游戏", "appid")
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.sort_combo)
        root.addLayout(toolbar)

        # 筛选
        filters = QHBoxLayout()
        self.only_enabled = QCheckBox("仅显示启用")
        self.only_enabled.toggled.connect(self._on_only_enabled_toggled)
        filters.addWidget(self.only_enabled)
        self.only_disabled = QCheckBox("仅显示禁用")
        self.only_disabled.toggled.connect(self._on_only_disabled_toggled)
        filters.addWidget(self.only_disabled)
        self.only_fav = QCheckBox("仅收藏")
        self.only_fav.toggled.connect(self.refresh)
        filters.addWidget(self.only_fav)
        filters.addStretch()
        root.addLayout(filters)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder)
        root.addWidget(self.list_widget, 1)

        # P5/B6：空状态可操作引导（空库 → 前往工坊；筛选无结果 → 清除筛选）
        self._empty_state = self._build_empty_state()
        root.addWidget(self._empty_state, 1)
        self._empty_state.setVisible(False)

        # 底部操作
        bottom = QHBoxLayout()
        self.enable_btn = QPushButton("启用选中")
        self.enable_btn.setProperty("secondary", True)
        self.enable_btn.clicked.connect(lambda: self._set_selected_enabled(True))
        bottom.addWidget(self.enable_btn)

        self.disable_btn = QPushButton("禁用选中")
        self.disable_btn.setProperty("secondary", True)
        self.disable_btn.clicked.connect(lambda: self._set_selected_enabled(False))
        bottom.addWidget(self.disable_btn)

        bottom.addStretch()

        self.import_btn = QPushButton("⬆ 导入已有目录")
        self.import_btn.setProperty("secondary", True)
        self.import_btn.clicked.connect(self._import_existing)
        bottom.addWidget(self.import_btn)

        self.export_btn = QPushButton("⬇ 导出列表")
        self.export_btn.setProperty("secondary", True)
        self.export_btn.clicked.connect(self._export_list)
        bottom.addWidget(self.export_btn)

        self.import_list_btn = QPushButton("⬆ 导入列表")
        self.import_list_btn.setProperty("secondary", True)
        self.import_list_btn.clicked.connect(self._import_list)
        bottom.addWidget(self.import_list_btn)

        self.refresh_btn = QPushButton("↻ 刷新")
        self.refresh_btn.setProperty("secondary", True)
        self.refresh_btn.clicked.connect(self.refresh)
        bottom.addWidget(self.refresh_btn)

        # C1（1.4.1）：mod 库更新检查（手动按钮版，首版不自动重下）
        self.check_updates_btn = QPushButton("🔍 检查更新")
        self.check_updates_btn.setProperty("secondary", True)
        self.check_updates_btn.setToolTip(
            "比对 Steam 最新 time_updated 与本地快照，标出有更新的 mod"
        )
        self.check_updates_btn.clicked.connect(self._check_updates)
        bottom.addWidget(self.check_updates_btn)
        self._updated_ids: set[str] = set()      # 标红集合
        self._check_thread = None                # daemon 线程（防 UI 卡死）
        self._check_cancel = False               # 用户取消标志
        self.updates_checked.connect(self._on_check_updates_done)
        self.check_progress.connect(self._set_check_progress)
        root.addLayout(bottom)

    # ------------------------------------------------------------- 数据
    def _current_filter(self) -> dict:
        """当前过滤/排序条件（刷新与导出共用；B③：导出当前筛选结果，
        而非全库）。"""
        return {
            "keyword": self.search_edit.text().strip(),
            "appid": self.appid_combo.currentData() or "",
            "category": self.category_combo.currentData() or "",
            "enabled_only": self.only_enabled.isChecked() and not self.only_disabled.isChecked(),
            "disabled_only": self.only_disabled.isChecked() and not self.only_enabled.isChecked(),
            "favorites_only": self.only_fav.isChecked(),
            "sort": self.sort_combo.currentData(),
        }

    def refresh(self) -> None:
        stats = self.library.stats()
        self.stats_label.setText(
            f"共 {stats['total']} 个 mod · 启用 {stats['enabled']} 个 · "
            f"占用 {stats['size'] / 1024 / 1024:.1f} MB · 覆盖 {stats['games']} 款游戏"
        )
        # 游戏过滤（B2：重建下拉会丢失用户已选的过滤条件，
        # 记录旧选择后恢复）
        prev_appid = self.appid_combo.currentData()
        self.appid_combo.blockSignals(True)
        self.appid_combo.clear()
        self.appid_combo.addItem("全部游戏", "")
        seen = set()
        for r in self.library.all():
            if r.appid and r.appid not in seen:
                seen.add(r.appid)
                # u12：显示游戏名而非裸 AppID，用户能一眼区分不同游戏的 mod
                self.appid_combo.addItem(game_name(r.appid), r.appid)
        _restore_combo(self.appid_combo, prev_appid)
        self.appid_combo.blockSignals(False)

        # 分类过滤（同上，恢复选择）
        prev_cat = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("全部分类", "")
        for c in self.library.categories():
            self.category_combo.addItem(c, c)
        _restore_combo(self.category_combo, prev_cat)
        self.category_combo.blockSignals(False)

        recs = self.library.search(**self._current_filter())
        # 刷新前记住选中项：_populate 会 clear 列表，否则每次
        # 启用/禁用/改分类后选中行都丢失，用户得重新选（test_gui_sweep 发现）
        prev_ids = set(self._selected_ids())
        self._populate(recs)
        if prev_ids:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole) in prev_ids:
                    item.setSelected(True)
                    if self.list_widget.currentRow() < 0:
                        self.list_widget.setCurrentRow(i)

    def _on_only_enabled_toggled(self, checked: bool) -> None:
        if checked:
            self.only_disabled.blockSignals(True)
            self.only_disabled.setChecked(False)
            self.only_disabled.blockSignals(False)
        self.refresh()

    def _on_only_disabled_toggled(self, checked: bool) -> None:
        if checked:
            self.only_enabled.blockSignals(True)
            self.only_enabled.setChecked(False)
            self.only_enabled.blockSignals(False)
        self.refresh()

    def _populate(self, recs: list[ModRecord]) -> None:
        self.list_widget.clear()
        for rec in recs:
            item = QListWidgetItem()
            title = rec.title or f"mod {rec.item_id}"
            status = "✓" if rec.enabled else "✗"
            fav = " ★" if rec.favorite else ""
            cat = f" [{rec.category}]" if rec.category else ""
            mb = rec.file_size / 1024 / 1024
            # u12：行内显示游戏名（未知游戏回退 "AppID 123"），让不同游戏的 mod 可区分
            game = game_name(rec.appid) if rec.appid else "未归类"
            text = f"{status} {title}{fav}{cat} — {mb:.1f} MB · {game} · {rec.item_id}"
            # C1（1.4.1）：有 Steam 侧更新的条目标红 + 前缀角标
            is_updated = rec.item_id in self._updated_ids
            if is_updated:
                text = f"🔄 {text}"
                item.setForeground(Qt.GlobalColor.red)
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole, rec.item_id)
            item.setToolTip(rec.description[:300] if rec.description else text)
            if not rec.enabled and not is_updated:
                # 灰色不覆盖标红：更新提示比启用状态更需用户注意
                item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(item)
            if rec.preview_url:
                self.image_loader.load(rec.preview_url, 48, 48)
        self._refresh_empty_state(len(recs))

    # ------------------------------------------------------------- 空状态（P5/B6）
    def _build_empty_state(self) -> QWidget:
        """空态面板：空库时给「前往工坊浏览」入口；筛选无结果时给「清除筛选」。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(24, 32, 24, 32)
        lay.setSpacing(10)

        self._empty_title = QLabel("还没有 mod")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._empty_hint = QLabel(
            "在「工坊浏览」页选择 mod 后点击下载，\n"
            "下载完成会自动登记到这里；也可以直接导入已有目录。"
        )
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_go = QPushButton("前往工坊浏览")
        self._empty_go.setProperty("secondary", True)
        self._empty_go.clicked.connect(self.navigate_requested.emit)
        self._empty_clear = QPushButton("清除筛选条件")
        self._empty_clear.setProperty("secondary", True)
        self._empty_clear.clicked.connect(self._clear_filters)
        lay.addWidget(self._empty_title)
        lay.addWidget(self._empty_hint)
        lay.addWidget(self._empty_go, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty_clear, 0, Qt.AlignmentFlag.AlignCenter)
        return w

    def _refresh_empty_state(self, shown: int) -> None:
        """shown=当前筛选后的条数。空库→引导去工坊；有库但筛选空→引导清筛选。"""
        total = self.library.stats().get("total", 0)
        is_empty = shown == 0
        self._empty_state.setVisible(is_empty)
        self.list_widget.setVisible(not is_empty)
        if not is_empty:
            return
        if total == 0:
            self._empty_title.setText("还没有 mod")
            self._empty_hint.setText(
                "在「工坊浏览」页选择 mod 后点击下载，\n"
                "下载完成会自动登记到这里；也可以直接导入已有目录。"
            )
            self._empty_go.setVisible(True)
            self._empty_clear.setVisible(False)
        else:
            self._empty_title.setText("没有匹配的 mod")
            self._empty_hint.setText("当前筛选条件下没有结果，试试放宽条件。")
            self._empty_go.setVisible(False)
            self._empty_clear.setVisible(True)

    def _clear_filters(self) -> None:
        """清空关键词/游戏/分类/启用/收藏筛选后刷新。"""
        self.search_edit.clear()
        self.appid_combo.setCurrentIndex(0)
        self.category_combo.setCurrentIndex(0)
        for cb in (self.only_enabled, self.only_disabled, self.only_fav):
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.refresh()

    def _on_image_loaded(self, url: str, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            return
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            rec = self.library.get(item.data(Qt.ItemDataRole.UserRole))
            if rec and rec.preview_url == url:
                item.setIcon(pixmap)

    # ------------------------------------------------------------- 操作
    def _selected_ids(self) -> list[str]:
        # selectedIndexes() 返回 QModelIndex，必须取 .row() 再换 item
        # （旧代码把 QModelIndex 直接传给 item() 导致右键崩溃，bug5）
        return [
            self.list_widget.item(idx.row()).data(Qt.ItemDataRole.UserRole)
            for idx in self.list_widget.selectedIndexes()
            if idx.row() >= 0
        ]

    # ------------------------------------------------- C1（1.4.1）库更新检查
    def _check_updates(self) -> None:
        """手动触发：比对 Steam 最新 time_updated，结果标红 + 一键入队。

        硬约束落实：
        1. bypass api_cache —— 走 api.check_updates（内部 _api_post 直连，
           绝不读旧快照）；
        2. 大库进度反馈 —— daemon 线程跑，状态栏实时显示「已检查 x/y 批」，
           按钮在运行期间禁用防重入；
        3. 首版只标红/角标 + 询问后一键入队（不自动重下）；
        4. 网络或限流失败弹提示，不崩。
        """
        if self._check_thread is not None and self._check_thread.is_alive():
            return                                            # 防重入
        recs = self.library.all()
        # 无本地快照（time_updated=0）的条目无法比对，提示但不阻塞
        snapshotted = [r for r in recs if r.time_updated > 0]
        if not snapshotted:
            QMessageBox.information(
                self, "检查更新",
                "库内没有带时间戳快照的 mod（全部为 0），无法比对。\n"
                "新下载的 mod 完成时会自动记录 time_updated。",
            )
            return
        self._check_cancel = False
        self._updated_ids = set()
        self.check_updates_btn.setEnabled(False)
        self.check_updates_btn.setText("🔍 检查中…")

        def _worker() -> None:
            try:
                updated = self.svc.api.check_updates(
                    [(r.item_id, r.time_updated) for r in snapshotted],
                    progress=_report,
                    cancel=lambda: self._check_cancel,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("库更新检查失败: %s", e)
                updated = None
            # A6：Signal(list) 跨线程投递到 GUI 线程（queued 由 Qt 保证），
            # 失败也必须 emit，否则按钮永久卡在「检查中」
            self.updates_checked.emit(updated or [])

        def _report(done: int, total: int) -> None:
            # 进度经信号回 GUI 线程（线程安全；A6：Signal 替代 Q_ARG(int)）
            self.check_progress.emit(done, total)

        import threading as _threading

        self._check_thread = _threading.Thread(
            target=_worker, name="swdm-lib-update-check", daemon=True,
        )
        self._check_thread.start()

    @Slot(int, int)
    def _set_check_progress(self, done: int, total: int) -> None:
        """检查进度（GUI 线程）：按钮文本实时显示已比对条数。"""
        if total > 0:
            self.check_updates_btn.setText(f"🔍 检查中 {done}/{total}")

    @Slot(list)
    def _on_check_updates_done(self, updated: list) -> None:
        """检查结束（GUI 线程）：恢复按钮、标红、询问一键入队。"""
        self.check_updates_btn.setEnabled(True)
        self.check_updates_btn.setText("🔍 检查更新")
        if not updated:
            QMessageBox.information(
                self, "检查更新", "没有发现需要更新的 mod。",
            )
            return
        self._updated_ids = set(updated)
        self.refresh()                                        # 触发 _populate 标红
        to_update = ", ".join(updated[:8]) + ("…" if len(updated) > 8 else "")
        ans = QMessageBox.question(
            self, "发现更新",
            f"{len(updated)} 个 mod 有新版本：\n{to_update}\n\n"
            f"现在加入下载队列重新下载？（不会自动开始下载之外的操作）",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        # 一键入队：从库记录重建 WorkshopItem，走标准队列（零状态机改动）
        from swdm.core.steam_api import WorkshopItem

        ok_ids: list[str] = []
        for item_id in updated:
            rec = self.library.get(item_id)
            if rec is None:
                continue
            self.svc.downloader.enqueue(
                WorkshopItem(
                    publishedfileid=rec.item_id,
                    appid=rec.appid,
                    title=rec.title,
                    preview_url=rec.preview_url,
                    file_size=rec.file_size,
                ),
                rec.appid,
            )
            ok_ids.append(item_id)
        # 入队后清除标红（已在队列里，不需要持续红色提示）
        self._updated_ids = set()
        self.refresh()
        QMessageBox.information(
            self, "已加入队列",
            f"{len(ok_ids)} 个 mod 已加入下载队列。",
        )

    def _set_selected_enabled(self, enabled: bool) -> None:
        for item_id in self._selected_ids():
            self.library.set_enabled(item_id, enabled)
        self.refresh()

    def _context_menu(self, pos) -> None:
        # bug6：右键时光标下若未选中，菜单拿不到 id 直接返回，
        # 用户感觉"无法删除"。先自动选中右键处的项目
        item_at = self.list_widget.itemAt(pos)
        if item_at is not None and not item_at.isSelected():
            self.list_widget.setCurrentItem(item_at)
        ids = self._selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        act_enable = menu.addAction("启用")
        act_disable = menu.addAction("禁用")
        menu.addSeparator()
        act_fav = menu.addAction("切换收藏")
        act_cat = menu.addAction("设置分类…")
        act_notes = menu.addAction("编辑备注…")
        menu.addSeparator()
        act_open = menu.addAction("在资源管理器打开")
        act_remove = menu.addAction("移除记录（保留文件）")
        act_remove_files = menu.addAction("移除并删除文件")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == act_enable:
            self._set_selected_enabled(True)
        elif action == act_disable:
            self._set_selected_enabled(False)
        elif action == act_fav:
            for i in ids:
                rec = self.library.get(i)
                if rec:
                    self.library.set_favorite(i, not rec.favorite)
            self.refresh()
        elif action == act_cat:
            text, ok = QInputDialog.getText(self, "设置分类", "分类名称：")
            if ok and text.strip():
                for i in ids:
                    self.library.set_category(i, text.strip())
                self.refresh()
        elif action == act_notes:
            first = self.library.get(ids[0])
            text, ok = QInputDialog.getText(self, "编辑备注", "备注：", text=first.notes if first else "")
            if ok:
                self.library.set_notes(ids[0], text)
                self.refresh()
        elif action == act_open:
            rec = self.library.get(ids[0])
            if rec and rec.local_path:
                self._open_folder_by_path(rec.local_path)
        elif action == act_remove:
            for i in ids:
                self.library.delete(i, remove_files=False)
            self.records_removed.emit(list(ids))
            self.refresh()
        elif action == act_remove_files:
            if QMessageBox.question(
                self, "确认删除",
                f"将永久删除 {len(ids)} 个 mod 的文件，确定继续？",
            ) == QMessageBox.StandardButton.Yes:
                for i in ids:
                    self.library.delete(i, remove_files=True)
                self.records_removed.emit(list(ids))
                self.refresh()

    def _open_folder(self, item: QListWidgetItem) -> None:
        rec = self.library.get(item.data(Qt.ItemDataRole.UserRole))
        if rec and rec.local_path:
            self._open_folder_by_path(rec.local_path)

    @staticmethod
    def _open_folder_by_path(path: str) -> None:
        import subprocess

        if path and path.startswith("/"):
            path = path.replace("/", "\\", 1)
        try:
            subprocess.Popen(["explorer", path])
        except OSError as e:
            log.warning("无法打开目录 %s: %s", path, e)

    def _import_existing(self) -> None:
        appid = self.appid_combo.currentData() or ""
        if not appid:
            appid, ok = QInputDialog.getText(self, "导入", "输入目标游戏的 AppID：")
            if not ok or not appid.strip().isdigit():
                return
            appid = appid.strip()
        lib_dir = self.svc.config.get("general", "library_dir") or LIBRARY_DIR
        folder = QFileDialog.getExistingDirectory(self, "选择 steamapps 根目录", lib_dir)
        if not folder:
            return
        n = self.library.import_existing(folder, appid)
        QMessageBox.information(self, "导入完成", f"已导入 {n} 个 mod")
        self.refresh()

    def _export_list(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 mod 列表", "swdm_mods.json", "JSON (*.json)"
        )
        if not path:
            return
        import json

        # B③：导出当前筛选结果（与列表显示一致），而非全库
        recs = [r.to_dict() for r in self.library.search(**self._current_filter())]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(recs, f, ensure_ascii=False, indent=2)
            QMessageBox.information(
                self, "导出完成",
                f"已导出 {len(recs)} 条记录（当前筛选结果）到\n{path}")
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _import_list(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 mod 列表", "", "JSON (*.json)"
        )
        if not path:
            return
        import json

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "导入失败", f"无法读取文件: {e}")
            return
        if not isinstance(data, list):
            # 非 JSON 数组（如 {item_id: ...} 的字典）：旧代码直接 for d in data
            # 遍历字典得到字符串键，d["item_id"] 抛 TypeError 崩掉点击处理器
            QMessageBox.critical(self, "导入失败", "文件内容不是 mod 记录数组")
            return
        n = 0
        for d in data:
            try:
                rec = ModRecord(
                    item_id=str(d["item_id"]),
                    appid=str(d.get("appid", "")),
                    title=d.get("title", ""),
                    description=d.get("description", ""),
                    creator=d.get("creator", ""),
                    creator_name=d.get("creator_name", ""),
                    file_size=int(d.get("file_size", 0) or 0),
                    subscriptions=int(d.get("subscriptions", 0) or 0),
                    tags=d.get("tags", []),
                    preview_url=d.get("preview_url", ""),
                    local_path=d.get("local_path", ""),
                    installed=bool(d.get("installed", False)),
                    enabled=bool(d.get("enabled", True)),
                    category=d.get("category", ""),
                    notes=d.get("notes", ""),
                    favorite=bool(d.get("favorite", False)),
                    download_time=int(d.get("download_time", 0) or 0),
                    time_updated=int(d.get("time_updated", 0) or 0),
                    source=d.get("source", "imported"),
                )
                self.library.upsert(rec)
                n += 1
            except (KeyError, TypeError) as e:
                log.warning("跳过无效记录: %s", e)
        QMessageBox.information(self, "导入完成", f"已导入 {n} 条记录")
        self.refresh()
