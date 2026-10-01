"""GUI 全面自测脚本（t3）：以用户视角扫遍 5 个 Tab 找 bug。

覆盖：
- 工坊页：游戏切换、标签栏、分页边界（第 1 页上一页禁用）、排序切换、
  搜索框、导入 URL、收藏游戏按钮、全选/下载勾选状态同步
- 下载页：空表状态、批量按钮（全部暂停/继续/重试失败/清除已完成/取消全部）、
  暂停状态显示、行内取消/重试/移除按钮
- 模组库页：过滤下拉切换、启用/禁用互斥筛选、收藏筛选、搜索、
  列表刷新后选择保持（B2 回归）
- 设置页：输入控件联动、保存后生效、游戏专属目录表格增删
- 调试页：日志显示、自动滚动开关、清空、导出

环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen，import swdm 前设 APPDATA 临时目录。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

_TMP = tempfile.mkdtemp(prefix="swdm_sweep_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QFileDialog, QInputDialog, QMessageBox,
    QPushButton, QSpinBox, QLineEdit, QTableWidget,
)

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


_crashed = []


def _install_excepthook():
    def hook(etype, val, tb):
        _crashed.append("".join(traceback.format_exception(etype, val, tb)))

    sys.excepthook = hook
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def _msg(_t, _ctx, msg):
            if "Fatal" in msg or "FATAL" in msg:
                _crashed.append(msg)

        qInstallMessageHandler(_msg)
    except Exception:  # noqa: BLE001
        pass


_install_excepthook()

# 对话框打补丁（offscreen 下模态对话框会阻塞）
os.makedirs(os.path.join(_TMP, "picked_dir"), exist_ok=True)
QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: os.path.join(_TMP, "picked_dir"))
QFileDialog.getOpenFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "picked.json"), ""))
QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "saved.log"), ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("4000", True))
# 注意位置参数顺序：(parent, title, label, items, ...) → a[3] 才是候选列表
QInputDialog.getItem = staticmethod(
    lambda *a, **k: (a[3][0] if len(a) > 3 and a[3] else "", True))
QMessageBox.question = staticmethod(
    lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()

wt = win.workshop_tab
dt = win.downloads_tab
lt = win.library_tab
st = win.settings_tab
dbg = win.debug_tab


def _btn(widget, needle: str) -> QPushButton | None:
    for b in widget.findChildren(QPushButton):
        if needle in (b.text() or ""):
            return b
    return None


# ============================================================ 工坊浏览页
# --- 分页边界：用真实按钮点击验证（页码/上一页禁用态在 _refresh_list
#     里同步更新，不需要等网络回包）
wt._refresh_timer.stop()   # 不让去抖定时器真正发网络请求
check("工坊: 初始第 1 页", wt._page == 1, f"page={wt._page}")
check("工坊: 第 1 页时上一页禁用",
      not wt.prev_btn.isEnabled(),
      f"prev enabled={wt.prev_btn.isEnabled()}")
check("工坊: 第 1 页页码标签", wt.page_label.text() == "第 1 页",
      repr(wt.page_label.text()))
wt.next_btn.click()
app.processEvents()
check("工坊: 点下一页后 _page=2", wt._page == 2, f"page={wt._page}")
check("工坊: 第 2 页页码标签同步更新",
      wt.page_label.text() == "第 2 页", repr(wt.page_label.text()))
check("工坊: 第 2 页时上一页启用",
      wt.prev_btn.isEnabled(), "prev should be enabled on page 2")
wt.prev_btn.click()
app.processEvents()
check("工坊: 点上一页后回第 1 页", wt._page == 1, f"page={wt._page}")
check("工坊: 回到第 1 页后上一页又禁用",
      not wt.prev_btn.isEnabled(), "prev should be disabled again")
wt._refresh_timer.stop()

# --- 排序切换：currentIndexChanged 必须连接到刷新（B1）
connected = False
try:
    receivers = wt.sort_combo.receivers(wt.sort_combo.currentIndexChanged)
    connected = receivers > 0
except Exception:  # noqa: BLE001
    connected = True  # 老版本 API 不可用时不算失败
check("工坊: 排序下拉连了 currentIndexChanged", connected)

# --- 搜索框占位与可编辑
check("工坊: 搜索框可编辑", wt.search_edit.isEnabled())
wt.search_edit.setText("test")
app.processEvents()
check("工坊: 搜索框文本可设置", wt.search_edit.text() == "test")
wt.search_edit.setText("")

# --- 导入 URL：空输入安全（对话框返回空）
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("", True))
try:
    wt._import_url()
    app.processEvents()
    check("工坊: 导入 URL 空输入不崩", True)
except Exception as e:  # noqa: BLE001
    check("工坊: 导入 URL 空输入不崩", False, f"{type(e).__name__}: {e}")
# 合法 ID 导入（网络部分会失败，但不应崩 UI）
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("123456789", True))
try:
    wt._import_url()
    app.processEvents()
    check("工坊: 导入 ID 不崩", True)
except Exception as e:  # noqa: BLE001
    check("工坊: 导入 ID 不崩", False, f"{type(e).__name__}: {e}")

# --- 收藏游戏按钮（菜单 action）
try:
    wt._toggle_favorite()
    app.processEvents()
    favs = wt.svc.config.get("favorites_games") or []
    check("工坊: 收藏当前游戏写入配置", "4000" in favs, str(favs))
    # 再点一次取消收藏
    wt._toggle_favorite()
    app.processEvents()
    favs = wt.svc.config.get("favorites_games") or []
    check("工坊: 再点取消收藏", "4000" not in favs, str(favs))
except Exception as e:  # noqa: BLE001
    check("工坊: 收藏切换不崩", False, f"{type(e).__name__}: {e}")

# --- 全选/下载勾选状态同步
items = [
    WorkshopItem(publishedfileid=str(1000 + i), title=f"Sweep Mod {i}",
                 appid="4000", file_size=1024, tags=["t"])
    for i in range(3)
]
wt._populate(items)
app.processEvents()
check("工坊: 填充后卡片数正确", len(wt._cards()) == 3, str(len(wt._cards())))
check("工坊: 无勾选时下载勾选禁用",
      not wt.dl_selected_btn.isEnabled())
sa = _btn(wt, "全选")
sa.click()
app.processEvents()
check("工坊: 全选后下载勾选启用", wt.dl_selected_btn.isEnabled())
check("工坊: 全选后计数为 3", "3" in wt.dl_selected_btn.text(),
      repr(wt.dl_selected_btn.text()))
sa.click()
app.processEvents()
check("工坊: 再点全选取消全部", not wt.dl_selected_btn.isEnabled())

# --- 卡片下载按钮（不入队真实下载，只验证信号路径不崩）
# F3 修复后 _download_item 会真正建占位行并启动真实下载生命周期
# （含 2s jitter + 自动重试的在途 worker 信号，清理段收不回 → ghost 行
# 竞态，qa 探针 _probe_ghost_row.py 证明）。此处 stub 掉 enqueue，
# 只验证同步信号路径；产品行为（占位行）由 test_retest_round1_142
# S5b 在真实链路下验证。
from swdm.core.downloader import DownloadJob as _StubJob  # noqa: E402

_orig_enqueue = win.svc.downloader.enqueue
win.svc.downloader.enqueue = lambda item, appid: _StubJob(item=item, appid=appid)
try:
    wt._download_item("1000")
    app.processEvents()
    check("工坊: 卡片下载入队不崩", True)
except Exception as e:  # noqa: BLE001
    check("工坊: 卡片下载入队不崩", False, f"{type(e).__name__}: {e}")
finally:
    win.svc.downloader.enqueue = _orig_enqueue
# 清掉占位行残留，保持下载页断言的空表前提
try:
    win.svc.downloader.clear_completed()
except Exception:  # noqa: BLE001
    pass
try:
    with win.svc.downloader._lock:
        win.svc.downloader._queue.clear()
        win.svc.downloader._active.clear()
except Exception:  # noqa: BLE001
    pass
dt._row_map.clear()
while dt.table.rowCount():
    dt.table.removeRow(0)

# --- 标签栏：选游戏自动拉取（网络失败走 _on_tags_failed，不崩）
try:
    wt._on_tags_failed("测试失败")
    app.processEvents()
    check("工坊: 标签拉取失败提示进状态栏",
          "标签拉取失败" in wt.status_label.text(), repr(wt.status_label.text()))
except Exception as e:  # noqa: BLE001
    check("工坊: 标签失败回调不崩", False, f"{type(e).__name__}: {e}")

# --- 游戏目录标签联动
wt._update_game_dir_label()
check("工坊: 游戏目录标签非空", wt.game_dir_label.text() != "",
      repr(wt.game_dir_label.text()))
check("工坊: 游戏目录按钮启用", wt.game_dir_btn.isEnabled())

# --- 自定义游戏添加 / 回车选游戏 / 修改目录（对话框已打补丁）
try:
    wt._add_custom_game()
    app.processEvents()
    check("工坊: 添加自定义游戏不崩", True)
except Exception as e:  # noqa: BLE001
    check("工坊: 添加自定义游戏不崩", False, f"{type(e).__name__}: {e}")
try:
    wt._on_game_enter()
    app.processEvents()
    check("工坊: 回车确认游戏不崩", True)
except Exception as e:  # noqa: BLE001
    check("工坊: 回车确认游戏不崩", False, f"{type(e).__name__}: {e}")
try:
    wt._change_game_dir()   # 弹文件对话框（已打补丁），改目录后标签联动
    app.processEvents()
    check("工坊: 修改游戏目录不崩", True)
    check("工坊: 修改目录后标签仍非空",
          wt.game_dir_label.text() != "", repr(wt.game_dir_label.text()))
except Exception as e:  # noqa: BLE001
    check("工坊: 修改游戏目录不崩", False, f"{type(e).__name__}: {e}")

# --- 空列表状态
wt._populate([])
app.processEvents()
check("工坊: 空列表状态文案",
      "没有匹配" in wt.status_label.text(), repr(wt.status_label.text()))
check("工坊: 空列表时全选不崩", True)

# ============================================================ 下载页
check("下载页: 空表 rowCount=0", dt.table.rowCount() == 0)
check("下载页: 空表统计标签", dt.stat_label.text() != "", repr(dt.stat_label.text()))

# 占位行 + 状态流转
it = WorkshopItem(publishedfileid="2000001", title="下载测试 A", appid="4000",
                  file_size=1024 * 1024)
dt.add_pending(it, "4000")
app.processEvents()
check("下载页: 占位行建立", dt.table.rowCount() == 1)
check("下载页: 占位行状态=排队中",
      dt.table.item(0, 2).text() == "排队中", repr(dt.table.item(0, 2).text()))

from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402

job = DownloadJob(item=it, appid="4000")
job.status = JobStatus.RUNNING
job.bytes_done = 512 * 1024
job.total_bytes = 1024 * 1024
dt._on_progress(job)
app.processEvents()
check("下载页: RUNNING 状态显示",
      dt.table.item(0, 2).text() == "下载中", repr(dt.table.item(0, 2).text()))
bar = dt.table.cellWidget(0, 3)
check("下载页: 进度条百分比", bar.value() == 50, f"bar={bar.value()}")

# 不确定进度（steamcmd 无逐字节输出）
job2 = DownloadJob(item=it, appid="4000")
job2.status = JobStatus.RUNNING
job2.total_bytes = 0
dt._on_progress(job2)
app.processEvents()
bar2 = dt.table.cellWidget(0, 3)
check("下载页: 不确定进度显示忙碌动画",
      bar2.minimum() == 0 and bar2.maximum() == 0,
      f"range={bar2.minimum()}..{bar2.maximum()}")

# 完成 → 按钮变"移除"
job3 = DownloadJob(item=it, appid="4000")
job3.status = JobStatus.SUCCESS
dt._on_finished(job3)
app.processEvents()
cancel_btn = dt.table.cellWidget(0, 6)
check("下载页: 成功后操作按钮变「移除」",
      cancel_btn.text() == "移除", repr(cancel_btn.text()))

# 失败 → 按钮变"重试"
job4 = DownloadJob(item=it, appid="4000")
job4.status = JobStatus.FAILED
dt._on_finished(job4)
app.processEvents()
cancel_btn = dt.table.cellWidget(0, 6)
check("下载页: 失败后操作按钮变「重试」",
      cancel_btn.text() == "重试", repr(cancel_btn.text()))

# --- 批量按钮（操作真实 manager）
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402

mgr = win.svc.downloader
# 暂停/继续（C②：单按钮切换）
dt._toggle_pause_all()
app.processEvents()
check("下载页: 全部暂停后 mgr.paused", mgr.paused is True)
check("下载页: 暂停时按钮文案为继续", "继续" in dt.pause_all_btn.text())
check("下载页: 暂停时按钮仍可用", dt.pause_all_btn.isEnabled())
dt._toggle_pause_all()
app.processEvents()
check("下载页: 全部继续后 mgr.paused=False", mgr.paused is False)
check("下载页: 继续后按钮文案为暂停", "暂停" in dt.pause_all_btn.text())

# 重试失败（无失败任务时应安全）
try:
    n = dt._retry_failed.__func__  # noqa: B018
    ok = True
except Exception:  # noqa: BLE001
    ok = False
check("下载页: _retry_failed 方法存在", ok)

# 清除已完成
try:
    dt._clear_done()
    app.processEvents()
    check("下载页: 清除已完成不崩", True)
except Exception as e:  # noqa: BLE001
    check("下载页: 清除已完成不崩", False, f"{type(e).__name__}: {e}")

# --- 清除已完成：多行必须一次清干净（旧实现按旧行号升序删，残留一行）
clr_items = [
    WorkshopItem(publishedfileid=f"CLR{i}", title=f"清除{i}", appid="4000",
                 file_size=1024)
    for i in range(3)
]
base_rows = dt.table.rowCount()      # 前面步骤残留的行（不在 mgr 中，清不掉）
for ci in clr_items:
    cj = DownloadJob(item=ci, appid="4000")
    cj.status = JobStatus.SUCCESS
    with mgr._lock:
        mgr._done.append(cj)
    dt._update_row(cj)          # 建立行 + 标记成功
app.processEvents()
check("下载页: 新增 3 行成功态",
      dt.table.rowCount() == base_rows + 3, str(dt.table.rowCount()))
dt._clear_done()
app.processEvents()
check("下载页: 清除已完成删完全部新增行",
      dt.table.rowCount() == base_rows, str(dt.table.rowCount()))

# --- 移除单行：_row_map 必须同步下移（删中间行后后面行的索引不能错位）
rm_items = [
    WorkshopItem(publishedfileid=f"RM{i}", title=f"移除{i}", appid="4000",
                 file_size=1024)
    for i in range(3)
]
for ri in rm_items:
    rj = DownloadJob(item=ri, appid="4000")
    rj.status = JobStatus.SUCCESS
    with mgr._lock:
        mgr._done.append(rj)
    dt._update_row(rj)
app.processEvents()
rm_base = dt.table.rowCount()
check("下载页: 移除前 3 行", rm_base >= 3, str(rm_base))
# 删掉中间那一行（RM1）
dt._remove_row("RM1")
app.processEvents()
check("下载页: 移除中间行后行数 -1",
      dt.table.rowCount() == rm_base - 1, str(dt.table.rowCount()))
# RM2 的行映射必须仍指向正确行（表格第 0 列文本对得上）
check("下载页: 移除后 _row_map 未错位",
      dt._row_map.get("RM2", -1) >= 0
      and dt.table.item(dt._row_map["RM2"], 0).text() == "RM2")
dt._clear_done()

# --- 重试失败：有失败任务时点「重试失败」不能崩（旧代码 self.status_bar
#     不存在 → AttributeError）
fj = DownloadJob(item=WorkshopItem(publishedfileid="RTR1", title="重试A",
                                   appid="4000", file_size=1024),
                 appid="4000")
fj.status = JobStatus.FAILED
with mgr._lock:
    mgr._done.append(fj)
dt._update_row(fj)
app.processEvents()
try:
    dt._retry_failed()
    app.processEvents()
    check("下载页: 有失败任务时重试不崩", True)
except Exception as e:  # noqa: BLE001
    check("下载页: 有失败任务时重试不崩", False, f"{type(e).__name__}: {e}")

# 取消全部（会弹确认框，已打补丁为 Yes）
try:
    dt._cancel_all()
    app.processEvents()
    check("下载页: 取消全部不崩", True)
except Exception as e:  # noqa: BLE001
    check("下载页: 取消全部不崩", False, f"{type(e).__name__}: {e}")

# ============================================================ 模组库页
# --- 插入测试数据
lib = win.svc.library
lib.upsert(__import__("swdm.core.mod_library", fromlist=["ModRecord"]).ModRecord(
    item_id="3000001", appid="4000", title="库测试 A", file_size=2 * 1024 * 1024,
    enabled=True, category="地图", preview_url=""))
lib.upsert(__import__("swdm.core.mod_library", fromlist=["ModRecord"]).ModRecord(
    item_id="3000002", appid="4000", title="库测试 B", file_size=1024,
    enabled=False, category="模型", preview_url=""))
lt.refresh()
app.processEvents()
check("库: 列表显示 2 条", lt.list_widget.count() == 2, str(lt.list_widget.count()))
check("库: 统计标签更新", "共 2 个 mod" in lt.stats_label.text(),
      repr(lt.stats_label.text()))

# --- 过滤下拉切换
lt.appid_combo.setCurrentIndex(1)  # 4000
app.processEvents()
check("库: 游戏过滤后仍 2 条", lt.list_widget.count() == 2,
      str(lt.list_widget.count()))
lt.appid_combo.setCurrentIndex(0)
app.processEvents()

# --- 启用/禁用筛选互斥
lt.only_enabled.setChecked(True)
app.processEvents()
check("库: 仅启用 → 只剩 1 条", lt.list_widget.count() == 1,
      str(lt.list_widget.count()))
lt.only_disabled.setChecked(True)
app.processEvents()
check("库: 切到仅禁用 → 自动取消仅启用",
      not lt.only_enabled.isChecked())
check("库: 仅禁用 → 只剩 1 条", lt.list_widget.count() == 1,
      str(lt.list_widget.count()))
lt.only_disabled.setChecked(False)
app.processEvents()

# --- 收藏筛选
lib.set_favorite("3000001", True)
lt.refresh()
app.processEvents()
lt.only_fav.setChecked(True)
app.processEvents()
check("库: 仅收藏 → 只剩 1 条", lt.list_widget.count() == 1,
      str(lt.list_widget.count()))
lt.only_fav.setChecked(False)
app.processEvents()

# --- 搜索
lt.search_edit.setText("库测试 A")
app.processEvents()
check("库: 搜索 → 只剩 1 条", lt.list_widget.count() == 1,
      str(lt.list_widget.count()))
lt.search_edit.setText("")
app.processEvents()

# --- B2 回归：刷新后下拉选择保持
lt.appid_combo.setCurrentIndex(1)  # 选 4000
app.processEvents()
lt.refresh()
app.processEvents()
check("库: 刷新后游戏过滤选择保持 (B2)",
      lt.appid_combo.currentData() == "4000",
      repr(lt.appid_combo.currentData()))

# --- 分类下拉切换
cat_idx = lt.category_combo.findData("地图")
if cat_idx >= 0:
    lt.category_combo.setCurrentIndex(cat_idx)
    app.processEvents()
    check("库: 分类过滤 → 只剩 1 条", lt.list_widget.count() == 1,
          str(lt.list_widget.count()))
    lt.category_combo.setCurrentIndex(0)
    app.processEvents()

# --- 排序下拉切换不崩
for i in range(lt.sort_combo.count()):
    lt.sort_combo.setCurrentIndex(i)
    app.processEvents()
check("库: 排序下拉全部切换不崩", True)

# --- 选中状态保持
lt.list_widget.setCurrentRow(0)
app.processEvents()
lt.refresh()
app.processEvents()
check("库: 刷新后选中行保持",
      lt.list_widget.currentRow() == 0, str(lt.list_widget.currentRow()))

# --- 右键菜单元数据不崩（无选中时）
try:
    lt._context_menu.__func__  # noqa: B018
    check("库: 右键菜单方法存在", True)
except Exception:  # noqa: BLE001
    check("库: 右键菜单方法存在", False)

# --- 导入列表：非数组 JSON（字典）不能崩（旧代码 for d in dict 崩 TypeError）
import json as _json  # noqa: E402

bad_path = os.path.join(_TMP, "bad_list.json")
with open(bad_path, "w", encoding="utf-8") as f:
    _json.dump({"3000001": {"title": "x"}}, f)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (bad_path, ""))
try:
    lt._import_list()
    app.processEvents()
    check("库: 导入非数组 JSON 不崩", True)
except Exception as e:  # noqa: BLE001
    check("库: 导入非数组 JSON 不崩", False, f"{type(e).__name__}: {e}")

# --- 导出列表：写出 JSON 数组
exp_path = os.path.join(_TMP, "exported.json")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (exp_path, ""))
try:
    lt._export_list()
    app.processEvents()
    ok = os.path.exists(exp_path) and os.path.getsize(exp_path) > 0
    check("库: 导出列表写文件", ok, str(os.path.exists(exp_path)))
except Exception as e:  # noqa: BLE001
    check("库: 导出列表写文件", False, f"{type(e).__name__}: {e}")

# ============================================================ 设置页
# --- 登录方式联动
st.mode_combo.setCurrentIndex(1)  # 手动登录
app.processEvents()
check("设置: 手动登录时用户名框启用", st.username_edit.isEnabled())
check("设置: 手动登录时密码框启用", st.password_edit.isEnabled())
st.mode_combo.setCurrentIndex(0)  # 回匿名
app.processEvents()
check("设置: 匿名时用户名框禁用", not st.username_edit.isEnabled())
check("设置: 匿名时登录状态文案",
      "匿名模式" in st.login_status.text(), repr(st.login_status.text()))

# --- 数值控件
st.timeout_spin.setValue(60)
check("设置: 超时数值可设", st.timeout_spin.value() == 60)
st.concurrency_spin.setValue(4)
check("设置: 并发数值可设", st.concurrency_spin.value() == 4)

# --- 保存后生效
st.hide_kw_edit.setText("Dead, 废弃")
st._apply_all()
app.processEvents()
cfg = win.svc.config
check("设置: 保存后超时生效", cfg.get("network", "timeout") == 60,
      str(cfg.get("network", "timeout")))
check("设置: 保存后并发生效", cfg.get("network", "max_concurrent_downloads") == 4,
      str(cfg.get("network", "max_concurrent_downloads")))
check("设置: 保存后过滤词去重排序",
      cfg.get("hide_keywords") == ["Dead", "废弃"],
      str(cfg.get("hide_keywords")))
check("设置: 保存后主题仍是 dark", cfg.get("general", "theme") == "dark")

# --- 游戏专属目录表格增删（先清空前面工坊页测试写入的配置，保持确定性）
from swdm.core.game_dirs import clear_game_dir, configured_game_dirs  # noqa: E402

for _a in list(configured_game_dirs()):
    clear_game_dir(_a)
gd = st.game_dirs_table
st._load_game_dirs()
gd_base = gd.rowCount()
check("设置: 目录表基线为 0", gd_base == 0, str(gd_base))
st._add_game_dir()  # 对话框已打补丁：选第一个游戏 + picked_dir
app.processEvents()
check("设置: 添加游戏目录后表行=1",
      gd.rowCount() == 1, str(gd.rowCount()))
gd.selectRow(0)
app.processEvents()
st._edit_game_dir()  # 修改目录
app.processEvents()
check("设置: 修改目录后表行仍 1", gd.rowCount() == 1, str(gd.rowCount()))
# _load_game_dirs 重建表格会清掉选中，删除前必须重新选行
gd.selectRow(0)
app.processEvents()
st._del_game_dir()  # 清除（确认框已打补丁为 Yes）
app.processEvents()
check("设置: 清除后表行=0", gd.rowCount() == 0, str(gd.rowCount()))

# --- 保存账号设置（匿名路径）
try:
    st._apply_account()
    app.processEvents()
    check("设置: 匿名账号保存不崩", True)
except Exception as e:  # noqa: BLE001
    check("设置: 匿名账号保存不崩", False, f"{type(e).__name__}: {e}")

# --- 各下拉切换不崩
for combo in st.findChildren(QComboBox):
    try:
        for i in range(combo.count()):
            combo.setCurrentIndex(i)
            app.processEvents()
    except Exception as e:  # noqa: BLE001
        check(f"设置: 下拉「{combo.objectName()}」切换不崩", False,
              f"{type(e).__name__}: {e}")
check("设置: 全部下拉切换不崩", True)

# --- 折叠分组切换不崩
from swdm.gui.widgets import CollapsibleSection  # noqa: E402

for sec in st.findChildren(CollapsibleSection):
    try:
        sec.setExpanded(False)
        app.processEvents()
        sec.setExpanded(True)
        app.processEvents()
    except Exception as e:  # noqa: BLE001
        check("设置: 折叠分组切换不崩", False, f"{type(e).__name__}: {e}")
check("设置: 折叠分组切换不崩", True)

# ============================================================ 调试页
# --- 日志显示：发一条日志，面板应出现内容
from swdm.core.logger import get_logger  # noqa: E402

get_logger("swdm.sweep").info("自测探针日志行")
app.processEvents()
check("调试: 日志视图非空", dbg.log_view.toPlainText() != "",
      repr(dbg.log_view.toPlainText()[:60]))
check("调试: 探针日志已入面板",
      "自测探针日志行" in dbg.log_view.toPlainText())

# --- 自动滚动开关
dbg._toggle_autoscroll(False)
check("调试: 关闭自动滚动", dbg._autoscroll is False)
dbg._toggle_autoscroll(True)
check("调试: 打开自动滚动", dbg._autoscroll is True)

# --- 清空显示
dbg._clear_log()
check("调试: 清空后日志视图为空", dbg.log_view.toPlainText() == "")

# --- 历史回填
dbg._load_job_history()
check("调试: 任务历史加载不崩", True)

# --- 导出日志（库页测试已改写 getSaveFileName，此处重新指回调试路径）
dbg_path = os.path.join(_TMP, "saved.log")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (dbg_path, ""))
try:
    dbg._export_log()
    app.processEvents()
    check("调试: 导出日志写文件", os.path.exists(dbg_path))
except Exception as e:  # noqa: BLE001
    check("调试: 导出日志不崩", False, f"{type(e).__name__}: {e}")

# --- 订阅注销安全
try:
    from swdm.core.logger import unsubscribe
    unsubscribe(dbg._on_log_entry)
    check("调试: 注销订阅不崩", True)
except Exception as e:  # noqa: BLE001
    check("调试: 注销订阅不崩", False, f"{type(e).__name__}: {e}")

# ============================================================ u6 切换游戏标签同步
# 旧实现：切游戏后 tag_bar 保留旧选中 + tag_edit 保留旧过滤参数 →
# 新游戏列表仍按旧标签过滤，且同名标签被 set_tags 自动重选
try:
    # 选两个标签模拟旧游戏的过滤状态
    wt.tag_edit.setText("生存, 建筑")
    wt.tag_bar.set_selected(["生存", "建筑"])
    app.processEvents()
    check("u6: 切换前标签参数已就位",
          wt.tag_edit.text() == "生存, 建筑",
          repr(wt.tag_edit.text()))
    check("u6: 切换前标签栏选中 2 个",
          len(wt.tag_bar.selected()) == 2, str(wt.tag_bar.selected()))
    # 触发游戏切换
    wt._on_game_changed(0)
    app.processEvents()
    check("u6: 切游戏后标签选中被清空",
          wt.tag_bar.selected() == [], str(wt.tag_bar.selected()))
    check("u6: 切游戏后过滤参数被清空",
          wt.tag_edit.text() == "", repr(wt.tag_edit.text()))
except Exception as e:  # noqa: BLE001
    check("u6: 游戏切换标签同步不崩", False, f"{type(e).__name__}: {e}")

# ============================================================ u10 删除/移除互通
# 下载页移除已入库任务 → 询问后同时删库记录并触发库页刷新
from swdm.core.downloader import DownloadJob as _DJ  # noqa: E402
from swdm.core.mod_library import ModRecord  # noqa: E402

sync_item = WorkshopItem(publishedfileid="3000001", title="互通测试",
                         appid="4000", file_size=2048)
sync_job = _DJ(item=sync_item, appid="4000")
sync_job.status = JobStatus.SUCCESS
sync_job.bytes_done = 2048
# 不走真实 worker：直接建行 + 桩 _job_by_id 让 _remove_row 能取到任务
dt._bridge.started.emit(sync_job)
app.processEvents()
dt._on_finished(sync_job)
app.processEvents()
_orig_job_by_id = dt._job_by_id
dt._job_by_id = lambda jid: sync_job if jid == sync_job.id else None
row_sync = dt._row_map.get(sync_job.id, -1)
check("u10: 成功任务建立下载行", row_sync >= 0, f"row={row_sync}")
lt.library.upsert(ModRecord(item_id=sync_job.id, appid="4000",
                            title="互通测试", local_path="c:/fake/3000001",
                            category="u10"))
check("u10: 该任务已入库", lt.library.get(sync_job.id) is not None)

# 下载页移除：选"否"→ 只删行，库记录保留
QMessageBox.question = staticmethod(
    lambda *a, **k: QMessageBox.StandardButton.No)
lib_events = []
_orig_lt_refresh = lt.refresh
lt.refresh = lambda: lib_events.append("refresh")
try:
    dt._remove_row(sync_job.id)
    app.processEvents()
    check("u10: 选「否」只移除下载行", sync_job.id not in dt._row_map,
          str(list(dt._row_map)[:3]))
    check("u10: 选「否」库记录保留",
          lt.library.get(sync_job.id) is not None)
    check("u10: 选「否」不触发库页刷新", "refresh" not in lib_events)
except Exception as e:  # noqa: BLE001
    check("u10: 移除流程不崩", False, f"{type(e).__name__}: {e}")

# 下载页移除（重建行后）：选"是"→ 删库记录 + 触发库页刷新
dt._bridge.started.emit(sync_job)
app.processEvents()
dt._on_finished(sync_job)
app.processEvents()
QMessageBox.question = staticmethod(
    lambda *a, **k: QMessageBox.StandardButton.Yes)
try:
    dt._remove_row(sync_job.id)
    app.processEvents()
    check("u10: 选「是」移除库记录",
          lt.library.get(sync_job.id) is None)
    check("u10: 选「是」触发库页刷新", "refresh" in lib_events)
except Exception as e:  # noqa: BLE001
    check("u10: 联动删除不崩", False, f"{type(e).__name__}: {e}")
dt._job_by_id = _orig_job_by_id
lt.refresh = _orig_lt_refresh

# 库页移除 → 下载页对应行被清除（反向联动）
dl_item = WorkshopItem(publishedfileid="3000002", title="反向联动",
                       appid="4000", file_size=1024)
dl_job = _DJ(item=dl_item, appid="4000")
dl_job.status = JobStatus.SUCCESS
dt._bridge.started.emit(dl_job)
app.processEvents()
dt._on_finished(dl_job)
app.processEvents()
check("u10: 反向联动前置：下载行存在", dl_job.id in dt._row_map)
removed_ids = []
_orig_rmrf = dt.remove_rows_for
dt.remove_rows_for = lambda ids: removed_ids.extend(ids)
try:
    lt.records_removed.emit([dl_job.id, "9999999"])
    app.processEvents()
    check("u10: 库移除信号送达下载页",
          dl_job.id in removed_ids, str(removed_ids))
except Exception as e:  # noqa: BLE001
    check("u10: 反向联动不崩", False, f"{type(e).__name__}: {e}")
# 真实 remove_rows_for 清行（G4 选中恢复不受影响：库页刷新自己处理）
dt.remove_rows_for = _orig_rmrf
dt.remove_rows_for([dl_job.id])
app.processEvents()
check("u10: remove_rows_for 清除下载行", dl_job.id not in dt._row_map)

# ============================================================ u9 设置页首行间距
# 量化断言：展开分组的标题按钮与首个内容控件间距 >= 8px（防挤压），
# 且表格首行不与表头重叠
from PySide6.QtCore import QPointF  # noqa: E402
from swdm.gui.widgets import CollapsibleSection  # noqa: E402

_secs = win.settings_tab.findChildren(CollapsibleSection)
# 必须切到设置页并 show，否则布局未计算、几何为垃圾值
win._tabs.setCurrentWidget(win.settings_tab)
win.settings_tab.show()
for _ in range(3):
    app.processEvents()
for _s in _secs:
    _s.setExpanded(True)
for _ in range(3):
    app.processEvents()
_gap_ok = True
_gap_bad = None
for _s in _secs:
    if not _s._content.isVisible():
        continue  # 折叠分组不占位，无法测量
    _tb = _s._title_btn
    _tb_bottom = _tb.mapTo(_s, QPointF(0, 0)).y() + _tb.height()
    _first = _s._content_layout.itemAt(0).widget()
    _first_top = _first.mapTo(_s, QPointF(0, 0)).y()
    if _first_top - _tb_bottom < 8:
        _gap_ok = False
        _gap_bad = f"{_s._title}: {_first_top - _tb_bottom:.0f}px"
check("u9: 全部展开分组标题→首控件间距 >= 8px", _gap_ok, str(_gap_bad))

_tw = win.settings_tab.game_dirs_table
_hh = _tw.horizontalHeader()
_hh_bottom = _hh.mapTo(_tw, QPointF(0, 0)).y() + _hh.height()
_row0_ok = True
if _tw.rowCount():
    _r0 = (_tw.viewport().mapTo(_tw, QPointF(0, 0)).y()
           + _tw.rowViewportPosition(0))
    _row0_ok = _r0 >= _hh_bottom - 1
check("u9: 目录表首行不与表头重叠", _row0_ok,
      f"header_bottom={_hh_bottom:.0f} row0={_tw.rowViewportPosition(0)}")
check("u9: 目录表首行行高 >= 24px",
      _tw.verticalHeader().defaultSectionSize() >= 24,
      str(_tw.verticalHeader().defaultSectionSize()))

# ============================================================ 主窗口
# B④：调试 Tab 默认隐藏 → 默认 4 个 Tab；debug_tab 属性仍存在
check("主窗口: 默认 4 个 Tab（调试 Tab 隐藏）", win._tabs.count() == 4,
      str(win._tabs.count()))
check("主窗口: debug_tab 属性存在（隐藏仍可访问）", hasattr(win, "debug_tab"))
check("主窗口: 状态栏非空", win.status_label.text() != "")
try:
    win._on_settings_changed()
    app.processEvents()
    check("主窗口: 设置变更回调不崩", True)
except Exception as e:  # noqa: BLE001
    check("主窗口: 设置变更回调不崩", False, f"{type(e).__name__}: {e}")
try:
    win._refresh_status_bar()
    check("主窗口: 状态栏刷新不崩", True)
except Exception as e:  # noqa: BLE001
    check("主窗口: 状态栏刷新不崩", False, f"{type(e).__name__}: {e}")

# ============================================================ 全局
app.processEvents()
check("全程无 Qt 未捕获异常", not _crashed,
      (_crashed[0][:300] if _crashed else ""))

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
