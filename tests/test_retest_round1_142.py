"""SWDM 1.4.2 复测第一轮（用户视角交互剧本）— 2026-10-02

复测人：qa-owner（t6 attempt 3，F1 修复后重开）。脚本式：check() + sys.exit。

剧本（全部走 QTest 真实按键/点击，不直调任何用户操作方法）：
  S1 换游戏：keyClicks "rimworld" → 联想 popup → Return 选中 → appid 294100
  S2 mod 搜索：keyClicks "wiremod" + Return → 即时反馈 + worker 以 search 词调用
  S3 翻页：mouseClick 下一页/上一页 → 页签与 worker.page 同步
  S4 勾选：mouseClick 卡片 check_box → 下载勾选按钮计数与使能
  S5 下载勾选：mouseClick → 自动切下载页 + 占位行 + 入队
  S6 暂停/继续：mouseClick 全部暂停 → 暂停期间排队任务不派发；继续后派发
  S7 重试失败：失败任务 → mouseClick「↻ 重试失败」→ 重新排队并成功
  S8 取消 + 行内重试：mouseClick 行内「取消」→ 已取消 → 变「重试」→ 点击后成功

桩原则（t6 F1 教训）：_FakeBrowseWorker 的信号契约与真实 BrowseWorker
逐项对齐——items_ready=Signal(list,int) 且 emit(items, generation)
（workers.py:33/74 已升级为同签名），progress/failed 同签名。
网络层全桩：GameSearchClient / SteamAPI.browse/enrich/resolve_dependency_tree；
下载引擎桩：swdm.gui.services.SteamCMDEngine（可阻塞闸门 + 可控失败）。
环境学知：QTest.qWait 的 C++ 事件循环不释放 GIL，纯 Python 线程会被
饿死——等待一律 time.sleep + app.processEvents。
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_r1_142_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_WINFONTS = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WINFONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _WINFONTS)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import QObject, Qt, Signal, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


class _Cap:
    """stderr 捕获：槽内未捕获异常 = bug。"""

    def __init__(self):
        self.real = sys.stderr
        self.err = io.StringIO()

    def write(self, s):
        self.err.write(s)
        self.real.write(s)

    def flush(self):
        self.err.flush()
        self.real.flush()


_cap = _Cap()
sys.stderr = _cap

app = QApplication.instance() or QApplication(sys.argv)
app.setFont(__import__("PySide6.QtGui", fromlist=["QFont"]).QFont("Microsoft YaHei", 9))
QMessageBox.question = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

# ---- 网络桩（在任何 MainWindow 构造前注入） ----
from swdm.core import game_search as gs_mod  # noqa: E402
import swdm.gui.services as svc_mod  # noqa: E402
import swdm.gui.workshop_tab as wt_mod  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.downloader import DownloadResult, DownloadStatus  # noqa: E402


class _FakeSearchClient:
    def is_in_cooldown(self):
        return False

    def cooldown_remaining(self):
        return 0.0

    def search(self, term):
        return []


gs_mod.GameSearchClient = _FakeSearchClient


# ---- 下载引擎桩（替代真实 steamcmd：可阻塞闸门 + 可控失败） ----
class _FakeEngine:
    """行为对齐 SteamCMDEngine 的被用面：
    ensure_partial / cancel / test_login / download_item(appid, item_id,
    total_hint, install_dir, on_progress) -> DownloadResult。"""

    fail_items = {"555003"}      # C：失败到 allow_success 放行
    allow_success = False
    started: list = []

    def __init__(self, exe_path="", install_dir="", anonymous=True, **kw):
        self.anonymous = anonymous
        self.username = self.password = self.guard_code = ""
        self.exe_path = exe_path
        self.install_dir = install_dir
        self.validate = False
        self._gates: dict = {}
        self._cancel = threading.Event()
        self.on_throttle_signal: list = []

    def ensure_partial(self, item_id, appid, install_dir=""):
        return 0

    def test_login(self):
        return True, "ok"

    def cancel(self):
        self._cancel.set()

    def gate(self, item_id):
        return self._gates.setdefault(str(item_id), threading.Event())

    def download_item(self, appid, item_id, total_hint=0, install_dir="",
                      on_progress=None):
        item_id = str(item_id)
        print(f"DIAG engine enter {item_id} t={time.time():.3f} "
              f"thr={threading.get_ident()}", flush=True)
        type(self).started.append(item_id)
        if item_id in self.fail_items and not self.allow_success:
            return DownloadResult(
                item_id=item_id, appid=str(appid),
                status=DownloadStatus.FAILED, message="模拟网络中断")
        ev = self._gates.get(item_id)
        if ev is not None:
            while not ev.is_set():
                if ev.wait(0.2):
                    break
                if self._cancel.is_set():
                    break
            if self._cancel.is_set():
                self._cancel.clear()
                return DownloadResult(
                    item_id=item_id, appid=str(appid),
                    status=DownloadStatus.FAILED, message="模拟用户取消")
        if on_progress:
            on_progress(100, total_hint or 4096, "完成")
        return DownloadResult(
            item_id=item_id, appid=str(appid),
            status=DownloadStatus.SUCCESS, bytes_done=total_hint or 4096)


svc_mod.SteamCMDEngine = _FakeEngine

# ---- SteamAPI 网络层桩 ----
import swdm.core.steam_api as sa_mod  # noqa: E402

_ITEMS = [
    WorkshopItem(publishedfileid="555001", title="wiremod 测试甲",
                 appid="294100", file_size=1048576, subscriptions=100,
                 creator_name="authorA", tags=["wiremod"]),
    WorkshopItem(publishedfileid="555002", title="wiremod 测试乙",
                 appid="294100", file_size=2097152, subscriptions=200,
                 creator_name="authorB", tags=["wiremod"]),
    WorkshopItem(publishedfileid="555003", title="wiremod 测试丙",
                 appid="294100", file_size=3145728, subscriptions=300,
                 creator_name="authorC", tags=["wiremod"]),
    WorkshopItem(publishedfileid="555004", title="wiremod 测试丁",
                 appid="294100", file_size=4194304, subscriptions=400,
                 creator_name="authorD", tags=["wiremod"]),
]


def _fake_browse(self, appid, page=1, search_text="", sort="", required_tags=None):
    return list(_ITEMS)


def _fake_enrich(self, items):
    return items


sa_mod.SteamAPI.browse = _fake_browse
sa_mod.SteamAPI.enrich = _fake_enrich

# ---- BrowseWorker 桩：契约与真实 workers.BrowseWorker 逐项对齐
# （t6 F1 教训：信号元数必须一致，否则桩掩盖生产路径 bug）
_FAKE_CALLS: list = []


class _FakeBrowseWorker(QObject):
    ready = Signal(list, int)
    progress = Signal(str)
    failed = Signal(str)
    items_ready = Signal(list, int)

    def __init__(self, api, appid, page=1, search="", sort="", tags=None,
                 generation=0):
        super().__init__()
        self._appid = appid
        self._page = page
        self._search = search
        _FAKE_CALLS.append((str(appid), page, search))

    def isRunning(self):
        return False

    def wait(self, *a, **k):
        return True

    def start(self):
        gen = wt_mod_singleton._worker_gen
        QTimer.singleShot(
            0, lambda: self.items_ready.emit(list(_ITEMS), gen))


wt_mod.BrowseWorker = _FakeBrowseWorker

from swdm.gui.main_window import MainWindow  # noqa: E402

# 并发 1：暂停测试需要队列任务不被并发派发
from swdm.core import get_config  # noqa: E402

_cfg = get_config()
_cfg.load()
_cfg.set("network", "max_concurrent_downloads", 1)

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab
wt._fetch_tags = lambda: None  # 标签拉取走网络，桩掉

wt_mod_singleton = wt  # 供 _FakeBrowseWorker 读当前代际（与 _do_refresh_list 实际用法一致）
wt.svc.api.resolve_dependency_tree = lambda *a, **k: ([], [])  # 依赖解析桩

# 测试提速：任务间抖动与失败退避归零（不改变暂停/重试语义）
wt.svc.downloader._jitter_base = 0.0
wt.svc.downloader._jitter_spread = 0.0


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


wt.svc.downloader._backoff = _NoBackoff()

dt = win.downloads_tab
engine_ctl = wt.svc.engine  # _FakeEngine 实例

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))
    print(("OK   " if cond else "FAIL ") + name + (f"  [{e}]" if e and not cond else ""),
          flush=True)


def _wait_for(pred, timeout=12.0, desc=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def _ed():
    ed = wt.game_combo.lineEdit()
    assert ed is not None
    return ed


def _type(text: str) -> None:
    """真实向输入框键入（与官方测试同路径：Latin-1 走 keyClicks，
    CJK 走携带 text 的 QKeyEvent——Qt 6.11.2 testlib 对非 Latin-1
    会 qFatal 硬中止，产品不可修）。"""
    ed = _ed()
    ed.setFocus()
    app.processEvents()
    if all(ord(ch) < 128 for ch in text):
        QTest.keyClicks(ed, text)
    else:
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_unknown,
                       Qt.KeyboardModifier.NoModifier, text)
        QApplication.sendEvent(ed, ev)
        app.sendEvent(ed, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_unknown,
                                    Qt.KeyboardModifier.NoModifier, text))
        app.processEvents()
    if ed.text() != text:
        ed.insert(text)


def _hit(key) -> None:
    ed = _ed()
    ed.setFocus()
    app.processEvents()
    QTest.keyClick(ed, key)
    QTest.qWait(30)


def _click(widget) -> None:
    """真实鼠标点击（QTest.mouseClick，左键）。"""
    widget.setFocus()
    app.processEvents()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    QTest.qWait(30)


def _snap():
    return wt.svc.downloader.snapshot()


def _done_ids():
    return {j.id for j in _snap()["done"]}


def _job(jid):
    for j in _snap()["done"] + list(_snap()["active"]) + list(_snap()["queued"]):
        if j.id == jid:
            return j
    return None


# =====================================================================
# S1 换游戏：联想 → 回车选中
# =====================================================================
_type("rimworld")
QTest.qWait(120)
check("S1a 打字即时出联想 popup",
      wt._game_completer.popup().isVisible(), repr(wt.game_combo.currentText()))
_hit(Qt.Key.Key_Return)
QTest.qWait(750)  # 真实去抖 350ms + 回包余量
check("S1b 回车选中联想项切到 RimWorld",
      "RimWorld" in wt.game_combo.currentText(), repr(wt.game_combo.currentText()))
check("S1c _current_appid 解析为 294100",
      wt._current_appid() == "294100", repr(wt._current_appid()))
check("S1d 状态栏未提示'请先选择'",
      "请先选择" not in wt.status_label.text(), repr(wt.status_label.text()))
check("S1e 切换游戏触发列表刷新请求",
      any(c[0] == "294100" for c in _FAKE_CALLS), repr(_FAKE_CALLS))

# =====================================================================
# S2 mod 搜索：即时反馈 + 搜索词透传
# =====================================================================
_FAKE_CALLS.clear()
wt.search_edit.setFocus()
app.processEvents()
QTest.keyClicks(wt.search_edit, "wiremod")
wt.search_edit.setFocus()
app.processEvents()
t0 = time.time()
QTest.keyClick(wt.search_edit, Qt.Key.Key_Return)
feedback_at = None
while time.time() - t0 < 0.5:
    app.processEvents()
    time.sleep(0.02)
    if wt.status_label.text().strip():
        feedback_at = time.time() - t0
        break
check("S2a 回车后 ≤150ms 出现可见反馈",
      feedback_at is not None and feedback_at < 0.15, f"at={feedback_at}")
_wait_for(lambda: any(c[2] == "wiremod" for c in _FAKE_CALLS), desc="search worker")
check("S2b 列表刷新以搜索词 wiremod 调用",
      any(c[2] == "wiremod" for c in _FAKE_CALLS), repr(_FAKE_CALLS))
_wait_for(lambda: len(wt._cards()) == 4, desc="cards after search")
check("S2c 搜索结果渲染 4 张卡片", len(wt._cards()) == 4,
      f"n={len(wt._cards())}")
check("S2d 状态栏显示物品数",
      "4" in wt.status_label.text(), repr(wt.status_label.text()))

# =====================================================================
# S3 翻页：下一页/上一页（真实鼠标点击）
# =====================================================================
_FAKE_CALLS.clear()
_click(wt.next_btn)
check("S3a 下一页后页签显示第 2 页",
      wt.page_label.text() == "第 2 页", repr(wt.page_label.text()))
check("S3b 上一页按钮由禁用变可用", wt.prev_btn.isEnabled())
_wait_for(lambda: any(c[1] == 2 for c in _FAKE_CALLS), desc="page2")
check("S3c 下一页触发 page=2 的刷新请求",
      any(c[1] == 2 for c in _FAKE_CALLS), repr(_FAKE_CALLS))
_wait_for(lambda: len(wt._cards()) == 4, desc="cards page2")
check("S3d 翻页后卡片重新渲染", len(wt._cards()) == 4, f"n={len(wt._cards())}")

_FAKE_CALLS.clear()
_click(wt.prev_btn)
check("S3e 上一页后页签回到第 1 页",
      wt.page_label.text() == "第 1 页", repr(wt.page_label.text()))
_wait_for(lambda: any(c[1] == 1 for c in _FAKE_CALLS), desc="page1")
check("S3f 上一页触发 page=1 的刷新请求",
      any(c[1] == 1 for c in _FAKE_CALLS), repr(_FAKE_CALLS))
_wait_for(lambda: len(wt._cards()) == 4)
check("S3g 回到第 1 页后卡片仍在", len(wt._cards()) == 4)

# =====================================================================
# S4 勾选（真实点击卡片复选框）
# =====================================================================
cards = wt._cards()
cards[0].check_box.setFocus()
app.processEvents()
_click(cards[0].check_box)
check("S4a 勾第 1 张卡 → 下载勾选按钮计数 (1)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (1)",
      repr(wt.dl_selected_btn.text()))
check("S4b 勾选后下载勾选按钮可用", wt.dl_selected_btn.isEnabled())

_click(cards[1].check_box)
check("S4c 再勾第 2 张卡 → 计数 (2)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (2)",
      repr(wt.dl_selected_btn.text()))

_click(cards[0].check_box)
check("S4d 取消勾选第 1 张卡 → 计数回落 (1)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (1)",
      repr(wt.dl_selected_btn.text()))
_click(cards[0].check_box)  # 重新勾上，为下载做准备
check("S4e 重新勾选第 1 张卡 → 计数恢复 (2)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (2)",
      repr(wt.dl_selected_btn.text()))

# =====================================================================
# S5 下载勾选 → 自动切到下载页 + 占位行
# =====================================================================
engine_ctl.gate("555001")  # A 阻塞：为 S6 暂停演示占住并发槽位
engine_ctl.gate("555002")  # B 阻塞：暂停期间应在队列里不被派发
_click(wt.dl_selected_btn)
QTest.qWait(200)
print("DIAG S5 row_map=", sorted(dt._row_map.keys()),
      "rowCount=", dt.table.rowCount(),
      "checked=", sorted(wt._checked_ids),
      "q=", [j.id for j in _snap()["queued"]],
      "a=", [j.id for j in _snap()["active"]], flush=True)
check("S5a 点击后自动切换到下载页",
      win._tabs.currentWidget() is dt, repr(win._tabs.currentWidget()))
check("S5b 下载页出现 2 行占位", dt.table.rowCount() == 2,
      f"rows={dt.table.rowCount()}")
check("S5c 工坊页状态提示已加入队列",
      "已加入下载队列" in wt.status_label.text(), repr(wt.status_label.text()))

# =====================================================================
# S6 暂停/继续（真实点击全部暂停按钮）
# =====================================================================
ok = _wait_for(lambda: engine_ctl.started == ["555001"], desc="A starts")
check("S6a 首个任务已开始下载（引擎占用）", ok, repr(engine_ctl.started))

_click(dt.pause_all_btn)
check("S6b 点击暂停后按钮变'▶ 全部继续'",
      dt.pause_all_btn.text() == "▶ 全部继续", repr(dt.pause_all_btn.text()))
check("S6c 管理器进入暂停态", wt.svc.downloader.paused)

engine_ctl.gate("555001").set()  # 放行 A
ok = _wait_for(lambda: "555001" in _done_ids(), desc="A done")
check("S6d 放行后第一个任务完成", ok, f"done={sorted(_done_ids())}")
_ok_paused = _wait_for(
    lambda: "555002" not in engine_ctl.started and not _snap()["active"]
    and any(j.id == "555002" for j in _snap()["queued"]), desc="B stays queued")
check("S6e 暂停期间排队任务不被派发（B 仍在队列）",
      _ok_paused and "555002" not in engine_ctl.started,
      f"started={engine_ctl.started} q={[j.id for j in _snap()['queued']]}")
ok = _wait_for(lambda: "555002" in engine_ctl.started, timeout=8.0,
               desc="B starts")

_click(dt.pause_all_btn)  # 继续
check("S6f 点击继续后按钮恢复'⏸ 全部暂停'",
      dt.pause_all_btn.text() == "⏸ 全部暂停", repr(dt.pause_all_btn.text()))
check("S6g 管理器恢复派发态", not wt.svc.downloader.paused)
engine_ctl.gate("555002").set()
ok = _wait_for(lambda: "555002" in _done_ids(), desc="B done")
check("S6h 继续后第二个任务完成", ok, f"done={sorted(_done_ids())}")

# =====================================================================
# S7 重试失败（真实点击「↻ 重试失败」）
# =====================================================================
cards = wt._cards()
for c in (cards[0], cards[1]):     # 先清掉 A/B 勾选
    if c.isChecked():
        _click(c.check_box)
_click(cards[2].check_box)          # 勾 C（失败项）
check("S7a 只勾 C → 计数 (1)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (1)",
      repr(wt.dl_selected_btn.text()))
_click(wt.dl_selected_btn)
ok = _wait_for(lambda: (_job("555003") is not None
                        and _job("555003").status.value in ("failed",)),
               timeout=15.0, desc="C fails")
job_c = _job("555003")
check("S7b C 两次执行后终态 FAILED（自动重试用尽）",
      ok and job_c is not None, f"job={job_c}")
row_c = dt._row_map.get("555003", -1)
check("S7c 失败行操作列按钮变'重试'",
      row_c >= 0 and dt.table.cellWidget(row_c, 6).text() == "重试",
      f"row={row_c}")

engine_ctl.allow_success = True     # 放行（模拟用户侧条件恢复）
print("DIAG pre-retry btn=", dt.retry_failed_btn.text(),
      "enabled=", dt.retry_failed_btn.isEnabled(), flush=True)
_orig_raf = wt.svc.downloader.retry_all_failed
_raf_log = {"n": None, "exc": None}


def _spy_raf():
    try:
        n = _orig_raf()
        _raf_log["n"] = n
        print("DIAG retry_all_failed ->", n, flush=True)
        return n
    except Exception as e:  # noqa: BLE001
        _raf_log["exc"] = repr(e)
        print("DIAG retry_all_failed EXC:", repr(e), flush=True)
        raise


wt.svc.downloader.retry_all_failed = _spy_raf
_click(dt.retry_failed_btn)
wt.svc.downloader.retry_all_failed = _orig_raf
print("DIAG post-click raf:", _raf_log, flush=True)
for _i in (1, 2, 4):
    time.sleep(float(_i))
    app.processEvents()
    print(f"DIAG +{_i}s snap=",
          {k: [(j.id, j.status.value, j.attempt) for j in v] for k, v in _snap().items()},
          "started=", engine_ctl.started, flush=True)
ok = _wait_for(lambda: "555003" in _done_ids()
               and _job("555003").status.value == "success", timeout=12.0,
               desc="C retry success")
check("S7d 点击'↻ 重试失败'后 C 重新排队并成功",
      ok, f"job={_job('555003')}")

# =====================================================================
# S8 取消 + 行内重试（真实点击行内按钮）
# =====================================================================
cards = wt._cards()
for c in (cards[2],):               # 清掉 C
    if c.isChecked():
        _click(c.check_box)
_click(cards[3].check_box)          # 勾 D（取消演示项）
check("S8a 只勾 D → 计数 (1)",
      wt.dl_selected_btn.text() == "⬇ 下载勾选 (1)",
      repr(wt.dl_selected_btn.text()))
engine_ctl.gate("555004")           # D 阻塞：取消演示需要任务挂起
_click(wt.dl_selected_btn)
ok = _wait_for(lambda: "555004" in engine_ctl.started, desc="D starts")
check("S8b D 已开始并被闸门挂起（用户可取消）", ok, repr(engine_ctl.started))
row_d = dt._row_map.get("555004", -1)
check("S8c D 行操作列按钮为'取消'",
      row_d >= 0 and dt.table.cellWidget(row_d, 6).text() == "取消",
      f"row={row_d}")

_click(dt.table.cellWidget(row_d, 6))   # 真实点击行内「取消」
ok = _wait_for(lambda: _job("555004") is not None
               and _job("555004").status.value == "cancelled",
               desc="D cancelled")
check("S8d 点击取消后 D 变已取消", ok, f"job={_job('555004')}")
print("DIAG S8e row_map=", sorted(dt._row_map.keys()),
      "rowCount=", dt.table.rowCount(),
      "started=", engine_ctl.started,
      "snap=", {k: [j.id for j in v] for k, v in _snap().items()}, flush=True)
row_d2 = dt._row_map.get("555004")
check("S8e-1 D 行仍存在于行映射", row_d2 is not None, f"row_map={sorted(dt._row_map.keys())}")
btn_d = dt.table.cellWidget(row_d2, 6) if row_d2 is not None else None
check("S8e 取消后行内按钮变'重试'",
      btn_d is not None and btn_d.text() == "重试",
      repr(btn_d.text() if btn_d is not None else None))

engine_ctl.gate("555004").set()         # 放行（重试将跑完）
_orig_retry = wt.svc.downloader.retry
_orig_cancel = wt.svc.downloader.cancel


def _spy_retry(jid):
    r = _orig_retry(jid)
    print(f"DIAG retry({jid}) -> {r}", flush=True)
    return r


def _spy_cancel(jid):
    import traceback as _tb
    print("DIAG cancel called for", jid, flush=True)
    _tb.print_stack()
    return _orig_cancel(jid)


wt.svc.downloader.retry = _spy_retry
wt.svc.downloader.cancel = _spy_cancel
_click(btn_d)                           # 真实点击行内「重试」
time.sleep(1.0)
app.processEvents()
print("DIAG post-row-retry started=", engine_ctl.started,
      "snap=", {k: [(j.id, j.status.value) for j in v] for k, v in _snap().items()},
      flush=True)
wt.svc.downloader.retry = _orig_retry
wt.svc.downloader.cancel = _orig_cancel
ok = _wait_for(lambda: "555004" in _done_ids()
               and _job("555004").status.value == "success", timeout=12.0,
               desc="D retry success")
check("S8f 点击行内'重试'后 D 重新排队并成功",
      ok, f"job={_job('555004')}")# =====================================================================
# S9 全局收尾
# =====================================================================
done = _snap()["done"]
check("S9a 四个任务全部成功入库（A/B/C/D）",
      {j.id for j in done} == {"555001", "555002", "555003", "555004"}
      and all(j.status.value == "success" for j in done),
      f"{[(j.id, j.status.value) for j in done]}")
check("S9b 下载页统计无失败计数",
      "✗失败：0" in dt.stat_label.text(), repr(dt.stat_label.text()))

err_out = _cap.err.getvalue()
bad = [s for s in ("Traceback", "RuntimeError", "shiboken",
                   "already deleted", "Signal source has been deleted")
       if s in err_out]
check("S9c 全程无未捕获异常/已删除 C++ 对象类错误", not bad, f"命中={bad}")

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.stdout.flush()
sys.exit(0 if not fails else 1)
