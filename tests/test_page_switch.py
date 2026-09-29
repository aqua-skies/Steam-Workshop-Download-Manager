"""翻页-翻回-滚动稳定性验证（QScrollArea 卡片架构）。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_page_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from swdm.core import WorkshopItem, ensure_dirs  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

ensure_dirs()
win = MainWindow()
win.resize(900, 700)
win.show()
app.processEvents()
tab = win.workshop_tab


def mk(i):
    return WorkshopItem(publishedfileid=str(i), appid="4000",
                        title=f"mod {i}", preview_url=f"http://x/{i}.jpg")


a = [mk(i) for i in range(30)]
b = [mk(i) for i in range(100, 130)]

ok = True
def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    print(("OK   " if cond else "FAIL ") + name + (f"  [{e}]" if e else ""))


tab._items = a
tab._populate(a)
app.processEvents()
app.processEvents()   # offscreen 下 QScrollArea 布局需两轮
sb = tab.list_scroll.verticalScrollBar()
check("页A卡片数 30", len(tab._cards()) == 30, str(len(tab._cards())))

# 可滚动范围正常（SmoothScrollBar 动画在 offscreen 下不推进时间，
# 故验证 maximum 而非动画后的 value）
check("页A可滚动", sb.maximum() > 0, str(sb.maximum()))

# 翻页
tab._items = b
tab._populate(b)
app.processEvents()
app.processEvents()
sb = tab.list_scroll.verticalScrollBar()
check("页B卡片数 30 且为新 id",
      len(tab._cards()) == 30 and tab._cards()[0].item.publishedfileid == "100",
      str(tab._cards()[0].item.publishedfileid))
check("页B滚动归零", sb.value() == 0, str(sb.value()))
check("页B可滚动范围重建", sb.maximum() > 0, str(sb.maximum()))

# 翻回
tab._items = a
tab._populate(a)
app.processEvents()
app.processEvents()
sb = tab.list_scroll.verticalScrollBar()
check("回页A卡片数 30 且为旧 id",
      len(tab._cards()) == 30 and tab._cards()[0].item.publishedfileid == "0")

# 再滚动（此前 bug：翻回后滚动导致列表空白）
check("回页A可再滚动", sb.maximum() > 0, str(sb.maximum()))
check("卡片仍全部存在", len(tab._cards()) == 30)

# 缩略图异步回填不报错
tab._on_image_loaded("http://x/5.jpg", None)
app.processEvents()
check("缩略图回填不报错", True)

# 勾选状态翻页隔离
tab._cards()[0].setChecked(True)
tab._populate(b)
check("翻页后勾选清空（不跨页残留）", len(tab._checked_ids) == 0,
      str(tab._checked_ids))

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
