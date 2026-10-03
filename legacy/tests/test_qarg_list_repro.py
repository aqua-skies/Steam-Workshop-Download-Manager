"""最小回归：C1 完成回调使用 Qt Signal(list)（A6 修复后行为）。

1.4.1 打包前修复：`QMetaObject.invokeMethod + Q_ARG(list, ...)` 在本机 PySide6
抛 `RuntimeError: qArgDataFromPyType: Unable to find a QMetaType for "list"`，
bare Python list 不能作为 QueuedConnection 的参数。library_tab.py 的 C1 完成
回调因此改为 `updates_checked = Signal(list)`，worker 线程直接 emit，由 Qt
自动排队到 GUI 线程。本脚本验证该修复路径可用。
"""
import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_qarg_")
os.environ["APPDATA"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QObject, Signal, Slot  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


class O(QObject):
    done = Signal(list)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.done.connect(self._on_done, type="QueuedConnection")

    @Slot(list)
    def _on_done(self, updated):
        self.calls.append(list(updated))


o = O()
worker_error = []


def _worker():
    try:
        o.done.emit(["111", "222"])
    except Exception as e:  # noqa: BLE001
        worker_error.append(f"{type(e).__name__}: {e}")


t = threading.Thread(target=_worker, daemon=True)
t.start()
t.join(timeout=5)

deadline = time.time() + 2.0
while not o.calls and time.time() < deadline:
    app.processEvents()
    time.sleep(0.01)

check("Signal(list) 在工作线程 emit 无异常", not worker_error, str(worker_error))
check("GUI 线程 slot 收到一次调用", len(o.calls) == 1, f"calls={o.calls}")
check("列表内容完整透传", o.calls == [["111", "222"]], str(o.calls))

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
