"""详情页评论折叠区验证。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_dd_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from swdm.core import WorkshopItem, ensure_dirs  # noqa: E402
from swdm.gui.detail_dialog import ModDetailDialog, Comment  # noqa: E402

ensure_dirs()

ok = True
def c(n, cond, e=""):
    global ok
    ok = ok and bool(cond)
    print(("OK   " if cond else "FAIL ") + n + (f"  [{e}]" if e else ""))

item = WorkshopItem(publishedfileid="12345", appid="4000", title="测试",
                    creator_name="作者A", tags=["Addon"])
dlg = ModDetailDialog(item)

c("评论折叠区存在", hasattr(dlg, "comments_section"))
c("评论区默认收起", not dlg.comments_section._content.isVisible())
t0 = dlg.comments_section._title_btn.text()
c("初始标题含「评论」", "评论" in t0, t0)

# 计数更新到标题
dlg.set_comment_count(42)
t1 = dlg.comments_section._title_btn.text()
c("计数显示在标题", "42" in t1, t1)

# 展开后箭头正确且标题保持
dlg.comments_section.setExpanded(True)
app.processEvents()
t2 = dlg.comments_section._title_btn.text()
c("展开后标题保持计数", "42" in t2 and "▾" in t2, t2)

# 填充评论（收起状态下数据仍正常写入）
dlg.set_comments([
    Comment(author="A", time="2024-01-01", content="好"),
    Comment(author="B", time="2024-01-02", content="赞"),
])
app.processEvents()
n_rendered = sum(
    1 for i in range(dlg.comments_layout.count())
    if dlg.comments_layout.itemAt(i).widget() is not None
    and dlg.comments_layout.itemAt(i).widget() is not dlg.comments_placeholder
)
c("评论填充正常", n_rendered >= 2, str(n_rendered))

# 折叠/展开不影响依赖区与冲突区
dlg.set_dependencies([("111", "VJ Base")])
c("依赖区不受评论折叠影响",
  sum(1 for i in range(dlg.deps_layout.count())
      if dlg.deps_layout.itemAt(i).widget() is not None
      and dlg.deps_layout.itemAt(i).widget() is not dlg.deps_placeholder) == 1)

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
