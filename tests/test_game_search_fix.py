"""搜索体验修复测试（u2 / t12）：

U1 游戏输入识别：_on_game_enter 精确匹配失败时的回退链
   （联想最佳匹配 / 本地匹配 / 结果到达自动选第一项 / 纯数字 AppID）
U2 联想下拉：currentIndex 与 lineEdit 文本一致、候选按匹配度排序、
   本地/网络结果都弹下拉
U3 搜索回车快捷键：returnPressed 已连接且 _refresh_list 实际被触发
U4 标签精确过滤：服务端 requiredtags 近似匹配 → 客户端交集过滤 + 提示

脚本式：check() + sys.exit，零网络依赖。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_gamesearch_")
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
from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()
wt = win.workshop_tab

# 回车选游戏会触发 _on_game_changed → 标签拉取 + 列表刷新（实网），
# 测试中桩掉两者，只验证选择/解析逻辑本身
wt._fetch_tags = lambda: None


def _enter(text: str) -> None:
    """输入游戏名并回车，随后停掉实网刷新定时器。"""
    ed = wt.game_combo.lineEdit()
    ed.setText(text)
    app.processEvents()
    wt._on_game_enter()
    app.processEvents()
    wt._refresh_timer.stop()


def _set_game_text(t: str) -> None:
    ed = wt.game_combo.lineEdit()
    ed.setText(t)
    app.processEvents()


def _mk_item(pid, title, tags=None):
    return WorkshopItem(
        publishedfileid=pid, title=title,
        creator_name="robotboy", creator="76561197999999999",
        tags=list(tags or []),
    )


# =====================================================================
# U1 游戏输入识别
# =====================================================================

def _set_game_text(t: str) -> None:
    ed = wt.game_combo.lineEdit()
    ed.setText(t)
    app.processEvents()


# U1a 纯数字 AppID 直接识别
_enter("440")  # TF2
check("U1a 纯数字 AppID 识别", wt._current_appid() == "440",
      repr(wt._current_appid()))

# U1b 联想结果模糊匹配（精确失败、开头命中）
wt._last_search_pairs = [("4000", "Garry's Mod"), ("105600", "Terraria")]
_enter("garry")
check("U1b 联想结果模糊匹配选中", wt.game_combo.currentData() == "4000",
      repr(wt.game_combo.currentData()))

# U1c 联想结果包含匹配（非开头）
wt._last_search_pairs = [("108600", "Project Zomboid")]
_enter("zomboid")
check("U1c 联想结果包含匹配选中", wt.game_combo.currentData() == "108600",
      repr(wt.game_combo.currentData()))

# U1d 联想未到 + 本地无匹配 → 触发搜索并标记待选
wt._last_search_pairs = []
wt._pending_enter_select = False
search_calls = []
wt._do_game_search = lambda: search_calls.append(True)  # 桩：不发网络
_set_game_text("zzzqqqunrealgame")
wt._on_game_enter()
app.processEvents()
wt._refresh_timer.stop()
check("U1d 无匹配时触发一次搜索", len(search_calls) == 1, f"{len(search_calls)}")
check("U1d 置待选标记", wt._pending_enter_select is True,
      repr(wt._pending_enter_select))
check("U1d 状态栏提示搜索中", "搜索" in wt.status_label.text(),
      repr(wt.status_label.text()))


# U1e 待选状态：结果到达自动选中第一项（最佳匹配）
class _FakeResult:
    def __init__(self, appid, name):
        self.appid, self.name = appid, name


wt._do_game_search = lambda: None  # 恢复（仍桩掉网络）
wt._search_version += 1
v = wt._search_version
wt._pending_enter_select = True
_set_game_text("zzzqqqunrealgame")
wt._on_search_ready(
    [_FakeResult("123456", "zzzqqqunrealgame mod hub"),
     _FakeResult("654321", "other game")],
    v,
)
app.processEvents()
wt._refresh_timer.stop()
check("U1e 结果到达自动选中第一项", wt.game_combo.currentData() == "123456",
      repr(wt.game_combo.currentData()))
check("U1e 待选标记已清除", wt._pending_enter_select is False,
      repr(wt._pending_enter_select))

# U1f 待选状态但无结果 → 明确提示
wt._search_version += 1
v = wt._search_version
wt._pending_enter_select = True
wt._on_search_ready([], v)
app.processEvents()
check("U1f 无结果给明确提示", "未找到该游戏" in wt.status_label.text(),
      repr(wt.status_label.text()))

# U1g 本地匹配命中直接选（不等网络）
wt._last_search_pairs = []
_enter("garry")  # 内置表含 Garry's Mod
check("U1g 本地匹配直接选中", wt.game_combo.currentData() == "4000",
      repr(wt.game_combo.currentData()))


# =====================================================================
# U2 联想下拉一致性
# =====================================================================

# U2a 填充候选后 currentIndex 为 -1，lineEdit 文本不被破坏
_set_game_text("terraria")
wt._fill_search_results([("105600", "Terraria"), ("4000", "Garry's Mod")])
app.processEvents()
check("U2a 填充后无选中项（currentIndex=-1）",
      wt.game_combo.currentIndex() == -1, repr(wt.game_combo.currentIndex()))
check("U2a lineEdit 文本保留", wt.game_combo.lineEdit().text() == "terraria",
      repr(wt.game_combo.lineEdit().text()))
check("U2a 候选项数正确", wt.game_combo.count() == 2,
      repr(wt.game_combo.count()))

# U2b 排序：精确匹配第一
wt._last_search_pairs = [("105600", "Terraria")]
wt._search_version += 1
v = wt._search_version
_set_game_text("terraria")
wt._on_search_ready([_FakeResult("105600", "Terraria")], v)
app.processEvents()
check("U2b 精确匹配排第一",
      wt.game_combo.itemText(0).startswith("Terraria"),
      repr(wt.game_combo.itemText(0)))

# U2c 排序：本地精确匹配优先于网络的包含/开头匹配
wt._last_search_pairs = [("999999", "Garry-like other game")]
wt._search_version += 1
v = wt._search_version
_set_game_text("garry")
wt._on_search_ready([_FakeResult("999999", "Garry-like other game")], v)
app.processEvents()
first = wt.game_combo.itemText(0)
check("U2c 本地精确匹配仍排第一", first.startswith("Garry's Mod  (4000)"),
      repr(first))

# U2d 无本地匹配时关闭残留下拉（不报错即通过）
_set_game_text("zzzqqqnomatchxyz")
wt._on_search_text_edited("zzzqqqnomatchxyz")
app.processEvents()
check("U2d 无匹配文本编辑不崩",
      wt.game_combo.lineEdit().text() == "zzzqqqnomatchxyz",
      repr(wt.game_combo.lineEdit().text()))

# U2e 匹配度评分函数
check("U2e 精确匹配 3 分", wt._match_score("Terraria", "terraria") == 3)
check("U2e 开头匹配 2 分", wt._match_score("Terraria 2", "terraria") == 2)
check("U2e 包含匹配 1 分", wt._match_score("play Terraria now", "terraria") == 1)
check("U2e 不匹配 0 分", wt._match_score("Garry's Mod", "terraria") == 0)


# =====================================================================
# U3 搜索回车快捷键
# =====================================================================

check("U3 placeholder 含回车提示",
      "回车" in wt.search_edit.placeholderText(),
      repr(wt.search_edit.placeholderText()))

# returnPressed 已连接：emit 后 _refresh_list 的去抖定时器应启动
wt._refresh_timer.stop()
wt.search_edit.setText("test")
wt.search_edit.returnPressed.emit()
app.processEvents()
check("U3 回车触发 _refresh_list（去抖定时器启动）",
      wt._refresh_timer.isActive(), "定时器未启动")

# tag_edit 与 tag_bar 选中同步（u3 联动前提）
wt._on_tag_selection_changed(["生存", "建筑"])
check("U3 标签栏选择同步到 tag_edit",
      wt.tag_edit.text() == "生存,建筑", repr(wt.tag_edit.text()))


# =====================================================================
# U4 标签精确过滤（纯函数 + GUI 集成）
# =====================================================================

items = [
    _mk_item("1", "生存小屋", tags=["生存", "建筑"]),
    _mk_item("2", "建筑大师", tags=["建筑"]),
    _mk_item("3", "无关 mod", tags=["载具"]),
    _mk_item("4", "无标签 mod", tags=[]),
]

# U4a 单标签过滤
out, dropped, unver = SteamAPI.filter_items_by_tags(list(items), ["生存"])
check("U4a 单标签只留含该标签的物品",
      [i.publishedfileid for i in out] == ["1"], f"{[i.publishedfileid for i in out]}")
check("U4a dropped 计数正确", dropped == 3, f"{dropped}")
check("U4a 可验证（非近似）", unver is False, repr(unver))

# U4b 多标签交集（必须同时包含）
out, dropped, unver = SteamAPI.filter_items_by_tags(list(items), ["生存", "建筑"])
check("U4b 多标签交集过滤",
      [i.publishedfileid for i in out] == ["1"], f"{[i.publishedfileid for i in out]}")

# U4c 大小写/空白不敏感
out, dropped, unver = SteamAPI.filter_items_by_tags(list(items), [" 建築 ".replace("建築", "建筑")])
check("U4c 标签去空白后匹配",
      [i.publishedfileid for i in out] == ["1", "2"],
      f"{[i.publishedfileid for i in out]}")

# U4d 空标签选择不过滤
out, dropped, unver = SteamAPI.filter_items_by_tags(list(items), [])
check("U4d 空标签不过滤", len(out) == 4 and dropped == 0, f"{len(out)}/{dropped}")

# U4e 多数物品无标签 → 不可验证，原样返回
no_tag = [_mk_item(str(i), f"mod {i}", tags=[]) for i in range(5)] + \
         [_mk_item("9", "有标签", tags=["生存"])]
out, dropped, unver = SteamAPI.filter_items_by_tags(list(no_tag), ["生存"])
check("U4e 标签数据缺失时不过滤", len(out) == 6, f"{len(out)}")
check("U4e 标记为不可验证", unver is True, repr(unver))

# U4f 空结果集
out, dropped, unver = SteamAPI.filter_items_by_tags([], ["生存"])
check("U4f 空结果集安全", out == [] and dropped == 0, f"{len(out)}/{dropped}")

# ---- GUI 集成：_on_items_ready 按代际标签过滤 + 状态栏提示 ----
gen = wt._worker_gen + 1
wt._worker_gen = gen
wt._tags_by_gen[gen] = ["生存"]
wt._search_by_gen.pop(gen, None)
gui_items = [
    _mk_item("1", "生存小屋", tags=["生存", "建筑"]),
    _mk_item("2", "建筑大师", tags=["建筑"]),
    _mk_item("3", "混进来的无关 mod", tags=["载具"]),
]
wt._on_items_ready(list(gui_items), gen)
app.processEvents()
ids = [c.item.publishedfileid for c in wt._cards()]
check("U4g GUI 过滤掉不含所选标签的卡片",
      ids == ["1"], f"{ids}")
check("U4g 状态栏含过滤提示", "过滤掉" in wt.status_label.text(),
      repr(wt.status_label.text()))

# U4h 全被过滤 → 明确空态
gen2 = wt._worker_gen + 1
wt._worker_gen = gen2
wt._tags_by_gen[gen2] = ["不存在的标签"]
wt._search_by_gen.pop(gen2, None)
wt._on_items_ready(list(gui_items), gen2)
app.processEvents()
check("U4h 全过滤掉时空态提示",
      "没有同时包含所选标签的物品" in wt.status_label.text(),
      repr(wt.status_label.text()))

# U4i 标签数据缺失 → 近似匹配提示，不过滤
gen3 = wt._worker_gen + 1
wt._worker_gen = gen3
wt._tags_by_gen[gen3] = ["生存"]
wt._search_by_gen.pop(gen3, None)
no_tag_items = [_mk_item(str(i), f"mod {i}", tags=[]) for i in range(5)]
wt._on_items_ready(list(no_tag_items), gen3)
app.processEvents()
check("U4i 标签缺失时不过滤", len(wt._cards()) == 5, f"{len(wt._cards())}")
check("U4i 状态栏提示近似匹配",
      "服务端近似匹配" in wt.status_label.text(),
      repr(wt.status_label.text()))

# U4j 无标签请求时不过滤（普通浏览）
gen4 = wt._worker_gen + 1
wt._worker_gen = gen4
wt._tags_by_gen.pop(gen4, None)
wt._search_by_gen.pop(gen4, None)
wt._on_items_ready(list(gui_items), gen4)
app.processEvents()
check("U4j 无标签请求不过滤", len(wt._cards()) == 3, f"{len(wt._cards())}")

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name
          + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
