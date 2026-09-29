"""t26 · bug 复测第二轮：核心逻辑独立复测（1.4.0 打包终态）。

与 t21/t28 的自测刻意不同角度：此处用"独立构造的 mock 数据 + 边界场景"
复测重点，不重复跑同一批用例。脚本式：check() + RESULT: ALL PASS。

复测重点：
  A. provider 链（回退不消耗 auto_retry / should_fallback 结构化判定 /
     熔断冷却恢复 / 探测路径已删 / terminal 豁免）
  B. 匿名降级（需 key provider 跳过 + 链尾 steamcmd）
  C. services.py:78 修复（manager 的 api 注入 provider）
  D. GGNetwork（限速器容量 + 压缩包解压 + 魔数弱校验不误伤）
  E. t22 核心项（cancel pending 集合 / GameSearchClient 熔断退避）
  F. 既有核心在 provider 链下（缓存深拷贝 / 端点节流礼让 / 卡99%）
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import threading
import time
import zipfile

_TMP = tempfile.mkdtemp(prefix="swdm_t26_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

out = []
ok = True


def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    out.append(f"[{'PASS' if cond else 'FAIL'}] {name}{' ' + str(e) if e else ''}")


from swdm.core.steam_api import WorkshopItem  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus  # noqa: E402


def _item(item_id="777", appid="4000", file_size=0, file_url=""):
    return WorkshopItem(publishedfileid=item_id, title=f"T{item_id}", appid=appid,
                        file_size=file_size, file_url=file_url)


# =====================================================================
# A. provider 链（独立角度）
# =====================================================================
from swdm.core.providers import (  # noqa: E402
    Availability,
    DownloadProvider,
    ProviderKind,
    ProviderMeta,
)
from swdm.core.providers.registry import _Circuit  # noqa: E402

# A1. should_fallback 结构化判定：消息含"回退"字样但 SUCCESS 不触发回退
#     （证明判定基于 status/结构，不是消息文本扫描）
class _MsgProv(DownloadProvider):
    meta = ProviderMeta(name="msgprov", display_name="M", kind=ProviderKind.HTTP)

    def __init__(self, results):
        super().__init__({})
        self._results = list(results)

    def probe(self, timeout=8.0):
        return Availability.OK

    def download(self, item, dest_dir, on_progress=None, stop_event=None,
                 total_hint=0):
        return self._results.pop(0)

    def cancel(self):
        pass

    def should_fallback(self, result):
        return result.status == DownloadStatus.FAILED  # 结构化

mp_ok = _MsgProv([DownloadResult(item_id="777", appid="4000",
                                status=DownloadStatus.SUCCESS,
                                message="已通过回退通道完成")])
check("should_fallback 不扫描消息文本（SUCCESS 带'回退'字样不回退）",
      mp_ok.should_fallback(DownloadResult(
          item_id="x", appid="4000", status=DownloadStatus.SUCCESS,
          message="回退完成")) is False)
check("should_fallback FAILED 触发回退",
      mp_ok.should_fallback(DownloadResult(
          item_id="x", appid="4000", status=DownloadStatus.FAILED,
          message="普通失败")) is True)

# A2. 回退不消耗 auto_retry（一条链 = 一次 attempt）
#     独立角度：直接调 _run_channel_chain，三通道链全失败后 job.attempt 仍为 0
import types  # noqa: E402

from swdm.core.downloader import DownloadJob, DownloadManager  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402
from swdm.core.throttle import ProgressSmoother  # noqa: E402


def _mk_mgr():
    engine = SteamCMDEngine.__new__(SteamCMDEngine)
    engine.__dict__.update({
        "install_dir": os.path.join(_TMP, "eng"), "anonymous": True,
        "username": "", "password": "", "exe_path": "", "validate": False,
        "on_throttle_signal": [],
    })
    engine.download_item = types.MethodType(
        lambda self, appid, item_id, **kw: DownloadResult(
            item_id=item_id, appid=appid, status=DownloadStatus.SUCCESS,
            bytes_done=10, message="ok"), engine)
    engine.ensure_partial = lambda *a, **k: 0
    engine.resolve_exe = lambda: ""
    engine.cancel = lambda: None
    lib = ModLibrary.__new__(ModLibrary)
    lib.__dict__.update({"_db": None})
    lib.upsert = lambda *a, **k: None
    lib.log_job = lambda *a, **k: None
    lib.write_metadata_sidecar = lambda *a, **k: None
    return DownloadManager(engine, lib, api=None)


class _ChainProv(DownloadProvider):
    meta = ProviderMeta(name=f"chainprov", display_name="C", kind=ProviderKind.HTTP)

    def __init__(self, results):
        super().__init__({})
        self._results = list(results)
        self.ran = 0

    def probe(self, timeout=8.0):
        return Availability.OK

    def download(self, item, dest_dir, on_progress=None, stop_event=None,
                 total_hint=0):
        self.ran += 1
        return self._results.pop(0)

    def cancel(self):
        pass


mgr = _mk_mgr()
sm = ProgressSmoother(min_interval=0.1)
dest = os.path.join(_TMP, "chain")
p1 = _ChainProv([DownloadResult(item_id="777", appid="4000",
                               status=DownloadStatus.FAILED, message="1 挂")])
p2 = _ChainProv([DownloadResult(item_id="777", appid="4000",
                               status=DownloadStatus.FAILED, message="2 挂")])
p3 = _ChainProv([DownloadResult(item_id="777", appid="4000",
                               status=DownloadStatus.FAILED, message="3 挂")])
mgr._build_channel_chain = lambda pref: [p1, p2, p3]
j = DownloadJob(item=_item(), appid="4000")
res = mgr._run_channel_chain(j, dest, sm)
check("三通道链全失败：每个 provider 都执行过",
      p1.ran == 1 and p2.ran == 1 and p3.ran == 1, f"{p1.ran}/{p2.ran}/{p3.ran}")
check("链内回退不消耗 auto_retry（attempt 仍为 0）",
      j.attempt == 0, str(j.attempt))
check("全失败终态 FAILED", res.status == DownloadStatus.FAILED, str(res.status))

# A3. 熔断冷却恢复（独立时间操作：直接改 _open_at 模拟冷却过期）
c = _Circuit()
for _ in range(3):
    c.record_failure()
check("3 次失败后熔断", c.is_tripped() is True)
c._open_at = time.time() - 61.0  # 冷却已过
check("冷却过期后半开（is_tripped 返回 False）", c.is_tripped() is False)
c.record_failure()  # 半开期失败 → 重新熔断
check("半开期失败重新熔断", c.is_tripped() is True)
c.record_success()
check("成功后完全重置", c.is_tripped() is False)

# A4. 探测路径已删（t28 第 2 项在打包终态的验证）
from swdm.core.providers import get_registry  # noqa: E402

reg = get_registry()
sig = inspect.signature(reg.list_channels)
check("list_channels 签名无 probe_results 参数",
      "probe_results" not in sig.parameters, str(sig.parameters))
check("registry 无 probe 方法", not hasattr(reg, "probe"))
check("registry 无 _probe_cache 属性", not hasattr(reg, "_probe_cache"))
check("registry 无 invalidate_probe 方法", not hasattr(reg, "invalidate_probe"))

# A5. terminal 通道在生产链中豁免熔断（独立角度：经 _run_channel_chain，
#     用与 t28 不同的 provider 名 + 直接验证 _circuits 状态）
class _TermProv(_ChainProv):
    meta = ProviderMeta(name="termprov", display_name="T", kind=ProviderKind.ENGINE,
                        priority=1, terminal=True)


cT = reg._circuits.setdefault("termprov", _Circuit())
cT.record_success()
pt = _TermProv([DownloadResult(item_id="777", appid="4000",
                              status=DownloadStatus.FAILED, message="兜底也挂")])
mgr._build_channel_chain = lambda pref: [pt]
jT = DownloadJob(item=_item(), appid="4000")
mgr._run_channel_chain(jT, dest, sm)
check("terminal 通道失败不熔断（兜底永不下线）",
      cT.is_tripped() is False)

# A6. 熔断通道被 build_chain 跳过，冷却后重新纳入
class _RegProv(DownloadProvider):
    """可注册进 registry 的假通道（构造签名与真 provider 一致）。"""
    meta = ProviderMeta(name="skipprov", display_name="S", kind=ProviderKind.HTTP,
                        priority=1)

    def __init__(self, config=None, api=None):
        super().__init__(config or {}, api)

    def probe(self, timeout=8.0):
        return Availability.OK

    def download(self, item, dest_dir, on_progress=None, stop_event=None,
                 total_hint=0):
        return DownloadResult(item_id=str(item.publishedfileid),
                              appid=str(item.appid),
                              status=DownloadStatus.FAILED, message="挂")

    def cancel(self):
        pass


cS = reg._circuits.setdefault("skipprov", _Circuit())
cS.record_success()
reg._classes["skipprov"] = _RegProv
for _ in range(3):
    reg.record_failure("skipprov")  # 模拟生产链三次失败
chain_tripped = reg.build_chain("skipprov")
check("熔断通道被 build_chain 跳过",
      all(p.meta.name != "skipprov" for p in chain_tripped),
      str([p.meta.name for p in chain_tripped]))
cS._open_at = time.time() - 61.0
cS.is_tripped()  # 半开
chain_open = reg.build_chain("skipprov")
check("半开后 build_chain 重新纳入该通道",
      any(p.meta.name == "skipprov" for p in chain_open),
      str([p.meta.name for p in chain_open]))
del reg._classes["skipprov"]

# =====================================================================
# B. 匿名降级（需 key provider 跳过 + 链尾 steamcmd）
# =====================================================================
from swdm.core.config import get_config  # noqa: E402

class _KeyProv(DownloadProvider):
    meta = ProviderMeta(name="keyprov", display_name="K", kind=ProviderKind.HTTP,
                        priority=1, requires_key=True, anonymous_ok=False,
                        key_hint="需 Key")

    def __init__(self, config=None, api=None):
        super().__init__(config or {}, api)

    def probe(self, timeout=8.0):
        return Availability.NO_KEY

    def download(self, item, dest_dir, on_progress=None, stop_event=None,
                 total_hint=0):
        return DownloadResult(item_id=str(item.publishedfileid), appid=str(item.appid),
                              status=DownloadStatus.FAILED, message="无 key")

    def cancel(self):
        pass

    def is_configured(self):
        return False  # 未配置 key


reg._classes["keyprov"] = _KeyProv
reg._circuits.setdefault("keyprov", _Circuit())
chain_anon = reg.build_chain("keyprov")
check("需 key 且未配置的通道被链构造跳过",
      all(p.meta.name != "keyprov" for p in chain_anon),
      str([p.meta.name for p in chain_anon]))
check("匿名降级后链尾仍是 steamcmd",
      chain_anon and chain_anon[-1].meta.name == "steamcmd",
      str([p.meta.name for p in chain_anon]))
del reg._classes["keyprov"]

# =====================================================================
# C. services.py:78 修复（manager 的 api 注入 provider）
# =====================================================================
class _FakeAPI:
    pass


api_obj = _FakeAPI()
mgr2 = _mk_mgr()
mgr2.api = api_obj
sc = mgr2._build_channel_chain("steamcmd")
check("manager 构造的链中 provider 拿到 api（services:78 修复）",
      sc and sc[0].api is api_obj, str(type(sc[0].api)))

# =====================================================================
# D. GGNetwork（限速器容量 / 压缩包解压 / 魔数弱校验不误伤）
# =====================================================================
from swdm.core.providers.ggnetwork import GGNetworkProvider  # noqa: E402

gg = GGNetworkProvider(config={})
limiter = gg._limiter
check("限速器默认 20/min（间隔 3s）",
      abs(limiter._interval - 3.0) < 0.01, str(limiter._interval))
check("限速器突发容量 3（初始令牌）",
      abs(limiter._tokens - 3.0) < 0.01, str(limiter._tokens))
# 突发 3 个令牌后，第 4 个用已置位的 stop_event → 立即返回 False 不阻塞
got = [limiter.acquire() for _ in range(3)]
se = threading.Event(); se.set()
check("突发 3 个令牌立即可用", all(got), str(got))
check("令牌耗尽且 stop_event 置位时 acquire 返回 False 不阻塞",
      limiter.acquire(stop_event=se) is False)

# 压缩包解压（独立夹具：不同 item id + 多层目录）
tmpdir = tempfile.mkdtemp(prefix="swdm_t26_gg_")
arch = os.path.join(tmpdir, "pack.zip")
with zipfile.ZipFile(arch, "w") as zf:
    zf.writestr("deep/nested/555.gma", b"GMAD" + b"\x01" * 250)
final = gg._maybe_extract(arch, tmpdir, "555")
check("zip 多层目录中的 .gma 被提取到 content 根",
      os.path.basename(final) == "555.gma", final)
check("解压后原压缩包删除", not os.path.isfile(arch))

# 魔数弱校验：非 GMAD 但 size 一致 → 只⚠ 不判坏包（不误伤合法转存）
weird = os.path.join(tmpdir, "weird.gma")
with open(weird, "wb") as fh:
    fh.write(b"XXXX" + b"\x01" * 246)  # 250 字节
note, bad = gg._verify_content(weird, _item(file_size=250))
check("魔数错误带⚠", "非标准" in note, note)
check("魔数错误但 size 一致不判坏包", bad is False, str(bad))
# size 一致的正品无⚠
good2 = os.path.join(tmpdir, "good.gma")
with open(good2, "wb") as fh:
    fh.write(b"GMAD" + b"\x01" * 246)
note2, bad2 = gg._verify_content(good2, _item(file_size=250))
check("正品（GMAD + size 一致）无⚠不判坏包", note2 == "" and bad2 is False, note2)

# =====================================================================
# E. t22 核心项
# =====================================================================
# E1. cancel pending 集合：cancel() 同锁内登记 + _stop 置位
mgr3 = _mk_mgr()
it = _item("999")
job = DownloadJob(item=it, appid="4000")
mgr3._queue.append(job)
mgr3._active[job.id] = job
mgr3.cancel(job.id)
check("cancel 后 job 在 _cancelling 集合中", job.id in mgr3._cancelling)
check("cancel 后 _stop 已置位", job._stop.is_set() is True)
check("取消的任务从 _active 移除", job.id not in mgr3._active)

# E2. GameSearchClient 熔断退避（连接错误 → 冷却 15s）
import requests  # noqa: E402

from swdm.core.game_search import GameSearchClient  # noqa: E402

gsc = GameSearchClient()
gsc._record_failure(requests.ConnectionError("10053"))
check("连接错误立即熔断冷却 15s",
      gsc._in_cooldown() is True and abs(gsc._cooldown_until - time.time() - 15.0) < 1.0)
gsc2 = GameSearchClient()
for _ in range(2):
    gsc2._record_failure(RuntimeError("普通失败"))
check("普通失败 2 次不熔断", gsc2._in_cooldown() is False)
gsc2._record_failure(RuntimeError("第 3 次"))
check("普通失败连续 3 次熔断", gsc2._in_cooldown() is True)
check("搜索词过短（<2 字符）返回空不报错", gsc.search("a") == [])
# 缓存命中：search 返回列表副本（外部 append 不污染缓存）
from swdm.core.game_search import GameSearchResult  # noqa: E402

gsc3 = GameSearchClient()
_cached = [GameSearchResult(appid="4000", name="Garry's Mod")]
gsc3._cache["garry"] = (time.time(), _cached)
r3 = gsc3.search("Garry")
check("GameSearch 缓存命中返回结果", len(r3) == 1 and r3[0].appid == "4000")
r3.append(GameSearchResult(appid="x", name="污染"))
check("GameSearch 命中返回副本（不污染缓存）",
      len(gsc3._cache["garry"][1]) == 1)

# =====================================================================
# F. 既有核心在 provider 链下
# =====================================================================
# F1. 卡99%：bytes_done >= total 才 100%
j99 = DownloadJob(item=_item(file_size=1000), appid="4000")
j99.total_bytes = 1000
j99.bytes_done = 999
check("bytes_done=999/total=1000 → percent 99 不卡 100", j99.percent == 99, str(j99.percent))
j99.bytes_done = 1000
check("bytes_done>=total → percent 100", j99.percent == 100, str(j99.percent))

# F2. 缓存深拷贝（browse() 命中缓存时返回深拷贝，enrich() 不污染缓存）
from swdm.core.api_cache import get_api_cache, make_cache_key  # noqa: E402
from swdm.core import steam_api  # noqa: E402

_cache = get_api_cache()
_ck = make_cache_key("4000", 1, "default", "", [], "schinese", 30)
_seed = [WorkshopItem(publishedfileid="1", title="原始", appid="4000")]
_cache.set(_ck, _seed)
_sa = steam_api.SteamAPI()
b1 = _sa.browse(appid="4000", page=1, sort="default", search_text="",
                required_tags=[], language="schinese", numperpage=30)
check("browse 缓存命中返回结果", len(b1) == 1 and b1[0].title == "原始",
      str(b1))
check("browse 命中返回的不是缓存里的同一对象",
      b1[0] is not _seed[0])
b1[0].title = "被污染"
b2 = _sa.browse(appid="4000", page=1, sort="default", search_text="",
                required_tags=[], language="schinese", numperpage=30)
check("browse 深拷贝：外部修改不污染缓存", b2[0].title == "原始", b2[0].title)

# F3. 端点节流礼让：priority=True 绕过等待；低优先级在高优先级在飞时让槽
from swdm.core import steam_api  # noqa: E402

sa = steam_api.SteamAPI.__new__(steam_api.SteamAPI)
sa.__dict__.update({
    "_endpoint_wait": {}, "_endpoint_last": {}, "_priority_pending": 0,
    "_priority_path": None, "_endpoint_lock": threading.Lock(),
    "_session": None, "_api_key": "",
})
pref = next(iter(steam_api.SteamAPI._ENDPOINT_INTERVALS.keys()))
sa._endpoint_last[pref] = time.time()  # 该端点刚请求过 → 低优先级本应等待
ok_low_normal = sa._endpoint_throttle(pref, priority=False)
check("无高优先级排队时低优先级等满间隔后放行", ok_low_normal is True)
sa._endpoint_last[pref] = time.time()
ok_high = sa._endpoint_throttle(pref, priority=True)
check("高优先级请求绕过端节流等待", ok_high is True)
sa._endpoint_last[pref] = time.time()
sa._priority_pending = 1  # 模拟用户点击在飞
ok_low_yield = sa._endpoint_throttle(pref, priority=False)
check("高优先级在飞时低优先级立即让槽（返回 False）", ok_low_yield is False)

# =====================================================================
print("\n".join(out))
n_pass = sum(1 for line in out if line.startswith("[PASS]"))
n_fail = sum(1 for line in out if line.startswith("[FAIL]"))
print(f"\nSUMMARY: {len(out)} checks, {n_pass} pass, {n_fail} fail")
print("RESULT: ALL PASS" if n_fail == 0 and ok else "RESULT: HAS FAILURES")
sys.exit(0 if n_fail == 0 and ok else 1)
