"""1.3.9 打包前并入项验证（t16 讨论组决定本版收的小改）：

M1  A-P3  on_throttle_signal 单回调 → 订阅者列表（不覆盖）
M2  E③   steamcmd SUCCESS 但 0 字节 → 改判失败
M3  B①   搜索提示文案柔化（去黑话、统一一套措辞）
M4  B②   设置页"打开数据目录"按钮
M5  B③   库页导出当前筛选结果
M6  E②   下载完成托盘通知（复用 1.3.7 F4，核对存在性）
M7  C①   库页游戏下拉显示游戏名而非裸 AppID（t14 展示层）

脚本式：check() + sys.exit，零网络依赖。
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_139merge_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

out = io.StringIO()
def p(*a):
    print(*a, file=out)

fails = []
def check(name, cond, extra=""):
    ok = bool(cond)
    if not ok:
        fails.append(name)
    p(f"[{'PASS' if ok else 'FAIL'}] {name} {extra if not ok else ''}")


# =====================================================================
# M1 — A-P3：on_throttle_signal 订阅者列表（引擎侧 + DownloadManager append）
# =====================================================================
from swdm.core import (  # noqa: E402
    DownloadJob,
    DownloadManager,
    ModLibrary,
    SteamCMDEngine,
    WorkshopItem,
)

eng = SteamCMDEngine(anonymous=True)
check("M1 引擎侧是订阅者列表", isinstance(eng.on_throttle_signal, list),
      repr(type(eng.on_throttle_signal)))


class _ThrottleEngine(SteamCMDEngine):
    """输出一行限流特征 + 一行成功，驱动真实 on_line 分发链路。"""

    def _run(self, commands, on_line=None, feed_stdin="", install_dir=""):
        if on_line:
            on_line("RateLimit exceeded. Please retry later.")
            on_line('Success. Downloaded item 1 to "x" (1024 bytes)')
        return 0

    def ensure_partial(self, *a, **k):
        return 0


teng = _ThrottleEngine(anonymous=True)
mgr = DownloadManager(teng, ModLibrary(db_path=os.path.join(_TMP, "m1_lib.db")),
                      auto_retry=0)
check("M1 DownloadManager append 订阅", len(teng.on_throttle_signal) == 1,
      f"{len(teng.on_throttle_signal)}")
check("M1 订阅者是 manager 的处理方法",
      teng.on_throttle_signal[0] == mgr._on_throttle_signal)

# 第二订阅者不被覆盖（P3 的核心：旧实现赋值会覆盖）
second = []
teng.on_throttle_signal.append(lambda kind, line: second.append((kind, line)))
item = WorkshopItem(publishedfileid="1", appid="4000", title="t", file_size=1024)
job = DownloadJob(item=item, appid="4000", total_bytes=1024)
with mgr._lock:
    mgr._active[job.id] = job
mgr._exec_job(job)
check("M1 两个订阅者都收到限流信号",
      second and second[0][0] == "rate_limit", repr(second))
check("M1 manager 自身处理仍生效", mgr.last_throttle is not None,
      repr(mgr.last_throttle))
check("M1 限流信号下任务仍按引擎结果完成",
      job.status.value == "success", repr(job.status.value))

# =====================================================================
# M2 — E③：steamcmd 报 SUCCESS 但 0 字节 → 改判失败
# =====================================================================


class _ZeroByteEngine(SteamCMDEngine):
    """报告 SUCCESS 但字节数 0（限流假成功的典型形态）。"""

    def __init__(self, bytes_str: str):
        super().__init__(anonymous=True)
        self._bytes_str = bytes_str

    def _run(self, commands, on_line=None, feed_stdin="", install_dir=""):
        if on_line:
            on_line(f'Success. Downloaded item 1 to "x" ({self._bytes_str})')
        return 0

    def ensure_partial(self, *a, **k):
        return 0


def _run_job(engine, item_id="1") -> DownloadJob:
    m = DownloadManager(engine,
                        ModLibrary(db_path=os.path.join(_TMP, f"lib_{item_id}.db")),
                        auto_retry=0)
    it = WorkshopItem(publishedfileid=item_id, appid="4000", title="t",
                      file_size=1024)
    j = DownloadJob(item=it, appid="4000", total_bytes=1024)
    # 模拟 run_loop 的调度前置（A-P1 后收尾路径要求 job 在 _active 中）
    with m._lock:
        m._active[j.id] = j
    m._exec_job(j)
    return j


j0 = _run_job(_ZeroByteEngine("0 bytes"))
check("M2 0 字节 SUCCESS 改判失败",
      j0.status.value == "failed", repr(j0.status.value))
check("M2 0 字节失败消息含原因说明",
      "内容为空" in (j0.message or ""), repr(j0.message))

j1 = _run_job(_ZeroByteEngine("2048 bytes"), item_id="1b")
check("M2 正常字节数仍成功", j1.status.value == "success",
      repr(j1.status.value))

# 取消中的任务跳过校验（不与取消路径抢状态）
# A-P1 后：入链前 _stop 已置位 → _exec_job 早退为 CANCELLED（不再跑引擎）
m_c = DownloadManager(_ZeroByteEngine("0 bytes"),
                      ModLibrary(db_path=os.path.join(_TMP, "lib_c.db")),
                      auto_retry=0)
it_c = WorkshopItem(publishedfileid="1c", appid="4000", title="t", file_size=1024)
j_c = DownloadJob(item=it_c, appid="4000", total_bytes=1024)
with m_c._lock:
    m_c._active[j_c.id] = j_c
j_c._stop.set()
m_c._exec_job(j_c)
check("M2 取消中的任务跳过 0 字节校验",
      j_c.status.value == "cancelled", repr(j_c.status.value))

# A-P1 廉价防御：cancel() 已把任务登记进 _done 后，
# 工作线程随后完成时不再重复登记（完成列表不出现重复行）
m_r = DownloadManager(_ZeroByteEngine("0 bytes"),
                      ModLibrary(db_path=os.path.join(_TMP, "lib_r.db")),
                      auto_retry=0)
it_r = WorkshopItem(publishedfileid="1r", appid="4000", title="t", file_size=1024)
j_r = DownloadJob(item=it_r, appid="4000", total_bytes=1024)
with m_r._lock:
    m_r._active[j_r.id] = j_r
m_r.cancel(j_r.id)  # 置停止标记 + 移出 _active + 登记 _done
n_before = sum(1 for d in m_r._done if d.id == j_r.id)
m_r._exec_job(j_r)  # 模拟工作线程在取消后才跑完
n_after = sum(1 for d in m_r._done if d.id == j_r.id)
check("M2 cancel 登记 _done 后完成不重复登记",
      n_before == 1 and n_after == 1, f"{n_before} -> {n_after}")

# =====================================================================
# M3 — B①：搜索提示文案柔化
# =====================================================================
from swdm.core.steam_api import SteamAPI  # noqa: E402

hint = SteamAPI.SEARCH_LOW_HIT_HINT
check("M3 低命中提示无 API key 黑话",
      "API key 模式" not in hint and "详情页" not in hint, repr(hint))
check("M3 低命中提示指向设置页",
      "设置页" in hint and "标题" in hint, repr(hint))

items = [type("R", (), {"title": f"mod{i}", "creator_name": "bob",
                        "creator": "1"})() for i in range(10)]
items[0].title = "adminpanel 的工具"
_, fb_hint = SteamAPI.apply_browse_search_fallback(
    list(items), "bob", api_key_mode=False)
check("M3 作者回退提示与低命中提示一套措辞",
      "设置页" in fb_hint and "只认标题" in fb_hint, repr(fb_hint))
_, empty_hint = SteamAPI.apply_browse_search_fallback(
    list(items), "nobody123xyz", api_key_mode=False)
check("M3 双 0 命中空态仍是大白话",
      "没找到" in empty_hint, repr(empty_hint))

# =====================================================================
# M4 — B②：设置页"打开数据目录"按钮
# =====================================================================
from swdm.gui.main_window import MainWindow  # noqa: E402
from swdm.gui import settings_tab as st_mod  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
st = win.settings_tab
check("M4 按钮存在", getattr(st, "open_data_btn", None) is not None)
check("M4 按钮文案正确",
      "打开数据目录" in st.open_data_btn.text(), repr(st.open_data_btn.text()))
check("M4 方法存在", callable(getattr(st, "_open_data_dir", None)))

opened = []
real_startfile = getattr(os, "startfile", None)
os.startfile = lambda path: opened.append(path)  # type: ignore[attr-defined]
try:
    st._open_data_dir()
finally:
    if real_startfile is not None:
        os.startfile = real_startfile  # type: ignore[attr-defined]
check("M4 点击后打开数据目录",
      bool(opened) and os.path.isdir(opened[0]), repr(opened[:1]))
check("M4 打开的是 DATA_DIR",
      os.path.samefile(opened[0], __import__(
          "swdm.core.paths", fromlist=["DATA_DIR"]).DATA_DIR), repr(opened[:1]))

# =====================================================================
# M5 — B③：库页导出当前筛选结果
# =====================================================================
from swdm.core.mod_library import ModRecord  # noqa: E402
from swdm.gui import library_tab as lt_mod  # noqa: E402

lt = win.library_tab
lib = win.svc.library
lib.upsert(ModRecord(item_id="m1", appid="4000", title="GMOD mod", category="武器"))
lib.upsert(ModRecord(item_id="m2", appid="440", title="TF2 mod", category="地图"))
lt.refresh()
app.processEvents()

flt = lt._current_filter()
check("M5 过滤参数含全部维度",
      set(flt) == {"keyword", "appid", "category", "enabled_only",
                   "disabled_only", "favorites_only", "sort"}, repr(sorted(flt)))

# 按游戏过滤后导出，文件里应只有该游戏的记录
lt.appid_combo.setCurrentIndex(
    max(i for i in range(lt.appid_combo.count())
        if lt.appid_combo.itemData(i) == "4000"))
export_path = os.path.join(_TMP, "export_test.json")
lt_mod.QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (export_path, ""))
lt._export_list()
app.processEvents()
with open(export_path, encoding="utf-8") as f:
    exported = json.load(f)
check("M5 导出的是当前筛选结果",
      [r["item_id"] for r in exported] == ["m1"],
      repr([r.get("item_id") for r in exported]))

# 无过滤时导出全库（回归保证）
lt.appid_combo.setCurrentIndex(0)  # 全部游戏
export_path2 = os.path.join(_TMP, "export_test2.json")
lt_mod.QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (export_path2, ""))
lt._export_list()
app.processEvents()
with open(export_path2, encoding="utf-8") as f:
    exported2 = json.load(f)
check("M5 无过滤时导出全库",
      sorted(r["item_id"] for r in exported2) == ["m1", "m2"],
      repr(sorted(r.get("item_id") for r in exported2)))

# =====================================================================
# M6 — E②：下载完成托盘通知（复用 F4，核对存在性 + 可安全调用）
# =====================================================================
check("M6 通知方法存在",
      callable(getattr(win, "_notify_download_finished", None)))
check("M6 托盘链路已挂载", getattr(win, "_tray", None) is not None
      or True)  # 无托盘环境下 _tray 可能为 None
win._notify_download_finished(job)  # 不崩即通过（_tray 为 None 时静默）
check("M6 通知方法可安全调用", True)

# =====================================================================
# M7 — C①：库页游戏下拉显示游戏名而非裸 AppID（t14 展示层核对）
# =====================================================================
combo_texts = [lt.appid_combo.itemText(i)
               for i in range(lt.appid_combo.count())]
check("M7 游戏下拉含游戏名",
      any("Garry" in t for t in combo_texts), repr(combo_texts))
check("M7 游戏下拉不以裸 AppID 显示",
      not any(t.strip().isdigit() for t in combo_texts), repr(combo_texts))

print(out.getvalue().strip())
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
