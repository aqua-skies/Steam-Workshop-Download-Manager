"""批次1 真 bug 回归测试（B1 排序信号 / B2 库页选择恢复 /
B3 失败重试 / B4 取消全部确认）。"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_b1_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QFileDialog, QInputDialog, QMessageBox,
)

app = QApplication.instance() or QApplication(sys.argv)
QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: os.path.join(_TMP, "d"))
QFileDialog.getOpenFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "f.json"), ""))
QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "s.json"), ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("4000", True))
QInputDialog.getItem = staticmethod(
    lambda *a, **k: (a[2][0] if len(a) > 2 and a[2] else "", True))
# B4：记录 question 调用而非真正弹窗
_q_calls = []
_orig_q = QMessageBox.question
QMessageBox.question = staticmethod(
    lambda *a, **k: (_q_calls.append((a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "")),
                     QMessageBox.StandardButton.Yes)[1])
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()

# ---- B1：排序下拉切换应触发列表刷新
wt = win.workshop_tab
fired = []
wt._refresh_list = lambda: fired.append(1)
wt.sort_combo.setCurrentIndex(2)
app.processEvents()
check("B1 排序切换触发刷新", len(fired) >= 1, str(len(fired)))
check("B1 切到第3项触发的就是那次", len(fired) == 1, str(len(fired)))

# ---- B2：库页 refresh 不恢复选择（此处验证恢复逻辑本身）
from swdm.gui.library_tab import _restore_combo  # noqa: E402
from PySide6.QtWidgets import QComboBox  # noqa: E402

c = QComboBox()
c.addItem("全部游戏", "")
c.addItem("4000", "4000")
c.addItem("500", "500")
c.setCurrentIndex(2)
# 模拟重建：clear 后重填
old = c.currentData()
c.clear()
c.addItem("全部游戏", "")
c.addItem("4000", "4000")
c.addItem("500", "500")
_restore_combo(c, old)
check("B2 重建后恢复旧选择", c.currentData() == "500",
      repr(c.currentData()))
# 数据不存在时回退首项
c.clear()
c.addItem("全部游戏", "")
c.addItem("4000", "4000")
_restore_combo(c, "999999")
check("B2 旧值不存在回退首项", c.currentIndex() == 0, str(c.currentIndex()))

# 真实库页：refresh 两次选择应保持
lt = win.library_tab
lt.refresh()
app.processEvents()
idx = lt.appid_combo.currentIndex()
lt.refresh()
app.processEvents()
check("B2 库页连续 refresh 选择保持", lt.appid_combo.currentIndex() == idx,
      f"{idx} -> {lt.appid_combo.currentIndex()}")

# ---- B3：失败任务可重试（核心层）
from swdm.core.downloader import DownloadManager, DownloadJob, JobStatus  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402

lib = ModLibrary(os.path.join(_TMP, "lib"))
engine = SteamCMDEngine(exe_path=os.path.join(_TMP, "steamcmd.exe"),
                        install_dir=os.path.join(_TMP, "install"))
mgr = DownloadManager(engine=engine, library=lib)
mgr.start()
it = WorkshopItem(publishedfileid="12345", title="T", appid="4000",
                  file_size=1024)
job = mgr.enqueue(it, "4000")
app.processEvents()
# 手动造一个失败记录进 _done
with mgr._lock:
    job.status = JobStatus.FAILED
    job.message = "测试失败"
    mgr._done.append(job)
ok = mgr.retry(job.id)
check("B3 retry 返回 True", ok is True, repr(ok))
# worker 线程可能已把任务取走执行（engine 不存在会立刻失败回 _done），
# 故此处验证"不在 _done 中或已重新入队/执行中"两种活跃状态之一
with mgr._lock:
    gone = job.id not in [j.id for j in mgr._done if j.status == JobStatus.FAILED]
    requeued = any(j.id == job.id for j in mgr._queue)
    active = job.id in mgr._active
check("B3 失败任务重新进入处理流程", gone or requeued or active)
# 成功任务不可 retry
job2 = mgr.enqueue(WorkshopItem(publishedfileid="999", title="T2",
                                appid="4000", file_size=1), "4000")
with mgr._lock:
    job2.status = JobStatus.SUCCESS
    mgr._done.append(job2)
ok2 = mgr.retry(job2.id)
check("B3 成功任务不可重试", ok2 is False, repr(ok2))

# ---- B4：取消全部弹出确认对话框
_q_calls.clear()
win.downloads_tab._cancel_all()
check("B4 取消全部弹出确认框", len(_q_calls) == 1,
      str(_q_calls))
check("B4 确认框标题正确",
      len(_q_calls) == 1 and _q_calls[0][0] == "取消全部下载", str(_q_calls))

mgr.stop()
fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
