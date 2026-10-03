"""搜索无关结果修复测试（S1 标题命中率/提示 / S2 0 命中作者过滤回退）。

根因：Steam 浏览页搜索只匹配标题，不匹配作者——搜作者名返回的
30 个结果里几乎全是标题模糊匹配的无关 mod。修复在客户端做二次处理：
高命中率原样展示，低命中率提示，0 命中回退按作者过滤。
脚本式：check() + sys.exit，不依赖网络。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_search_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

RESULTS = []


def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))


from swdm.core.steam_api import SteamAPI, WorkshopItem  # noqa: E402

LOW_HINT = SteamAPI.SEARCH_LOW_HIT_HINT


def _mk(pid, title, creator_name="", creator=""):
    return WorkshopItem(
        publishedfileid=pid,
        title=title,
        creator_name=creator_name,
        creator=creator,
        appid="4000",
    )


# ---- S1：标题命中率高时不提示、不过滤
high = [
    _mk(str(i), f"admin tool {i}", creator_name="someone")
    for i in range(8)
] + [
    _mk(str(100 + i), f"other mod {i}", creator_name="someone")
    for i in range(2)
]
out, hint = SteamAPI.apply_browse_search_fallback(high, "admin", api_key_mode=False)
check("S1 高命中率不提示", hint == "", repr(hint))
check("S1 高命中率不过滤", len(out) == len(high), f"{len(out)}/{len(high)}")
check("S1 命中率计算正确",
      abs(SteamAPI.title_hit_rate(high, "admin") - 0.8) < 1e-9,
      repr(SteamAPI.title_hit_rate(high, "admin")))

# ---- S2：0 命中时触发作者过滤（模拟搜作者名 "Robotboy655"）
mixed = [
    _mk("1", "Robotboy's Ragdoll", creator_name="Robotboy655"),
    _mk("2", "普通 mod 一号", creator_name="Robotboy655"),
    _mk("3", "普通 mod 二号", creator_name="Robotboy655"),
    _mk("4", "无关 mod A", creator_name="OtherGuy"),
    _mk("5", "无关 mod B", creator_name="OtherGuy2"),
]
out, hint = SteamAPI.apply_browse_search_fallback(mixed, "Robotboy655",
                                                  api_key_mode=False)
check("S2 0 命中触发作者过滤", len(out) == 3, f"{len(out)}")
check("S2 过滤结果都是该作者",
      all("Robotboy655".lower() in (i.creator_name or "").lower() for i in out))
check("S2 作者过滤给提示", hint != "", repr(hint))
check("S2 提示含按作者过滤说明", "作者" in hint, repr(hint))
check("S2 原列表不被污染（深拷贝语义由调用方负责，此处验证过滤不就地改）",
      len(mixed) == 5, f"{len(mixed)}")

# 作者字段命中 creator（steamid64）也算
mixed2 = [_mk("1", "完全无关的标题", creator="76561197999999999")]
out2, hint2 = SteamAPI.apply_browse_search_fallback(mixed2, "76561197999999999",
                                                    api_key_mode=False)
check("S2b 按 creator steamid 过滤", len(out2) == 1 and hint2 != "",
      f"{len(out2)}/{hint2!r}")

# 0 标题命中、作者也 0 命中：返回空列表 + 明确空态（t9 议题 B）
none_hit = [_mk("1", "乱七八糟的标题", creator_name="nobody"),
            _mk("2", "另一个标题", creator_name="nobody2")]
out, hint = SteamAPI.apply_browse_search_fallback(none_hit, "zzzqqqnomatchxyz",
                                                  api_key_mode=False)
check("S2c 双 0 命中返回空列表", out == [], f"{out!r}")
check("S2c 空态提示明确", hint == "没找到标题或作者含「zzzqqqnomatchxyz」的 mod",
      repr(hint))
check("S2c 空态不含限流误导", "限流" not in hint, repr(hint))

# ---- S3：提示文字正确（低命中率非 0：1/10 命中）
low = [_mk("1", "adminpanel 的工具", creator_name="x")] + [
    _mk(str(10 + i), f"管理员工具 {i}", creator_name="y") for i in range(9)
]
out, hint = SteamAPI.apply_browse_search_fallback(low, "adminpanel",
                                                  api_key_mode=False)
check("S3 低命中率原样展示", len(out) == len(low), f"{len(out)}/{len(low)}")
check("S3 低命中率展示固定提示", hint == LOW_HINT, repr(hint))
check("S3 提示内容含关键说明",
      LOW_HINT == "Steam 搜索只匹配标题；想精确搜索作者，可在设置页填写 Steam API Key",
      repr(LOW_HINT))

# ---- S4：边界行为
out, hint = SteamAPI.apply_browse_search_fallback(low, "", api_key_mode=False)
check("S4 空搜索词不处理", hint == "" and len(out) == len(low))
out, hint = SteamAPI.apply_browse_search_fallback([], "adminpanel",
                                                  api_key_mode=False)
check("S4 空结果不处理", hint == "" and out == [])
out, hint = SteamAPI.apply_browse_search_fallback(low, "adminpanel",
                                                  api_key_mode=True)
check("S4 API key 模式跳过二次处理",
      hint == "" and len(out) == len(low), repr(hint))
check("S4 title_hit_rate 空输入为 0",
      SteamAPI.title_hit_rate([], "x") == 0.0
      and SteamAPI.title_hit_rate(low, "") == 0.0)

# ---- S5：GUI 集成——_on_items_ready 按代际搜索词做二次处理并写状态栏
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab

gui_items = [_mk("1", "无关标题一号", creator_name="Robotboy655"),
             _mk("2", "无关标题二号", creator_name="Robotboy655"),
             _mk("3", "无关标题三号", creator_name="OtherGuy")]
gen = wt._worker_gen + 1
wt._worker_gen = gen
wt._search_by_gen[gen] = "robotboy655"      # 大小写不敏感
wt._on_items_ready(list(gui_items), gen)
app.processEvents()
status = wt.status_label.text()
check("S5 GUI 0 命中按作者过滤", len(wt._cards()) == 2,
      f"{len(wt._cards())}")
check("S5 状态栏含提示", "作者" in status, repr(status))

# 过期代际被丢弃
wt._worker_gen = gen + 1
wt._on_items_ready(gui_items, gen)
check("S5 过期代际结果被丢弃", len(wt._cards()) == 2, "旧结果不应覆盖")

# 无搜索词（普通浏览）不触发任何提示
gen2 = wt._worker_gen + 1
wt._worker_gen = gen2
wt._search_by_gen.pop(gen2, None)
wt._on_items_ready(gui_items, gen2)
app.processEvents()
check("S5 普通浏览无作者过滤提示", "作者" not in wt.status_label.text(),
      repr(wt.status_label.text()))

# 双 0 命中：空列表 + 状态栏明确空态（t9 议题 B）
gen3 = wt._worker_gen + 1
wt._worker_gen = gen3
wt._search_by_gen[gen3] = "zzzqqqnomatchxyz"
wt._on_items_ready(list(gui_items), gen3)
app.processEvents()
check("S5 双 0 命中清空列表", len(wt._cards()) == 0, f"{len(wt._cards())}")
check("S5 空态状态栏明确", "没找到" in wt.status_label.text(),
      repr(wt.status_label.text()))
check("S5 空态不含限流误导", "限流" not in wt.status_label.text(),
      repr(wt.status_label.text()))

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name
          + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
