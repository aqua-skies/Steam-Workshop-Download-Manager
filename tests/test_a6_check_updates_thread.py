"""A6 回归：C1 库更新检查的真实线程完成路径。

1.4.1 打包前修复：`_check_updates` 的 daemon worker 原先使用
`QMetaObject.invokeMethod(..., Q_ARG(list, ...))` 回 GUI 线程；bare Python
list 在本机 PySide6 没有 QMetaType，调用抛 RuntimeError，完成回调从未触发，
按钮永久卡在「检查中…」。本测试从按钮点击开始，完整验证：
button click → daemon worker → Signal(list) → GUI 线程收尾 → 按钮恢复。
不直接调用 `_on_check_updates_done`，避免再次绕过线程路径。
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_a6_")
os.environ["APPDATA"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, ".")

ok = True


def check(name: str, cond, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

from swdm.core.mod_library import ModRecord  # noqa: E402
from swdm.gui.services import build_services  # noqa: E402
from swdm.gui.library_tab import LibraryTab  # noqa: E402

svc = build_services()
svc.library.upsert(
    ModRecord(item_id="1001", appid="4000", title="A6 Mod", time_updated=1000)
)

tab = LibraryTab(svc)
tab.setParent(None)

dialogs = []
_orig_info = QMessageBox.information
_orig_q = QMessageBox.question
QMessageBox.information = lambda p, t, x, *a, **k: dialogs.append((t, x))
QMessageBox.question = lambda p, t, x, *a, **k: (
    dialogs.append((t, x)),
    QMessageBox.StandardButton.No,
)[1]

done_calls = {"n": 0}


def _done(updated):
    done_calls["n"] += 1
    done_calls["ids"] = list(updated)


tab.updates_checked.connect(_done)


worker_started = threading.Event()


def _fast_check(records, progress=None, cancel=None):
    worker_started.set()
    if progress:
        progress(len(records), len(records))
    # 短暂占线，确保断言能观察到 daemon worker 运行态
    time.sleep(0.2)
    return ["1001"]


svc.api.check_updates = _fast_check

tab.check_updates_btn.click()
check("点击按钮启动 daemon worker", worker_started.wait(timeout=5))
thread = tab._check_thread
check("worker 线程对象存在", thread is not None)
thread.join(timeout=10)

deadline = time.time() + 2.0
while not done_calls["n"] and time.time() < deadline:
    app.processEvents()
    time.sleep(0.01)

check("真实线程路径收到完成信号", done_calls["n"] == 1, str(done_calls))
check("完成信号携带更新列表", done_calls.get("ids") == ["1001"], str(done_calls))
check("按钮恢复可用", tab.check_updates_btn.isEnabled())
check("按钮文案恢复", tab.check_updates_btn.text() == "🔍 检查更新",
      tab.check_updates_btn.text())
check("弹出「发现更新」询问窗", any(t == "发现更新" for t, _ in dialogs), str(dialogs))
check("用户选择「否」时保留标红", tab._updated_ids == {"1001"},
      str(tab._updated_ids))

QMessageBox.information = _orig_info
QMessageBox.question = _orig_q

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
