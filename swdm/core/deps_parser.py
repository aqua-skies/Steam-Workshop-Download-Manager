"""工坊物品依赖（前置 mod）解析。

Steam 工坊详情页（/sharedfiles/filedetails/?id=X）右侧栏展示
"Required items"（前置依赖）区块。本模块从 HTML 抓取该依赖列表。

真实页面结构（经真实页面验证）：

  <div class="requiredItemsContainer" id="RequiredItems">
      <a href="https://steamcommunity.com/workshop/filedetails/?id=<dep_id>"
         target="_blank" data-subscribed="0">
          <div class="requiredItem"> 依赖名称 </div>
      </a>
      ...
  </div>

说明：
- Steam Web API 的 referenced_files 字段对匿名访问恒为空（实测采样为证），
  依赖关系只能从网页抓取。
- 依赖链接使用 /workshop/filedetails/?id= 路径（与 sharedfiles/ 不同）。
- 依赖标题是 requiredItem 容器内的纯文本（无图片）。
"""

from __future__ import annotations

import re

from .logger import get_logger

log = get_logger("swdm.deps")

# 依赖容器锚点（id="RequiredItems" 精确定位）
_REQUIRED_ANCHOR_RE = re.compile(
    r'<div[^>]*id="RequiredItems"[^>]*>',
)
# 容器内的依赖链接（workshop/filedetails 路径）
_DEP_LINK_RE = re.compile(
    r'workshop/filedetails/\?id=(\d+)"[^>]*>\s*<div[^>]*class="[^"]*requiredItem[^"]*"[^>]*>\s*(.*?)\s*</div>',
    re.DOTALL,
)
# 兜底：页面内任意 requiredItem 容器中的链接
_ANY_DEP_LINK_RE = re.compile(
    r'(?:workshop|sharedfiles)/filedetails/\?id=(\d+)"[^>]*>\s*<div[^>]*class="[^"]*requiredItem[^"]*"[^>]*>\s*(.*?)\s*</div>',
    re.DOTALL,
)


def _slice_required_section(html: str) -> str:
    """从 id="RequiredItems" 锚点截取容器内容（div 配对）。"""
    m = _REQUIRED_ANCHOR_RE.search(html)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(html) and depth > 0:
        next_open = html.find("<div", i)
        next_close = html.find("</div>", i)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            i = next_open + 4
        else:
            depth -= 1
            i = next_close + 6
    return html[start:i]


def _extract(html_slice: str) -> list[tuple[str, str]]:
    """从 HTML 片段提取 [(dep_id, dep_title), ...]，有序去重。"""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pid, title in _DEP_LINK_RE.findall(html_slice):
        if pid not in seen:
            seen.add(pid)
            # 标题里的 HTML 实体简单还原
            title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            out.append((pid, title.strip()))
    return out


def parse_required_items(html: str) -> list[str]:
    """从工坊详情页 HTML 解析前置依赖物品 id 列表（有序、去重）。"""
    return [pid for pid, _ in parse_required_items_with_titles(html)]


def parse_required_items_with_titles(html: str) -> list[tuple[str, str]]:
    """解析前置依赖，返回 [(id, 标题)]。只在 RequiredItems 区块内精确匹配。"""
    if not html:
        return []
    section = _slice_required_section(html)
    if not section:
        return []
    items = _extract(section)
    if items:
        log.debug("解析到 %d 个前置依赖: %s", len(items), [i[0] for i in items[:8]])
    return items


def parse_required_items_robust(html: str) -> list[str]:
    """兜底解析：精确区块定位失败时，在页面范围内抓 requiredItem 链接。"""
    items = parse_required_items_with_titles(html)
    if items:
        return [pid for pid, _ in items]
    if not html or "requiredItem" not in html:
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for pid, _t in _ANY_DEP_LINK_RE.findall(html):
        if pid not in seen:
            seen.add(pid)
            ids.append(pid)
    return ids
