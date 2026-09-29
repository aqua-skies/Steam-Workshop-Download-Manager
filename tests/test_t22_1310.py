"""t22 · 1.3.10 遗留项验证（B④ 调试 Tab 默认隐藏 / C② 暂停继续合并 / D 搜索间隔+熔断）。

环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen，import swdm 前设 APPDATA 临时目录。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

_TMP = tempfile.mkdtemp(prefix="swdm_t22_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

# _apply_all 等会弹模态对话框，offscreen 下永久阻塞 → 统一打桩
QMessageBox.information = staticmethod(lambda *a, **k: 0)
QMessageBox.warning = staticmethod(lambda *a, **k: 0)
QMessageBox.critical = staticmethod(lambda *a, **k: 0)

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))
    print(("OK  " if cond else "FAIL") + f"  {name}" + (f"  {e}" if e and not cond else ""))


# ================================================================ B④ 调试 Tab 默认隐藏
try:
    from swdm.core.config import Config

    cfg = Config()
    check("B4-1: show_debug_panel 默认 False", cfg.get("logging", "show_debug_panel") is False,
          str(cfg.get("logging", "show_debug_panel")))

    from swdm.gui.main_window import MainWindow

    def has_debug_tab(w):
        for i in range(w._tabs.count()):
            if w._tabs.widget(i) is w.debug_tab:
                return True
        return False

    win = MainWindow()
    app.processEvents()

    check("B4-2: win.debug_tab 属性存在（测试耦合保护）", hasattr(win, "debug_tab"))
    check("B4-3: 默认配置下调试 Tab 不显示", not has_debug_tab(win))
    check("B4-4: 默认 Tab 数量为 4", win._tabs.count() == 4, str(win._tabs.count()))

    st = win.settings_tab
    check("B4-5: 设置页有调试面板开关", hasattr(st, "debug_panel_check"))
    check("B4-6: 开关默认未勾选", not st.debug_panel_check.isChecked())

    # 开关持久化路径：经 settings_tab._apply_all 写入 svc.config
    # （注意：win.close() 的退出路径会保存 svc.config，必须走同一对象，
    #  否则退出时会用内存中的旧值覆盖文件）
    st.debug_panel_check.setChecked(True)
    st._apply_all()
    check("B4-7: 保存后 show_debug_panel=True",
          win.svc.config.get("logging", "show_debug_panel") is True)

    win.close()
    win2 = MainWindow()   # 模拟下次启动
    app.processEvents()
    check("B4-8: 开启后调试 Tab 显示", has_debug_tab(win2))
    check("B4-9: 开启后 Tab 数量为 5", win2._tabs.count() == 5, str(win2._tabs.count()))
    # 开启态下开关回读为勾选
    check("B4-10: 开启态开关回读勾选", win2.settings_tab.debug_panel_check.isChecked())
except Exception:
    check("B④ 异常", False, traceback.format_exc())

# ================================================================ C② 暂停/继续合并为单按钮
try:
    dt = win2.downloads_tab
    mgr = win2.svc.downloader

    check("C2-1: 暂停/继续已合并为单按钮（无 resume_all_btn）",
          not hasattr(dt, "resume_all_btn"))
    check("C2-2: 按钮文案默认为暂停", "暂停" in dt.pause_all_btn.text(), dt.pause_all_btn.text())

    dt._toggle_pause_all()
    app.processEvents()
    check("C2-3: 暂停后 mgr.paused=True", mgr.paused is True)
    check("C2-4: 暂停后按钮文案变为继续", "继续" in dt.pause_all_btn.text(), dt.pause_all_btn.text())
    check("C2-5: 暂停后按钮仍可用", dt.pause_all_btn.isEnabled())

    dt._toggle_pause_all()
    app.processEvents()
    check("C2-6: 继续后 mgr.paused=False", mgr.paused is False)
    check("C2-7: 继续后按钮文案变回暂停", "暂停" in dt.pause_all_btn.text(), dt.pause_all_btn.text())

    win2.close()
except Exception:
    check("C② 异常", False, traceback.format_exc())

# ================================================================ D GameSearch 间隔 + 熔断退避
try:
    from swdm.core.game_search import GameSearchClient

    gsc = GameSearchClient()
    check("D-1: 最低间隔为 0.7s", abs(gsc._min_interval - 0.7) < 1e-9, str(gsc._min_interval))

    import requests

    class _FakeSession:
        def __init__(self):
            self.headers = {}
            self.proxies = {}
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1
            raise requests.ConnectionError("WinSock 10053")

    gsc._session = _FakeSession()

    # 首次失败：ConnectionError → 立即进入冷却
    r1 = gsc.search("garry")
    check("D-2: 连接失败返回空列表", r1 == [])
    check("D-3: 连接失败触发熔断冷却", gsc._in_cooldown() is True)

    # 冷却期内搜索：直接返回空、不调网络
    calls_before = gsc._session.calls
    r2 = gsc.search("csgo")
    check("D-4: 冷却期内返回空列表", r2 == [])
    check("D-5: 冷却期内未发网络请求", gsc._session.calls == calls_before,
          f"{calls_before}->{gsc._session.calls}")

    # 冷却结束后恢复发请求
    gsc._cooldown_until = 0.0
    gsc.search("l4d2")
    check("D-6: 冷却结束后恢复发请求", gsc._session.calls == calls_before + 1)

    # 连续 3 次非连接级失败也触发熔断
    gsc2 = GameSearchClient()

    class _FakeSession2:
        def __init__(self):
            self.headers = {}
            self.proxies = {}
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1
            raise ValueError("bad json")

    gsc2._session = _FakeSession2()
    for _ in range(3):
        gsc2.search("xyz")
    check("D-7: 连续 3 次失败触发熔断", gsc2._in_cooldown() is True)

    # 成功后失败计数清零 + DLC 过滤
    gsc3 = GameSearchClient()

    class _FakeSession3:
        def __init__(self):
            self.headers = {}
            self.proxies = {}
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1

            class _R:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {"items": [
                        {"type": "app", "id": 4000, "name": "Garry's Mod",
                         "tiny_image": "http://x/y.jpg"},
                        {"type": "dlc", "id": 1, "name": "X DLC"},
                    ]}

            return _R()

    gsc3._session = _FakeSession3()
    gsc3._fail_streak = 2
    res = gsc3.search("garry")
    check("D-8: 成功返回过滤 DLC 后的结果", len(res) == 1 and res[0].appid == "4000",
          str(res))
    check("D-9: 成功后失败计数清零", gsc3._fail_streak == 0)

    # 缓存命中路径：第二次相同 term 不再发请求
    calls3 = gsc3._session.calls
    gsc3.search("garry")
    check("D-10: 缓存命中不再发请求", gsc3._session.calls == calls3,
          f"{calls3}->{gsc3._session.calls}")
except Exception:
    check("D 异常", False, traceback.format_exc())

# ================================================================ 汇总
failed = [r for r in RESULTS if not r[1]]
print(f"\n共 {len(RESULTS)} 项检查，{len(RESULTS) - len(failed)} 通过，{len(failed)} 失败")
for name, _, e in failed:
    print(f"  FAIL {name}\n{e}")
if failed or not RESULTS:
    sys.exit(1)
print("RESULT: ALL PASS")
