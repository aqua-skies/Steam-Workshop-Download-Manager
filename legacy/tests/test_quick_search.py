"""快捷搜索测试：详情页标签/作者/依赖标题点击 → 跳转筛选页搜索。"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.mkdtemp(prefix="swdm_quicksearch_")
os.environ["APPDATA"] = _TMP

import io as _io  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.core import WorkshopItem  # noqa: E402
from swdm.gui.detail_dialog import ModDetailDialog  # noqa: E402

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

item = WorkshopItem(
    publishedfileid="12345", appid="4000",
    title="测试 mod", creator="76561198000000000",
    creator_name="AwesomeModder",
    tags=["Addon", "Fun", "Realism"],
)

dlg = ModDetailDialog(item)
received = []
dlg.search_requested.connect(lambda k, v: received.append((k, v)))

# 1) 作者链接
p("作者链接文本:", dlg.author_label.text()[:80])
check("作者链接含作者名", "AwesomeModder" in dlg.author_label.text())
dlg.author_label.linkActivated.emit("author:AwesomeModder")
check("作者点击发出 search_requested",
      ("author", "AwesomeModder") in received, str(received[-1:]))

# 2) 标签 chips
check("标签 chips 已渲染", dlg.tags_layout.count() >= 3,
      str(dlg.tags_layout.count()))
# 找到第一个 chip 里的 QLabel 并触发 linkActivated
from PySide6.QtWidgets import QLabel  # noqa: E402

tag_fired = False
for i in range(dlg.tags_layout.count()):
    w = dlg.tags_layout.itemAt(i).widget()
    if w is None:
        continue
    for child in (w, *w.findChildren(QLabel)):
        if isinstance(child, QLabel) and child.text().startswith("<a"):
            child.linkActivated.emit("tag:Addon")
            tag_fired = True
            break
    if tag_fired:
        break
check("标签点击发出 search_requested", tag_fired and ("tag", "Addon") in received)

# 3) 依赖标题点击 → text 搜索
dlg.set_dependencies([("111", "VJ Base"), ("222", "SheepSquatch")])
dep_rows = [dlg.deps_layout.itemAt(i).widget()
            for i in range(dlg.deps_layout.count())
            if dlg.deps_layout.itemAt(i).widget() is not None]
check("依赖行已渲染", len(dep_rows) == 2, str(len(dep_rows)))
if dep_rows:
    dep_rows[0].title_label.linkActivated.emit("dep")
    check("依赖标题点击发出 text 搜索",
          ("text", "VJ Base") in received, str(received[-1:]))

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
