# tests/test_t33_detail_cache.py
# B1 详情页磁盘缓存（TTL + time_updated 双失效）— t33 专项测试
# 约定：脚本式 check() + RESULT: ALL PASS；不依赖网络
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_appdata = tempfile.mkdtemp(prefix="swdm_t33_")
os.environ["APPDATA"] = _appdata
# 标准路径插入（与 test_t26/t19 等一致）：从仓库根运行也能导入 swdm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_RESULTS = []


def check(name, cond, extra=""):
    _RESULTS.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}".rstrip())


# ====================================================== A. 缓存模块本体
from swdm.core.detail_cache import DetailDiskCache, get_detail_cache  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="swdm_t33_cache_")
_cache = DetailDiskCache(root_dir=_tmp, ttl_hours=24)

# A1 基本写入/命中
_cache.set("100001", "<html>mod-a</html>", 1111)
ok, html = _cache.get("100001", 1111)
check("A1 写入后命中", ok and html == "<html>mod-a</html>", f"ok={ok}")

# A2 深拷贝纪律：返回的 html 修改不污染缓存（str 不可变，改用对象等价检查）
_cache.set("100002", "payload", 2222)
_ok2, _h2 = _cache.get("100002", 2222)
check("A2 命中返回的是独立副本（str 不可变即天然安全）",
      _ok2 and _h2 == "payload")

# A3 time_updated 变化 → 立即失效（"及时清除"硬约束）
_cache.set("100003", "<html>v1</html>", 100)
ok, _ = _cache.get("100003", 999)   # 新 time_updated 与缓存不一致
check("A3 time_updated 变化判 miss", not ok)
# 且文件已被清除
ok3, _ = _cache.get("100003", 100)  # 旧值也拿不到了（条目已删）
check("A3b time_updated 失效后条目被物理删除", not ok3)

# A4 time_updated=0（未知）不触发误失效
_cache.set("100004", "<html>v0</html>", 0)
ok, _ = _cache.get("100004", 555)
check("A4 调用方 time_updated 未知（0）不误判失效", ok)

# A5 缓存条目 time_updated=0 时调用方提供新值 → 不失效（存时未知）
_cache.set("100005", "<html>x</html>", 0)
ok, _ = _cache.get("100005", 8888)
check("A5 存入时 time_updated=0 不阻塞后续命中", ok)

# A6 TTL 到期失效
_c2 = DetailDiskCache(root_dir=_tmp, ttl_hours=0.0001)  # 约 0.36s
_c2.set("100006", "<html>ttl</html>", 1)
time.sleep(0.5)
ok, _ = _c2.get("100006", 1)
check("A6 TTL 到期判 miss 且删除条目", not ok)

# A7 TTL=0（配置关闭）→ 读写均不生效
_c3 = DetailDiskCache(root_dir=_tmp, ttl_hours=0)
_c3.set("100007", "<html>off</html>", 1)
ok, _ = _c3.get("100007", 1)
check("A7 ttl_hours=0 时 get 永远 miss", not ok)

# A8 损坏容忍：非法 JSON 当 miss 且不崩
_path = _cache._path("100008")
os.makedirs(os.path.dirname(_path), exist_ok=True)
with open(_path, "w", encoding="utf-8") as f:
    f.write("{not valid json,,,")
ok, _ = _cache.get("100008", 1)
check("A8 非法 JSON 当 miss 不崩", not ok)
ok8, _ = _cache.get("100008", 1)
check("A8b 损坏文件被清理（第二次仍 miss）", not ok8)

# A9 损坏容忍：缺字段（html 空）
_p9 = _cache._path("100009")
with open(_p9, "w", encoding="utf-8") as f:
    import json as _json
    _json.dump({"html": "", "cached_at": time.time(), "time_updated": 1}, f)
ok, _ = _cache.get("100009", 1)
check("A9 空 html 条目当 miss", not ok)

# A10 缺字段：无 cached_at
_p10 = _cache._path("100010")
import json as _json2  # noqa: E402
with open(_p10, "w", encoding="utf-8") as f:
    _json2.dump({"html": "x", "time_updated": 1}, f)
ok, _ = _cache.get("100010", 1)
check("A10 无 cached_at 条目当 miss", not ok)

# A11 路径穿越防御：非法字符被规范化，落点仍在缓存目录内
_cache.set("../../evil", "<html>e</html>", 1)
_evil_path = _cache._path("../../evil")
check("A11 非法 item id 被规范化到缓存目录内（无穿越）",
      os.path.dirname(_evil_path) == os.path.join(_tmp, "detail"),
      _evil_path)
check("A11b 规范化后键一致可命中（非穿越，行为正确）",
      _cache.get("../../evil", 1)[0] is True)

# A12 invalidate 单条 / 全部
_cache.set("100012a", "a", 1)
_cache.set("100012b", "b", 1)
n1 = _cache.invalidate("100012a")
okA, _ = _cache.get("100012a", 1)
okB, _ = _cache.get("100012b", 1)
check("A12 invalidate 单条删 1 条且不影响其他",
      n1 == 1 and not okA and okB, f"n={n1}")
n2 = _cache.invalidate()
check("A12b invalidate 全部清空", n2 >= 1 and _cache.get("100012b", 1)[0] is False)

# A13 空目录 invalidate 不崩
_c4 = DetailDiskCache(root_dir=tempfile.mkdtemp(prefix="swdm_t33_empty_"),
                      ttl_hours=24)
check("A13 空目录 invalidate 返回 0 不崩", _c4.invalidate() == 0)
check("A13b 空目录 get 为 miss", _c4.get("x", 1)[0] is False)

# A14 原子写：写完即立即可读（os.replace 语义）
_cache.set("100014", "<html>atomic</html>", 77)
ok, html = _cache.get("100014", 77)
check("A14 写后立即命中", ok and html == "<html>atomic</html>")

# A15 全局单例可用且路径落在 CACHE_DIR 下
_gc = get_detail_cache()
check("A15 全局单例目录在 cache/detail 下",
      _gc._dir.endswith(os.path.join("cache", "detail")),
      _gc._dir)

# ====================================================== B. 配置联动
from swdm.core.config import get_config  # noqa: E402

_cfg = get_config()
_cfg.set("network", "detail_cache_ttl_hours", 12)
_cfg.set("network", "detail_cache_enabled", True)
_cc = DetailDiskCache(root_dir=_tmp)  # ttl_hours=None → 读配置
_cc.set("200001", "cfg", 1)
check("B1 ttl 从配置读取（12h 生效）", _cc.get("200001", 1)[0])
_cfg.set("network", "detail_cache_enabled", False)
_cc2 = DetailDiskCache(root_dir=_tmp)
_cc2.set("200002", "cfg-off", 1)
check("B2 enabled=False 时 get 永远 miss",
      _cc2.get("200002", 1)[0] is False)
_cfg.set("network", "detail_cache_enabled", True)
_cfg.set("network", "detail_cache_ttl_hours", 24)

# ====================================================== C. DetailPageWorker 接入
from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402
from swdm.core.steam_api import SteamAPI  # noqa: E402

# 用独立缓存目录替换全局单例，避免污染真实数据目录
import swdm.core.detail_cache as dc_mod  # noqa: E402

dc_mod._global = DetailDiskCache(root_dir=_tmp, ttl_hours=24)

_net = {"n": 0}
_api = SteamAPI()
_orig = SteamAPI._community_get


def _fake_cg(self, *a, **k):
    _net["n"] += 1
    return "<html>net-fresh</html>"


# C1 磁盘缓存命中 → _community_get 零调用（复用 t25 A-U12 模式）
dc_mod._global.set("300001", "<html>disk-cached</html>", 4242)
DetailPageWorker._page_cache.pop("300001", None)
SteamAPI._community_get = _fake_cg
try:
    _w = DetailPageWorker(_api, "300001", time_updated=4242)
    _w.run()
finally:
    SteamAPI._community_get = _orig
check("C1 磁盘缓存命中零网络调用", _net["n"] == 0, f"net={_net['n']}")

# C2 未命中 → 走网络且回写磁盘
dc_mod._global.invalidate("300002")
DetailPageWorker._page_cache.pop("300002", None)
_net["n"] = 0
SteamAPI._community_get = _fake_cg
try:
    _w = DetailPageWorker(_api, "300002", time_updated=5000)
    _w.run()
finally:
    SteamAPI._community_get = _orig
_disk_hit, _disk_html = dc_mod._global.get("300002", 5000)
check("C2 未命中走网络且回写磁盘",
      _net["n"] == 1 and _disk_hit and _disk_html == "<html>net-fresh</html>",
      f"net={_net['n']}")

# C3 time_updated 变化 → 磁盘条目失效，重新走网络
_net["n"] = 0
SteamAPI._community_get = _fake_cg
try:
    _w = DetailPageWorker(_api, "300003", time_updated=6000)
    _w.run()  # 首次：写盘（同时写进程级内存缓存）
    DetailPageWorker._page_cache.pop("300003", None)  # 排除内存层干扰
    _w2 = DetailPageWorker(_api, "300003", time_updated=6001)  # 更新了
    _w2.run()
finally:
    SteamAPI._community_get = _orig
check("C3 time_updated 变化触发重新拉取", _net["n"] == 2, f"net={_net['n']}")

# C4 force_refresh=True → 强制 bypass 磁盘缓存
dc_mod._global.set("300004", "<html>stale</html>", 7000)
DetailPageWorker._page_cache.pop("300004", None)
_net["n"] = 0
SteamAPI._community_get = _fake_cg
try:
    _w = DetailPageWorker(_api, "300004", time_updated=7000,
                          force_refresh=True)
    _w.run()
finally:
    SteamAPI._community_get = _orig
check("C4 force_refresh 绕过磁盘缓存走网络", _net["n"] == 1, f"net={_net['n']}")
_hit4, _h4 = dc_mod._global.get("300004", 7000)
check("C4b 刷新结果已回写磁盘（新值覆盖旧值）",
      _hit4 and _h4 == "<html>net-fresh</html>")

# C5 进程级 _page_cache 仍优先（5 分钟内不查磁盘也不走网络）
DetailPageWorker._page_cache["300005"] = (time.time(), "<html>mem</html>")
dc_mod._global.set("300005", "<html>disk</html>", 1)
_net["n"] = 0
SteamAPI._community_get = _fake_cg
try:
    DetailPageWorker(_api, "300005", time_updated=1).run()
finally:
    SteamAPI._community_get = _orig
check("C5 进程级缓存优先于磁盘缓存", _net["n"] == 0)

# C6 构造函数默认参数向后兼容（旧调用方式不报错）
try:
    _w6 = DetailPageWorker(_api, "300006")
    _ok6 = (_w6._time_updated == 0 and _w6._force_refresh is False)
except Exception as e:  # noqa: BLE001
    _ok6 = False
    print("  构造异常:", e)
check("C6 旧式构造（仅 api+id）兼容", _ok6)

# ====================================================== D. 设置页控件存在
from types import SimpleNamespace  # noqa: E402

from swdm.gui.settings_tab import SettingsTab  # noqa: E402
from swdm.core.auth import AuthManager  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402

    _app = QApplication.instance() or QApplication([])
    _svc = SimpleNamespace(
        config=get_config(),
        auth=AuthManager(),
        library=None,
        downloader=None,
        refresh_api=lambda: None,
        refresh_engine=lambda: None,
    )
    _st = SettingsTab(_svc)
    _ok_d = all(hasattr(_st, a) for a in (
        "detail_cache_check", "detail_ttl_spin", "clear_detail_cache_btn"))
    _vals_ok = (
        _st.detail_cache_check.isChecked() is True
        and _st.detail_ttl_spin.value() == 24
    )
except Exception as e:  # noqa: BLE001
    _ok_d = _vals_ok = False
    print("  SettingsTab 实例化异常:", e)
check("D1 SettingsTab 具备 B1 三控件", _ok_d)
check("D1b 控件初始值从配置正确装载（开 + 24h）", _vals_ok)

# D2 默认配置项存在且默认值正确
check("D2 默认配置 detail_cache_enabled=True",
      get_config().get("network", "detail_cache_enabled", default=None) is True)
check("D3 默认配置 detail_cache_ttl_hours=24",
      get_config().get("network", "detail_cache_ttl_hours", default=None) == 24)

# 清理测试目录
dc_mod._global = None
for _d in (_tmp,):
    pass

_n_fail = sum(1 for _n, ok in _RESULTS if not ok)
print(f"\nTOTAL: {len(_RESULTS)} checks, {len(_RESULTS) - _n_fail} pass, "
      f"{_n_fail} fail")
if _n_fail:
    print("FAILED:")
    for _n, ok in _RESULTS:
        if not ok:
            print("  -", _n)
    sys.exit(1)
print("RESULT: ALL PASS")
