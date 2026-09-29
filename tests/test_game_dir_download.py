"""游戏专属下载目录的下载链路集成测试（mock 引擎，零网络）。

验证：为某游戏配置专属目录后，DownloadManager 把该目录传给 steamcmd 引擎
（force_install_dir），且未配置的游戏仍走默认目录。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_gdlink_")
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
from swdm.core.game_dirs import clear_game_dir, set_game_dir  # noqa: E402

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


class RecordingEngine(SteamCMDEngine):
    """记录每次 download_item 收到的 install_dir。"""

    def __init__(self, install_dir):
        super().__init__(install_dir=install_dir, anonymous=True)
        self.seen_dirs: list[str] = []
        self.seen_partial_dirs: list[str] = []

    def _run(self, commands, on_line=None, feed_stdin="", install_dir=""):
        self.seen_dirs.append(install_dir)
        # 模拟 steamcmd 成功输出
        if on_line:
            on_line("Success. Downloaded item 123 to \"dummy\" (1024 bytes)")
        return 0

    def ensure_partial(self, item_id, appid="", install_dir=""):
        self.seen_partial_dirs.append(install_dir)
        return 0


DEFAULT_DIR = os.path.join(_TMP, "default_mods")
GAME_DIR = os.path.join(_TMP, "game4000_mods")

mgr = DownloadManager(RecordingEngine(DEFAULT_DIR), ModLibrary(), auto_retry=0)

def _download(appid: str) -> str:
    """下载一个物品，返回引擎实际收到的 install_dir。"""
    item = WorkshopItem(
        publishedfileid="123", appid=appid, title="t", file_size=1024,
    )
    job = DownloadJob(item=item, appid=appid, total_bytes=1024)
    mgr._exec_job(job)
    eng = mgr.engine  # type: ignore
    return eng.seen_dirs[-1]

# 1) 未配置任何游戏目录 → 走默认目录（不传 install_dir）
d = _download("4000")
check("未配置时走默认目录", d == "", repr(d))

# 2) 为 4000 配置专属目录 → 引擎收到该目录
set_game_dir("4000", GAME_DIR)
d = _download("4000")
check("配置后引擎收到专属目录", os.path.abspath(d) == os.path.abspath(GAME_DIR), repr(d))

# 3) ensure_partial 也收到专属目录
check("ensure_partial 收到专属目录",
      any(os.path.abspath(x) == os.path.abspath(GAME_DIR)
          for x in mgr.engine.seen_partial_dirs),
      str(mgr.engine.seen_partial_dirs))

# 4) 其它游戏（未配置）仍走默认目录
d = _download("718670")
check("未配置的游戏仍走默认目录", d == "", repr(d))

# 5) 清除配置后回到默认
clear_game_dir("4000")
d = _download("4000")
check("清除配置后回到默认目录", d == "", repr(d))

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
