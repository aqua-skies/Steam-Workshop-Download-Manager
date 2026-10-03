"""t19 · 复测第二轮 Part 2：E③ bytes=0 校验、缓存深拷贝、端点节流礼让。

与 Part 1 独立，聚焦 captain 补充的三个检查点：
- E③：steamcmd 报 SUCCESS 但 0 字节 → 改判 FAILED（不假成功）
- api_cache 命中必须深拷贝（用户级硬规则）
- _endpoint_throttle priority 礼让语义（t15）
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_t19b_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

out = []
ok = True


def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    out.append(f"[{'PASS' if cond else 'FAIL'}] {name}{' ' + str(e) if e else ''}")


# =====================================================================
# E③：steamcmd 报 SUCCESS 但 0 字节 → 改判 FAILED
# =====================================================================
from swdm.core.steamcmd_engine import (  # noqa: E402
    DownloadResult,
    DownloadStatus,
    SteamCMDEngine,
)
from swdm.core.downloader import DownloadJob, DownloadManager, JobStatus  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402


class _FakeSuccessEngine(SteamCMDEngine):
    """返回 SUCCESS，字节数由参数控制（模拟 steamcmd 假成功）。"""

    def __init__(self, bytes_done, install_dir):
        super().__init__(install_dir=install_dir)
        self._bytes = bytes_done
        self.on_throttle_signal = []  # 隔离信号订阅

    def download_item(self, appid, item_id, total_hint=0, install_dir="",
                      on_progress=None):
        return DownloadResult(
            item_id=str(item_id), appid=str(appid),
            status=DownloadStatus.SUCCESS,
            bytes_done=self._bytes,
            message="Success" if self._bytes else "Success",
        )


def _run_fake(bytes_done, auto_retry=0):
    d = tempfile.mkdtemp(prefix="t19b_e3_")
    eng = _FakeSuccessEngine(bytes_done, d)
    lib = ModLibrary()
    mgr = DownloadManager(eng, lib, max_concurrent=1, auto_retry=auto_retry,
                          jitter_base=0.0)
    it = WorkshopItem(publishedfileid="500000001", title="fake", appid="4000")
    job = DownloadJob(it, "4000")
    mgr.start()
    with mgr._lock:
        mgr._queue.append(job)
        mgr._cond.notify_all()
    t_end = time.time() + 30
    while job.status.value not in ("success", "failed", "cancelled") and time.time() < t_end:
        time.sleep(0.05)
    mgr.stop()
    return job


j0 = _run_fake(0)
check("E③: SUCCESS+0字节 → 改判 FAILED",
      j0.status == JobStatus.FAILED, j0.status.value)
check("E③: 0字节失败消息提示限流可能",
      "空" in (j0.message or "") or "限流" in (j0.message or ""), j0.message)
j1 = _run_fake(1024 * 1024)
check("E③ 对照: SUCCESS+真实字节 → 仍 SUCCESS",
      j1.status == JobStatus.SUCCESS, j1.status.value)

# =====================================================================
# 缓存深拷贝（用户级硬规则）：在 browse() 层验证——命中缓存返回前
# 必须深拷贝，enrich() 就地修改返回值不得污染缓存
# =====================================================================
from swdm.core.api_cache import get_api_cache  # noqa: E402
from swdm.core.steam_api import SteamAPI  # noqa: E402

_CARD_HTML = (
    '<div class="workshopItem">'
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=600000001">'
    '<img src="https://steamusercontent.com/1.jpg" alt="缓存项"></a></div>'
)

# __new__ 绕过 __init__（不联网）；_session=None 使任何意外网络调用即报错
api_dc = SteamAPI.__new__(SteamAPI)
api_dc.timeout = 30
api_dc._session = None
api_dc._community_get = lambda path, params, max_retries=4, priority=False: _CARD_HTML
get_api_cache().invalidate()

first = api_dc.browse("4000", page=1)
check("browse mock 返回 1 项", len(first) == 1, str(len(first)))
# 第二次走缓存命中
second = api_dc.browse("4000", page=1)
check("browse 第二次命中缓存", len(second) == 1, str(len(second)))
# 模拟 enrich() 就地修改返回值
if second:
    second[0].title = "MUTATED"
    if hasattr(second[0], "tags"):
        second[0].tags.append("污染标签")
third = api_dc.browse("4000", page=1)
check("深拷贝保护：外部修改不污染缓存",
      len(third) == 1 and third[0].title != "MUTATED",
      str(third[0].title if third else None))
get_api_cache().invalidate()

# TTL 行为：cache 原语层
cache = get_api_cache()
cache.set("t19_ttl_key", ["v"], ttl=1.0)
time.sleep(1.2)
hit3, _ = cache.get("t19_ttl_key")
check("TTL 过期自动失效", not hit3)

# =====================================================================
# 端点节流 priority 礼让（t15）
# =====================================================================
from swdm.core.steam_api import SteamAPI  # noqa: E402

api = SteamAPI()
# priority=True 绕过端点等待：先设一个近期的 last 时间，再 priority 请求
api._endpoint_last["/sharedfiles/"] = time.time()
t0 = time.time()
got = api._endpoint_throttle("/sharedfiles/filedetails/123", priority=True)
dt = time.time() - t0
check("priority=True 绕过端点等待", got is True and dt < 0.5, f"dt={dt:.2f}s")

# 低优先级请求在 _priority_pending>0 时立即礼让（返回 False）
api._endpoint_last["/sharedfiles/"] = time.time()  # 制造需要等待的状态
api._priority_pending = 1
t0 = time.time()
got2 = api._endpoint_throttle("/sharedfiles/filedetails/456", priority=False)
dt2 = time.time() - t0
check("低优先级请求被高优先级打断立即礼让", got2 is False and dt2 < 0.5, f"dt={dt2:.2f}s")
api._priority_pending = 0

# 无等待需要时低优先级正常放行
api._endpoint_last["/sharedfiles/"] = time.time() - 100  # 上次在 100s 前
got3 = api._endpoint_throttle("/sharedfiles/filedetails/789", priority=False)
check("无积压时低优先级正常放行", got3 is True)
check("_priority_pending 计数器归零（无泄漏）", api._priority_pending == 0,
      str(api._priority_pending))

# 非端点路径不受端点节流影响
got4 = api._endpoint_throttle("/some/other/path", priority=False)
check("非端点路径不被端点节流拦截", got4 is True)

# =====================================================================
# 结果输出
# =====================================================================
result = "\n".join(out)
print(result)
report = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t19b_retest_out.txt")
with open(report, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
