"""t37（C1）mod 库更新检查测试 —— 手动按钮版（首版不自动重下）。

四条硬约束的测试映射：
1. bypass api_cache —— U1/U2：插桩 _api_post 计数，断言请求确实发出（未走缓存）
2. 大库进度反馈 —— U6/U7：500 条 = 10 批，progress 回调必被多次调用且单调递增
3. 首版只标红/角标 + 一键入队 —— U8b/U9：无新版本弹窗/有新版本询问后才入队
4. 批 50 条/批复用 _throttle 端点基准 —— U3：批大小与 _ENDPOINT_INTERVALS 端点键存在

契约三条：
- 旧值无更新（time_updated 未变 → 不标红）
- 新值标红（time_updated 变大 → 标红 + 询问入队）
- 断言请求绕过 api_cache（_api_post 直调，不经 get_api_cache）
"""

from __future__ import annotations

import os
import sys
import tempfile

# 独立数据目录，必须先于 swdm 设置
_TMP = tempfile.mkdtemp(prefix="swdm_t37_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, ".")

ok = True


def check(name: str, cond, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


# ------------------------------------------------------------- 核心层（U 组）
from swdm.core.steam_api import SteamAPI  # noqa: E402
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402

api = SteamAPI()

# 插桩 _api_post：记录请求（证明绕过 api_cache）+ 返回可控 payload
posts = {"n": 0, "seen_ids": []}


def _fake_post(path, data):
    posts["n"] += 1
    posts["seen_ids"].append(path)
    ids = [v for k, v in sorted(data.items()) if k.startswith("publishedfileids[")]
    details = []
    for i in ids:
        if i in NEW_TU:                    # 新版本
            details.append({"publishedfileid": i, "result": 1, "time_updated": NEW_TU[i]})
        else:                              # 旧版本（不变）
            details.append({"publishedfileid": i, "result": 1, "time_updated": OLD_TU[i]})
    return {"response": {"publishedfiledetails": details}}


NEW_TU = {"111": 9999, "222": 8888}        # 这两个有更新
OLD_TU = {"111": 1000, "222": 1000, "333": 1000, "444": 1000, "555": 1000}

api._api_post = _fake_post

# U1 旧值无更新：全部 time_uploaded 不变 → 返回空列表
res = api.check_updates([("333", 1000), ("444", 1000)])
check("U1 旧值无更新返回空", res == [], str(res))
check("U1b 请求确实发出（绕过 api_cache）", posts["n"] >= 1, f"posts={posts['n']}")

# U2 新值标红（比对层）：time_updated 变大 → 出现在结果集
posts["n"] = 0
res = api.check_updates([("111", 1000), ("333", 1000)])
check("U2 新值进入结果集", res == ["111"], str(res))
check("U2b 只含变化项", "333" not in res)

# U2c 断言绕过 api_cache：请求路径是 API POST 而非社区页/缓存
check("U2c 打的是 API 批量端点",
      all("/ISteamRemoteStorage/" in p for p in posts["seen_ids"]),
      str(posts["seen_ids"][:2]))

# U3 批 50 条/批：_ENDPOINT_INTERVALS 端点基准存在
check("U3 批量端点节流基准存在",
      any(p.startswith("/ISteamRemoteStorage/") for p in SteamAPI._ENDPOINT_INTERVALS),
      str([p for p in SteamAPI._ENDPOINT_INTERVALS]))

# U4 快照为 0 的条目被跳过（无快照不误报）
posts["n"] = 0
res = api.check_updates([("111", 0), ("222", 0)])
check("U4 无快照条目跳过", res == [] and posts["n"] == 0, f"posts={posts['n']}")

# U5 全部无快照 → 零请求
posts["n"] = 0
res = api.check_updates([])
check("U5 空输入零请求", res == [] and posts["n"] == 0)

# U6 大库进度反馈：500 条 = 10 批，progress 必调用且单调递增
posts["n"] = 0
progress = []
recs = [(f"{i}", 1000) for i in range(500)]
res = api.check_updates(recs, progress=lambda d, t: progress.append((d, t)))
check("U6 500 条分 10 批", posts["n"] == 10, f"posts={posts['n']}")
check("U6b progress 被调用 10 次", len(progress) == 10, f"calls={len(progress)}")
check("U6c progress 单调递增到 500",
      progress and progress[-1] == (500, 500) and
      all(progress[i][0] <= progress[i + 1][0] for i in range(len(progress) - 1)),
      str(progress[-1]))

# U7 cancel 中止后续批次
posts["n"] = 0
calls = {"n": 0}


def _cancel():
    calls["n"] += 1
    return calls["n"] > 2                  # 第 2 次询问后取消


res = api.check_updates(recs, cancel=_cancel)
check("U7 cancel 中止后续批", posts["n"] <= 4, f"posts={posts['n']}")
check("U7b cancel 被轮询", calls["n"] >= 2)

# U8 单批失败不废整次检查（第 1 批抛异常，后续批仍完成）
posts["n"] = 0


def _flaky_post(path, data):
    posts["n"] += 1
    if posts["n"] == 1:
        raise RuntimeError("network down")
    return _fake_post(path, data)


api._api_post = _flaky_post
res = api.check_updates([("111", 1000), ("333", 1000)])
check("U8 首批失败不传播异常", isinstance(res, list), str(res))
check("U8b 首批失败跳过不误标", res == [], str(res))

# ------------------------------------------------- GUI 层（V 组：标红/入队）
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

from swdm.gui.services import build_services  # noqa: E402
from swdm.gui.library_tab import LibraryTab  # noqa: E402

svc = build_services()

# 造库：3 条记录，111 有更新（新 tu 9999），333 无更新，555 无快照
svc.library.upsert(ModRecord(item_id="111", appid="4000", title="Mod A", time_updated=1000))
svc.library.upsert(ModRecord(item_id="333", appid="4000", title="Mod C", time_updated=1000))
svc.library.upsert(ModRecord(item_id="555", appid="4000", title="Mod E", time_updated=0))
svc.library.upsert(ModRecord(item_id="222", appid="4000", title="Mod B", time_updated=1000))

tab = LibraryTab(svc)
tab.setParent(None)

# 插桩 GUI 层用到的 api（与核心用同一个 svc.api 实例）
svc.api._api_post = _fake_post

# V1 初始无标红
check("V1 初始无标红", tab._updated_ids == set())

# V2 无新版本弹窗：Qt 阻塞弹窗用 exec 方式，插桩 QMessageBox.information
msgs = []
_orig_info = QMessageBox.information
_orig_q = QMessageBox.question


def _info(parent, title, text, *a, **k):
    msgs.append(("info", title, text))
    return QMessageBox.StandardButton.Ok


def _q(parent, title, text, *a, **k):
    msgs.append(("q", title, text))
    # 模拟真实阻塞弹窗：用户看到询问窗时列表已标红（refresh 先于弹窗）
    marked["ids"] = set(tab._updated_ids)
    _row = None
    for i in range(tab.list_widget.count()):
        it = tab.list_widget.item(i)
        if it.data(0x0100) == "111":
            _row = it.text()
            marked["brush"] = it.foreground()
            break
    marked["row"] = _row or ""
    return QMessageBox.StandardButton.Yes      # 模拟用户同意入队


QMessageBox.information = _info
QMessageBox.question = _q
marked = {"ids": set(), "row": "", "brush": None}

# V3 触发检查（直调 worker 串行执行，绕过线程以便测试）
tabs_net = {"n": 0}
_orig_all = svc.library.all
svc.library.all = lambda: _orig_all()
tab._check_thread = None
# 手动串行执行 worker 逻辑（不建线程）：
tab._check_cancel = False
tab.check_updates_btn.setEnabled(False)
res = svc.api.check_updates(
    [(r.item_id, r.time_updated) for r in _orig_all() if r.time_updated > 0],
)
tab._on_check_updates_done(res)

# V3 有更新 → 标红集合为 {111, 222}（333 无更新，555 无快照跳过）
check("V3 标红集合正确", marked["ids"] == {"111", "222"}, str(marked["ids"]))
# V3b 用户看到询问窗时，列表里的标红行已渲染（🔄 前缀）
check("V3b 标红行在询问时已渲染", "🔄" in marked["row"], marked["row"][:50])
_cb = marked["brush"]
check("V3c 标红行红色", _cb is not None and _cb.color().red() == 255,
      str(_cb.color().getRgb() if _cb else None))

# V4 弹了「发现更新」询问窗（一键入队走询问，不自动下）
qmsgs = [m for m in msgs if m[0] == "q"]
check("V4 弹出更新询问窗（不自动重下）", len(qmsgs) == 1 and "发现更新" in qmsgs[0][1])

# V5 一键入队：同意后 111/222 进入下载队列
_snap = svc.downloader.snapshot()
queue_ids = {j.item.publishedfileid for j in _snap["queued"] + _snap["active"] + _snap["done"]}
check("V5 同意后入队", "111" in queue_ids and "222" in queue_ids, str(queue_ids))
check("V5b 未更新项不入队", "333" not in queue_ids and "555" not in queue_ids)

# V6 标红在入队后清除
check("V6 入队后清除标红", tab._updated_ids == set())

# V7 入队后列表行失去标红（V3b 已验证渲染时为红，此处验证清除后无前缀）
found_red = False
for i in range(tab.list_widget.count()):
    it = tab.list_widget.item(i)
    if it.data(0x0100) == "111":            # Qt.ItemDataRole.UserRole
        found_red = True
        check("V7 入队后标红已清除", "🔄" not in it.text(), it.text()[:40])
        cb = it.foreground().color()
        check("V7b 入队后非红色", cb.red() != 255, str(cb.getRgb()))
check("V7c 行存在于列表", found_red)

# V8 按钮恢复
check("V8 按钮恢复可用", tab.check_updates_btn.isEnabled())
check("V8b 按钮文本恢复", tab.check_updates_btn.text() == "🔍 检查更新")

# V9 询问「否」时标红保留、不入队
svc.api._api_post = _fake_post


def _q_no(parent, title, text, *a, **k):
    marked["ids"] = set(tab._updated_ids)    # 拒绝前捕获标红态
    return QMessageBox.StandardButton.No


QMessageBox.question = _q_no
svc.downloader._queue.clear()                # 清空队列再测
svc.downloader._active.clear()
svc.downloader._done.clear()
res = svc.api.check_updates(
    [(r.item_id, r.time_updated) for r in _orig_all() if r.time_updated > 0],
)
tab._on_check_updates_done(res)
_snap = svc.downloader.snapshot()
queue_ids = {j.item.publishedfileid for j in _snap["queued"] + _snap["active"] + _snap["done"]}
check("V9 拒绝时标红保留", marked["ids"] == {"111", "222"}, str(marked["ids"]))
check("V9a 拒绝后标红仍在集合", tab._updated_ids == {"111", "222"}, str(tab._updated_ids))
check("V9b 拒绝时入队为零", "111" not in queue_ids, str(queue_ids))

# V10 无新版本弹「没有发现需要更新的 mod」
msgs.clear()
QMessageBox.question = _q
svc.api._api_post = lambda p, d: {"response": {"publishedfiledetails": [
    {"publishedfileid": "111", "result": 1, "time_updated": 1000},
    {"publishedfileid": "222", "result": 1, "time_updated": 1000},
    {"publishedfileid": "333", "result": 1, "time_updated": 1000},
]}}
res = svc.api.check_updates(
    [(r.item_id, r.time_updated) for r in _orig_all() if r.time_updated > 0],
)
tab._on_check_updates_done(res)
infos = [m for m in msgs if m[0] == "info"]
check("V10 无更新弹「没有发现」窗", any("没有发现" in m[2] for m in infos), str(infos))

# V11 空库防护：全部无快照时提示且不请求
msgs.clear()
svc.library.all = lambda: [ModRecord(item_id="999", appid="4000", time_updated=0)]
tab._check_updates()
infos = [m for m in msgs if m[0] == "info"]
check("V11 全无快照弹提示", any("快照" in m[2] for m in infos), str(infos))
check("V11b 空库无线程启动", tab._check_thread is None or not tab._check_thread.is_alive())
svc.library.all = _orig_all

QMessageBox.information = _orig_info
QMessageBox.question = _orig_q

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
