"""轻量验证：_register_to_library 正确记录 dependencies（无需网络/下载）。
直接构造 DownloadJob + DownloadResult，调用入库逻辑，检查依赖字段落库。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_depRec_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from swdm.core import (  # noqa: E402
    DownloadJob,
    DownloadManager,
    DownloadResult,
    DownloadStatus,
    JobStatus,
    ModLibrary,
    SteamCMDEngine,
    WorkshopItem,
    ensure_dirs,
    setup_logger,
)
from swdm.core.downloader import DownloadManager  # noqa: E402,F811

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

lib = ModLibrary()
mgr = DownloadManager(SteamCMDEngine(anonymous=True), lib, auto_retry=0)

# 构造一个带依赖的物品
item = WorkshopItem(
    publishedfileid="999000111", appid="718670",
    title="测试子模组", file_size=1024,
    dependencies=["111222333", "444555666"],
)
job = DownloadJob(item=item, appid="718670", total_bytes=1024)
job.status = JobStatus.SUCCESS
job.bytes_done = 1024

# 模拟 steamcmd 成功结果（local_path 指向一个存在的目录）
content_dir = os.path.join(_TMP, "SWDM", "mods", "steamapps", "workshop",
                          "content", "718670", "999000111")
os.makedirs(content_dir, exist_ok=True)
result = DownloadResult(
    item_id="999000111", appid="718670", status=DownloadStatus.SUCCESS,
    bytes_done=1024, path=content_dir,
)

mgr._register_to_library(job, result)

rec = lib.get("999000111")
check("mod 已入库", rec is not None)
if rec:
    check("依赖被正确记录", rec.dependencies == ["111222333", "444555666"],
          str(rec.dependencies))
    check("local_path 是目录", os.path.isdir(rec.local_path))
    # 元数据旁车里也应有依赖
    import json
    meta_p = os.path.join(rec.local_path, "swdm_meta.json")
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p, encoding="utf-8"))
        check("元数据旁车含依赖", meta.get("dependencies") == ["111222333", "444555666"],
              str(meta.get("dependencies")))
    else:
        check("元数据旁车存在", False)

result_text = "\n".join(out.getvalue().splitlines())
print(result_text)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
