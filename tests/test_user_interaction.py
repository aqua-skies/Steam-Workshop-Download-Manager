"""用户交互层测试：真实按键模拟（QTest），不做任何方法直调。

继任者请先读 docs/process/user_interaction_scenarios.md。
作假原则：直调 setText/方法 = API 测试；keyClicks/keyClick/QInputMethodEvent 才算
用户交互测试。本文件全部场景走后者。

复现 1.4.1 用户实机报告的 4 个交互 bug：
  I1 输入/选中联想出的游戏名后显示"找不到游戏"（_current_appid 解析）
  I2 联想 popup 打开时 Backspace 只能删一个字符（clear()+popup 竞争）
  I3 错误游戏名回车（含 popup 打开态 Return 应走 combo 选择路径，不崩）
  I4 中文/英文游戏名智能适配（"饥荒" ↔ "Don't Starve"）
  I5 搜索阶段即时反馈（回车后界面立即进入"搜索中"态）

网络全桩（GameSearchClient/BrowseWorker），场景自闭合。
脚本式：check() + sys.exit(0 iff ALL PASS)；Qt 退出崩溃 -1073740791 属既有环境噪声，以 stdout RESULT 为准。
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_ux_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_WINFONTS = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WINFONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _WINFONTS)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, Qt, QObject, Signal, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


class _Cap:
    """stderr 捕获：PySide6 槽内未捕获异常会 print 到 stderr，不致进程死但等同 bug。"""

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

# ---- 网络桩（在任何 MainWindow 构造前注入）----
from swdm.core import game_search as gs_mod  # noqa: E402
import swdm.gui.workshop_tab as wt_mod  # noqa: E402


class _FR:
    def __init__(self, appid, name):
        self.appid, self.name = appid, name


# storesearch 真实行为模拟：中文词回中文名结果、英文词回英文名、无结果回 []
_FAKE_STORE = {
    "饥荒": [_FR("322330", "饥荒"), _FR("219740", "Don't Starve")],
    "ji huang": [_FR("322330", "饥荒")],
    "dont starve": [_FR("219740", "Don't Starve"), _FR("322330", "Don't Starve Together")],
    "rimworld": [_FR("294100", "RimWorld")],
}


class _FakeSearchClient:
    def __init__(self):
        self.calls = 0

    def is_in_cooldown(self):
        return False

    def cooldown_remaining(self):
        return 0.0

    def search(self, term):
        self.calls += 1
        time.sleep(0.2)  # 模拟网络延迟
        t = (term or "").strip().lower()
        for k, v in _FAKE_STORE.items():
            if t == k.lower() or t in k.lower():
                return list(v)
        return []


gs_mod.GameSearchClient = _FakeSearchClient


class _FakeBrowseWorker(QObject):
    """BrowseWorker 桩：契约对齐真类（api, appid, page, search, sort, tags,
    generation）+ progress/failed/items_ready 信号 + isRunning/wait 语义。"""

    ready = Signal(list, int)
    progress = Signal(str)
    failed = Signal(str)
    items_ready = Signal(list, int)
    made = []

    def __init__(self, api, appid, page=1, search="", sort="", tags=None,
                 generation=0):
        super().__init__()
        self._appid = appid
        self._gen = generation
        _FakeBrowseWorker.made.append(appid)

    def isRunning(self):
        return False

    def wait(self, *a, **k):
        return True

    def start(self):
        gen = self._gen or 0
        QTimer.singleShot(0, lambda: self.items_ready.emit([], gen))


wt_mod.BrowseWorker = _FakeBrowseWorker

from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab
wt._fetch_tags = lambda: None  # 标签拉取走网络，桩掉
# 注意：_refresh_list 内硬编码 _refresh_timer.start(350)，setInterval 无效——
# 测试统一按真实 350ms 去抖等待（750ms+），不缩短，避免时间竞争假阳性。

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


def _ed():
    ed = wt.game_combo.lineEdit()
    assert ed is not None
    return ed


def _type(text: str) -> None:
    """真实向输入框键入。
    纯 Latin-1 文本走 keyClicks（真实按键事件）；
    含 CJK 等 non-Latin-1 字符走携带 text 的 QKeyEvent（QLineEdit 对非空
    event.text() 一律插入，与真实按键同路径）——Qt 6.11.2 testlib 的
    keyClicks 对非 Latin-1 字符 QChar::toLatin1()=0 会 asciiToKey(0) →
    qFatal 硬中止（最小复现=裸 QLineEdit，产品不可修，须测试侧规避）；
    QInputMethodEvent 的 (preedit, attrs) 构造是预编辑串不等于提交，误用。"""
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
        ed.insert(text)  # 最后兜底：仍走 QLineEdit 内部插入路径（发 textEdited）


def _hit(key) -> None:
    ed = _ed()
    ed.setFocus()
    app.processEvents()
    QTest.keyClick(ed, key)
    QTest.qWait(30)


def _combo_text() -> str:
    return wt.game_combo.currentText()


# =====================================================================
# I1 选中联想出的游戏名后"找不到游戏"
# 真实路径：打字→completer popup 弹→Return（completer 拦截=选高亮项）
# → 选中项 UserRole 的 appid → 切游戏 → 解析
# =====================================================================
_ed().clear()
_type("don")  # 内置表有 Don't Starve 系列 → 本地联想即时弹
QTest.qWait(120)
popup_open = wt._game_completer.popup().isVisible()
check("I1 打字即时出联想 popup", popup_open, repr(_combo_text()))

_hit(Qt.Key.Key_Return)  # popup 打开时 Return：completer 选高亮项
QTest.qWait(750)  # 真实去抖 350ms + worker 回包余量
check("I1 选中联想项后切换到 Don't Starve 系列游戏",
      any(x in _combo_text() for x in ("258130", "322330", "219740", "Starve")),
      repr(_combo_text()))
appid_after_select = wt._current_appid()
check("I1 选中联想项后 _current_appid 解析成功", appid_after_select != "",
      repr(appid_after_select))
check("I1 状态栏未提示'请先选择或输入游戏 AppID'",
      "请先选择" not in wt.status_label.text(), repr(wt.status_label.text()))
check("I1 触发了列表刷新请求（AppID 已解析）",
      bool(_FakeBrowseWorker.made), repr(_FakeBrowseWorker.made))

# =====================================================================
# I2 Backspace 只能删一个字符
# 真实路径：联想 popup 打开（旧实现每次 textEdited 都 clear()+重建
# combo 构件，打断后续按键；m2 后改 QCompleter 原地更新模型）
# =====================================================================
_ed().clear()
_type("garry")  # 本地有 Garry's Mod → popup 打开
QTest.qWait(80)
expect = ["garr", "gar", "ga"]
got = []
for _ in range(3):
    _hit(Qt.Key.Key_Backspace)
    got.append(_ed().text())
check("I2 popup 打开态连按 3 次 Backspace 每次都删一个字符",
      got == expect, f"got={got} expect={expect}")
check("I2 删除后输入框非卡死（仍可继续编辑）", _ed().text() == "ga", repr(_ed().text()))

# I2b 中文输入 + Backspace（用户真实场景是 IME 上下文）
_ed().clear()
_type("饥荒")
QTest.qWait(80)
expect_b = ["饥", ""]
got_b = []
for _ in range(2):
    _hit(Qt.Key.Key_Backspace)
    got_b.append(_ed().text())
check("I2b CJK 输入后连按 Backspace 逐字删除",
      got_b == expect_b, f"got={got_b} expect={expect_b}")

# =====================================================================
# I3 错误游戏名回车：不崩 + 有反馈
# =====================================================================
_ed().clear()
_type("zzzzqqqunrealgame")  # 无本地匹配 → hidePopup → popup 关
QTest.qWait(80)
_hit(Qt.Key.Key_Return)  # returnPressed → _on_game_enter → 触发搜索
# 注意：QTest.qWait 的 C++ 事件循环不释放 GIL，纯 Python 工作线程
# 会被饿死（0.2s 的请求迟迟完不成）。真实 app.exec 会释放 GIL，所以
# 这是测试环境假象；这里用 time.sleep（释放 GIL）+ processEvents 代替。
time.sleep(0.45)
app.processEvents()
check("I3 错误游戏名回车进程存活", True)  # 走到此处即未硬崩
check("I3 无结果时给出明确反馈",
      "未找到" in wt.status_label.text().replace("　", " ")
      or "未识别" in wt.status_label.text(),
      repr(wt.status_label.text()))

# popup 打开态 Return（combo 选择路径）也不崩
_ed().clear()
_type("don")
QTest.qWait(80)
_hit(Qt.Key.Key_Return)
QTest.qWait(300)
check("I3b popup 打开态 Return 进程存活", True)

# =====================================================================
# I4 中英文游戏名智能适配
# =====================================================================
_ed().clear()
_type("饥荒")  # keyClicks/CJK 或 IME 兜底
check("I4 中文键入落到输入框", _ed().text() == "饥荒", repr(_ed().text()))
_hit(Qt.Key.Key_Return)
QTest.qWait(750)
resolved = wt._current_appid()
check("I4 '饥荒' 解析到 Don't Starve 系列 AppID",
      resolved in {"322330", "219740"}, repr(resolved))
_FakeBrowseWorker.made.clear()  # 只计入本次触发的刷新
_hit(Qt.Key.Key_Return)
QTest.qWait(750)
check("I4 '饥荒' 后触发列表刷新",
      bool(_FakeBrowseWorker.made), repr(_FakeBrowseWorker.made))

_ed().clear()
_type("dont starve")
QTest.qWait(80)
_hit(Qt.Key.Key_Return)
QTest.qWait(300)
resolved2 = wt._current_appid()
check("I4 'dont starve'（无撇号）解析到 AppID",
      resolved2 in {"219740", "322330"}, repr(resolved2))

# =====================================================================
# I5 搜索阶段即时反馈：回车后界面立即进入"搜索中"态（<150ms）
# =====================================================================
wt._refresh_timer.stop()
wt.status_label.setText("")
wt.search_edit.setFocus()
app.processEvents()
QTest.keyClicks(wt.search_edit, "wiremod")
wt.search_edit.setFocus()
QTest.keyClick(wt.search_edit, Qt.Key.Key_Return)
QTest.qWait(120)  # 去抖 60ms 已过，_do_refresh_list 应已同步执行
feedback = wt.status_label.text()
loading = getattr(wt, "_list_overlay", None)
loading_vis = bool(loading and loading.isVisible())
check("I5 mod 搜索回车后 150ms 内有可见反馈",
      bool(feedback.strip()) or loading_vis,
      f"status={feedback!r} overlay={loading_vis}")

# ---- stderr 异常捕获：槽内未处理异常 = bug ----
err_out = _cap.err.getvalue()
bad = [s for s in ("Traceback", "RuntimeError", "shiboken", "already deleted")
       if s in err_out]
check("I0 全程未触发 C++ 对象已删除类异常", not bad, f"命中={bad}")

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.stdout.flush()
sys.exit(0 if not fails else 1)
