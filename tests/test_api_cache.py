"""API 缓存层测试：命中/过期/失效/上限/请求合并/限流降级（零网络）。"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_apicache_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# ================================================================ 1. ApiCache 基础
from swdm.core.api_cache import ApiCache, get_api_cache, make_cache_key  # noqa: E402

c = ApiCache(ttl=10, max_entries=5)
c.set("k1", "v1")
hit, val = c.get("k1")
check("set/get 命中", hit and val == "v1", f"{hit},{val}")
hit, _ = c.get("missing")
check("未命中返回 False", not hit)

# 过期
c.set("k2", "v2", ttl=0.05)
time.sleep(0.1)
hit, _ = c.get("k2")
check("过期自动失效", not hit)

# LRU 上限淘汰（max_entries 最小保护为 8，故插入 10 项验证）
c2 = ApiCache(ttl=100, max_entries=3)
for i in range(10):
    c2.set(f"k{i}", i)
entries = c2.stats()["entries"]
check("条目数受上限约束", entries <= 8, f"entries={entries}")
hit, _ = c2.get("k0")
check("超出上限淘汰最旧", not hit)
hit, v9 = c2.get("k9")
check("最新条目保留", hit and v9 == 9)

# invalidate 按子串
c3 = ApiCache(ttl=100)
c3.set("browse:4000:1:trend::", "a")
c3.set("browse:4000:2:trend::", "b")
c3.set("browse:718670:1:trend::", "x")
n = c3.invalidate("4000")
check("invalidate 按 appid 失效", n == 2 and not c3.get("browse:4000:1:trend::")[0]
      and c3.get("browse:718670:1:trend::")[0], f"n={n}")
c3.invalidate()
check("invalidate() 清空全部", c3.stats()["entries"] == 0)

# make_cache_key 维度隔离
k_a = make_cache_key("4000", 1, "trend", "", [], "schinese")
k_b = make_cache_key("4000", 2, "trend", "", [], "schinese")
k_c = make_cache_key("4000", 1, "mostsubscribed", "", [], "schinese")
check("不同页 key 不同", k_a != k_b)
check("不同排序 key 不同", k_a != k_c)

# ================================================================ 2. 请求合并
calls = {"n": 0}
lock = threading.Lock()

def slow_compute():
    with lock:
        calls["n"] += 1
    time.sleep(0.2)
    return "computed"

c4 = ApiCache(ttl=100)
results = []
threads = [threading.Thread(
    target=lambda: results.append(c4.get_or_compute("shared", slow_compute))
) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("并发相同 key 只计算一次", calls["n"] == 1, f"calls={calls['n']}")
check("合并结果一致", results == ["computed"] * 5, str(results[:2]))

# 命中后不再计算
c4.get_or_compute("shared", slow_compute)
check("缓存命中不重复计算", calls["n"] == 1, f"calls={calls['n']}")

# ================================================================ 3. 限流降级
c5 = ApiCache(ttl=100)
c5.set("dep_key", ["stale_data"])

def failing():
    raise RuntimeError("429 模拟")

# 有缓存时降级返回过期数据
r = c5.get_or_compute("dep_key", failing)
check("compute 失败时降级返回缓存", r == ["stale_data"], str(r))

# 无缓存时抛出
try:
    c5.get_or_compute("no_cache", failing, allow_expired_fallback=True)
    check("无缓存时抛出", False)
except RuntimeError:
    check("无缓存时抛出", True)

# ================================================================ 4. 全局单例
g1 = get_api_cache()
g2 = get_api_cache()
check("全局缓存单例", g1 is g2)

# ================================================================ 5. browse 集成（mock）
from swdm.core.steam_api import SteamAPI, RateLimitError, _throttle  # noqa: E402

api = SteamAPI.__new__(SteamAPI)   # 绕过 __init__（不联网）
api.timeout = 30
api._session = None

# mock _community_get：第一次返回卡片 HTML，之后计数
fetch_count = {"n": 0}
CARD_HTML = (
    '<div class="workshopItem">'
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111">'
    '<img src="https://steamusercontent.com/1.jpg" alt="Mod A"></a></div>'
    '<div class="workshopItem">'
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=222">'
    '<img src="https://steamusercontent.com/2.jpg" alt="Mod B"></a></div>'
)
api._community_get = lambda path, params, max_retries=4: CARD_HTML
# 包装计数
orig = api._community_get
def counting(path, params, max_retries=4):
    fetch_count["n"] += 1
    return orig(path, params, max_retries)
api._community_get = counting

# 清空全局缓存，避免互相干扰
get_api_cache().invalidate()

items1 = api.browse("4000", page=1)
check("browse 首次抓取返回 2 项", len(items1) == 2, str(len(items1)))
first_fetches = fetch_count["n"]

items2 = api.browse("4000", page=1)
check("同条件第二次命中缓存（零请求）",
      fetch_count["n"] == first_fetches, f"fetches={fetch_count['n']}")

# 深拷贝保护：修改返回值不污染缓存
items2[0].title = "POLLUTED"
items3 = api.browse("4000", page=1)
check("深拷贝保护：缓存未被污染",
      items3[0].title == "Mod A", items3[0].title)

# force_refresh 跳过缓存
before = fetch_count["n"]
api.browse("4000", page=1, force_refresh=True)
check("force_refresh 触发新请求", fetch_count["n"] > before,
      f"{before}->{fetch_count['n']}")

# 不同页不命中
before = fetch_count["n"]
api.browse("4000", page=2)
check("不同页号触发新请求", fetch_count["n"] > before)

# 限流降级：_community_get 抛 RateLimitError，browse 应回退缓存
api._community_get = lambda path, params, max_retries=4: (
    (_ for _ in ()).throw(RateLimitError(20))
)
fallback = api.browse("4000", page=1)
check("browse 限流时降级返回缓存", len(fallback) == 2, str(len(fallback)))

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
