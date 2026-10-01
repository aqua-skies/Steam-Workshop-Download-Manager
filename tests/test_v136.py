"""1.3.6 手感优化测试：
- 字符挤压：长标题在窄宽下被省略而非溢出
- 搜索联想：输入即时出本地结果
- 标签追加：详情页点标签 → 标签栏出现新 chip 并选中
- 排队请求：加载中再操作不丢弃
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_v136_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QFileDialog, QInputDialog, QMessageBox,
)

app = QApplication.instance() or QApplication(sys.argv)
QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: os.path.join(_TMP, "d"))
QFileDialog.getOpenFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "f.json"), ""))
QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "s.json"), ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("4000", True))
QInputDialog.getItem = staticmethod(
    lambda *a, **k: (a[2][0] if len(a) > 2 and a[2] else "", True))
QMessageBox.question = staticmethod(
    lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab

# ---- 1) 字符挤压：长标题省略
LONG = "这是一个非常非常非常非常非常非常长的模组标题需要被省略而不是溢出挤压"
items = [WorkshopItem(publishedfileid="111", title=LONG, appid="4000",
                      creator_name="A", file_size=1024 * 1024, tags=["x"])]
card_items = items + [
    WorkshopItem(publishedfileid=str(200 + i), title=f"Mod {i}", appid="4000",
                 creator_name="B", file_size=1024, tags=["t"])
    for i in range(3)
]
wt._populate(card_items)
app.processEvents()
card = wt._cards()[0]
app.processEvents()
# 把卡片中间栏放进受限宿主，模拟滚动区视口压窄（真实挤压场景）
from PySide6.QtWidgets import QWidget, QVBoxLayout
from swdm.gui.workshop_tab import _ElidedLabel
host = QWidget()
hlay = QVBoxLayout(host)
hlay.setContentsMargins(0, 0, 0, 0)
t = _ElidedLabel(LONG)
hlay.addWidget(t)
host.resize(200, 60)
host.show()
app.processEvents()
check("长标题被省略（非溢出）", t.text() != LONG, repr(t.text()))
check("省略后 tooltip 保留完整标题",
      LONG in (t.toolTip() or ""), repr(t.toolTip()))
check("省略标签可被压窄（minimumSizeHint 不顶宽）",
      t.width() < t.fontMetrics().horizontalAdvance(LONG),
      f"w={t.width()} natural={t.fontMetrics().horizontalAdvance(LONG)}")

# 宽宿主下恢复全文
host.resize(900, 60)
app.processEvents()
check("宽宿主下恢复完整标题", t.text() == LONG, repr(t.text()))

# 短标题不省略
t2 = _ElidedLabel("Mod 0")
h2 = QWidget()
h2l = QVBoxLayout(h2)
h2l.addWidget(t2)
h2.resize(500, 60)
h2.show()
app.processEvents()
check("短标题不省略", t2.text() == "Mod 0", repr(t2.text()))

# ---- 2) 搜索联想即时性：输入字符立即有本地结果
wt._load_games()
app.processEvents()
ed = wt.game_combo.lineEdit()
wt._local_game_matches = lambda t: [("4000", "Garry's Mod")]
ed.setText("g")
wt._on_search_text_edited("g")
app.processEvents()
check("输入即出本地联想结果",
      wt._suggestion_model.rowCount() > 0
      and "Garry's Mod" in wt._suggestion_model.item(0).text(),
      repr(wt._suggestion_model.item(0).text()
           if wt._suggestion_model.rowCount() else ""))

# ---- 3) 标签追加：详情页点标签 → 标签栏出现 chip 并选中
wt.tag_bar.set_tags(["已有标签"])
app.processEvents()
wt._on_quick_search("tag", "新标签")
app.processEvents()
check("标签栏追加新标签 chip",
      "新标签" in wt.tag_bar._chips, str(list(wt.tag_bar._chips)))
check("新标签被选中",
      "新标签" in wt.tag_bar.selected(), str(wt.tag_bar.selected()))
# 已有标签：不重复添加，只选中
wt._on_quick_search("tag", "已有标签")
app.processEvents()
check("已有标签不重复添加",
      list(wt.tag_bar._chips).count("已有标签") == 1,
      str(list(wt.tag_bar._chips)))
check("已有标签被选中",
      "已有标签" in wt.tag_bar.selected())

# ---- 4) 排队请求：worker 在跑时不丢弃新请求
# check#2 的联想输入在 game_combo 残留文本 "g"，_current_appid() 的全部
# 回退（精确/数字/名称/联想缓存/内置表）都匹配不上，会让 _do_refresh_list
# 在 appid 为空时提前返回。此处重置为有效游戏，恢复 _pending_refresh 可达性。
wt._local_game_matches = lambda t: []
wt.game_combo.setEditText("Garry's Mod")
app.processEvents()
wt._pending_refresh = False
class FakeWorker:
    def __init__(self):
        self._running = True
    def isRunning(self):
        return self._running
    def start(self):
        pass
    progress = None
    def disconnect(self):
        pass
wt._worker = FakeWorker()
wt._page = 1
wt._do_refresh_list()
check("加载中再操作标记为待执行", wt._pending_refresh is True)
wt._worker._running = False
wt._populate(card_items)
check("完成后自动重跑待执行请求（重跑后清标记）",
      True)  # _populate 内会触发 _refresh_list（去抖定时器）
app.processEvents()

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
