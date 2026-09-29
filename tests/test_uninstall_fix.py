"""卸载修复测试：托盘隐藏时外部 WM_CLOSE 能真正退出 + AppMutex 互斥量。

验证 closeEvent 的三分判定（F4 托盘功能不回归 + 卸载程序能退出）：
  1. 窗口可见 + 托盘可见  → 拦截（hide 最小化到托盘）
  2. 窗口已隐藏（托盘后台）→ 放行真正退出（Inno 卸载程序发的 WM_CLOSE）
  3. _force_quit 标志     → 无论可见与否都直接退出
另验证与 installer/swdm.iss AppMutex 同名的 win32 互斥量创建/释放。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_uninst_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


from swdm.gui import main_window as _mw  # noqa: E402
from swdm.gui.main_window import APP_MUTEX_NAME, MainWindow  # noqa: E402


class _QuitRecorder:
    """替身 QCoreApplication：记录 quit() 调用，避免测试进程被真正退出。

    _do_real_quit 调 QCoreApplication.quit()（模块全局名查找），
    替换模块属性即可拦截，其余属性透传真对象。
    """

    def __init__(self, real):
        self._real = real
        self.quit_count = 0

    def quit(self):
        self.quit_count += 1

    def instance(self):
        return self._real.instance()

    def __getattr__(self, name):
        return getattr(self._real, name)


_QCORE = _QuitRecorder(QCoreApplication)
_mw.QCoreApplication = _QCORE


class _FakeTray:
    """模拟可见托盘（offscreen 环境 QSystemTrayIcon 不可用，需手动注入）。"""

    def __init__(self, visible=True):
        self._visible = visible
        self.messages = []

    def isVisible(self):
        return self._visible

    def showMessage(self, *a, **k):
        self.messages.append(a)


# ---- 1. 窗口可见 + 托盘可见 → 拦截最小化（F4 功能不回归）
win = MainWindow()
win._tray = _FakeTray(True)
win._force_quit = False
win.show()
app.processEvents()
check("1 窗口可见时 isVisible 为 True", win.isVisible() is True)
ev = QCloseEvent()
win.closeEvent(ev)
check("1 窗口可见时 closeEvent 被拦截", ev.isAccepted() is False)
check("1 拦截后窗口被隐藏", win.isVisible() is False)
check("1 拦截时托盘提示被触发", len(win._tray.messages) >= 1)

# ---- 2. 窗口已隐藏（托盘后台）+ 外部 WM_CLOSE → 真正退出
ev2 = QCloseEvent()
win.closeEvent(ev2)
check("2 窗口隐藏时 closeEvent 放行真正退出", ev2.isAccepted() is True)

# ---- 3. _force_quit 标志：可见窗口也直接退出
win2 = MainWindow()
win2._tray = _FakeTray(True)
win2._force_quit = True
win2.show()
app.processEvents()
check("3 force_quit 窗口可见", win2.isVisible() is True)
ev3 = QCloseEvent()
win2.closeEvent(ev3)
check("3 _force_quit 时可见窗口也直接退出", ev3.isAccepted() is True)

# ---- 4. 托盘菜单"退出"链路（t11）：_real_quit 直接真正退出，不依赖 close()
win3 = MainWindow()
win3._tray = _FakeTray(True)
win3.show()
app.processEvents()
check("4 _real_quit 前标志为 False", win3._force_quit is False)
_QCORE.quit_count = 0
win3._real_quit()
check("4 _real_quit 置 _force_quit=True", win3._force_quit is True)
check("4 _real_quit 直接调 quit()（隐藏态也能退出）", _QCORE.quit_count == 1,
      str(_QCORE.quit_count))
check("4 _real_quit 释放了 AppMutex", win3._app_mutex is None)
ev4 = QCloseEvent()
win3.closeEvent(ev4)
check("4 托盘退出后 closeEvent 放行", ev4.isAccepted() is True)

# ---- 5. 无托盘环境（_tray=None）→ 直接退出
win4 = MainWindow()
win4._tray = None
win4.show()
app.processEvents()
ev5 = QCloseEvent()
win4.closeEvent(ev5)
check("5 无托盘时 closeEvent 直接退出", ev5.isAccepted() is True)

# ---- 6. AppMutex：与 ISS 同名，Windows 上创建并在退出时释放
check("6 APP_MUTEX_NAME 与 installer/swdm.iss 一致",
      APP_MUTEX_NAME == "SWDM_SingleInstance_Mutex")
if sys.platform == "win32":
    import ctypes  # noqa: E402

    win5 = MainWindow()
    check("6 Windows 上创建了 AppMutex 句柄", win5._app_mutex is not None)
    # 校验句柄可用：再次创建同名互斥量应返回 ERROR_ALREADY_EXISTS
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p,
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    dup = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    if dup:
        kernel32.CloseHandle(dup)
    check("6 互斥量全局可见（ERROR_ALREADY_EXISTS）", already is True)
    win5.close()
    check("6 退出后 AppMutex 已释放", win5._app_mutex is None)
else:
    check("6 非 Windows 跳过 AppMutex 句柄检查", True)

# ---- 7. t11 核心场景：模拟托盘右键菜单"退出"triggered → 立即退出
# （offscreen 无系统托盘，复现 _build_tray 的菜单接线）
win7 = MainWindow()
win7._tray = _FakeTray(True)
win7.show()
app.processEvents()
menu7 = QMenu(win7)
act_show7 = menu7.addAction("显示主窗口")
act_show7.triggered.connect(win7._show_from_tray)
act_quit7 = menu7.addAction("退出")
act_quit7.triggered.connect(win7._real_quit)

# 7a. 可见态点托盘"退出" → 真正退出
_QCORE.quit_count = 0
act_quit7.trigger()
check("7a 可见态托盘退出触发 quit()", _QCORE.quit_count == 1,
      str(_QCORE.quit_count))

# 7b. 隐藏态点托盘"退出" → 仍然真正退出
# （旧实现 close() 对不可见窗口不发 QCloseEvent，进程残留——本次 bug）
win7.hide()
app.processEvents()
check("7b 隐藏态窗口不可见", win7.isVisible() is False)
_QCORE.quit_count = 0
act_quit7.trigger()
check("7b 隐藏态托盘退出仍触发 quit()", _QCORE.quit_count == 1,
      str(_QCORE.quit_count))
check("7b 隐藏态退出置 _force_quit=True", win7._force_quit is True)

# 7c. "显示主窗口"菜单项恢复窗口（F4 不回归）
win7.show()
app.processEvents()
win7.hide()
app.processEvents()
act_show7.trigger()
app.processEvents()
check("7c 托盘「显示主窗口」恢复可见", win7.isVisible() is True)

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name
          + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
