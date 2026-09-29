"""deps_parser 单元测试：覆盖真实页面结构 + 边界情况。
真实结构（已用真实页面验证）：
  <div class="requiredItemsContainer" id="RequiredItems">
    <a href=".../workshop/filedetails/?id=X" target="_blank" data-subscribed="0">
      <div class="requiredItem"> 名称 </div>
    </a>
  </div>
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.deps_parser import (  # noqa: E402
    parse_required_items,
    parse_required_items_robust,
    parse_required_items_with_titles,
)

out_lines: list[str] = []
def p(*a):
    out_lines.append(" ".join(str(x) for x in a))

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


# --- 真实结构（单个依赖）---
HTML_ONE = (
    '<div class="requiredItemsContainer" id="RequiredItems">\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=1111111111"\n'
    '     target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> The Ability To Read </div>\n'
    '  </a>\n'
    '</div>\n'
)
check("单个依赖解析", parse_required_items(HTML_ONE) == ["1111111111"],
      str(parse_required_items(HTML_ONE)))

# --- 真实结构（两个依赖，带标题）---
HTML_TWO = (
    '<div class="requiredItemsContainer" id="RequiredItems">\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=131759821" target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> VJ Base </div></a>\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=2161380206" target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> [F76] SheepSquatch </div></a>\n'
    '</div>\n'
)
items = parse_required_items_with_titles(HTML_TWO)
check("两个依赖带标题", items == [("131759821", "VJ Base"), ("2161380206", "[F76] SheepSquatch")],
      str(items))

# --- 实体还原（&amp;）---
HTML_ENT = (
    '<div class="requiredItemsContainer" id="RequiredItems">\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=2222" target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> Guns &amp; Ammo </div></a>\n'
    '</div>\n'
)
check("实体还原", parse_required_items_with_titles(HTML_ENT)[0][1] == "Guns & Ammo",
      str(parse_required_items_with_titles(HTML_ENT)))

# --- 无依赖页面 ---
HTML_NONE = '<div class="panel"><div class="rightSectionTopTitle">Created by</div></div>'
check("无依赖返回空", parse_required_items(HTML_NONE) == [])
check("空 HTML 返回空", parse_required_items("") == [])

# --- 重复依赖去重 ---
HTML_DUP = (
    '<div class="requiredItemsContainer" id="RequiredItems">\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=3333" target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> A </div></a>\n'
    '  <a href="https://steamcommunity.com/workshop/filedetails/?id=3333" target="_blank" data-subscribed="0">\n'
    '    <div class="requiredItem"> A </div></a>\n'
    '</div>\n'
)
check("重复去重", parse_required_items(HTML_DUP) == ["3333"])

# --- robust 兜底：容器定位失败但有 requiredItem 链接 ---
HTML_ROBUST = (
    '<a href="https://steamcommunity.com/workshop/filedetails/?id=4444" target="_blank" data-subscribed="0">\n'
    '  <div class="requiredItem"> D </div></a>\n'
)
check("精确失败时兜底生效",
      parse_required_items(HTML_ROBUST) == [] and parse_required_items_robust(HTML_ROBUST) == ["4444"])

# --- robust 对无依赖页面不误抓 ---
check("robust 无依赖返回空", parse_required_items_robust(HTML_NONE) == [])

# --- 真实保存页面回归 ---
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
if os.path.isdir(FIX):
    for fn in sorted(os.listdir(FIX)):
        if fn.startswith("deps_") and fn.endswith(".html"):
            html = open(os.path.join(FIX, fn), encoding="utf-8").read()
            ids = parse_required_items(html)
            check(f"真实页面 {fn} 解析非空", len(ids) >= 1, str(ids))

result = "\n".join(out_lines)
print(result)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_deps_unit.txt"),
          "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
