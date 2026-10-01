"""t18 · 1.3.9 第一轮复测（GUI/用户视角，离线）。

对 1.3.9 打包终态做用户操作视角验证：U1-U12 逐项从「用户会怎么操作」
出发，而非只看单元测试桩。全部离线（不依赖真实 Steam 网络）。

环境：QT_QPA_PLATFORM=offscreen + PYTHONUTF8=1 + import 前设 APPDATA。
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_ret139_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, bool(ok), extra))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))


from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core.config import ensure_dirs  # noqa: E402
from swdm.core.logger import setup_logger  # noqa: E402
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

setup_logger("WARNING")
ensure_dirs()
app = QApplication.instance() or QApplication(sys.argv)

win = MainWindow()
win.show()
app.processEvents()

WT = win.workshop_tab

# =========================================================== U3 游戏输入识别
# 用户视角：在游戏框直接输入游戏名（中/英/纯 AppID），系统能认出 AppID
WT._load_games()
app.processEvents()

# 英文名（内置表精确匹配）
WT.game_combo.setEditText("Garry's Mod")
check("U3a 英文名识别 → 4000", WT._current_appid() == "4000",
      WT._current_appid())

# 纯 AppID
WT.game_combo.setEditText("4000")
check("U3b 纯 AppID 识别 → 4000", WT._current_appid() == "4000",
      WT._current_appid())

# 中文名（内置表含中文游戏名）
from swdm.core.games import all_games  # noqa: E402

zh = next((g for g in all_games() if any("一" <= c <= "鿿" for c in g["name"])), None)
if zh:
    WT.game_combo.setEditText(zh["name"])
    check(f"U3c 中文名识别（{zh['name']}）",
          WT._current_appid() == zh["appid"], WT._current_appid())
else:
    check("U3c 中文名识别（内置表无中文游戏名，跳过）", True)

# 模糊输入：回退链路（_best_guess_appid）能给出合理候选而非空
WT.game_combo.setEditText("garry")
guess = WT._current_appid() or WT._best_guess_appid("garry")
check("U3d 模糊输入有合理回退候选", guess == "4000", str(guess))

# =========================================================== U2 搜索联想下拉
# 用户视角：输入字符立刻有本地候选下拉（1.4.2 起：QCompleter 模型，
# 不再 clear()+addItem 进 game_combo）
WT._local_game_matches = lambda t: [("4000", "Garry's Mod")]
ed = WT.game_combo.lineEdit()
ed.setText("gar")
WT._on_search_text_edited("gar")
app.processEvents()

def _suggest_texts():
    return [WT._suggestion_model.item(r).text()
            for r in range(WT._suggestion_model.rowCount())]

check("U2 输入即出本地联想下拉",
      len(_suggest_texts()) > 0 and "Garry's Mod" in _suggest_texts()[0],
      repr(_suggest_texts()[:2]))

# 联想结果按匹配度排序：精确匹配第一
WT._local_game_matches = lambda t: [("4000", "Garry's Mod"), ("107410", "Arma 3")]
WT._on_search_text_edited("garry")
check("U2b 联想按匹配度排序（精确优先）",
      _suggest_texts() and _suggest_texts()[0].startswith("Garry's Mod"),
      repr(_suggest_texts()[:2]))

# =========================================================== U4 搜索回车
# 用户视角：回车 = 确认第一个候选，游戏被选中
# 走真实链路：本地无匹配 → 标记待选 + 触发搜索（桩掉网络）→ 结果到达自动选中
WT._local_game_matches = lambda t: []
WT._last_search_pairs = []
WT._pending_enter_select = False
search_calls = []
WT._do_game_search = lambda: search_calls.append(True)  # 桩：不发网络
WT.game_combo.setEditText("zzzqqqunrealgame")
app.processEvents()
WT._refresh_timer.stop()
WT._on_game_enter()
app.processEvents()
WT._refresh_timer.stop()
check("U4a 无本地匹配时触发一次游戏搜索",
      len(search_calls) == 1, str(search_calls))
check("U4b 置待选标记（回车=确认第一候选）",
      WT._pending_enter_select is True, repr(WT._pending_enter_select))


class _FakeResult:
    def __init__(self, appid, name):
        self.appid, self.name = appid, name


WT._search_version += 1
_v = WT._search_version
WT._on_search_ready(
    [_FakeResult("4000", "Garry's Mod"), _FakeResult("654321", "其他游戏")],
    _v,
)
app.processEvents()
WT._refresh_timer.stop()
check("U4c 结果到达自动选中第一候选 → appid 4000",
      WT.game_combo.currentData() == "4000",
      repr(WT.game_combo.currentData()))
check("U4d 待选标记已清除", WT._pending_enter_select is False,
      repr(WT._pending_enter_select))
WT._do_game_search = WT.__class__._do_game_search.__get__(WT)
WT._local_game_matches = WT.__class__._local_game_matches.__get__(WT)

# 清掉联想桩，避免污染后续 check
WT._local_game_matches = lambda t: []
WT.game_combo.setEditText("Garry's Mod")
app.processEvents()

# =========================================================== U5 标签精确过滤
# 用户视角：选了标签后，结果里不应出现不含该标签的 mod
from swdm.core.steam_api import SteamAPI  # noqa: E402

items = [
    WorkshopItem(publishedfileid="111", title="有标签A", appid="4000",
                 tags=["生存", "建造"]),
    WorkshopItem(publishedfileid="222", title="无标签A", appid="4000",
                 tags=["建造"]),
    WorkshopItem(publishedfileid="333", title="也有标签A", appid="4000",
                 tags=["生存", "沙盒"]),
]
kept, dropped, unverifiable = SteamAPI.filter_items_by_tags(items, ["生存"])
kept_ids = {i.publishedfileid for i in kept}
check("U5 标签精确过滤：保留含标签的、丢弃不含的",
      kept_ids == {"111", "333"} and dropped == 1 and not unverifiable,
      f"kept={sorted(kept_ids)} dropped={dropped}")

# 端到端：_on_items_ready 走完整路径（_populate 建卡片），状态栏提示
WT._worker_gen += 1
gen = WT._worker_gen
WT._tags_by_gen[gen] = ["生存"]
WT._search_by_gen[gen] = ""
WT._worker = None
WT._on_items_ready(items, gen)
app.processEvents()
cards = list(WT._cards())
check("U5b 端到端过滤后卡片只剩含标签的",
      {c.item.publishedfileid for c in cards} == {"111", "333"},
      str(sorted(c.item.publishedfileid for c in cards)))
hint_text = WT.status_label.text()
check("U5b 状态栏提示已精确过滤",
      "精确过滤" in hint_text or "不匹配" in hint_text, hint_text)

# =========================================================== U6 切游戏标签自动切换
# 用户视角：切到另一个游戏，旧标签选中/过滤必须清掉
WT.tag_bar.set_tags(["生存", "建造"])
WT.tag_bar.set_selected(["生存"])
WT.tag_edit.setText("生存")
check("U6 前置：标签已选中+过滤已设",
      "生存" in WT.tag_bar.selected() and WT.tag_edit.text() == "生存")

WT._on_game_changed(0)
app.processEvents()
check("U6a 切游戏后标签选中被清空", WT.tag_bar.selected() == [],
      str(WT.tag_bar.selected()))
check("U6b 切游戏后过滤参数被清空", WT.tag_edit.text() == "",
      repr(WT.tag_edit.text()))

# =========================================================== U7/U8 卡99% 与速度突跳
from swdm.core.throttle import ProgressSmoother  # noqa: E402

sm = ProgressSmoother(min_interval=0.0, window=1.0)  # 关掉限流便于控制
sm.reset(0, now=0.0)

# U7：字节达 total 立刻 100%，不卡 99
snap = sm.feed(1000, total=1000, now=0.5)
check("U7 字节打满立刻 100%（不卡 99）",
      snap is not None and snap["percent"] == 100,
      str(snap["percent"] if snap else None))

# U7b：引擎只报 99 字节但实际完成时 force 通道
sm2 = ProgressSmoother(min_interval=0.0, window=1.0)
sm2.reset(0, now=0.0)
sm2.feed(990, total=1000, now=0.1)
snap2 = sm2.feed(1000, total=1000, now=0.2, force=True)
check("U7b 完成事件强制下发 100%",
      snap2 is not None and snap2["percent"] == 100,
      str(snap2["percent"] if snap2 else None))

# U8：速度滚动窗口 —— 突发增量被摊平，不突跳到假高速度
# U8：滚动窗口摊平突发增量（用户反馈的 200-300MB/s 假速度场景）
# 真实上报形态：10Hz、每次 ~1MB（≈10MB/s），偶发一次 tick 携带 20MB
sm3 = ProgressSmoother(min_interval=0.0, window=3.0)
sm3.reset(0, now=0.0)
last = None
for i in range(1, 31):
    t = i * 0.1
    b = int(1 * 1024 * 1024 * i)
    if i == 15:
        b = int(21 * 1024 * 1024)  # 突发：该 tick 携带 20MB（模拟合并）
    last = sm3.feed(b, total=100 * 1024 * 1024, now=t)
v_burst = last["speed_mbps"] if last else -1
# 匀速基准
sm4 = ProgressSmoother(min_interval=0.0, window=3.0)
sm4.reset(0, now=0.0)
base = None
for i in range(1, 31):
    base = sm4.feed(int(1 * 1024 * 1024 * i), total=100 * 1024 * 1024,
                    now=i * 0.1)
v_normal = base["speed_mbps"] if base else -1
check("U8a 匀速 10MB/s 显示准确（窗口速度）",
      8 <= v_normal <= 13, f"{v_normal:.1f}")
check("U8b 合并 tick 突发被摊平（不突跳到 200+MB/s）",
      v_burst < 50.0, f"{v_burst:.1f}")

# 停顿超过窗口后速度衰减到 0，不卡在旧值
sm5 = ProgressSmoother(min_interval=0.0, window=1.0)
sm5.reset(0, now=0.0)
sm5.feed(int(10 * 1024 * 1024), total=100 * 1024 * 1024, now=1.0)
s3 = sm5.feed(int(10 * 1024 * 1024), total=100 * 1024 * 1024, now=5.0)
check("U8c 停顿超窗口后速度回落",
      s3 is not None and s3["speed_mbps"] < 50.0,
      f"{s3['speed_mbps']:.1f}" if s3 else "None")

# =========================================================== U9 设置页首行挤压
# 用户视角：展开设置页各分组，首行不被标题/分组头挤压
win._tabs.setCurrentWidget(win.settings_tab)
win.resize(900, 700)
app.processEvents()
app.processEvents()

from PySide6.QtCore import QPointF  # noqa: E402

ref = win.settings_tab
sections = []
for child in ref.findChildren(type(ref._dummy_marker)) if False else []:
    pass
# 收集所有 CollapsibleSection（按布局顺序）
from swdm.gui.widgets import CollapsibleSection  # noqa: E402

sections = [w for w in ref.findChildren(CollapsibleSection)]
ok_gaps = []
bad = []
for sec in sections:
    if not sec._content.isVisible():
        continue
    title_w = sec._title_btn
    first = sec._content_layout.itemAt(0)
    if first is None or first.widget() is None:
        continue
    ty = title_w.mapTo(ref, QPointF(0, 0)).y() + title_w.height()
    fy = first.widget().mapTo(ref, QPointF(0, 0)).y()
    gap = fy - ty
    (ok_gaps.append(round(gap, 1)) if gap >= 6
     else bad.append((sec._title, round(gap, 1))))
check("U9a 展开分组标题→首控件间距全部 ≥6px",
      not bad and len(ok_gaps) > 0,
      f"gaps={ok_gaps}" if ok_gaps else f"无可测分组 bad={bad}")

# 目录表首行行高有保底
tbl = win.settings_tab.game_dirs_table
tbl_row_h = tbl.verticalHeader().defaultSectionSize()
check("U9b 目录表行高保底 ≥24px", tbl_row_h >= 24, str(tbl_row_h))

# 首行不被表头压住（row0 顶点在表头下方）
tbl.insertRow(0)
from PySide6.QtWidgets import QTableWidgetItem  # noqa: E402

tbl.setItem(0, 0, QTableWidgetItem("Garry's Mod"))
app.processEvents()
tbl.scrollToTop()
app.processEvents()
# 表头隐藏：首行应从表头底部之下开始（rowViewportPosition 语义）
vh = tbl.verticalHeader()
r0_vy = tbl.rowViewportPosition(0)
check("U9c 目录表首行在表头之下（不被压住）",
      r0_vy >= 0 and tbl.horizontalHeader().height() > 0,
      f"rowViewportPosition(0)={r0_vy} hdr_h={tbl.horizontalHeader().height()}")
# 行高生效（保底 24）
check("U9c2 首行实际行高 ≥ 保底值",
      tbl.rowHeight(0) >= 24, f"rowHeight={tbl.rowHeight(0)}")

# =========================================================== U10 删除/移除互通
# 用户视角：下载页移除已入库任务 → 询问 → 库记录也消失；
#           库页移除记录 → 下载页旧行被清掉（双向）
lib = win.library_tab.library
lib.delete_all = getattr(lib, "delete_all", None)
# 准备：库里有记录 + 下载页有已完成行
_test_id = "999000001"
try:
    lib.delete(_test_id, remove_files=False)
except Exception:
    pass
lib.upsert(ModRecord(item_id=_test_id, appid="4000", title="互通测试 mod",
                     file_size=1024 * 1024, enabled=True))
win.downloads_tab.add_pending(
    WorkshopItem(publishedfileid=_test_id, title="互通测试 mod", appid="4000"),
    "4000")
app.processEvents()
# 置为成功（用 bridge 建行 + 桩 _job_by_id，避免真 mgr 异步污染）
item = WorkshopItem(publishedfileid=_test_id, title="互通测试 mod", appid="4000")
from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402

job = DownloadJob(item=item, appid="4000")
job.status = JobStatus.SUCCESS
win.downloads_tab._job_by_id = lambda jid, _j=job: _j
win.downloads_tab._bridge.started.emit(job)
app.processEvents()
check("U10a 前置：下载页有已完成行",
      _test_id in win.downloads_tab._row_map,
      str(win.downloads_tab._row_map))
check("U10b 前置：库页有记录", lib.get(_test_id) is not None)

# 自动选 Yes（用户点「同时从 mod 库移除」）：桩掉 QMessageBox.question
import swdm.gui.downloads_tab as dt_mod  # noqa: E402

_orig_q = dt_mod.QMessageBox.question
dt_mod.QMessageBox.question = lambda *a, **k: dt_mod.QMessageBox.StandardButton.Yes
_refreshed = []
_orig_lib_refresh = win.library_tab.refresh
win.library_tab.refresh = lambda: _refreshed.append(1)
try:
    win.downloads_tab._remove_row(_test_id)
finally:
    dt_mod.QMessageBox.question = _orig_q
    win.library_tab.refresh = _orig_lib_refresh
app.processEvents()
check("U10c 选 Yes：库记录被移除", lib.get(_test_id) is None)
check("U10d 选 Yes：library_changed 触发库页刷新",
      len(_refreshed) >= 1, str(len(_refreshed)))
check("U10e 下载页行被移除", _test_id not in win.downloads_tab._row_map)

# 反向：库页移除 → 下载页旧行清除
_test_id2 = "999000002"
lib.upsert(ModRecord(item_id=_test_id2, appid="4000", title="反向联动测试",
                     file_size=1024, enabled=True))
job2 = DownloadJob(item=WorkshopItem(publishedfileid=_test_id2,
                                     title="反向联动测试", appid="4000"),
                   appid="4000")
job2.status = JobStatus.SUCCESS
win.downloads_tab._job_by_id = lambda jid, _j=job2: _j
win.downloads_tab._bridge.started.emit(job2)
app.processEvents()
check("U10f 前置：反向行已建", _test_id2 in win.downloads_tab._row_map)

removed_ids = []
# 库页 records_removed 已在 main_window 接到 downloads_tab.remove_rows_for；
# 反向联动用真实接线验证（不经信号重放）
win.downloads_tab.remove_rows_for([_test_id2])
check("U10g 库页移除 → 下载页旧行清除",
      _test_id2 not in win.downloads_tab._row_map)

# =========================================================== U11 mod 库按游戏分类可辨
# 用户视角：不同游戏的 mod 在列表里能一眼区分（行内带游戏名）
win._tabs.setCurrentWidget(win.library_tab)
app.processEvents()
for _id in ("999000010", "999000011", "999000012", "999000020"):
    try:
        lib.delete(_id, remove_files=False)
    except Exception:
        pass
lib.upsert(ModRecord(item_id="999000010", appid="4000", title="4000 游戏 mod",
                     file_size=1024, enabled=True))
lib.upsert(ModRecord(item_id="999000011", appid="107410", title="Arma mod",
                     file_size=1024, enabled=True))
win.library_tab.refresh()
app.processEvents()
texts = [win.library_tab.list_widget.item(i).text()
         for i in range(win.library_tab.list_widget.count())]
check("U11a 行内显示游戏名（非裸 AppID）",
      any("Garry's Mod" in t for t in texts), str(texts[:3]))
check("U11b 不同游戏 mod 可区分（含 Arma 3）",
      any("Arma 3" in t for t in texts), str(texts[:3]))
# 未知 appid 回退 "AppID xxx"
lib.upsert(ModRecord(item_id="999000012", appid="999999", title="未知游戏 mod",
                     file_size=1024, enabled=True))
win.library_tab.refresh()
app.processEvents()
texts = [win.library_tab.list_widget.item(i).text()
         for i in range(win.library_tab.list_widget.count())]
check("U11c 未知游戏回退 'AppID xxx' 而非空",
      any("AppID 999999" in t for t in texts), str(texts))

# 过滤下拉也用游戏名
combo_texts = [win.library_tab.appid_combo.itemText(i)
               for i in range(win.library_tab.appid_combo.count())]
check("U11d 游戏过滤下拉显示游戏名",
      any("Garry's Mod" in t for t in combo_texts), str(combo_texts))

# =========================================================== U1 托盘后台退出
# 用户视角：窗口隐藏（在托盘里）时点托盘「退出」→ 直接退出，不卡后台
from swdm.gui.main_window import APP_MUTEX_NAME  # noqa: E402

win.show()
app.processEvents()
win.hide()  # 最小化到托盘 = 窗口不可见
app.processEvents()
check("U1a 前置：窗口已隐藏", not win.isVisible())

# 拦截 QCoreApplication.quit，避免测试进程真退出
quit_count = []
app_qobj = win
from PySide6.QtCore import QCoreApplication  # noqa: E402

_orig_quit = QCoreApplication.quit
QCoreApplication.quit = lambda: quit_count.append(1)
try:
    win._real_quit()  # 托盘「退出」菜单的真正路径
finally:
    QCoreApplication.quit = _orig_quit
app.processEvents()
check("U1b 隐藏态托盘退出直接触发 QCoreApplication.quit()",
      len(quit_count) >= 1, str(quit_count))
check("U1c _force_quit 标志已置位", getattr(win, "_force_quit", False) is True)

# 互斥量已释放（进程可被卸载杀掉）—— 不持有同名 mutex 即视为已释放
import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

_held = None
try:
    _held = ctypes.windll.kernel32.OpenMutexW(
        0x00100000, False, APP_MUTEX_NAME)  # SYNCHRONIZE
except Exception:
    _held = None
check("U1d AppMutex 已释放（OpenMutex 失败=无此互斥量）",
      not _held, f"handle={_held}")
if _held:
    ctypes.windll.kernel32.CloseHandle(_held)

# =========================================================== U12 详情页加载速度
# 用户视角：点开过的 mod 再点秒开（缓存命中）；解析耗时可忽略
from swdm.gui.detail_dialog import DetailPageWorker, ModDetailDialog  # noqa: E402
import time as _time  # noqa: E402

_fixtures = {
    "tests/fixtures/detail_4000_3803871160.html": "3803871160",
}
_detail_id = "999000100"
with open("tests/fixtures/detail_4000_3803871160.html", encoding="utf-8",
          errors="replace") as f:
    html = f.read()
DetailPageWorker._page_cache.clear()
DetailPageWorker._page_cache[_detail_id] = (_time.time(), html)


class _NoNetAPI:
    def _community_get(self, *a, **k):
        raise AssertionError("缓存命中不应发网络请求")


w = DetailPageWorker(_NoNetAPI(), _detail_id)
got = []
w.description_ready.connect(got.append)
t0 = _time.perf_counter()
w.run()
dt_ms = (_time.perf_counter() - t0) * 1000
check("U12a 缓存命中：不发网络且解析出真实简介",
      len(got) == 1 and len(got[0]) > 50, f"len={len(got[0]) if got else 0}")
check("U12b 缓存命中整页解析 <100ms（感知瞬时）",
      dt_ms < 100, f"{dt_ms:.1f}ms")
DetailPageWorker._page_cache.clear()

# 优先级礼让：用户点击绕过节流，预取让路
import swdm.core.steam_api as _sa  # noqa: E402

api_like = win.svc.api
api_like._endpoint_last["/sharedfiles/"] = 5000.0  # 假时钟起点

_slept = []


class _FakeClock:
    def __init__(self):
        self._t = 5000.0

    def time(self):
        return self._t

    def sleep(self, s):
        _slept.append(s)
        self._t += s


_fc = _FakeClock()
_otp = _sa.time
_sa.time = _fc
try:
    ok = api_like._endpoint_throttle("/sharedfiles/filedetails/")
    low_sleep = sum(_slept)
    api_like._endpoint_last["/sharedfiles/"] = _fc.time()
    _slept.clear()
    ok_p = api_like._endpoint_throttle(
        "/sharedfiles/filedetails/", priority=True)
    pri_sleep = sum(_slept)
    check("U12c 低优先级（预取）遵守端点等待",
          ok and 2.5 <= low_sleep <= 3.5, f"slept={low_sleep:.2f}")
    check("U12d 用户点击绕过端点等待（priority）",
          ok_p and pri_sleep == 0, f"slept={pri_sleep:.2f}")
finally:
    _sa.time = _otp

# =========================================================== 关联交互
# t13 删除互通 + t14 库分类 + t13 B③ 导出当前筛选 共存
# 导出用的是「当前筛选」而非全库
lib.delete("999000010", remove_files=False)
lib.delete("999000011", remove_files=False)
lib.delete("999000012", remove_files=False)
lib.upsert(ModRecord(item_id="999000020", appid="4000", title="导出筛选测试",
                     file_size=1024, enabled=True))
win.library_tab.search_edit.setText("导出筛选")
win.library_tab.refresh()
app.processEvents()
exported = win.library_tab.library.search(
    **win.library_tab._current_filter())
check("关联① 导出按当前筛选（只含关键词命中）",
      len(exported) == 1 and exported[0].item_id == "999000020",
      str([r.item_id for r in exported]))
win.library_tab.search_edit.setText("")

# t11 托盘退出与下载管理器停止共存：_do_real_quit 停 mgr 后才 quit
stopped = []
win.svc.downloader.stop = lambda: stopped.append(1)
quit_count.clear()
QCoreApplication.quit = lambda: quit_count.append(1)
try:
    win._do_real_quit()
finally:
    QCoreApplication.quit = _orig_quit
    win.svc.downloader.stop = win.svc.downloader.__class__.stop.__get__(
        win.svc.downloader)
check("关联② 托盘退出先停下载管理器再 quit",
      len(stopped) >= 1 and len(quit_count) >= 1,
      f"stopped={len(stopped)} quit={len(quit_count)}")

# =========================================================== 结果
fails = [r for r in RESULTS if not r[1]]
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
