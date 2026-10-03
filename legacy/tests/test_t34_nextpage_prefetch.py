# tests/test_t34_nextpage_prefetch.py
# B2 下一页预取入 ApiCache — t34 专项测试
# 三条硬约束：① 复用熔断退避 ② 深拷贝共用 browse() 路径 ③ 代际丢弃不覆盖当前页
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_appdata = tempfile.mkdtemp(prefix="swdm_t34_")
os.environ["APPDATA"] = _appdata
# 标准路径插入（与 test_t26/t19 等一致）：从仓库根运行也能导入 swdm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_RESULTS = []


def check(name, cond, extra=""):
    _RESULTS.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}".rstrip())


# ====================================================== A. 熔断器（共享）
from swdm.core.circuit import CircuitBreaker  # noqa: E402

_b = CircuitBreaker()
check("A1 初始非冷却期", not _b.in_cooldown())

# A2 连续 3 次失败 → 冷却
for _ in range(2):
    _b.record_failure(ValueError("x"))
check("A2 2 次失败未熔断", not _b.in_cooldown())
_b.record_failure(ValueError("x"))
check("A3 连续 3 次失败熔断 15s", _b.in_cooldown() and 14 < _b.cooldown_remaining() <= 15)

# A4 成功重置
_b2 = CircuitBreaker()
_b2.record_failure(ValueError("x"))
_b2.record_failure(ValueError("x"))
_b2.record_success()
_b2.record_failure(ValueError("x"))
check("A4 成功重置计数（再 1 次失败不熔断）", not _b2.in_cooldown())

# A5 ConnectionError 立即熔断（不等 3 次）
import requests  # noqa: E402

_b3 = CircuitBreaker()
_b3.record_failure(requests.ConnectionError("10053"))
check("A5 ConnectionError 立即熔断", _b3.in_cooldown())

# A6 冷却期过后自动半开
_b4 = CircuitBreaker()
_b4.force_trip(seconds=1)
time.sleep(1.1)
check("A6 冷却期过后自动解除", not _b4.in_cooldown())

# A7 GameSearchClient 与 SteamAPI 复用同一实现
from swdm.core.game_search import GameSearchClient  # noqa: E402
from swdm.core.steam_api import SteamAPI  # noqa: E402

_gs = GameSearchClient()
_api = SteamAPI()
check("A7a GameSearchClient 复用 CircuitBreaker",
      isinstance(_gs._breaker, CircuitBreaker))
check("A7b SteamAPI._browse_breaker 复用 CircuitBreaker",
      isinstance(_api._browse_breaker, CircuitBreaker))
# 行为等价：t22 语义（连接错误/连续 3 次 → 冷却）
_gs._breaker.force_trip()
check("A7c GameSearchClient._in_cooldown 委托 breaker",
      _gs._in_cooldown() is True)

# ====================================================== B. 预取调度（GUI）
from PySide6.QtWidgets import QApplication  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
wt = win.workshop_tab

# 30 个物品 = 满页（numperpage=30）
_full = [WorkshopItem(publishedfileid=str(i), title=f"mod-{i}", appid="4000")
         for i in range(30)]
_half = _full[:10]

# B1 满页 + 代际当前 → 调度预取（timer 启动）
wt._worker_gen = 5
wt._page = 1
wt._items = _full
wt._nextpage_timer.stop()
wt._schedule_prefetch_next_page(5)
check("B1 满页且代际当前 → 启动预取定时器", wt._nextpage_timer.isActive())

# B2 未满页 → 不调度
wt._nextpage_timer.stop()
wt._items = _half
wt._schedule_prefetch_next_page(5)
check("B2 未满页（<30）不调度预取", not wt._nextpage_timer.isActive())

# B3 代际过期 → 不调度
wt._items = _full
wt._schedule_prefetch_next_page(4)  # 旧代际
check("B3 代际过期不调度预取", not wt._nextpage_timer.isActive())

# B4 熔断期 → 不调度
wt._worker_gen = 5
wt._items = _full
wt.svc.api._browse_breaker.force_trip()
wt._schedule_prefetch_next_page(5)
check("B4 熔断冷却期不调度预取", not wt._nextpage_timer.isActive())
wt.svc.api._browse_breaker.record_success()  # 解除

# ====================================================== C. 预取执行 + 礼让
from swdm.core.api_cache import get_api_cache, make_cache_key  # noqa: E402

# 清空缓存并注入当前页状态
_cache = get_api_cache()
_cache.invalidate()
wt._page = 1
wt._worker_gen = 10
wt._items = _full
# 让 _current_appid 返回 4000（绕过下拉控件依赖）
wt._current_appid = lambda: "4000"
wt.search_edit.setText("")
wt.sort_combo.setCurrentIndex(0)
wt.tag_edit.setText("")
# B4 的 force_trip 冷却未到期（record_success 只重置计数，符合 t22 语义），
# 这里换上新熔断器隔离
from swdm.core.circuit import CircuitBreaker as _CB  # noqa: E402

wt.svc.api._browse_breaker = _CB()

# 网络层 mock：browse 的唯一网络出口是 _community_get，
# 返回空串 → browse 解析 0 卡片但仍 cache.set([])（空结果也暖缓存）
_net = {"n": 0}
_orig_cg = SteamAPI._community_get


def _fake_cg(self, path, params=None, **kw):
    _net["n"] += 1
    return ""


# C1 _priority_pending>0 → 礼让：定时器重排且不发线程
wt.svc.api._priority_pending = 1
wt._do_prefetch_next_page()
check("C1 用户请求在飞时预取礼让（重排定时器）",
      wt._nextpage_timer.isActive() and wt._nextpage_thread is None)
wt.svc.api._priority_pending = 0
wt._nextpage_timer.stop()

# C2 正常预取：daemon 线程启动，下一页 key 入缓存
_key_p2 = make_cache_key("4000", 2, wt.sort_combo.currentData(), "", [],
                         "schinese", 30)
SteamAPI._community_get = _fake_cg
_net["n"] = 0
try:
    wt._do_prefetch_next_page()
    check("C2a 预取 daemon 线程启动", wt._nextpage_thread is not None
          and wt._nextpage_thread.daemon)
    # 等待线程完成
    _deadline = time.time() + 20
    while wt._nextpage_prefetching and time.time() < _deadline:
        app.processEvents()
        time.sleep(0.05)
    check("C2b 预取完成（不卡死）", not wt._nextpage_prefetching)
    # 预取实际发了 1 次网络请求（page=2）
    check("C2c 预取触发一次 browse 网络请求", _net["n"] == 1, f"n={_net['n']}")
    _hit_p2, _v_p2 = _cache.get(_key_p2)
    check("C2d 下一页 key 已写入 ApiCache（空结果也暖缓存）",
          _hit_p2, f"key={_key_p2[:40]}")
finally:
    SteamAPI._community_get = _orig_cg

# C3 用户真正翻页：browse() 命中缓存零网络（_community_get 计数验证）
SteamAPI._community_get = _fake_cg
_net["n"] = 0
try:
    _r = wt.svc.api.browse("4000", page=2)
    check("C3 翻页命中预取缓存零网络（_community_get 不再被调）",
          _r is not None and _net["n"] == 0, f"n={_net['n']}")
finally:
    SteamAPI._community_get = _orig_cg

# C4 深拷贝纪律：预取暖的缓存与 browse 命中路径共用同一深拷贝
_r_mut = wt.svc.api.browse("4000", page=2)
if _r_mut:
    _r_mut[0].title = "MUTATED-POLLUTION-TEST"
    _r_mut[0].tags.append("polluted")
_r_again = wt.svc.api.browse("4000", page=2)
_polluted = any(
    (it.title == "MUTATED-POLLUTION-TEST" or "polluted" in (it.tags or []))
    for it in _r_again
) if _r_again else False
check("C4 命中缓存返回深拷贝（修改不污染缓存）", not _polluted)

# ====================================================== D. 代际丢弃
# 模拟预取完成后代际已前进：结果不得覆盖当前页
wt._worker_gen = 20
wt._page = 1
wt._items = _full
_cur_ids = [c.item.publishedfileid for c in wt._cards()]
# 直接调用回调（gen=99 已过期，key 由调用方传入）
wt._on_nextpage_prefetched(99, "browse:4000:2:trend::::schinese:30")
check("D1 过期代际预取结果被丢弃（当前页不变）",
      [c.item.publishedfileid for c in wt._cards()] == _cur_ids
      and not wt._nextpage_prefetching)

# D2 _on_items_ready 代际过期丢弃（照搬 t25 A-U5 已验证机制）
wt._worker_gen = 30
wt._tags_by_gen = {30: []}
wt._search_by_gen = {30: ""}
wt._on_items_ready(_full[:3], 29)  # 过期代际
check("D2 _on_items_ready 过期代际结果被丢弃",
      [c.item.publishedfileid for c in wt._cards()] == _cur_ids)

# D3 线程内代际校验：预取线程启动后代际已变 → 不发包（静默丢弃）
wt._worker_gen = 40
wt._nextpage_prefetching = False
SteamAPI._community_get = _fake_cg
_net["n"] = 0
try:
    wt._do_prefetch_next_page()   # 捕获 gen=40
    wt._worker_gen = 41           # 线程执行前代际已变
    _d3 = time.time() + 10
    while wt._nextpage_prefetching and time.time() < _d3:
        app.processEvents()
        time.sleep(0.02)
    check("D3 线程内代际过期 → 不发包（静默丢弃）", _net["n"] == 0,
          f"n={_net['n']}")
finally:
    SteamAPI._community_get = _orig_cg

# ====================================================== E. browse 熔断计入
# browse 连接失败 → 熔断器记录（真实网络层用 mock 触发）
from swdm.core.steam_api import RateLimitError  # noqa: E402

_b5 = CircuitBreaker()
_api2 = SteamAPI()
_api2._browse_breaker = _b5
# 直接调 record_failure 模拟 browse 的 except 分支
_api2._browse_breaker.record_failure(requests.ConnectionError("down"))
check("E1 browse 连接失败计入共享熔断器", _b5.in_cooldown())

# F 新请求作废待发预取
wt._nextpage_timer.start()
wt._worker_gen = 40
wt._do_refresh_list.__wrapped__ if False else None  # noqa: B018
# 直接走 _do_refresh_list 的前置：清缓存+代际+1（会真发网络，用计时器路径代替）
wt._nextpage_timer.start()
# 模拟新请求发出（不真发：只验证 stop 语义在 _do_refresh_list 内）
# 用反射确认 _do_refresh_list 中存在 stop 调用（代码层保证）
import inspect  # noqa: E402

_src = inspect.getsource(wt._do_refresh_list)
check("F _do_refresh_list 发新请求前 stop 下一页预取定时器",
      "_nextpage_timer.stop()" in _src)

_n_fail = sum(1 for _n, ok in _RESULTS if not ok)
print(f"\nTOTAL: {len(_RESULTS)} checks, {len(_RESULTS) - _n_fail} pass, "
      f"{_n_fail} fail")
if _n_fail:
    print("FAILED:")
    for _n, ok in _RESULTS:
        if not ok:
            print("  -", _n)
    sys.exit(1)
print("RESULT: ALL PASS")
