"""t10 探针：test_gui_sweep 下载页 6 FAIL 因果证明。
复制该脚本的精确序列：_populate 3 卡 → _download_item("1000") →
立即清理（clear_completed/_queue/_active/row_map/rows）→ 等 5 秒
→ 观察 ghost 行是否在清理之后异步生成。"""
import io
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_ghost_")
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

from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab
dt = win.downloads_tab
wt._fetch_tags = lambda: None

items = [WorkshopItem(publishedfileid=str(1000 + i), title=f"Sweep Mod {i}",
                     appid="4000", file_size=1024, tags=["t"])
         for i in range(3)]
wt._populate(items)
app.processEvents()

def _rows():
    return [[dt.table.item(r, c).text() if dt.table.item(r, c) else ""
             for c in range(7)] for r in range(dt.table.rowCount())]

print("[A] 下载前 rowCount:", dt.table.rowCount(), flush=True)
wt._download_item("1000")
app.processEvents()
print("[B] _download_item 后 rowCount:", dt.table.rowCount(),
      "row_map:", sorted(dt._row_map.keys()), flush=True)

# 清理段（与 test_gui_sweep 204-216 相同）
try:
    win.svc.downloader.clear_completed()
except Exception:
    pass
try:
    with win.svc.downloader._lock:
        win.svc.downloader._queue.clear()
        win.svc.downloader._active.clear()
except Exception:
    pass
dt._row_map.clear()
while dt.table.rowCount():
    dt.table.removeRow(0)
print("[C] 清理后 rowCount:", dt.table.rowCount(), flush=True)

t0 = time.time()
while time.time() - t0 < 5.0:
    app.processEvents()
    time.sleep(0.05)
print("[D] +5s rowCount:", dt.table.rowCount(),
      "row_map:", sorted(dt._row_map.keys()), flush=True)
print("    rows:", _rows(), flush=True)
snap = win.svc.downloader.snapshot()
print("    snap:", {k: [(j.id, j.status.value) for j in v]
                   for k, v in snap.items()}, flush=True)
print("    row_map 内容:", {k: v for k, v in dt._row_map.items()}, flush=True)
