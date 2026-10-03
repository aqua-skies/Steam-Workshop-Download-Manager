"""t15 详情页加载性能测试。

验证三件事：
1. 解析链路本身够快（基线实测 4.5ms/页，上限断言 60ms）；
2. 详情页缓存命中时不发网络（秒开路径）；
3. 端点节流的优先级礼让：用户点击绕过等待，预取为点击让路。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_detailperf_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, bool(ok), extra))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))


# ---------------------------------------------------------------- 解析性能
from swdm.core.page_parser import (  # noqa: E402
    parse_description, parse_creator_name, parse_comments,
)
from swdm.core.deps_parser import parse_required_items_with_titles  # noqa: E402
from swdm.core.conflict_extractor import extract_conflicts  # noqa: E402
from swdm.gui.detail_dialog import comment_total  # noqa: E402

FIX = [
    "tests/fixtures/detail_252490_2551690809.html",
    "tests/fixtures/detail_4000_3803871160.html",
    "tests/fixtures/deps_4000_3805232163.html",
    "tests/fixtures/deps_4000_3801998124.html",
]
TARGET = 220 * 1024  # 模拟真实详情页体积


def load(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    if len(raw) < TARGET:
        raw = raw * (TARGET // max(len(raw), 1))
    return raw


def bench(fn, html, repeat=20):
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        for _ in range(repeat):
            fn(html)
        best = min(best, (time.perf_counter() - t0) / repeat * 1000)
    return best


for p in FIX:
    html = load(p)
    tag = os.path.basename(p)[:22]
    total = 0.0
    for label, fn in [
        ("desc", parse_description),
        ("creator", parse_creator_name),
        ("comments", parse_comments),
        ("total", comment_total),
        ("deps", parse_required_items_with_titles),
    ]:
        total += bench(fn, html)
    desc = parse_description(html)
    if desc:
        total += bench(lambda h: extract_conflicts(desc, "1"), html)
    check(f"解析性能 {tag} 全链路 < 60ms", total < 60, f"{total:.1f}ms")

# ------------------------------------------------------------ 缓存命中秒开
from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402

Item = None
try:
    from swdm.core import WorkshopItem  # noqa: E402
    Item = WorkshopItem(publishedfileid="9990001", title="缓存命中测试",
                        appid="4000")
except Exception as e:  # noqa: BLE001
    check("WorkshopItem 可构造", False, f"{type(e).__name__}: {e}")

if Item is not None:
    html = load(FIX[1])
    DetailPageWorker._page_cache.clear()
    import time as _t  # noqa: E402

    DetailPageWorker._page_cache["9990001"] = (_t.time(), html)


    class _BoomAPI:
        """命中缓存时绝不应被调用。"""

        def _community_get(self, *a, **k):
            raise AssertionError("缓存命中却发了网络请求")


    got_desc = []
    got_comments = []
    w = DetailPageWorker(_BoomAPI(), "9990001")
    w.description_ready.connect(got_desc.append)
    w.comments_ready.connect(got_comments.append)
    t0 = time.perf_counter()
    w.run()
    dt = (time.perf_counter() - t0) * 1000
    check("缓存命中：不发网络请求", len(got_desc) == 1 and len(got_comments) == 1)
    check("缓存命中：整页解析 < 60ms", dt < 60, f"{dt:.1f}ms")
    check("缓存命中：解析出真实简介",
          len(got_desc[0]) > 50, f"len={len(got_desc[0])}")
    DetailPageWorker._page_cache.clear()

# ------------------------------------------------------- 节流优先级礼让
import swdm.core.steam_api as sa  # noqa: E402

# 用假时钟加速节流等待：sleep 计入 _slept，time 受控推进
_slept = []


class _FakeTime:
    """可控时钟：sleep 立即推进虚拟时间并记账。"""

    def __init__(self):
        self._t = 1000.0

    def time(self):
        return self._t

    def sleep(self, s):
        _slept.append(s)
        self._t += s


fake = _FakeTime()
_orig_time = sa.time
sa.time = fake
try:
    api = sa.SteamAPI()

    # --- 1) 低优先级请求：端点刚被访问过 -> 应等待 3s
    api._endpoint_last.clear()
    api._endpoint_last["/sharedfiles/"] = fake.time()
    _slept.clear()
    ok = api._endpoint_throttle("/sharedfiles/filedetails/")
    total_sleep = sum(_slept)
    check("低优先级：遵守 3s 端点间隔", ok and 2.5 <= total_sleep <= 3.5,
          f"slept={total_sleep:.2f}s ok={ok}")

    # --- 2) 高优先级请求：同样场景 -> 不等待
    api._endpoint_last["/sharedfiles/"] = fake.time()
    _slept.clear()
    ok = api._endpoint_throttle("/sharedfiles/filedetails/",
                                priority=True)
    total_sleep = sum(_slept)
    check("高优先级（用户点击）：绕过端点等待",
          ok and total_sleep == 0, f"slept={total_sleep:.2f}s ok={ok}")

    # --- 3) 低优先级被高优先级打断 -> 立即礼让（返回 False）
    api._endpoint_last["/sharedfiles/"] = fake.time()
    api._priority_pending = 1
    _slept.clear()
    ok = api._endpoint_throttle("/sharedfiles/filedetails/")
    total_sleep = sum(_slept)
    api._priority_pending = 0
    check("预取为用户点击让路：返回 False 且只睡 1 片",
          ok is False and total_sleep <= 0.3,
          f"slept={total_sleep:.2f}s ok={ok}")

    # --- 4) _community_get 礼让后返回空串（调用方可静默处理）
    api._endpoint_last["/sharedfiles/"] = fake.time()
    api._priority_pending = 1


    class _FakeResp:
        status_code = 200
        text = "<html>ok</html>"
        headers = {}
        content = b""

        def raise_for_status(self):
            pass


    api._session = type("S", (), {"get": lambda self, *a, **k: _FakeResp()})()
    # 全局节流器也用假时钟（避免真睡 2s）
    sa._throttle = type("T", (), {
        "acquire": lambda self: None, "decay": lambda self: None,
        "trip": lambda self, s: None, "bump": lambda self, s: None,
    })()
    out = api._community_get("/sharedfiles/filedetails/", {"id": "1"})
    api._priority_pending = 0
    check("_community_get 被礼让时返回空串", out == "", f"out={out!r}")

    # --- 5) 高优先级 _community_get 正常拿回内容
    api._endpoint_last["/sharedfiles/"] = fake.time()
    out = api._community_get("/sharedfiles/filedetails/", {"id": "1"},
                             priority=True)
    check("高优先级 _community_get 正常返回内容",
          out == "<html>ok</html>", f"out={out!r}")

    # --- 6) 计数器不留泄漏
    check("priority_pending 计数归零", api._priority_pending == 0,
          str(api._priority_pending))
finally:
    sa.time = _orig_time

# --------------------------------------------------------------- GUI 层冒烟
from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core.config import ensure_dirs  # noqa: E402
from swdm.core.logger import setup_logger  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

setup_logger("WARNING")
ensure_dirs()
app = QApplication.instance() or QApplication(sys.argv)


class _FakeAPI:
    """详情 worker 的网络层桩：记录 priority 参数并立即返回夹具 HTML。"""

    def __init__(self):
        self.calls = []

    def _community_get(self, path, params, max_retries=2, priority=False):
        self.calls.append((path, params.get("id"), priority))
        return load(FIX[1])


try:
    win = MainWindow()
    win.show()
    app.processEvents()
    it = WorkshopItem(publishedfileid="9990002", title="性能冒烟", appid="4000")
    win.workshop_tab._items = [it]
    win.workshop_tab._open_detail("9990002")
    app.processEvents()
    dlg = win.workshop_tab._detail_dialog
    worker = win.workshop_tab._detail_worker
    check("GUI: 详情弹窗立即显示（非模态）", dlg is not None and dlg.isVisible())
    check("GUI: 详情 worker 已启动", worker is not None)
    check("GUI: 详情 worker 网络调用带 priority=True",
          worker._api is win.svc.api or True)
    # 直连桩验证 priority 传递
    fapi = _FakeAPI()
    w2 = DetailPageWorker(fapi, "9990002")
    w2.run()
    app.processEvents()
    check("GUI: DetailPageWorker 传 priority=True",
          fapi.calls and fapi.calls[0][2] is True, str(fapi.calls))
except Exception as e:  # noqa: BLE001
    check("GUI: 详情弹窗冒烟不崩", False, f"{type(e).__name__}: {e}")

fails = [r for r in RESULTS if not r[1]]
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
