"""下载页与下载管理器修复测试（bug2/3/4/5/7 + downloader 健壮性）。"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_dl_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.core.downloader import DownloadJob, DownloadManager, JobStatus  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

def _mk_item(pid: str) -> WorkshopItem:
    return WorkshopItem(publishedfileid=pid, title=f"mod {pid}", appid="4000")

def _mk_mgr() -> DownloadManager:
    engine = MagicMock()
    engine.download_item.return_value = MagicMock(
        status="success", message="ok", bytes_done=1024, path="/tmp"
    )
    engine.ensure_partial.return_value = 0
    lib = MagicMock()
    return DownloadManager(engine=engine, library=lib)

mgr = _mk_mgr()
job = mgr.enqueue(_mk_item("111"), "4000")
mgr.cancel("111")
snap = mgr.snapshot()
check("取消排队任务后进入 done", any(j.id == "111" for j in snap["done"]))
check("取消后状态为 CANCELLED",
      next(j for j in snap["done"] if j.id == "111").status == JobStatus.CANCELLED)
check("取消后队列已清空", len(snap["queued"]) == 0)

mgr2 = _mk_mgr()
mgr2.enqueue(_mk_item("a"), "4000")
mgr2.enqueue(_mk_item("b"), "4000")
mgr2.enqueue_high_priority(_mk_item("c"), "4000")
snap2 = mgr2.snapshot()
check("高优先级插入队首", snap2["queued"][0].id == "c",
      str([j.id for j in snap2["queued"]]))

before = len(mgr2.snapshot()["queued"])
mgr2.enqueue(_mk_item("a"), "4000")
after = len(mgr2.snapshot()["queued"])
check("重复入队被跳过", before == after, f"{before}->{after}")

mgr3 = _mk_mgr()
j3 = mgr3.enqueue(_mk_item("333"), "4000")
with mgr3._lock:
    mgr3._queue.popleft()
    mgr3._active["333"] = j3
fired = []
mgr3.on_finished.append(lambda j: fired.append(j.id))
mgr3.cancel("333")
snap3 = mgr3.snapshot()
check("取消活跃任务后移出 _active", "333" not in mgr3._active)
check("取消活跃任务后入 done 且 CANCELLED",
      any(j.id == "333" and j.status == JobStatus.CANCELLED for j in snap3["done"]))
check("取消活跃任务触发 finished 回调", "333" in fired)

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
