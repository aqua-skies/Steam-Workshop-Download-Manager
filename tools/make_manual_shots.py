"""A1 用户手册截图生成（t42 · 1.4.1）。

固定夹具数据 + offscreen 渲染，**不跑实网**（本机代理不稳会截到错误页）。
与 tools/make_readme_shots.py 同源思路，扩展为手册需要的 5 个场景：
工坊浏览（搜索+标签）、详情弹窗（依赖+冲突+评论）、下载队列（进行中/
排队/失败+C2 原因）、模组库（刷新标记红+右键菜单提示）、设置（全部展开）。

本机读图工具不可用（sharp ERR_DLOPEN_FAILED / modlens key invalid）：
本脚本只保证"生成不崩溃 + 尺寸非零"，成图需人工目检后入库。

用法：python tools/make_manual_shots.py
输出：docs/manual/images/manual-*.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

# offscreen QPA 不枚举 Windows 系统字体（默认查 PySide6/lib/fonts，Qt 不再自带字体）
# → 0 个字体族，连 ASCII 都无字形，成图全是豆腐块。指到 %WINDIR%\Fonts 修复。
_WINFONTS = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WINFONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _WINFONTS)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import tempfile  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="swdm_manual_")
os.environ["APPDATA"] = _TMP

from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core import ensure_dirs  # noqa: E402
from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402
from swdm.core.mod_library import ModRecord  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

ensure_dirs()
OUT = os.path.join(_ROOT, "docs", "manual", "images")
os.makedirs(OUT, exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv)

# 显式中文字体：offscreen 默认字体经 fontdb 兜底不一定命中 CJK 字形，
# 且需与真实 Windows 观感一致（微软雅黑）
from PySide6.QtGui import QFont  # noqa: E402

app.setFont(QFont("Microsoft YaHei", 9))

# 延迟导入：MainWindow 会读配置/起下载管理器，在环境变量就绪后进行
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.resize(1280, 800)

# ---- 固定夹具：6 个 GMod(app 4000) 工坊物品（虚构标题，避免实网） ----
ITEMS = [
    WorkshopItem(
        publishedfileid="2537001001",
        title="Wiremod 进阶工具包 E2 扩展",
        description="Expression2 常用函数库与 spawnlist，一键导入。",
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

# ---- 库夹具：2 条已入库记录（供库页截图 + 详情弹窗"已在库"状态） ----
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

results = []


def _save(widget, name: str) -> None:
    widget.show()
    app.processEvents()
    pix = widget.grab()
    path = os.path.join(OUT, name)
    saved = pix.save(path, "PNG")
    size = os.path.getsize(path) if saved and os.path.exists(path) else 0
    ok = bool(saved) and size > 1_000 and not pix.isNull()
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {size}B {pix.width()}x{pix.height()}")


# ---- 1) 工坊浏览：填入列表 + 搜索词 + 标签筛选 ----
win._tabs.setCurrentIndex(0)
win.workshop_tab._populate(ITEMS)
win.workshop_tab.search_edit.setText("wiremod")
win.workshop_tab.tag_edit.setText("tool")
_save(win, "manual-workshop.png")
win.workshop_tab.search_edit.setText("")
win.workshop_tab.tag_edit.setText("")

# ---- 2) 详情弹窗：依赖 + 冲突声明 + 评论（全部夹具，零网络） ----
from swdm.gui.detail_dialog import Comment, ModDetailDialog  # noqa: E402

dlg = ModDetailDialog(
    ITEMS[0],
    library=win.svc.library,
    downloader=win.svc.downloader,
    api=None,
    comments=[
        Comment(author="玩家A", content="E2 函数库很全，spawnlist 直接能用。", time="9 月 20 日"),
        Comment(author="玩家B", content="和 Wiremod 正式版搭配食用更佳。", time="9 月 18 日"),
    ],
    dependencies=[("2537001003", "道具合成系统 (Prop Combine)")],
    conflicts=[("2537001006", "音效替换：环境氛围 200+", "本地库存在同名 mod，可能存在内容冲突")],
)
dlg.resize(900, 680)
_save(dlg, "manual-detail.png")
dlg.close()

# ---- 3) 下载队列：进行中（进度）+ 排队 + 失败（C2 原因枚举文案） ----
win._tabs.setCurrentIndex(1)
job_run = DownloadJob(
    item=ITEMS[0],
    appid="4000",
    status=JobStatus.RUNNING,
    bytes_done=13_200_000,
    total_bytes=24_500_000,
    speed_mbps=8.4,
    channel="steamcmd",
)
job_queued = DownloadJob(item=ITEMS[1], appid="4000", status=JobStatus.QUEUED)
job_failed = DownloadJob(
    item=ITEMS[5],
    appid="4000",
    status=JobStatus.FAILED,
    message="账号问题：该物品归受限 App，匿名无法下载，请在设置页登录",
)
for _j in (job_run, job_queued, job_failed):
    win.downloads_tab._ensure_row(_j)
    win.downloads_tab._update_row(_j)
_save(win, "manual-downloads.png")

# ---- 4) 模组库：刷新标记红（C1 检查更新结果） + 检索 ----
win._tabs.setCurrentIndex(2)
win.library_tab.refresh()
win.library_tab.search_edit.setText("")
win.library_tab._updated_ids = {"2537001004"}  # 模拟 C1 检查更新命中
win.library_tab.refresh()
_save(win, "manual-library.png")

# ---- 5) 设置页：展开全部折叠区（CollapsibleSection） ----
win._tabs.setCurrentIndex(3)
from swdm.gui.widgets import CollapsibleSection  # noqa: E402

for sec in win.settings_tab.findChildren(CollapsibleSection):
    sec.setExpanded(True)
win.resize(1280, 1500)  # 拉高让展开内容尽量入镜
win._tabs.setCurrentIndex(3)
_save(win, "manual-settings.png")

win.close()

if all(results):
    print("RESULT: ALL PASS")
else:
    print(f"RESULT: FAIL ({results.count(False)} bad shots)")
    sys.exit(1)
