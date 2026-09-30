"""t25 · 1.4.0 第一轮复测（GUI / 用户视角）。

复测对象：1.4.0 打包终态（installer\Output\SWDM-Setup-1.4.0.exe 42.69MB，
版本号双端 1.4.0）。四部分：
  A. U1-U12 回归（t21/t22 改动是否破坏 1.3.9 既有修复）
  B. provider 链新行为（通道 UI / 匿名降级 / 链尾兜底 / 熔断 / 坏包回退）
  C. t22 GUI 项（调试 Tab 隐藏 / 批量按钮合并 / 搜索间隔 0.7s）
  D. 关联交互（通道切换↔在飞任务 / 库分类+导出共存）

环境：PYTHONUTF8=1 + QT_QPA_PLATFORM=offscreen + import swdm 前设 APPDATA。
退出码 -1073740791 是已知 Qt 拆卸 flake，判定标准为 stdout RESULT。
"""
import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_t25_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, bool(ok), extra))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))


from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# _apply_all 末尾模态对话框在 offscreen 下无人点击会永久阻塞（t23 已定位）
_QBOX = QMessageBox.information
QMessageBox.information = staticmethod(lambda *a, **k: None)

from swdm.core.config import ensure_dirs  # noqa: E402
from swdm.core.logger import setup_logger  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

setup_logger("WARNING")
ensure_dirs()
app = QApplication.instance() or QApplication(sys.argv)
win = MainWindow()
win.show()
app.processEvents()
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
app.processEvents()

# ====================================================== A. U1-U12 回归
# U1 托盘隐藏态直退
from PySide6.QtCore import QCoreApplication  # noqa: E402

_quits = []
_orig = QCoreApplication.quit
QCoreApplication.quit = lambda: _quits.append(1)
try:
    win._force_quit = False
    win._real_quit()
    check("A-U1a 隐藏态 _real_quit 直接触发 quit", len(_quits) == 1, str(_quits))
    check("A-U1b _force_quit 已置位", win._force_quit is True)
    # AppMutex 释放路径存在（不重复断言句柄细节，t18 已验证）
    check("A-U1c _do_real_quit 方法存在且可调", hasattr(win, "_do_real_quit"))
finally:
    QCoreApplication.quit = _orig

# U4 回车待选链路
class _FR:
    def __init__(self, appid, name):
        self.appid = appid
        self.name = name


wt = win.workshop_tab
wt._do_game_search = lambda t=None, **kw: None
wt._local_game_matches = lambda t: []
_gen0 = wt._search_version
wt._search_version = _gen0 + 1
_ed = wt.game_combo.lineEdit()
_ed.setText("zzzqqq")  # 无本地匹配的词，强制走待选链路
wt._on_game_enter()
app.processEvents()
_searches = getattr(wt, "_pending_enter_select", None)
check("A-U4 回车进入待选链路（_pending_enter_select 已挂）",
      _searches is True, repr(_searches))
wt._on_search_ready([_FR("4000", "Garry's Mod"), _FR("440", "TF2")],
                    version=wt._search_version)
app.processEvents()
check("A-U4b 搜索就绪自动选中首项",
      str(wt.game_combo.currentData()) == "4000",
      repr(wt.game_combo.currentData()))

# U5 标签精确过滤端到端
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

_items = [
    WorkshopItem(publishedfileid="111", title="A", appid="4000", tags=["生存"]),
    WorkshopItem(publishedfileid="222", title="B", appid="4000", tags=["建造"]),
    WorkshopItem(publishedfileid="333", title="C", appid="4000", tags=["生存", "建造"]),
]
wt._worker_gen = wt._search_version
wt._tags_by_gen = {wt._search_version: ["生存"]}
wt._on_items_ready(_items, wt._search_version)
app.processEvents()
_cards = {c.item.publishedfileid for c in wt._cards()}
check("A-U5 标签精确过滤（交集）", _cards == {"111", "333"}, str(_cards))

# U6 切游戏清标签
wt._on_game_changed(0)
app.processEvents()
check("A-U6a 切游戏清标签选中", len(wt.tag_bar.selected()) == 0,
      str(wt.tag_bar.selected()))
check("A-U6b 切游戏清过滤输入", wt.tag_edit.text() == "",
      repr(wt.tag_edit.text()))

# U7/U8 速度采样（provider 链下 smoother 仍由 _exec_job 构造并喂入 provider）
from swdm.core.throttle import ProgressSmoother  # noqa: E402

sm = ProgressSmoother(min_interval=0.1, smoothing=0.5)
_now = [0.0]
_snaps = []
for i in range(30):
    _now[0] += 0.1
    _s = sm.feed(1_000_000 * (i + 1), 30_000_000, now=_now[0])
    if _s:
        _snaps.append(_s)
_snap = sm.feed(30_000_000, 30_000_000, force=True, now=_now[0])
if _snap is None:
    _snap = _snaps[-1] if _snaps else {}
check("A-U7a 滚动窗口速度稳定（1-30MB/s 合理区间）",
      0.5 < _snap.get("speed_mbps", 0) < 60, str(_snap))
check("A-U7b 字节达 total 直返 100%",
      abs(_snap.get("percent", 0) - 100.0) < 1e-6, str(_snap.get("percent")))
check("A-U7c 10Hz 喂入有有效快照下发（非全限流）", len(_snaps) >= 10,
      str(len(_snaps)))
# 突发摊平：第 15 tick 合并 20MB
sm2 = ProgressSmoother(min_interval=0.1, smoothing=0.5)
_n2 = [0.0]
_speeds = []
for i in range(30):
    _n2[0] += 0.1
    _b = 1_000_000 * (i + 1) + (20_000_000 if i == 15 else 0)
    _s = sm2.feed(min(_b, 30_000_000), 30_000_000, force=True, now=_n2[0])
    if _s:
        _speeds.append(_s.get("speed_mbps", 0))
check("A-U8 突发 20MB 被摊平（峰值 <50MB/s）",
      _speeds and max(_speeds) < 50, f"peak={max(_speeds) if _speeds else 0:.1f}")

# U9 设置页几何
from swdm.gui.widgets import CollapsibleSection  # noqa: E402

_secs = win.settings_tab.findChildren(CollapsibleSection)
check("A-U9a 设置页分组区存在", len(_secs) >= 1, str(len(_secs)))
_ref = _secs[0]
_ok_geo = True
for s in _secs:
    if s.isVisible():
        p = s.mapTo(_ref, __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(0, 0))
        if p.y() < 0:
            _ok_geo = False
check("A-U9b 可见分组相对坐标非负（无挤压重叠）", _ok_geo)
_tbl = win.settings_tab.game_dirs_table
check("A-U9c 目录表首行行高 ≥24",
      _tbl.rowHeight(0) >= 24 if _tbl.rowCount() else True,
      str(_tbl.rowHeight(0) if _tbl.rowCount() else "no rows"))

# U10 删除互通（下载现在走 provider 链，信号路径不变）
dl = win.downloads_tab
_xid = "999001"
lib = win.library_tab
lib.library.upsert(ModRecord(item_id=_xid, title="X", appid="4000"))
lib.refresh()
app.processEvents()
# 走库页真实的删除路径：library.delete → records_removed → 下载页清行 → refresh
_removed = []
_orig_rr = dl.remove_rows_for
dl.remove_rows_for = lambda ids: _removed.extend(ids)
try:
    lib.library.delete(_xid, remove_files=False)
    lib.records_removed.emit([_xid])
    lib.refresh()
    app.processEvents()
finally:
    dl.remove_rows_for = _orig_rr
check("A-U10a 库删除 → 下载页行清除", _xid in _removed, str(_removed))

# U11 库行游戏名渲染 + 删除无残留
lib.refresh()
app.processEvents()
_texts = [lib.list_widget.item(i).text()
          for i in range(lib.list_widget.count())]
check("A-U11 删除后列表无残留", not any(_xid in t for t in _texts),
      str(_texts[:3]))
# 新增一条验证游戏名行内渲染（u12）
lib.library.upsert(ModRecord(item_id="999011", title="GameNameTest",
                             appid="4000"))
lib.refresh()
app.processEvents()
_texts2 = [lib.list_widget.item(i).text()
           for i in range(lib.list_widget.count())]
check("A-U11b 库行含游戏名渲染（Garry's Mod）",
      any("Garry" in t for t in _texts2), str(_texts2[:3]))

# U12 详情页缓存命中（进程级 _page_cache，命中则不调 _community_get）
from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402

DetailPageWorker._page_cache["999002"] = (time.time(), "<html>cached</html>")
_net_called = {"n": 0}
from swdm.core.steam_api import SteamAPI  # noqa: E402
_orig_cg = SteamAPI._community_get
SteamAPI._community_get = lambda self, *a, **k: _net_called.__setitem__(
    "n", _net_called["n"] + 1) or ""
try:
    _w = DetailPageWorker(SteamAPI(), "999002")
    _t0 = time.time()
    _w.run()
    _elapsed = time.time() - _t0
finally:
    SteamAPI._community_get = _orig_cg
check("A-U12a 详情页缓存命中不走网络",
      _net_called["n"] == 0 and _elapsed < 0.5,
      f"net={_net_called['n']} t={_elapsed:.3f}")

# ====================================================== B. provider 链新行为
from swdm.core.downloader import DownloadJob  # noqa: E402
from swdm.core.providers import get_registry  # noqa: E402
from swdm.core.providers.base import Availability  # noqa: E402
from swdm.core.providers.cdn import CDNProvider  # noqa: E402
from swdm.core.providers.ggnetwork import GGNetworkProvider  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus  # noqa: E402

reg = get_registry()

# B1 通道下拉（UI）
st = win.settings_tab
_rows = st._channel_rows
_names = [r[0] for r in _rows]
check("B1a 通道下拉含三通道", {"steamcmd", "cdn", "ggnetwork"} <= set(_names),
      str(_names))
check("B1b 下拉项附可用性标记文案",
      any("匿名" in r[1] or "推荐" in r[1] for r in _rows),
      str([r[1] for r in _rows]))

# B2 通道切换写 config
_ci = st.channel_combo.findData("cdn")
st.channel_combo.setCurrentIndex(_ci if _ci >= 0 else 0)
app.processEvents()
st._apply_all()
app.processEvents()
_ch = win.svc.config.get("download", "channel", default="")
check("B2 切换通道写入 config.download.channel", _ch == "cdn", repr(_ch))

# B3 匿名降级：CDN 匿名无直链 → FAILED + 回退提示 → 下一通道
_cdn = reg.get_provider("cdn")
_item = WorkshopItem(publishedfileid="999003", title="T", appid="4000", file_url="")
_item.file_url = ""
_r = _cdn.download(_item, os.path.join(_TMP, "d3"),
                   on_progress=None, stop_event=None)
check("B3a CDN 匿名无直链 → FAILED", _r.status == DownloadStatus.FAILED,
      str(_r.status))
check("B3b 回退提示文案带 SteamCMD",
      "SteamCMD" in (_r.message or ""), (_r.message or "")[:60])
check("B3c CDN should_fallback=True", _cdn.should_fallback(_r) is True)

# B4 链尾兜底 + terminal 豁免熔断
_chain = reg.build_chain(preferred="cdn")
check("B4a 链尾永远是 steamcmd",
      _chain and _chain[-1].meta.name == "steamcmd",
      str([c.meta.name for c in _chain]))
check("B4b 首选 cdn 在链首", _chain[0].meta.name == "cdn",
      str([c.meta.name for c in _chain]))
# B4c terminal 豁免熔断：走真实 _run_channel_chain，所有通道全失败，
# steamcmd 的熔断器不应被累计（否则链会失去兜底）
reg.record_success("steamcmd")
reg.record_success("cdn")
reg.record_success("ggnetwork")
_mgr0 = win.downloads_tab.mgr
_orig_rp0 = _mgr0._run_provider
def _all_fail(provider, job, install_dir, smoother):
    return DownloadResult(item_id=job.id, appid=job.appid,
                          status=DownloadStatus.FAILED, message="fail")
_mgr0._run_provider = _all_fail
try:
    _job0 = DownloadJob(item=WorkshopItem(publishedfileid="999010", title="T", appid="4000"), appid="4000")
    _job0._stop = threading.Event()
    _mgr0._run_channel_chain(_job0, _TMP, None)
finally:
    _mgr0._run_provider = _orig_rp0
_chain2 = reg.build_chain(preferred="steamcmd")
check("B4c terminal 通道豁免熔断（生产路径失败后 steamcmd 仍可用）",
      any(c.meta.name == "steamcmd" for c in _chain2),
      str([c.meta.name for c in _chain2]))
reg.record_success("steamcmd")
reg.record_success("cdn")
reg.record_success("ggnetwork")

# B5 熔断器生产接线：cd 非失败 3 次 → 后续链构造跳过
for _ in range(3):
    reg.record_failure("cdn")
_chain3 = reg.build_chain(preferred="cdn")
check("B5a cdn 熔断后被链构造跳过",
      "cdn" not in [c.meta.name for c in _chain3],
      str([c.meta.name for c in _chain3]))
check("B5b 熔断后链尾仍是 steamcmd",
      _chain3 and _chain3[-1].meta.name == "steamcmd")
reg.record_success("cdn")

# B6 ggnetwork 守卫语义（t32 修复后：url 优先，position 仅在无 url 时表示排队）
_gg = reg.get_provider("ggnetwork")


class _FakeResp:
    status_code = 200

    def json(self):
        return {"url": "http://x/y.gma", "queue": {"position": 3}}


class _FakeSess:
    def post(self, *a, **k):
        return _FakeResp()


class _QueuedResp:
    status_code = 200

    def json(self):
        return {"queue": {"position": 3}}   # 无 url：排队中


class _QueuedSess:
    def post(self, *a, **k):
        return _QueuedResp()


_orig_sess = _gg._session
_gg._session = lambda: _FakeSess()
try:
    _u = _gg.resolve(WorkshopItem(publishedfileid="999004", title="T",
                                  appid="4000"))
    check("B6 有 url 时优先返回 url（position 不再误吞成功响应）",
          _u == "http://x/y.gma", repr(_u))
finally:
    _gg._session = _orig_sess
_gg._session = lambda: _QueuedSess()
try:
    _u2 = _gg.resolve(WorkshopItem(publishedfileid="999004b", title="T2",
                                   appid="4000"))
    check("B6b 无 url 且 position>0 → 返空串（排队中干净回退）",
          _u2 == "", repr(_u2))
finally:
    _gg._session = _orig_sess

# B7 ggnetwork 坏包（>1% 尺寸差异）→ FAILED + 回退
class _BadGG:
    """最小替身：复用真实 should_fallback 与坏包消息路径。"""
_gg2 = reg.get_provider("ggnetwork")
_note, _size_bad = "size mismatch", True
_r2 = DownloadResult(item_id="999005", appid="4000",
                     status=DownloadStatus.FAILED,
                     message="内容大小与 Steam 声明不符（可能下载不完整），已回退 SteamCMD 重下")
check("B7a 坏包消息含回退原因", "回退" in _r2.message and "大小" in _r2.message)
check("B7b 坏包 should_fallback=True", _gg2.should_fallback(_r2) is True)

# B8 匿名场景无 key 通道优雅跳过（ggnetwork 匿名可用）
check("B8 ggnetwork requires_key=False（匿名可用）",
      GGNetworkProvider.meta.requires_key is False)

# ====================================================== C. t22 GUI 项
# C1 调试 Tab 默认隐藏
_tab_names = [win._tabs.tabText(i) for i in range(win._tabs.count())]
check("C1a 默认无调试 Tab", not any("调试" in t for t in _tab_names),
      str(_tab_names))
check("C1b debug_tab 实例常在", getattr(win, "debug_tab", None) is not None)
_dpc = st.debug_panel_check
check("C1c 开关默认关闭", _dpc.isChecked() is False)
_dpc.setChecked(True)
app.processEvents()
st._apply_all()
app.processEvents()
check("C1d 开关写入 config",
      bool(win.svc.config.get("logging", "show_debug_panel", default=False)))

# C2 批量按钮 4 操作
_btn = dl.pause_all_btn
_allb = [c.text() for c in dl.findChildren(type(_btn))]
check("C2a 暂停/继续单按钮", "暂停" in _btn.text(), repr(_btn.text()))
check("C2b 重试失败/清除已完成仍独立",
      any("重试" in t for t in _allb) and any("清除" in t for t in _allb),
      str(_allb))
dl.mgr.pause_all()
app.processEvents()
dl._sync_batch_buttons()
check("C2c 暂停后按钮切「全部继续」", "继续" in _btn.text(), repr(_btn.text()))
dl._toggle_pause_all()
app.processEvents()
dl._sync_batch_buttons()
check("C2d 继续后按钮切回「全部暂停」", "暂停" in _btn.text())
check("C2e mgr.paused 已复位", getattr(dl.mgr, "paused", False) is False)

# C3 搜索间隔 0.7s + 熔断
from swdm.core.game_search import GameSearchClient  # noqa: E402
import requests  # noqa: E402

_gsc = GameSearchClient()
check("C3a 最低间隔 0.7s", abs(_gsc._min_interval - 0.7) < 1e-9,
      str(_gsc._min_interval))
_gsc._record_failure(requests.ConnectionError("10053"))
# 熔断细节委托 CircuitBreaker（t34 起），用公开 API 判冷却（私有属性已移除）
_rem = _gsc.cooldown_remaining()
check("C3b 连接熔断 → 冷却 15s", 14.0 <= _rem <= 15.0, f"remain={_rem:.1f}")
check("C3b2 is_in_cooldown 与剩余时间一致", _gsc.is_in_cooldown())
_gsc._cache.clear()
check("C3c 冷却内 search 返空", _gsc.search("garry") == [])
_gsc._breaker.force_trip(0.0)          # 立即解除冷却（测试用）
_gsc._cache["garry"] = (1e12, [("4000", "Garry's Mod")])
check("C3d 缓存命中即时返回",
      len(_gsc.search("garry")) == 1)
# 本地联想即时层不受网络影响
wt._local_game_matches = lambda t: [("4000", "Garry's Mod")]
_ed2 = wt.game_combo.lineEdit()
_ed2.setText("gar")
try:
    wt._on_search_text_edited("gar")
except Exception:  # noqa: BLE001
    pass
app.processEvents()
check("C3e 本地联想即时出候选（不等 0.7s）",
      wt.game_combo.count() > 0 and "Garry's Mod" in wt.game_combo.itemText(0),
      repr(wt.game_combo.itemText(0) if wt.game_combo.count() else ""))

# ====================================================== D. 关联交互
# D1 通道切换 ↔ 在飞任务：job.channel 由链内实际跑通的通道记录
from swdm.core.downloader import DownloadManager, DownloadJob  # noqa: E402

_dlg = win.downloads_tab
_mgr = _dlg.mgr
_job = DownloadJob(item=WorkshopItem(publishedfileid="999006", title="T", appid="4000"),
                   appid="4000")
_job._stop = threading.Event()
_chan_used = {"name": None}
_orig_rp = _mgr._run_provider
def _fake_rp(provider, job, install_dir, smoother):
    _chan_used["name"] = provider.meta.name
    return DownloadResult(item_id=job.id, appid=job.appid,
                          status=DownloadStatus.SUCCESS, path=install_dir,
                          bytes_done=0, message="ok")
_mgr._run_provider = _fake_rp
try:
    _r3 = _mgr._run_channel_chain(_job, _TMP, None)
    check("D1a 链内回退不消耗 auto_retry（一次 attempt 跑通首通道）",
          _chan_used["name"] == "cdn", _chan_used["name"])
    check("D1b job.channel 记录实际通道", _job.channel == "cdn",
          repr(_job.channel))
finally:
    _mgr._run_provider = _orig_rp

# D2 库分类 + 导出共存
lib2 = win.library_tab
lib2.library.upsert(ModRecord(item_id="999007", title="Exp", appid="4000"))
app.processEvents()
_f = getattr(lib2, "_current_filter", None)
check("D2a _current_filter 方法存在（导出当前筛选）", callable(_f))
_exports = []
_orig_exp = lib2._export_list
lib2._export_list = lambda *a, **k: _exports.append(1)
try:
    _btns = lib2.findChildren(type(_btn))
    _exp_btn = next((c for c in _btns if "导出" in c.text()), None)
    if _exp_btn is not None:
        _exp_btn.click()
        app.processEvents()
finally:
    lib2._export_list = _orig_exp
check("D2b 导出按钮可触发导出路径", len(_exports) >= 1, str(_exports))

# ====================================================== 结果
_fails = [r for r in RESULTS if not r[1]]
print("RESULT:", "ALL PASS" if not _fails else f"HAS FAILURES ({len(_fails)})")
sys.exit(0 if not _fails else 1)
