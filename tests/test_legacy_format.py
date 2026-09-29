"""验证 local_path 修复：3 款 legacy 格式游戏的 mod 下载后正确入库。
绕开浏览页限流：直接用已知的 publishedfileid 下载。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_legacy_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, ".")

import io as _io  # noqa: E402

from swdm.core import (  # noqa: E402
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
    WorkshopItem,
    ensure_dirs,
    setup_logger,
)
from swdm.core.logger import get_logger  # noqa: E402

setup_logger("INFO")
ensure_dirs()
log = get_logger("swdm.legacy")

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# legacy 单文件格式：appid, item_id（此前批量测试中下载成功的）
CASES = [
    ("550", "3803864823", "Early Left 4 Dead 2 Skies", 30810934),
    ("1250", "3804451821", "Chronic for Killing Floor", 68552188),
    ("8930", "3804862053", "_Reworked Honor Policies_", 18434),
]

api = SteamAPI()
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)

# 先用 API 取标题（详情接口不限流）
ids = [c[1] for c in CASES]
details = api.get_file_details(ids)
p("元数据接口返回: %d 个" % len(details))

mgr.start()
for appid, item_id, title, expected_bytes in CASES:
    d = details.get(item_id)
    it = d if d else WorkshopItem(publishedfileid=item_id, appid=appid, title=title)
    it.appid = appid
    p(f"---- {appid}/{item_id} {it.title[:36]!r} ----")

    job = mgr.enqueue(it, appid)
    t0 = time.time()
    while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 240:
        time.sleep(1)
    grace = time.time() + 4
    while grace > time.time() and job.status.value not in ("success", "failed", "cancelled"):
        time.sleep(0.3)

    check(f"{appid}: 下载成功", job.status.value == "success",
          f"bytes={job.bytes_done}")
    check(f"{appid}: 字节数一致", job.bytes_done == expected_bytes,
          f"{job.bytes_done} vs {expected_bytes}")

    rec = lib.get(item_id)
    check(f"{appid}: 已入库", rec is not None)
    if rec:
        check(f"{appid}: local_path 是目录", os.path.isdir(rec.local_path), rec.local_path)
        check(f"{appid}: 元数据旁车存在",
              os.path.exists(os.path.join(rec.local_path, "swdm_meta.json")))
        # legacy bin 文件仍在该目录下
        bins = [f for f in os.listdir(rec.local_path) if f.endswith("_legacy.bin")]
        check(f"{appid}: legacy 文件在目录中", len(bins) >= 1, str(bins[:1]))
        check(f"{appid}: 关键词检索", len(lib.search(keyword=rec.title[:6])) >= 1)
        lib.set_category(item_id, "legacy 测试")
        check(f"{appid}: 分类检索", any(r.item_id == item_id for r in lib.search(category="legacy 测试")))
mgr.stop()

stats = lib.stats()
p(f"库统计: {stats}")
check("3 款 legacy 游戏全部入库", stats["total"] == 3 and stats["games"] == 3, str(stats))

result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_legacy_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

try:
    shutil.rmtree(_TMP, ignore_errors=True)
except OSError:
    pass
sys.exit(0 if ok else 1)
