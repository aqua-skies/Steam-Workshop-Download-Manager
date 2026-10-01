"""t10 探针：test_gui_sweep 下载页 6 FAIL 复现——MainWindow 启动后
dt.table 为什么在 add_pending 前就非空？"""
import io
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_sweep_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_WF = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WF):
    os.environ.setdefault("QT_QPA_FONTDIR", _WF)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

_cap = io.StringIO()
_real = sys.stderr
sys.stderr = _cap

from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
t0 = time.time()
while time.time() - t0 < 3.0:
    app.processEvents()
    time.sleep(0.05)

sys.stderr = _real
dt = win.downloads_tab
print("rowCount:", dt.table.rowCount(), flush=True)
print("row_map:", sorted(dt._row_map.keys()), flush=True)
for r in range(dt.table.rowCount()):
    cells = [dt.table.item(r, c).text() if dt.table.item(r, c) else ""
             for c in range(6)]
    print(f"  row{r}: {cells}", flush=True)
snap = win.svc.downloader.snapshot()
print("snap:", {k: [(j.id, j.status.value) for j in v] for k, v in snap.items()},
      flush=True)
try:
    cb = QApplication.clipboard()
    print("clipboard:", repr(cb.text()[:120]), flush=True)
except Exception as e:
    print("clipboard err:", e, flush=True)
print("statusbar:", win.statusBar().currentMessage()[:80], flush=True)
txt = _cap.getvalue()
print("stderr_has_traceback:", "Traceback" in txt, flush=True)
for line in txt.splitlines():
    if "下载" in line or "Traceback" in line or "clipboard" in line.lower():
        print("  |", line.strip()[:120], flush=True)
