"""多游戏完整链路测试：浏览 → 元数据 → 匿名下载 → 入库 → 分类检索 → 管理。

对多款不同游戏逐一跑完整链路，验证不是只对 GMod 特例可用。
每款游戏：浏览列表 → 搜索 → 取最小 mod → 匿名下载 → 入库 → 分类/标签/启禁用/清单。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

# 独立数据目录，必须先于 swdm 导入设置
_TMP = tempfile.mkdtemp(prefix="swdm_multi_")
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

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

setup_logger("INFO")
ensure_dirs()
log = get_logger("swdm.multi")
log.info("==== 多游戏完整链路测试（数据目录 %s） ====", DATA_DIR)

cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()

# 测试游戏：覆盖不同规模与类型
#   4000  Garry's Mod   经典页 SSR，稳定
#   252490 Rust         新 hub 页：经典页 0 卡片，走内联数据回退
#   304930 Unturned     免费游戏
#   322330 DST-beta     主版本 258130 浏览页在 Steam 侧为空，beta 正常
#   107410 Arma 3       付费且工坊需许可：预期匿名下载失败，验证程序正确报告失败
GAMES = [
    ("4000", "Garry's Mod"),
    ("252490", "Rust"),
    ("304930", "Unturned"),
    ("322330", "DST-beta"),
    ("107410", "Arma 3"),
]
# 匿名下载预期失败的游戏（工坊内容需要拥有游戏的许可）
DOWNLOAD_EXPECTED_FAIL = {"107410"}

check("零账号: 默认匿名", auth.is_anonymous())
check("零账号: 无保存凭据", auth.get_credentials() == ("", "", ""))

per_game: dict[str, dict] = {}

for appid, gname in GAMES:
    log.info("---- %s (%s) ----", gname, appid)
    g = {"browse": 0, "enrich": 0, "download": None, "library": False}
    try:
        items = api.browse(appid, page=1)
    except Exception as e:  # noqa: BLE001
        p(f"   [WARN] {gname} 浏览异常: {e}")
        items = []
    g["browse"] = len(items)
    check(f"{gname}: 浏览列表", len(items) > 0, f"得到 {len(items)} 个物品")

    if items:
        # 元数据补全
        try:
            api.enrich(items[:5])
        except Exception as e:  # noqa: BLE001
            p(f"   [WARN] {gname} 补全异常: {e}")
        enriched = sum(1 for i in items[:5] if i.subscriptions > 0 or i.file_size > 0)
        g["enrich"] = enriched
        check(f"{gname}: 元数据补全", enriched > 0, f"{enriched}/5 有数据")

        # 搜索（该游戏内关键词）
        try:
            searched = api.browse(appid, search_text=items[0].title.split()[0] if items[0].title.split() else "a")
        except Exception as e:  # noqa: BLE001
            searched = []
        check(f"{gname}: 搜索接口可用", isinstance(searched, list))

        # 选最小的 mod 下载（控制时长）
        cand = [i for i in items[:8] if i.file_size and 0 < i.file_size < 100 * 1024 * 1024]
        small = min(cand, key=lambda i: i.file_size) if cand else items[0]
        p(f"   选中: {small.publishedfileid} {small.title!r} ({small.file_size} bytes)")

        engine = SteamCMDEngine(anonymous=True)
        mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=1)
        events = {"finished": 0}
        mgr.on_finished = lambda j: events.__setitem__("finished", events["finished"] + 1)
        mgr.start()
        job = mgr.enqueue(small, appid)
        t0 = time.time()
        while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 240:
            time.sleep(1)
        grace = time.time() + 5
        while events["finished"] < 1 and time.time() < grace:
            time.sleep(0.2)
        mgr.stop()
        g["download"] = job.status.value

        expect_fail = appid in DOWNLOAD_EXPECTED_FAIL
        if expect_fail:
            # 该游戏工坊内容需要拥有游戏的许可：匿名下载应失败且给出可读信息
            check(f"{gname}: 匿名下载被正确拒绝", job.status.value == "failed",
                  f"status={job.status.value} msg={job.message}")
        else:
            check(f"{gname}: 匿名下载", job.status.value == "success",
                  f"status={job.status.value} bytes={job.bytes_done}")

        if job.status.value == "success":
            rec = lib.get(small.publishedfileid)
            check(f"{gname}: 已入库", rec is not None)
            if rec:
                check(f"{gname}: 本地文件存在", os.path.isdir(rec.local_path), rec.local_path)
                check(f"{gname}: 元数据旁车", os.path.exists(os.path.join(rec.local_path, "swdm_meta.json")))
                # 管理操作
                lib.set_category(small.publishedfileid, f"{gname}分类")
                found_cat = lib.search(category=f"{gname}分类")
                check(f"{gname}: 按分类检索", any(r.item_id == small.publishedfileid for r in found_cat))
                lib.set_enabled(small.publishedfileid, False)
                check(f"{gname}: 禁用生效", len(lib.search(disabled_only=True)) >= 1)
                lib.set_enabled(small.publishedfileid, True)
                check(f"{gname}: 重新启用", len(lib.search(enabled_only=True)) >= 1)
                g["library"] = True
    per_game[appid] = g
    p(f"   汇总 {gname}: {json.dumps(g, ensure_ascii=False)}")

# ------------------------------------------------------------------ 清单导出/导入
all_recs = lib.search()
export_path = os.path.join(DATA_DIR, "multi_export.json")
export_data = [r.to_dict() for r in all_recs]
with open(export_path, "w", encoding="utf-8") as f:
    json.dump(export_data, f, ensure_ascii=False, indent=2)
check("清单导出有效", os.path.exists(export_path) and len(export_data) == len(all_recs),
      f"{len(export_data)} 条")

from swdm.core.mod_library import ModRecord  # noqa: E402

with open(export_path, "r", encoding="utf-8") as f:
    import_data = json.load(f)
n_before = lib.stats()["total"]
restored = 0
for d in import_data:
    try:
        rec = ModRecord(
            item_id=str(d["item_id"]),
            appid=str(d.get("appid", "")),
            title=d.get("title", ""),
            description=d.get("description", ""),
            creator=d.get("creator", ""),
            creator_name=d.get("creator_name", ""),
            file_size=int(d.get("file_size", 0) or 0),
            subscriptions=int(d.get("subscriptions", 0) or 0),
            tags=d.get("tags", []),
            preview_url=d.get("preview_url", ""),
            local_path=d.get("local_path", ""),
            installed=bool(d.get("installed", False)),
            enabled=bool(d.get("enabled", True)),
            category=d.get("category", ""),
            notes=d.get("notes", ""),
            favorite=bool(d.get("favorite", False)),
            download_time=int(d.get("download_time", 0) or 0),
            time_updated=int(d.get("time_updated", 0) or 0),
            source=d.get("source", "imported"),
        )
        lib.upsert(rec)
        restored += 1
    except (KeyError, TypeError) as e:
        p(f"   [WARN] 跳过无效记录: {e}")
check("清单导入无损", restored == len(import_data) and lib.stats()["total"] == n_before,
      f"导入 {restored} 条，库总数 {lib.stats()['total']}")

# ------------------------------------------------------------------ 统计
stats = lib.stats()
p(f"最终库统计: {json.dumps(stats, ensure_ascii=False)}")
dl_ok = [g for g in per_game.values() if g.get("download") == "success"]
dl_expected_fail = [a for a, g in per_game.items()
                    if g.get("download") == "failed" and a in DOWNLOAD_EXPECTED_FAIL]
p(f"下载成功: {len(dl_ok)}/{len(GAMES)}（另有 {len(dl_expected_fail)} 个按预期被拒绝）")
p("")
p("=== 各游戏明细 ===")
for appid, g in per_game.items():
    p(f"  {appid:>7}: browse={g['browse']:>3} enrich={g['enrich']} "
      f"dl={g['download']} library={g['library']}")

result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_multi_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

try:
    shutil.rmtree(_TMP, ignore_errors=True)
except OSError:
    pass
sys.exit(0 if ok else 1)
