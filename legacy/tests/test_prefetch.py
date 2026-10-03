"""详情页悬停预取验证（点击秒开的核心机制）。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_pf_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QEnterEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from swdm.core import WorkshopItem, ensure_dirs  # noqa: E402
from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

ensure_dirs()
win = MainWindow()
win.resize(900, 700)
win.show()
app.processEvents()
tab = win.workshop_tab

items = [
    WorkshopItem(publishedfileid="200", appid="4000", title="mod X"),
    WorkshopItem(publishedfileid="201", appid="4000", title="mod Y"),
]
tab._items = items
tab._populate(items)
app.processEvents()

ok = True
def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    print(("OK   " if cond else "FAIL ") + name + (f"  [{e}]" if e else ""))

# 清空缓存保证从干净状态开始
DetailPageWorker._page_cache.clear()

# 1. hover 信号连通
hovered = {"id": ""}
tab._on_card_hover = lambda iid: hovered.update(id=iid)
tab._cards()[0].enterEvent(
    QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
)
check("卡片 hover 信号到达 tab", hovered["id"] == "200", hovered["id"])

# 恢复真实方法，验证防抖定时器启动
tab._on_card_hover = tab.__class__._on_card_hover.__get__(tab)
tab._on_card_hover("200")
check("预取防抖定时器已启动", tab._prefetch_timer.isActive())
check("待预取 id 记录正确", tab._prefetch_id == "200", str(tab._prefetch_id))

# 2. 已有缓存时预取跳过（不浪费请求）
DetailPageWorker._page_cache["202"] = (9999999999.0, "<html>")
tab._prefetch_id = "202"
tab._do_prefetch_detail()
check("已有缓存时跳过（未加入预取集合）", "202" not in tab._prefetching,
      str(sorted(tab._prefetching)))

# 3. 预取执行路径（mock api，不真实联网，验证写入缓存）
tab._prefetch_id = "203"
tab._prefetching.discard("203")

class _FakeApi:
    def _community_get(self, path, params):
        return f"<html>fake detail for {params['id']}</html>"

tab.svc._api = _FakeApi()
tab.svc.api = _FakeApi()
tab._do_prefetch_detail()
app.processEvents()
# worker 是 QThread，等它完成（同步等待不现实，改用标志轮询）
import time  # noqa: E402
_deadline = time.time() + 5
while "203" not in DetailPageWorker._page_cache and time.time() < _deadline:
    app.processEvents()
    time.sleep(0.05)
# done 信号跨线程排队，多处理几轮确保主线程收到
for _ in range(10):
    app.processEvents()
    time.sleep(0.02)
check("预取结果写入 5 分钟缓存", "203" in DetailPageWorker._page_cache,
      str(list(DetailPageWorker._page_cache.keys())))
check("预取完成后清理进行中标记", "203" not in tab._prefetching,
      str(sorted(tab._prefetching)))

# 4. 正在预取的物品不重复发请求
tab._prefetching.add("204")
tab._prefetch_id = "204"
calls = {"n": 0}
_f2 = _FakeApi._community_get
_FakeApi._community_get = lambda self, path, params: calls.update(
    n=calls["n"] + 1) or "<html>x</html>"
tab._do_prefetch_detail()
check("进行中的预取被跳过", calls["n"] == 0, str(calls["n"]))
_FakeApi._community_get = _f2

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
