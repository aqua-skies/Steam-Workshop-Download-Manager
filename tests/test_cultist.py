"""端到端测试：Cultist Simulator (718670) 热度排行第 3 的 mod。

完整链路：游戏注册表 -> 浏览（热度排序）-> 取第 3 项 -> 匿名下载 -> 入库 -> 分类检索。
用真实数据目录（%APPDATA%/SWDM），模拟安装后实际使用。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, ".")

import io as _io

from swdm.core import (  # noqa: E402
    AuthManager,
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
    WorkshopItem,
    get_config,
    setup_logger,
)
from swdm.core.games import add_custom, all_games, game_name  # noqa: E402
from swdm.core.logger import get_logger  # noqa: E402

setup_logger("INFO")
log = get_logger("swdm.cultist")

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

APPID = "718670"
TARGET_RANK = 3  # 热度排行第 3

# ------------------------------------------------------------------ 1. 游戏识别
ids = {g["appid"] for g in all_games()}
check("游戏已登记", APPID in ids, game_name(APPID))

cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()

check("匿名模式", auth.is_anonymous())

# ------------------------------------------------------------------ 2. 浏览（热度排序）
# actualsort=trend 即"最热"（按热度排行）
items = api.browse(APPID, page=1, sort="trend")
check("热度排行列表非空", len(items) >= TARGET_RANK, f"共 {len(items)} 个物品")
p("热度排行前 5：")
for i, it in enumerate(items[:5], 1):
    p(f"   #{i} {it.publishedfileid}  {it.title[:44]!r}  preview={'有' if it.preview_url else '无'}")

if len(items) < TARGET_RANK:
    p("!! 物品数不足，无法取第 3 名")
    p(out.getvalue())
    print("RESULT: HAS FAILURES")
    sys.exit(1)

target = items[TARGET_RANK - 1]
p(f"目标：热度第 {TARGET_RANK} 名 = {target.publishedfileid} {target.title!r}")

# ------------------------------------------------------------------ 3. 元数据补全
api.enrich([target])
check("元数据补全-订阅数", target.subscriptions > 0, f"subs={target.subscriptions}")
check("元数据补全-文件大小", target.file_size > 0, f"{target.file_size} bytes")
p(f"   详情: subs={target.subscriptions} size={target.file_size} "
  f"tags={target.tags[:4]} author={target.creator_name or target.creator}")

# ------------------------------------------------------------------ 4. 匿名下载
before = lib.stats()
engine = SteamCMDEngine(
    exe_path=cfg.get("steamcmd", "exe_path") or "",
    install_dir=cfg.get("steamcmd", "force_install_dir")
    or cfg.get("general", "library_dir") or None,
    anonymous=True,
)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=1)
events = {"started": 0, "finished": 0}
mgr.on_started = lambda j: events.__setitem__("started", events["started"] + 1)
mgr.on_finished = lambda j: events.__setitem__("finished", events["finished"] + 1)
mgr.start()
job = mgr.enqueue(target, APPID)
p(f"已入队：{job.id}（{target.title}）")
t0 = time.time()
while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 300:
    time.sleep(1)
grace = time.time() + 5
while events["finished"] < 1 and time.time() < grace:
    time.sleep(0.2)
mgr.stop()

check("匿名下载成功", job.status.value == "success",
      f"status={job.status.value} bytes={job.bytes_done}")
check("下载回调触发", events["started"] >= 1 and events["finished"] >= 1, str(events))

# ------------------------------------------------------------------ 5. 入库与管理
if job.status.value == "success":
    rec = lib.get(target.publishedfileid)
    check("已入库", rec is not None)
    if rec:
        check("本地文件存在", os.path.isdir(rec.local_path), rec.local_path)
        check("元数据旁车", os.path.exists(os.path.join(rec.local_path, "swdm_meta.json")))
        check("标题已记录", rec.title == target.title, repr(rec.title))
        # 分类 / 检索 / 启用禁用
        lib.set_category(rec.item_id, "热度推荐")
        check("按分类检索", any(r.item_id == rec.item_id for r in lib.search(category="热度推荐")))
        check("关键词检索", len(lib.search(keyword=target.title[:6])) >= 1)
        lib.set_enabled(rec.item_id, False)
        check("禁用生效", any(r.item_id == rec.item_id for r in lib.search(disabled_only=True)))
        lib.set_enabled(rec.item_id, True)
        check("重新启用", any(r.item_id == rec.item_id for r in lib.search(enabled_only=True)))
        # 按游戏检索
        check("按游戏检索", len(lib.search(appid=APPID)) >= 1)

after = lib.stats()
p(f"库统计变化: {before} -> {after}")
check("库中新增记录", after["total"] == before["total"] + 1,
      f"+{after['total'] - before['total']}")

result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cultist_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
