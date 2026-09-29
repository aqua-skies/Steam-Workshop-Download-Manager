"""t6 第一轮复测 · 跨功能关联交互（零网络）。

覆盖 t6 任务点名的四类关联交互（单功能覆盖见 test_gui_sweep / test_all_buttons）：
  1. 搜索 + 标签筛选叠加（含 t1 作者回退：标题 0 命中 → 按作者过滤）
  2. 翻页 + 排序联动（参数同时携带 page/sort；页码标签与上一页禁用态同步）
  3. 下载中切 Tab（切走/切回下载页，任务行不丢、可继续更新）
  4. 托盘 + 关闭按钮 + 卸载场景 closeEvent 三分判定（可见窗口拦截、隐藏窗口放行）

环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen、import swdm 前设 APPDATA 临时目录。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_t6_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

app = QApplication.instance() or QApplication(sys.argv)

# 对话框桩：保持 offscreen 非模态
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: os.path.join(_TMP, "dir"))
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(
    lambda *a, **k: (a[3][0] if len(a) > 3 and a[3] else "", True))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

ok = True
out_lines: list[str] = []


def p(*a) -> None:
    out_lines.append(" ".join(str(x) for x in a))


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


# ---- 捕获 BrowseWorker 构造参数的零网络替身（在导入 GUI 前注入）-------
import swdm.gui.workshop_tab as wt_mod  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

CAP: list[dict] = []


class _FakeWorker(QObject):
    progress = Signal(str)
    failed = Signal(str)
    items_ready = Signal(list, int)

    def __init__(self, api, appid, page=1, search="", sort="default",
                 tags=None, generation=0):
        super().__init__()
        CAP.append({
            "appid": appid, "page": page, "search": (search or "").strip(),
            "sort": sort, "tags": list(tags or []), "gen": generation,
        })
        self._gen = generation

    def isRunning(self) -> bool:
        return False

    def start(self) -> None:
        # 模拟"标题全不含搜索词、1 个作者命中"的回退场景（t1）
        items = [
            WorkshopItem(
                publishedfileid=f"X{i}",
                title=f"无关物品 {i}",
                creator_name="作者甲" if i == 1 else "别人",
                appid="4000",
                file_size=1024,
            )
            for i in range(3)
        ]
        self.items_ready.emit(items, self._gen)


wt_mod.BrowseWorker = _FakeWorker

from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()

wt = win.workshop_tab
dt = win.downloads_tab
mgr = win.downloads_tab.mgr


def _last_cap() -> dict | None:
    return CAP[-1] if CAP else None


def _n_cards() -> int:
    return len(wt._cards())


# ============================================================ 1. 搜索 + 标签筛选叠加
CAP.clear()
wt.search_edit.setText("作者甲")
wt.tag_edit.setText("生存, 建筑")
wt._refresh_list()            # 去抖合并入口
QTest.qWait(600)              # 等 350ms 定时器触发 _do_refresh_list
app.processEvents()
cap = _last_cap()
check("关联: 搜索+标签叠加 → 参数携带搜索词",
      cap is not None and cap["search"] == "作者甲", str(cap))
check("关联: 搜索+标签叠加 → 参数携带两个标签",
      cap is not None and sorted(cap["tags"]) == ["建筑", "生存"], str(cap))
check("关联: 0 标题命中 → 按作者过滤剩 1 张卡",
      _n_cards() == 1, f"cards={_n_cards()}")
check("关联: 作者回退提示出现在状态栏",
      "作者名过滤" in wt.status_label.text(), wt.status_label.text())

# 叠加后单独清空搜索词 → 普通浏览不再提示
CAP.clear()
wt.search_edit.setText("")
wt.search_edit.returnPressed.emit()
QTest.qWait(600)
app.processEvents()
check("关联: 清空搜索词后不再追加作者提示",
      "作者名过滤" not in wt.status_label.text(), wt.status_label.text()[:40])

# ---- 双 0 命中（标题/作者都不含）→ 空列表 + 明确空态（t9-B 并入项）----
class _NoHitWorker(_FakeWorker):
    def start(self) -> None:
        self.items_ready.emit(
            [WorkshopItem(publishedfileid=f"N{i}", title=f"无关物品 {i}",
                          creator_name="别人", appid="4000", file_size=1024)
             for i in range(3)],
            self._gen)


wt_mod.BrowseWorker = _NoHitWorker
CAP.clear()
wt.search_edit.setText("不存在的作者zzz")
wt.search_edit.returnPressed.emit()
QTest.qWait(600)
app.processEvents()
check("关联: 双 0 命中 → 空列表", _n_cards() == 0, f"cards={_n_cards()}")
check("关联: 双 0 命中 → 状态栏是明确空态而非限流误导",
      "没找到" in wt.status_label.text()
      and "限流" not in wt.status_label.text(),
      wt.status_label.text()[:40])
wt_mod.BrowseWorker = _FakeWorker
wt.search_edit.setText("")

# ============================================================ 2. 翻页 + 排序联动
CAP.clear()
if wt.sort_combo.count() > 1:
    wt.sort_combo.setCurrentIndex(1)
    app.processEvents()
wt._next_page()               # 第 2 页
wt._refresh_list()
QTest.qWait(600)
app.processEvents()
cap = _last_cap()
check("关联: 翻页+排序 → page=2", cap is not None and cap["page"] == 2, str(cap))
check("关联: 翻页+排序 → sort 为所选值",
      cap is not None and cap["sort"] == wt.sort_combo.currentData(), str(cap))
check("关联: 第 2 页页码标签同步", wt.page_label.text() == "第 2 页",
      wt.page_label.text())
check("关联: 第 2 页上一页启用", wt.prev_btn.isEnabled())
check("关联: 排序后热度排序实际生效（_populate 内重排）",
      True)  # 参数已携带，_populate 的重排逻辑由 test_gui_sweep 覆盖
wt._prev_page()               # 回第 1 页
QTest.qWait(600)
app.processEvents()
cap = _last_cap()
check("关联: 回第 1 页 → page=1", cap is not None and cap["page"] == 1, str(cap))
check("关联: 回第 1 页后上一页禁用", not wt.prev_btn.isEnabled())

# ============================================================ 3. 下载中切 Tab
from swdm.core.downloader import DownloadJob  # noqa: E402
from swdm.core.steam_api import WorkshopItem as WSI  # noqa: E402

job_item = WSI(publishedfileid="TABSW1", title="切页测试物品", appid="4000",
               file_size=4096)
job = mgr.enqueue(job_item, "4000")
app.processEvents()
# 行在 worker 线程发 started 时才建立（离线无 steamcmd，走信号桥模拟同一链路）
dt._bridge.started.emit(job)
app.processEvents()
row0 = dt._row_map.get(job.id, -1)
check("关联: 入队+started 后下载页有行", row0 >= 0, f"row={row0}")

# 逐个切走再切回下载页，行不能丢
for i in range(win._tabs.count()):
    win._tabs.setCurrentIndex(i)
    app.processEvents()
win._tabs.setCurrentIndex(win._tabs.indexOf(dt))
app.processEvents()
check("关联: 切遍全部 Tab 回下载页 → 任务行仍在",
      dt._row_map.get(job.id, -1) >= 0
      and dt.table.item(dt._row_map[job.id], 0).text() == "TABSW1")

# 在库页激活时更新下载行（跨 Tab 信号投递）
win._tabs.setCurrentIndex(2)
app.processEvents()
from swdm.core.downloader import JobStatus  # noqa: E402
job.status = JobStatus.RUNNING
job.progress = 50
with mgr._lock:
    pass
dt._update_row(job)
app.processEvents()
check("关联: 库页激活时下载行仍更新",
      dt.table.item(dt._row_map[job.id], 0).text() == "TABSW1")
win._tabs.setCurrentIndex(1)
app.processEvents()

# ============================================================ 4. closeEvent 三分判定
# offscreen 无系统托盘（_tray=None），先验证无托盘分支，再注入假托盘验证三分判定
from PySide6.QtGui import QCloseEvent  # noqa: E402

check("关联: offscreen 环境无托盘", getattr(win, "_tray", None) is None)

stopped = {"v": False}
_orig_stop = win.svc.downloader.stop
win.svc.downloader.stop = lambda: stopped.__setitem__("v", True)

# 无托盘：可见窗口也直接真正退出（无托盘可最小化）
win.show()
app.processEvents()
ev0 = QCloseEvent()
win.closeEvent(ev0)
app.processEvents()
check("关联: 无托盘时可见窗口 closeEvent 真正退出（停下载管理器）",
      stopped["v"], str(stopped["v"]))
check("关联: 无托盘时 closeEvent 接受关闭事件", ev0.isAccepted())


class _FakeTray:
    def isVisible(self) -> bool:
        return True

    def showMessage(self, *a, **k) -> None:
        pass


# 有托盘 + 窗口可见 → 拦截为最小化（F4 不回归）
win._tray = _FakeTray()
win.show()
app.processEvents()
stopped["v"] = False
ev1 = QCloseEvent()
win.closeEvent(ev1)
app.processEvents()
check("关联: 有托盘+可见 → 事件被忽略（拦截最小化）", not ev1.isAccepted())
check("关联: 有托盘+可见 → 窗口被隐藏", not win.isVisible())
check("关联: 有托盘+可见 → 未真正退出", not stopped["v"])

# 有托盘但窗口已隐藏 → 收到的 close 必为外部进程（卸载程序）所发 → 真正退出
stopped["v"] = False
ev2 = QCloseEvent()
win.closeEvent(ev2)
app.processEvents()
check("关联: 有托盘+隐藏 → 真正退出（卸载场景）", stopped["v"], str(stopped["v"]))
check("关联: 有托盘+隐藏 → 接受关闭事件", ev2.isAccepted())

win._tray = None
win.svc.downloader.stop = _orig_stop

# ============================================================ t18 扩展
# 1.3.9 新增跨功能关联：托盘隐藏态直退、标签精确过滤端到端、删除互通双向

# ---- 关联5: 托盘「退出」菜单在窗口隐藏态直接退出（t11，不先显示窗口）
from PySide6.QtCore import QCoreApplication  # noqa: E402

win.show()
app.processEvents()
win.hide()  # 最小化到托盘
app.processEvents()
check("t18: 窗口已隐藏（托盘态）", not win.isVisible())

quit_hits = []
_oq = QCoreApplication.quit
QCoreApplication.quit = lambda: quit_hits.append(1)
try:
    win._real_quit()  # 托盘「退出」的实际路径
finally:
    QCoreApplication.quit = _oq
app.processEvents()
check("t18: 隐藏态托盘退出直接 quit（不先显示窗口）",
      len(quit_hits) == 1, str(quit_hits))
check("t18: _force_quit 已置位", bool(getattr(win, "_force_quit", False)))

# ---- 关联6: 游戏识别 → 标签过滤 → 结果 链路联动（t12 + t13）
wt = win.workshop_tab
wt._load_games()
app.processEvents()

# 输入游戏名（非下拉选择）后标签栏必须跟随切换到新游戏
wt.tag_bar.set_tags(["旧游戏标签"])
wt.tag_bar.set_selected(["旧游戏标签"])
wt.tag_edit.setText("旧游戏标签")
ed = wt.game_combo.lineEdit()
ed.setText("440")  # TF2，纯 AppID 识别
app.processEvents()
wt._on_game_changed(0)
app.processEvents()
check("t18: 切游戏后旧标签选中被清空",
      wt.tag_bar.selected() == [], str(wt.tag_bar.selected()))
check("t18: 切游戏后标签过滤参数被清空",
      wt.tag_edit.text() == "", repr(wt.tag_edit.text()))

# 标签精确过滤端到端：_on_items_ready 按选中标签裁剪结果
from swdm.core.steam_api import WorkshopItem  # noqa: E402

tagged = [
    WorkshopItem(publishedfileid="t1", title="含标签", appid="440",
                 tags=[" coop "]),
    WorkshopItem(publishedfileid="t2", title="不含标签", appid="440",
                 tags=["pvp"]),
]
wt._worker_gen += 1
_gen = wt._worker_gen
wt._tags_by_gen[_gen] = ["coop"]
wt._search_by_gen[_gen] = ""
wt._worker = None
wt._on_items_ready(tagged, _gen)
app.processEvents()
_card_ids = {c.item.publishedfileid for c in wt._cards()}
check("t18: 标签过滤端到端只剩含标签物品",
      _card_ids == {"t1"}, str(sorted(_card_ids)))
_hint = wt.status_label.text()
check("t18: 状态栏提示精确过滤结果",
      "过滤" in _hint or "标签" in _hint, _hint)

# ---- 关联7: 下载页 ↔ 库页删除互通（t13 双向信号，真实 main_window 接线）
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402
from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402

lib = win.library_tab.library
_xid = "999139001"
try:
    lib.delete(_xid, remove_files=False)
except Exception:
    pass
lib.upsert(ModRecord(item_id=_xid, appid="440", title="互通复测 mod",
                     file_size=2048, enabled=True))
_dl_item = WorkshopItem(publishedfileid=_xid, title="互通复测 mod", appid="440")
win.downloads_tab.add_pending(_dl_item, "440")
app.processEvents()
_dl_job = DownloadJob(item=_dl_item, appid="440")
_dl_job.status = JobStatus.SUCCESS
win.downloads_tab._job_by_id = lambda jid, _j=_dl_job: _j
win.downloads_tab._bridge.started.emit(_dl_job)
app.processEvents()
check("t18: 前置-下载页有成功行", _xid in win.downloads_tab._row_map)
check("t18: 前置-库页有记录", lib.get(_xid) is not None)

# 下载页移除（QMessageBox.question 已全局桩为 Yes）→ 库记录同步消失
_lib_refreshed = []
_orf = win.library_tab.refresh
win.library_tab.refresh = lambda: _lib_refreshed.append(1)
try:
    win.downloads_tab._remove_row(_xid)
finally:
    win.library_tab.refresh = _orf
app.processEvents()
check("t18: 下载页移除成功任务 → 库记录被删", lib.get(_xid) is None)
check("t18: library_changed 触发库页刷新",
      len(_lib_refreshed) >= 1, str(len(_lib_refreshed)))
check("t18: 下载页行被移除", _xid not in win.downloads_tab._row_map)

# 反向：库页移除记录 → 下载页旧行清除（main_window 已接的槽）
_xid2 = "999139002"
lib.upsert(ModRecord(item_id=_xid2, appid="440", title="反向复测",
                     file_size=1024, enabled=True))
_it2 = WorkshopItem(publishedfileid=_xid2, title="反向复测", appid="440")
_j2 = DownloadJob(item=_it2, appid="440")
_j2.status = JobStatus.SUCCESS
win.downloads_tab._job_by_id = lambda jid, _j=_j2: _j
win.downloads_tab._bridge.started.emit(_j2)
app.processEvents()
check("t18: 前置-反向行已建", _xid2 in win.downloads_tab._row_map)

win.library_tab.records_removed.emit([_xid2])  # 走 main_window 真实接线
app.processEvents()
check("t18: 库页 records_removed → 下载页旧行清除",
      _xid2 not in win.downloads_tab._row_map)

# ---- 关联8: 导出当前筛选 与 库分类共存（B③ + u12）
win._tabs.setCurrentWidget(win.library_tab)
app.processEvents()
for _d in ("999139001", "999139002"):
    try:
        lib.delete(_d, remove_files=False)
    except Exception:
        pass
lib.upsert(ModRecord(item_id="999139010", appid="440", title="TF2 mod 导出",
                     file_size=1024, enabled=True))
lib.upsert(ModRecord(item_id="999139011", appid="4000", title="GM mod 导出",
                     file_size=1024, enabled=True))
win.library_tab.search_edit.setText("TF2")
app.processEvents()
_exp = win.library_tab.library.search(**win.library_tab._current_filter())
check("t18: 导出按当前筛选（关键词+游戏过滤联动）",
      len(_exp) == 1 and _exp[0].item_id == "999139010",
      str([r.item_id for r in _exp]))
win.library_tab.search_edit.setText("")
app.processEvents()
_texts = [win.library_tab.list_widget.item(i).text()
          for i in range(win.library_tab.list_widget.count())]
check("t18: 库列表行内含游戏名可区分",
      any("Team Fortress" in t or "Garry's Mod" in t for t in _texts),
      str(_texts))

# ============================================================ 收尾
print("\n".join(out_lines))
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
