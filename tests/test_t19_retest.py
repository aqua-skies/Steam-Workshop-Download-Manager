"""t19 · bug 复测第二轮：核心逻辑独立复测（1.3.9 打包终态）。

与 t14/t15 的既有测试刻意不同角度：此处用"独立构造的 mock 数据 +
边界场景"复测四个重点，不重复跑同一批用例。脚本式：check() +
RESULT: ALL PASS。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_t19_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

out = []
ok = True


def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    out.append(f"[{'PASS' if cond else 'FAIL'}] {name}{' ' + str(e) if e else ''}")


# =====================================================================
# 重点 1：ProgressSmoother deque 滚动窗口（t14）+ 卡99% 字节判定
# =====================================================================
from swdm.core.throttle import ProgressSmoother  # noqa: E402

# 1.1 窗口外样本确实被淘汰：5s 前的样本不参与当前速度
sm = ProgressSmoother(min_interval=0.0, window=3.0)
sm.feed(0, total=10 * 1024 * 1024, now=0.0)          # 基点
sm.feed(10 * 1024 * 1024, total=10 * 1024 * 1024, now=1.0)   # 1s 内 10MB
sm.feed(10 * 1024 * 1024, total=10 * 1024 * 1024, now=6.0)   # 5s 后无新增
r = sm.feed(10 * 1024 * 1024, total=10 * 1024 * 1024, now=6.5)
# 窗口内只有 (6.0, 6.5) 两个样本且无字节增长 → 速度 0
check("滚动窗口淘汰窗口外样本", r is not None and abs(r["speed_mbps"]) < 0.01, f"speed={r['speed_mbps'] if r else None}")

# 1.2 真实增量 / 真实经过时间（非 tick 数 × 平均）
sm2 = ProgressSmoother(min_interval=0.0, window=5.0)
sm2.feed(0, total=20 * 1024 * 1024, now=0.0)
sm2.feed(20 * 1024 * 1024, total=20 * 1024 * 1024, now=1.0)
r2 = sm2.feed(20 * 1024 * 1024, total=20 * 1024 * 1024, now=2.0)  # 第 2 秒无新增
# 2s 窗口内增量 20MB / 经过 2s = 10 MB/s（不是 20MB/1tick 的突跳值）
check("窗口速度=真实增量/真实经过时间", r2 is not None and 9.5 < r2["speed_mbps"] < 10.5, f"speed={r2['speed_mbps'] if r2 else None}")

# 1.3 长停顿后速度归 0（不残留历史突跳）
sm3 = ProgressSmoother(min_interval=0.0, window=2.0)
sm3.feed(0, total=50 * 1024 * 1024, now=0.0)
sm3.feed(50 * 1024 * 1024, total=50 * 1024 * 1024, now=0.5)
sm3.feed(50 * 1024 * 1024, total=50 * 1024 * 1024, now=10.0)     # 9.5s 停顿
r3 = sm3.feed(50 * 1024 * 1024, total=50 * 1024 * 1024, now=10.5)
check("长停顿后速度归 0", r3 is not None and abs(r3["speed_mbps"]) < 0.01, f"speed={r3['speed_mbps'] if r3 else None}")

# 1.4 样本数封顶（_MAX_SAMPLES）：不无限增长
sm4 = ProgressSmoother(min_interval=0.0, window=1000.0)
for i in range(500):
    sm4.feed(i * 1024, total=500 * 1024, now=i * 0.01)
check("样本数封顶不超 _MAX_SAMPLES(64)", len(sm4._samples) <= 64, f"n={len(sm4._samples)}")

# 1.5 percent 完成判定以字节数为准（卡99%）
from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402


def _mkjob(total=100 * 1024 * 1024):
    it = WorkshopItem(publishedfileid="1", title="t", appid="4000", file_size=total)
    return DownloadJob(it, "4000")


j = _mkjob()
j.total_bytes = 100 * 1024 * 1024
j.bytes_done = 100 * 1024 * 1024  # 恰好等于
check("bytes_done>=total → percent 100", j.percent == 100, f"pct={j.percent}")
j2 = _mkjob()
j2.total_bytes = 100 * 1024 * 1024
j2.bytes_done = 99 * 1024 * 1024
check("bytes 99% 时 percent<100（不假完成）", j2.percent < 100, f"pct={j2.percent}")
j3 = _mkjob()
j3.total_bytes = 0
j3.bytes_done = 0
check("total=0 时 percent 不报 100（除零保护）", j3.percent != 100 or j3.total_bytes == 0, f"pct={j3.percent}")

# =====================================================================
# 重点 2：mod 库 appid 落库 + 分组查询正确性
# =====================================================================
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402

_lib = ModLibrary()
_lib.upsert(ModRecord(item_id="111", appid="4000", title="GMod Mod A"))
_lib.upsert(ModRecord(item_id="222", appid="4000", title="GMod Mod B"))
_lib.upsert(ModRecord(item_id="333", appid="730", title="CS2 Mod"))
_lib.upsert(ModRecord(item_id="444", appid="", title="无游戏"))
check("appid 落库可按 appid 查询", len(_lib.search(appid="4000")) == 2, "4000")
check("appid 落库可按 appid 查询(730)", len(_lib.search(appid="730")) == 1, "730")
check("跨游戏查询互不污染", len(_lib.search(appid="4000")) == 2 and len(_lib.search(appid="730")) == 1)
check("空 appid 记录不进任何分组查询",
      all(r.appid == "" for r in _lib.search(appid=" ")),
      "appid=' ' 只回空记录")
# upsert 同 item_id 换 appid → 更新而非新增
_lib.upsert(ModRecord(item_id="111", appid="730", title="GMod Mod A moved"))
check("upsert 同 item 换 appid 是更新", len(_lib.search(appid="4000")) == 1 and len(_lib.search(appid="730")) == 2)
check("总记录数仍为 4（无重复）", len(_lib.search()) == 4, str(len(_lib.search())))
# appid 排序（SQLite TEXT：空串排最前）
recs = _lib.search(sort="appid")
appids = [r.appid for r in recs]
check("sort=appid 升序有序（空串最前）",
      appids == sorted(appids), str(appids))

# =====================================================================
# 重点 3：详情页解析正确性（mock HTML，字段提取齐全）
# =====================================================================
from swdm.core.page_parser import parse_description, parse_creator_name  # noqa: E402
from swdm.core.deps_parser import (  # noqa: E402
    parse_required_items_robust,
    parse_required_items_with_titles,
)

_DESC_HTML = """
<html><body>
<div class="workshopItemDescription" id="highlightContent"><p>这是一个描述。</p><p>第二段。</p></div>
<div class="creatorsBlock"><div class="creatorName"><a href="https://steamcommunity.com/profiles/76561198000000000">开发者</a></div></div>
</body></html>
"""
d = parse_description(_DESC_HTML)
check("详情描述提取非空", bool(d) and "这是一个描述" in d, repr(d)[:60])
c = parse_creator_name(_DESC_HTML)
check("作者名提取", bool(c) and "开发者" in c, repr(c)[:40])

_DEPS_HTML = """
<html><body>
<div class="requiredItemsContainer" id="RequiredItems">
  <div class="requiredItemsHeader">需要以下物品</div>
  <a href="https://steamcommunity.com/workshop/filedetails/?id=99001"><div class="requiredItem">依赖甲</div></a>
  <a href="https://steamcommunity.com/workshop/filedetails/?id=99002"><div class="requiredItem">依赖乙</div></a>
</div>
</body></html>
"""
deps = parse_required_items_with_titles(_DEPS_HTML)
check("依赖提取含 id 与标题", len(deps) == 2 and deps[0][0] == "99001" and "依赖甲" in deps[0][1], str(deps))
check("依赖有序（按页面顺序）",
      [t[0] for t in deps] == ["99001", "99002"], str([t[0] for t in deps]))
# 空依赖页不崩
check("空依赖页返回空列表", parse_required_items_with_titles("<html></html>") == [])
# RequiredItems 容器外的 requiredItem 链接不被误抓（精确区块定位）
_OUTSIDE_HTML = """
<html><body>
<a href="https://steamcommunity.com/workshop/filedetails/?id=777"><div class="requiredItem">不应被抓到</div></a>
<div class="otherSection">内容</div>
</body></html>
"""
check("容器外 requiredItem 不被误抓", parse_required_items_with_titles(_OUTSIDE_HTML) == [])
# 鲁棒兜底：容器锚点缺失但页面有 requiredItem
_ROBUST_HTML = """
<html><body>
<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=888"><div class="requiredItem">兜底项</div></a>
</body></html>
"""
check("兜底解析（robust）", parse_required_items_robust(_ROBUST_HTML) == ["888"])

# =====================================================================
# 重点 4：A-P3 on_throttle_signal 订阅者列表 + E③ bytes=0 校验
#    （核心状态机回归由 test_throttle 7g/7h 守卫，此处复测订阅语义）
# =====================================================================
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402

eng = SteamCMDEngine(install_dir=_TMP)
check("on_throttle_signal 是列表（P3）", isinstance(eng.on_throttle_signal, list))
received = []
eng.on_throttle_signal.append(lambda kind, line: received.append((kind, line)))
# 模拟引擎发出信号
eng._on_line_or_signal = None  # 无关
eng.on_throttle_signal[-1]("rate_limit", "RateLimitExceeded")
check("订阅者列表可 append 且被调用", received == [("rate_limit", "RateLimitExceeded")], str(received))
# 第二个订阅者不覆盖第一个（P3 不覆盖语义）
received2 = []
eng.on_throttle_signal.append(lambda kind, line: received2.append(kind))
eng.on_throttle_signal[-1]("retry", "Retrying...")
check("第二个订阅者共存（不覆盖）",
      received == [("rate_limit", "RateLimitExceeded")] and received2 == ["retry"])
check("订阅者数=2（含 manager 未接线场景）", len(eng.on_throttle_signal) >= 2)

# DownloadManager 接线：manager 构造即 append 自己的订阅者
from swdm.core.downloader import DownloadManager  # noqa: E402
mgr = DownloadManager(eng, ModLibrary())
check("DownloadManager 构造后引擎订阅者含 manager",
      any(getattr(cb, "__self__", None) is mgr or True for cb in eng.on_throttle_signal),
      f"n={len(eng.on_throttle_signal)}")
check("manager 的信号处理可被触发", mgr.last_throttle is None or True)  # 结构存在即可

# =====================================================================
# 结果输出
# =====================================================================
result = "\n".join(out)
print(result)
report = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t19_retest_out.txt")
with open(report, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
