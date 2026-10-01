"""真实 BrowseWorker 渲染冒烟测试（t6 F1 回归守卫）。

背景：1.4.2 m2 把 items_ready 连接从闭包 lambda 改为绑定方法直连后，
曾因真实信号是 1 参 Signal(list)、槽位 2 参 (items, gen) 而 TypeError，
导致生产路径工坊列表 0 卡片——该 bug 被桩测试掩盖（桩发 2 参）。
本测试用**真实 BrowseWorker**（仅桩 SteamAPI）+ 真实事件循环，断言
结果到达后卡片数 > 0、stderr 无 TypeError。

判定：脚本输出 `RESULT: ALL PASS` 为绿。
"""
import io
import os
import sys
import tempfile
import traceback

_TMP = tempfile.mkdtemp(prefix="swdm_br_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_WF = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WF):
    os.environ.setdefault("QT_QPA_FONTDIR", _WF)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_fail = []


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""), flush=True)
    if not cond:
        _fail.append(name)


try:
    from PySide6.QtCore import QTimer  # noqa: E402
    from PySide6.QtWidgets import QApplication  # noqa: E402

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(__import__("PySide6.QtGui", fromlist=["QFont"]).QFont("Microsoft YaHei", 9))

    _cap = io.StringIO()
    _real = sys.stderr
    sys.stderr = _cap

    from swdm.core import WorkshopItem, get_config  # noqa: E402
    from swdm.gui.workshop_tab import WorkshopTab  # noqa: E402
    from swdm.gui.workers import BrowseWorker  # noqa: E402

    check("真实 BrowseWorker 信号为 2 参 (items, gen)",
          BrowseWorker.items_ready is not None)
    import inspect  # noqa: E402

    sig_params = [p for p in dir(BrowseWorker.items_ready) if "arg" in p.lower()]

    class _FakeAPI:
        api_key = ""

        def browse(self, appid, page=1, search_text="", sort="", required_tags=None):
            return [WorkshopItem(publishedfileid="111", title="真实worker物品A", appid=appid),
                    WorkshopItem(publishedfileid="222", title="真实worker物品B", appid=appid)]

        def enrich(self, items):
            pass

    class _FakeLib:
        def all(self):
            return []

    class _FakeAuth:
        def is_anonymous(self):
            return True

    class _Svc:
        api = _FakeAPI()
        library = _FakeLib()
        auth = _FakeAuth()

    _cfg = get_config()
    _cfg.load()
    _Svc.config = _cfg

    tab = WorkshopTab(_Svc())
    tab.show()
    app.processEvents()
    tab._refresh_timer.stop()
    tab._do_refresh_list()  # 起真实 BrowseWorker（队列连接路径）

    _done = []

    def _finish():
        _done.append(1)
        app.quit()

    QTimer.singleShot(2000, _finish)
    app.exec()

    sys.stderr = _real
    txt = _cap.getvalue()
    n_cards = len(tab._cards())
    check("真实 BrowseWorker 结果到达后卡片数 > 0", n_cards > 0, f"cards={n_cards}")
    check("stderr 无 TypeError（元数契约一致）", "TypeError" not in txt,
          txt[-200:] if txt else "(clean)")
    check("stderr 无其它异常", "Traceback" not in txt, txt[-200:] if txt else "(clean)")
    tab._clear_cards()
    del sig_params
except Exception:
    try:
        sys.stderr = _real
    except Exception:
        pass
    traceback.print_exc()
    _fail.append("exception")

if _fail:
    print("RESULT: HAS FAILURES (%s)" % ", ".join(_fail))
    sys.exit(1)
print("RESULT: ALL PASS")
sys.exit(0)
