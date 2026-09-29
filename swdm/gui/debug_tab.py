"""调试页：实时日志流 + 历史回看 + 快速诊断命令（需求 3）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from swdm.core import logger as logmod
from swdm.core.logger import get_logger, snapshot, subscribe, unsubscribe

log = get_logger("swdm.gui.debug")


class DebugTab(QWidget):
    """调试系统页：实时日志 + 任务历史 + 诊断。"""

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.svc = services
        self._autoscroll = True
        self._build()
        # 订阅实时日志
        subscribe(self._on_log_entry)
        # 回填历史缓冲
        for entry in snapshot():
            self._append_entry(entry)
        self._load_job_history()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("实时日志"))
        toolbar.addStretch()
        self.autoscroll_check = QPushButton("自动滚动: 开")
        self.autoscroll_check.setProperty("secondary", True)
        self.autoscroll_check.setCheckable(True)
        self.autoscroll_check.setChecked(True)
        self.autoscroll_check.toggled.connect(self._toggle_autoscroll)
        toolbar.addWidget(self.autoscroll_check)

        clear_btn = QPushButton("清空显示")
        clear_btn.setProperty("secondary", True)
        clear_btn.clicked.connect(self._clear_log)
        toolbar.addWidget(clear_btn)

        self.export_btn = QPushButton("导出日志…")
        self.export_btn.setProperty("secondary", True)
        self.export_btn.clicked.connect(self._export_log)
        toolbar.addWidget(self.export_btn)

        diag_btn = QPushButton("🩺 诊断")
        diag_btn.clicked.connect(self._run_diagnostics)
        toolbar.addWidget(diag_btn)
        root.addLayout(toolbar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_view.setStyleSheet(
            "QTextEdit { background:#14161a; color:#c8d0da; font-family: Consolas,"
            " 'Cascadia Mono', monospace; font-size: 11px; }"
        )
        root.addWidget(self.log_view, 3)

        # 任务历史
        hist_label = QLabel("下载任务历史")
        hist_label.setStyleSheet("color:#9aa0aa; font-weight:600;")
        root.addWidget(hist_label)
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("QListWidget { font-size: 11px; }")
        root.addWidget(self.history_list, 1)

    # ------------------------------------------------------------- 日志
    def _append_entry(self, entry: dict) -> None:
        if self.log_view is None:
            return
        color = {
            "ERROR": "#e06060",
            "WARNING": "#e0a040",
            "CRITICAL": "#ff5050",
            "DEBUG": "#707880",
            "INFO": "#9aa0aa",
        }.get(entry.get("level", "INFO"), "#9aa0aa")
        msg = entry.get("message", "").replace("<", "&lt;").replace(">", "&gt;")
        html = (
            f"<span style='color:#4a5159'>{entry.get('time','')}</span> "
            f"<span style='color:{color};font-weight:600'>[{entry.get('level','')}]</span> "
            f"<span style='color:#6a7078'>{entry.get('name','')}:</span> {msg}"
        )
        self.log_view.append(html)
        if self._autoscroll:
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum()
            )

    @Slot(dict)
    def _on_log_entry(self, entry: dict) -> None:
        self._append_entry(entry)

    def _toggle_autoscroll(self, checked: bool) -> None:
        self._autoscroll = checked
        self.autoscroll_check.setText(f"自动滚动: {'开' if checked else '关'}")

    def _clear_log(self) -> None:
        self.log_view.clear()

    def _export_log(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "swdm_debug.log", "日志 (*.log)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log_view.toPlainText())
        except OSError as e:
            log.warning("导出日志失败: %s", e)

    # ------------------------------------------------------------- 历史
    def _load_job_history(self) -> None:
        self.history_list.clear()
        try:
            for j in self.svc.library.job_history(limit=200):
                status = j.get("status", "")
                icon = {"success": "✓", "failed": "✗", "cancelled": "⊘"}.get(status, "·")
                text = (
                    f"{icon} [{status}] {j.get('item_id')} "
                    f"{j.get('title','')[:50]} — {j.get('message','')[:80]}"
                )
                item = QListWidgetItem(text)
                if status == "failed":
                    item.setForeground(Qt.GlobalColor.red)
                elif status == "success":
                    item.setForeground(Qt.GlobalColor.darkGreen)
                self.history_list.addItem(item)
        except Exception as e:  # noqa: BLE001
            log.warning("加载任务历史失败: %s", e)

    # ------------------------------------------------------------- 诊断
    def _run_diagnostics(self) -> None:
        import json as _json
        import os as _os

        lines: list[str] = []

        def out(msg: str) -> None:
            lines.append(msg)
            log.info("[诊断] %s", msg)

        try:
            cfg = self.svc.config
            out(f"配置文件: {cfg.get('general') and 'OK'}")
            out(f"匿名模式: {self.svc.auth.is_anonymous()}")
            out(f"steamcmd.exe: {self.svc.engine.resolve_exe()}")
            out(f"安装目录: {self.svc.engine.install_dir}")
            out(f"库统计: {self.svc.library.stats()}")
            # 网络连通性
            ok = self.svc.api.ping()
            out(f"Steam API 连通性: {'OK' if ok else '失败'}")
            # steamcmd 登录
            ok2, msg2 = self.svc.engine.test_login()
            out(f"steamcmd 登录: {'OK' if ok2 else '失败'} - {msg2}")
        except Exception as e:  # noqa: BLE001
            out(f"诊断异常: {e}")
        self.log_view.append("<span style='color:#4a9bff'>===== 诊断完成 =====</span>")
        for ln in lines:
            self.log_view.append(
                f"<span style='color:#4a9bff'>[诊断]</span> "
                f"<span style='color:#c8d0da'>{ln.replace('<','&lt;').replace('>','&gt;')}</span>"
            )

    def closeEvent(self, event) -> None:
        try:
            unsubscribe(self._on_log_entry)
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
