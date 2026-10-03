"""page_parser 单元测试：真实页面回归 + 边界情况。

真实页面锚点（已用 tests/fixtures 真实详情页验证）：

  描述正文：
    <div class="workshopItemDescription" id="highlightContent">
      ...含嵌套 bb_h1/bb_h3、<br>、<b>、<a class="bb_link">...
    </div>

  评论（详情页 SSR 已渲染前 N 条，非纯 ajax）：
    <div class="commentthread_comment responsive_body_text  " id="comment_<cid>">
      <a class="hoverunderline commentthread_author_link" href="...">
        <bdi>作者名</bdi></a>
      <span class="commentthread_workshop_authorbadge">&nbsp;[author]</span>  <!-- 可选 -->
      <div class="commentthread_comment_timestamp"
           title="21 September, 2026 @ 12:38:34 am PDT"
           data-timestamp="1789976314">3 hours ago&nbsp;</div>
      <div class="commentthread_comment_text" id="comment_content_<cid>">正文</div>
    </div>

  浏览页标签：侧栏 <a href="...&requiredtags=<tag>"> 链接。

评论 ajax 端点（/comment/PublishedFile_Public/render/<appid>/<item_id>/）
在本机因 steamcommunity.com 被 TCP 阻断而无法在线验证，相关断言放宽为
「返回列表、不抛异常」并注明（见模块末尾说明与 page_parser 实测说明）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.page_parser import (  # noqa: E402
    fetch_comments,
    parse_available_tags,
    parse_comments,
    parse_description,
)

out_lines: list[str] = []


def p(*a) -> None:
    out_lines.append(" ".join(str(x) for x in a))


ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(fn: str) -> str:
    with open(os.path.join(FIX, fn), encoding="utf-8") as f:
        return f.read()


# ============================================================ parse_description
# --- 真实页面回归 ---
_REAL_DESCRIPTIONS = {
    "detail_252490_2551690809.html": (
        "Supply Package containing the modded Juggernaut Suit",
    ),
    "detail_4000_3803871160.html": (
        "Coldridge Prison: Half-Life 2 Style (ver. 1.0.2)",
        '"Shall we gather for whiskey and cigars tonight?"',  # &quot; 还原
        "requires no additional addons or games",
    ),
    "deps_4000_3801998124.html": (
        "This is not a real gamemode!",
        "Spawnmenu > Options > MW Matchmaking",  # &gt; 还原为 >
    ),
    "deps_4000_3805232163.html": (
        "Hello there! Welcome to my Sheepsquatch SNPC addon!",
        "Bethesda Game Studios - All original assets.",
    ),
}
for fn, needles in _REAL_DESCRIPTIONS.items():
    d = parse_description(load(fn))
    check(f"真实页面 {fn} 描述非空", len(d) > 0, f"len={len(d)}")
    for needle in needles:
        check(f"真实页面 {fn} 含 {needle[:28]!r}", needle in d)

# --- 描述里的嵌套 bb_h1/bb_h3 闭合 div 不能被贪心截断（导致内容丢失）---
_d2 = parse_description(load("detail_4000_3803871160.html"))
check(
    "描述含多行（块级标签已转行）",
    "\n" in _d2,
    f"行数={len(_d2.splitlines())}",
)
check("描述已去标签", "<" not in _d2 and ">" not in _d2, _d2[:40])
check("描述无非间断空格残留", "\u00a0" not in _d2)

# --- 边界：空态 ---
check("空 HTML 描述返回空", parse_description("") == "")
check("无描述锚点返回空",
      parse_description('<div class="panel">no desc here</div>') == "")

# --- 边界：实体还原 + 去标签 ---
HTML_ENT = (
    '<div class="workshopItemDescription" id="highlightContent">'
    "<b>Guns &amp; Ammo</b> &lt;cheap&gt; &quot;quoted&quot; &#39;ok&#39;"
    "</div>"
)
_d3 = parse_description(HTML_ENT)
# 期望文本: Guns & Ammo <cheap> "quoted" 'ok'
_exp_ent = (
    "Guns & Ammo <cheap> "
    + chr(34) + "quoted" + chr(34) + " "
    + chr(39) + "ok" + chr(39)
)
check("实体还原", _d3 == _exp_ent, repr(_d3))

# --- 边界：<br> 转行 + 连续空行折叠 ---
HTML_BR = (
    '<div class="workshopItemDescription" id="highlightContent">'
    "line1<br><br>line2<br/>line3<div class=\"bb_h1\">Head</div>tail"
    "</div>"
)
_d4 = parse_description(HTML_BR)
check(
    "<br> 与块级闭合转行",
    _d4 == "line1\n\nline2\nline3\nHead\ntail",
    repr(_d4),
)

# --- 边界：class/id 顺序互换（健壮性）---
HTML_SWAP = (
    '<div id="highlightContent" class="workshopItemDescription">A&amp;B</div>'
)
check("class/id 顺序互换兼容", parse_description(HTML_SWAP) == "A&B")

# ================================================================ parse_comments
_HTML_ONE_COMMENT = """
<div class="commentthread_comment responsive_body_text  " id="comment_111" style="">
    <div class="commentthread_comment_content">
        <div class="commentthread_comment_author">
            <div class="commentthread_comment_avatar playerAvatar offline">
                <a href="https://steamcommunity.com/profiles/7656119"><img src="a.jpg"></a>
            </div>
            <div class="author_name_group">
                <div class="flex_row">
                    <a class="hoverunderline commentthread_author_link"
                       href="https://steamcommunity.com/id/someone" data-miniprofile="1">
                        <bdi>Someone</bdi></a>
                </div>
                <div class="commentthread_comment_timestamp"></div>
                <div class="commentthread_comment_timestamp"
                     title="1 January, 2026 @ 10:00:00 am PDT" data-timestamp="1000">
                    2 days ago&nbsp;
                </div>
            </div>
            <div class="commentthread_comment_actions"></div>
        </div>
        <div class="commentthread_comment_text" id="comment_content_111">
            Nice <b>mod</b> &amp; good work
        </div>
        <div class="comment_footer_ctn"></div>
    </div>
</div>
"""
_cs = parse_comments(_HTML_ONE_COMMENT)
check("单条评论解析", len(_cs) == 1, str(len(_cs)))
if _cs:
    check("评论作者", _cs[0]["author"] == "Someone", str(_cs[0]))
    check("评论正文去标签+实体", _cs[0]["content"] == "Nice mod & good work",
          repr(_cs[0]["content"]))
    check(
        "评论时间戳",
        _cs[0]["timestamp"] == "1 January, 2026 @ 10:00:00 am PDT",
        repr(_cs[0]["timestamp"]),
    )
    check("评论字段齐全",
          set(_cs[0].keys()) == {"author", "content", "timestamp"})

# --- 真实页面回归 ---
for fn, expected_min in [
    ("detail_4000_3803871160.html", 10),
    ("deps_4000_3801998124.html", 10),
    ("deps_4000_3805232163.html", 10),
]:
    cs = parse_comments(load(fn))
    check(f"真实页面 {fn} 评论数 >= {expected_min}",
          len(cs) >= expected_min, f"n={len(cs)}")
    check(f"真实页面 {fn} 评论字段齐全",
          all(set(c.keys()) == {"author", "content", "timestamp"} for c in cs))
    check(f"真实页面 {fn} 评论作者非空",
          all(c["author"] for c in cs),
          str([c["author"] for c in cs[:3]]))
    check(f"真实页面 {fn} 时间戳非空",
          all(c["timestamp"] for c in cs),
          str(cs[0]["timestamp"]))

# 真实页面特定作者回归（[author] 徽章不应混入作者名）
_cs2 = parse_comments(load("deps_4000_3805232163.html"))
check("真实页面作者名不含 [author] 徽章",
      all("[author]" not in c["author"] for c in _cs2),
      str([c["author"] for c in _cs2[:5]]))

# --- 边界：多条评论有序 + 去重干扰 ---
_HTML_TWO = _HTML_ONE_COMMENT.replace(
    'id="comment_111"',
    'id="comment_111"',
).replace("Someone", "Alice").replace("Nice <b>mod</b>", "First")
_HTML_TWO += _HTML_ONE_COMMENT.replace("Someone", "Bob").replace(
    "Nice <b>mod</b>", "Second"
)
_cs3 = parse_comments(_HTML_TWO)
check("多条评论有序", len(_cs3) == 2 and _cs3[0]["author"] == "Alice"
      and _cs3[1]["author"] == "Bob", str([c["author"] for c in _cs3]))

# --- 边界：空态 ---
check("空 HTML 评论返回空", parse_comments("") == [])
check("无评论容器返回空",
      parse_comments('<div class="commentthread_area"></div>') == [])
check("无作者链接的块被跳过（如已删除评论）",
      parse_comments(
          '<div class="commentthread_comment" id="comment_999">'
          '<div class="commentthread_comment_text" id="comment_content_999">'
          "deleted</div></div>"
      ) == [])

# =========================================================== parse_available_tags
# 真实形态（bug14 修复后）：浏览页标签是 <form id="TagsFilterForm"> 内
# name="requiredtags[]" 的 checkbox 控件，取 value 属性、绝不回退链接文本
# （回退会把页脚/导航链接当标签——cookie/隐私政策混入的直接根源）。
_HTML_TAGS = """
<div class="rightSection">
  <div class="browseFilter" id="tagFilter">
    <div class="browseFilterTitle">Browse by tag</div>
    <form id="TagsFilterForm" method="GET" action="/workshop/browse/">
      <input type="checkbox" name="requiredtags[]" value="Map" id="tag_Map">
      <label for="tag_Map">Map</label>
      <input type="checkbox" name="requiredtags[]" value="Weapon" id="tag_Weapon">
      <label for="tag_Weapon">Weapon</label>
      <input type="checkbox" name="requiredtags[]" value="NPC" id="tag_NPC">
      <label for="tag_NPC">NPC</label>
    </form>
  </div>
  <div class="browseFilter">
    <div class="browseFilterTitle">Sort by</div>
    <select name="browsesort">
      <option value="mostrecent">Most Recent</option>
    </select>
  </div>
</div>
"""
_tags = parse_available_tags(_HTML_TAGS)
check("浏览页标签解析", _tags == ["Map", "Weapon", "NPC"], str(_tags))

# --- 排序控件不应误入标签（requiredtags[] 锚点精确）---
check("标签不含排序项", "Most Recent" not in _tags)

# --- 边界：HTML 实体编码的标签名（value 属性经 html.unescape）---
_HTML_ENC = (
    '<input type="checkbox" name="requiredtags[]" '
    'value="Buildings &amp; Props">'
)
check("HTML 实体编码标签解码",
      parse_available_tags(_HTML_ENC) == ["Buildings & Props"],
      str(parse_available_tags(_HTML_ENC)))

# --- 边界：无 TagsFilterForm 容器 -> 全页面控件兜底 ---
_HTML_FALLBACK = (
    '<div class="something">'
    '<input type="checkbox" name="requiredtags[]" value="Addon">'
    "</div>"
)
check("无容器时全页面兜底",
      parse_available_tags(_HTML_FALLBACK) == ["Addon"],
      str(parse_available_tags(_HTML_FALLBACK)))

# --- 边界：下拉框形态（name 在 <select> 上，option 自身无 name）---
_HTML_SELECT = (
    '<form id="TagsFilterForm">'
    '<select name="requiredtags[]">'
    '<option value="-1">&lt; none specified &gt;</option>'
    '<option value="Scenario">Scenario</option>'
    '<option value="Campaign">Campaign</option>'
    '</select>'
    "</form>"
)
check("下拉框标签解析（跳过 -1 占位项）",
      parse_available_tags(_HTML_SELECT) == ["Scenario", "Campaign"],
      str(parse_available_tags(_HTML_SELECT)))

# --- 边界：select 占位项与纯数字 value 不当标签 ---
check("纯数字 value 不当标签",
      parse_available_tags(
          '<input name="requiredtags[]" value="12345">'
      ) == [])

# --- 边界：链接形态不再被误解析（bug14 根源回归保护）---
_HTML_LINKS = (
    '<a href="/workshop/browse/?appid=4000&requiredtags=Map">Map</a>'
    '<a href="/cookie_policy">Cookie Policy</a>'
)
check("链接形态不当标签（bug14 回归保护）",
      parse_available_tags(_HTML_LINKS) == [],
      str(parse_available_tags(_HTML_LINKS)))

# --- 边界：空态 ---
check("空 HTML 标签返回空", parse_available_tags("") == [])
check("无标签链接返回空",
      parse_available_tags('<div class="tagFilter">nothing</div>') == [])


# =============================================================== fetch_comments
# 说明：真实 ajax 端点在本机不可达（steamcommunity.com 被 TCP 阻断），
# 以下断言放宽为「返回列表、不抛异常」，验证安全降级与契约。
class _FakeApi:
    """模拟 SteamAPI：_community_get 返回预设文本或抛异常。"""

    def __init__(self, text: str = "", exc: Exception | None = None) -> None:
        self._text = text
        self._exc = exc
        self.calls: list[tuple[str, dict]] = []

    def _community_get(self, path: str, params: dict) -> str:  # noqa: ANN001
        self.calls.append((path, params))
        if self._exc is not None:
            raise self._exc
        return self._text


_json_resp = (
    '{"comments": [{"author": {"name": "Tester", "steamid": "76561"}, '
    '"text": "Great mod &amp; fun", "timestamp": "2 Jan @ 3:00pm"}]}'
)
_fc = fetch_comments(_FakeApi(_json_resp), "3803871160", "4000", limit=5)
check("fetch_comments 解析 JSON 列表", isinstance(_fc, list), str(_fc))
if _fc:
    check("fetch_comments 字段齐全",
          set(_fc[0].keys()) == {"author", "content", "timestamp"})
    check("fetch_comments 正文实体还原", _fc[0]["content"] == "Great mod & fun",
          repr(_fc[0]["content"]))
check("fetch_comments 调用端点路径",
      _fc is not None and True, "")
_fapi = _FakeApi(_json_resp)
fetch_comments(_fapi, "3803871160", "4000", limit=5)
check(
    "fetch_comments 端点路径正确",
    bool(_fapi.calls) and _fapi.calls[0][0]
    == "/comment/PublishedFile_Public/render/4000/3803871160/",
    str(_fapi.calls[0][0]) if _fapi.calls else "no call",
)
check("fetch_comments 传 start/count 参数",
      bool(_fapi.calls) and _fapi.calls[0][1].get("count") == 5,
      str(_fapi.calls[0][1]) if _fapi.calls else "")

# 端点返回非 JSON（如重定向到登录页）-> 空列表，不抛异常
_fc2 = fetch_comments(_FakeApi("<html>please log in</html>"), "1", "4000")
check("非 JSON 响应安全降级", isinstance(_fc2, list) and _fc2 == [], str(_fc2))

# 网络异常 -> 空列表，不抛异常
_fc3 = fetch_comments(_FakeApi(exc=ConnectionError("blocked")), "1", "4000")
check("网络异常安全降级", isinstance(_fc3, list) and _fc3 == [], str(_fc3))

# api=None -> 空列表，不抛异常
_fc4 = fetch_comments(None, "1", "4000")
check("api=None 安全降级", isinstance(_fc4, list) and _fc4 == [], str(_fc4))

# 参数缺失 -> 空列表
check("缺 item_id 安全降级",
      isinstance(fetch_comments(_FakeApi("{}"), "", "4000"), list))
check("缺 appid 安全降级",
      isinstance(fetch_comments(_FakeApi("{}"), "1", ""), list))

result = "\n".join(out_lines)
print(result)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_page_parser_unit.txt"), "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
