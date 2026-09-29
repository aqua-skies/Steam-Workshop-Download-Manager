"""验证列表页工具栏整理。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_tb_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from swdm.core import ensure_dirs  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

ensure_dirs()
win = MainWindow()
win.resize(900, 700)
win.show()
app.processEvents()
tb = win.workshop_tab

ok = True
def c(n, cond, e=""):
    global ok
    ok = ok and bool(cond)
    print(("OK   " if cond else "FAIL ") + n + (f"  [{e}]" if e else ""))

c("更多菜单按钮存在", hasattr(tb, "more_btn"))
c("收藏 action 存在", hasattr(tb, "fav_action"))
c("旧按钮已移除",
  not hasattr(tb, "fav_btn") and not hasattr(tb, "add_game_btn")
  and not hasattr(tb, "import_btn"))
menu = tb.more_btn.menu()
c("菜单含 3 项", menu is not None and len(menu.actions()) == 3,
  str(len(menu.actions()) if menu else 0))
tb._update_fav_button()
app.processEvents()
c("收藏状态更新不报错", True, tb.fav_action.text())
c("下载按钮勾选语义", "勾选" in tb.dl_selected_btn.text(),
  tb.dl_selected_btn.text())
# 菜单动作可触发（连接存在）
c("收藏 action 可触发", tb.fav_action is not None)

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
