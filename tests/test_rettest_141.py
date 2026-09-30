"""t44 · SWDM 1.4.1 GUI/用户视角第一轮复测（参照 1.4.0 t25 的 test_rettest_140.py）

复测对象：1.4.1 打包终态（installer\\Output\\SWDM-Setup-1.4.1.exe + 源树）。
全部网络出站打桩，offscreen 执行。

覆盖：
- P0 打包终态（exe/版本号双端/changelog/帮助菜单/MainWindow 标题）
- P5a B6 下载页空态（新装用户第一眼）
- P1 B1 详情页磁盘缓存（命中零网络/刷新 bypass/time_updated 双失效/回写/损坏容忍）
- P2 B2 翻页预取（满页调度/未满不调度/熔断期不调度）
- P3 B3 剪贴板自动入队（解析/去重/非工坊静默/开关生效）
- P8 关联交互（剪贴板入队 → 下载页空态切换为表格行）
- P4 B5 批量粘贴导入（多链接+ID+垃圾行/合集展开/去重）
- P5b B6 库页空态（空库/筛选无结果两态）
- P6 A2 QSS（进度条状态色/主题解析/跟随系统）
- P7 设置页新开关（剪贴板监听/详情缓存 TTL/主题三选项/清除缓存按钮）

托盘态剪贴板行为不在自动化范围（docs/clipboard_watch_notes.md 5 条人工清单）。
审计必检项（U3/A6/P0-4）专项验证见 tests/test_t44_retest_gui.py——A6 覆盖
真实线程路径 daemon worker → Signal(list) → _on_check_updates_done。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_ret141_")
os.environ["APPDATA"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, ".")

ok = True


def check(name: str, cond, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

# ====================================================== P0 打包终态
print("\n--- P0 打包终态 ---")

_exe = "installer\\Output\\SWDM-Setup-1.4.1.exe"
check("P0a 安装包存在", os.path.isfile(_exe))
check("P0b 安装包 >40MB", os.path.getsize(_exe) > 40 * 1024 * 1024,
      f"{os.path.getsize(_exe) / 1048576:.1f}MB")
check("P0c changelog_1.4.1.md 存在", os.path.isfile("docs\\changelog_1.4.1.md"))

with open("swdm\\core\\paths.py", encoding="utf-8") as f:
    _pv = [ln for ln in f if "APP_VERSION" in ln]
check("P0d paths.py APP_VERSION=1.4.1", any('APP_VERSION = "1.4.1"' in ln for ln in _pv))
with open("installer\\swdm.iss", encoding="utf-8") as f:
    _iv = [ln for ln in f if "SWDMVersion" in ln and "define" in ln]
check("P0e swdm.iss SWDMVersion=1.4.1", any("1.4.1" in ln for ln in _iv))

from swdm.gui.main_window import MainWindow  # noqa: E402
from swdm.core.paths import APP_VERSION  # noqa: E402

check("P0f 运行时 APP_VERSION=1.4.1", APP_VERSION == "1.4.1", APP_VERSION)
win = MainWindow()
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
check("P0g MainWindow 标题含 v1.4.1", "1.4.1" in win.windowTitle(), win.windowTitle())

_acts = win.menuBar().actions()
_help = [a for a in _acts if "帮助" in a.text()]
_help_texts = []
for _ha in _help:
    _hm = _ha.menu()
    if _hm is not None:
        for _sa in _hm.actions():
            _help_texts.append(_sa.text())
check("P0h 帮助>用户手册 菜单项存在（t43 接线）",
      any("用户手册" in t for t in _help_texts), str(_help_texts))
check("P0i 手册随包文件存在（dist）",
      os.path.isfile("build\\dist\\SWDM\\_internal\\manual\\SWDM-用户手册.html"))

# 弹窗打桩
_msgs = []
QMessageBox.information = lambda p, t, x, *a, **k: _msgs.append((t, x))
QMessageBox.question = lambda p, t, x, *a, **k: _msgs.append((t, x))
QMessageBox.warning = lambda p, t, x, *a, **k: _msgs.append((t, x))

wt = win.workshop_tab
dt = win.downloads_tab
lt = win.library_tab
st = win.settings_tab

# 下载链打桩：防止真实网络 + 加速派发（MainWindow 初始化已 start()）
from swdm.core.downloader import DownloadResult, DownloadStatus  # noqa: E402

win.svc.downloader._throttle_wait = lambda job: None
win.svc.downloader._run_channel_chain = (
    lambda job, install_dir, smoother: DownloadResult(
        item_id=job.id, appid=job.appid, status=DownloadStatus.FAILED,
        message="测试桩：快速失败",
    )
)

# 详情磁盘缓存打桩：DetailPageWorker / 设置页清除按钮都落到受控目录
import swdm.core.detail_cache as _dc_mod  # noqa: E402
from swdm.core.detail_cache import DetailDiskCache  # noqa: E402

_cache_dir = os.path.join(_TMP, "dcache")
_cache = DetailDiskCache(root_dir=_cache_dir, ttl_hours=24)
_orig_gdc = _dc_mod.get_detail_cache
_dc_mod.get_detail_cache = lambda: _cache

# ====================================================== P5a 下载页空态（B6）
print("\n--- P5a 下载页空态（新装第一眼） ---")

win._tabs.setCurrentWidget(dt)
app.processEvents()
check("P5a1 空队列时空态面板可见", not dt._empty_state.isHidden())
check("P5a2 空态含「前往工坊浏览」引导按钮",
      any("前往工坊浏览" in b.text() for b in dt._empty_state.findChildren(
          __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)))
check("P5a3 空态时表格隐藏", dt.table.isHidden())

# ====================================================== P1 B1 详情磁盘缓存
print("\n--- P1 B1 详情页磁盘缓存（GUI 集成） ---")

from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402

DetailPageWorker._page_cache.clear()


class _FakeAPI:
    def __init__(self):
        self.calls = 0

    def _community_get(self, path, params=None, **kw):
        self.calls += 1
        return "<html>detail page body</html>"


_fapi = _FakeAPI()

_cache.set("999", "<html>cached body</html>", 1000)
_fapi.calls = 0
DetailPageWorker(_fapi, "999", 1000).run()
check("P1a 磁盘缓存命中零网络（_community_get 未被调）", _fapi.calls == 0,
      f"calls={_fapi.calls}")

_fapi.calls = 0
DetailPageWorker(_fapi, "999", 1000, force_refresh=True).run()
check("P1b 手动刷新绕过缓存（bypass 命中网络）", _fapi.calls == 1, f"calls={_fapi.calls}")

DetailPageWorker._page_cache.clear()   # P1b 的抓取回写了内存缓存，清掉以测磁盘双失效
_fapi.calls = 0
DetailPageWorker(_fapi, "999", 2000).run()
check("P1c time_updated 前进后缓存失效（走网络）", _fapi.calls == 1, f"calls={_fapi.calls}")

DetailPageWorker._page_cache.clear()
_fapi2 = _FakeAPI()
DetailPageWorker(_fapi2, "888", 5000).run()
_hit, _html = _cache.get("888", 5000)
check("P1d 详情页回写磁盘缓存", _hit, f"hit={_hit}")

_p = _cache._path("777")
os.makedirs(os.path.dirname(_p), exist_ok=True)
with open(_p, "w", encoding="utf-8") as f:
    f.write("\x00\x01\x02 not json {{{")
_fapi.calls = 0
DetailPageWorker(_fapi, "777", 1000).run()
check("P1e 损坏缓存文件不崩且回退网络", _fapi.calls >= 1, f"calls={_fapi.calls}")

DetailPageWorker._page_cache.clear()
DetailPageWorker(_fapi, "666", 3000).run()
_fapi.calls = 0
DetailPageWorker(_fapi, "666", 3000).run()
check("P1f 内存缓存命中零网络", _fapi.calls == 0, f"calls={_fapi.calls}")
DetailPageWorker._page_cache.clear()

# ====================================================== P2 B2 翻页预取（调度）
print("\n--- P2 B2 翻页预取 ---")

from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.circuit import CircuitBreaker  # noqa: E402

_full = [WorkshopItem(publishedfileid=str(i), title=f"mod-{i}", appid="4000")
         for i in range(30)]

wt._worker_gen = 5
wt._page = 1
wt._items = _full
wt._nextpage_timer.stop()
wt._schedule_prefetch_next_page(5)
check("P2a 满页+代际当前 → 启动预取定时器", wt._nextpage_timer.isActive())

wt._nextpage_timer.stop()
wt._items = _full[:10]
wt._schedule_prefetch_next_page(5)
check("P2b 未满页不调度预取", not wt._nextpage_timer.isActive())

wt._items = _full
_wt_cb = CircuitBreaker()
_wt_cb.force_trip()
wt.svc.api._browse_breaker = _wt_cb
wt._schedule_prefetch_next_page(5)
check("P2c 熔断冷却期不调度预取", not wt._nextpage_timer.isActive())
_wt_cb.record_success()
wt._nextpage_timer.stop()

# ====================================================== P3 B3 剪贴板自动入队
print("\n--- P3 B3 剪贴板自动入队 ---")

_real_resolve = win.svc.api.resolve_any_url
_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id=123456"
_item = WorkshopItem(publishedfileid="123456", appid="4000", title="Clip Mod")

win.svc.api.resolve_any_url = (
    lambda text: ("4000", "123456") if "123456" in text else ("", "")
)
win.svc.api.get_file_details = lambda ids: {"123456": _item}
win._clipboard_text = lambda: _URL


def _total(snap):
    return sum(len(snap[k]) for k in ("queued", "active", "done"))


_n0 = _total(win.svc.downloader.snapshot())
win._on_clipboard_changed()
_n1 = _total(win.svc.downloader.snapshot())
check("P3a 工坊链接剪贴板 → 自动入队", _n1 == _n0 + 1, f"{_n0}->{_n1}")
check("P3b 状态栏提示入队", "已从剪贴板加入下载队列" in
      win.statusBar().currentMessage(), win.statusBar().currentMessage()[:40])

win._on_clipboard_changed()
_n2 = _total(win.svc.downloader.snapshot())
check("P3c 重复触发不二次入队", _n2 == _n1, f"{_n1}->{_n2}")

win._clipboard_text = lambda: "hello world 普通文本"
win._on_clipboard_changed()
check("P3d 非工坊文本静默跳过", _total(win.svc.downloader.snapshot()) == _n2)

win.svc.config.set("general", "clipboard_watch", False)
win._start_clipboard_watch()
check("P3e 配置关闭后剪贴板信号解绑", not win._clip_connected)
win.svc.config.set("general", "clipboard_watch", True)
win._start_clipboard_watch()
check("P3f 重开启后重新连接", win._clip_connected)

# ====================================================== P8 关联交互
print("\n--- P8 关联交互：剪贴板入队 → 下载页空态切换 ---")

# bridge 经 Qt 信号（QueuedConnection）分发：轮询事件循环直到行出现
_rows = 0
_t0 = time.time()
while time.time() - _t0 < 8.0 and dt.table.rowCount() < 1:
    app.processEvents()
    time.sleep(0.03)
_rows = dt.table.rowCount()
check("P8a 入队后下载页出现表格行", _rows >= 1, f"rows={_rows}")
check("P8b 空态面板切换为隐藏", dt._empty_state.isHidden())
check("P8c 表格切换为可见", not dt.table.isHidden())

# ====================================================== P4 B5 批量粘贴导入
print("\n--- P4 B5 批量粘贴导入 ---")

win.svc.api.resolve_any_url = _real_resolve


def _fake_details(ids):
    return {i: WorkshopItem(publishedfileid=i, appid="4000", title=f"T{i}") for i in ids}


win.svc.api.get_file_details = _fake_details
win.svc.api.get_collection_details = lambda cid: []   # 非合集 → 不展开
wt._current_appid = lambda: "4000"

def _all_ids():
    _s = win.svc.downloader.snapshot()
    return {j.item.publishedfileid
            for k in ("queued", "active", "done") for j in _s[k]}


_q0 = _all_ids()
_tokens = [
    "https://steamcommunity.com/sharedfiles/filedetails/?id=111",
    "222",
    "https://steamcommunity.com/sharedfiles/filedetails/?id=333",
    "这不是链接",
]
wt._import_tokens(_tokens)
_new = _all_ids() - _q0
check("P4a 多链接+ID 混合导入全部入队", _new == {"111", "222", "333"},
      f"new={sorted(_new)}")

# 对话框路径（B5 入口在「⋯ 更多」菜单）
_multi = "\n".join([
    "https://steamcommunity.com/sharedfiles/filedetails/?id=555",
    "https://steamcommunity.com/sharedfiles/filedetails/?id=555",  # 重复行
    "666",
])
QInputDialog.getMultiLineText = (
    lambda *a, **k: (_multi, True)
)
wt._import_url()
_new2 = _all_ids() - _q0 - _new
check("P4b 弹窗路径去重导入（555×2+666 → 2 个新）", _new2 == {"555", "666"},
      f"new={sorted(_new2)}")

# 无效输入提示
QInputDialog.getMultiLineText = lambda *a, **k: ("完全无法解析的文本", True)
_msgs.clear()
wt._import_url()
check("P4c 无效输入弹警告窗", any("未能从输入中解析出任何物品 ID" in m[1] for m in _msgs))

# ====================================================== P5b 库页空态（B6）
print("\n--- P5b 库页空态（空库/筛选无结果两态） ---")

win._tabs.setCurrentWidget(lt)
lt.refresh()
app.processEvents()
_lib_empty = lt.list_widget.count() == 0
if _lib_empty:
    check("P5b1 空库时空态面板可见", not lt._empty_state.isHidden())
    check("P5b2 空库态文案「还没有 mod」+ 工坊引导按钮",
          "还没有 mod" in lt._empty_title.text() and not lt._empty_go.isHidden())
    check("P5b3 空库态隐藏「清除筛选」", lt._empty_clear.isHidden())

from swdm.core.mod_library import ModRecord  # noqa: E402

win.svc.library.upsert(ModRecord(item_id="9001", appid="4000", title="Lib Mod",
                                 time_updated=1000))
lt.refresh()
app.processEvents()
check("P5b4 有记录时空态隐藏", lt._empty_state.isHidden())

lt.search_edit.setText("zzzz-no-match")
lt.refresh()
app.processEvents()
check("P5b5 筛选无结果 → 「没有匹配的 mod」+ 显示「清除筛选」",
      "没有匹配的 mod" in lt._empty_title.text() and not lt._empty_clear.isHidden())
_check_btn = lt.check_updates_btn
check("P5b6 筛选无结果时空态可见", not lt._empty_state.isHidden())

# 顺手验证 C1 按钮存在（功能验证在 test_t44_retest_gui.py）
check("P5b7 库页「🔍 检查更新」按钮存在", _check_btn.text() == "🔍 检查更新")
lt.search_edit.setText("")
lt.refresh()

# ====================================================== P6 A2 QSS
print("\n--- P6 A2 QSS 界面 ---")

from swdm.gui import styles  # noqa: E402

_dark = styles.qss("dark")
_light = styles.qss("light")
check("P6a 深色主题含进度条 done/failed 状态色",
      'QProgressBar[status="done"]' in _dark and 'QProgressBar[status="failed"]' in _dark)
check("P6b 浅色主题含进度条 done/failed 状态色",
      'QProgressBar[status="done"]' in _light and 'QProgressBar[status="failed"]' in _light)
check("P6c 表头 min-height 规则存在", "QHeaderView::section" in _dark)
check("P6d 滚动条 handle 描边规则存在", "QScrollBar::handle" in _dark)

check("P6e _resolve_theme 对 auto/dark/light 均有解",
      styles._resolve_theme("dark") == "dark" and
      styles._resolve_theme("light") == "light" and
      styles._resolve_theme("auto") in ("dark", "light"))
check("P6f system_theme_supported 返回布尔", isinstance(styles.system_theme_supported(), bool))

# 手动设置的 QSS 真的应用到窗口
win.setStyleSheet(_dark)
check("P6g 主题 QSS 可应用到 MainWindow", win.styleSheet() == _dark)

# ====================================================== P7 设置页新开关
print("\n--- P7 设置页新开关 ---")

check("P7a 剪贴板监听开关存在且默认开", st.clipboard_watch_check.isChecked())
check("P7b 详情缓存开关存在且默认开", st.detail_cache_check.isChecked())
check("P7c 详情缓存 TTL 控件存在", hasattr(st, "detail_ttl_spin") and
      st.detail_ttl_spin.value() >= 0)
check("P7d 主题组合框三选项（深色/浅色/跟随系统）",
      [st.theme_combo.itemData(i) for i in range(st.theme_combo.count())] ==
      ["dark", "light", "auto"])

# 清除缓存按钮可用且真的清缓存
_dc_mod.get_detail_cache = lambda: _cache   # 与设置页按钮同一受控实例
_cache.set("del-1", "x", 100)
st._clear_detail_cache()
_h_del, _ = _cache.get("del-1", 100)
check("P7e 「🧹 立即清除全部详情缓存」生效", not _h_del)

# 保存路径把开关写回配置（_apply_all 是设置页统一应用入口）
import inspect  # noqa: E402

_src = inspect.getsource(type(st)._apply_all)
check("P7f 应用函数含 clipboard_watch/detail_cache_enabled/ttl_hours 回写",
      "clipboard_watch" in _src and "detail_cache_enabled" in _src
      and "detail_cache_ttl_hours" in _src)
st.clipboard_watch_check.setChecked(True)
st.detail_cache_check.setChecked(True)

print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
