"""压力测试：模拟高频交互，定位事件循环卡顿（无响应）热点。

在每个操作前后采样 Qt 事件循环计时，标记 >100ms 的卡顿点。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_stress_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QElapsedTimer  # noqa: E402
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

from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()

wt = win.workshop_tab
SLOW = []


def time_op(name, fn):
    t = QElapsedTimer()
    t.start()
    fn()
    # 处理完所有挂起事件（含异步回调返回）
    for _ in range(6):
        app.processEvents()
    ms = t.elapsed()
    flag = "  <<<< 卡顿" if ms > 100 else ""
    print(f"{ms:6d} ms  {name}{flag}", flush=True)
    if ms > 100:
        SLOW.append((name, ms))
    return ms


# ---- 1) 卡片渲染压力：30 张卡（真实列表规模）
from swdm.core.steam_api import WorkshopItem  # noqa: E402


def make_items(n=30):
    return [
        WorkshopItem(
            publishedfileid=str(3800000000 + i),
            title=f"测试模组名称很长很长很长的情况 {i} —— 特别长的标题",
            appid="4000",
            creator="76561198146839798",
            creator_name=f"Author{i}",
            file_size=10 * 1024 * 1024 * (i + 1),
            tags=[f"标签{j}" for j in range(5)],
            preview_url="",
        )
        for i in range(n)
    ]


time_op("填充 30 张卡片", lambda: wt._populate(make_items(30)))

# ---- 2) 重复填充（翻页场景）
time_op("再次填充 30 张卡片（翻页）", lambda: wt._populate(make_items(30)))
time_op("清空卡片", wt._clear_cards)
time_op("填充 60 张卡片", lambda: wt._populate(make_items(60)))

# ---- 3) 搜索联想压力：快速连打 10 个字符（防抖场景）
ed = wt.game_combo.lineEdit()
def type_burst():
    for ch in "garrysmod":
        ed.setText(ed.text() + ch)
        app.processEvents()
time_op("连打 9 字符（含防抖）", type_burst)

# ---- 4) 标签栏压力
time_op("标签栏填充 77 个标签",
        lambda: wt.tag_bar.set_tags([f"标签{i}" for i in range(77)]))
time_op("标签栏选中 5 个",
        lambda: wt.tag_bar.set_selected([f"标签{i}" for i in range(5)]))

# ---- 5) 详情页打开（本地数据，无网络）
items = make_items(3)
wt._items = items
time_op("打开详情弹窗", lambda: wt._show_detail(items[0].publishedfileid))
app.processEvents()
for d in app.topLevelWidgets():
    if d.__class__.__name__ == "DetailDialog":
        time_op("关闭详情弹窗", d.close)

# ---- 6) 下载页批量行
from swdm.core.downloader import DownloadJob  # noqa: E402
dt = win.downloads_tab
def add_rows():
    for i in range(20):
        j = DownloadJob(item=items[0], appid="4000")
        j.status = "queued"
        dt._ensure_row(j)
time_op("下载页添加 20 行", add_rows)
time_op("下载页更新 20 行进度", lambda: [dt._update_row(j) for j in []])

# ---- 7) 库页刷新
lt = win.library_tab
time_op("库页刷新（空）", lt.refresh)

# ---- 8) 状态栏与切页
time_op("切换 5 个 Tab", lambda: [win._tabs.setCurrentIndex(i) for i in range(5)])

# ---- 9) 排序切换（UX 审计发现的未接信号场景，测刷新耗时）
time_op("切换排序维度 4 次",
        lambda: [wt.sort_combo.setCurrentIndex(i % 4) for i in range(4)])

# ---- 10) 标签快速选中/取消（并发筛选压力）
time_op("标签快速选 10 个再取消",
        lambda: [wt.tag_bar.set_selected([f"标签{i}"]) or
                 wt.tag_bar.set_selected([]) for i in range(10)])

# ---- 11) 待执行请求排队（手感优化路径）
wt._pending_refresh = False
items3 = make_items(5)
wt._populate(items3)
app.processEvents()
time_op("populate 后立即再 populate（翻页竞态）",
        lambda: wt._populate(make_items(5)))

# ---- 12) 详情弹窗开关 5 次（内存泄漏粗测）
def open_close_5():
    for _ in range(5):
        wt._show_detail(items3[0].publishedfileid)
        app.processEvents()
        for d in app.topLevelWidgets():
            if d.__class__.__name__ == "DetailDialog":
                d.close()
                break
time_op("详情弹窗开关 5 次", open_close_5)

# ---- 13) 图片缓存满量清空触发（workers max_cache=300）
from swdm.gui import workers as _w  # noqa: E402
def fill_image_cache():
    from PySide6.QtGui import QPixmap
    for i in range(310):
        _w._image_cache[f"url_{i}"] = QPixmap(96, 96)
time_op("图片缓存填充 310 张（触发清空）", fill_image_cache)

print("\n=== 卡顿热点（>100ms） ===", flush=True)
for name, ms in SLOW:
    print(f"  {ms} ms  {name}", flush=True)
print("RESULT:", "NO_SLOW" if not SLOW else f"{len(SLOW)}_SLOW")
sys.exit(0)
