"""t6 探针：DownloadManager 层隔离验证两个可疑行为（无 GUI）。
1) 失败任务 retry_all_failed() 是否真的重新排队并成功（fake 引擎放行后）。
2) 暂停期间排队任务是否被派发（F2 疑点）。
"""
import os
import sys
import threading
import time

_TMP = os.environ.get("APPDATA") or ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.downloader import (DownloadManager, DownloadResult,  # noqa: E402
                                  DownloadStatus)
from swdm.core.steam_api import WorkshopItem  # noqa: E402


class _FakeEngine:
    fail_items = {"555003"}
    allow = False
    started = []

    def __init__(self):
        self.on_throttle_signal = []
        self._gates = {}
        self._cancel = threading.Event()

    def ensure_partial(self, *a, **k):
        return 0

    def cancel(self):
        self._cancel.set()

    def gate(self, iid):
        return self._gates.setdefault(str(iid), threading.Event())

    def download_item(self, appid, item_id, total_hint=0, install_dir="",
                      on_progress=None):
        iid = str(item_id)
        type(self).started.append(iid)
        if iid in self.fail_items and not self.allow:
            return DownloadResult(item_id=iid, appid=str(appid),
                                  status=DownloadStatus.FAILED,
                                  message="probe fake failure")
        ev = self._gates.get(iid)
        if ev is not None:
            while not ev.is_set():
                if ev.wait(0.2):
                    break
                if self._cancel.is_set():
                    break
        if self._cancel.is_set():
            self._cancel.clear()
            return DownloadResult(item_id=iid, appid=str(appid),
                                  status=DownloadStatus.FAILED,
                                  message="probe cancel")
        if on_progress:
            on_progress(100, 1024, "done")
        return DownloadResult(item_id=iid, appid=str(appid),
                              status=DownloadStatus.SUCCESS, bytes_done=1024)


class _FakeLib:
    def log_job(self, *a, **k):
        pass

    def get(self, jid):
        return None


def _mk(item_fail, item_ok):
    eng = _FakeEngine()
    mgr = DownloadManager(eng, _FakeLib(), max_concurrent=1, auto_retry=1,
                          jitter_base=0.0, jitter_spread=0.0,
                          backoff=_NoBackoff())
    mgr.start()
    return eng, mgr


class _NoBackoff:
    level = 0
    level_delay = 0.0

    def record_failure(self, reason=""):
        return 0.0

    def record_success(self):
        pass

    def nudge(self, max_level=3):
        pass

    def reset(self):
        pass


def _snap(mgr):
    return mgr.snapshot()


def _wait(pred, timeout=12.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


# ---- 场景 1：失败 → retry_all_failed → 成功 ----
eng, mgr = _mk("555003", None)
mgr.enqueue(WorkshopItem(publishedfileid="555003", title="C", appid="294100"),
            "294100")
ok = _wait(lambda: any(j.id == "555003" and j.status.value == "failed"
                       for j in _snap(mgr)["done"]))
print(f"[1] C 终态 FAILED: {ok}, started={eng.started}", flush=True)
_FakeEngine.allow = True
n = mgr.retry_all_failed()
print(f"[1] retry_all_failed 返回 n={n}", flush=True)
ok = _wait(lambda: any(j.id == "555003" and j.status.value == "success"
                       for j in _snap(mgr)["done"]))
print(f"[1] 重试后 C SUCCESS: {ok}, started={eng.started}", flush=True)

# ---- 场景 2：暂停期间排队任务是否被派发 ----
class _FakeEngine2(_FakeEngine):
    started = []
    fail_items = set()
    allow = True


eng2 = _FakeEngine2()
mgr2 = DownloadManager(eng2, _FakeLib(), max_concurrent=1, auto_retry=1,
                       jitter_base=0.0, jitter_spread=0.0, backoff=_NoBackoff())
mgr2.start()
eng2.gate("A")  # A 阻塞占住并发槽
mgr2.enqueue(WorkshopItem(publishedfileid="A", title="A", appid="294100"),
             "294100")
ok = _wait(lambda: eng2.started == ["A"])
print(f"[2] A 已开始（阻塞中）: {ok}, started={eng2.started}", flush=True)
mgr2.enqueue(WorkshopItem(publishedfileid="B", title="B", appid="294100"),
             "294100")
mgr2.pause_all()
print(f"[2] 已暂停 paused={mgr2.paused}", flush=True)
eng2.gate("A").set()  # A 完成
ok = _wait(lambda: "A" in {j.id for j in _snap(mgr2)["done"]}, timeout=8.0)
print(f"[2] A 完成: {ok}", flush=True)
time.sleep(1.5)  # 给调度器派发窗口
b_started = "B" in eng2.started
q = [j.id for j in _snap(mgr2)["queued"]]
print(f"[2] 暂停期间 B 是否被派发: {b_started}; 队列={q}", flush=True)
print(f"[2] 结论: {'B 被派发（暂停竞态成立）' if b_started else 'B 未派发（暂停生效）'}",
      flush=True)
mgr2.stop()
mgr.stop()

# ---- 场景 3：取消后立即行内重试 → 旧 worker 收尾块按 id 吞掉新任务成功结果 ----
class _FakeEngine3(_FakeEngine):
    """首次调用：阻塞在闸门上（可取消）；重试调用：慢速 0.4s 后成功。"""
    started = []
    fail_items = set()
    allow = True
    calls = {}

    def download_item(self, appid, item_id, total_hint=0, install_dir="",
                      on_progress=None):
        iid = str(item_id)
        n = _FakeEngine3.calls.get(iid, 0)
        _FakeEngine3.calls[iid] = n + 1
        type(self).started.append(iid)
        print(f"  [3] engine call #{n + 1} for {iid} t={time.time():.3f}",
              flush=True)
        if n == 0:
            ev = self._gates.get(iid)
            if ev is not None:
                while not ev.is_set():
                    if ev.wait(0.2):
                        break
                    if self._cancel.is_set():
                        break
            if self._cancel.is_set():
                self._cancel.clear()
                return DownloadResult(item_id=iid, appid=str(appid),
                                      status=DownloadStatus.FAILED,
                                      message="probe cancel")
        else:
            time.sleep(0.4)   # 重试任务慢速执行：制造新旧线程重叠窗口
        if on_progress:
            on_progress(100, 1024, "done")
        return DownloadResult(item_id=iid, appid=str(appid),
                              status=DownloadStatus.SUCCESS, bytes_done=1024)


eng3 = _FakeEngine3()
mgr3 = DownloadManager(eng3, _FakeLib(), max_concurrent=1, auto_retry=1,
                       jitter_base=0.0, jitter_spread=0.0, backoff=_NoBackoff())
mgr3.start()
eng3.gate("D")
mgr3.enqueue(WorkshopItem(publishedfileid="D", title="D", appid="294100"),
             "294100")
_wait(lambda: eng3.started == ["D"])
print("[3] D 首次执行已阻塞", flush=True)
mgr3.cancel("D")                     # 用户点「取消」
print(f"[3] cancel 后 done={[(j.id, j.status.value) for j in _snap(mgr3)['done']]}",
      flush=True)
r = mgr3.retry("D")                  # 用户立即点行内「重试」
print(f"[3] retry -> {r}", flush=True)
_wait(lambda: len(eng3.started) >= 2, timeout=6.0)
time.sleep(1.5)
fin = [(j.id, j.status.value) for j in _snap(mgr3)["done"]]
print(f"[3] 最终 done={fin}", flush=True)
ok3 = any(j.id == "D" and j.status.value == "success" for j in _snap(mgr3)["done"])
print(f"[3] 结论: {'重试成功正常登记' if ok3 else 'F4 成立：重试的 SUCCESS 被旧线程按 id 吞掉，终态停留在 CANCELLED'}",
      flush=True)
mgr3.stop()
print("DONE", flush=True)
