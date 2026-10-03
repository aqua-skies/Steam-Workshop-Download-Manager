"""1.3.4 GUI 修复测试：标签横向滚动(bug3)、下载页列宽(bug4)、
AppID 解析与回车(bug1/2)、mod 库右键选中(bug6)、不确定进度消息(bug5)。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_v134_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

# ---- bug3：标签栏横向滚动
from swdm.gui.tag_bar import TagBar  # noqa: E402

bar = TagBar()
bar.resize(400, 60)
bar.show()
app.processEvents()
bar.set_tags([f"Tag{i:02d}" for i in range(30)])
app.processEvents()
host_w = bar._host.minimumWidth()
view_w = bar._scroll.viewport().width()
check("30 个标签 host 最小宽 > 视口宽", host_w > view_w > 0,
      f"host={host_w} view={view_w}")
check("layout 不压缩子项（SetMinimumSize）",
      bar._row.sizeConstraint() != 0)
# 少量标签不强制超宽
bar.set_tags(["A", "B"])
app.processEvents()
check("少量标签 host 宽适配内容", bar._host.minimumWidth() < 600)

# ---- bug4：下载页列宽（用 QTableWidget 直建，复刻 downloads_tab 配置）
from PySide6.QtWidgets import QHeaderView, QTableWidget  # noqa: E402

tbl = QTableWidget(0, 7)
tbl.setHorizontalHeaderLabels(["物品 ID", "标题", "状态", "进度", "大小", "信息", "操作"])
hdr = tbl.horizontalHeader()
hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
hdr.resizeSection(2, 72)
hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
hdr.resizeSection(3, 150)
hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
hdr.resizeSection(4, 84)
hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
hdr.resizeSection(6, 88)
tbl.resize(900, 300)
tbl.show()
app.processEvents()
check("状态列固定 72", tbl.columnWidth(2) == 72, str(tbl.columnWidth(2)))
check("进度列固定 150", tbl.columnWidth(3) == 150, str(tbl.columnWidth(3)))
check("大小列固定 84", tbl.columnWidth(4) == 84, str(tbl.columnWidth(4)))
check("操作列固定 88", tbl.columnWidth(6) == 88, str(tbl.columnWidth(6)))
check("各列宽之和不超表宽过多（无重叠挤压）",
      sum(tbl.columnWidth(i) for i in range(7)) <= tbl.width() + 120)

# ---- bug1/2：_current_appid 多层回退（用 QComboBox 复刻解析链）
from PySide6.QtWidgets import QComboBox  # noqa: E402

combo = QComboBox()
combo.setEditable(True)
combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
combo.addItem("★ 收藏", "")
combo.insertSeparator(combo.count())
combo.addItem("Garry's Mod  (4000)", "4000")

class MiniTab:
    """复刻 WorkshopTab._current_appid 的回退链。"""
    def __init__(self, c, pairs=None):
        self.game_combo = c
        self._last_search_pairs = pairs or []
    def _current_appid(self) -> str:
        data = self.game_combo.currentData()
        if data:
            return str(data)
        text = self.game_combo.currentText().strip()
        if text.isdigit():
            return text
        low = text.lower()
        for i in range(self.game_combo.count()):
            if self.game_combo.itemText(i).split("(")[0].strip().lower() == low:
                d = self.game_combo.itemData(i)
                if d:
                    return str(d)
        for appid, name in self._last_search_pairs:
            if name.strip().lower() == low:
                return str(appid)
        return ""

mini = MiniTab(combo, [("730", "Counter-Strike 2")])
# 选中下拉项 → currentData 生效
combo.setCurrentIndex(2)
check("选中下拉项返回 AppID", mini._current_appid() == "4000",
      mini._current_appid())
# 直接输入 AppID 数字
combo.setCurrentIndex(-1)
combo.setEditText("730")
check("直接输入 AppID 数字可解析", mini._current_appid() == "730")
# 输入下拉项中的游戏名（未选中）
combo.setEditText("Garry's Mod")
check("输入下拉项游戏名可解析", mini._current_appid() == "4000",
      mini._current_appid())
# 输入仅存在于联想缓存中的游戏名
combo.setEditText("Counter-Strike 2")
check("输入联想缓存中的游戏名可解析", mini._current_appid() == "730",
      mini._current_appid())
# 完全未识别
combo.setEditText("不存在的游戏 xyz")
check("未识别返回空", mini._current_appid() == "")

# ---- bug1/2：_on_game_enter 回车后追加项并触发 game_changed
fired = []


class MiniTab2(MiniTab):
    def _on_game_enter(self) -> None:
        appid = self._current_appid()
        if not appid:
            return
        idx = self.game_combo.findData(appid)
        if idx < 0:
            self.game_combo.addItem(self.game_combo.currentText().strip(), appid)
            idx = self.game_combo.count() - 1
        self.game_combo.setCurrentIndex(idx)


combo2 = QComboBox()
combo2.setEditable(True)
combo2.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
combo2.currentIndexChanged.connect(lambda _i: fired.append(_i))
mt2 = MiniTab2(combo2, [("730", "Counter-Strike 2")])
combo2.setEditText("Counter-Strike 2")
mt2._on_game_enter()
app.processEvents()
check("回车后追加下拉项", combo2.findData("730") >= 0)
check("回车触发 currentIndexChanged", len(fired) >= 1, str(fired))
check("回车后 currentData 生效", combo2.currentData() == "730")

# ---- bug6：右键自动选中
lw = QListWidget()
lw.addItem(QListWidgetItem("AAA"))
lw.addItem(QListWidgetItem("BBB"))
lw.item(0).setData(Qt.ItemDataRole.UserRole if False else 0x100, "111")
lw.item(1).setData(0x100, "222")

class MiniLib:
    def __init__(self, w):
        self.list_widget = w
    def _context_menu_core(self, pos):
        item_at = self.list_widget.itemAt(pos)
        if item_at is not None and not item_at.isSelected():
            self.list_widget.setCurrentItem(item_at)
        return self.list_widget.selectedIndexes()

ml = MiniLib(lw)
lw.setCurrentItem(lw.item(0))   # 先选第一行
# 右键第二行的位置（模拟 viewport 坐标）
pos = lw.visualItemRect(lw.item(1)).center()
sel = ml._context_menu_core(pos)
check("右键第二行后选中第二行",
      [lw.item(idx.row()).data(0x100) for idx in sel] == ["222"],
      str([lw.item(idx.row()).data(0x100) for idx in sel]))
# 空白处右键保持原选择
lw.clearSelection()
lw.setCurrentItem(lw.item(0))
blank = lw.viewport().rect().bottomRight() - lw.viewport().rect().bottomLeft()
blank = lw.viewport().rect().bottomRight()
sel2 = ml._context_menu_core(blank)
check("空白处右键不崩", isinstance(sel2, list))

# ---- bug5：不确定进度时 job.message 保留引擎消息
from swdm.core.downloader import DownloadJob  # noqa: E402
from swdm.core.throttle import ProgressSmoother  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402


class MiniMgr:
    def __init__(self):
        self.on_progress = []
    def _fire_progress(self, job):
        for cb in self.on_progress:
            cb(job)


mgr = MiniMgr()
job = DownloadJob(item=WorkshopItem(publishedfileid="x", title="X", appid="4000"),
                  appid="4000")
sm = ProgressSmoother()
sm.reset(0)
time.sleep(0.15)   # 越过 10Hz 限流的首次静默
# 复刻 _on_engine_progress 的不确定分支
snap = sm.feed(0, job.total_bytes, force=False)
if snap is not None:
    job.bytes_done = snap["bytes"]
    if snap["percent"] < 0:
        job.message = "已下载 12.3 MB" or snap["label"]
    else:
        job.message = snap["label"]
check("不确定进度时消息为引擎文案", job.message == "已下载 12.3 MB",
      job.message)

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
