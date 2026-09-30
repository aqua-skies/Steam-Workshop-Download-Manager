"""README 截图生成（t39 / A3 · 1.4.1）。

固定夹具数据 + offscreen 渲染，**不跑实网**（本机代理不稳会截到错误页）。
本机读图工具不可用（sharp ERR_DLOPEN_FAILED / modlens key invalid）：
本脚本只保证"生成不崩溃 + 尺寸非零"，成图需人工目检后入库。

用法：python tools/make_readme_shots.py
输出：docs/screenshots/*.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import tempfile  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="swdm_shots_")
os.environ["APPDATA"] = _TMP

from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core import ensure_dirs  # noqa: E402
from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402
from swdm.core.mod_library import ModRecord  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

ensure_dirs()
OUT = os.path.join(_ROOT, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv)
win = MainWindow()
win.resize(1280, 800)

# ---- 固定夹具：6 个 GMod(app 4000) 工坊物品（虚构标题，避免实网） ----
ITEMS = [
    WorkshopItem(
        publishedfileid="2537001001",
        title="Wiremod 进阶工具包 E2 扩展",
        description="Expression2 常用函数库与spawnlist，一键导入。",
        creator_name="FixtureAuthor",
        appid="4000",
        file_size=24_500_000,
        subscriptions=128_400,
        lifetime_subscriptions=410_200,
        favorited=9_800,
        views=1_204_000,
        tags=["wiremod", "tool", "e2"],
    ),
    WorkshopItem(
        publishedfileid="2537001002",
        title="RP 城市地图：暮光之城 v3.2",
        creator_name="FixtureMapper",
        appid="4000",
        file_size=310_400_000,
        subscriptions=86_700,
        favorited=5_100,
        views=840_000,
        tags=["map", "roleplay", "city"],
    ),
    WorkshopItem(
        publishedfileid="2537001003",
        title="道具合成系统 (Prop Combine)",
        creator_name="FixtureAuthor",
        appid="4000",
        file_size=1_200_000,
        subscriptions=42_300,
        favorited=2_240,
        views=510_000,
        tags=["tool", "sandbox"],
    ),
    WorkshopItem(
        publishedfileid="2537001004",
        title="真实车辆物理引擎包",
        creator_name="FixtureModder",
        appid="4000",
        file_size=88_000_000,
        subscriptions=64_900,
        favorited=3_700,
        views=690_000,
        tags=["vehicle", "physics"],
    ),
    WorkshopItem(
        publishedfileid="2537001005",
        title="玩家模型：未来战士套装",
        creator_name="FixtureArtist",
        appid="4000",
        file_size=56_300_000,
        subscriptions=31_200,
        favorited=1_850,
        views=420_000,
        tags=["playermodel", "skin"],
    ),
    WorkshopItem(
        publishedfileid="2537001006",
        title="音效替换：环境氛围 200+",
        creator_name="FixtureAuthor",
        appid="4000",
        file_size=145_000_000,
        subscriptions=18_600,
        favorited=940,
        views=260_000,
        tags=["sound", "audio"],
    ),
]

win.workshop_tab._populate(ITEMS)

# ---- 下载夹具：1 运行中（带进度）+ 1 排队 ----
job_run = DownloadJob(
    item=ITEMS[0],
    appid="4000",
    status=JobStatus.RUNNING,
    bytes_done=13_200_000,
    total_bytes=24_500_000,
    speed_mbps=8.4,
    channel="steamcmd",
)
job_queued = DownloadJob(
    item=ITEMS[1],
    appid="4000",
    status=JobStatus.QUEUED,
)
for _j in (job_run, job_queued):
    win.downloads_tab._ensure_row(_j)
    win.downloads_tab._update_row(_j)

# ---- 库夹具：2 条已入库记录 ----
win.svc.library.upsert(
    ModRecord(
        item_id="2537001003",
        appid="4000",
        title="道具合成系统 (Prop Combine)",
        creator_name="FixtureAuthor",
        file_size=1_200_000,
        subscriptions=42_300,
        tags=["tool", "sandbox"],
        local_path=os.path.join(_TMP, "GModMods", "4000", "2537001003"),
        installed=True,
        enabled=True,
        category="工具",
    )
)
win.svc.library.upsert(
    ModRecord(
        item_id="2537001004",
        appid="4000",
        title="真实车辆物理引擎包",
        creator_name="FixtureModder",
        file_size=88_000_000,
        subscriptions=64_900,
        tags=["vehicle", "physics"],
        local_path=os.path.join(_TMP, "GModMods", "4000", "2537001004"),
        installed=True,
        enabled=False,
        category="载具",
    )
)
win.library_tab.refresh()

# ---- 逐页截图 ----
results = []


def shot(name: str, idx: int) -> None:
    win._tabs.setCurrentIndex(idx)
    win.show()
    app.processEvents()
    pix = win.grab()
    path = os.path.join(OUT, name)
    saved = pix.save(path, "PNG")
    size = os.path.getsize(path) if saved and os.path.exists(path) else 0
    ok = bool(saved) and size > 1_000 and not pix.isNull()
    results.append(ok)
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name} {size}B "
        f"{pix.width()}x{pix.height()}"
    )
    win.close()


shot("workshop.png", 0)
shot("downloads.png", 1)
shot("library.png", 2)
shot("settings.png", 3)

if all(results):
    print("RESULT: ALL PASS")
else:
    print(f"RESULT: FAIL ({results.count(False)} bad shots)")
    sys.exit(1)
