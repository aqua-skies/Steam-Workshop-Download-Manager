"""A-P1：cancel 与完成登记微秒竞态窗口的确定性回归测试。

场景：
1. cancel 在链路返回 SUCCESS 与 worker 终态判定之间抢注（取消胜出）：
   终态 CANCELLED、不导入库、_done 只登记一次、finished 只发一次。
2. cancel 在任务间等待（_throttle_wait）期间发生：worker 入链前即收尾，
   不调用任何通道。
3. pending-cancel 标记收尾后清理：同 id 重新入队跑成功，不被残留标记
   误判为取消（修复前若标记残留，重试的成功结果会被错杀成 CANCELLED）。
（cancel 不覆盖已置 SUCCESS/FAILED 终态的 7g/7h 语义由 test_throttle 覆盖）
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_ap1_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.core.downloader import (  # noqa: E402
    DownloadManager, DownloadResult, DownloadStatus, JobStatus,
)
from swdm.core.steam_api import WorkshopItem  # noqa: E402

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


def _wait_terminal(job, timeout=15.0):
    t0 = time.time()
    while job.status not in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED):
        if time.time() - t0 > timeout:
            return False
        time.sleep(0.01)
    return True


def _mk_mgr():
    engine = MagicMock()
    engine.ensure_partial.return_value = 0
    lib = MagicMock()
    return DownloadManager(engine=engine, library=lib, auto_retry=0)


def _mk_item(pid: str) -> WorkshopItem:
    return WorkshopItem(publishedfileid=pid, title=f"mod {pid}", appid="4000")


# ================================================= 场景 1：cancel 抢在终态判定前
mgr = _mk_mgr()
mgr._throttle_wait = lambda job: None  # 跳过任务间等待，保持确定性
state = {"cancel_next": True}


def chain_hooked(job, install_dir, smoother):
    """模拟「链路刚跑完、worker 尚未判定终态」的瞬间 cancel() 抢注。"""
    res = DownloadResult(
        item_id=job.id, appid=job.appid, status=DownloadStatus.SUCCESS,
        bytes_done=1024, message="ok",
    )
    if state["cancel_next"]:
        mgr.cancel(job.id)  # worker 线程内、_exec_job 收尾前
    return res


mgr._run_channel_chain = chain_hooked
fired = []
mgr.on_finished.append(lambda j: fired.append(j.id))

job1 = mgr.enqueue(_mk_item("p1"), "4000")
mgr.start()
check("S1: 等待终态未超时", _wait_terminal(job1))

upsert_calls = mgr.library.upsert.call_count
done_ids = [j.id for j in mgr.snapshot()["done"]]
check("S1: 终态为 CANCELLED（取消胜出，非 SUCCESS）",
      job1.status == JobStatus.CANCELLED, str(job1.status))
check("S1: _done 恰好登记一次", done_ids.count("p1") == 1, str(done_ids))
check("S1: 未导入库（取消的任务不入库）", upsert_calls == 0,
      f"upsert 调用 {upsert_calls} 次")
check("S1: finished 只触发一次", fired.count("p1") == 1, str(fired))
check("S1: _active 已清空", "p1" not in mgr._active)
check("S1: pending-cancel 标记已清理", "p1" not in mgr._cancelling,
      str(sorted(mgr._cancelling)))

# ================================================= 场景 2：等待期间取消，入链前收尾
mgr2 = _mk_mgr()
mgr2._throttle_wait = lambda job: None
chain_calls = []


def chain_record(job, install_dir, smoother):
    chain_calls.append(job.id)
    return DownloadResult(item_id=job.id, appid=job.appid, status=DownloadStatus.FAILED)


mgr2._run_channel_chain = chain_record
fired2 = []
mgr2.on_finished.append(lambda j: fired2.append(j.id))

j2 = mgr2.enqueue(_mk_item("p2"), "4000")
with mgr2._lock:
    mgr2._queue.popleft()
    mgr2._active["p2"] = j2
j2._stop.set()  # 模拟 cancel() 已在等待期间置位（cancel 逻辑由场景 1/既有用例覆盖）
mgr2._exec_job(j2)  # 直接在当前线程驱动（确定性）

check("S2: 入链前收尾，通道链未被调用", chain_calls == [], str(chain_calls))
check("S2: 终态为 CANCELLED", j2.status == JobStatus.CANCELLED, str(j2.status))
check("S2: 已登记进 _done", any(x.id == "p2" for x in mgr2.snapshot()["done"]))
check("S2: finished 触发一次", fired2.count("p2") == 1, str(fired2))
check("S2: _active 已清空", "p2" not in mgr2._active)

# ================================================= 场景 3：标记清理后同 id 重跑成功
state["cancel_next"] = False
job3 = mgr.enqueue(_mk_item("p1"), "4000")  # 与场景 1 同 id（retry 语义）
check("S3: 同 id 重新入队成功（未被去重）", job3.id == "p1")
check("S3: 重试跑完为终态", _wait_terminal(job3))
check("S3: 重试结果为 SUCCESS（无残留 pending-cancel 误判）",
      job3.status == JobStatus.SUCCESS, str(job3.status))
check("S3: 重试后 pending 标记已清理", "p1" not in mgr._cancelling)

mgr.stop()
mgr2.stop()

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print(f"\n共 {len(RESULTS)} 项，{len(RESULTS) - len(fails)} 通过")
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
