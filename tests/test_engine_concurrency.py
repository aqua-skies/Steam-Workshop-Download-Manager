"""引擎并发与取消竞态测试（bug7/8 复现与回归）。

bug7 现象：下载两个物品时其中一个报
  AttributeError: 'NoneType' object has no attribute 'poll'
根因：多任务共享 engine 的实例字段 self._proc，一个任务的 _run 把它置 None
或覆盖为另一任务的进程。
bug8 现象：下载中点取消，软件直接关闭。
根因：cancel() 与 _run 的 finally 竞态 + 无异常防护。

本测试用假进程并发驱动 _run / cancel，验证不再出现 NoneType 与异常外泄。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = os.environ.get("APPDATA")
if not _TMP:
    _TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_engine")
    os.makedirs(_TMP, exist_ok=True)
    os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


class FakeProc:
    """最小化的 Popen 替身，覆盖 _run 用到的接口。"""
    def __init__(self, lines=()):
        self.stdout = io.BytesIO(b"".join(l.encode() + b"\n" for l in lines))
        self.stdin = io.BytesIO()
        self.returncode = 0
        self._terminated = False
        self._waited = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self._waited = True
        return self.returncode

    def terminate(self):
        self._terminated = True


def _make_engine(monkeypatch_popen):
    from swdm.core.steamcmd_engine import SteamCMDEngine

    eng = SteamCMDEngine(install_dir=os.path.join(_TMP, "eng"))
    # 跳过真实 steamcmd 可执行文件解析
    eng.resolve_exe = lambda: "fake-steamcmd.exe"
    if monkeypatch_popen:
        subprocess.Popen = monkeypatch_popen
    return eng


# ---- 1) 并发两个 _run：旧代码这里会 NoneType 崩溃
errors: list[str] = []
procs = []
_REAL_POPEN = subprocess.Popen


def fake_popen_factory():
    def _popen(*a, **k):
        p = FakeProc(lines=["Logging in user", "Downloading item 111"])
        procs.append(p)
        return p
    return _popen


eng = _make_engine(fake_popen_factory())


def run_once(tag):
    try:
        eng._run(["+workshop_download_item", "4000", tag], on_line=lambda _l: None)
    except Exception as e:  # noqa: BLE001
        errors.append(f"{tag}: {type(e).__name__}: {e}")


threads = [threading.Thread(target=run_once, args=(t,), daemon=True)
           for t in ("111", "222")]
for t in threads:
    t.start()
    time.sleep(0.05)   # 制造交错
for t in threads:
    t.join(timeout=10)
check("并发两任务 _run 无 NoneType 异常", not errors, str(errors))
subprocess.Popen = _REAL_POPEN   # 恢复，避免影响后续模块导入

# ---- 2) 取消与 _run 并行：cancel 不应抛异常、不应让 _run 崩溃
errors2 = []
cancel_errs = []


def fake_popen_slow():
    def _popen(*a, **k):
        # stdout 阻塞读：用管道而非 BytesIO，使 for 循环挂起等待数据
        r, w = os.pipe()
        # 立即有一行，之后阻塞（进程"卡住"）
        os.write(w, b"Logging in user\n")
        return FakePipeProc(r, w)
    return _popen

class FakePipeProc(FakeProc):
    def __init__(self, r, w):
        super().__init__(lines=())
        self._r, self._w = r, w
        self.stdout = os.fdopen(r, "rb")
        self.stdin = os.fdopen(w, "wb", closefd=True)

    def poll(self):
        return None if not self._terminated else 0

    def wait(self, timeout=None):
        t0 = time.time()
        while not self._terminated and time.time() - t0 < (timeout or 30):
            time.sleep(0.02)
        return 0


eng2 = _make_engine(fake_popen_slow())
stop = threading.Event()


def run_slow():
    try:
        eng2._run(["+workshop_download_item", "4000", "333"],
                  on_line=lambda _l: None)
    except Exception as e:  # noqa: BLE001
        errors2.append(f"run: {type(e).__name__}: {e}")


def do_cancel():
    try:
        for _ in range(20):
            eng2.cancel()
            time.sleep(0.02)
    except Exception as e:  # noqa: BLE001
        cancel_errs.append(f"cancel: {type(e).__name__}: {e}")


tr = threading.Thread(target=run_slow, daemon=True)
tc = threading.Thread(target=do_cancel, daemon=True)
tr.start()
time.sleep(0.1)
tc.start()
tr.join(timeout=15)
tc.join(timeout=5)
check("_run 与 cancel 并发不崩溃", not errors2, str(errors2))
check("cancel() 并发调用不抛异常", not cancel_errs, str(cancel_errs))
subprocess.Popen = _REAL_POPEN

# ---- 3) DownloadManager 串行化 steamcmd：两任务不会同时进入引擎
from swdm.core.downloader import DownloadManager  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

engine_mock = MagicMock()
engine_mock.ensure_partial.return_value = 0
enter = threading.Lock()
concurrent = {"cur": 0, "max": 0}


def fake_download_item(**kw):
    with enter:
        concurrent["cur"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["cur"])
    time.sleep(0.15)   # 模拟下载耗时
    with enter:
        concurrent["cur"] -= 1
    return MagicMock(status="success", message="ok", bytes_done=1024,
                     path="/tmp/x")


engine_mock.download_item.side_effect = fake_download_item
# 强制走 steamcmd 通道（默认配置可能是 cdn，会绕过引擎）
import swdm.core.config as cfg_mod  # noqa: E402


class _FakeCfg:
    def get(self, *a, **k):
        if len(a) >= 2 and a[0] == "download" and a[1] == "channel":
            return "steamcmd"
        return ""


cfg_mod.get_config = lambda: _FakeCfg()

mgr = DownloadManager(engine=engine_mock, library=MagicMock())
mgr._throttle_wait = lambda _j: None   # 跳过节流等待
mgr.start()
mgr.enqueue(WorkshopItem(publishedfileid="a", title="A", appid="4000"), "4000")
mgr.enqueue(WorkshopItem(publishedfileid="b", title="B", appid="4000"), "4000")
time.sleep(1.5)
check("两任务经 steamcmd 通道串行执行（峰值并发=1）",
      concurrent["max"] == 1, f"peak={concurrent['max']}")
mgr.stop()
subprocess.Popen = _REAL_POPEN

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
