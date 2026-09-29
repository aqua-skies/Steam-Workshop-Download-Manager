"""批量多游戏导入下载测试：15 款不同 Steam 游戏。

每款游戏执行完整链路：浏览列表 -> 选最小 mod -> 匿名下载 -> 入库 -> 元数据。
失败项记录真实原因（空工坊页 / 需游戏许可 / 物品不存在），不做掩盖。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

# 独立数据目录，必须先于 swdm 设置
_TMP = tempfile.mkdtemp(prefix="swdm_bulk_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, ".")

import io as _io  # noqa: E402

from swdm.core import (  # noqa: E402
    AuthManager,
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
    WorkshopItem,
    ensure_dirs,
    get_config,
    setup_logger,
)
from swdm.core.logger import get_logger  # noqa: E402
from swdm.core.paths import DATA_DIR  # noqa: E402

setup_logger("WARNING")  # 批量测试降噪
ensure_dirs()
log = get_logger("swdm.bulk")

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# ------------------------------------------------------------------ 候选游戏
GAMES = [
    ("4000", "Garry's Mod"),
    ("550", "Left 4 Dead 2"),
    ("440", "Team Fortress 2"),
    ("240", "Counter-Strike: Source"),
    ("252490", "Rust"),
    ("304930", "Unturned"),
    ("322330", "DST Beta"),
    ("718670", "Cultist Simulator"),
    ("221100", "DayZ"),
    ("108600", "Project Zomboid"),
    ("242760", "The Forest"),
    ("1250", "Killing Floor"),
    ("255710", "Cities: Skylines"),
    ("1063730", "Tabletop Simulator"),
    ("8930", "Civilization V"),
]

p(f"==== 批量多游戏测试（{len(GAMES)} 款，数据目录 {DATA_DIR}） ====")

cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)

check("零账号匿名模式", auth.is_anonymous())
check("无任何凭据", auth.get_credentials() == ("", "", ""))

mgr.start()
results: list[dict] = []

# 游戏之间的冷却：Steam 社区按 IP 配额限流，连续请求易触发 429。
# 每款游戏后等待一段时间，让配额恢复（真实使用中用户不会连续刷 15 款游戏）。
COOLDOWN = 8.0

for idx, (appid, gname) in enumerate(GAMES):
    if idx > 0:
        time.sleep(COOLDOWN)
    r = {"appid": appid, "name": gname, "browse": 0, "item": "",
         "download": "skipped", "bytes": 0, "library": False, "note": ""}
    log.info("---- %s (%s) ----", gname, appid)
    items = []
    # 限流补偿：最多三轮，每轮失败后等待配额窗口恢复
    for attempt in range(3):
        try:
            items = api.browse(appid, page=1)
            break
        except Exception as e:  # noqa: BLE001
            from swdm.core import RateLimitError

            if isinstance(e, RateLimitError) and attempt < 2:
                p(f"   [WARN] {gname}: 限流，第 {attempt+1} 次等待 "
                  f"{e.retry_after:.0f}s 后重试")
                time.sleep(e.retry_after)
                continue
            r["note"] = f"浏览异常: {type(e).__name__}: {e}"
            p(f"   [WARN] {gname}: {r['note']}")
            break
    if not items and not r["note"]:
        r["note"] = "工坊浏览页为空（Steam 侧无 SSR 内容）"

    r["browse"] = len(items)
    if not items:
        if not r["note"]:
            r["note"] = "工坊浏览页为空（Steam 侧无 SSR 内容）"
        p(f"   [--] {gname}: {r['note']}")
        results.append(r)
        continue

    # 取最小的 mod（控制下载时长）
    cand = [i for i in items if i.file_size and 0 < i.file_size < 200 * 1024 * 1024]
    if not cand:
        # 无文件大小的（新 hub 页未带 size），直接取第 1 个
        cand = items[:1]
    small = min(cand, key=lambda i: i.file_size or 0)
    r["item"] = small.publishedfileid
    p(f"   {gname}: 浏览 {len(items)} 项，选中 {small.publishedfileid} "
      f"{small.title[:34]!r} ({small.file_size} bytes)")

    # 匿名下载
    job = mgr.enqueue(small, appid)
    t0 = time.time()
    while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 240:
        time.sleep(1)
    grace = time.time() + 4
    while grace > time.time() and job.status.value not in ("success", "failed", "cancelled"):
        time.sleep(0.3)
    r["download"] = job.status.value
    r["bytes"] = job.bytes_done

    if job.status.value == "success":
        rec = lib.get(small.publishedfileid)
        if rec and os.path.isdir(rec.local_path):
            r["library"] = True
            r["note"] = f"已入库：{rec.local_path}"
        else:
            r["note"] = "下载成功但入库失败"
    else:
        r["note"] = f"匿名下载被拒绝：{job.message[:80]}"

    results.append(r)

mgr.stop()

# ------------------------------------------------------------------ 汇总
p("")
p("==== 汇总 ====")
p(f"{'游戏':<24} {'浏览':>4} {'下载':>8} {'字节':>10} {'入库':>5}  说明")
p("-" * 100)
dl_ok = 0
for r in results:
    p(f"{r['name'][:22]:<24} {r['browse']:>4} {r['download']:>8} "
      f"{r['bytes']:>10} {'是' if r['library'] else '否':>5}  {r['note'][:44]}")
    if r["download"] == "success":
        dl_ok += 1

stats = lib.stats()
p("")
p(f"下载成功：{dl_ok}/{len(GAMES)} 款游戏")
p(f"库统计：共 {stats['total']} 个 mod，{stats['games']} 款游戏，"
  f"{stats['size'] / 1024 / 1024:.1f} MB")

check("至少 10 款游戏成功下载", dl_ok >= 10, f"实际 {dl_ok}")
check("入库数量与下载数一致",
      stats["total"] == dl_ok, f"库 {stats['total']} vs 下载成功 {dl_ok}")

result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bulk_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

try:
    shutil.rmtree(_TMP, ignore_errors=True)
except OSError:
    pass
sys.exit(0 if ok else 1)
