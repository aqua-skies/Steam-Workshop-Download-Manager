"""GUI 自动化冒烟测试：启动 → 浏览 → 下载 → 截图 → 退出。

用 QTimer 驱动自动操作，无需人工点击。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, ".")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from swdm.core import get_logger, setup_logger
from swdm.core.config import get_config
from swdm.core.paths import ensure_dirs

setup_logger("DEBUG")
log = get_logger("swdm.test.gui")
ensure_dirs()

SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SHOT_DIR, exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv)
cfg = get_config()

from swdm.gui import MainWindow, install_exception_handler

install_exception_handler()
win = MainWindow()
win.show()

state = {"phase": 0, "t0": time.time()}
phases_log = []


def shot(name: str) -> None:
    screen = app.primaryScreen()
    pix: QPixmap = screen.grabWindow(win.winId())
    path = os.path.join(SHOT_DIR, name)
    pix.save(path, "PNG")
    phases_log.append(f"截图: {name} ({pix.width()}x{pix.height()})")


def step() -> None:
    el = time.time() - state["t0"]
    p = state["phase"]
    try:
        if p == 0 and el > 1.5:
            log.info("[GUI测试] 阶段1：主窗口已显示")
            shot("01_main.png")
            state["phase"] = 1
        elif p == 1 and el > 2.5:
            # 触发工坊浏览（默认已选 GMod）
            log.info("[GUI测试] 阶段2：触发浏览")
            win.workshop_tab._refresh_list()
            state["phase"] = 2
        elif p == 2 and el > 9.0:
            n = win.workshop_tab.list_widget.count()
            log.info("[GUI测试] 阶段3：列表项数量 = %d", n)
            shot("02_workshop.png")
            state["phase"] = 3
        elif p == 3 and el > 10.5:
            # 选最小的一项下载（快速验证）
            if win.workshop_tab.list_widget.count() > 0:
                log.info("[GUI测试] 阶段4：下载最小的 mod")
                items = win.workshop_tab._items
                smallest = min(items, key=lambda i: i.file_size or 10**12) if items else None
                pid = smallest.publishedfileid if smallest else None
                if not pid:
                    item = win.workshop_tab.list_widget.item(0)
                    pid = item.data(Qt.ItemDataRole.UserRole)
                log.info("[GUI测试] 选中 %s (size=%s)", pid,
                         smallest.file_size if smallest else "?")
                win.workshop_tab._download_item(pid)
            win._tabs.setCurrentIndex(1)
            state["phase"] = 4
        elif p == 4 and el > 14.0:
            log.info("[GUI测试] 阶段5：下载队列页")
            shot("03_downloads.png")
            state["phase"] = 5
        elif p == 5 and el > 18.0:
            win._tabs.setCurrentIndex(2)
            win.library_tab.refresh()
            shot("04_library.png")
            state["phase"] = 6
        elif p == 6 and el > 21.0:
            win._tabs.setCurrentIndex(3)
            shot("05_settings.png")
            state["phase"] = 7
        elif p == 7 and el > 24.0:
            win._tabs.setCurrentIndex(4)
            shot("06_debug.png")
            state["phase"] = 8
        elif p == 8 and el > 27.0:
            # 回到工坊页，最终截图
            win._tabs.setCurrentIndex(0)
            shot("07_final.png")
            state["phase"] = 9
        elif p == 9 and el > 32.0:
            snap = win.svc.downloader.snapshot()
            stats = win.svc.library.stats()
            summary = {
                "workshop_items": win.workshop_tab.list_widget.count(),
                "active_downloads": len(snap["active"]),
                "done_downloads": len(snap["done"]),
                "library_total": stats["total"],
                "library_size_mb": round(stats["size"] / 1024 / 1024, 1),
            }
            log.info("[GUI测试] 汇总: %s", summary)
            with open(os.path.join(SHOT_DIR, "summary.json"), "w", encoding="utf-8") as f:
                import json

                json.dump({"summary": summary, "phases": phases_log}, f,
                          ensure_ascii=False, indent=2)
            ok = summary["workshop_items"] > 0 and summary["library_total"] > 0
            with open(os.path.join(SHOT_DIR, "result.txt"), "w", encoding="utf-8") as f:
                f.write("PASS" if ok else "FAIL\n" + str(summary))
            log.info("[GUI测试] 结果: %s", "PASS" if ok else "FAIL")
            try:
                win.svc.downloader.stop()
            except Exception:
                pass
            app.quit()
    except Exception:
        log.exception("[GUI测试] 步骤异常")
        with open(os.path.join(SHOT_DIR, "result.txt"), "w", encoding="utf-8") as f:
            f.write("EXCEPTION\n")
        app.quit()


timer = QTimer()
timer.timeout.connect(step)
timer.start(300)

# 总超时保护
QTimer.singleShot(90000, app.quit)

code = app.exec()
log.info("[GUI测试] 退出 code=%s", code)
sys.exit(0 if os.path.exists(os.path.join(SHOT_DIR, "result.txt")) else 1)
