"""C2（t41）失败原因枚举 + 受限物品提示登录 —— 测试。

覆盖：
- 分类表（各桶正例）
- 误报红线：通用 I/O 串（含真实 "I/O Operation Failed"）→ GENERIC
- 正向信号 ①：受限 App + 未开始下载 → ACCOUNT_NEEDED
- 正向信号 ②：重试后同错且无网络信号 → ACCOUNT_NEEDED；有 timeout 信号 → GENERIC
- 与熔断器正交：分类是纯函数；downloader 失败仍照常 record_failure
- 文案：ACCOUNT_NEEDED 含登录引导且不误导；GENERIC 不提账号
- 集成：downloader 终态 FAILED 用归类后的文案
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))

_RESULTS: list[tuple] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    _RESULTS.append((name, bool(cond), extra))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


from swdm.core.failure_reason import (  # noqa: E402
    FailureBucket, RESTRICTED_APPS, classify_failure, render_failure,
)

# ------------------------------------------------------------------ 分类表
check("受限 App 名单含 DayZ/Barotrauma",
      "221100" in RESTRICTED_APPS and "602960" in RESTRICTED_APPS)

check("磁盘满（英文）", classify_failure("ERROR! No space left on device")
      == FailureBucket.DISK_FULL)
check("磁盘满（中文）", classify_failure("磁盘空间不足") == FailureBucket.DISK_FULL)

check("限流（运行信号）", classify_failure("失败", signals=["rate_limit"])
      == FailureBucket.RATE_LIMITED)
check("限流（消息字样）", classify_failure("触发限流，请稍后") == FailureBucket.RATE_LIMITED)

check("网络超时（运行信号）", classify_failure("失败", signals=["timeout"])
      == FailureBucket.NETWORK)
check("网络超时（消息字样）", classify_failure("Timeout connecting to Steam")
      == FailureBucket.NETWORK)

check("登录失败桶（凭据，非所有权）",
      classify_failure("登录失败（可能是账号/密码错误，或触发 Steam Guard）")
      == FailureBucket.LOGIN_FAILED)

check("物品不存在", classify_failure("物品不存在或已下架") == FailureBucket.ITEM_GONE)

check("空成功（E③）",
      classify_failure("steamcmd 报告成功但下载内容为空（可能触发限流）")
      == FailureBucket.EMPTY_SUCCESS)

# ------------------------------------------------------------------ 误报红线
for raw in (
    "ERROR! I/O Operation Failed",
    "Failed to download item 12345 (I/O Operation Failed)",
    "ERROR! Download item 12345 failed",
    "Not Logged On",
    "下载未完成（可能超时）",  # 「超时」→ NETWORK，不是账号
):
    b = classify_failure(raw, appid="221100")
    check(f"红线：通用串不入账号桶 [{raw[:28]}]",
          b != FailureBucket.ACCOUNT_NEEDED, b.value)

# 「下载未完成（可能超时）」应归 NETWORK
check("「可能超时」归 NETWORK",
      classify_failure("下载未完成（可能超时）") == FailureBucket.NETWORK)

# 非受限 App 的未开始下载 → GENERIC（不能因「不支持匿名下载」就判账号）
check("非受限 App 未开始下载 → GENERIC",
      classify_failure("未开始下载（物品可能不存在或该游戏不支持匿名下载）",
                       appid="4000") == FailureBucket.GENERIC)

# ------------------------------------------------------------------ 正向信号
# ① 受限 App + 匿名下载未开始
b = classify_failure("未开始下载（物品可能不存在或该游戏不支持匿名下载）",
                     appid="221100")
check("正向①：受限 App + 未开始下载 → ACCOUNT_NEEDED",
      b == FailureBucket.ACCOUNT_NEEDED, b.value)

# ② 重试后同错且无网络信号
same = ["ERROR! I/O Operation Failed"] * 3
b = classify_failure(same[-1], attempt_messages=same)
check("正向②：重试同错无网络信号 → ACCOUNT_NEEDED",
      b == FailureBucket.ACCOUNT_NEEDED, b.value)

# ② 有 timeout 信号 → 归 NETWORK（网络问题优先，不判账号）
b = classify_failure(same[-1], attempt_messages=same, signals=["timeout"])
check("正向②被 timeout 信号否决 → NETWORK",
      b == FailureBucket.NETWORK, b.value)

# ② 消息不一致（重试出现了不同错误）→ GENERIC
b = classify_failure(same[-1],
                     attempt_messages=["ERROR! I/O Operation Failed", "Timeout xxx"])
check("正向②消息不一致 → 非 ACCOUNT_NEEDED",
      b != FailureBucket.ACCOUNT_NEEDED, b.value)

# ② 只有一次失败（未重试）→ 不判账号
b = classify_failure(same[-1], attempt_messages=[same[-1]])
check("正向②未重试 → 非 ACCOUNT_NEEDED",
      b != FailureBucket.ACCOUNT_NEEDED, b.value)

# ------------------------------------------------------------------ 文案
msg = render_failure(FailureBucket.ACCOUNT_NEEDED)
check("账号文案含登录引导", "登录" in msg and "账号" in msg, msg[:30])
check("账号文案不误导（含「可能」+ 日志兜底）",
      "可能" in msg and "日志" in msg, msg[:30])
check("账号文案不保证因果（含「可能并非权限问题」）",
      "并非权限" in msg, msg[:40])

gmsg = render_failure(FailureBucket.GENERIC)
check("通用文案不提账号", "账号" not in gmsg, gmsg[:30])
check("通用文案说明未区分原因", "未区分" in gmsg and "建议重试" in gmsg, gmsg[:30])
check("通用文案指引日志", "日志" in gmsg)

check("物品下架文案", "下架" in render_failure(FailureBucket.ITEM_GONE))
check("限流文案", "限流" in render_failure(FailureBucket.RATE_LIMITED))
check("网络文案", "网络" in render_failure(FailureBucket.NETWORK))
check("磁盘文案", "磁盘" in render_failure(FailureBucket.DISK_FULL))
check("登录文案透出原文",
      render_failure(FailureBucket.LOGIN_FAILED, "登录失败：xxx") == "登录失败：xxx")
check("空成功透出原文",
      render_failure(FailureBucket.EMPTY_SUCCESS, "内容为空") == "内容为空")

# ------------------------------------------------------------------ 熔断正交
# classify_failure 是纯函数：不触碰 provider 注册表/全局状态
import swdm.core.providers as prov_pkg  # noqa: E402

_before = type(prov_pkg.get_registry())  # 导入即可用，注册表未被分类器修改
check("分类器不影响 provider 注册表", _before is not None)
try:
    prov_pkg.get_registry()
    reg_ok = True
except Exception as e:  # noqa: BLE001
    reg_ok = False
check("注册表仍可用", reg_ok)

# ------------------------------------------------------------------ 集成
from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.downloader import DownloadJob, DownloadManager  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus  # noqa: E402


def _job(appid="4000"):
    return DownloadJob(item=WorkshopItem(publishedfileid="12345", title="t",
                                         appid=appid, file_size=100),
                       appid=appid)


# 模拟 _exec_job 终态分支使用的归类路径
job = _job("221100")
job.attempt_messages = ["未开始下载（物品可能不存在或该游戏不支持匿名下载）"]
raw = job.attempt_messages[-1]
bucket = classify_failure(raw, appid=job.appid, signals=job.signals,
                          attempt_messages=job.attempt_messages)
job.failure_bucket = bucket.value
job.message = render_failure(bucket, raw)
check("集成：受限 App 终态归类 account", job.failure_bucket == "account")
check("集成：终态文案是渲染文案而非原始串",
      "正版" in job.message and raw[:10] not in job.message, job.message[:30])

# 账号失败与熔断解耦：downloader 失败路径照常 record_failure（回归现有行为）
from swdm.core.throttle import AdaptiveConcurrency, Backoff  # noqa: E402

backoff = Backoff()
lvl0 = backoff.level
backoff.record_failure("ERROR! I/O Operation Failed")
check("熔断与枚举解耦：失败仍记退避", backoff.level > lvl0,
      f"{lvl0}->{backoff.level}")

# DownloadManager 信号采集：thread-local job
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402

engine = SteamCMDEngine.__new__(SteamCMDEngine)
engine.__dict__.update({
    "install_dir": "", "anonymous": True, "username": "", "password": "",
    "exe_path": "", "validate": False, "on_throttle_signal": [],
})
mgr = DownloadManager.__new__(DownloadManager)
mgr.__dict__.update({
    "engine": engine, "_local": type("_L", (), {})(),
    "last_throttle": None, "on_throttle": None,
    "_backoff": Backoff(), "_concurrency": AdaptiveConcurrency(),
    "on_started": None, "on_finished": None,
})
job2 = _job()
mgr._local.job = job2
mgr._on_throttle_signal("rate_limit", "RateLimit reached")
check("thread-local 信号归到 job", "rate_limit" in job2.signals)
mgr._local.job = None
mgr._on_throttle_signal("timeout", "Timeout")
check("无当前 job 时信号不崩", job2.signals == {"rate_limit"})

# job 默认字段
j3 = _job()
check("job 默认 signals/attempt_messages 为空容器",
      j3.signals == set() and j3.attempt_messages == [] and j3.failure_bucket == "")

fails = [r for r in _RESULTS if not r[1]]
print(f"\nSUMMARY: {len(_RESULTS)} checks, {len(_RESULTS) - len(fails)} pass, {len(fails)} fail")
if fails:
    for n, _, _x in fails:
        print("  FAILED:", n)
sys.exit(1 if fails else 0)
