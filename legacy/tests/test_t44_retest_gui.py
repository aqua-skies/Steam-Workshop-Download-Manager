"""t44 GUI 复测第一轮 · 1.4.1 打包终态 offscreen 实测

两项审计必检项（1.4.2 审计）+ A6 修复验证（1.4.1 打包前修复）：

① 库页「🔍 检查更新」运行中能否取消（ux_audit U3 / P0 → 1.4.2 修复池）
   - A1 静态：_check_cancel 恒 False（死代码接线，captain 裁决 1.4.2 修）
   - A2/A3/A4 运行时：运行中按钮禁用；点击/刷新均不能中止；cancel 回调
     被轮询恒 False。本轮为特征化记录（现状与断言一致，避免误报）。
   - A5 契约对照：核心层 cancel 契约真实生效。

② 「最大并发下载」改大/调小静默失败（core_audit P0-4 → 1.4.2 修复池）
   - B1/B2/B3 特征化断言：refresh 只改 max_concurrent，调度门
     _concurrency._max/current 构造时固化；功能级实测实际并发=旧值。
     captain 裁决 1.4.2 修，本轮只确认现状与断言一致。

A6（1.4.1 打包前已修复）：C1 完成回调 Q_ARG(list) RuntimeError →
   library_tab.py 改用 Signal(list)。A6/A7 组验证**真实线程路径**：
   daemon worker → updates_checked Signal → GUI 线程 _on_check_updates_done，
   不再直调收尾函数绕过（t37 测试盲区，captain 第 2 点要求）。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

# 独立数据目录 + offscreen，必须先于 swdm 设置
_TMP = tempfile.mkdtemp(prefix="swdm_t44_")
os.environ["APPDATA"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, ".")

ok = True


def check(name: str, cond, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

import inspect  # noqa: E402

from swdm.core.mod_library import ModRecord  # noqa: E402
from swdm.core.steam_api import SteamAPI, WorkshopItem  # noqa: E402
from swdm.gui.services import build_services  # noqa: E402
from swdm.gui.library_tab import LibraryTab  # noqa: E402

svc = build_services()

# 造库：3 条带快照记录（time_updated>0 才可比对）
for i in range(3):
    svc.library.upsert(
        ModRecord(item_id=f"100{i}", appid="4000", title=f"Mod {i}", time_updated=1000)
    )

tab = LibraryTab(svc)
tab.setParent(None)

# 弹窗打桩（非阻塞）
msgs = []
_orig_info = QMessageBox.information
_orig_q = QMessageBox.question
QMessageBox.information = lambda p, t, x, *a, **k: msgs.append((t, x))
QMessageBox.question = lambda p, t, x, *a, **k: msgs.append((t, x))

# 线程异常捕获
thread_errors: list[str] = []
_orig_excepthook = threading.excepthook


def _hook(args):
    thread_errors.append(f"{args.exc_type.__name__}: {args.exc_value}")
    _orig_excepthook(args)


threading.excepthook = _hook

# ===================================================== ① 检查更新可取消性
print("\n--- ① 库页检查更新可取消性（U3 特征化，1.4.2 修复池） ---")

# A1 静态事实：library_tab.py 源码中 _check_cancel 的全部赋值点
src = inspect.getsource(LibraryTab)
assigns = [
    line.strip() for line in src.splitlines() if "_check_cancel" in line and "=" in line
]
true_writes = [ln for ln in assigns if "_check_cancel = True" in ln or "_check_cancel=True" in ln]
check("A1 _check_cancel 无任何置 True 的赋值点（死代码现状）",
      not true_writes and assigns, str(assigns))

# A6 端到端完成路径（修复后行为）：真实 daemon worker → Signal → GUI 线程回调
done_calls = {"n": 0, "updated": None}
_orig_done = tab._on_check_updates_done


def _count_done(updated):
    done_calls["n"] += 1
    done_calls["updated"] = list(updated)
    return _orig_done(updated)


tab._on_check_updates_done = _count_done


def _fast_check(records, progress=None, cancel=None):
    if progress:
        progress(len(records), len(records))
    return ["1001"]


svc.api.check_updates = _fast_check
msgs.clear()
tab._check_updates()
tab._check_thread.join(timeout=10)

deadline = time.time() + 3.0
while done_calls["n"] == 0 and time.time() < deadline:
    app.processEvents()
    time.sleep(0.02)

check("A6a daemon worker 正常结束（无异常）", tab._check_thread is not None
      and not tab._check_thread.is_alive())
check("A6b _on_check_updates_done 经真实线程路径（Signal(list)）被调用",
      done_calls["n"] == 1, f"done_calls={done_calls['n']}")
check("A6c 更新列表完整透传到 GUI 线程", done_calls["updated"] == ["1001"],
      str(done_calls["updated"]))
check("A6d 线程内无 QMetaType/其它异常",
      not [e for e in thread_errors if "QMetaType" in e or "qArgData" in e],
      str(thread_errors))
check("A6e 按钮恢复可用", tab.check_updates_btn.isEnabled())
check("A6f 按钮文本恢复", tab.check_updates_btn.text() == "🔍 检查更新",
      tab.check_updates_btn.text())
check("A6g 标红集合生成", tab._updated_ids == {"1001"}, str(tab._updated_ids))
check("A6h 弹出「发现更新」询问窗", any("发现更新" in m[0] for m in msgs), str(msgs))

tab._on_check_updates_done = _orig_done
thread_errors.clear()

# A2 运行时事实：启动真实 _check_updates，worker 期间 cancel 回调恒 False
polls: list[bool] = []
entered = threading.Event()
release = threading.Event()


def _blocking_check_updates(records, progress=None, cancel=None):
    entered.set()
    # 模拟大库多批检查：每批轮询 cancel，第 3 批起阻塞等待「用户取消/完成」
    total = len(records)
    for b in range(8):
        if cancel is not None:
            polls.append(bool(cancel()))
        if progress is not None:
            progress(min((b + 1) * 50, total), total)
        if b >= 2 and not release.is_set():
            release.wait(timeout=15)      # 阻塞：模拟几分钟的长检查
            if not release.is_set():
                return []
    return []


svc.api.check_updates = _blocking_check_updates
tab._check_updates()
entered.wait(timeout=10)
time.sleep(0.3)
app.processEvents()

check("A2a worker 真实启动（daemon 线程）", tab._check_thread is not None
      and tab._check_thread.is_alive())
check("A2b 运行中按钮禁用（防重入）", not tab.check_updates_btn.isEnabled())
check("A2c 运行中按钮文本为「检查中」",
      "检查中" in tab.check_updates_btn.text(), tab.check_updates_btn.text())
time.sleep(0.2)

# A3 模拟用户全部可能的取消路径，无一能中止检查（U3 现状特征化）
tab.check_updates_btn.click()        # 路径1：点击按钮——被禁用，无反应
tab.refresh()                        # 路径2：刷新列表——与检查无关
time.sleep(0.2)
still_alive = tab._check_thread is not None and tab._check_thread.is_alive()
check("A3a 点击/刷新均不能中止检查线程", still_alive)
check("A3b _check_cancel 仍为 False（无任何 UI 路径置位）", tab._check_cancel is False)

# A4 cancel 回调被 worker 轮询且恒 False（契约回调在 UI 层确为死代码）
if not polls:
    release.set()
    time.sleep(0.3)
check("A4 cancel() 被轮询过", len(polls) > 0, f"polls={len(polls)}")
check("A4b 轮询返回值恒 False", not any(polls), str(polls))

# A7 长检查完成后经真实 Signal 路径恢复 UI（A6 修复在阻塞场景同样成立）
done_after_block = done_calls["n"]
tab._on_check_updates_done = _count_done
release.set()
tab._check_thread.join(timeout=10)
deadline = time.time() + 3.0
while done_calls["n"] == done_after_block and time.time() < deadline:
    app.processEvents()
    time.sleep(0.02)
check("A7a 阻塞检查完成后 done 回调仍经真实线程路径到达",
      done_calls["n"] == done_after_block + 1)
check("A7b 按钮恢复可用", tab.check_updates_btn.isEnabled())
tab._on_check_updates_done = _orig_done
threading.excepthook = _orig_excepthook

# A5 契约对照：核心 API 层 cancel 语义真实存在且生效（t37 U7 复核）
api2 = SteamAPI()


def _fake_post(path, data):
    ids = [v for k, v in sorted(data.items()) if k.startswith("publishedfileids[")]
    return {"response": {"publishedfiledetails": [
        {"publishedfileid": i, "result": 1, "time_updated": 2000} for i in ids
    ]}}


api2._api_post = _fake_post
_c = {"n": 0}


def _cancel_after_2():
    _c["n"] += 1
    return _c["n"] > 2


recs = [(f"{i}", 1000) for i in range(200)]   # 4 批
_out = api2.check_updates(recs, cancel=_cancel_after_2)
check("A5 核心层 cancel 契约真实生效（第 2 次询问后中止）",
      _c["n"] >= 2 and len(_out) <= 150, f"n={_c['n']} out={len(_out)}")

_doc = inspect.getsource(SteamAPI.check_updates)
check("A5b 契约文档承诺 cancel 语义（用户关闭进度对话框中止）",
      "cancel" in _doc and "True" in _doc)

QMessageBox.information = _orig_info
QMessageBox.question = _orig_q

# ===================================================== ② 最大并发下载配置生效
print("\n--- ② 最大并发下载配置静默失败（P0-4 特征化，1.4.2 修复池） ---")

from swdm.core.downloader import DownloadManager, DownloadResult, DownloadStatus  # noqa: E402

# B1 初始并发（读配置默认值）→ 改大 → refresh_engine
cfg = svc.config
before = svc.downloader.max_concurrent
NEW = before + 3   # 明显更大的值
check("B1a 初始并发配置读取成功", before >= 1, str(before))

cfg.set("network", "max_concurrent_downloads", NEW)
svc.refresh_engine()

check("B1b refresh 后 downloader.max_concurrent 已更新（配置值）",
      svc.downloader.max_concurrent == NEW, f"{before} -> {svc.downloader.max_concurrent}")
gate = svc.downloader._concurrency
check("B1c 但调度门 _concurrency._max 仍为旧值（构造时固化）",
      gate.max_concurrent == before, f"gate_max={gate.max_concurrent} old={before}")
check("B1d current 上限被旧 _max 封顶（实际门未变）",
      gate.current <= before, f"current={gate.current} old_max={gate.max_concurrent}")

# B2 功能级实测：真实派发循环 + 打桩通道链，观测实际并发数
# （_throttle_wait 默认抖动 2s+ 会掩盖并发观测，打桩归零）
svc.downloader._throttle_wait = lambda job: None

obs = {"cur": 0, "max": 0}
_obs_lock = threading.Lock()


def _fake_chain(job, install_dir, smoother):
    with _obs_lock:
        obs["cur"] += 1
        obs["max"] = max(obs["max"], obs["cur"])
    time.sleep(0.4)
    with _obs_lock:
        obs["cur"] -= 1
    return DownloadResult(
        item_id=job.id, appid=job.appid,
        status=DownloadStatus.SUCCESS, bytes_done=1000,
    )


svc.downloader._run_channel_chain = _fake_chain   # 实例属性：调用时不绑 self

N_JOBS = before * 2 + 2     # 远超旧并发门，确保能观测到门上限
for i in range(N_JOBS):
    svc.downloader.enqueue(
        WorkshopItem(publishedfileid=f"200{i}", appid="4000", title=f"J{i}",
                     file_size=1000),
        "4000",
    )
svc.downloader.start()
t0 = time.time()
while time.time() - t0 < (N_JOBS / max(before, 1)) * 0.4 + 2.5:
    time.sleep(0.05)
    if obs["max"] >= before:
        # 已观测到旧门上限：再给一点窗口确认不会超过
        time.sleep(1.0)
        break
observed = obs["max"]
svc.downloader.stop()

check("B2a 实际并发观测上限为旧值（配置改大未生效，P0-4 现状）",
      observed == before, f"observed_max={observed} old={before}")
check("B2b 并非新配置值（调大静默失败，1.4.2 待修）", observed < NEW,
      f"observed_max={observed} new={NEW}")

# B3 反向：调低也不立即降（_current 固化在旧 _max，直至失败降级）
dm2 = DownloadManager(svc.engine, svc.library, max_concurrent=5)
dm2.max_concurrent = 1     # 模拟 refresh_engine 把配置改为 1 时的全部动作
check("B3a 调低后 _concurrency._max 仍为 5（P0-4 现状）",
      dm2._concurrency.max_concurrent == 5, str(dm2._concurrency.max_concurrent))
check("B3b current 仍为 5（派发门不会降到 1）", dm2._concurrency.current == 5,
      str(dm2._concurrency.current))
check("B3c 配置值 max_concurrent 已是 1（仅管理层字段变了）",
      dm2.max_concurrent == 1, str(dm2.max_concurrent))

print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
