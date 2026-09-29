"""核心链路冒烟测试：浏览 → 元数据补全 → 匿名下载 → 入库检索。"""
import io
import sys
import time

sys.path.insert(0, ".")

from swdm.core import (
    APP_DISPLAY,
    AuthManager,
    DownloadManager,
    ModLibrary,
    SteamAPI,
    SteamCMDEngine,
    WorkshopItem,
    all_games,
    get_config,
    setup_logger,
)

out = io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

setup_logger("INFO")
p(f"== {APP_DISPLAY} 核心冒烟测试 ==")

cfg = get_config()

# 1) 游戏注册表
games = all_games()
check("游戏注册表非空", len(games) > 30, f"({len(games)} 游戏)")
gmod = [g for g in games if g["appid"] == "4000"]
check("包含 GMod", bool(gmod), gmod[0]["name"] if gmod else "")

# 2) API 浏览
api = SteamAPI(api_key=cfg.get("network", "api_key"), proxy=cfg.get("network", "proxy"))
check("API 连通", api.ping())
items = api.browse("4000", page=1)
check("浏览页抓取", len(items) > 5, f"得到 {len(items)} 个物品")
if items:
    p(f"   样例: {items[0].publishedfileid} {items[0].title!r}")

# 3) 元数据补全
api.enrich(items[:5])
sample = items[0]
check("元数据补全-订阅数", sample.subscriptions > 0, f"subs={sample.subscriptions}")
check("元数据补全-标签", len(sample.tags) > 0, str(sample.tags[:3]))
check("元数据补全-文件大小", sample.file_size > 0, f"{sample.file_size} bytes")

# 4) 单项详情
det = api.get_file_details([sample.publishedfileid])
check("单项详情 API", sample.publishedfileid in det)

# 5) URL 解析
appid, iid = api.resolve_any_url("https://steamcommunity.com/sharedfiles/filedetails/?id=3802244270")
check("URL 解析-filedetails", iid == "3802244270", f"appid={appid}")
a2, i2 = api.resolve_any_url("3802244270")
check("URL 解析-纯数字", i2 == "3802244270")

# 6) 匿名下载（小文件：Dynamic Flashlight 1.8MB）
auth = AuthManager()
check("默认匿名模式", auth.is_anonymous())
user, pw, guard = auth.get_credentials()
check("匿名无凭据", user == "" and pw == "")

engine = SteamCMDEngine(
    exe_path=cfg.get("steamcmd", "exe_path"),
    install_dir=cfg.get("steamcmd", "force_install_dir") or None,
    anonymous=True,
)
dl_item = WorkshopItem(publishedfileid="3802244270", appid="4000", title="Dynamic Flashlight", file_size=1840727)
result = engine.download_item("4000", "3802244270")
check("匿名下载成功", result.status.value == "success", f"bytes={result.bytes_done} path={result.path}")
# 注：工坊物品会被作者更新，字节数随之变化，只要求非空
check("下载字节数非空", result.bytes_done > 0, f"{result.bytes_done} bytes")

# 7) 入库与检索
lib = ModLibrary()
from swdm.core.mod_library import ModRecord

rec = ModRecord(
    item_id="3802244270",
    appid="4000",
    title="Dynamic Flashlight",
    file_size=result.bytes_done,
    tags=["Fun"],
    local_path=result.path,
    installed=True,
    download_time=int(time.time()),
)
lib.upsert(rec)
lib.write_metadata_sidecar(rec)
got = lib.get("3802244270")
check("入库", got is not None and got.title == "Dynamic Flashlight")
found = lib.search(keyword="Flashlight")
check("关键词检索", len(found) >= 1)
found2 = lib.search(appid="4000", sort="subs")
check("按游戏检索+排序", len(found2) >= 1)
stats = lib.stats()
check("统计接口", stats["total"] >= 1, str(stats))

# 8) 下载管理器（队列+回调）
mgr_events = {"started": 0, "finished": 0}
mgr = DownloadManager(engine, lib, max_concurrent=1, auto_retry=0)
mgr.on_started = lambda j: mgr_events.__setitem__("started", mgr_events["started"] + 1)
mgr.on_finished = lambda j: mgr_events.__setitem__("finished", mgr_events["finished"] + 1)
mgr.start()
job = mgr.enqueue(WorkshopItem(publishedfileid="3803469767", appid="4000", title="Test mod"), "4000")
t0 = time.time()
while job.status.value not in ("success", "failed", "cancelled") and time.time() - t0 < 120:
    time.sleep(1)
# 状态终态会先于 on_finished 回调返回，补宽限等待回调落账
grace = time.time() + 5
while (mgr_events["finished"] < 1) and time.time() < grace:
    time.sleep(0.2)
check("下载队列执行", job.status.value == "success", f"status={job.status.value}")
check("管理器回调触发", mgr_events["started"] >= 1 and mgr_events["finished"] >= 1, str(mgr_events))
mgr.stop()

lib.log_job("3803469767", "4000", "Test mod", job.status.value, job.bytes_done, job.message)
check("任务历史", len(lib.job_history(10)) >= 1)

open("tests/_smoke_out.txt", "w", encoding="utf-8").write(out.getvalue())
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
