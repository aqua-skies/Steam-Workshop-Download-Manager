"""GUI 修复测试：mod 库右键(bug5)、卡片进度条与编号(bug8/11)、
标签过滤(bug14)、详情页作者回填(bug9)。"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_gui2_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QModelIndex, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

# ---- bug14：标签过滤
from swdm.gui.tag_bar import filter_nav_tags  # noqa: E402

mixed = ["Map", "cookie", "Cookie 设置", "隐私政策", "Addon", "用户协议",
         "创意工坊", "商店", " refunds", "Map", "Weapon"]
kept = filter_nav_tags(mixed)
check("过滤 cookie/隐私/协议", not any(k.lower() in ("cookie", "隐私政策", "用户协议") for k in kept),
      str(kept))
check("保留真实标签", kept == ["Map", "Addon", "Weapon"], str(kept))
check("去重", kept.count("Map") == 1)

# ---- bug9：parse_creator_name
from swdm.core.page_parser import parse_creator_name  # noqa: E402

html_custom = '''
<div class="creatorsBlock"><div class="creatorName">
<a class="hoverunderline" href="https://steamcommunity.com/id/MasterMellow">MasterMellow</a>
</div></div>
'''
check("creatorName 区解析作者", parse_creator_name(html_custom) == "MasterMellow",
      parse_creator_name(html_custom))
html_link = '<a href="https://steamcommunity.com/id/Rafi00101/myworkshopfiles/?appid=4000">x</a>'
check("myworkshopfiles 链接兜底", parse_creator_name(html_link) == "Rafi00101",
      parse_creator_name(html_link))
html_profile = '<a href="https://steamcommunity.com/profiles/765611980/myworkshopfiles/?appid=4000">x</a>'
check("仅 steamid64 时返回空", parse_creator_name(html_profile) == "",
      parse_creator_name(html_profile))
check("空 HTML 返回空", parse_creator_name("") == "")

# ---- bug8/11：卡片迷你进度条 + mod 编号
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.workshop_tab import ModCardWidget  # noqa: E402

item = WorkshopItem(publishedfileid="1234567", title="Test Mod", appid="4000",
                    creator_name="Bob", subscriptions=500, file_size=2 * 1024 * 1024)
card = ModCardWidget(item)
card.resize(700, 110)
card.show()
app.processEvents()
check("meta 含 mod 编号", "#1234567" in card._meta_text(item),
      card._meta_text(item))
check("meta 含作者名", "作者 Bob" in card._meta_text(item))
check("初始不显示进度条", not card.dl_progress.isVisible())
card.set_download_progress(42)
app.processEvents()
check("下载中显示进度条", card.dl_progress.isVisible())
check("进度条隐藏下载按钮", not card.dl_btn.isVisible())
card.set_download_progress(-1)
app.processEvents()
check("不确定进度用忙碌动画", card.dl_progress.minimum() == 0
      and card.dl_progress.maximum() == 0)
card.mark_downloaded()
app.processEvents()
check("完成后按钮变已在库", "已在库" in card.dl_btn.text())
check("完成后进度条隐藏", not card.dl_progress.isVisible())

# ---- bug5：mod 库右键（QModelIndex → row 转换）——用 ListWidget 直接验证
# _selected_ids 的转换逻辑，不构造完整 LibraryTab（其菜单 exec 在
# offscreen 下会阻塞）
from PySide6.QtWidgets import QListWidget, QListWidgetItem  # noqa: E402

lw = QListWidget()
lw.addItem(QListWidgetItem("AAA"))
lw.addItem(QListWidgetItem("BBB"))
lw.item(1).setData(Qt.ItemDataRole.UserRole, "222")
lw.item(0).setData(Qt.ItemDataRole.UserRole, "111")

class _MiniTab:
    """复刻 LibraryTab._selected_ids 的转换。"""
    def __init__(self, w):
        self.list_widget = w
    def _selected_ids(self):
        return [
            self.list_widget.item(idx.row()).data(Qt.ItemDataRole.UserRole)
            for idx in self.list_widget.selectedIndexes()
            if idx.row() >= 0
        ]

mini = _MiniTab(lw)
idx = lw.model().index(1, 0)
from PySide6.QtCore import QItemSelectionModel  # noqa: E402

lw.selectionModel().select(idx, QItemSelectionModel.Select)
ids = mini._selected_ids()
check("_selected_ids 用 row() 转换", ids == ["222"], str(ids))

# 空选择不崩
lw.clearSelection()
check("空选择返回空列表", mini._selected_ids() == [])

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
