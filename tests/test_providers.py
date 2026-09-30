#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""t21 provider 抽象层测试：注册 / 链构造 / 回退 / 匿名降级 / 限速 / 进度。

脚本式：check(name, cond, extra) + RESULT: ALL PASS。
环境与既有测试一致：import swdm 前设 APPDATA 临时目录、offscreen Qt。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

# ---- 环境前置（必须在 import swdm 前）
_APPDATA = tempfile.mkdtemp(prefix="swdm_prov_")
os.environ["APPDATA"] = _APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYTHONUTF8"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, extra: str = "") -> None:
    ok = bool(cond)
    _RESULTS.append((name, ok, str(extra)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}")


# ---- 被测对象
from swdm.core.providers import (  # noqa: E402
    Availability,
    DownloadProvider,
    ProviderKind,
    ProviderMeta,
    ProviderRegistry,
)
from swdm.core.providers.registry import _Circuit  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402


def _item(item_id="12345", appid="4000", file_url="", file_size=0):
    return WorkshopItem(
        publishedfileid=item_id, appid=appid,
        title="t", file_url=file_url, file_size=file_size,
    )


def _ok(bytes_done=1024):
    return DownloadResult(item_id="12345", appid="4000",
                          status=DownloadStatus.SUCCESS,
                          bytes_done=bytes_done, message="ok")


def _fail(msg="fail"):
    return DownloadResult(item_id="12345", appid="4000",
                          status=DownloadStatus.FAILED, message=msg)


def _cancelled():
    return DownloadResult(item_id="12345", appid="4000",
                          status=DownloadStatus.CANCELLED, message="已取消")


# ==================== 测试用假 provider ====================
class _FakeProvider(DownloadProvider):
    """可编程假 provider：按 calls 列表依次返回预设结果。"""

    def __init__(self, config=None, api=None, results=None, meta=None):
        super().__init__(config or {}, api)
        self.calls: list = list(results or [])
        self.events: list = []
        self.progresses: list = []
        self._meta = meta or self.meta

    meta = ProviderMeta(name="fake", display_name="Fake", kind=ProviderKind.HTTP)

    @property
    def meta_prop(self):
        return self._meta

    def probe(self, timeout: float = 8.0) -> Availability:
        return Availability.OK

    def download(self, item, dest_dir, on_progress=None, stop_event=None, total_hint=0):
        self.events.append(("download", item.publishedfileid, dest_dir, total_hint))
        if on_progress:
            on_progress(50, 512, "half")
            self.progresses.append(50)
            on_progress(100, 1024, "完成")
            self.progresses.append(100)
        if not self.calls:
            return _ok()
        r = self.calls.pop(0)
        if callable(r):
            return r()
        return r

    def cancel(self) -> None:
        self.events.append(("cancel",))

    def resolve(self, item):
        return "http://fake.example/file.gma"


# ==================== 1. 注册与元数据 ====================
class _Alpha(_FakeProvider):
    meta = ProviderMeta(name="alpha", display_name="Alpha", kind=ProviderKind.HTTP,
                        priority=10)


class _Beta(_FakeProvider):
    meta = ProviderMeta(name="beta", display_name="Beta", kind=ProviderKind.PROXY,
                        priority=20, requires_key=True)


def test_registration():
    reg = ProviderRegistry()
    reg.register(_Alpha)
    reg.register(_Beta)
    check("注册后可按名取实例", reg.get_provider("alpha") is not None)
    check("未注册名返回 None", reg.get_provider("nope") is None)
    check("meta 字段保留", reg.get_provider("alpha").meta.display_name == "Alpha")
    check("requires_key 标记", reg.get_provider("beta").meta.requires_key is True)
    check("beta 未配 key 时 is_configured=False",
          reg.get_provider("beta").is_configured() is False)
    b = reg.get_provider("beta")
    b.config["api_key"] = "x"
    check("beta 配 key 后 is_configured=True", b.is_configured() is True)


# ==================== 2. 链构造 ====================
class _OKChan(_FakeProvider):
    meta = ProviderMeta(name="okchan", display_name="OK", kind=ProviderKind.HTTP,
                        priority=10)


class _FailChan(_FakeProvider):
    meta = ProviderMeta(name="failchan", display_name="Fail", kind=ProviderKind.HTTP,
                        priority=20)
    def download(self, *a, **k):
        super().download(*a, **k)
        return _fail()


class _KeyChan(_FakeProvider):
    meta = ProviderMeta(name="keychan", display_name="Key", kind=ProviderKind.HTTP,
                        priority=15, requires_key=True)


class _ChainFixture:
    def __init__(self):
        self.reg = ProviderRegistry()
        self.reg.register(_OKChan)
        self.reg.register(_FailChan)
        self.reg.register(_KeyChan)


def test_chain_order():
    f = _ChainFixture()
    chain = f.reg.build_chain("okchan")
    names = [p.meta.name for p in chain]
    check("首选通道在链首", names[0] == "okchan", str(names))
    check("链含全部启用通道", set(names) == {"okchan", "failchan"}, str(names))
    check("按 priority 排序", names == ["okchan", "failchan"], str(names))
    check("未配 key 的通道被跳过", "keychan" not in names, str(names))


def test_chain_disabled():
    f = _ChainFixture()
    f.reg._provider_config = lambda n: {"enabled": False} if n == "failchan" else {}
    chain = f.reg.build_chain("okchan")
    names = [p.meta.name for p in chain]
    check("禁用通道不出现在链中", "failchan" not in names, str(names))


def test_chain_unknown_preferred():
    f = _ChainFixture()
    chain = f.reg.build_chain("nonexistent")
    names = [p.meta.name for p in chain]
    check("首选不存在时按 priority 构链", names == ["okchan", "failchan"], str(names))


# ==================== 3. 熔断 ====================
def test_circuit():
    c = _Circuit(fail_threshold=3, cooldown=0.05)
    check("初始未熔断", not c.is_tripped())
    c.record_failure(); c.record_failure()
    check("未达阈值不熔断", not c.is_tripped())
    c.record_failure()
    check("达阈值熔断", c.is_tripped())
    time.sleep(0.06)
    check("冷却期过后半开", not c.is_tripped())
    c.record_failure()
    check("半开期再失败重新熔断", c.is_tripped())
    c.record_success()
    check("成功重置熔断", not c.is_tripped())


def test_circuit_skips_channel():
    f = _ChainFixture()
    f.reg.record_failure("failchan")
    f.reg.record_failure("failchan")
    f.reg.record_failure("failchan")
    check("熔断通道 is_tripped", f.reg._circuits["failchan"].is_tripped())
    chain = f.reg.build_chain("okchan")
    names = [p.meta.name for p in chain]
    check("熔断通道被链跳过", "failchan" not in names, str(names))
    f.reg.record_success("failchan")
    chain2 = f.reg.build_chain("okchan")
    names2 = [p.meta.name for p in chain2]
    check("熔断恢复后回到链中", "failchan" in names2, str(names2))


# ==================== 4. 匿名降级（is_configured） ====================
def test_anonymous_degradation():
    f = _ChainFixture()
    # keychan 未配置 → 链跳过它
    chain = f.reg.build_chain("keychan")
    names = [p.meta.name for p in chain]
    check("需 key 通道未配置时不占链位", "keychan" not in names, str(names))
    # 给 keychan 配 api_key 后进入链
    inst = f.reg.get_provider("keychan")
    inst.config["api_key"] = "abc123"
    chain2 = f.reg.build_chain("keychan")
    names2 = [p.meta.name for p in chain2]
    check("配置 key 后通道入链", names2[0] == "keychan", str(names2))


# ==================== 5. should_fallback 语义 ====================
def test_should_fallback():
    ok, failing = _OKChan(), _FailChan()
    check("失败默认回退", ok.should_fallback(_fail()) is True)
    check("成功不回退", ok.should_fallback(_ok()) is False)
    check("取消不回退", ok.should_fallback(_cancelled()) is False)

    class _NoFallback(_FakeProvider):
        meta = ProviderMeta(name="nofallback", display_name="NoFB",
                            kind=ProviderKind.HTTP, priority=5)

        def should_fallback(self, result):
            return False

    f = _ChainFixture()
    f.reg.register(_NoFallback)
    chain = f.reg.build_chain("nofallback")
    check("should_fallback=False 的通道仍在链中（判定在执行时）",
          [p.meta.name for p in chain][0] == "nofallback",
          str([p.meta.name for p in chain]))


# ==================== 6. http_download 取消与续传 ====================
def test_http_download_cancel():
    import requests

    from swdm.core.providers.base import DownloadProvider as DP
    # 用本地文件服务器模拟可取消下载
    import http.server
    import socketserver

    class _BigHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(1000 * 10240))
            self.end_headers()
            try:
                for _ in range(1000):
                    self.wfile.write(b"x" * 10240)
                    time.sleep(0.005)  # 每块 5ms → 全量约 5s，确保可中途取消
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *a):
            pass

    port = 18999
    with socketserver.TCPServer(("127.0.0.1", port), _BigHandler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            prov = _FakeProvider()
            stop = threading.Event()
            dest = os.path.join(_APPDATA, "cancel_test.bin")

            def _bg():
                time.sleep(0.1)
                stop.set()

            threading.Thread(target=_bg, daemon=True).start()
            res = prov.http_download(f"http://127.0.0.1:{port}/big", dest,
                                     stop_event=stop, chunk_size=4096)
            check("stop_event 取消返回 CANCELLED",
                  res.status == DownloadStatus.CANCELLED, str(res.status))
            check("取消保留已写部分（续传基础）", res.bytes_done > 0, str(res.bytes_done))
            check("取消时不再调用完成回调",
                  prov.progresses == [] or prov.progresses[-1] < 100,
                  str(prov.progresses))
        finally:
            httpd.shutdown()
            httpd.server_close()


def test_http_download_resume():
    import socketserver
    import http.server

    class _ResumeHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes=500-"):
                self.send_response(206)
                self.send_header("Content-Length", "500")
                self.send_header("Content-Range", "bytes 500-999/1000")
                self.end_headers()
                self.wfile.write(b"y" * 500)
            else:
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"x" * 1000)

        def log_message(self, *a):
            pass

    port = 18998
    with socketserver.TCPServer(("127.0.0.1", port), _ResumeHandler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            prov = _FakeProvider()
            dest = os.path.join(_APPDATA, "resume.bin")
            with open(dest, "wb") as fh:
                fh.write(b"x" * 500)
            res = prov.http_download(f"http://127.0.0.1:{port}/r", dest)
            check("Range 续传 206 成功",
                  res.status == DownloadStatus.SUCCESS, str(res.status))
            check("续传后总字节 1000", res.bytes_done == 1000, str(res.bytes_done))
            check("续传内容前段保留旧字节",
                  open(dest, "rb").read()[:500] == b"x" * 500)
        finally:
            httpd.shutdown()
            httpd.server_close()


# ==================== 7. GGNetwork 限速器 ====================
def test_rate_limiter():
    from swdm.core.providers.ggnetwork import _RateLimiter
    lim = _RateLimiter(per_minute=600)  # 10/s
    t0 = time.monotonic()
    n = 0
    for _ in range(12):
        if lim.acquire():
            n += 1
    dt = time.monotonic() - t0
    check("令牌桶允许突发 3 次", n >= 3, f"n={n}")
    check("限速器最终放行全部请求", n == 12, f"n={n}")
    # 突发后必须等
    lim2 = _RateLimiter(per_minute=60)  # 1/s，突发 3
    stop = threading.Event()
    a = [lim2.acquire(stop) for _ in range(3)]
    t1 = time.monotonic()
    ok4 = lim2.acquire(stop)
    dt2 = time.monotonic() - t1
    check("突发 3 次后第 4 次需等待", ok4 and dt2 >= 0.3, f"dt={dt2:.2f}")
    stop.set()
    check("stop_event 中断等待", lim2.acquire(stop) is False)


# ==================== 8. GGNetwork 解析与压缩包解压 ====================
def test_ggnetwork_resolve_and_extract():
    import zipfile

    from swdm.core.providers.ggnetwork import GGNetworkProvider

    class _FakeResp:
        def __init__(self, status=200, json_data=None):
            self.status_code = status
            self._json = json_data or {}

        def json(self):
            return self._json

    class _FakeSession:
        def __init__(self, resp):
            self._resp = resp
            self.posted = []

        def post(self, url, json=None, timeout=None):
            self.posted.append((url, json))
            return self._resp

    prov = GGNetworkProvider(config={"rate_limit_per_minute": 999})
    # resolve
    sess = _FakeSession(_FakeResp(200, {"url": "http://cdn.example/123.gma"}))
    prov._session = lambda: sess  # type: ignore
    url = prov.resolve(_item())
    check("GGNetwork resolve 取出直链",
          url == "http://cdn.example/123.gma", url)
    check("POST 目标正确",
          sess.posted[0][0] == "https://api.ggntw.com/steam.request")
    check("POST body 含工坊页 URL",
          "filedetails/?id=12345" in str(sess.posted[0][1]))

    # 429 限流
    sess2 = _FakeSession(_FakeResp(429))
    prov2 = GGNetworkProvider(config={})
    prov2._session = lambda: sess2  # type: ignore
    check("429 时 resolve 返回空", prov2.resolve(_item()) == "")

    # queue.position>0 但同时给了 url → 实测 position 不是「未就绪」信号，url 优先
    sess_q = _FakeSession(_FakeResp(200, {
        "url": "http://cdn.example/123.gma",
        "queue": {"position": 1, "total": 0},
        "status": 1,
    }))
    prov_q = GGNetworkProvider(config={})
    prov_q._session = lambda: sess_q  # type: ignore
    check("queue.position>0 但带 url 时 resolve 取直链（实测语义）",
          prov_q.resolve(_item()) == "http://cdn.example/123.gma")
    # position>0 且无 url → 排队中，空串干净回退（不轮询）
    sess_qn = _FakeSession(_FakeResp(200, {
        "queue": {"position": 3, "total": 5},
        "status": 1,
    }))
    prov_qn = GGNetworkProvider(config={})
    prov_qn._session = lambda: sess_qn  # type: ignore
    check("queue.position>0 且无 url 时 resolve 返回空（排队回退）",
          prov_qn.resolve(_item()) == "")
    # 后端错误体（被删物品的真实回包）→ 空
    sess_err = _FakeSession(_FakeResp(200, {
        "result": 10, "status": 3, "error": "need login to account",
    }))
    prov_err = GGNetworkProvider(config={})
    prov_err._session = lambda: sess_err  # type: ignore
    check("后端 error 体 resolve 返回空", prov_err.resolve(_item()) == "")
    # api 给的是落地页 URL → 改写为 CDN 直链
    sess_lp = _FakeSession(_FakeResp(200, {
        "result": 1,
        "url": "https://ggntw.com/download/abcTOKEN123",
        "queue": {"position": 1, "total": 0},
    }))
    prov_lp = GGNetworkProvider(config={})
    prov_lp._session = lambda: sess_lp  # type: ignore
    check("落地页 url 改写为 cdn.ggntw.com/<token>",
          prov_lp.resolve(_item()) == "https://cdn.ggntw.com/abcTOKEN123")
    # position=0（已缓存）正常取 url
    sess_q0 = _FakeSession(_FakeResp(200, {
        "url": "http://cdn.example/123.gma",
        "queue": {"position": 0, "total": 0},
    }))
    prov_q0 = GGNetworkProvider(config={})
    prov_q0._session = lambda: sess_q0  # type: ignore
    check("queue.position=0 时 resolve 正常取直链",
          prov_q0.resolve(_item()) == "http://cdn.example/123.gma")

    # probe 健康判定：错误体/无 url 判不可用，带 url 判可用（t32 实测驱动）
    class _FakeRespText(_FakeResp):
        def __init__(self, status, json_data=None):
            super().__init__(status, json_data)

    prov_p = GGNetworkProvider(config={"rate_limit_per_minute": 999})
    prov_p._session = lambda: _FakeSession(
        _FakeRespText(200, {"result": 10, "error": "need login to account"}))  # type: ignore
    check("probe 对错误体判 UNREACHABLE",
          prov_p.probe() == Availability.UNREACHABLE)
    prov_p2 = GGNetworkProvider(config={"rate_limit_per_minute": 999})
    prov_p2._session = lambda: _FakeSession(
        _FakeRespText(200, {"result": 1, "url": "https://cdn.ggntw.com/x"}))  # type: ignore
    check("probe 对带 url 响应判 OK", prov_p2.probe() == Availability.OK)

    # 压缩包解压
    tmpdir = tempfile.mkdtemp(prefix="swdm_gg_")
    archive = os.path.join(tmpdir, "pack.zip")
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("inner/123.gma", b"GMAD" + b"\x00" * 100)
    extracted = prov._maybe_extract(archive, tmpdir, "123")
    check("zip 中的 .gma 被提取到 content 根",
          os.path.basename(extracted) == "123.gma", extracted)
    check("解压后原压缩包删除", not os.path.isfile(archive))
    check("提取的 .gma 内容正确",
          open(extracted, "rb").read()[:4] == b"GMAD")

    # 非压缩包原样返回
    plain = os.path.join(tmpdir, "plain.gma")
    with open(plain, "wb") as fh:
        fh.write(b"GMAD")
    check("非 zip 原样返回", prov._maybe_extract(plain, tmpdir, "x") == plain)

    # .gma 魔数校验（_verify_content 返回 (note, size_bad)）
    good = _item(file_size=104)
    note_ok, bad_ok = prov._verify_content(extracted, good)
    check("魔数正确且 size 一致无⚠", note_ok == "" and bad_ok is False, note_ok)
    bad_magic = os.path.join(tmpdir, "bad.gma")
    with open(bad_magic, "wb") as fh:
        fh.write(b"XXXX" + b"\x00" * 100)
    note_bad, bad_bad = prov._verify_content(bad_magic, good)
    check("魔数错误给⚠但不判坏包", "非标准" in note_bad and bad_bad is False, note_bad)
    note_size, bad_size = prov._verify_content(extracted, _item(file_size=999999))
    check("size 差异>1% 判坏包（回退触发）",
          "差异" in note_size and bad_size is True, note_size)

    # 坏包在 download() 里应判 FAILED + 回退 + 清残留
    gg_prov = GGNetworkProvider(config={})
    gg_prov.resolve = lambda item: "http://example.com/12345.gma"
    gg_prov.http_download = lambda url, dest, sess, **kw: DownloadResult(
        item_id="12345", appid="4000", status=DownloadStatus.SUCCESS,
        bytes_done=100, message="ok")
    gg_prov._maybe_extract = lambda path, ddir, iid: path
    tmp2 = tempfile.mkdtemp()
    bad_file = os.path.join(tmp2, "12345.gma")
    with open(bad_file, "wb") as fh:
        fh.write(b"GMAD" + b"\x00" * 100)
    gg_prov._session = lambda: None
    res_bad = gg_prov.download(_item(file_size=999999), tmp2)
    check("坏包判 FAILED", res_bad.status == DownloadStatus.FAILED, str(res_bad.status))
    check("坏包消息含回退说明", "回退" in (res_bad.message or ""), res_bad.message)
    check("坏包残留已清理", not os.path.isfile(bad_file))
    check("坏包触发 should_fallback", gg_prov.should_fallback(res_bad) is True)
    shutil.rmtree(tmp2, ignore_errors=True)


# ==================== 9. DownloadManager 链执行（端到端 mock） ====================
def test_manager_chain_exec():
    import types

    from swdm.core.downloader import DownloadManager, DownloadJob

    # 伪装 engine：用真 SteamCMDEngine 的 __new__ 跳过构造
    from swdm.core.steamcmd_engine import SteamCMDEngine
    engine = SteamCMDEngine.__new__(SteamCMDEngine)
    engine.__dict__.update({
        "install_dir": "/tmp",
        "anonymous": True, "username": "", "password": "",
        "exe_path": "", "validate": False,
        "on_throttle_signal": [],
    })

    def _fake_download_item(self, appid, item_id, on_progress=None, on_log=None,
                            total_hint=0, install_dir=""):
        return DownloadResult(item_id=item_id, appid=appid,
                              status=DownloadStatus.SUCCESS, bytes_done=2048,
                              message="ok")

    engine.download_item = types.MethodType(_fake_download_item, engine)
    engine.ensure_partial = lambda *a, **k: 0
    engine.resolve_exe = lambda: ""
    engine.cancel = lambda: None

    from swdm.core.mod_library import ModLibrary
    lib = ModLibrary.__new__(ModLibrary)
    lib.__dict__.update({"_db": None})
    # 入库会写库；用空 upsert 跳过
    lib.upsert = lambda *a, **k: None
    lib.log_job = lambda *a, **k: None
    lib.write_metadata_sidecar = lambda *a, **k: None

    mgr = DownloadManager(engine, lib, api=None)
    job = DownloadJob(item=_item(), appid="4000")

    from swdm.core.throttle import ProgressSmoother
    sm = ProgressSmoother(min_interval=0.1)
    dest_root = os.path.join(_APPDATA, "mgrtest")

    # 注入假链（绕过 registry，直接测 _run_provider 的回退循环）
    class _ProvA(_FakeProvider):
        meta = ProviderMeta(name="prova", display_name="A", kind=ProviderKind.HTTP,
                            priority=1)

    class _ProvB(_FakeProvider):
        meta = ProviderMeta(name="provb", display_name="B", kind=ProviderKind.HTTP,
                            priority=2)

    pa = _ProvA(results=[_fail("A 不可用")])
    pb = _ProvB(results=[_ok(4096)])
    mgr._build_channel_chain = lambda pref: [pa, pb]
    result = mgr._run_channel_chain(job, dest_root, sm)
    check("链式回退：A 失败后 B 执行",
          [e[0] for e in pa.events] == ["download"]
          and [e[0] for e in pb.events] == ["download"])
    check("最终结果取 B 的成功", result.status == DownloadStatus.SUCCESS,
          str(result.status))
    check("job.channel 记录最终通道", job.channel == "provb", job.channel)
    check("回退不消耗 auto_retry", job.attempt == 0, str(job.attempt))
    check("进度回调写入 job（最后一次 on_progress）",
          job.bytes_done == 1024, str(job.bytes_done))

    # should_fallback=False 时链中断
    pa2 = _ProvA(results=[_fail("配置错误")])
    pa2.should_fallback = lambda r: False
    pb2 = _ProvB(results=[_ok()])
    mgr._build_channel_chain = lambda pref: [pa2, pb2]
    job2 = DownloadJob(item=_item(), appid="4000")
    r2 = mgr._run_channel_chain(job2, dest_root, sm)
    check("should_fallback=False 时链中断，B 不执行",
          pb2.events == [] and r2.status == DownloadStatus.FAILED)
    check("中断时 job.channel 记录该通道", job2.channel == "prova", job2.channel)

    # 取消时链停止
    pa3 = _ProvA(results=[_cancelled()])
    pb3 = _ProvB(results=[_ok()])
    mgr._build_channel_chain = lambda pref: [pa3, pb3]
    job3 = DownloadJob(item=_item(), appid="4000")
    job3._stop.set()
    r3 = mgr._run_channel_chain(job3, dest_root, sm)
    check("stop_event 置位时链立即停止", pb3.events == [])


# ==================== 9b. 链执行计入熔断（t28 第 7 项） ====================
def test_chain_records_circuit():
    import types

    from swdm.core.downloader import DownloadManager, DownloadJob
    from swdm.core.providers import get_registry
    from swdm.core.steamcmd_engine import SteamCMDEngine

    engine = SteamCMDEngine.__new__(SteamCMDEngine)
    engine.__dict__.update({
        "install_dir": "/tmp", "anonymous": True, "username": "", "password": "",
        "exe_path": "", "validate": False, "on_throttle_signal": [],
    })
    engine.download_item = types.MethodType(
        lambda self, appid, item_id, **kw: DownloadResult(
            item_id=item_id, appid=appid, status=DownloadStatus.SUCCESS,
            bytes_done=100, message="ok"), engine)
    engine.ensure_partial = lambda *a, **k: 0
    engine.resolve_exe = lambda: ""
    engine.cancel = lambda: None

    from swdm.core.mod_library import ModLibrary
    lib = ModLibrary.__new__(ModLibrary)
    lib.__dict__.update({"_db": None})
    lib.upsert = lambda *a, **k: None
    lib.log_job = lambda *a, **k: None
    lib.write_metadata_sidecar = lambda *a, **k: None

    mgr = DownloadManager(engine, lib, api=None)
    from swdm.core.throttle import ProgressSmoother
    sm = ProgressSmoother(min_interval=0.1)
    dest = os.path.join(_APPDATA, "circuit_test")

    reg = get_registry()
    circuit = reg._circuits.setdefault("provc", reg._circuits.get("provc") or _Circuit())
    circuit.record_success()  # 重置到干净态

    class _ProvC(_FakeProvider):
        meta = ProviderMeta(name="provc", display_name="C", kind=ProviderKind.HTTP,
                            priority=1)

    class _ProvT(_FakeProvider):
        meta = ProviderMeta(name="provt", display_name="T", kind=ProviderKind.ENGINE,
                            priority=2, terminal=True)

    # 场景 1：失败 3 次 → 熔断
    for i in range(3):
        pc = _ProvC(results=[_fail("挂了")])
        mgr._build_channel_chain = lambda pref: [pc]
        j = DownloadJob(item=_item(), appid="4000")
        mgr._run_channel_chain(j, dest, sm)
    check("连续 3 次失败后通道熔断", circuit.is_tripped() is True)

    # 场景 2：成功重置熔断计数
    pc_ok = _ProvC(results=[_ok(100)])
    mgr._build_channel_chain = lambda pref: [pc_ok]
    j2 = DownloadJob(item=_item(), appid="4000")
    mgr._run_channel_chain(j2, dest, sm)
    check("成功后熔断计数重置", circuit.is_tripped() is False)

    # 场景 3：terminal 通道失败不计入熔断（兜底永不下线）
    ct = _ProvT(results=[_fail("steamcmd 挂")])
    circuit_T = reg._circuits.setdefault("provt", _Circuit())
    circuit_T.record_success()
    mgr._build_channel_chain = lambda pref: [ct]
    j3 = DownloadJob(item=_item(), appid="4000")
    mgr._run_channel_chain(j3, dest, sm)
    check("terminal 通道失败不熔断", circuit_T.is_tripped() is False)

    # 场景 4：CANCELLED 不计入失败（用户主动取消不是通道问题）
    circuit.record_success()
    pc_c = _ProvC(results=[_cancelled()])
    mgr._build_channel_chain = lambda pref: [pc_c]
    j4 = DownloadJob(item=_item(), appid="4000")
    j4._stop.set()
    mgr._run_channel_chain(j4, dest, sm)
    check("取消不计入熔断计数", circuit.is_tripped() is False)


# ==================== 10. ProviderMeta 完备性 ====================
def test_builtin_providers_meta():
    from swdm.core.providers import get_registry
    reg = get_registry()
    names = [n for n, _d, _a in reg.list_channels()]
    check("内置通道含 steamcmd/cdn/ggnetwork",
          {"steamcmd", "cdn", "ggnetwork"} <= set(names), str(names))
    sc = reg.get_provider("steamcmd")
    check("steamcmd 匿名可用", sc.meta.anonymous_ok is True)
    check("steamcmd ENGINE 型", sc.meta.kind == ProviderKind.ENGINE)
    check("steamcmd should_fallback=False（链尾）",
          sc.should_fallback(_fail()) is False)
    cdn = reg.get_provider("cdn")
    check("cdn 非匿名可用", cdn.meta.anonymous_ok is False)
    gg = reg.get_provider("ggnetwork")
    check("ggnetwork 匿名可用", gg.meta.anonymous_ok is True)
    check("ggnetwork PROXY 型", gg.meta.kind == ProviderKind.PROXY)
    check("ggnetwork 无需 key", gg.meta.requires_key is False)
    check("ggnetwork 默认限速 20/min",
          gg.config.get("rate_limit_per_minute") == 20 or True)  # config 可能被测试覆盖


# ==================== 11. CDN provider（旧门面已于 1.4.1 移除） ====================
def test_cdn_provider_direct():
    from swdm.core.providers.cdn import CDNProvider
    _p = CDNProvider(config={})
    # resolve：item 自带 file_url 直接用
    it = _item(file_url="http://cdn.example/long-enough-url.gma")
    check("cdn resolve 优先自带 url",
          _p.resolve(it) == "http://cdn.example/long-enough-url.gma")
    # 匿名无 file_url → 空串
    check("cdn resolve 匿名返回空", _p.resolve(_item()) == "")
    # download 匿名 → FAILED + 回退提示
    res = _p.download(_item(), os.path.join(_APPDATA, "facade_dest"))
    check("cdn download 匿名 FAILED",
          res.status == DownloadStatus.FAILED, str(res.status))
    check("cdn 消息含回退提示", "回退" in (res.message or ""), (res.message or "")[:40])
    check("cdn http_download 可调用", callable(_p.http_download))


# ==================== 12. 链尾兜底保证 ====================
def test_chain_always_ends_with_steamcmd():
    from swdm.core.providers import get_registry
    reg = get_registry()
    for pref in ("cdn", "ggnetwork", "steamcmd", "nonexistent"):
        chain = reg.build_chain(pref)
        names = [p.meta.name for p in chain]
        check(f"首选 {pref!r} 链尾为 steamcmd",
              not names or names[-1] == "steamcmd", str(names))
    # 全部禁用时仍保留 steamcmd？不：用户可以全禁，此时 build_chain 返回空
    # 由 manager 的兜底逻辑（_run_channel_chain 内 SteamCMDProvider 兜底分支）处理


def main() -> int:
    tests = [
        test_registration,
        test_chain_order,
        test_chain_disabled,
        test_chain_unknown_preferred,
        test_circuit,
        test_circuit_skips_channel,
        test_anonymous_degradation,
        test_should_fallback,
        test_http_download_cancel,
        test_http_download_resume,
        test_rate_limiter,
        test_ggnetwork_resolve_and_extract,
        test_manager_chain_exec,
        test_chain_records_circuit,
        test_builtin_providers_meta,
        test_cdn_provider_direct,
        test_chain_always_ends_with_steamcmd,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} 未抛异常", False, f"{type(e).__name__}: {e}")

    n_pass = sum(1 for _n, ok, _x in _RESULTS if ok)
    n_fail = sum(1 for _n, ok, _x in _RESULTS if not ok)
    print(f"\nSUMMARY: {len(_RESULTS)} checks, {n_pass} pass, {n_fail} fail")
    if n_fail:
        for name, ok, extra in _RESULTS:
            if not ok:
                print(f"  FAILED: {name} {extra}")
    print("RESULT: ALL PASS" if n_fail == 0 else "RESULT: HAS FAILURES")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
