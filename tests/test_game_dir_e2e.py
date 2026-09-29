"""游戏目录端到端实测：为 Cultist Simulator 配置专属目录，下载 mod，
验证文件落到该目录且入库记录正确（走真实 steamcmd，无需 filedetails）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="swdm_gd_e2e_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truststore  # noqa: E402

truststore.inject_into_ssl()

import io as _io  # noqa: E402

from swdm.core import (  # noqa: E402
    DownloadJob,
    DownloadManager,
    SteamAPI,
    SteamCMDEngine,
    WorkshopItem,
    ensure_dirs,
    setup_logger,
)
from swdm.core.game_dirs import game_install_dir, set_game_dir  # noqa: E402

setup_logger("WARNING")
ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

GAME_DIR = os.path.join(_TMP, "CultistMods")
set_game_dir("718670", GAME_DIR)
check("游戏目录已配置", game_install_dir("718670") == GAME_DIR)

api = SteamAPI()
lib = ModLibrary = None
from swdm.core import ModLibrary  # noqa: E402

lib = ModLibrary()
mgr = DownloadManager(SteamCMDEngine(anonymous=True), lib, auto_retry=2)

# 取 Cultist 热度排行第 3 的 mod（此前已验证可匿名下载，无复杂依赖）
items = api.browse("718670", sort="mostsubscribed", numperpage=10)
target = next((i for i in items if i.publishedfileid == "3800888654"), None)
if target is None and items:
    target = min(items, key=lambda i: i.file_size or 0)
check("找到测试 mod", target is not None,
      f"{target.title if target else '?'} ({target.file_size//1048576 if target else 0} MB)")

if target:
    job = mgr.enqueue(target, "718670")
    done = {"flag": False}
    mgr.on_finished = lambda j: done.__setitem__("flag", True)
    mgr.start()

    t0 = time.time()
    while not done["flag"] and time.time() - t0 < 300:
        time.sleep(2)

    check("下载完成（5分钟内）", done["flag"], f"{time.time()-t0:.0f}s")
    check("任务成功", job.status.value == "success" or str(job.status) == "JobStatus.SUCCESS",
          str(job.status))

    rec = lib.get(target.publishedfileid)
    check("已入库", rec is not None)
    if rec:
        check("local_path 在专属目录下",
              os.path.normpath(rec.local_path).lower().startswith(
                  os.path.normpath(GAME_DIR).lower()),
              rec.local_path)
        check("内容目录真实存在", os.path.isdir(rec.local_path))
        files = []
        for root, _d, fs in os.walk(rec.local_path):
            files.extend(fs)
        check("内容目录非空", len(files) > 0, f"{len(files)} 个文件")

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
