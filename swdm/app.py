"""SWDM application entry point (Steam Workshop Download Manager / Steam 工坊下载管理器).

Keeps ``main()`` as the single entry and ``if __name__ == '__main__'`` calling it,
so the PyInstaller spec (swdm.spec) and the Inno Setup installer need no changes.
"""
from __future__ import annotations

import sys


def main() -> int:
    """Run the application: build the Qt app, wire the main window, and enter the event loop.

    Returns:
        The Qt exit code.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    # High DPI support / 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from swdm.core import APP_DISPLAY, ensure_dirs, get_logger, setup_logger
    from swdm.core.config import get_config

    ensure_dirs()
    cfg = get_config()
    setup_logger(cfg.get("logging", "level") or "INFO")
    log = get_logger("swdm.app")
    log.info("==== %s 启动 ====", APP_DISPLAY)

    from swdm.gui import MainWindow, install_exception_handler

    install_exception_handler()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY)
    app.setQuitOnLastWindowClosed(True)

    # 单实例保护
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    _SOCKET = "swdm-single-instance"
    existing = QLocalSocket()
    existing.connectToServer(_SOCKET)
    if existing.waitForConnected(300):
        log.warning("已有实例在运行，退出")
        existing.close()
        return 0

    window = MainWindow()
    window.show()

    server = QLocalServer()
    server.listen(_SOCKET)
    app.aboutToQuit.connect(lambda: server.close())

    code = app.exec()
    log.info("应用退出，code=%s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
