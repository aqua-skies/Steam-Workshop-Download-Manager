"""勾选框选择机制测试 + 设置页布局修复回归（QScrollArea 卡片架构）。"""
from __future__ import annotations

import io as _io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_check_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.core import WorkshopItem, ensure_dirs  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


win = MainWindow()
tab = win.workshop_tab

# 造 3 个物品直接灌入列表
items = [
    WorkshopItem(publishedfileid="100", appid="4000", title="mod A"),
    WorkshopItem(publishedfileid="101", appid="4000", title="mod B"),
    WorkshopItem(publishedfileid="102", appid="4000", title="mod C"),
]
tab._items = items
tab._populate(items)  # 直接走渲染

check("卡片数正确", len(tab._cards()) == 3, str(len(tab._cards())))
check("初始无勾选", len(tab._checked_ids) == 0)
check("每张卡片含勾选框", all(c.check_box is not None for c in tab._cards()))
check("初始全部未勾选", all(not c.isChecked() for c in tab._cards()))

# 勾选第 0 张卡片（模拟真实点击：toggle 卡片内 QCheckBox）
cards = tab._cards()
cards[0].setChecked(True)
check("勾选后集合含该 id", tab._checked_ids == {"100"}, str(tab._checked_ids))
check("下载按钮文本更新", "(1)" in tab.dl_selected_btn.text(),
      tab.dl_selected_btn.text())

# 取消勾选
cards[0].setChecked(False)
check("取消后集合为空", len(tab._checked_ids) == 0, str(tab._checked_ids))

# 全选 → 3 项
tab._check_all()
check("全选后 3 项勾选", tab._checked_ids == {"100", "101", "102"},
      str(tab._checked_ids))
check("卡片 isChecked 同步", all(c.isChecked() for c in tab._cards()))
# 再点 → 全部取消
tab._check_all()
check("再点全选 → 全部取消", len(tab._checked_ids) == 0, str(tab._checked_ids))

# 重新填充（翻页模拟）：旧卡片销毁、勾选状态正确清空
tab._cards()[0].setChecked(True)
tab._populate(items)
check("重新填充后勾选清空", len(tab._checked_ids) == 0, str(tab._checked_ids))
check("重新填充后仍是 3 张新卡片", len(tab._cards()) == 3)


def _fake_mouse_left(widget):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(10, 10),
        QPointF(10, 10), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


# 详情入口只有"详情"按钮（bug3：移除整卡点击，避免误触）
detail_fired = {"id": ""}
tab._show_detail = lambda iid: detail_fired.update(id=iid)
tab._cards()[1].mousePressEvent(_fake_mouse_left(tab._cards()[1]))
check("整卡点击不打开详情", detail_fired["id"] == "", detail_fired["id"])

# 卡片仍含"详情"按钮（唯一入口）
btns = [b.text() for b in tab._cards()[1].findChildren(QPushButton)]
check("卡片含详情按钮", any("详情" in b for b in btns), str(btns))

# 勾选框不触发详情
detail_fired["id"] = ""
tab._cards()[2].setChecked(True)
check("勾选不误触详情", detail_fired["id"] == "", detail_fired["id"])

# 设置页布局回归：控件高度应 >= 18px
win.resize(900, 700)
win._tabs.setCurrentIndex(3)
win.show()
app.processEvents()
short = [n for n in ("username_edit", "password_edit", "mode_combo",
                     "api_key_edit", "library_edit")
         if getattr(win.settings_tab, n, None)
         and getattr(win.settings_tab, n).geometry().height() < 18]
check("设置页无压扁控件", not short, str(short))

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
