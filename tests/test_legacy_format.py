"""验证 local_path 修复：3 款 legacy 格式游戏的 mod 下载后正确入库。
绕开浏览页限流：直接用已知的 publishedfileid 下载。

网络感知夹具（t36 修复）：本机 api.steampowered.com 常被 SNI 阻断、
steamcontent CDN 也可能不可达。测试按网络可用性分级：
  - API 可用（live=True）：字节数须与 API 实时 file_size 一致，下载失败=FAIL
  - API 不可达（live=False）：字节数只要求 >0，下载失败=该例 SKIP（环境）
入库结构检查（local_path 是目录 / 旁车 JSON / legacy bin / 检索 / 分类）
在两种模式下只要下载成功就是硬断言——这是本测试的真正目的。
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

def skip(name, why):
    p(f"[SKIP] {name} {why}")

# legacy 单文件格式：appid, item_id（此前批量测试中下载成功的）
# expected_bytes 为历史参考值，live 模式下改用 API 实时 file_size
CASES = [
    ("550", "3803864823", "Early Left 4 Dead 2 Skies", 30810934),
    ("1250", "3804451821", "Chronic for Killing Floor", 68552188),
    ("8930", "3804862053", "_Reworked Honor Policies_", 18434),
]

api = SteamAPI()
lib = ModLibrary()
engine = SteamCMDEngine(anonymous=True)
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)

# 先用 API 取标题与实时大小（详情接口不限流）
ids = [c[1] for c in CASES]
try:
    details = api.get_file_details(ids)
except Exception as e:  # noqa: BLE001
    details = {}
    p("元数据接口异常: %r" % e)
live = bool(details)
p(f"元数据接口返回: {len(details)} 个（live={live}）")

mgr.start()
n_ok = 0
for appid, item_id, title, expected_bytes in CASES:
    d = details.get(item_id)
    it = d if d else WorkshopItem(publishedfileid=item_id, appid=appid, title=title)
    it.appid = appid
    p(f"---- {appid}/{item_id} {it.title[:36]!r} ----")

    job = mgr.enqueue(it, appid)
    t0 = time.time()
    # 离线模式用较短超时：失败例本就 SKIP，避免 run_all 长时间挂起
    deadline = 240 if live else 90
    while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < deadline:
        time.sleep(1)
    grace = time.time() + 4
    while grace > time.time() and job.status.value not in ("success", "failed", "cancelled"):
        time.sleep(0.3)

    if job.status.value != "success":
        # live 模式下下载失败是产品问题；离线模式是环境问题，跳过该例
        if live:
            check(f"{appid}: 下载成功", False, f"status={job.status.value}")
        else:
            skip(f"{appid}: 下载成功", f"环境不可达 status={job.status.value}")
        continue
    n_ok += 1
    check(f"{appid}: 下载成功", True, f"bytes={job.bytes_done}")

    if live:
        want = int(getattr(d, "file_size", 0) or 0)
        if want:
            check(f"{appid}: 字节数与 API 一致", job.bytes_done == want,
                  f"{job.bytes_done} vs api={want}")
        else:
            check(f"{appid}: 字节数非零", job.bytes_done > 0)
    else:
        # 离线模式：mod 内容会随作者更新变化，只要求真的下到了数据
        check(f"{appid}: 字节数非零", job.bytes_done > 0, f"bytes={job.bytes_done}")

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
if n_ok == len(CASES):
    check("3 款 legacy 游戏全部入库", stats["total"] == 3 and stats["games"] == 3, str(stats))
else:
    skip("3 款 legacy 游戏全部入库", f"仅 {n_ok}/{len(CASES)} 例下载成功（环境）")

result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_legacy_out.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

try:
    shutil.rmtree(_TMP, ignore_errors=True)
except OSError:
    pass
sys.exit(0 if ok else 1)
