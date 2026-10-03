"""t14 回归测试：下载速度采样（卡 99%/速度突跳）+ mod 库按游戏分类。

覆盖：
- ProgressSmoother 滚动窗口速度：突发合并 tick 不再突跳到 2-300MB/s、
  长停顿后窗口正确反映真实速率、窗口外样本被淘汰
- DownloadJob.percent 完成判定以字节数为准（u9 卡 99%）
- mod 库 appid 维度：upsert 写入 appid、search 按 appid 过滤/排序、
  库页下拉与行文本显示游戏名

环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen，import swdm 前设 APPDATA 临时目录。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_dlstats_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.core.downloader import DownloadJob, JobStatus  # noqa: E402
from swdm.core.mod_library import ModLibrary, ModRecord  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.throttle import ProgressSmoother  # noqa: E402

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


# ================================================================ 1. 速度采样
# ---- 1.1 稳定下载：窗口速度贴近真实速率
sm = ProgressSmoother(min_interval=0.05, window=2.0)
sm.reset(0, now=0.0)
# 每 0.1s 下 1MB -> 真实 10 MB/s
snaps = []
for i in range(1, 21):
    s = sm.feed(i * 1024 * 1024, 100 * 1024 * 1024, now=0.1 * i)
    if s is not None:
        snaps.append(s)
check("稳定下载有速度下发", len(snaps) > 0, str(len(snaps)))
steady = snaps[-1]
check("稳定下载窗口速度 > 0", steady["speed_mbps"] > 0, f"{steady['speed_mbps']:.2f}")
# 窗口跨越最近 2s（约 20MB 增量 / 2s），速度应在 8-15 MB/s 区间
check("稳定下载窗口速度贴近真实（不突跳）",
      8.0 < steady["speed_mbps"] < 15.0, f"{steady['speed_mbps']:.2f} MB/s")
check("稳定下载 ETA > 0", steady["eta"] > 0, f"{steady['eta']:.1f}s")
check("稳定下载 label 含速度", "MB/s" in steady["label"], steady["label"])

# ---- 1.2 合并 tick 不突跳（旧 EMA 的核心病灶）
# 模拟：工作线程稳定上报，但某次 Qt 把多个 tick 合并到同一时刻下发。
# 旧实现 dt->1e-6，一次 tick 携带 2MB 增量 -> 突跳到 ~2e4 MB/s。
sm2 = ProgressSmoother(min_interval=0.0, window=2.0)  # 关闭限流以隔离速度算法
sm2.reset(0, now=0.0)
for i in range(1, 11):
    sm2.feed(i * 1024 * 1024, 100 * 1024 * 1024, now=0.1 * i)  # 0-1s 稳定 10MB/s
# 关键：dt 极小（0.0001s，合并 tick）携带 2MB 增量
burst = sm2.feed(12 * 1024 * 1024, 100 * 1024 * 1024, now=1.0001)
check("合并 tick 仍下发（窗口模式不限流时）", burst is not None, "None")
check("合并 tick 速度不突跳（旧 EMA 会给 ~20000 MB/s）",
      burst is not None and burst["speed_mbps"] < 100.0,
      f"{burst['speed_mbps']:.2f}" if burst else "None")
# 滚动窗口：窗口内总增量 12MB / 1.0001s ≈ 12MB/s，而非 2MB/0.0001s
check("合并 tick 后速度落在窗口平均值附近",
      burst is not None and 8.0 < burst["speed_mbps"] < 20.0,
      f"{burst['speed_mbps']:.2f}" if burst else "None")

# ---- 1.2b 限流场景下的合并 tick：emit 被 min_interval 丢弃时速度仍不突跳
sm2b = ProgressSmoother(min_interval=0.1, window=2.0)
sm2b.reset(0, now=0.0)
for i in range(1, 11):
    sm2b.feed(i * 1024 * 1024, 100 * 1024 * 1024, now=0.1 * i)
# 限流丢弃的观测仍进入窗口（否则窗口缺数据，下次下发会突跳）
dropped = sm2b.feed(15 * 1024 * 1024, 100 * 1024 * 1024, now=1.001)
check("限流窗口内合并 tick 被丢弃", dropped is None, "should be None")
after = sm2b.feed(15 * 1024 * 1024, 100 * 1024 * 1024, now=1.15)
check("限流丢弃期间样本仍入窗口 -> 恢复下发不突跳",
      after is not None and after["speed_mbps"] < 25.0,
      f"{after['speed_mbps']:.2f}" if after else "None")

# ---- 1.3 长停顿后速度反映真实（先 0 后恢复，不再卡在旧 EMA 或突跳）
sm3 = ProgressSmoother(min_interval=0.0, window=2.0)
sm3.reset(0, now=0.0)
sm3.feed(5 * 1024 * 1024, 100 * 1024 * 1024, now=1.0)   # 第 1 秒下了 5MB
# 停顿 10 秒（远超窗口）——旧 EMA 在此期间会反复以 dt=大值喂 0 增量而衰减
stall = sm3.feed(5 * 1024 * 1024, 100 * 1024 * 1024, now=11.0)
check("长停顿后窗口内无增量 -> 速度归 0",
      stall is not None and stall["speed_mbps"] == 0.0,
      f"{stall['speed_mbps']:.2f}" if stall else "None")
# 恢复后窗口只含新增量，不会把停顿前的旧速度或突跳混入
resume = sm3.feed(15 * 1024 * 1024, 100 * 1024 * 1024, now=12.0)
check("停顿后恢复：速度按窗口内真实增量计算",
      resume is not None and 4.0 < resume["speed_mbps"] < 11.0,
      f"{resume['speed_mbps']:.2f}" if resume else "None")

# ---- 1.4 窗口外样本被淘汰（内存不无限增长，且旧增量不污染当前速度）
sm4 = ProgressSmoother(min_interval=0.0, window=1.0)
sm4.reset(0, now=0.0)
for i in range(1, 21):
    sm4.feed(i * 1024 * 1024, 100 * 1024 * 1024, now=0.1 * i)  # 2s 内 20MB
check("窗口外样本被淘汰", len(sm4._samples) <= 12, str(len(sm4._samples)))
late = sm4.feed(21 * 1024 * 1024, 100 * 1024 * 1024, now=2.05)
# 窗口 [1.05, 2.05]：增量 ≈ (21-10)MB / 1s ≈ 11MB/s，不含 1s 前的量
check("旧增量不污染当前窗口速度",
      late is not None and 9.0 < late["speed_mbps"] < 13.0,
      f"{late['speed_mbps']:.2f}" if late else "None")

# ---- 1.5 限流 / 不倒退 / force 语义保持（不能被重构破坏）
sm5 = ProgressSmoother(min_interval=0.1)
sm5.reset(0, now=1.0)
check("限流丢弃（< min_interval）",
      sm5.feed(1_000_000, 10_000_000, now=1.001) is None)
b = sm5.feed(2_000_000, 10_000_000, now=1.2)
check("超间隔后下发", b is not None and b["bytes"] == 2_000_000,
      str(b["bytes"]) if b else "None")
c = sm5.feed(500_000, 10_000_000, now=1.3)
check("字节不倒退", c is not None and c["bytes"] == 2_000_000,
      str(c["bytes"]) if c else "None")
check("force 绕过限流",
      sm5.feed(10_000_000, 10_000_000, force=True, now=1.301) is not None)
check("完成时 percent=100",
      sm5.feed(10_000_000, 10_000_000, force=True, now=1.4)["percent"] == 100)

# ---- 1.6 高频上报样本数有上限（防爆内存）
sm6 = ProgressSmoother(min_interval=0.0, window=3.0)
sm6.reset(0, now=0.0)
for i in range(1000):
    sm6.feed(i, 10_000_000, now=0.001 * i)
check("高频上报样本数受 _MAX_SAMPLES 封顶",
      len(sm6._samples) <= ProgressSmoother._MAX_SAMPLES + 2,
      str(len(sm6._samples)))


# ================================================================ 2. 卡 99%
def _mk_job(total: int) -> DownloadJob:
    return DownloadJob(
        item=WorkshopItem(publishedfileid="999000001", title="测试 mod", appid="4000"),
        appid="4000",
        total_bytes=total,
    )


j1 = _mk_job(100 * 1024 * 1024)
j1.status = JobStatus.RUNNING
j1.bytes_done = int(99.9 * 1024 * 1024)
check("进行中进度封顶 99（UI 不谎报完成）", j1.percent == 99, str(j1.percent))
# 关键场景：最后一块完成但完成回调被 Qt 合并/延迟时，UI 不再卡 99%
j1.bytes_done = 100 * 1024 * 1024
check("字节数达标 -> percent=100（完成判定以字节数为准）",
      j1.percent == 100, str(j1.percent))
j1.bytes_done = 100 * 1024 * 1024 + 123  # CDN 续传 total 与实际字节细微不一致
check("字节数超过 total 也正确显示 100", j1.percent == 100, str(j1.percent))
j2 = _mk_job(0)
check("total 未知 -> 不确定进度 -1", j2.percent == -1, str(j2.percent))
# 即使完成回调触发，status 才翻转；字节数先行到 100 不依赖 status
j3 = _mk_job(50 * 1024 * 1024)
j3.status = JobStatus.RUNNING
j3.bytes_done = 50 * 1024 * 1024
check("RUNNING 态字节数达标也显示 100", j3.percent == 100, str(j3.percent))


# ================================================================ 3. mod 库按游戏分类
_lib = ModLibrary(db_path=os.path.join(_TMP, "mods.db"))
_lib.upsert(ModRecord(item_id="8000001", appid="4000", title="GMod mod",
                      file_size=1024, download_time=3))
_lib.upsert(ModRecord(item_id="8000002", appid="550", title="L4D2 mod",
                      file_size=1024, download_time=2))
_lib.upsert(ModRecord(item_id="8000003", appid="4000", title="另一个 GMod mod",
                      file_size=1024, download_time=1))
# 未知游戏（不在内置表）-> game_name 回退 "AppID N"
_lib.upsert(ModRecord(item_id="8000004", appid="999123", title="冷门游戏 mod",
                      file_size=1024, download_time=0))

# ---- 3.1 appid 维度落库（t4 C5 upsert 不回归）
r = _lib.get("8000001")
check("upsert 写入 appid", r is not None and r.appid == "4000",
      r.appid if r else "None")
check("upsert appid 隔离不同游戏",
      _lib.get("8000002").appid == "550")

# ---- 3.2 search 按 appid 过滤
only_gmod = _lib.search(appid="4000")
check("search(appid) 只返回该游戏的 mod",
      len(only_gmod) == 2 and all(x.appid == "4000" for x in only_gmod),
      str(len(only_gmod)))
check("search(appid=550) 隔离", len(_lib.search(appid="550")) == 1)

# ---- 3.3 按游戏排序
by_game = _lib.search(sort="appid")
appids = [x.appid for x in by_game]
check("sort=appid 按游戏分组排序",
      appids == sorted(appids), str(appids))

# ---- 3.4 重新下载时 appid 更新（upsert ON CONFLICT 不丢 appid）
_lib.upsert(ModRecord(item_id="8000001", appid="4000", title="GMod mod 改名",
                      file_size=2048, download_time=4))
r2 = _lib.get("8000001")
check("重新 upsert 保留 appid", r2.appid == "4000", r2.appid)

# ---- 3.5 库页 UI：下拉与行文本显示游戏名
from swdm.core.games import game_name  # noqa: E402
from swdm.gui.library_tab import LibraryTab  # noqa: E402


class _Svc:
    def __init__(self, library):
        self.library = library


lt = LibraryTab(_Svc(_lib))
app.processEvents()

combo_labels = [lt.appid_combo.itemText(i) for i in range(lt.appid_combo.count())]
check("库页下拉含全部游戏选项", len(combo_labels) >= 4, str(combo_labels))
check("库页下拉显示游戏名而非裸 AppID",
      any("Garry's Mod" in t for t in combo_labels), str(combo_labels))
check("库页下拉包含未知游戏的 AppID 回退项",
      any("AppID 999123" in t for t in combo_labels), str(combo_labels))
# currentData 仍是裸 appid（过滤逻辑不变）
idx = lt.appid_combo.findData("4000")
check("库页下拉 userData 仍为 appid（过滤不回归）",
      idx >= 0 and lt.appid_combo.itemData(idx) == "4000", str(idx))

row_texts = [lt.list_widget.item(i).text()
             for i in range(lt.list_widget.count())]
check("库页行数 = 4 条", len(row_texts) == 4, str(len(row_texts)))
check("库页行文本显示游戏名",
      any("Garry's Mod" in t for t in row_texts), str(row_texts[:2]))
check("库页行文本含未知游戏 AppID 回退",
      any("AppID 999123" in t for t in row_texts), str(row_texts))
check("库页行文本不含裸 AppID 数字",
      not any("· 4000 ·" in t for t in row_texts), str(row_texts[:2]))
check("库页统计标签显示游戏数",
      "3 款游戏" in lt.stats_label.text(), repr(lt.stats_label.text()))

# ---- 3.6 过滤切换后行文本仍带游戏名
lt.appid_combo.setCurrentIndex(idx)
app.processEvents()
filtered = [lt.list_widget.item(i).text()
            for i in range(lt.list_widget.count())]
check("按游戏过滤后只剩该游戏 mod", len(filtered) == 2, str(len(filtered)))
check("过滤后行文本仍显示游戏名",
      all("Garry's Mod" in t for t in filtered), str(filtered))
lt.appid_combo.setCurrentIndex(0)
app.processEvents()


# ================================================================ 汇总
failed = [r for r in RESULTS if not r[1]]
for name, ok, extra in RESULTS:
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  [{extra}]" if extra else ""))
print(f"\nRESULT: {'ALL PASS' if not failed else str(len(failed)) + ' FAILED'}")
sys.exit(0 if not failed else 1)
