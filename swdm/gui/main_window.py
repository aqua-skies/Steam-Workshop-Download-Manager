"""Main window: tab integration (Workshop / Downloads / Library / Settings / Debug) plus tray, single instance and crash handling (主窗口).

The Debug tab (调试页) is hidden by default since t22 and toggled from Settings.
Tray exit goes through ``_do_real_quit()`` so a hidden window still quits cleanly (t11).
Cross-tab signals are wired here: ``library_changed`` (download → library refresh) and
``records_removed`` (library → download row removal, t13 双向互通).
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from swdm.core import APP_DISPLAY, APP_VERSION, get_logger
from swdm.core.paths import CRASH_FILE, LOG_DIR, resource_path

log = get_logger("swdm.gui.main")

# Inno Setup AppMutex 同名互斥量（installer/swdm.iss 的 AppMutex 指令引用）。
# 主程序启动时创建并持有，安装/卸载程序据此检测运行中的实例。
APP_MUTEX_NAME = "SWDM_SingleInstance_Mutex"


class MainWindow(QMainWindow):
    """Top-level window: builds every tab, the tray icon and the signal wiring between tabs."""

    def __init__(self) -> None:
        super().__init__()
        self._force_quit = False
        self._app_mutex = None
        self.setWindowTitle(f"{APP_DISPLAY} v{APP_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self._build()
        self._apply_theme()
        self._create_app_mutex()

    def _build(self) -> None:
        from swdm.gui.debug_tab import DebugTab
        from swdm.gui.downloads_tab import DownloadsTab
        from swdm.gui.library_tab import LibraryTab
        from swdm.gui.services import build_services
        from swdm.gui.settings_tab import SettingsTab
        from swdm.gui.workshop_tab import WorkshopTab

        self.svc = build_services()
        self.svc.downloader.start()

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tabs = QTabWidget()
        lay.addWidget(self._tabs, 1)

        self.workshop_tab = WorkshopTab(self.svc)
        self.downloads_tab = DownloadsTab(self.svc)
        self.library_tab = LibraryTab(self.svc)
        self.settings_tab = SettingsTab(self.svc)
        self.debug_tab = DebugTab(self.svc)

        self._tabs.addTab(self.workshop_tab, "🌐 工坊浏览")
        self._tabs.addTab(self.downloads_tab, "⬇ 下载")
        self._tabs.addTab(self.library_tab, "🗂 我的模组库")
        self._tabs.addTab(self.settings_tab, "⚙ 设置")
        # B④：调试 Tab 默认隐藏（始终创建实例，保持 win.debug_tab 属性可用）
        # 设置页勾选"显示调试面板"后保存，下次启动生效
        if self.svc.config.get("logging", "show_debug_panel", default=False):
            self._tabs.addTab(self.debug_tab, "🐛 调试")

        # 下载完成时刷新库页（回调在子线程，经信号桥接回主线程）
        from swdm.gui.workers import DownloadEventBridge

        self._main_bridge = DownloadEventBridge()
        self._main_bridge.finished.connect(self._on_download_finished)
        # F4：完成时托盘通知
        self._main_bridge.finished.connect(self._notify_download_finished)
        self.svc.downloader.add_listener(
            finished=self._main_bridge.finished.emit
        )

        self.settings_tab.settings_changed.connect(self._on_settings_changed)
        # u10：下载页移除已入库 mod → 刷新库页；库页移除记录 → 清下载页旧行
        self.downloads_tab.library_changed.connect(self._on_library_changed)
        self.library_tab.records_removed.connect(
            self.downloads_tab.remove_rows_for
        )
        # 点击下载后切换到下载页（即时反馈，bug1）
        self.workshop_tab.show_downloads.connect(
            lambda: self._tabs.setCurrentWidget(self.downloads_tab)
        )

        statusbar = QStatusBar(self)
        self.setStatusBar(statusbar)
        statusbar.showMessage("就绪")
        self.status_label = QLabel("")
        statusbar.addPermanentWidget(self.status_label)
        self._refresh_status_bar()

        # F4：系统托盘 + 下载完成通知
        self._build_tray()

    # ------------------------------------------------------------- F4 托盘
    def _build_tray(self) -> None:
        # offscreen/无桌面环境时 isSystemTrayAvailable() 为 False，
        # 此时不下拉托盘，closeEvent 走正常退出路径（测试环境也走这里）
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            log.debug("系统托盘不可用，跳过")
            return
        from PySide6.QtGui import QIcon, QPixmap

        self._tray = QSystemTrayIcon(self)
        pix = QPixmap(64, 64)
        pix.fill(QColor("#5f8fd0"))
        self._tray.setIcon(QIcon(pix))
        self._tray.setToolTip(APP_DISPLAY)
        menu = QMenu(self)
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self._show_from_tray)
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _real_quit(self) -> None:
        # 窗口处于隐藏态（在托盘里）时，QWidget.close() 对不可见窗口直接
        # 返回 true 且不发送 QCloseEvent（Qt 行为），closeEvent 的真正退出
        # 逻辑因此被跳过，进程残留后台。故托盘退出不依赖 close() 转发，
        # 直接执行真正退出。
        self._force_quit = True
        self._do_real_quit()

    def _do_real_quit(self) -> None:
        """真正退出：停止下载管理器、保存配置、释放互斥量、退出应用。

        托盘"退出"与 closeEvent 的真正退出分支共用此路径，避免重复逻辑。
        """
        log.info("真正退出：停止下载管理器…")
        try:
            self.svc.downloader.stop()
        except Exception:  # noqa: BLE001
            log.warning("停止下载管理器失败")
        try:
            self.svc.config.save()
        except Exception:  # noqa: BLE001
            pass
        self._release_app_mutex()
        QCoreApplication.quit()

    # --------------------------------------------- AppMutex（安装/卸载检测）
    def _create_app_mutex(self) -> None:
        """创建全局命名互斥量（与 installer/swdm.iss 的 AppMutex 同名）。

        Inno Setup 安装/卸载程序据此检测运行中的实例；本进程退出时释放。
        非 Windows 或创建失败时静默跳过，不阻断启动。
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # restype 必须显式设为指针：默认 c_int 会把 64 位句柄截断
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p,
            ]
            kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
            if not handle:
                return
            self._app_mutex = (kernel32, handle)
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                log.warning("检测到另一个 SWDM 实例正在运行（AppMutex 已存在）")
            # 兜底：closeEvent 未被调用的退出路径（如 QApp.quit）也释放互斥量
            app_inst = QCoreApplication.instance()
            if app_inst is not None:
                app_inst.aboutToQuit.connect(self._release_app_mutex)
        except Exception:  # noqa: BLE001
            log.debug("创建 AppMutex 失败（忽略）")

    def _release_app_mutex(self) -> None:
        """释放互斥量（重复调用安全）。"""
        if self._app_mutex is None:
            return
        try:
            kernel32, handle = self._app_mutex
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            pass
        self._app_mutex = None

    def _on_tray_activated(self, reason) -> None:
        # 双击/单击托盘图标恢复窗口
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._show_from_tray()

    def _notify_download_finished(self, job) -> None:
        """下载完成时托盘弹通知（窗口最小化时尤其有用）。"""
        if self._tray is None:
            return
        try:
            title = "下载完成" if job.status.value == "success" else "下载失败"
            self._tray.showMessage(
                title,
                f"{job.item.title or job.id}\n{job.message or ''}",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        except Exception:  # noqa: BLE001
            pass

    def _apply_theme(self) -> None:
        from swdm.core.config import get_config
        from swdm.gui.styles import qss

        theme = get_config().get("general", "theme") or "dark"
        self.setStyleSheet(qss(theme))
        try:
            icon_path = resource_path("swdm", "resources", "icon.ico")
            self.setWindowIcon(QIcon(icon_path))
        except Exception:  # noqa: BLE001
            pass

    def _refresh_status_bar(self) -> None:
        stats = self.svc.library.stats()
        mode = "匿名" if self.svc.auth.is_anonymous() else self.svc.auth.account.username
        self.status_label.setText(
            f"模式: {mode}  |  本地 mod: {stats['total']}  |  版本 {APP_VERSION}"
        )

    # ------------------------------------------------------------- 事件
    def _on_download_finished(self, job) -> None:
        self.library_tab.refresh()
        self._refresh_status_bar()

    def _on_library_changed(self) -> None:
        # u10：下载页移除已入库记录后刷新库页（无 job 参数，与 bridge 信号分流）
        self.library_tab.refresh()
        self._refresh_status_bar()

    def _on_settings_changed(self) -> None:
        self.workshop_tab.refresh_login_ui()
        self._refresh_status_bar()

    def closeEvent(self, event) -> None:
        # F4：有托盘且窗口可见时，关闭按钮改为最小化到托盘（真正的退出走托盘菜单）。
        # 窗口已隐藏（最小化在托盘）时收到 QCloseEvent，必然是外部进程发出的
        # 关闭请求（例如 Inno 卸载程序通过 CloseApplications 发来的 WM_CLOSE），
        # 此时必须真正退出，否则卸载完成后进程与文件残留（卸载残留 bug）。
        if not self._force_quit and self.isVisible() and \
                getattr(self, "_tray", None) is not None and self._tray.isVisible():
            self.hide()
            event.ignore()
            try:
                self._tray.showMessage(
                    APP_DISPLAY, "已最小化到托盘，双击图标恢复窗口。",
                    QSystemTrayIcon.MessageIcon.Information, 2000,
                )
            except Exception:  # noqa: BLE001
                pass
            return
        log.info("主窗口关闭，停止下载管理器…")
        self._do_real_quit()
        super().closeEvent(event)


def install_exception_handler() -> None:
    """全局异常钩子：未捕获异常写入 crash.log 并提示。"""
    from swdm.core.paths import ensure_dirs

    def handler(exc_type, exc_value, exc_tb) -> None:
        try:
            ensure_dirs()
            with open(CRASH_FILE, "a", encoding="utf-8") as f:
                f.write("==== 未捕获异常 ====\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:  # noqa: BLE001
            pass
        log.error("未捕获异常: %s: %s", exc_type.__name__, exc_value)
        try:
            QMessageBox.critical(
                None, "程序错误",
                f"发生未捕获异常：{exc_type.__name__}: {exc_value}\n"
                f"详细信息已写入 {CRASH_FILE}",
            )
        except Exception:  # noqa: BLE001
            pass

    import sys

    sys.excepthook = handler
