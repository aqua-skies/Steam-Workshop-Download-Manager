"""Steam 工坊页面解析：描述正文 / 评论 / 浏览页可用标签。

设计要点（与 deps_parser.py 同风格：纯函数 + 明确锚点 + 兜底）：
- parse_description / parse_comments / parse_available_tags 均为纯函数，
  无网络、无副作用，可直接用 tests/fixtures 下的真实页面做回归。
- fetch_comments 接收外部传入的 SteamAPI 实例（依赖注入，便于测试与限流复用）。
- 文本清洗统一走 _to_text()：块级标签闭合转换行、去标签、还原 HTML 实体。

真实页面锚点（均经 tests/fixtures 真实页面验证）：

1) 描述正文（详情页右侧栏）
   <div class="workshopItemDescriptionTitle">Description</div>
   <div class="workshopItemDescription" id="highlightContent">
       ...含 bb_h1/bb_h3/<br>/<b>/<a> 等 BBCode 富文本...
   </div>
   描述区内含嵌套 <div>（bb_h1/bb_h3），需按 div 配对截取，不能贪心到首个 </div>。

2) 评论（详情页 SSR 已渲染前 N 条，非纯 ajax）
   <div ... class="commentthread_comment responsive_body_text   "
        id="comment_<cid>" style="">
       <div class="commentthread_comment_content">
           <div class="commentthread_comment_author">
               <div class="commentthread_comment_avatar playerAvatar ...">...</div>
               <div class="author_name_group">
                   <div class="flex_row">
                       <a class="hoverunderline commentthread_author_link" href="...">
                           <bdi>作者名</bdi></a>
                       <span class="commentthread_workshop_authorbadge">
                           &nbsp;[author]</span>   <!-- 可选，作者本人徽章 -->
                   </div>
                   <div class="commentthread_comment_timestamp"></div>      <!-- 空 -->
                   <div class="commentthread_comment_timestamp"
                        title="21 September, 2026 @ 12:38:34 am PDT"
                        data-timestamp="1789976314">3 hours ago&nbsp;</div>
               </div>
               <div class="commentthread_comment_actions"></div>
           </div>
           <div class="commentthread_comment_text" id="comment_content_<cid>">
               评论正文（可含 BBCode 标签）</div>
           <div class="comment_footer_ctn">...</div>
       </div>
   </div>
   注意：作者名在 <bdi> 内；[author] 徽章在链接之外，不可混入作者名；
        时间戳有两个同名 div，取带 title= 的那个（绝对时间）。

3) 浏览页可用标签（/workshop/browse/?appid=X 左侧筛选栏）
   Steam 经典浏览页的标签筛选链接形如：
   <a href=".../workshop/browse/?appid=4000&requiredtags=Map">Map</a>
   （真实 URL 实测样例：
     .../browse/?actualsort=trend&appid=730&...&requiredtags=Sticker&section=mtxitems
     —— 单值参数 requiredtags=<tag>，非数组写法）
   侧栏容器锚点可能为 id="tagFilter" / class="browseFilter" 等；
   本解析器以「requiredtags 链接」为最终提取依据，容器定位失败时
   退化为全页面兜底，保证健壮性。
   说明：浏览页结构本机因网络受限未能抓取实样（steamcommunity.com 在本机
   被 TCP 阻断，详见模块末尾「实测说明」），标签解析以 requiredtags
   链接锚点 + 多级兜底实现，单元测试用构造 HTML 覆盖。
"""

from __future__ import annotations

import html as _html
import json
import re
from typing import Any
from urllib.parse import unquote

from .logger import get_logger

log = get_logger("swdm.page")

# ---------------------------------------------------------------- 描述正文
_DESCRIPTION_ANCHOR_RE = re.compile(
    r'<div[^>]*\bclass="[^"]*workshopItemDescription[^"]*"[^>]*\bid="highlightContent"[^>]*>',
    re.IGNORECASE,
)
# 兜底：仅 class 匹配（id 缺失或改名时）
_DESCRIPTION_CLASS_RE = re.compile(
    r'<div[^>]*\bclass="[^"]*workshopItemDescription[^"]*"[^>]*>',
    re.IGNORECASE,
)


def _slice_div(html: str, start: int) -> str:
    """从 start（div 开标签结束位置）开始按 div 配对截取容器内容。"""
    depth = 1
    i = start
    while i < len(html) and depth > 0:
        nxt_open = html.find("<div", i)
        nxt_close = html.find("</div>", i)
        if nxt_close == -1:
            break
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            i = nxt_close + 6
    return html[start:i]


def _find_description_block(html: str) -> str:
    """定位描述区容器并返回其内部 HTML。失败返回空串。"""
    m = _DESCRIPTION_ANCHOR_RE.search(html)
    if not m:
        m = _DESCRIPTION_CLASS_RE.search(html)
    if not m:
        return ""
    return _slice_div(html, m.end())


# ---------------------------------------------------------------- 文本清洗
# 块级元素：闭合标签转为换行（避免把 <div>a</div><div>b</div> 粘成 ab）
_BLOCK_TAGS = (
    "div", "p", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "tr", "table", "section", "article", "header", "footer",
)
_BLOCK_CLOSE_RE = re.compile(
    r"</(" + "|".join(_BLOCK_TAGS) + r")\s*>", re.IGNORECASE
)
_BLOCK_OPEN_RE = re.compile(
    r"<(" + "|".join(_BLOCK_TAGS) + r")\b[^>]*/?>", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")


def _to_text(html_fragment: str) -> str:
    """HTML 片段 -> 纯文本：块级标签开/闭合转换行、去标签、还原实体、规整空白。"""
    if not html_fragment:
        return ""
    # <br> 与自闭合形式先统一为换行
    s = re.sub(r"<br\s*/?>", "\n", html_fragment, flags=re.IGNORECASE)
    # 块级元素开标签 -> 换行（如 <div class="bb_h1">Head</div> 独占一行）
    s = _BLOCK_OPEN_RE.sub("\n", s)
    # 块级元素闭合 -> 换行
    s = _BLOCK_CLOSE_RE.sub("\n", s)
    # 去掉其余标签（保留内容）
    s = _TAG_RE.sub("", s)
    # 还原 HTML 实体（&quot; &amp; &#39; &nbsp; …）
    s = _html.unescape(s)
    # 不间断空格归一为普通空格
    s = s.replace("\u00a0", " ")
    # 行内空白压缩
    lines = [_WS_RE.sub(" ", ln).strip() for ln in s.split("\n")]
    # 折叠连续空行，首尾去白
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out).strip()


def parse_description(html: str) -> str:
    """从工坊详情页 HTML 提取描述正文（纯文本）。

    锚点：<div class="workshopItemDescription" id="highlightContent">
    无描述或页面结构缺失时返回空串。
    """
    if not html:
        return ""
    block = _find_description_block(html)
    if not block:
        return ""
    return _to_text(block)


# ---------------------------------------------------------------- 作者
# 详情页物品作者区：creatorName 链接（bug9：GetPublishedFileDetails 只给
# steamid64，详情页 HTML 才有真实昵称）
_CREATOR_NAME_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*creatorName[^"]*"[^>]*>\s*'
    r'<a\b[^>]*>(?:\s*<bdi>)?([^<]+?)(?:</bdi>)?\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
# 兜底：工坊作者链接（/id/<昵称>/myworkshopfiles 或 /profiles/<steamid>）
_CREATOR_LINK_RE = re.compile(
    r'steamcommunity\.com/(?:id/([^/"]+)|profiles/(\d+))/myworkshopfiles'
)


def parse_creator_name(html: str) -> str:
    """从详情页 HTML 提取物品作者昵称（bug9）。

    优先 creatorName 区；兜底用 myworkshopfiles 链接的自定义昵称。
    只有 steamid64 时返回空（调用方应显示"未知"而非数字串）。
    """
    if not html:
        return ""
    m = _CREATOR_NAME_RE.search(html)
    if m:
        name = _html.unescape(m.group(1)).strip()
        if name:
            return name
    m = _CREATOR_LINK_RE.search(html)
    if m:
        return _html.unescape(m.group(1) or "").strip()
    return ""


# ---------------------------------------------------------------- 评论
# 评论块开标签：<div ... class="... commentthread_comment ..." id="comment_<cid>" ...>
_CLASS_ATTR_RE = re.compile(r'\bclass="([^"]*)"', re.IGNORECASE)
_COMMENT_ID_RE = re.compile(r'\bid="comment_(\d+)"')
# 作者链接：<a class="... commentthread_author_link" ...><bdi>名字</bdi></a>
_AUTHOR_LINK_RE = re.compile(
    r'<a\b[^>]*\bclass="[^"]*commentthread_author_link[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_BDI_RE = re.compile(r"<bdi\b[^>]*>(.*?)</bdi>", re.IGNORECASE | re.DOTALL)
# 时间戳：取带 title= 的那个 div（绝对时间）
_TIMESTAMP_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*commentthread_comment_timestamp[^"]*"'
    r'[^>]*\btitle="([^"]*)"[^>]*>',
    re.IGNORECASE,
)
# 评论正文容器：<div class="commentthread_comment_text" id="comment_content_<cid>">
_COMMENT_TEXT_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*commentthread_comment_text[^"]*"[^>]*\bid="comment_content_(\d+)"[^>]*>',
    re.IGNORECASE,
)
# 兜底：正文容器（无 id）
_COMMENT_TEXT_ANY_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*commentthread_comment_text[^"]*"[^>]*>',
    re.IGNORECASE,
)


def _find_comment_blocks(html: str) -> list[tuple[str, int, int]]:
    """定位各评论块 (cid, 内容开始位置, 块结束位置)。

    以「下一个评论块开标签起点」为边界截取，天然避免嵌套子评论重复计数。
    """
    if not html:
        return []
    starts: list[tuple[str, int, int]] = []  # (cid, 开标签起点, 内容起点)
    for m in re.finditer(r"<div\b[^>]*>", html, re.IGNORECASE):
        tag = m.group(0)
        cid_m = _COMMENT_ID_RE.search(tag)
        if not cid_m:
            continue
        cls_m = _CLASS_ATTR_RE.search(tag)
        if not cls_m:
            continue
        tokens = cls_m.group(1).split()
        if "commentthread_comment" not in tokens:
            continue  # 跳过 commentthread_comment_text/author/timestamp 等派生类
        starts.append((cid_m.group(1), m.start(), m.end()))

    blocks: list[tuple[str, int, int]] = []
    for idx, (cid, tag_start, content_start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(html)
        blocks.append((cid, content_start, end))
    return blocks


def parse_comments(html: str) -> list[dict]:
    """从工坊详情页 HTML 提取评论列表。

    返回 [{"author": str, "content": str, "timestamp": str}, ...]，
    按页面出现顺序（即新→旧）。无评论或结构缺失返回 []。

    说明：Steam 详情页 SSR 已渲染前 N 条评论（fixture 中为 10 条/页），
    因此本函数可直接从 HTML 解析；更早/更多评论需走 ajax 分页端点，
    见 fetch_comments。
    """
    if not html:
        return []
    out: list[dict] = []
    for cid, start, end in _find_comment_blocks(html):
        block = html[start:end]

        # 作者：<a class=commentthread_author_link><bdi>名字</bdi></a>
        author = ""
        am = _AUTHOR_LINK_RE.search(block)
        if am:
            inner = am.group(1)
            bm = _BDI_RE.search(inner)
            author = _to_text(bm.group(1) if bm else inner)
        if not author:
            continue  # 无作者链接（如已删除评论）——跳过

        # 时间戳：带 title= 的绝对时间
        timestamp = ""
        tm = _TIMESTAMP_RE.search(block)
        if tm:
            timestamp = _html.unescape(tm.group(1)).strip()

        # 正文：优先按精确 id 匹配，兜底取块内第一个正文容器
        content = ""
        cm = None
        for cm2 in _COMMENT_TEXT_RE.finditer(block):
            if cm2.group(1) == cid:
                cm = cm2
                break
        if cm is None:
            cm = _COMMENT_TEXT_ANY_RE.search(block)
        if cm:
            content = _to_text(_slice_div(block, cm.end()))

        out.append(
            {"author": author, "content": content, "timestamp": timestamp}
        )
    if out:
        log.debug("解析到 %d 条评论", len(out))
    return out


# ------------------------------------------------- 评论 ajax 端点（动态分页）
_COMMENT_RENDER_PATH = "/comment/PublishedFile_Public/render/{appid}/{item_id}/"


def _pick_str(d: dict, keys: list[str]) -> str:
    """从字典按候选键取首个非空字符串。"""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and v:
            return str(v)
    return ""


def _comment_from_json(c: Any) -> dict | None:
    """把 Steam 评论 render 端点的一条 JSON 记录转为统一 dict。

    端点字段未经本机在线验证（steamcommunity.com 在本机被 TCP 阻断），
    因此对多种常见键名做容错；无法识别时返回 None。
    """
    if not isinstance(c, dict):
        return None
    # 作者：可能为 {"author": {"name": ...}} 或平铺 author/author_name
    author = ""
    a = c.get("author")
    if isinstance(a, dict):
        author = _pick_str(a, ["name", "persona", "persona_name", "steamid"])
    else:
        author = _pick_str(c, ["author", "author_name", "author_persona"])
    # 正文：htmltext 可能含标签，统一清洗
    content_raw = _pick_str(c, ["text", "content", "htmltext", "html_text", "comment"])
    content = _to_text(content_raw) if content_raw else ""
    # 时间戳
    timestamp = _pick_str(c, ["timestamp", "time", "date", "formatted_timestamp"])
    if not author and not content:
        return None
    return {"author": author, "content": content, "timestamp": timestamp}


def fetch_comments(api: Any, item_id: str, appid: str, limit: int = 10) -> list[dict]:
    """通过 Steam 评论 ajax 端点抓取评论（动态分页）。

    端点：GET /comment/PublishedFile_Public/render/<appid>/<item_id>/
    参数：start / count 等。使用传入的 SteamAPI 实例（复用其浏览器 UA、
    节流与 429 退避重试）。

    返回 [{"author", "content", "timestamp"}, ...]；端点失败、非 JSON、
    或返回异常时返回空列表并记录日志（不抛异常，保证调用方可用性）。

    实测说明：本机环境 steamcommunity.com 被 TCP 阻断（api.steampowered.com
    可达，社区域名 443 连接超时），该端点未能在线验证。实现按
   Steam 社区评论 render 端点的公开字段约定编写并做容错；若字段不符，
    会安全降级为空列表。参见 parse_comments 直接解析 SSR HTML 的可靠路径。
    """
    if api is None:
        return []
    item_id = str(item_id or "").strip()
    appid = str(appid or "").strip()
    if not item_id or not appid:
        return []
    limit = max(1, min(int(limit or 10), 100))
    path = _COMMENT_RENDER_PATH.format(appid=appid, item_id=item_id)
    try:
        txt = api._community_get(path, {"start": 0, "count": limit})
    except Exception as e:  # noqa: BLE001 - 限流/网络错误，调用方不应崩溃
        log.warning("抓取评论端点失败 %s: %s", path, e)
        return []
    try:
        data = json.loads(txt)
    except (json.JSONDecodeError, TypeError):
        log.warning("评论端点返回非 JSON（可能需要登录或被重定向）: %s", txt[:120])
        return []
    if not isinstance(data, dict):
        return []
    raw_comments = data.get("comments")
    if not isinstance(raw_comments, list):
        log.warning("评论端点 JSON 无 comments 列表，键: %s", list(data.keys()))
        return []
    out: list[dict] = []
    for c in raw_comments:
        rec = _comment_from_json(c)
        if rec:
            out.append(rec)
    log.debug("评论端点返回 %d 条", len(out))
    return out


# ------------------------------------------------- 浏览页可用标签
# 真实结构（Wayback Machine 三快照实证 2022/2024/2026，见
# research/steam_tag_filter_research.md + research/_browse_*.html）：
#   - 旧版：标签筛选栏是表单控件，<input type="checkbox" name="requiredtags[]"
#     value="Map" class="inputTagsFilter"> 与 <select name="requiredtags[]">
#     内的 <option value="Addon">；表单锚点 <form id="TagsFilterForm">
#   - 新版（React SSR）：window.SSR.loaderData = ["<json>"]，二次 parse 后
#     declaredTags.<section>_tags[*].tags[*] = {id,name,display_name,...}
# 浏览页**没有** <a href=...requiredtags=X> 链接（旧实现的假设错误，
# 是"cookie/隐私政策"混入标签的直接根源），也没有标签热度计数。

_TAG_ATTR_VALUE_RE = re.compile(r'\bvalue="([^"]*)"', re.IGNORECASE)
_TAG_ATTR_NAME_RE = re.compile(
    r'\bname="requiredtags(?:%5B%5D|%5b%5d|\[\])?"', re.IGNORECASE
)
# 旧版表单内所有带 name=requiredtags[] 的控件（checkbox / input hidden）
_TAG_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.IGNORECASE)
# 下拉框：name 在 <select> 上，option 自身无 name，需按块提取
_TAG_SELECT_RE = re.compile(
    r'<select\b([^>]*\bname="requiredtags(?:%5B%5D|%5b%5d|\[\])?"[^>]*)>'
    r"(.*?)</select>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_OPTION_RE = re.compile(r"<option\b([^>]*)>", re.IGNORECASE)
# 新版 SSR：loaderData 是 JSON 字符串数组（需二次 parse）；赋值可能极长
# （单文件数百 KB），正则不可靠，改用字符级 JSON 边界扫描
_SSR_LOADER_START_RE = re.compile(
    r"window\.SSR\.loaderData\s*=\s*\[", re.IGNORECASE
)


def _slice_json_array(html: str, start: int) -> str | None:
    """从 html[start] == '[' 开始，按 JSON 边界扫描到配对的 ']'。

    正确处理字符串内的括号与转义引号。返回含两端括号的子串。
    """
    if start >= len(html) or html[start] != "[":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return html[start:i + 1]
    return None


def _tags_from_form_inputs(fragment: str) -> list[str]:
    """从 HTML 片段提取 requiredtags[] 控件的 value（有序去重）。

    旧版浏览页标签的真实形态：checkbox 与 select option，只取 value 属性，
    绝不回退链接文本（回退会把页脚/导航链接当标签，bug14 根源）。
    """
    out: list[str] = []
    seen: set[str] = set()

    def _push(tag: str) -> None:
        tag = _html.unescape(tag).strip()
        # select 占位项 < none specified >（value="-1"）；真实标签
        # 不会是纯数字
        if not tag or tag.startswith("<") or tag.lstrip("-").isdigit():
            return
        if tag in seen:
            return
        seen.add(tag)
        out.append(tag)

    for m in _TAG_INPUT_RE.finditer(fragment or ""):
        attrs = m.group(1)
        if not _TAG_ATTR_NAME_RE.search(attrs):
            continue
        vm = _TAG_ATTR_VALUE_RE.search(attrs)
        if vm:
            _push(vm.group(1))
    # select：name 在父标签上，取块内所有 option 的 value
    for m in _TAG_SELECT_RE.finditer(fragment or ""):
        for om in _TAG_OPTION_RE.finditer(m.group(2)):
            vm = _TAG_ATTR_VALUE_RE.search(om.group(1))
            if vm:
                _push(vm.group(1))
    return out


def _tags_from_ssr_loader(html: str) -> list[str]:
    """新版 React SSR：window.SSR.loaderData → declaredTags.*_tags[*].tags。

    loaderData 是「JSON 字符串的数组」，需要二次 json.loads。
    取所有 declaredTags 分组合并（浏览页侧栏本就跨分类展示全部标签）。
    UI 显示用 display_name，拼筛选 URL 应用 name；此处返回 name 以
    与 requiredtags 参数一致。
    """
    m = _SSR_LOADER_START_RE.search(html or "")
    if not m:
        return []
    arr = _slice_json_array(html or "", m.end() - 1)
    if not arr:
        return []
    try:
        outer = json.loads(arr)
    except (ValueError, TypeError):
        return []
    for blob in outer or []:
        if not isinstance(blob, str):
            continue
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            continue
        declared = data.get("declaredTags") if isinstance(data, dict) else None
        if not isinstance(declared, dict):
            continue
        out: list[str] = []
        seen: set[str] = set()
        for group in declared.values():
            if not isinstance(group, list):
                continue
            for sec in group:
                if not isinstance(sec, dict):
                    continue
                for tag in sec.get("tags") or []:
                    if not isinstance(tag, dict):
                        continue
                    name = (tag.get("name") or "").strip()
                    if name and name not in seen and not name.startswith("#"):
                        seen.add(name)
                        out.append(name)
        if out:
            return out
    return []


def parse_available_tags_with_counts(html: str) -> list[tuple[str, int]]:
    """同 parse_available_tags，但返回 (标签名, 热度计数) 元组列表。

    浏览页没有标签计数（三快照实测 (N) 计数与 count 字段均不存在），
    因此计数恒为 0，由 UI 决定是否显示。
    """
    return [(t, 0) for t in parse_available_tags(html)]


def parse_available_tags(html: str) -> list[str]:
    """从工坊浏览页（/workshop/browse/?appid=X）提取该游戏的可用标签列表。

    四级降级（实证结构，详见 research/steam_tag_filter_research.md）：
      1) 新版 React SSR：window.SSR.loaderData → declaredTags.*_tags
      2) 旧版表单：<form id="TagsFilterForm"> 内 requiredtags[] 控件
      3) 宽兜底：全页面属性级扫描 requiredtags[] 控件（不用链接文本）
      4) 全失败 → 返回空（UI 提示"拉取失败"而非塞入导航链接）

    返回有序去重的标签名列表；无标签或页面结构缺失返回 []。
    """
    if not html:
        return []

    tags = _tags_from_ssr_loader(html)
    if tags:
        log.debug("浏览页标签（新版 SSR）: %s", tags[:10])
        return tags

    # 旧版：定位 TagsFilterForm 表单块
    form_m = re.search(
        r'<form\b[^>]*\b(?:id|name)="TagsFilterForm"[^>]*>(.*?)</form>',
        html, re.IGNORECASE | re.DOTALL,
    )
    if form_m:
        tags = _tags_from_form_inputs(form_m.group(1))
        if tags:
            log.debug("浏览页标签（旧版表单）: %s", tags[:10])
            return tags

    # 宽兜底：全页面属性级扫描（只认 requiredtags[] 控件的 value）
    tags = _tags_from_form_inputs(html)
    if tags:
        log.debug("浏览页标签（全页面控件兜底）: %s", tags[:10])
    return tags


__all__ = [
    "parse_description",
    "parse_comments",
    "fetch_comments",
    "parse_available_tags",
    "parse_available_tags_with_counts",
    "parse_creator_name",
]

"""
实测说明（2026-09 会话内）：
- 描述/评论锚点：由 tests/fixtures 下 4 个真实详情页 HTML 验证，确定可靠。
- 评论 ajax 端点 /comment/PublishedFile_Public/render/<appid>/<item_id>/：
  本机 steamcommunity.com 443 端口被 TCP 阻断（DNS 正常解析到
  31.13.88.169，但 connect 超时；同会话 api.steampowered.com 返回 200），
  因此未能在线验证端点返回。fetch_comments 按公开字段约定实现并做容错，
  不可用时安全降级为空列表；可靠的评论来源是 parse_comments 直接解析
  SSR HTML（详情页已内联前 N 条评论）。
- 浏览页标签：结构已由 Wayback Machine 三快照实证（2022/2024 经典版 +
  2026-09 React SSR，见 research/_browse_*.html 与
  research/steam_tag_filter_research.md）。旧假设「浏览页有 requiredtags
  链接 + tagFilter/browseFilter 容器」从未存在；真实来源是表单控件
  （checkbox/select 的 value）与新版 SSR JSON（declaredTags）。浏览页
  没有标签热度计数，parse_available_tags_with_counts 计数恒为 0。
  新旧版灰度分流未知，两套结构都必须兼容。
"""
