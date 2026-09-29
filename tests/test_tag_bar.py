"""标签栏组件测试（bug2：横向滚动、单击多选、已选高亮带叉、去重、去无关标签）。"""
from __future__ import annotations

import io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_tag_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from swdm.gui.tag_bar import TagBar, filter_nav_tags  # noqa: E402

out = io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    p(("OK   " if cond else "FAIL ") + name + (f"  [{e}]" if e else ""))


# ---- filter_nav_tags：去无关导航标签 + 语言名 + 去重保序
mixed = ["Map", "商店", "创意工坊", "Addon", "Map", "Weapon",
         "日本語（日语）", "市场", "Skin", "登录"]
kept = filter_nav_tags(mixed)
check("过滤无关导航标签", kept == ["Map", "Addon", "Weapon", "Skin"], str(kept))
check("去重保序", kept.count("Map") == 1)

# ---- TagBar 行为
bar = TagBar()
bar.resize(600, 100)
bar.show()
app.processEvents()

bar.set_tags([("Map", 1234), ("Addon", 0), ("Weapon", 56), ("商店", 9)])
app.processEvents()
check("标签数 3（过滤后）", len(bar._chips) == 3, str(list(bar._chips)))
check("计数显示在 chip 文本", "(1,234)" in bar._chips["Map"].text(),
      bar._chips["Map"].text())
check("0 计数不显示括号", "(" not in bar._chips["Addon"].text(),
      bar._chips["Addon"].text())
check("栏启用", bar.isEnabled())
check("表头计数", "3" in bar._header.text(), bar._header.text())

# 单击选中（多选）
bar._chips["Map"].setChecked(True)
app.processEvents()
check("选中后 selected 含该标签", bar.selected() == ["Map"], str(bar.selected()))
check("选中触发 selection_changed 信号（外部已连接，直接验证集合）",
      bar._selected == ["Map"])
check("已选行显示带叉 chip", bar._sel_host.isVisible())

bar._chips["Weapon"].setChecked(True)
app.processEvents()
check("多选累积", bar.selected() == ["Map", "Weapon"], str(bar.selected()))

# 重复添加保护：直接 set_selected 同名不重复
bar.set_selected(["Map", "Map", "Addon"])
check("set_selected 去重", bar.selected() == ["Map", "Addon"], str(bar.selected()))
check("chip 状态同步", bar._chips["Weapon"].isChecked() is False)

# 点已选行的叉删除
bar._remove_tag("Map")
app.processEvents()
check("点叉删除标签", bar.selected() == ["Addon"], str(bar.selected()))
check("删除后对应 chip 取消勾选", bar._chips["Map"].isChecked() is False)

# clear_selection
bar.clear_selection()
check("清空选择", bar.selected() == [])
check("清空后已选行隐藏", not bar._sel_host.isVisible())

# 切换游戏后保留选中并恢复 chip 状态
bar.set_selected(["Addon"])
bar.set_tags([("Addon", 5), ("Skin", 3)])
app.processEvents()
check("重填标签后保留选中", bar.selected() == ["Addon"])
check("重填后 chip 恢复勾选", bar._chips["Addon"].isChecked() is True)

# loading 态
bar.set_loading(True)
check("loading 态表头", "拉取中" in bar._header.text())
bar.set_loading(False)

# 空标签列表
bar.set_tags([])
check("空列表时禁用", not bar.isEnabled())

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
