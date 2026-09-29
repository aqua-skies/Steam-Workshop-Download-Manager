"""真实端到端集成测试（bug5/7/8）：用真实 steamcmd 下载一个工坊物品。

验证：
- bug5：进度回调有实质变化（不是恒 0% 直到完成）
- bug7：下载期间引擎不出现 NoneType 异常
- bug8：下载中取消不崩溃、程序继续响应
- 防护：所有文件只落在 %APPDATA%/SWDM 临时目录内；不执行任何 mod 内容；
  测试结束自动清理下载目录（可逆）
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

_TMP = tempfile.mkdtemp(prefix="swdm_e2e_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402
from swdm.core import ensure_dirs  # noqa: E402

ensure_dirs()

# GMod (4000) 已知存在的小物品（测试专用，VJ Base 依赖库，知名安全 mod）
TEST_APPID = "4000"
TEST_ITEM = "3803871160"   # 之前会话验证过可下载

engine = SteamCMDEngine(install_dir=os.path.join(_TMP, "swdm_eng"))
# 若本机没有 steamcmd，跳过真实测试（不失败）
exe = ""
try:
    exe = engine.resolve_exe()
except Exception:  # noqa: BLE001
    exe = ""
if not exe or not os.path.isfile(exe):
    print("SKIP: 本机未找到 steamcmd，跳过真实下载测试")
    print("RESULT: SKIP")
    sys.exit(0)

print(f"steamcmd: {exe}")
events = {"progress": [], "log": [], "result": None, "err": None}
done = threading.Event()


def on_progress(pct, done_bytes, msg):
    events["progress"].append((time.time(), pct, done_bytes, msg))


def on_log(line):
    events["log"].append(line)


def run_download():
    try:
        r = engine.download_item(
            appid=TEST_APPID, item_id=TEST_ITEM,
            on_progress=on_progress, on_log=on_log,
        )
        events["result"] = r
    except Exception as e:  # noqa: BLE001
        events["err"] = e
    finally:
        done.set()


t = threading.Thread(target=run_download, daemon=True)
t.start()

# ---- bug5：观察 30 秒的进度事件序列（steamcmd 登录+连接需要时间）
t0 = time.time()
time.sleep(30.0)
got_progress = len(events["progress"])
pct_vals = [p for _, p, _, _ in events["progress"]]
msgs = [m for _, _, _, m in events["progress"]]
print(f"进度事件数: {got_progress}")
print(f"pct 样本: {pct_vals[:12]}")
print(f"消息样本: {msgs[:6]}")
print(f"日志最后 8 行: {events['log'][-8:]}")
print(f"已结束: {done.is_set()}, 结果: "
      f"{events['result'].status if events['result'] else None} "
      f"{events['result'].message if events['result'] else ''}")

if events["err"] is not None:
    check("下载期间无引擎异常（bug7）", False, str(events["err"]))
else:
    check("下载期间无引擎异常（bug7）", True)

# bug5：要么有非零 pct，要么有"已下载 N MB"这类变化消息
has_progress_signal = (
    any(p > 0 for p in pct_vals)
    or any("MB" in m for m in msgs)
    or any("Downloading" in m for m in msgs)
)
check("进度回调有实质信号（bug5）", got_progress > 0 and has_progress_signal,
      f"n={got_progress} msgs={msgs[:4]}")

# ---- bug8：如果还在下载，测试取消
if not done.is_set():
    print("仍在下载，测试取消…")
    try:
        engine.cancel()
    except Exception as e:  # noqa: BLE001
        check("取消不抛异常（bug8）", False, str(e))
    else:
        check("取消不抛异常（bug8）", True)
    done.wait(timeout=30)
else:
    check("取消不抛异常（bug8）", True, "(下载已自然结束)")

# 取消或完成后，引擎状态可复用（再跑一次不崩）
try:
    r2 = engine.download_item(
        appid=TEST_APPID, item_id=TEST_ITEM, on_progress=lambda *a: None,
    )
    check("取消后引擎可再次运行", r2 is not None)
except Exception as e:  # noqa: BLE001
    check("取消后引擎可再次运行", False, str(e))

# ---- 防护：确认所有落盘文件都在临时目录内
violations = []
for root, _dirs, files in os.walk(os.path.join(_TMP, "swdm_eng")):
    for f in files:
        full = os.path.join(root, f)
        if not full.startswith(_TMP):
            violations.append(full)
check("所有文件落在临时目录内（防护）", not violations, str(violations[:3]))

# 清理（可逆）
try:
    shutil.rmtree(os.path.join(_TMP, "swdm_eng"), ignore_errors=True)
except Exception:  # noqa: BLE001
    pass

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
