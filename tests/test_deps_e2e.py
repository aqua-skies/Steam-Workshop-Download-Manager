"""端到端依赖下载测试：真实有依赖的 GMod mod 3805232163
（依赖 VJ Base 131759821 + [F76] SheepSquatch 2161380206）。

验证：解析依赖 -> 入队（依赖在前）-> 全部匿名下载成功 -> 入库。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_deps_e2e_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from swdm.core import (  # noqa: E402
    AuthManager,
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
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

# 已知有依赖的物品（真实页面验证过）
ROOT_ID = "3805232163"
EXPECTED_DEPS = {"131759821", "2161380206"}

cfg = get_config()
auth = AuthManager()
api = SteamAPI(api_key=cfg.get("network", "api_key") or "")
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)

check("零账号匿名模式", auth.is_anonymous())

p("---- 第 1 步：解析依赖 ----")
root = __import__("swdm.core", fromlist=["WorkshopItem"]).WorkshopItem(
    publishedfileid=ROOT_ID, appid="4000"
)
try:
    deps, skipped = api.resolve_dependency_tree(root, max_depth=10, skip_installed=True)
except Exception as e:  # noqa: BLE001
    p(f"解析异常（可能限流）: {e}")
    deps, skipped = [], []

dep_ids = {d.publishedfileid for d in deps}
p(f"  解析到 {len(deps)} 个依赖: {[d.publishedfileid for d in deps]}")
p(f"  依赖标题: {[(d.publishedfileid, d.title[:30]) for d in deps]}")
# 直接依赖（第 1 层）必须包含 VJ Base 与 SheepSquatch
check("包含预期直接依赖", EXPECTED_DEPS.issubset(dep_ids), str(dep_ids))
check("依赖带标题", all(d.title for d in deps),
      str([d.title[:20] for d in deps]))

p("---- 第 2 步：依赖优先入队并下载 ----")
mgr.start()
# 用第 1 步已解析的依赖直接入队（命中缓存，不再重复抓页面）
jobs = []
for d in deps:
    jobs.append(mgr.enqueue(d, d.appid or "4000"))
jobs.append(mgr.enqueue(root, "4000"))
job_ids = [j.id for j in jobs]
p(f"  入队 {len(jobs)} 个: {job_ids}")

# 等待全部完成
deadline = time.time() + 600
while time.time() < deadline:
    with mgr._lock:
        pending = [j for j in jobs if j.status.value not in ("success", "failed", "cancelled")]
    if not pending:
        break
    time.sleep(2)

p("  下载结果:")
for j in jobs:
    p(f"    {j.id} ({j.item.title[:28]!r}): {j.status.value} {j.bytes_done} bytes")

succeeded = {j.id for j in jobs if j.status.value == "success"}
check("根 mod 下载成功", ROOT_ID in succeeded)
check("VJ Base 依赖下载成功", "131759821" in succeeded)
check("SheepSquatch 依赖下载成功", "2161380206" in succeeded)

p("---- 第 3 步：入库与依赖记录 ----")
mgr.stop()
stats = lib.stats()
p(f"  库统计: {stats}")
# 递归依赖树：根 + 直接依赖 + 传递依赖，总数 >= 3
check("库中至少 3 个 mod（含递归依赖）", stats["total"] >= 3, str(stats))

rec = lib.get(ROOT_ID)
check("根 mod 已入库", rec is not None and rec.installed)
for did in EXPECTED_DEPS:
    d = lib.get(did)
    check(f"依赖 {did} 已入库", d is not None and d.installed)
check("全部下载成功", all(
    j.status.value == "success" for j in jobs
))

result = "\n".join(out.getvalue().splitlines())
print(result)
rf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_deps_e2e.txt")
with open(rf, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
