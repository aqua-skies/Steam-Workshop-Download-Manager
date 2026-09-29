"""离线 GUI 构造测试：验证各 tab 能正常构造（不依赖网络）。
重点验证本轮新增：settings_tab 的游戏目录表格。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402
import tempfile  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="swdm_gui_offline_")
os.environ["APPDATA"] = _TMP

from swdm.gui.main_window import MainWindow  # noqa: E402
from swdm.gui.settings_tab import SettingsTab  # noqa: E402
from swdm.core import ensure_dirs  # noqa: E402

ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

win = MainWindow()
check("MainWindow 构造成功", win is not None)
# B④：调试 Tab 默认隐藏 → 默认 4 个标签页；debug_tab 实例仍存在
check("默认 4 个标签页（调试 Tab 隐藏）", win._tabs.count() == 4,
      str(win._tabs.count()))
check("debug_tab 实例存在（隐藏仍可访问）", hasattr(win, "debug_tab"))

# 设置页构造 + 游戏目录表格
st = win.settings_tab
check("SettingsTab 存在", isinstance(st, SettingsTab))
check("游戏目录表格存在", hasattr(st, "game_dirs_table"))
check("表格 3 列", st.game_dirs_table.columnCount() == 3)

# 添加一个游戏目录配置，验证表格加载
from swdm.core.game_dirs import set_game_dir  # noqa: E402

set_game_dir("4000", os.path.join(_TMP, "GModMods"))
st._load_game_dirs()
check("表格加载 1 行", st.game_dirs_table.rowCount() == 1,
      str(st.game_dirs_table.rowCount()))
check("表格含游戏名",
      st.game_dirs_table.item(0, 0).text().find("Garry") >= 0,
      st.game_dirs_table.item(0, 0).text())
check("表格含 appid", st.game_dirs_table.item(0, 1).text() == "4000")
check("表格含目录", st.game_dirs_table.item(0, 2).text().endswith("GModMods"),
      st.game_dirs_table.item(0, 2).text())

# 全部截图验证不崩
win._tabs.setCurrentIndex(3)
win.show()
app.processEvents()
win.close()

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
