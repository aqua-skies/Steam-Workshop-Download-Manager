"""退避 / 抖动 / 并发自适应 / 续传 / 进度平滑 单元测试。

全部使用 mock 引擎（重放 tests/fixtures 下的真实 steamcmd 输出），
不发起任何网络请求，也不依赖 steamcmd 二进制。

运行：$env:PYTHONUTF8=1; python tests/test_throttle.py
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
import threading
import time

# 必须在导入 swdm 之前设置：让 paths.DATA_DIR 指向临时目录，隔离库与日志
_TMP = tempfile.mkdtemp(prefix="swdm_throttle_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

import swdm.core.downloader as dl  # noqa: E402
from swdm.core import (  # noqa: E402
    DownloadJob,
    DownloadManager,
    JobStatus,
    ModLibrary,
    SteamCMDEngine,
    WorkshopItem,
    ensure_dirs,
)
from swdm.core.steamcmd_engine import DownloadStatus  # noqa: E402
from swdm.core.throttle import (  # noqa: E402
    AdaptiveConcurrency,
    Backoff,
    ProgressSmoother,
    classify_steamcmd_line,
    jittered,
)

ensure_dirs()

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

out = _io.StringIO()


def p(*a):
    print(*a, file=out)


ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def _mkitem(pid="3802244270", size=1816113, title="Dynamic Flashlight"):
    return WorkshopItem(publishedfileid=pid, appid="4000", title=title, file_size=size)


# ================================================================ 引擎 mock
class ReplayEngine(SteamCMDEngine):
    """重放 fixture 输出，替代真实 steamcmd 子进程（无网络、无二进制依赖）。

    fixtures 为调用顺序队列（串行场景确定性）；fail_ids 按 item id 固定失败，
    供并发场景使用——并发调度顺序不确定，不能用"第 N 次调用"来指定失败者。
    """

    def __init__(self, fixtures, install_dir, fail_ids=(), **kw):
        super().__init__(install_dir=install_dir, **kw)
        self._fixtures = [fixtures] if isinstance(fixtures, str) else list(fixtures)
        self._fail_ids = {str(i) for i in fail_ids}
        self.calls: list[str] = []
        self.progress_events: list[tuple] = []

    @staticmethod
    def _item_id_of(commands):
        for i, c in enumerate(commands):
            if c == "+workshop_download_item" and i + 2 < len(commands):
                return str(commands[i + 2])
        return ""

    def _run(self, commands, on_line=None, feed_stdin=""):
        self._cancel_flag.clear()
        item_id = self._item_id_of(commands)
        if item_id in self._fail_ids:
            fx = "steamcmd_rate_limit.txt"
        else:
            fx = self._fixtures.pop(0) if self._fixtures else "steamcmd_success.txt"
        self.calls.append(fx)
        with open(os.path.join(FIXTURES, fx), encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if not line.strip():
                    continue
                if on_line:
                    on_line(line)
        return 0


class HangingEngine(SteamCMDEngine):
    """模拟卡死的 steamcmd：不输出任何行，直到被取消。"""

    def _run(self, commands, on_line=None, feed_stdin=""):
        self._cancel_flag.clear()
        deadline = time.time() + 30
        while time.time() < deadline and not self._cancel_flag.is_set():
            time.sleep(0.1)
        return 0


class _SleepRecorder:
    """替换 downloader 模块的 time，记录 sleep 调用（不真正休眠）。"""

    def __init__(self, real):
        self._real = real
        self.sleeps: list[float] = []

    def sleep(self, seconds):
        self.sleeps.append(float(seconds))

    def __getattr__(self, name):
        return getattr(self._real, name)


# ================================================================ 1. 抖动
p("== 1. 随机抖动 ==")
rng = random.Random(1234)
vals = [jittered(2.0, 0.4, rng) for _ in range(200)]
check("抖动在 [base*(1-spread), base*(1+spread)] 内",
      all(1.2 <= v <= 2.8 for v in vals), f"min={min(vals):.2f} max={max(vals):.2f}")
check("抖动确实随机（出现多种值）", len(set(round(v, 3) for v in vals)) > 10, f"{len(set(vals))} 种")
check("抖动有方差", abs(sum(vals) / len(vals) - 2.0) < 0.2, f"均值={sum(vals) / len(vals):.3f}")
check("base<=0 时抖动为 0", jittered(0.0, 0.4, rng) == 0.0)
check("spread 钳制到 [0,1]", 0.0 <= jittered(2.0, 5.0, rng) <= 4.0)

# ================================================================ 2. 指数退避
p("== 2. 全局指数退避 ==")
bo = Backoff(base=2.0, factor=2.0, cap=120.0, jitter_spread=0.0, rng=random.Random(7))
check("初始等级 0", bo.level == 0)
check("初始基准延迟 = base", abs(bo.level_delay - 2.0) < 1e-9, f"{bo.level_delay}")
d1 = bo.record_failure()
check("失败 1: base*factor=4s", abs(d1 - 4.0) < 1e-9 and bo.level == 1, f"delay={d1} level={bo.level}")
d2 = bo.record_failure()
d3 = bo.record_failure()
check("失败 2: 8s", abs(d2 - 8.0) < 1e-9, f"{d2}")
check("失败 3: 16s（指数增长）", abs(d3 - 16.0) < 1e-9, f"{d3}")
for _ in range(10):
    bo.record_failure()
check("退避有上限 cap=120", abs(bo.level_delay - 120.0) < 1e-9, f"{bo.level_delay}")
bo.record_success()
check("成功后等级 -1（缓慢恢复）", bo.level == 12, f"level={bo.level}")
while bo.level > 0:
    bo.record_success()
check("连续成功最终回到基线", bo.level == 0 and abs(bo.level_delay - 2.0) < 1e-9)
bo2 = Backoff(base=2.0, cap=120.0, jitter_spread=0.3, rng=random.Random(3))
check("含抖动的退避值 > 0", all(bo2.record_failure() > 0 for _ in range(5)))
bo3 = Backoff(base=2.0, cap=120.0)
bo3.nudge()
check("软信号 nudge 抬升等级", bo3.level == 1, f"level={bo3.level}")
for _ in range(4):
    bo3.nudge(max_level=3)
check("nudge 不超过 max_level", bo3.level == 3, f"level={bo3.level}")
bo2.reset()
check("reset 回到基线", bo2.level == 0)

# ================================================================ 3. 并发自适应
p("== 3. 并发自适应 ==")
ac = AdaptiveConcurrency(max_concurrent=4, min_concurrent=1, successes_to_raise=3, step=1)
check("初始并发 = 上限", ac.current == 4)
check("失败 -> 立刻降到 1", ac.on_failure("rate_limit") == 1 and ac.current == 1)
s1 = ac.on_success()
s2 = ac.on_success()
s3 = ac.on_success()
check("一次/两次成功不回升", s1 == 1 and s2 == 1, f"{s1},{s2}")
check("三次持续成功 -> 回升到 2", s3 == 2 and ac.current == 2, str(s3))
s4, s5, s6 = ac.on_success(), ac.on_success(), ac.on_success()
check("再三次成功 -> 回升到 3", s4 == 2 and s5 == 2 and s6 == 3, f"{s4},{s5},{s6}")
s7, s8, s9 = ac.on_success(), ac.on_success(), ac.on_success()
check("达上限后不再上升", s7 == 3 and s9 == 4 and ac.current == 4, f"{s7},{s9}")
ac.on_failure("timeout")
check("再次失败立刻降回 1", ac.current == 1)
ac.reset()
check("reset 恢复上限", ac.current == 4)
ac2 = AdaptiveConcurrency(max_concurrent=1)
check("上限 1 时恒为 1", ac2.current == 1 and ac2.on_failure() == 1 and ac2.on_success() == 1)

# ================================================================ 4. steamcmd 特征识别
p("== 4. steamcmd 限流/超时特征识别 ==")
check("RateLimit -> rate_limit", classify_steamcmd_line("ERROR! Download item 1 failed (RateLimitExceeded)") == "rate_limit")
check("rate limit -> rate_limit", classify_steamcmd_line("rate limit exceeded, try later") == "rate_limit")
check("429 too many -> rate_limit", classify_steamcmd_line("HTTP 429 Too Many Requests") == "rate_limit")
check("Timeout -> timeout", classify_steamcmd_line("Timeout downloading item 1") == "timeout")
check("TimeoutException -> timeout", classify_steamcmd_line("TimeoutException after 30000ms") == "timeout")
check("timed out -> timeout", classify_steamcmd_line("Connection timed out") == "timeout")
check("Retrying... -> retry", classify_steamcmd_line("Connecting anonymously to Steam Public...Retrying...") == "retry")
check("rate_limit 优先于 timeout", classify_steamcmd_line("RateLimit: timeout reached") == "rate_limit")
check("Success 行无特征", classify_steamcmd_line('Success. Downloaded item 3802244270 to "..." (1816113 bytes)') is None)
check("Downloading 行无特征", classify_steamcmd_line("Downloading item 3802244270 ...") is None)
check("空行/None 无特征", classify_steamcmd_line("") is None and classify_steamcmd_line(None) is None)
# 用真实 fixture 逐行扫描，确保正常输出不误报
for fx in ("steamcmd_success.txt", "steamcmd_resume.txt"):
    hits = []
    with open(os.path.join(FIXTURES, fx), encoding="utf-8") as _fh:
        for line in _fh:
            k = classify_steamcmd_line(line.rstrip("\n"))
            if k:
                hits.append((k, line.strip()[:60]))
    if fx == "steamcmd_resume.txt":
        check(f"{fx}: 仅 Retrying 软信号", [k for k, _ in hits] == ["retry"], str(hits))
    else:
        check(f"{fx}: 正常输出零误报", not hits, str(hits))
rl_hits = sum(1 for line in open(os.path.join(FIXTURES, "steamcmd_rate_limit.txt"), encoding="utf-8")
             if classify_steamcmd_line(line.rstrip("\n")))
to_hits = [(classify_steamcmd_line(l.rstrip("\n")),) for l in
           open(os.path.join(FIXTURES, "steamcmd_timeout.txt"), encoding="utf-8")]
check("rate_limit fixture 命中 1 次硬信号", rl_hits == 1, str(rl_hits))
check("timeout fixture 命中 timeout", any(k == "timeout" for (k,) in to_hits), str(to_hits))

# ================================================================ 5. 进度平滑
p("== 5. 进度平滑（10Hz 限流 / 不倒退 / 速度 ETA）==")
t0 = 0.0
sm = ProgressSmoother(min_interval=0.1)


def now_plus(dt):
    global t0
    t0 += dt
    return t0


sm.reset(0, now=0.0)
a = sm.feed(1_000_000, 10_000_000, now=now_plus(0.001))   # 立即第二次：应被限流
check("连续喂入被限流（返回 None）", a is None)
b = sm.feed(2_000_000, 10_000_000, now=now_plus(0.15))
check("超过 min_interval 后下发", b is not None and b["bytes"] == 2_000_000)
check("百分比正确", b["percent"] == 20, str(b["percent"]))
c = sm.feed(500_000, 10_000_000, now=now_plus(0.2))   # 更小的观测
check("字节不倒退", c is not None and c["bytes"] == 2_000_000, str(c["bytes"]))
check("force 绕过限流", sm.feed(10_000_000, 10_000_000, force=True, now=now_plus(0.001)) is not None)
sm2 = ProgressSmoother(min_interval=0.1)
sm2.reset(0, now=1.0)
e = sm2.feed(5_000_000, 10_000_000, now=2.0)   # 1 秒下了 5MB -> 5 MB/s
check("速度估算 > 0", e is not None and e["speed_mbps"] > 0, f"{e['speed_mbps']:.2f} MB/s")
check("ETA 估算 > 0", e is not None and e["eta"] > 0, f"{e['eta']:.1f}s")
check("label 含百分比与速度", "50%" in e["label"] and "MB/s" in e["label"], e["label"])
f2 = sm2.feed(10_000_000, 10_000_000, force=True, now=3.0)
check("完成时 percent=100", f2["percent"] == 100)
sm3 = ProgressSmoother()
sm3.reset(0, now=1.0)
g = sm3.feed(0, 0, now=1.2)
check("总大小未知 -> percent=-1（不确定进度）", g is not None and g["percent"] == -1, str(g["percent"] if g else None))
check("不确定进度 label 为中文", g is not None and "下载中" in g["label"], g["label"] if g else "")

# ================================================================ 6. 引擎解析（mock，无网络）
p("== 6. steamcmd_engine 输出解析与续传钩子（mock）==")
tmp_install = tempfile.mkdtemp(prefix="swdm_engine_")
eng = ReplayEngine("steamcmd_success.txt", tmp_install)
events = []
sig = []
eng.on_throttle_signal = lambda kind, line: sig.append((kind, line.strip()[:50]))
res = eng.download_item("4000", "3802244270",
                        on_progress=lambda pct, done, msg: events.append((pct, done, msg)),
                        total_hint=1816113)
check("成功 fixture 解析为 SUCCESS", res.status == DownloadStatus.SUCCESS, res.status.value)
check("成功字节数来自 Success 行", res.bytes_done == 1816113, str(res.bytes_done))
# 1.3.4 进度重做后，"Downloading item" 行即发射 1%（而非不确定的 -1），
# 让用户立刻看到进度条动；这里验"开始事件"的语义不变
check("on_progress 首事件 = 下载开始",
      events and events[0][0] == 1 and "正在下载物品" in events[0][2],
      str(events[0]) if events else "")
check("on_progress 末事件 = 100%", events and events[-1][0] == 100, str(events[-1]) if events else "")
check("成功输出未触发节流信号", not sig, str(sig))
# 自更新阶段的 [0%] 行在 Success 之后，不得被当成工坊进度
check("Success 之后的 [0%] 行不产生进度事件",
      all(pct != 0 for pct, _, _ in events[1:-1]) or len(events) <= 2, str(events))

eng2 = ReplayEngine("steamcmd_rate_limit.txt", tmp_install)
sig2 = []
eng2.on_throttle_signal.append(lambda kind, line: sig2.append(kind))
res2 = eng2.download_item("4000", "3802244270")
check("RateLimit fixture -> FAILED", res2.status == DownloadStatus.FAILED, res2.status.value)
check("RateLimit 特征被识别", "rate_limit" in sig2, str(sig2))
check("失败消息携带错误行", "RateLimit" in (res2.message or ""), res2.message)

eng3 = ReplayEngine("steamcmd_timeout.txt", tmp_install)
sig3 = []
eng3.on_throttle_signal.append(lambda kind, line: sig3.append(kind))
res3 = eng3.download_item("4000", "3802244270")
check("Timeout fixture -> FAILED", res3.status == DownloadStatus.FAILED, res3.status.value)
check("Timeout 特征被识别", "timeout" in sig3, str(sig3))

eng4 = ReplayEngine("steamcmd_resume.txt", tmp_install)
sig4 = []
eng4.on_throttle_signal.append(lambda kind, line: sig4.append(kind))
res4 = eng4.download_item("4000", "3803469767")
check("Resume fixture（含 Retrying...）成功", res4.status == DownloadStatus.SUCCESS, res4.status.value)
check("Retrying 软信号被识别", "retry" in sig4, str(sig4))

# ---- ensure_partial 续传钩子
item_dir = os.path.join(tmp_install, "steamapps", "workshop", "content", "4000", "999000111")
os.makedirs(item_dir, exist_ok=True)
with open(os.path.join(item_dir, "gma.bin"), "wb") as fh:
    fh.write(b"A" * (2 * 1024 * 1024 + 1234))
eng5 = ReplayEngine("steamcmd_success.txt", tmp_install)
check("ensure_partial 报告已有字节数", eng5.ensure_partial("999000111", "4000") == 2 * 1024 * 1024 + 1234,
      str(eng5.ensure_partial("999000111", "4000")))
check("ensure_partial 不存在的物品 = 0", eng5.ensure_partial("000000000", "4000") == 0)
check("ensure_partial 可省略 appid", eng5.ensure_partial("999000111") == 2 * 1024 * 1024 + 1234)
os.makedirs(os.path.join(tmp_install, "steamapps", "workshop", "content", "4000", "888000222"), exist_ok=True)
with open(os.path.join(tmp_install, "steamapps", "workshop", "content", "4000", "888000222", "x.txt"), "wb") as fh:
    fh.write(b"B" * 500)
check("ensure_partial 空目录子文件计数", eng5.ensure_partial("888000222") == 500)

# ---- 停滞看门狗
hang_dir = tempfile.mkdtemp(prefix="swdm_hang_")
hang = HangingEngine(hang_dir, stall_timeout=0.5)
hres = hang.download_item("4000", "777000333")
check("停滞超时 -> FAILED（非 CANCELLED）",
      hres.status == DownloadStatus.FAILED, f"{hres.status.value}: {hres.message}")
check("停滞消息含'停滞超时'", "停滞超时" in (hres.message or ""), hres.message)

# ================================================================ 7. DownloadManager 集成（mock）
p("== 7. DownloadManager 集成：抖动/退避/并发自适应/续传 ==")
lib = ModLibrary()

# 7a. 失败一次后重试成功：退避升级 + 并发降级 + 恢复
mgr_dir = tempfile.mkdtemp(prefix="swdm_mgr_")
seq = ReplayEngine(["steamcmd_rate_limit.txt", "steamcmd_success.txt"], mgr_dir)
mgr = DownloadManager(seq, lib, max_concurrent=2, auto_retry=1, jitter_base=0.05)
mgr_sig = []
mgr.on_throttle = lambda kind, line: mgr_sig.append(kind)
check("管理器自动桥接引擎节流信号", mgr._on_throttle_signal in seq.on_throttle_signal)
mgr.start()
job = mgr.enqueue(_mkitem("3802244270"), "4000")
t_end = time.time() + 60
while job.status.value not in ("success", "failed", "cancelled") and time.time() < t_end:
    time.sleep(0.1)
mgr.stop()
check("失败后自动重试成功", job.status == JobStatus.SUCCESS, job.status.value)
check("重试次数 = 1", job.attempt == 1, str(job.attempt))
check("rate_limit 信号到达管理器", "rate_limit" in mgr_sig, str(mgr_sig))
check("并发已降到 1", mgr._concurrency.current == 1, str(mgr._concurrency.current))
check("退避等级已升级（>=1）", mgr._backoff.level >= 1, str(mgr._backoff.level))

# 7b. 续传提示：预置部分内容，作业启动时应报告"续传中"
mgr_dir2 = tempfile.mkdtemp(prefix="swdm_mgr2_")
eng6 = ReplayEngine("steamcmd_success.txt", mgr_dir2)
partial_dir = os.path.join(mgr_dir2, "steamapps", "workshop", "content", "4000", "555000666")
os.makedirs(partial_dir, exist_ok=True)
with open(os.path.join(partial_dir, "part.bin"), "wb") as fh:
    fh.write(b"C" * (3 * 1024 * 1024))
mgr2 = DownloadManager(eng6, ModLibrary(), max_concurrent=1, auto_retry=0, jitter_base=0.05)
msgs = []
# on_progress 是观察者列表（不可直接赋值覆盖，否则 _fire_progress
# 迭代函数对象抛 TypeError 致 worker 线程死亡、任务被 stop() 取消）
mgr2.add_listener(progress=lambda j: msgs.append(j.message))
mgr2.start()
job2 = mgr2.enqueue(_mkitem("555000666"), "4000")
t_end2 = time.time() + 60
while job2.status.value not in ("success", "failed", "cancelled") and time.time() < t_end2:
    time.sleep(0.1)
mgr2.stop()
check("续传任务最终成功", job2.status == JobStatus.SUCCESS, job2.status.value)
check("续传提示写入 job.message", any("续传中（已有 3.0 MB）" in m for m in msgs), str(msgs[:3]))
check("resumed_bytes 记录已有字节", job2.resumed_bytes == 3 * 1024 * 1024, str(job2.resumed_bytes))
check("部分内容在下载后仍保留",
      os.path.getsize(os.path.join(partial_dir, "part.bin")) == 3 * 1024 * 1024)

# 7c. 并发降级（并发场景，失败者按 item id 固定，不受调度顺序影响）
mgr_dir3 = tempfile.mkdtemp(prefix="swdm_mgr3_")
pat = ReplayEngine("steamcmd_success.txt", mgr_dir3, fail_ids=("111000000",))
mgr3 = DownloadManager(pat, ModLibrary(), max_concurrent=3, auto_retry=0, jitter_base=0.05)
mgr3.start()
jobs = [mgr3.enqueue(_mkitem(f"111000{i:03d}"), "4000") for i in range(3)]
t_end3 = time.time() + 90
while any(j.status.value not in ("success", "failed", "cancelled") for j in jobs) and time.time() < t_end3:
    time.sleep(0.2)
mgr3.stop()
check("3 个任务全部终态", all(j.status.value in ("success", "failed") for j in jobs),
      str([j.status.value for j in jobs]))
check("指定失败者 FAILED、其余成功",
      jobs[0].status == JobStatus.FAILED and
      all(j.status == JobStatus.SUCCESS for j in jobs[1:]),
      str([j.status.value for j in jobs]))
check("失败使并发上限降到 1", mgr3._concurrency.current == 1, str(mgr3._concurrency.current))

# 7c2. 并发回升：上限 3 但逐个入队（执行必然串行、顺序确定），
#       1 次失败 + 3 次持续成功 -> 从 1 回升到 2
mgr_dir3b = tempfile.mkdtemp(prefix="swdm_mgr3b_")
pat2 = ReplayEngine("steamcmd_success.txt", mgr_dir3b, fail_ids=("222000000",))
mgr3b = DownloadManager(pat2, ModLibrary(), max_concurrent=3, auto_retry=0, jitter_base=0.01)
mgr3b.start()


def _run_one(mgr, item_id):
    j = mgr.enqueue(_mkitem(item_id), "4000")
    t_end = time.time() + 40
    while j.status.value not in ("success", "failed", "cancelled") and time.time() < t_end:
        time.sleep(0.1)
    return j


jobs2 = [_run_one(mgr3b, "222000000"),
         _run_one(mgr3b, "222000001"),
         _run_one(mgr3b, "222000002"),
         _run_one(mgr3b, "222000003")]
mgr3b.stop()
check("回升场景：失败在前、三次成功在后",
      [j.status.value for j in jobs2] == ["failed", "success", "success", "success"],
      str([j.status.value for j in jobs2]))
check("失败降到 1 后，三次持续成功回升到 2",
      mgr3b._concurrency.current == 2, str(mgr3b._concurrency.current))

# 7d. 任务间抖动确实发生（记录 sleep，不真正休眠）
mgr_dir4 = tempfile.mkdtemp(prefix="swdm_mgr4_")
eng7 = ReplayEngine("steamcmd_success.txt", mgr_dir4)
rec = _SleepRecorder(dl.time)
dl.time = rec
try:
    mgr4 = DownloadManager(eng7, ModLibrary(), max_concurrent=1, auto_retry=0,
                           jitter_base=2.0, jitter_spread=0.4)
    mgr4.start()
    job4 = mgr4.enqueue(_mkitem("333000444"), "4000")
    t_end4 = time.time() + 60
    while job4.status.value not in ("success", "failed", "cancelled") and time.time() < t_end4:
        time.sleep(0.1)
    mgr4.stop()
finally:
    dl.time = rec._real
check("任务开始前发生了 sleep（抖动）", len(rec.sleeps) >= 1, f"{len(rec.sleeps)} 次")
check("抖动量在 [base*0.6, base*1.4] 内",
      len(rec.sleeps) >= 1 and all(1.2 <= s <= 2.8 for s in rec.sleeps), str(rec.sleeps))
check("抖动后任务仍成功", job4.status == JobStatus.SUCCESS, job4.status.value)

# 7e. 直接调用信号通道：硬信号降并发、软信号只轻退避
bo5 = Backoff()
ac5 = AdaptiveConcurrency(max_concurrent=3)
mgr5 = DownloadManager(SteamCMDEngine(anonymous=True), ModLibrary(),
                       max_concurrent=3, backoff=bo5, concurrency=ac5, jitter_base=0.0)
mgr5._on_throttle_signal("rate_limit", "RateLimitExceeded")
check("硬信号：并发->1", ac5.current == 1, str(ac5.current))
check("硬信号：退避等级 +1", bo5.level == 1, str(bo5.level))
mgr5._on_throttle_signal("retry", "Retrying...")
check("软信号：并发不变", ac5.current == 1, str(ac5.current))
check("软信号：退避等级 <= 3", 1 <= bo5.level <= 3, str(bo5.level))

# 7f. 失败时保留已落盘的部分内容（不清理 content/<appid>/<itemid>）
mgr_dir6 = tempfile.mkdtemp(prefix="swdm_mgr6_")
eng8 = ReplayEngine("steamcmd_rate_limit.txt", mgr_dir6)
keep_dir = os.path.join(mgr_dir6, "steamapps", "workshop", "content", "4000", "666000777")
os.makedirs(keep_dir, exist_ok=True)
with open(os.path.join(keep_dir, "keep.bin"), "wb") as _fh:
    _fh.write(b"D" * (1024 * 1024))
mgr6 = DownloadManager(eng8, ModLibrary(), max_concurrent=1, auto_retry=0, jitter_base=0.05)
msgs6 = []
mgr6.add_listener(progress=lambda j: msgs6.append(j.message))
mgr6.start()
job6 = mgr6.enqueue(_mkitem("666000777"), "4000")
t_end6 = time.time() + 60
while job6.status.value not in ("success", "failed", "cancelled") and time.time() < t_end6:
    time.sleep(0.1)
mgr6.stop()
check("失败任务终态为 FAILED", job6.status == JobStatus.FAILED, job6.status.value)
check("失败后部分内容仍保留在原处",
      os.path.isfile(os.path.join(keep_dir, "keep.bin"))
      and os.path.getsize(os.path.join(keep_dir, "keep.bin")) == 1024 * 1024)
check("失败任务也报告续传提示", any("续传中（已有 1.0 MB）" in m for m in msgs6), str(msgs6[:2]))

# 7g. 竞态回归：cancel() 不得覆盖已达终态（SUCCESS/FAILED）的 job。
# 复现窗口：worker 在 _exec_job 里刚置完终态、尚未移出 _active 时，
# stop()->cancel_all()->cancel() 抢先把 job 判成 CANCELLED 并登记，
# 真实结果被抹掉。用 hook 在置态后、收尾前注入 cancel 来确定性复现。
mgr_dir7 = tempfile.mkdtemp(prefix="swdm_mgr7_")
eng9 = ReplayEngine("steamcmd_success.txt", mgr_dir7)
mgr7 = DownloadManager(eng9, ModLibrary(), max_concurrent=1, auto_retry=0, jitter_base=0.0)
canceled_during_success = {"hit": False}
_orig_register = mgr7._register_to_library


def _hooked_register(job, result):
    # 成功路径已置完 job.status=SUCCESS，尚未移出 _active：
    # 此时 cancel_all 应保留终态、不覆盖
    canceled_during_success["hit"] = job.status == JobStatus.SUCCESS and job.id in mgr7._active
    mgr7.cancel(job.id)
    return _orig_register(job, result)


mgr7._register_to_library = _hooked_register
mgr7.start()
job7 = mgr7.enqueue(_mkitem("777000888"), "4000")
t_end7 = time.time() + 60
while job7.status.value not in ("success", "failed", "cancelled") and time.time() < t_end7:
    time.sleep(0.1)
# 关键断言：cancel 在 SUCCESS 已置、job 仍在 _active 时触发，终态须保留
check("cancel 不覆盖已置的 SUCCESS 终态",
      canceled_during_success["hit"] and job7.status == JobStatus.SUCCESS,
      job7.status.value)
# 等收尾路径把 job 登记进 _done（status 早于登记置位，直接读会空）
t_dedup = time.time() + 10
while job7 not in mgr7._done and time.time() < t_dedup:
    time.sleep(0.05)
check("cancel 后 job 只登记一次（_done 无重复）",
      sum(1 for j in mgr7._done if j.id == job7.id) == 1,
      str([j.status.value for j in mgr7._done if j.id == job7.id]))
mgr7.stop()

# 7h. 竞态回归：cancel() 对 FAILED 终态同样不覆盖
mgr_dir8 = tempfile.mkdtemp(prefix="swdm_mgr8_")
eng10 = ReplayEngine("steamcmd_rate_limit.txt", mgr_dir8)
mgr8 = DownloadManager(eng10, ModLibrary(), max_concurrent=1, auto_retry=0, jitter_base=0.0)
canceled_during_failed = {"hit": False}
_orig_log = mgr8.library.log_job


def _hooked_log(*a, **kw):
    # 失败路径已置完 job.status=FAILED，尚未移出 _active
    canceled_during_failed["hit"] = a and a[3] == "failed"
    mgr8.cancel(a[0])
    return _orig_log(*a, **kw)


mgr8.library.log_job = _hooked_log
mgr8.start()
job8 = mgr8.enqueue(_mkitem("888000999"), "4000")
t_end8 = time.time() + 60
while job8.status.value not in ("success", "failed", "cancelled") and time.time() < t_end8:
    time.sleep(0.1)
check("cancel 不覆盖已置的 FAILED 终态",
      canceled_during_failed["hit"] and job8.status == JobStatus.FAILED,
      job8.status.value)
mgr8.stop()

# ================================================================ 结果
result = "\n".join(out.getvalue().splitlines())
print(result)
report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_throttle_out.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
