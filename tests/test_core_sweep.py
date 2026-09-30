"""核心逻辑全面自测（1.3.8）：缓存污染 / 队列状态机 / 线程安全 /
steamcmd 输出解析 / CDN 续传 / 配置默认值。零网络。

覆盖 swdm/core/ 的 steam_api、downloader、mod_library、steamcmd_engine、
providers.cdn、config、paths、throttle。脚本式：check() + sys.exit。
"""
from __future__ import annotations

import copy
import io
import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_core_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


out = io.StringIO()


def p(*a):
    print(*a, file=out)


# ================================================================ 1. steam_api
from swdm.core.steam_api import SteamAPI, WorkshopItem  # noqa: E402
from swdm.core.api_cache import get_api_cache, make_cache_key  # noqa: E402

CARD_HTML = (
    '<div class="workshopItem">'
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111">'
    '<img src="https://steamusercontent.com/1.jpg" alt="Mod A">'
    '<div class="authorBlock">作者：AuthorA</div></a></div>'
    '<div class="workshopItem">'
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=222">'
    '<img src="https://steamusercontent.com/2.jpg" alt="Mod B"></a></div>'
)


def _bare_api():
    from swdm.core.circuit import CircuitBreaker

    a = SteamAPI.__new__(SteamAPI)      # 绕过 __init__（不建 session、不联网）
    a.timeout = 30
    a._session = None
    a.api_key = ""
    a._dep_titles = {}
    a._dep_cache = {}
    # browse() 访问共享熔断器（B2/t34），绕过 __init__ 时须手动补
    a._browse_breaker = CircuitBreaker()
    return a


# ---- _parse_cards 解析（id/标题/预览图/作者名）
api = _bare_api()
cards = api._parse_cards(CARD_HTML, "4000")
check("_parse_cards 解析 2 项", len(cards) == 2, str(len(cards)))
check("_parse_cards 解析 id/标题/预览图",
      cards and cards[0].publishedfileid == "111" and cards[0].title == "Mod A"
      and cards[0].preview_url == "https://steamusercontent.com/1.jpg",
      str(cards[0]) if cards else "empty")
check("_parse_cards 解析作者名（文本优先）",
      cards and cards[0].creator_name == "AuthorA",
      cards[0].creator_name if cards else "empty")
check("_parse_cards 空输入返回空列表", api._parse_cards("", "4000") == [])

# ---- 空输入 / 重复入队去重
check("_parse_cards 重复 id 去重",
      len(api._parse_cards(CARD_HTML + CARD_HTML, "4000")) == 2)

# ---- browse 缓存键维度 + 深拷贝（命中与未命中路径都必须深拷贝）
get_api_cache().invalidate()
fetches = {"n": 0}


def counting_get(path, params, max_retries=2):
    fetches["n"] += 1
    return CARD_HTML


api._community_get = counting_get
first = api.browse("4000", page=1)
check("browse 首次抓取 2 项", len(first) == 2, str(len(first)))
check("browse 首次抓取发起了网络请求", fetches["n"] == 1, str(fetches["n"]))

# 模拟 GUI 的 enrich() 就地修改返回值
first[0].title = "POLLUTED"
first[0].tags.append("BAD")
first[1].description = "POLLUTED_DESC"
again = api.browse("4000", page=1)
check("browse 命中缓存（零请求）", fetches["n"] == 1, str(fetches["n"]))
check("深拷贝：缓存未被污染（标题）",
      again[0].title == "Mod A", again[0].title)
check("深拷贝：缓存未被污染（tags）",
      again[0].tags == [], str(again[0].tags))
check("深拷贝：缓存未被污染（描述）",
      again[1].description == "", again[1].description)

# ---- hub 内联路径同样必须深拷贝
get_api_cache().invalidate()
api2 = _bare_api()
api2._community_get = lambda path, params, max_retries=2: "<html>no cards</html>"
_hub = [WorkshopItem(publishedfileid="999", title="Hub Mod", appid="4000")]


def _hub_inline(html, appid):
    return list(_hub)


api2._parse_hub_inline = _hub_inline
h1 = api2.browse("4000", page=2)
check("browse hub 内联路径返回 1 项", len(h1) == 1 and h1[0].title == "Hub Mod")
h1[0].title = "POLLUTED_HUB"
h2 = api2.browse("4000", page=2)
check("hub 路径深拷贝：缓存未被污染",
      h2[0].title == "Hub Mod", h2[0].title)

# ---- make_cache_key 维度隔离（含 numperpage）
k1 = make_cache_key("4000", 1, "trend", "", [], "schinese", 30)
k2 = make_cache_key("4000", 1, "trend", "", [], "schinese", 10)
check("make_cache_key: 不同 numperpage 生成不同 key", k1 != k2, f"{k1}|{k2}")
check("make_cache_key: tags 顺序无关",
      make_cache_key("4000", 1, "trend", "", ["b", "a"], "zh") ==
      make_cache_key("4000", 1, "trend", "", ["a", "b"], "zh"))
check("make_cache_key: 默认参数等价 30 档",
      make_cache_key("4000", 1, "trend", "", [], "schinese") == k1)

# ---- 端点节流：实例隔离 + 加锁串行（全局速率限制语义）
a_e1, a_e2 = SteamAPI(), SteamAPI()
check("_endpoint_throttle 状态不跨实例共享（按实例隔离）",
      a_e1._endpoint_last is not a_e2._endpoint_last
      and a_e1._endpoint_lock is not a_e2._endpoint_lock)
_orig_intervals = dict(SteamAPI._ENDPOINT_INTERVALS)
SteamAPI._ENDPOINT_INTERVALS = {"/workshop/browse/": 0.03}
try:
    shared_api = SteamAPI()
    n_calls = 40


    def _hammer():
        for _ in range(n_calls // 8):
            shared_api._endpoint_throttle("/workshop/browse/")


    t0 = time.time()
    ths = [threading.Thread(target=_hammer, daemon=True) for _ in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=30)
    elapsed = time.time() - t0
    # 无锁时线程并发 sleep，总耗时 ≈ 单次间隔；加锁后串行 = 间隔 × 调用数
    check("_endpoint_throttle 加锁串行（总耗时 >= 间隔×次数×0.8）",
          elapsed >= n_calls * 0.03 * 0.8, f"elapsed={elapsed:.2f}s")
finally:
    SteamAPI._ENDPOINT_INTERVALS = _orig_intervals

# ---- 429/403 错误处理与熔断器
from swdm.core.steam_api import _throttle, RateLimitError  # noqa: E402

_throttle._circuit_until = 0.0
_throttle._min_interval = 2.0
_throttle.trip(30.0)
check("熔断器 trip 后 in_circuit=True", _throttle.in_circuit is True)
_throttle._circuit_until = 0.0
_throttle._min_interval = 2.0
_throttle.bump(10.0)
check("bump 抬升最小间隔（上限 60s）",
      _throttle._min_interval == 10.0, str(_throttle._min_interval))
_throttle._min_interval = 2.0
_throttle.decay()
check("decay 每次回落 2s（下限 2s）",
      _throttle._min_interval == 2.0, str(_throttle._min_interval))

# 403 快速失败不重试
api3 = _bare_api()
api3._session = None
calls403 = {"n": 0}


def fake_403(path, params, max_retries=2):
    calls403["n"] += 1
    raise RateLimitError(60.0, status=403)


api3._community_get = fake_403
get_api_cache().invalidate()
try:
    api3.browse("4000", page=1)
    check("browse 403 无缓存时抛 RateLimitError", False)
except RateLimitError as e:
    check("browse 403 无缓存时抛 RateLimitError（不重试，1 次请求）",
          calls403["n"] == 1 and e.status == 403, f"n={calls403['n']}")

# ---- query_files 参数构造（无 key 时返回空，不抛异常）
api4 = _bare_api()
items_q, total_q = api4.query_files("4000", search_text="test")
check("query_files 无 key 返回空", items_q == [] and total_q == 0)

# ---- resolve_any_url 边界
check("resolve_any_url 空串", api4.resolve_any_url("") == ("", ""))
check("resolve_any_url 纯数字",
      api4.resolve_any_url("12345") == ("", "12345"))
check("resolve_any_url 详情页链接",
      api4.resolve_any_url(
          "https://steamcommunity.com/sharedfiles/filedetails/?id=999"
      ) == ("", "999"))
check("resolve_any_url 浏览页链接带 appid",
      api4.resolve_any_url(
          "https://steamcommunity.com/workshop/browse/?appid=4000&p=2"
      ) == ("4000", ""))

# ================================================================ 2. downloader
from swdm.core.downloader import DownloadManager, JobStatus  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steamcmd_engine import DownloadStatus  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import swdm.core.config as _cfg_mod  # noqa: E402


class _FakeCfg:
    def get(self, *a, **k):
        if len(a) >= 2 and a[0] == "download" and a[1] == "channel":
            return "steamcmd"
        return ""


_cfg_mod.get_config = _FakeCfg

lib = ModLibrary(os.path.join(_TMP, "lib"))

# ---- 2.1 取消运行中的任务：_done 不得重复登记
eng_cancel = MagicMock()
eng_cancel.ensure_partial.return_value = 0
started_ev = threading.Event()
release_ev = threading.Event()


def slow_download(**kw):
    started_ev.set()
    release_ev.wait(5)
    return MagicMock(status=DownloadStatus.FAILED, message="失败",
                     bytes_done=0, path="")


eng_cancel.download_item.side_effect = slow_download
mgr = DownloadManager(engine=eng_cancel, library=lib, auto_retry=0)
mgr._throttle_wait = lambda _j: None
mgr.start()
mgr.enqueue(WorkshopItem(publishedfileid="c100", title="C", appid="4000",
                         file_size=100), "4000")
check("任务被调度启动", started_ev.wait(5))
mgr.cancel("c100")
release_ev.set()
time.sleep(0.6)
done_jobs = [j for j in mgr.snapshot()["done"] if j.id == "c100"]
check("取消后 _done 不重复登记", len(done_jobs) == 1, f"n={len(done_jobs)}")
check("取消任务状态为 CANCELLED",
      bool(done_jobs) and done_jobs[0].status == JobStatus.CANCELLED,
      done_jobs[0].status.value if done_jobs else "none")
mgr.stop()

# ---- 2.2 取消不存在的 job 不抛异常
mgr2 = DownloadManager(engine=MagicMock(), library=lib)
mgr2.cancel("does_not_exist")
check("取消不存在的 job 不抛异常", True)
mgr2.stop()

# ---- 2.3 重复入队跳过
mgr3 = DownloadManager(engine=MagicMock(), library=lib)
it_d = WorkshopItem(publishedfileid="d1", title="D", appid="4000")
mgr3.enqueue(it_d, "4000")
mgr3.enqueue(it_d, "4000")
check("重复入队只保留一个",
      len([j for j in mgr3.snapshot()["queued"] if j.id == "d1"]) == 1)
mgr3.stop()

# ---- 2.4 失败重试状态机：retry 从 _done 移除并重新入队
eng_fail = MagicMock()
eng_fail.ensure_partial.return_value = 0
eng_fail.download_item.side_effect = lambda **kw: MagicMock(
    status=DownloadStatus.FAILED, message="失败", bytes_done=0, path="")
mgr4 = DownloadManager(engine=eng_fail, library=lib, auto_retry=0)
mgr4._throttle_wait = lambda _j: None
mgr4.start()
mgr4.enqueue(WorkshopItem(publishedfileid="r1", title="R", appid="4000"), "4000")
time.sleep(0.6)
snap = mgr4.snapshot()
check("失败任务进入 done 且状态 FAILED",
      any(j.id == "r1" and j.status == JobStatus.FAILED for j in snap["done"]))
# 先暂停派发，再 retry：否则重试任务瞬间跑完又落回 done，无法观察迁移
mgr4.pause_all()
ok_r = mgr4.retry("r1")
check("retry 失败任务返回 True", ok_r is True)
time.sleep(0.3)
snap = mgr4.snapshot()
check("retry 后任务离开 done",
      not any(j.id == "r1" for j in snap["done"]))
check("retry 后任务重新进入 queued/active",
      any(j.id == "r1" for j in snap["queued"])
      or any(j.id == "r1" for j in snap["active"]))
check("retry 不存在的 id 返回 False", mgr4.retry("nope") is False)
# retry_all_failed
mgr4.resume_all()
time.sleep(0.6)
n_retry = mgr4.retry_all_failed()
check("retry_all_failed 返回重试数 >= 1", n_retry >= 1, f"n={n_retry}")
mgr4.stop()

# ---- 2.5 pause_all 不派发 / resume_all 派发 / clear_completed
mgr5 = DownloadManager(engine=MagicMock(), library=lib)
mgr5._throttle_wait = lambda _j: None
dispatched = threading.Event()


def _dispatch(**kw):
    dispatched.set()
    return MagicMock(status=DownloadStatus.SUCCESS, message="ok",
                     bytes_done=1, path="")


mgr5.engine.download_item.side_effect = _dispatch
mgr5.engine.ensure_partial.return_value = 0
mgr5.start()
mgr5.pause_all()
mgr5.enqueue(WorkshopItem(publishedfileid="p1", title="P", appid="4000"), "4000")
time.sleep(0.5)
check("暂停时不派发新任务", not dispatched.is_set())
check("暂停时任务留在队列",
      any(j.id == "p1" for j in mgr5.snapshot()["queued"]))
mgr5.resume_all()
check("恢复后派发任务", dispatched.wait(5))
time.sleep(0.3)
check("成功任务进入 done",
      any(j.id == "p1" and j.status == JobStatus.SUCCESS
          for j in mgr5.snapshot()["done"]))
n_clear = mgr5.clear_completed()
check("clear_completed 清空 done（返回数>=1）", n_clear >= 1, f"n={n_clear}")
check("clear_completed 后 done 为空",
      len(mgr5.snapshot()["done"]) == 0)
mgr5.stop()

# ================================================================ 3. mod_library
from swdm.core.mod_library import ModRecord  # noqa: E402

lib2 = ModLibrary(os.path.join(_TMP, "lib2"))
lib2.upsert(ModRecord(item_id="m1", appid="4000", title="T1", file_size=100,
                      download_time=1000))
rec = lib2.get("m1")
check("upsert 新增记录", rec is not None and rec.title == "T1")

# 重新下载（_register_to_library 路径）：upsert 更新可变字段
lib2.upsert(ModRecord(item_id="m1", appid="4000", title="T1", file_size=200,
                      enabled=False, download_time=2000))
rec = lib2.get("m1")
check("upsert 更新 file_size", rec.file_size == 200, str(rec.file_size))
check("upsert 更新 download_time（重下载后排序信号刷新）",
      rec.download_time == 2000, str(rec.download_time))
check("upsert 更新 enabled", rec.enabled is False, str(rec.enabled))

# 用户元数据（分类/收藏/备注）在重新 upsert 后保留
lib2.set_category("m1", "我的分类")
lib2.set_favorite("m1", True)
lib2.set_notes("m1", "备注")
lib2.upsert(ModRecord(item_id="m1", appid="4000", title="T1", file_size=300,
                      download_time=3000))
rec = lib2.get("m1")
check("重新 upsert 保留用户分类", rec.category == "我的分类", rec.category)
check("重新 upsert 保留收藏标记", rec.favorite is True, str(rec.favorite))
check("重新 upsert 保留备注", rec.notes == "备注", rec.notes)

# 查询/统计
lib2.upsert(ModRecord(item_id="m2", appid="730", title="Alpha", file_size=50,
                      tags=["t1"], download_time=500, enabled=False))
check("search 按 appid 过滤",
      len(lib2.search(appid="4000")) == 1 and len(lib2.search(appid="730")) == 1)
check("search 关键词过滤",
      [r.item_id for r in lib2.search(keyword="alpha")] == ["m2"],
      str([r.item_id for r in lib2.search(keyword="alpha")]))
check("search tag 过滤",
      [r.item_id for r in lib2.search(tag="t1")] == ["m2"])
check("search disabled_only",
      [r.item_id for r in lib2.search(disabled_only=True)] == ["m2"],
      str([r.item_id for r in lib2.search(disabled_only=True)]))
check("search 空关键词返回全部", len(lib2.search()) == 2)
check("categories 列表", lib2.categories() == ["我的分类"],
      str(lib2.categories()))
check("all_tags 列表", lib2.all_tags() == ["t1"], str(lib2.all_tags()))
st = lib2.stats()
check("stats 统计",
      st["total"] == 2 and st["games"] == 2 and st["size"] == 350
      and st["enabled"] == 1, str(st))
check("delete 不存在的记录返回 False", lib2.delete("nope") is False)
lib2.set_enabled("m2", True)
check("set_enabled 生效", lib2.get("m2").enabled is True)
lib2.delete("m2")
check("delete 删除记录", lib2.get("m2") is None)

# ================================================================ 4. steamcmd_engine
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def feed_lines(lines, total_hint=1000):
    """用假 _run 喂入 steamcmd 输出行，跑完整 download_item 解析流程。"""
    eng = SteamCMDEngine(install_dir=os.path.join(_TMP, f"eng_{len(lines)}"))
    eng.resolve_exe = lambda: "fake-steamcmd.exe"
    events = []

    def fake_run(cmds, on_line=None, feed_stdin="", install_dir=""):
        for line in lines:
            on_line(line)
        return 0

    eng._run = fake_run
    res = eng.download_item(
        "4000", "111", total_hint=total_hint,
        on_progress=lambda pct, done, msg: events.append((pct, done, msg)),
    )
    return res, events


# ---- 成功 fixture
with open(os.path.join(FIX, "steamcmd_success.txt"), encoding="utf-8",
          errors="replace") as f:
    success_lines = [l.rstrip("\r\n") for l in f if l.strip()]
res, ev = feed_lines(success_lines, total_hint=1816113)
check("成功 fixture 解析为 SUCCESS",
      res.status == DownloadStatus.SUCCESS, res.status.value)
check("成功 fixture 解析字节数",
      res.bytes_done == 1816113, str(res.bytes_done))
check("成功 fixture 解析落地路径",
      res.path.endswith(os.path.join("4000", "3802244270")), res.path)
check("成功时下发 100% 完成事件",
      bool(ev) and ev[-1][0] == 100 and ev[-1][1] == 1816113, str(ev[-3:]))
check("'Downloading item' 立即下发开始事件",
      any(e[0] == 1 and e[1] == 0 for e in ev), str(ev[:2]))

# ---- 百分比 / Update state 行解析
res2, ev2 = feed_lines([
    "Connecting anonymously to Steam Public...OK",
    "Downloading item 111 ...",
    "[ 50%] 检查可用更新...",
    "Update state (0x61) downloading, progress: 45.6 (10.2 / 22.4 MBs)",
    'Success. Downloaded item 111 to "C:\\fake\\4000\\111" (5000 bytes)',
], total_hint=1000)
check("百分比行换算字节（total_hint=1000, 50% -> 500）",
      any(e[0] == 50 and e[1] == 500 for e in ev2), str(ev2))
_check_update = any(
    e[0] == 45 and e[1] == int(10.2 * 1024 * 1024) for e in ev2)
check("Update state 行解析（45%, 10.2MB）", _check_update, str(ev2))

# ---- 限流 fixture：FAILED + 特征消息
with open(os.path.join(FIX, "steamcmd_rate_limit.txt"), encoding="utf-8",
          errors="replace") as f:
    rl_lines = [l.rstrip("\r\n") for l in f if l.strip()]
res3, _ = feed_lines(rl_lines)
check("限流 fixture 解析为 FAILED",
      res3.status == DownloadStatus.FAILED, res3.status.value)
check("限流 fixture 消息含 RateLimit",
      "RateLimit" in (res3.message or ""), res3.message)

# ---- 超时 fixture：FAILED + 特征消息
with open(os.path.join(FIX, "steamcmd_timeout.txt"), encoding="utf-8",
          errors="replace") as f:
    to_lines = [l.rstrip("\r\n") for l in f if l.strip()]
res4, _ = feed_lines(to_lines)
check("超时 fixture 解析为 FAILED",
      res4.status == DownloadStatus.FAILED, res4.status.value)
check("超时 fixture 消息含 Timeout",
      "Timeout" in (res4.message or ""), res4.message)

# ---- 看门狗：停滞超时终止（短超时 + 无输出）
eng_wd = SteamCMDEngine(install_dir=os.path.join(_TMP, "eng_wd"),
                        stall_timeout=0.6)
eng_wd.resolve_exe = lambda: "fake-steamcmd.exe"


def fake_run_stall(cmds, on_line=None, feed_stdin="", install_dir=""):
    time.sleep(2.0)   # 模拟 steamcmd 卡死无输出
    return 0


eng_wd._run = fake_run_stall
res_wd = eng_wd.download_item("4000", "wd1")
check("停滞看门狗触发并标记失败",
      res_wd.status == DownloadStatus.FAILED and "停滞" in (res_wd.message or ""),
      res_wd.message)

# ---- 取消标志：cancel() 后 download_item 返回 CANCELLED
eng_c = SteamCMDEngine(install_dir=os.path.join(_TMP, "eng_c"))
eng_c.resolve_exe = lambda: "fake-steamcmd.exe"
_cancel_started = threading.Event()


def fake_run_cancel(cmds, on_line=None, feed_stdin="", install_dir=""):
    _cancel_started.set()
    for _ in range(100):
        if eng_c._cancel_flag.is_set():
            break
        time.sleep(0.02)
    return 0


eng_c._run = fake_run_cancel


def fire_cancel():
    time.sleep(0.2)
    eng_c.cancel()


tc = threading.Thread(target=fire_cancel, daemon=True)
tc.start()
res_c = eng_c.download_item("4000", "c1")
tc.join(3)
check("取消标志生效：download_item 返回 CANCELLED",
      res_c.status == DownloadStatus.CANCELLED, res_c.status.value)

# ---- ensure_partial：无内容返回 0
eng_p = SteamCMDEngine(install_dir=os.path.join(_TMP, "eng_p"))
check("ensure_partial 无内容返回 0",
      eng_p.ensure_partial("x1", "4000") == 0)

# ================================================================ 5. providers/cdn（门面已于 1.4.1 移除，直接测 provider）
from swdm.core.providers.cdn import CDNProvider  # noqa: E402

_cdn = CDNProvider(config={})
_cdn.api = None


class FakeResp:
    def __init__(self, status, chunks, headers=None):
        self.status_code = status
        self._chunks = chunks
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield from self._chunks


class FakeSession:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, headers=None, **k):
        self.calls.append(headers or {})
        return self._resp


dest = os.path.join(_TMP, "cdn", "mod.gma")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "wb") as f:
    f.write(b"A" * 10)

# ---- 206 续传
sess = FakeSession(FakeResp(206, [b"B" * 20], {"Content-Length": "20"}))
r = _cdn.http_download("http://x/f.gma", dest, sess)
check("206 续传成功且字节数=已有+新下",
      r.status == DownloadStatus.SUCCESS and r.bytes_done == 30, str(r))
check("续传请求携带 Range 头",
      sess.calls[0].get("Range") == "bytes=10-", str(sess.calls[0]))
check("续传内容正确追加",
      open(dest, "rb").read() == b"A" * 10 + b"B" * 20)

# ---- 200 忽略 Range：丢弃已有部分重下
sess2 = FakeSession(FakeResp(200, [b"C" * 5], {"Content-Length": "5"}))
r2 = _cdn.http_download("http://x/f.gma", dest, sess2)
check("200 忽略 Range 时整体重写",
      r2.status == DownloadStatus.SUCCESS and r2.bytes_done == 5, str(r2))
check("200 重写后文件为新内容",
      open(dest, "rb").read() == b"C" * 5)

# ---- 错误状态码
sess3 = FakeSession(FakeResp(403, []))
r3 = _cdn.http_download("http://x/f.gma", dest, sess3)
check("403 返回失败且消息含状态码",
      r3.status == DownloadStatus.FAILED and "403" in (r3.message or ""), str(r3))

# ---- resolve：匿名空直链回退
empty_item = WorkshopItem(publishedfileid="123", appid="4000")
check("resolve 空直链返回空串",
      _cdn.resolve(empty_item) == "")

# ---- download 无直链时返回可回退的失败
res_cdn = _cdn.download(empty_item, os.path.join(_TMP, "cdn"))
check("CDN 通道无直链返回 FAILED + 回退提示",
      res_cdn.status == DownloadStatus.FAILED and "回退" in res_cdn.message,
      res_cdn.message)

# ================================================================ 6. throttle
from swdm.core.throttle import (  # noqa: E402
    AdaptiveConcurrency,
    Backoff,
    ProgressSmoother,
    classify_steamcmd_line,
    jittered,
)

check("jittered base<=0 返回 0", jittered(0) == 0.0 and jittered(-1) == 0.0)
b = Backoff(base=2.0, cap=10.0)
d1 = b.record_failure()
check("Backoff 失败等级提升", b.level == 1 and 0 < d1 <= 10.0,
      f"level={b.level} delay={d1}")
b.record_success()
check("Backoff 成功回落", b.level == 0, str(b.level))

ac = AdaptiveConcurrency(max_concurrent=4, successes_to_raise=3, step=1)
ac.on_failure()
check("AdaptiveConcurrency 失败降到 1", ac.current == 1, str(ac.current))
for _ in range(6):
    ac.on_success()
check("AdaptiveConcurrency 连续成功回升", ac.current >= 2, str(ac.current))

# ---- AdaptiveConcurrency 并发安全（多线程 on_success 不丢计数、不越界）
ac2 = AdaptiveConcurrency(max_concurrent=4, successes_to_raise=3, step=1)
errs = []


def hammer():
    try:
        for _ in range(500):
            ac2.on_success()
    except Exception as e:  # noqa: BLE001
        errs.append(e)


ths2 = [threading.Thread(target=hammer, daemon=True) for _ in range(8)]
for t in ths2:
    t.start()
for t in ths2:
    t.join(timeout=20)
check("AdaptiveConcurrency 并发调用不抛异常", not errs, str(errs))
check("AdaptiveConcurrency 并发计数正确（4000 次成功后到顶 4）",
      ac2.current == 4 and ac2._successes >= 0, str(ac2.current))

# ---- ProgressSmoother
sm = ProgressSmoother(min_interval=0.1)
sm.reset(0, now=1.0)
snap1 = sm.feed(50, 100, now=1.2)     # 距 reset 0.2s -> 下发
check("ProgressSmoother 首次喂入下发",
      snap1 is not None and snap1["percent"] == 50, str(snap1))
snap2 = sm.feed(60, 100, now=1.22)    # 0.02s -> 限流丢弃
check("ProgressSmoother 限流丢弃（< min_interval）", snap2 is None)
snap3 = sm.feed(60, 100, now=1.4)     # 0.2s -> 下发
check("ProgressSmoother 超间隔后下发", snap3 is not None)
snap4 = sm.feed(40, 100, now=1.5)     # 字节倒退 -> 钳制为 60
check("ProgressSmoother 字节不倒退",
      snap4 is not None and snap4["bytes"] == 60, str(snap4))
snap5 = sm.feed(100, 100, force=True, now=1.55)
check("ProgressSmoother force 绕过限流",
      snap5 is not None and snap5["percent"] == 100, str(snap5))

# ---- classify_steamcmd_line
check("classify: rate_limit",
      classify_steamcmd_line("ERROR! Download item 1 failed (RateLimitExceeded)")
      == "rate_limit")
check("classify: timeout",
      classify_steamcmd_line("Timeout downloading item 1") == "timeout")
check("classify: retry",
      classify_steamcmd_line("Retrying... (3/3)") == "retry")
check("classify: 普通行返回 None",
      classify_steamcmd_line("Downloading item 1 ...") is None)
check("classify: 空行返回 None", classify_steamcmd_line("") is None)

# ================================================================ 7. config / paths
from swdm.core.config import Config, DEFAULT_CONFIG  # noqa: E402

c = Config.__new__(Config)          # 绕过单例与文件 IO
c._data = copy.deepcopy(DEFAULT_CONFIG)
c._file_lock = threading.Lock()
c._merge({
    "network": {"api_key": "KEY", "timeout": 60, "unknown_sub": 1},
    "game_dirs": {"4000": "D:/games"},
    "favorites_games": ["730"],
    "unknown_top": {"a": 1},
})
check("配置合并保留默认结构", c.get("general", "language") == "zh_CN")
check("配置合并用户值", c.get("network", "api_key") == "KEY")
check("配置合并未知顶层键", c.get("unknown_top", "a") == 1)
check("配置合并未知子键", c.get("network", "unknown_sub") == 1)
check("配置合并 game_dirs", c.get("game_dirs", "4000") == "D:/games")
check("配置合并列表类型", c.get("favorites_games") == ["730"])
check("get 缺失路径返回默认", c.get("network", "nope", default="D") == "D")
check("get 中途非 dict 返回默认",
      c.get("favorites_games", "x", default="D") == "D")
check("get 缺失 section 返回默认", c.get("nope", default="D") == "D")
# set / 嵌套创建
c.set("network", "proxy", "http://127.0.0.1:7890")
check("set 已有 section", c.get("network", "proxy") == "http://127.0.0.1:7890")
c.set("newsec", "k", "v")
check("set 创建新 section", c.get("newsec", "k") == "v")

# ---- 配置缺字段（老配置文件只有部分 section）
c2 = Config.__new__(Config)
c2._data = copy.deepcopy(DEFAULT_CONFIG)
c2._file_lock = threading.Lock()
c2._merge({"general": {"theme": "light"}})
check("老配置缺失 section 时其他默认值仍在",
      c2.get("network", "timeout") == 30
      and c2.get("download", "channel") == "steamcmd")

# ---- 磁盘读写往返
cfg_path = os.path.join(_TMP, "cfg_write")
os.makedirs(cfg_path, exist_ok=True)
_cfg_file_backup = _cfg_mod.CONFIG_FILE
_cfg_mod.CONFIG_FILE = os.path.join(cfg_path, "config.json")
try:
    c3 = Config()
    c3.set("network", "api_key", "DISKKEY")
    c3.save()
    c4 = Config()
    c4.load()
    check("配置写盘后重载保留值",
          c4.get("network", "api_key") == "DISKKEY")
    check("配置重载补齐默认结构",
          c4.get("dependencies", "max_depth") == 10)
finally:
    _cfg_mod.CONFIG_FILE = _cfg_file_backup

# ---- paths
from swdm.core import paths as _paths_mod  # noqa: E402

check("paths.DATA_DIR 取自 APPDATA 临时目录",
      _paths_mod.DATA_DIR == os.path.join(_TMP, "SWDM")
      or _paths_mod.DATA_DIR.startswith(_TMP),
      _paths_mod.DATA_DIR)
check("resource_path 开发态可定位核心文件",
      os.path.isfile(_paths_mod.resource_path("swdm", "core", "config.py")))

# ================================================================ 输出
fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    p(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("\n".join(out.getvalue().splitlines()))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if not fails else 1)
