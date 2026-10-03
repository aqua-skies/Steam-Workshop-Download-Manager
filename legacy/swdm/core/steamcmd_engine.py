"""SteamCMD download engine (SteamCMD 下载引擎).

Features:
- Locate the steamcmd executable, or deploy the bundled copy
- Anonymous login (default, no account) / user login (interactive Steam Guard supported)
- ``workshop_download_item`` downloads with progress and success/failure parsing
- Threaded execution, reporting logs and state through callbacks (GUI-independent)

Wrapped as a provider since 1.4.0 by ``swdm.core.providers.steamcmd`` (terminal channel);
this module's own behavior is unchanged.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from .logger import get_logger
from .paths import (
    DEPLOYED_STEAMCMD_EXE,
    LIBRARY_DIR,
    STEAMCMD_DIR,
    ensure_dirs,
)
from .steamcmd_deploy import deploy as deploy_bundled, has_bundled_zip
from .throttle import classify_steamcmd_line

log = get_logger("swdm.steamcmd")

_STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/steamcmd_win32.zip"
# 常见安装位置（按优先级）
_SEARCH_PATHS = [
    r"C:\Program Files (x86)\steamcmd\steamcmd.exe",
    r"C:\Program Files\steamcmd\steamcmd.exe",
    r"C:\steamcmd\steamcmd.exe",
    os.path.expanduser(r"~\steamcmd\steamcmd.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "steamcmd", "steamcmd.exe"),
]

_DL_RE = re.compile(r"Downloading item (\d+)")
_SUCCESS_RE = re.compile(r"Success\. Downloaded item (\d+) to \"([^\"]+)\" \((\d+) bytes\)")
_FAIL_RE = re.compile(r"(ERROR! .*|Failed to download item \d+.*|Timeout .*|Not Logged On.*)", re.I)
_LOGIN_OK_RE = re.compile(r"(Logged-in OK|Waiting for user info.*OK|Connecting anonymously to Steam Public.*OK)")
_LOGIN_FAIL_RE = re.compile(r"(Login Failure|Invalid Password|Not Logged On|rate limit|RateLimit)", re.I)

# 实测（tests/fixtures/steamcmd_*.txt）：steamcmd 对 workshop_download_item
# 不输出逐字节/百分比进度，只有 "Downloading item X ..." -> "Success. ... (N bytes)"。
# 下面两个正则是防御性的，用于多块/应用更新类输出（部分游戏会逐块落盘并打印进度）：
#   [ 12%] xxx              —— steamcmd 通用百分比标记（自更新/部分内容下载）
#   Update state (0x61) downloading, progress: 45.6 (10.2 / 22.4 MBs)
_PERCENT_RE = re.compile(r"\[\s*(\d{1,3})\s*%\s*\]")
_UPDATE_STATE_RE = re.compile(
    r"Update state \(0x[0-9a-fA-F]+\)[^(]*progress:\s*([\d.]+)\s*\(\s*([\d.]+)\s*/\s*([\d.]+)\s*([KkMmGg]?[Bb])",
    re.IGNORECASE,
)
_UNIT_BYTES = {"b": 1, "kb": 1024, "mb": 1024 * 1024, "gb": 1024 * 1024 * 1024}


def _path_size(path: str) -> int:
    """递归求一个路径下全部文件总字节数（容错，忽略不可访问项）。"""
    if not path or not os.path.exists(path):
        return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


class DownloadStatus(Enum):
    """Outcome of a steamcmd run: queued → running → success/failed/cancelled."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadResult:
    """Result of one steamcmd ``workshop_download_item`` invocation."""

    item_id: str
    appid: str
    status: DownloadStatus
    path: str = ""
    bytes_done: int = 0
    message: str = ""
    elapsed: float = 0.0


@dataclass
class _Task:
    item_id: str
    appid: str
    result: DownloadResult
    done: threading.Event = field(default_factory=threading.Event)


class SteamCMDError(Exception):
    """Raised when steamcmd fails to start, or a non-download steamcmd error occurs."""


class SteamCMDEngine:
    """steamcmd 子进程托管 + 输出解析。"""

    def __init__(
        self,
        exe_path: str = "",
        install_dir: str = "",
        anonymous: bool = True,
        username: str = "",
        password: str = "",
        guard_code: str = "",
        validate: bool = False,
        stall_timeout: float = 60.0,
        min_bytes_per_sec: float = 200_000.0,
    ) -> None:
        self.exe_path = exe_path
        self.install_dir = install_dir or LIBRARY_DIR
        self.anonymous = anonymous
        self.username = username
        self.password = password
        self.guard_code = guard_code
        self.validate = validate
        # 停滞超时：steamcmd 输出静默超过该秒数（且无磁盘增长）则判定卡死，
        # 终止进程并按失败处理（需求 3：下载停滞检测）。
        self.stall_timeout = max(1.0, float(stall_timeout))
        # 原子落盘的物品（GMod .gma 等）在完成前无法观测到字节增长，
        # 此时按"最小期望速率"放宽超时上限，避免大文件被误杀。
        self.min_bytes_per_sec = max(1.0, float(min_bytes_per_sec))
        self._lock = threading.Lock()
        self._proc_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._current: _Task | None = None
        self._cancel_flag = threading.Event()
        # 节流信号出口：(kind, line) 订阅者列表 —— 由 DownloadManager
        # 桥接到退避/并发自适应。多订阅者 append 订阅，后赋值不覆盖前者。
        self.on_throttle_signal: list = []
        self._last_appid = ""
        # 进度回调串行化：输出线程与停滞看门狗都可能回调 on_progress
        self._prog_lock = threading.Lock()
        self._activity = 0.0
        self._stall_killed = False
        self._stall_reason = ""

    # ------------------------------------------------------------ 定位/部署
    def resolve_exe(self) -> str:
        """返回可执行的 steamcmd.exe 路径；找不到则自动部署内置版本。

        优先级：用户在设置里指定的路径 > 已部署的内置 steamcmd >
        系统已安装的 steamcmd > 解压随程序分发的内置 zip >
        在线下载（最后手段）。
        """
        # 1) 用户显式指定
        if self.exe_path and os.path.isfile(self.exe_path):
            return self.exe_path
        # 2) 已部署的内置 steamcmd
        if os.path.isfile(DEPLOYED_STEAMCMD_EXE):
            self.exe_path = DEPLOYED_STEAMCMD_EXE
            return DEPLOYED_STEAMCMD_EXE
        # 3) 系统已安装
        for p in _SEARCH_PATHS:
            if os.path.isfile(p):
                self.exe_path = p
                return p
        # 4) 解压随程序分发的内置 zip（安装时自动附带，免用户自装）
        if has_bundled_zip():
            exe = deploy_bundled()
            self.exe_path = exe
            return exe
        # 5) 最后手段：在线下载
        return self.deploy()

    def deploy(self) -> str:
        """在线下载并解压 steamcmd 到内置工作区（无内置 zip 时的回退）。"""
        import io
        import zipfile

        import requests

        ensure_dirs()
        os.makedirs(STEAMCMD_DIR, exist_ok=True)
        exe = os.path.join(STEAMCMD_DIR, "steamcmd.exe")
        log.info("开始在线部署 steamcmd 到 %s", STEAMCMD_DIR)
        try:
            r = requests.get(_STEAMCMD_URL, timeout=120, stream=True)
            r.raise_for_status()
            buf = io.BytesIO()
            for chunk in r.iter_content(1 << 16):
                buf.write(chunk)
            buf.seek(0)
            with zipfile.ZipFile(buf) as zf:
                zf.extractall(STEAMCMD_DIR)
        except Exception as e:  # noqa: BLE001
            raise SteamCMDError(f"steamcmd 部署失败: {e}") from e
        if not os.path.isfile(exe):
            raise SteamCMDError("steamcmd 解压后未找到 steamcmd.exe")
        self.exe_path = exe
        log.info("steamcmd 部署完成: %s", exe)
        return exe

    # ------------------------------------------------------------------ 登录
    def _login_args(self) -> list[str]:
        if self.anonymous or not self.username:
            return ["+login", "anonymous"]
        args = ["+login", self.username]
        if self.password:
            args.append(self.password)
        if self.guard_code:
            args.append(self.guard_code)
        return args

    # ------------------------------------------------------------- 核心运行
    def _redact_secrets(self, line: str) -> str:
        """账号敏感信息过滤（C3 风控①）。

        steamcmd 输出行可能回显用户名（"Connecting to Steam as <name>" 等）；
        密码/验证码理论上不会回显，但一并过滤。匿名模式无密钥，原样返回。
        必须在 log.debug / on_line 之前调用——下游解析用的正则只匹配
        "Logged-in OK" / "Login Failure" / "Invalid Password" 等固定串，
        不依赖账号名，替换不影响解析。
        """
        for secret in (self.username, self.password, self.guard_code):
            if secret:
                line = line.replace(secret, "***")
        return line

    def _run(self, commands: list[str], on_line=None, feed_stdin: str = "",
             install_dir: str = "") -> int:
        """运行 steamcmd 并逐行回调输出。返回退出码。

        install_dir 可覆盖本次运行的 force_install_dir（按游戏指定目录）。
        """
        exe = self.resolve_exe()
        target_dir = install_dir or self.install_dir
        os.makedirs(target_dir, exist_ok=True)
        args = [exe, "+force_install_dir", target_dir] + commands + ["+quit"]
        log.debug("运行: %s", " ".join(args[:2]) + " ...")
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            shell=False,
            startupinfo=startupinfo,
        )
        # 实例字段仅用于 cancel() 查询；并发任务会互相覆盖，_run 内部
        # 一律使用局部变量 proc，避免 'NoneType' object has no attribute
        # 'poll'（bug7：多任务共享 engine 时 _proc 被置 None）
        with self._proc_lock:
            self._proc = proc
        self._cancel_flag.clear()
        code = -1
        assert proc.stdout is not None and proc.stdin is not None
        if feed_stdin:
            try:
                proc.stdin.write(feed_stdin.encode("utf-8", "replace"))
                proc.stdin.flush()
            except Exception:  # noqa: BLE001
                pass
        try:
            for raw in proc.stdout:
                if self._cancel_flag.is_set():
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line.strip():
                    continue
                # C3 风控①：账号名/密码/验证码不得落日志，也不得进 on_line 回调
                line = self._redact_secrets(line)
                log.debug("[steamcmd] %s", line)
                if on_line:
                    on_line(line)
        finally:
            # 全部使用局部快照，不依赖 self._proc（可能已被另一任务覆盖）
            if proc.poll() is None:
                try:
                    proc.stdin.write(b"quit\n")
                    proc.stdin.flush()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
            code = proc.wait(timeout=30) if proc.poll() is None else proc.returncode
            with self._proc_lock:
                if self._proc is proc:
                    self._proc = None
        return code

    # --------------------------------------------------------------- 下载
    def download_item(
        self,
        appid: str,
        item_id: str,
        on_progress=None,
        on_log=None,
        total_hint: int = 0,
        install_dir: str = "",
    ) -> DownloadResult:
        """下载单个工坊物品（阻塞）。

        on_progress(percent, bytes_done, msg)：percent < 0 表示不确定进度。
        total_hint：物品预期总字节数（来自工坊元数据），用于把百分比行换算成
          字节数，并按"最小期望速率"放宽停滞超时（大文件不被误杀）。
        install_dir：指定本次下载的 force_install_dir（按游戏指定目录）；
          留空使用引擎默认目录。

        实测 steamcmd 对 workshop_download_item 不输出逐字节进度（见
        tests/fixtures/steamcmd_success.txt），只有 "Downloading item X ..."
        与最终的 "Success. ... (N bytes)"。实时进度来自：
          - 百分比行 / Update state 行（部分游戏会有）
          - 内容目录的磁盘增长（多文件游戏会逐文件落盘）
        二者都缺失时，UI 显示不确定进度直到完成。
        """
        result = DownloadResult(item_id=str(item_id), appid=str(appid), status=DownloadStatus.RUNNING)
        self._last_appid = str(appid)
        t0 = time.time()
        cmds = self._login_args() + ["+workshop_download_item", str(appid), str(item_id)]
        if self.validate:
            cmds.append("+validate")

        state = {"dl_seen": False, "login_ok": False, "err": ""}
        self._activity = time.time()
        self._stall_killed = False
        self._stall_reason = ""
        content_dir = self.content_path(str(appid), str(item_id))

        def emit(pct: int, done: int, msg: str) -> None:
            """串行化地回调 on_progress（输出线程与看门狗共用）。"""
            with self._prog_lock:
                if on_progress:
                    try:
                        on_progress(pct, done, msg)
                    except Exception:  # noqa: BLE001
                        log.exception("on_progress 回调异常")

        def touch() -> None:
            """刷新"最后活跃时间"（任何 steamcmd 输出都算活跃）。"""
            self._activity = time.time()

        def on_line(line: str) -> None:
            if on_log:
                on_log(line)
            touch()
            # 限流/超时/重试特征识别（需求 1：触发退避）
            kind = classify_steamcmd_line(line)
            if kind:
                log.warning("steamcmd 特征 [%s]: %s", kind, line.strip())
                for cb in list(self.on_throttle_signal):
                    try:
                        cb(kind, line)
                    except Exception:  # noqa: BLE001
                        log.exception("on_throttle_signal 回调异常")
            m = _LOGIN_OK_RE.search(line)
            if m:
                state["login_ok"] = True
            m = _DL_RE.search(line)
            if m:
                state["dl_seen"] = True
                touch()
                # bug1/5：立即给一次"开始下载"信号，UI 马上有反馈
                emit(1, 0, f"正在下载物品 {m.group(1)}…")
            # 实时进度解析（仅在下载阶段、未完成前）
            if state["dl_seen"] and result.status != DownloadStatus.SUCCESS:
                mp = _PERCENT_RE.search(line)
                if mp:
                    pct = max(0, min(99, int(mp.group(1))))
                    done = int(pct / 100 * total_hint) if total_hint > 0 else 0
                    emit(pct, done, f"下载中 {pct}%")
                else:
                    mu = _UPDATE_STATE_RE.search(line)
                    if mu:
                        pct = max(0, min(99, int(float(mu.group(1)))))
                        unit = mu.group(4).strip().lower()
                        mult = _UNIT_BYTES.get(unit, 1)
                        emit(pct, int(float(mu.group(2)) * mult), f"下载中 {pct}%")
            m = _SUCCESS_RE.search(line)
            if m:
                result.path = m.group(2)
                result.bytes_done = int(m.group(3))
                result.status = DownloadStatus.SUCCESS
                result.message = "下载成功"
            m = _FAIL_RE.search(line)
            if m:
                if not state["err"]:
                    state["err"] = m.group(1).strip()

        # 停滞看门狗：磁盘增长或任何输出都会重置计时器；静默超时则终止进程
        wd_stop = threading.Event()
        # steamcmd 下载中的内容先落在 downloads 临时目录，完成后才移入 content；
        # 只扫 content 会看到"进度恒 0% 直到完成跳 100%"（bug5）。
        # content_dir = <root>/steamapps/workshop/content/<appid>/<item>，
        # downloads  = <root>/steamapps/workshop/downloads/<appid>/<item>，
        # 需从 content_dir 向上剥 3 层（item→appid→content）到 workshop
        dl_tmp_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(content_dir))),
            "downloads", str(appid), str(item_id),
        )

        def _watched_dirs() -> list:
            return [content_dir, dl_tmp_dir]

        def watchdog() -> None:
            max_silence = self.stall_timeout
            if total_hint > 0:
                # 原子落盘物品在完成前看不到字节增长：按最小速率放宽上限
                max_silence = max(max_silence, total_hint / self.min_bytes_per_sec)
            last_size = sum(_path_size(d) for d in _watched_dirs())
            while not wd_stop.wait(0.3):
                size = sum(_path_size(d) for d in _watched_dirs())
                if size > last_size:
                    last_size = size
                    touch()  # 有新字节落盘：重置停滞计时器
                    # bug5：无论是否已看到 "Downloading item" 行，只要有
                    # 字节落盘就上报，UI 显示"已下载 X MB"而非恒 0%
                    if result.status != DownloadStatus.SUCCESS:
                        if total_hint > 0:
                            pct = int(size / total_hint * 100)
                            pct = max(0, min(99, pct))
                            emit(pct, size, f"下载中 {pct}%（已落盘）")
                        else:
                            mb = size / 1048576
                            emit(-1, size, f"已下载 {mb:.1f} MB")
                idle = time.time() - self._activity
                if idle > max_silence:
                    self._stall_killed = True
                    self._stall_reason = f"下载停滞超时（{idle:.0f}s 无进展）"
                    log.warning("下载 %s 触发停滞看门狗，终止 steamcmd", item_id)
                    self.cancel()
                    return

        wd = threading.Thread(target=watchdog, name=f"steamcmd-wd-{item_id}", daemon=True)
        wd.start()
        try:
            # 仅在指定了游戏专属目录时才传 install_dir，保持与重写 _run 的
            # mock 引擎向后兼容
            if install_dir:
                self._run(cmds, on_line=on_line, install_dir=install_dir)
            else:
                self._run(cmds, on_line=on_line)
        except Exception as e:  # noqa: BLE001
            result.status = DownloadStatus.FAILED
            result.message = f"引擎异常: {e}"
            log.exception("下载 %s 时引擎异常", item_id)
            return result
        finally:
            wd_stop.set()
            wd.join(timeout=3)

        result.elapsed = time.time() - t0
        if self._stall_killed and result.status != DownloadStatus.SUCCESS:
            result.status = DownloadStatus.FAILED
            result.message = self._stall_reason or "下载停滞超时"
        elif self._cancel_flag.is_set() and result.status != DownloadStatus.SUCCESS:
            result.status = DownloadStatus.CANCELLED
            result.message = "已取消"
        elif result.status != DownloadStatus.SUCCESS:
            result.status = DownloadStatus.FAILED
            if state["err"]:
                result.message = state["err"]
            elif not state["login_ok"]:
                result.message = "登录失败（可能是账号/密码错误，或触发 Steam Guard）"
            elif not state["dl_seen"]:
                result.message = "未开始下载（物品可能不存在或该游戏不支持匿名下载）"
            else:
                result.message = "下载未完成（可能超时）"
        if result.status == DownloadStatus.SUCCESS:
            emit(100, result.bytes_done, "完成")
        log.info(
            "下载结果 %s: status=%s bytes=%s msg=%s",
            item_id, result.status.value, result.bytes_done, result.message,
        )
        return result

    # --------------------------------------------------------------- 续传
    def ensure_partial(self, item_id: str, appid: str = "",
                       install_dir: str = "") -> int:
        """重试前检查已落盘的部分内容字节数（需求 2：多点续传钩子）。

        返回 content/<appid>/<itemid> 目录下已有文件总字节数；0 表示无内容。
        steamcmd 重复下载同一物品会校验已有内容、只补差异，因此重试时保留
        该目录即可实现"效果上的续传"；本方法把"已有多少"告诉调用方，
        由 DownloadManager 写入 job.message（"续传中（已有 N MB）"）。

        install_dir 可指定该游戏专属的下载根目录。
        """
        base_dir = install_dir or self.install_dir
        appid = str(appid or self._last_appid or "").strip()
        if appid:
            return _path_size(self.content_path(appid, item_id, base_dir))
        # appid 未知时在 content/*/itemid 下扫描
        base = os.path.join(base_dir, "steamapps", "workshop", "content")
        if not os.path.isdir(base):
            return 0
        for a in os.listdir(base):
            p = os.path.join(base, a, str(item_id))
            if os.path.exists(p):
                return _path_size(p)
        return 0

    def cancel(self) -> None:
        """请求取消当前正在运行的 steamcmd 进程。

        线程安全：用锁快照进程引用。多个下载任务共享同一 engine 实例时，
        _run 的 finally 可能把 self._proc 置 None，此处必须容忍。
        """
        self._cancel_flag.set()
        with self._proc_lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"quit\n")
                    proc.stdin.flush()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        log.info("已请求取消 steamcmd")

    # ------------------------------------------------------------- 工具方法
    def test_login(self) -> tuple[bool, str]:
        """测试登录连通性（不下载任何内容）。返回 (ok, message)。"""
        state = {"ok": False, "err": ""}
        cmds = self._login_args()

        def on_line(line: str) -> None:
            if _LOGIN_OK_RE.search(line):
                state["ok"] = True
            m = _LOGIN_FAIL_RE.search(line)
            if m and not state["err"]:
                state["err"] = m.group(1).strip()

        try:
            self._run(cmds, on_line=on_line)
        except Exception as e:  # noqa: BLE001
            return False, f"引擎异常: {e}"
        if state["ok"]:
            # C3 风控①：返回串不含用户名（该串会进诊断日志/UI）；
            # 账号名由调用方（设置页）从 auth 自行展示
            mode = "账号" if not (self.anonymous or not self.username) else "匿名"
            return True, f"{mode}登录成功"
        if state["err"]:
            return False, f"登录失败：{state['err']}"
        return False, "登录失败：未收到成功标志（可能需要 Steam Guard 或触发速率限制）"

    def content_path(self, appid: str, item_id: str, install_dir: str = "") -> str:
        """steamcmd 下载内容的落盘路径。"""
        return os.path.join(
            install_dir or self.install_dir, "steamapps", "workshop",
            "content", str(appid), str(item_id),
        )
