"""t45 · bug 复测第二轮：核心逻辑独立复测（1.4.1 打包终态）。

参照 1.4.0 t26 的方法：独立构造的 mock 数据 + 边界场景，刻意不重复
t32/t33/t34/t37/t38/t41 各任务自测的用例（自测见 tests/test_providers.py、
test_t33_detail_cache.py、test_t34_nextpage_prefetch.py、test_t37_lib_updates.py、
test_failure_reason.py、test_account_provider.py）。脚本式：check() + RESULT: ALL PASS。

复测重点（任务书六项 + 打包终态）：
  P. 打包终态核对（exe/手册/安装包版本/新模块入包）
  A. detail_cache：双失效（TTL 边界 + time_updated 相等/变化）+ 深拷贝 + 损坏容忍
  B. 预取代际丢弃 + 熔断守卫（_do 层重入/熔断/暖缓存短路/无 appid/daemon）
  C. check_updates：50/51 批边界、progress 精确序列、cancel 首批前、
     逐次实时比对（bypass api_cache 语义）、中间批失败隔离
  D. failure_reason：8 桶独立消息、误报红线（三条通用串单次绝不映射账号）、
     优先级组合、render 全桶
  E. account provider：默认链不含、会话级失活、熔断豁免（经真实 manager 路径）、
     失败文案归类 LOGIN_FAILED
  F. GGNetwork：resolve url 优先（position>0 不再丢弃）、CDN 改写各形状
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import types

_TMP = tempfile.mkdtemp(prefix="swdm_t45_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

out = []
ok = True


def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    out.append(f"[{'PASS' if cond else 'FAIL'}] {name}{' ' + str(e) if e else ''}")


# =====================================================================
# P. 打包终态核对
# =====================================================================
_exe = os.path.join(_ROOT, "build", "dist", "SWDM", "SWDM.exe")
_manual = os.path.join(_ROOT, "build", "dist", "SWDM", "_internal", "manual")
_installer = os.path.join(_ROOT, "installer", "Output", "SWDM-Setup-1.4.1.exe")

check("P1 SWDM.exe 存在且 >8MB", os.path.isfile(_exe)
      and os.path.getsize(_exe) > 8_000_000,
      f"{os.path.getsize(_exe) if os.path.isfile(_exe) else 'missing'}")
_h = os.path.join(_manual, "SWDM-用户手册.html")
_p = os.path.join(_manual, "SWDM-用户手册.pdf")
check("P2 手册 HTML 随包且非空", os.path.isfile(_h) and os.path.getsize(_h) > 100_000,
      f"{os.path.getsize(_h) if os.path.isfile(_h) else 'missing'}")
check("P2b 手册 PDF 随包且非空", os.path.isfile(_p) and os.path.getsize(_p) > 1_000_000,
      f"{os.path.getsize(_p) if os.path.isfile(_p) else 'missing'}")
check("P3 安装包存在且 >40MB", os.path.isfile(_installer)
      and os.path.getsize(_installer) > 40_000_000,
      f"{os.path.getsize(_installer) if os.path.isfile(_installer) else 'missing'}")
if os.path.isfile(_installer):
    _bin = open(_installer, "rb").read()
    # VS_VERSION_INFO 中 ProductVersion 以 UTF-16LE 存储
    check("P3b 安装包内嵌版本资源为 1.4.1",
          "1.4.1".encode("utf-16le") in _bin)
else:
    check("P3b 安装包内嵌版本资源为 1.4.1", False, "installer missing")

from swdm.core.paths import APP_VERSION  # noqa: E402

check("P4 源码 APP_VERSION == 1.4.1", APP_VERSION == "1.4.1", APP_VERSION)
_iss = os.path.join(_ROOT, "installer", "swdm.iss")
_iss_txt = open(_iss, "r", encoding="utf-8").read() if os.path.isfile(_iss) else ""
check("P4b swdm.iss 定义 1.4.1",
      "SWDMVersion" in _iss_txt and '"1.4.1"' in _iss_txt, "")

if os.path.isfile(_exe):
    _exe_bin = open(_exe, "rb").read()
    # PyInstaller 归档 TOC 中的模块名（新 1.4.1 模块入包证据）
    _m1 = b"failure_reason" in _exe_bin
    _m2 = b"account_steamcmd" in _exe_bin
    _m3 = b"swdm.core.providers" in _exe_bin
    check("P5 exe 归档含新模块 failure_reason / account_steamcmd / providers",
          _m1 and _m2 and _m3, f"{_m1}/{_m2}/{_m3}")
else:
    check("P5 exe 归档含新模块 failure_reason / account_steamcmd / providers",
          False, "exe missing")

# =====================================================================
# A. detail_cache（双失效 + 深拷贝 + 损坏容忍，独立夹具）
# =====================================================================
from swdm.core.detail_cache import DetailDiskCache  # noqa: E402

_d = tempfile.mkdtemp(prefix="swdm_t45_dc_")
c = DetailDiskCache(root_dir=_d, ttl_hours=0.01)       # 36 秒 TTL
c.set("T100", "<html>x</html>", time_updated=42)

# A1 TTL 边界：cached_at 回拨至到期前 1 秒 → 仍命中
_path100 = c._path("T100")
with open(_path100, "r", encoding="utf-8") as f:
    _entry = json.load(f)
_entry["cached_at"] = time.time() - 35.0
with open(_path100, "w", encoding="utf-8") as f:
    json.dump(_entry, f)
hit, html = c.get("T100", 42)
check("A1 TTL 边界：到期前 1 秒仍命中", hit is True and html == "<html>x</html>")

# A2 TTL 边界：回拨至到期后 1 秒 → miss 且条目被物理删除
_entry["cached_at"] = time.time() - 37.0
with open(_path100, "w", encoding="utf-8") as f:
    json.dump(_entry, f)
hit2, _ = c.get("T100", 42)
check("A2 TTL 边界：到期后 1 秒判 miss 并删除", hit2 is False
      and not os.path.isfile(_path100))

# A3 time_uploaded 相等 → 命中（「变化才失效」的补集）
c.set("T200", "<html>y</html>", time_updated=100)
hit3, html3 = c.get("T200", 100)
check("A3 time_updated 相等不误判失效（命中）", hit3 is True and html3 == "<html>y</html>")

# A4 双失效优先级：TTL 已过但 time_updated 一致 → 仍 miss（TTL 优先）
c.set("T201", "<html>z</html>", time_updated=100)
_p201 = c._path("T201")
with open(_p201, "r", encoding="utf-8") as f:
    _e201 = json.load(f)
_e201["cached_at"] = time.time() - 3600.0
with open(_p201, "w", encoding="utf-8") as f:
    json.dump(_e201, f)
hit4, _ = c.get("T201", 100)
check("A4 TTL 优先于 time_updated（过期即 miss，即使 tu 一致）", hit4 is False)

# A5 损坏容忍：cached_at 非法字符串 → miss 且不抛
c.set("T300", "<html>c</html>", 1)
_p300 = c._path("T300")
with open(_p300, "r", encoding="utf-8") as f:
    _e300 = json.load(f)
_e300["cached_at"] = "not-a-number"
with open(_p300, "w", encoding="utf-8") as f:
    json.dump(_e300, f)
try:
    hit5, _ = c.get("T300", 1)
    _corrupt_ok = hit5 is False and not os.path.isfile(_p300)
except Exception as exc:                                # noqa: BLE001
    _corrupt_ok = False
check("A5 损坏容忍：cached_at 非法 → miss 且清理，不抛异常", _corrupt_ok)

# A6 损坏容忍：time_updated 字段非法 → miss 不崩
c.set("T301", "<html>d</html>", 1)
_p301 = c._path("T301")
with open(_p301, "r", encoding="utf-8") as f:
    _e301 = json.load(f)
_e301["time_updated"] = "XX"
with open(_p301, "w", encoding="utf-8") as f:
    json.dump(_e301, f)
try:
    hit6, _ = c.get("T301", 1)
    _tu_bad_ok = hit6 is False
except Exception as exc:                                # noqa: BLE001
    _tu_bad_ok = False
check("A6 损坏容忍：time_updated 非法 → miss，不抛异常", _tu_bad_ok)

# A7 损坏容忍：html 字段为非字符串真值 → 不抛异常（写路径只写 str，
# 此为「读取永远不抛进 UI」的防御性验证）
c.set("T302", "<html>e</html>", 1)
_p302 = c._path("T302")
with open(_p302, "r", encoding="utf-8") as f:
    _e302 = json.load(f)
_e302["html"] = 12345
with open(_p302, "w", encoding="utf-8") as f:
    json.dump(_e302, f)
try:
    _h7, _v7 = c.get("T302", 1)
    _weird_ok = True
except Exception as exc:                                # noqa: BLE001
    _weird_ok = False
check("A7 损坏容忍：html 类型损坏不抛异常（写路径不可产生）", _weird_ok)

# A8 .tmp 残留不被当作缓存条目（get 只读 .json）
c.set("T400", "<html>t</html>", 5)
with open(c._path("T400") + ".tmp", "w", encoding="utf-8") as f:
    f.write("garbage half-written")
hit8, html8 = c.get("T400", 5)
check("A8 .tmp 残留不污染 get（只读 .json）", hit8 is True and html8 == "<html>t</html>")

# A9 目标 .json 路径被目录占据 → miss 不崩
c.set("T401", "<html>g</html>", 5)
_p401 = c._path("T401")
os.remove(_p401)
os.makedirs(_p401)
try:
    hit9, _ = c.get("T401", 5)
    _dirok = hit9 is False
except Exception as exc:                                # noqa: BLE001
    _dirok = False
os.rmdir(_p401) if os.path.isdir(_p401) else None
check("A9 .json 路径是目录 → miss 不抛", _dirok)

# A10 深拷贝/往返：复杂 unicode HTML 二次 get 内容一致且文件未变
_big = '<html><body>café \U0001F600 <b>"引号" \'嵌套\'</b>><!--注释--></body></html>'
c.set("T500", _big, 9)
_h10a, v10a = c.get("T500", 9)
_h10b, v10b = c.get("T500", 9)
check("A10 复杂内容二次往返一致（深拷贝语义）",
      v10a == _big and v10b == _big and _h10a and _h10b)

# A11 并发读写同一条目不崩、终态可收敛
c.set("T600", "<html>init</html>", 7)
errors = []


def _rw(k):
    try:
        for i in range(30):
            c.set(k, f"<html>v{i}</html>", 7)
            c.get(k, 7)
    except Exception as exc:                              # noqa: BLE001
        errors.append(exc)


ths = [threading.Thread(target=_rw, args=("T600",)) for _ in range(8)]
for t in ths:
    t.start()
for t in ths:
    t.join()
_h11, v11 = c.get("T600", 7)
check("A11 8 线程并发 set/get 不崩且终态收敛", not errors and _h11
      and v11.startswith("<html>v"), str(errors[:1]))

# A12 set 空 html 不落盘
c.set("T700", "", 3)
check("A12 set 空 html 不写文件", not os.path.isfile(c._path("T700")))

# A13 invalidate 只清 .json，不动 .tmp 残留
c.set("T800", "<html>i</html>", 3)
_tmp_file = c._path("T800") + ".tmp"
with open(_tmp_file, "w", encoding="utf-8") as f:
    f.write("residue")
n = c.invalidate()
check("A13 invalidate 删除自身条目", n >= 1 and not os.path.isfile(c._path("T800")))
check("A13b invalidate 不删 .tmp 残留（仅清缓存条目）", os.path.isfile(_tmp_file))

# =====================================================================
# C. check_updates（批边界 / progress / cancel / 实时比对 / 中间批失败）
# =====================================================================
from swdm.core.steam_api import SteamAPI  # noqa: E402

api = SteamAPI()
posts = {"n": 0}
BASE_TU = 1000
NEW_TU: dict[str, int] = {}


def _fake_post(path, data):
    posts["n"] += 1
    n = int(data.get("itemcount", 0) or 0)
    ids = [data.get(f"publishedfileids[{i}]") for i in range(n)]
    details = []
    for i in ids:
        tu = NEW_TU.get(str(i), BASE_TU)
        details.append({"publishedfileid": str(i), "result": 1,
                        "time_updated": tu, "title": f"m{i}", "appid": "4000"})
    return {"response": {"publishedfiledetails": details}}


api._api_post = _fake_post
# 测试局部：把批间端点节流置 0，避免 3s/批 等待拖慢回归（行为本身由
# _ENDPOINT_INTERVALS 条目覆盖，见 C0）
_IV = "/ISteamRemoteStorage/"
_orig_iv = SteamAPI._ENDPOINT_INTERVALS.get(_IV)
SteamAPI._ENDPOINT_INTERVALS[_IV] = 0.0
check("C0 批量端点节流基准存在（/ISteamRemoteStorage/）",
      _orig_iv is not None and _orig_iv > 0, str(_orig_iv))

# C1 恰 50 条 → 1 批 1 次请求
NEW_TU.clear()
posts["n"] = 0
recs50 = [(f"{i:04d}", BASE_TU) for i in range(50)]
res = api.check_updates(recs50)
check("C1 恰 50 条 → 1 次请求（整批边界）", res == [] and posts["n"] == 1,
      f"posts={posts['n']}")

# C2 51 条 → 2 批，progress 精确序列
NEW_TU.clear()
NEW_TU["0050"] = 2000          # 第 51 条（索引 50）有更新
posts["n"] = 0
prog = []
recs51 = [(f"{i:04d}", BASE_TU) for i in range(51)]
res = api.check_updates(recs51, progress=lambda d, t: prog.append((d, t)))
check("C2 51 条 → 2 次请求（第 2 批 1 条）", posts["n"] == 2,
      f"posts={posts['n']}")
check("C2b 结果只含变化项", res == ["0050"], str(res))
check("C2c progress 精确序列 [(50,51),(51,51)]",
      prog == [(50, 51), (51, 51)], str(prog))

# C3 cancel 首批前 → 零请求、零 progress、空结果
posts["n"] = 0
prog2 = []
res = api.check_updates(recs50, progress=lambda d, t: prog2.append((d, t)),
                        cancel=lambda: True)
check("C3 cancel 首批前 → 零请求", posts["n"] == 0, f"posts={posts['n']}")
check("C3b cancel 首批前 → 未回调 progress", prog2 == [], str(prog2))
check("C3c cancel 首批前 → 返回空列表", res == [], str(res))

# C4 逐次实时比对（bypass api_cache 的值级证明）：同一会话内两次调用，
# API 返回值变化 → 结果立即跟随；不存在「首次结果被缓存」的回归
NEW_TU.clear()
NEW_TU["X1"] = 5000
r1 = api.check_updates([("X1", BASE_TU), ("X2", BASE_TU)])
NEW_TU.clear()                                     # 第二次 API 全部回到旧值
r2 = api.check_updates([("X1", BASE_TU), ("X2", BASE_TU)])
check("C4 第一次 API 新值 → 报告更新", r1 == ["X1"], str(r1))
check("C4b 第二次 API 旧值 → 不报告（逐次实时比对，无内部结果缓存）",
      r2 == [], str(r2))

# C5 中间批失败隔离：150 条 = 3 批，第 2 批抛异常 → 该批跳过，其余完成
NEW_TU.clear()
NEW_TU.update({f"{i:04d}": 2000 for i in range(150)})   # 全部标记为新值
posts["n"] = 0
_flaky_calls = {"n": 0}


def _flaky_post(path, data):
    _flaky_calls["n"] += 1
    if _flaky_calls["n"] == 2:
        raise RuntimeError("network down on batch 2")
    # 成功路径直接构造响应（不经 _fake_post，避免 posts 双计数）
    _n = int(data.get("itemcount", 0) or 0)
    _ids = [data.get(f"publishedfileids[{i}]") for i in range(_n)]
    details = [{"publishedfileid": str(i), "result": 1,
                "time_updated": NEW_TU.get(str(i), BASE_TU),
                "title": f"m{i}", "appid": "4000"} for i in _ids]
    return {"response": {"publishedfiledetails": details}}


api._api_post = _flaky_post
recs150 = [(f"{i:04d}", BASE_TU) for i in range(150)]
res = api.check_updates(recs150)
api._api_post = _fake_post
# 批 1 = 0000..0049，批 2 = 0050..0099（失败跳过），批 3 = 0100..0149
expect = [f"{i:04d}" for i in list(range(50)) + list(range(100, 150))]
check("C5 中间批失败 → 3 批全跑、失败批条目不误标",
      _flaky_calls["n"] == 3 and res == expect,
      f"calls={_flaky_calls['n']} len={len(res)}")
check("C5b 失败批条目不在结果集（如 0075）", "0075" not in res)
check("C5c 失败批后一批条目仍检出（如 0100）", "0100" in res)

# C6 相等与更旧都报告：tu 相等 → 不报；Steam 值更旧 → 不报
NEW_TU.clear()
res = api.check_updates([("E1", 1000), ("E2", 2000)])   # API 均回 1000
check("C6 tu 相等或 Steam 更旧 → 均不报告", res == [], str(res))

# C7 非法记录过滤（空 id / tu<=0）→ 零请求
posts["n"] = 0
res = api.check_updates([("", 1000), ("999", 0), ("888", -5)])
check("C7 非法记录被过滤且零请求", res == [] and posts["n"] == 0,
      f"posts={posts['n']}")

SteamAPI._ENDPOINT_INTERVALS[_IV] = _orig_iv

# =====================================================================
# D. failure_reason（8 桶 + 误报红线 + 优先级 + render）
# =====================================================================
from swdm.core.failure_reason import (  # noqa: E402
    FailureBucket, RESTRICTED_APPS, classify_failure, render_failure,
)

check("D0 RESTRICTED_APPS 含 DayZ 与 Barotrauma",
      {"221100", "602960"} <= set(RESTRICTED_APPS), str(sorted(RESTRICTED_APPS)))

_dmsgs = [
    ("磁盘满(EN)", "ERROR! No space left on device [errno 28]",
     FailureBucket.DISK_FULL),
    ("空成功(E③)", "steamcmd 报告成功但下载内容为空（可能触发限流）",
     FailureBucket.EMPTY_SUCCESS),
    ("限流(消息)", "Rate limited by Steam, retry later",
     FailureBucket.RATE_LIMITED),
    ("网络(消息)", "Connection to Steam timed out after 30s",
     FailureBucket.NETWORK),
    ("登录失败", "Login Failure: Invalid Password",
     FailureBucket.LOGIN_FAILED),
    ("物品下架", "The item you tried to download does not exist (result=9)",
     FailureBucket.ITEM_GONE),
    ("账号正向①(Barotrauma)", "引擎未开始下载该物品",
     FailureBucket.ACCOUNT_NEEDED),
    ("通用 I/O", "ERROR! I/O Operation Failed",
     FailureBucket.GENERIC),
]
for name, msg, want in _dmsgs:
    kw = {}
    if name.startswith("账号正向"):
        kw = {"appid": "602960"}
    got = classify_failure(msg, **kw)
    check(f"D1 {name} → {want.value}", got == want, got.value)

# D2 误报红线：三条通用串单次消息绝不映射 ACCOUNT_NEEDED
for msg in ("ERROR! I/O Operation Failed",
            "Failed to download item 123456 [Worker Error]",
            "Not Logged On"):
    b = classify_failure(msg)
    check(f"D2 红线串单次不映射账号：{msg[:28]}…",
          b != FailureBucket.ACCOUNT_NEEDED, b.value)

# D3 红线边界：同一通用串重复出现 + 无网络信号 → 正向②成立（设计行为）
b_rep = classify_failure("ERROR! I/O Operation Failed",
                         attempt_messages=["ERROR! I/O Operation Failed",
                                           "ERROR! I/O Operation Failed"])
check("D3 同一通用串重试 2 次且无网络信号 → ACCOUNT_NEEDED（正向②）",
      b_rep == FailureBucket.ACCOUNT_NEEDED, b_rep.value)
b_rep_t = classify_failure("ERROR! I/O Operation Failed",
                           signals=["timeout"],
                           attempt_messages=["ERROR! I/O Operation Failed",
                                             "ERROR! I/O Operation Failed"])
check("D3b 同串但有 timeout 信号 → NETWORK（正向②被否决）",
      b_rep_t == FailureBucket.NETWORK, b_rep_t.value)

# D4 优先级组合：磁盘 > 限流 > 网络 > 登录
check("D4 磁盘+超时同串 → DISK_FULL（磁盘优先）",
      classify_failure("磁盘空间不足且 connection timed out")
      == FailureBucket.DISK_FULL)
check("D4b 登录失败+限流字样 → RATE_LIMITED（限流优先于登录）",
      classify_failure("Invalid Password 且触发限流")
      == FailureBucket.RATE_LIMITED)
check("D4c 运行信号覆盖消息（signals 优先）",
      classify_failure("普通失败", signals=["rate_limit"])
      == FailureBucket.RATE_LIMITED)

# D5 空消息 → GENERIC 不崩
check("D5 空消息 → GENERIC", classify_failure("") == FailureBucket.GENERIC)

# D6 render 全桶非空
_all_ok = True
for b in FailureBucket:
    txt = render_failure(b, "raw-原文")
    if not txt:
        _all_ok = False
check("D6 render 8 桶全非空", _all_ok)
_acct_txt = render_failure(FailureBucket.ACCOUNT_NEEDED)
check("D6b 账号文案含「可能」且含登录引导",
      "可能" in _acct_txt and "账号" in _acct_txt, _acct_txt[:40])
_gen_txt = render_failure(FailureBucket.GENERIC)
check("D6c 通用文案不含「账号」（不误导）", "账号" not in _gen_txt, _gen_txt[:40])
check("D6d 通用文案说明未区分并指引日志",
      "未区分" in _gen_txt and "日志" in _gen_txt, "")
check("D6e LOGIN_FAILED 透出原文",
      render_failure(FailureBucket.LOGIN_FAILED, "原始登录失败串")
      == "原始登录失败串")
check("D6f EMPTY_SUCCESS 透出原文",
      render_failure(FailureBucket.EMPTY_SUCCESS, "原始空成功串")
      == "原始空成功串")

# =====================================================================
# E. account provider（默认链不含 / 会话级失活 / 熔断豁免）
# =====================================================================
from swdm.core.providers import get_registry  # noqa: E402
from swdm.core.providers.account_steamcmd import (  # noqa: E402
    AccountSteamCMDProvider, _ACCOUNT_FAIL_HINT, reset_auth_state,
    set_auth_manager,
)
from swdm.core.providers.base import ProviderKind  # noqa: E402
from swdm.core.steamcmd_engine import DownloadResult, DownloadStatus  # noqa: E402

reg = get_registry()


class _FakeAuth:
    def __init__(self, user="t45user", pw="t45pw", guard=""):
        self._c = (user, pw, guard)

    def is_anonymous(self):
        return not self._c[0]

    def get_credentials(self):
        return self._c


# E1 默认链不含（无 AuthManager）
set_auth_manager(None)
chain_d = reg.build_chain()
names_d = [p.meta.name for p in chain_d]
check("E1 无 AuthManager → 默认链不含 account_steamcmd",
      "account_steamcmd" not in names_d, str(names_d))
check("E1b 默认链尾仍是 steamcmd 兜底",
      names_d and names_d[-1] == "steamcmd", str(names_d))

# E2 登录态：链首为账号通道、链尾 steamcmd
set_auth_manager(_FakeAuth())
prov = reg.get_provider("account_steamcmd", None)
check("E2 登录态 is_configured=True", prov.is_configured() is True)
chain_l = reg.build_chain("account_steamcmd")
names_l = [p.meta.name for p in chain_l]
check("E2b 首选账号通道时链首为 account_steamcmd",
      names_l[:1] == ["account_steamcmd"], str(names_l))
check("E2c 登录态链尾仍是 steamcmd",
      names_l and names_l[-1] == "steamcmd", str(names_l))

# E3 会话级失活：认证失败 → 失活、链回退匿名、文案替换
# （在注册表实例上验证 —— build_chain 真正咨询的对象）
res3 = DownloadResult(item_id="I1", appid="4000",
                      status=DownloadStatus.FAILED,
                      message="Login Failure: Invalid Password")
prov.note_result(res3)
check("E3 认证失败 → _auth_dead=True（会话级失活）", prov._auth_dead is True)
check("E3b 失活后 is_configured=False", prov.is_configured() is False)
check("E3c 失活后链不含账号通道（注册表实例生效）",
      "account_steamcmd" not in [p.meta.name for p in reg.build_chain()])
check("E3d 文案替换为风控提示（含「回退匿名通道」）",
      res3.message == _ACCOUNT_FAIL_HINT and "回退匿名通道" in res3.message)

# E4 非认证失败不失活（I/O 通用失败不误判）
prov3 = AccountSteamCMDProvider({}, api=None)
res4 = DownloadResult(item_id="I2", appid="4000",
                      status=DownloadStatus.FAILED,
                      message="ERROR! I/O Operation Failed")
prov3.note_result(res4)
check("E4 通用 I/O 失败不触发会话级失活", prov3._auth_dead is False)

# E5 熔断豁免 + 失败归类（经真实 DownloadManager 路径）
from swdm.core.downloader import DownloadJob, DownloadManager  # noqa: E402
from swdm.core.mod_library import ModLibrary  # noqa: E402
from swdm.core.steamcmd_engine import SteamCMDEngine  # noqa: E402
from swdm.core.throttle import ProgressSmoother  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402


def _mk_mgr():
    engine = SteamCMDEngine.__new__(SteamCMDEngine)
    engine.__dict__.update({
        "install_dir": os.path.join(_TMP, "eng45"), "anonymous": True,
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
    m = DownloadManager(engine, lib, api=None)
    m.auto_retry = 0            # 强制终态失败，走归类路径
    return m


mgr = _mk_mgr()
prov4 = AccountSteamCMDProvider({}, api=None)
prov4.set_engine(mgr.engine)     # 共享引擎占位（download 路径由下面替换）


class _FakeAcctEngine:
    def download_item(self, appid, item_id, **kw):
        return DownloadResult(item_id=item_id, appid=appid,
                              status=DownloadStatus.FAILED,
                              message="Login Failure: Invalid Password")


prov4.get_engine = lambda: _FakeAcctEngine()     # 模拟账号专属引擎登录失败
mgr._build_channel_chain = lambda pref: [prov4]

job = DownloadJob(item=WorkshopItem(publishedfileid="I3", title="T", appid="4000"),
                  appid="4000")
mgr._active[job.id] = job
mgr._exec_job(job)
_circ = reg._circuits.get("account_steamcmd")
check("E5 账号认证失败经真实 manager 路径后通道未熔断（breaker_exempt）",
      _circ is not None and not _circ.is_tripped() and _circ._fail == 0,
      f"fail={_circ._fail if _circ else 'n/a'}")
check("E5b 会话级失活在 manager 路径同样生效", prov4._auth_dead is True)
check("E5c 终态归类 login_failed（凭据桶，非账号桶）",
      job.failure_bucket == "login_failed", job.failure_bucket)
check("E5d 终态文案为渲染文案（LOGIN_FAILED 透出风控提示）",
      job.message == _ACCOUNT_FAIL_HINT, job.message[:40])
check("E5e 账号通道失败建议回退（should_fallback 恒 True）",
      prov4.should_fallback(res3) is True)

# E6 reset_auth_state 重开
reset_auth_state()
check("E6 reset_auth_state 后账号通道重新可用",
      prov._auth_dead is False and prov4._auth_dead is False)

# E7 失活后 get_engine → None，download 直接失败带提示
set_auth_manager(_FakeAuth())
prov5 = AccountSteamCMDProvider({}, api=None)
prov5.set_engine(mgr.engine)
prov5.note_result(DownloadResult(item_id="I4", appid="4000",
                                 status=DownloadStatus.FAILED,
                                 message="RateLimit exceeded"))
check("E7 失活后 get_engine() 返回 None", prov5.get_engine() is None)
r7 = prov5.download(WorkshopItem(publishedfileid="I4", appid="4000"),
                    os.path.join(_TMP, "e7"))
check("E7b 失活后 download → FAILED + 风控提示",
      r7.status == DownloadStatus.FAILED and r7.message == _ACCOUNT_FAIL_HINT,
      r7.message[:40])

# E8 _is_auth_failure 字符串判定
for s, want in (("Login Failure: bad pw", True), ("Not Logged On", True),
                ("RateLimit exceeded", True), ("Invalid Password", True),
                ("ERROR! I/O Operation Failed", False),
                ("下载内容为空", False)):
    check(f"E8 _is_auth_failure({s[:22]}) → {want}",
          AccountSteamCMDProvider._is_auth_failure(
              DownloadResult(item_id="x", appid="4000",
                             status=DownloadStatus.FAILED, message=s)) is want)

set_auth_manager(None)          # 清理模块级状态

# =====================================================================
# F. GGNetwork（resolve url 优先 + CDN 改写，独立响应形状）
# =====================================================================
from swdm.core.providers.ggnetwork import GGNetworkProvider  # noqa: E402


class _Resp:
    def __init__(self, status=200, data=None, json_exc=None):
        self.status_code = status
        self._data = data
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._data


class _Sess:
    def __init__(self, resp=None, exc=None):
        self._r = resp
        self._e = exc
        self.posts = 0

    def post(self, url, json=None, timeout=None):
        self.posts += 1
        if self._e is not None:
            raise self._e
        return self._r


class _ApiStub:
    def __init__(self, sess):
        self._session = sess


def _gg(resp=None, exc=None, cfg=None):
    g = GGNetworkProvider(config=cfg or {})
    s = _Sess(resp=resp, exc=exc)
    g.api = _ApiStub(s)
    return g, s


_item_f = WorkshopItem(publishedfileid="160250458", title="Wiremod",
                       appid="4000")

# F1 url 优先：position>0 与 url 同时存在 → 取 url（1.4.0 position>0 丢弃 bug 不复现）
g1, _ = _gg(_Resp(200, {"url": "https://cdn.ggntw.com/DIRECTFILE77",
                       "queue": {"position": 1, "total": 3}}))
check("F1 position>0 且带 url → 取 url（实测语义）",
      g1.resolve(_item_f) == "https://cdn.ggntw.com/DIRECTFILE77")

# F2 落地页改写：ggntw.com/download/<token> → cdn.ggntw.com/<token>
g2, _ = _gg(_Resp(200, {"url": "https://ggntw.com/download/TOKENXYZ9"}))
check("F2 落地页 url 改写为 cdn.ggntw.com/<token>",
      g2.resolve(_item_f) == "https://cdn.ggntw.com/TOKENXYZ9")

# F3 嵌套 data.url 改写
g3, _ = _gg(_Resp(200, {"data": {"url": "https://ggntw.com/download/NESTTOKN"}}))
check("F3 嵌套 data.url 同样改写为 CDN 直链",
      g3.resolve(_item_f) == "https://cdn.ggntw.com/NESTTOKN")

# F4 非 ggntw 的 /download/ 直链不改写（原样返回）
g4, _ = _gg(_Resp(200, {"url": "https://example.com/download/plain.gma"}))
check("F4 非 ggntw 域名的 /download/ url 原样返回（不改写）",
      g4.resolve(_item_f) == "https://example.com/download/plain.gma")

# F5 落地页带尾斜杠 → token 正确
g5, _ = _gg(_Resp(200, {"url": "https://ggntw.com/download/SLASHTOK/"}))
check("F5 落地页尾斜杠 → token 正确（无 / 残留）",
      g5.resolve(_item_f) == "https://cdn.ggntw.com/SLASHTOK")

# F6 无 url + position>0 → 干净回退空串（不轮询）
g6, _ = _gg(_Resp(200, {"queue": {"position": 7, "total": 10}}))
check("F6 无 url 且 position>0 → 空串干净回退", g6.resolve(_item_f) == "")

# F7 error 体 → 空串
g7, _ = _gg(_Resp(200, {"error": "need login to account"}))
check("F7 后端 error 体 → 空串", g7.resolve(_item_f) == "")

# F8 429 → 空串 + 限流信号上报
g8, _ = _gg(_Resp(429))
sig = []
g8.on_throttle_signal.append(lambda kind, line: sig.append((kind, line)))
check("F8 HTTP 429 → 空串", g8.resolve(_item_f) == "")
check("F8b 429 上报 rate_limit 信号", sig and sig[0][0] == "rate_limit",
      str(sig))

# F9 非 200 → 空串
g9, _ = _gg(_Resp(500, {}))
check("F9 HTTP 500 → 空串", g9.resolve(_item_f) == "")

# F10 非 JSON 响应体 → 空串不崩
g10, _ = _gg(_Resp(200, None, json_exc=ValueError("not json")))
check("F10 响应体非法 JSON → 空串不崩", g10.resolve(_item_f) == "")

# F11 网络层异常（连接错误）→ 空串不崩
import requests  # noqa: E402

g11, _ = _gg(None, exc=requests.ConnectionError("winsock 10053"))
check("F11 session.post 连接异常 → 空串不崩", g11.resolve(_item_f) == "")

# F12 限速配置注入：rate_limit_per_minute=60 → 间隔 1.0s
g12, _ = _gg(cfg={"rate_limit_per_minute": 60})
check("F12 rate_limit_per_minute=60 → 限速间隔 1.0s",
      abs(g12._limiter._interval - 1.0) < 0.01, str(g12._limiter._interval))

# F13 resolve 失败时 download → FAILED + 明确文案 + 建议回退
g13, _ = _gg(_Resp(200, {"error": "need login to account"}))
r13 = g13.download(_item_f, os.path.join(_TMP, "f13"),
                   stop_event=threading.Event())
check("F13 resolve 失败 → download FAILED 且文案明确",
      r13.status == DownloadStatus.FAILED
      and "无法解析下载地址" in (r13.message or ""), (r13.message or "")[:40])
check("F13b 该失败建议链内回退", g13.should_fallback(r13) is True)

# =====================================================================
# B. 预取代际丢弃 + 熔断守卫（GUI 层，放最后：Qt 导入重）
# =====================================================================
from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core import steam_api as _sa_mod  # noqa: E402
from swdm.core.api_cache import get_api_cache, make_cache_key  # noqa: E402
from swdm.core.circuit import CircuitBreaker as _CB  # noqa: E402
from swdm.core.steam_api import WorkshopItem as _WI  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])
win = MainWindow()
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
wt = win.workshop_tab
wt.svc.api._browse_breaker = _CB()          # 隔离的新熔断器
wt._current_appid = lambda: "4000"
wt.search_edit.setText("")
wt.sort_combo.setCurrentIndex(0)
wt.tag_edit.setText("")
wt._page = 1
wt._worker_gen = 100
_full30 = [_WI(publishedfileid=str(i), title=f"t45-{i}", appid="4000")
           for i in range(30)]
wt._items = _full30
_s0 = wt.sort_combo.currentData()


def _fake_cg(self, path, params=None, **kw):
    _net_b["n"] += 1
    return ""


_net_b = {"n": 0}
_orig_cg = _sa_mod.SteamAPI._community_get

# B1 重入保护：_nextpage_prefetching 已置位 → 不再启动线程
wt._nextpage_timer.stop()
wt._nextpage_prefetching = True
_before_thread = wt._nextpage_thread
_sa_mod.SteamAPI._community_get = _fake_cg
_net_b["n"] = 0
try:
    wt._do_prefetch_next_page()
finally:
    _sa_mod.SteamAPI._community_get = _orig_cg
check("B1 预取重入保护：已在预取时不启动新线程",
      wt._nextpage_thread is _before_thread and _net_b["n"] == 0)
wt._nextpage_prefetching = False

# B2 熔断守卫（_do 层）：熔断冷却 → 不发包不启线程
wt.svc.api._browse_breaker = _CB()
wt.svc.api._browse_breaker.force_trip()
_before_thread2 = wt._nextpage_thread
_sa_mod.SteamAPI._community_get = _fake_cg
_net_b["n"] = 0
try:
    wt._do_prefetch_next_page()
finally:
    _sa_mod.SteamAPI._community_get = _orig_cg
check("B2 熔断冷却期 _do_prefetch_next_page 不发包不启线程",
      wt._nextpage_thread is _before_thread2 and _net_b["n"] == 0
      and not wt._nextpage_prefetching)

# B3 暖缓存短路：下一页 key 已在 ApiCache → 不发请求
wt.svc.api._browse_breaker = _CB()
_cache_b = get_api_cache()
_cache_b.invalidate()
_key_p2 = make_cache_key("4000", 2, _s0, "", [], "schinese", 30)
_cache_b.set(_key_p2, [])
_before_thread3 = wt._nextpage_thread
_sa_mod.SteamAPI._community_get = _fake_cg
_net_b["n"] = 0
try:
    wt._do_prefetch_next_page()
finally:
    _sa_mod.SteamAPI._community_get = _orig_cg
check("B3 下一页缓存已暖 → 零网络、不启线程",
      wt._nextpage_thread is _before_thread3 and _net_b["n"] == 0)

# B4 无 appid 守卫 → 不启线程
wt._current_appid = lambda: ""
_cache_b.invalidate()
_before_thread4 = wt._nextpage_thread
_sa_mod.SteamAPI._community_get = _fake_cg
_net_b["n"] = 0
try:
    wt._do_prefetch_next_page()
finally:
    _sa_mod.SteamAPI._community_get = _orig_cg
check("B4 无 appid → 不发包不启线程",
      wt._nextpage_thread is _before_thread4 and _net_b["n"] == 0)
wt._current_appid = lambda: "4000"

# B5 过期代际回包静默丢弃（不抛异常、不改当前页）
wt._worker_gen = 200
_items_before = list(wt._items)
try:
    wt._on_nextpage_prefetched(199, _key_p2)     # 过期代际
    _stale_ok = True
except Exception:                               # noqa: BLE001
    _stale_ok = False
check("B5 过期代际预取回包静默丢弃（不抛异常）", _stale_ok)
check("B5b 当前页物品未被预触及", wt._items == _items_before)
try:
    wt._on_nextpage_prefetched(200, _key_p2)     # 当前代际：读缓存命中
    _cur_ok = True
except Exception:                               # noqa: BLE001
    _cur_ok = False
check("B5c 当前代际回包正常处理（读命中不抛）", _cur_ok)

# B6 真实预取一次：daemon 线程 + 完成 + 一次 browse（与 t34 不同的
# 代际号/物品集，验证打包终态同一代码路径）
_cache_b.invalidate()
wt._worker_gen = 300
wt._page = 3
_sa_mod.SteamAPI._community_get = _fake_cg
_net_b["n"] = 0
try:
    wt._do_prefetch_next_page()
    check("B6a 预取线程为 daemon（退出不挂）",
          wt._nextpage_thread is not None and wt._nextpage_thread.daemon)
    _dl = time.time() + 20
    while wt._nextpage_prefetching and time.time() < _dl:
        app.processEvents()
        time.sleep(0.05)
    check("B6b 预取完成（不卡死）", not wt._nextpage_prefetching)
    check("B6c 预取恰好触发一次 browse 网络请求",
          _net_b["n"] == 1, f"n={_net_b['n']}")
    _k3 = make_cache_key("4000", 4, _s0, "", [], "schinese", 30)
    check("B6d 下一页（第 4 页）key 已暖 ApiCache",
          _cache_b.get(_k3)[0] is True)
finally:
    _sa_mod.SteamAPI._community_get = _orig_cg

# =====================================================================
print("\n".join(out))
n_pass = sum(1 for line in out if line.startswith("[PASS]"))
n_fail = sum(1 for line in out if line.startswith("[FAIL]"))
print(f"\nSUMMARY: {len(out)} checks, {n_pass} pass, {n_fail} fail")
print("RESULT: ALL PASS" if n_fail == 0 and ok else "RESULT: HAS FAILURES")
sys.stdout.flush()
# Qt 进程退出阶段存在已知析构竞态（QThread destroyed while running，
# 与 packager 18:11 冒烟 teardown 崩溃同一既有模式）。结果行已打印并
# flush，run_all 按文本判定；此处直接退出避免 teardown 崩溃的退出码污染。
if n_fail == 0 and ok:
    os._exit(0)
sys.exit(1)
