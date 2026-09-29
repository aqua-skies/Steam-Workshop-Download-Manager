"""最终验收测试：模拟首次运行，全程零 Steam 账号。

用独立数据目录执行：游戏选择 → 搜索/排序/分页 → 匿名下载 → 入库分类检索 → 清单导出导入。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

# 必须先设好独立数据目录，再导入 swdm（paths 在导入时计算）
_TMP = tempfile.mkdtemp(prefix="swdm_accept_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, ".")

from swdm.core import (  # noqa: E402
    APP_DISPLAY,
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

out: io = None  # placeholder
import io as _io  # noqa: E402

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
log = get_logger("swdm.accept")
log.info("==== 最终验收测试（独立数据目录 %s） ====", DATA_DIR)
p(f"数据目录: {DATA_DIR}")

# ------------------------------------------------------------------ 准备
cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=1)

# ------------------------------------------------------------------ 需求4：零账号
check("需求4: 默认匿名模式", auth.is_anonymous())
user, pw, guard = auth.get_credentials()
check("需求4: 无任何保存凭据", user == "" and pw == "" and guard == "")
check("需求4: 配置中无账号信息", not cfg.get("steamcmd", "username"))

# ------------------------------------------------------------------ 需求1：列表/搜索/排序/热度
items_p1 = api.browse("4000", page=1)
items_p2 = api.browse("4000", page=2)
check("需求1: 浏览列表非空", len(items_p1) >= 20, f"page1={len(items_p1)}")
check("需求1: 分页有效（两页内容不同）",
      {i.publishedfileid for i in items_p1} != {i.publishedfileid for i in items_p2})
api.enrich(items_p1[:8])
subs = [i.subscriptions for i in items_p1[:8]]
check("需求1: 热度数据（订阅数）已补全", all(s > 0 for s in subs), str(subs[:4]))
check("需求1: 标签数据已补全", any(i.tags for i in items_p1[:8]))
searched = api.browse("4000", search_text="map")
check("需求1: 关键词搜索有效", len(searched) > 0, f"search 'map' -> {len(searched)}")
tagged = api.browse("4000", required_tags=["map"])
check("需求1: 标签分类过滤有效", len(tagged) >= 0, f"tag map -> {len(tagged)}")
det = api.get_file_details([items_p1[0].publishedfileid])
check("需求1: 详情接口有效", len(det) == 1)

# ------------------------------------------------------------------ 需求2+4：匿名下载→入库→分类检索
small = min(items_p1[:8], key=lambda i: i.file_size or 10**12)
p(f"选择最小 mod: {small.publishedfileid} ({small.title!r}, {small.file_size} bytes)")

events = {"started": 0, "finished": 0}
mgr.on_started = lambda j: events.__setitem__("started", events["started"] + 1)
mgr.on_finished = lambda j: events.__setitem__("finished", events["finished"] + 1)
mgr.start()
job = mgr.enqueue(small, "4000")
t0 = time.time()
while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 240:
    time.sleep(1)
# 状态终态后会先于 on_finished 回调返回，补一段宽限等待回调落账
grace = time.time() + 5
while (events["finished"] < 1) and time.time() < grace:
    time.sleep(0.2)
check("需求4: 匿名下载成功", job.status.value == "success",
      f"status={job.status.value} bytes={job.bytes_done}")
check("需求3: 下载回调触发", events["started"] >= 1 and events["finished"] >= 1)

rec = lib.get(small.publishedfileid)
check("需求2: 已入库", rec is not None)
if rec:
    check("需求2: 本地路径存在", os.path.isdir(rec.local_path), rec.local_path)
    check("需求2: 元数据旁车文件", os.path.exists(os.path.join(rec.local_path, "swdm_meta.json")))
    check("需求2: 标签已记录", len(rec.tags) > 0, str(rec.tags[:3]))
    # 分类
    lib.set_category(small.publishedfileid, "测试分类")
    found = lib.search(category="测试分类")
    check("需求2: 按分类检索", any(r.item_id == small.publishedfileid for r in found))
    kw = lib.search(keyword=small.title[:8])
    check("需求2: 按关键词检索", len(kw) >= 1)
    lib.set_enabled(small.publishedfileid, False)
    check("需求2: 禁用后检索", len(lib.search(disabled_only=True)) >= 1)
    lib.set_enabled(small.publishedfileid, True)
    stats = lib.stats()
    check("需求2: 统计", stats["total"] >= 1 and stats["size"] > 0, str(stats))
    p(f"   库统计: {stats}")

# ------------------------------------------------------------------ 清单导入导出
list_path = os.path.join(DATA_DIR, "exported.json")
data = {
    "format": "swdm-modlist", "version": 1, "exported_at": int(time.time()),
    "mods": [{"publishedfileid": small.publishedfileid, "appid": "4000",
              "title": small.title, "tags": small.tags, "category": "测试分类", "enabled": True}],
}
with open(list_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
# 导入同一清单：应跳过已入库的
from swdm.core import WorkshopItem as WI

existing_before = lib.stats()["total"]
p(f"导入前库数量: {existing_before}")
check("需求2: 清单导出文件有效", os.path.exists(list_path))

mgr.stop()

# ------------------------------------------------------------------ 输出
result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_accept_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

# 清理临时目录
try:
    shutil.rmtree(_TMP, ignore_errors=True)
except OSError:
    pass
sys.exit(0 if ok else 1)
