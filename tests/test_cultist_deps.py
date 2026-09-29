"""Cultist Simulator（718670）依赖功能实测。

目标 mod：3801750928「【哀殛魅影】蔑世使徒 - 子模组」——子模组通常依赖主模组。
完整链路：解析前置依赖 -> 弹窗确认（模拟）-> 依赖优先下载 -> 入库 -> 依赖关系记录。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_cultist_deps_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

setup_logger("INFO")
ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

APPID = "718670"
ROOT_ID = "3801750928"   # 【哀殛魅影】蔑世使徒 - 子模组
ROOT_TITLE = "【哀殛魅影】蔑世使徒 - 子模组"

cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)

check("零账号匿名模式", auth.is_anonymous())
check("无任何凭据", auth.get_credentials() == ("", "", ""))

p("---- 第 1 步：解析前置依赖 ----")
root = WorkshopItem(publishedfileid=ROOT_ID, appid=APPID, title=ROOT_TITLE)
try:
    deps, skipped = api.resolve_dependency_tree(root, max_depth=10,
                                               skip_installed=True)
except Exception as e:  # noqa: BLE001
    p(f"  解析异常: {type(e).__name__}: {e}")
    deps, skipped = [], []

p(f"  解析到 {len(deps)} 个依赖:")
for d in deps:
    p(f"    {d.publishedfileid} {d.title[:40]!r}")

if deps:
    check("子模组存在前置依赖", len(deps) >= 1)
    check("依赖带标题", all(d.title for d in deps))
    # 模拟 GUI 弹窗确认逻辑（这里自动选「是」）
    p("  [GUI 模拟] 弹窗「是否一并下载？」-> 选「是」")
else:
    p("  该 mod 无前置依赖（Steam 侧未声明）")

p("---- 第 2 步：依赖优先入队并下载 ----")
mgr.start()
# 把解析到的依赖写回根物品，供入库时记录依赖关系（与 GUI 路径一致）
root.dependencies = [d.publishedfileid for d in deps]
jobs = []
for d in deps:
    jobs.append(mgr.enqueue(d, d.appid or APPID))
jobs.append(mgr.enqueue(root, APPID))
p(f"  入队 {len(jobs)} 个，顺序: {[j.id for j in jobs]}")
check("依赖在根 mod 之前入队",
      [j.id for j in jobs][:-1] == [d.publishedfileid for d in deps])

deadline = time.time() + 600
while time.time() < deadline:
    with mgr._lock:
        pending = [j for j in jobs
                   if j.status.value not in ("success", "failed", "cancelled")]
    if not pending:
        break
    time.sleep(2)

p("  下载结果:")
for j in jobs:
    p(f"    {j.id} ({j.item.title[:30]!r}): {j.status.value} {j.bytes_done} bytes")

succeeded = {j.id for j in jobs if j.status.value == "success"}
check("根 mod 下载成功", ROOT_ID in succeeded)
for d in deps:
    check(f"依赖 {d.publishedfileid} 下载成功", d.publishedfileid in succeeded)

p("---- 第 3 步：入库与分类检索 ----")
mgr.stop()
stats = lib.stats()
p(f"  库统计: {stats}")
check("下载数与入库数一致",
      stats["total"] == len(jobs), f"{stats['total']} vs {len(jobs)}")

rec = lib.get(ROOT_ID)
check("根 mod 已入库", rec is not None and rec.installed)
if rec:
    check("根 mod 可关键词检索", len(lib.search(keyword="哀殛")) >= 1)
    lib.set_category(ROOT_ID, "Cultist 子模组")
    check("根 mod 可分类检索",
          any(r.item_id == ROOT_ID for r in lib.search(category="Cultist 子模组")))
    if deps:
        check("根 mod 记录了依赖",
              set(rec.dependencies) == {d.publishedfileid for d in deps},
              str(rec.dependencies))

for d in deps:
    dr = lib.get(d.publishedfileid)
    check(f"依赖 {d.publishedfileid} 已入库", dr is not None and dr.installed)

# 元数据旁车
if rec and rec.local_path:
    check("元数据旁车存在",
          os.path.exists(os.path.join(rec.local_path, "swdm_meta.json")))

result = "\n".join(out.getvalue().splitlines())
print(result)
rf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cultist_deps.txt")
with open(rf, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
