"""工坊 mod 冲突声明提取。

mod 作者常在简介里写明已验证的冲突 mod，例如：

  - 本 mod 与 XXX mod 冲突，请勿同时使用
  - Conflict with [Some Mod](steamcommunity.com/sharedfiles/filedetails/?id=123)
  - Incompatible with ABC addon
  - 不要和 123456789 一起装

本模块从简介文本（可能含 HTML / BBCode / Markdown 标记）中提取这些声明，
再与本地 mod 库对照，提示用户“已安装的冲突 mod”。

设计约束：纯逻辑，零网络请求、零文件 IO。

提取流程：
1. 按句（换行 / 。！？ / <br> / 块级闭合标签 / BBCode 块边界）切分简介；
2. 丢弃含否定语义的句子（“不冲突”“no conflict”“compatible”等）；
3. 命中冲突关键词的句子，再到其中找工坊链接（HTML / BBCode / Markdown / 裸链接）：
   有链接 → 提取 id 与链接文本作为名称；无链接 → 用关键词附近的文本猜测名称。
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from typing import NamedTuple

from .logger import get_logger

log = get_logger("swdm.conflict")

__all__ = ["ConflictInfo", "extract_conflicts", "check_installed_conflicts"]


@dataclass
class ConflictInfo:
    """一条从简介中提取到的冲突声明。"""

    mod_id: str       # 冲突 mod 的工坊 id（从简介链接提取，无链接则空）
    name: str         # 冲突 mod 名称（链接文本或关键词附近的名词短语）
    statement: str    # 原始声明句（供用户核对）
    confidence: str   # "high" / "medium" / "low"


# ------------------------------------------------------------------ 关键词

# 明确的冲突关键词（中英）。命中即视为冲突声明，配合链接判定置信度。
_HARD_KW_RE = re.compile(
    r"请勿同时使用|请勿同时安装"
    r"|请勿与.{0,20}同时|请勿和.{0,20}同时"
    r"|不要同时使用|不要同时安装|不要和|不要与"
    r"|不可共存|不可同时|不能同时|不兼容|互斥|无法共存|冲突"
    r"|incompatible\s+with|not\s+compatible\s+with"
    r"|conflicts?\s+with|conflicting\s+with"
    r"|mutually\s+exclusive"
    r"|do\s+not\s+(?:use|combine|stack)\s+with|don'?t\s+use\s+with"
    r"|cannot\s+be\s+used\s+(?:with|together)"
    r"|conflicts?\b|incompatible\b",
    re.IGNORECASE,
)

# 模糊/视语境的关键词：单独出现时可信度低（如“植被覆盖”也会命中“覆盖”）。
_SOFT_KW_RE = re.compile(r"(?<![不没])覆盖|overrides?\b|overwrites?\b", re.IGNORECASE)

# 否定/兼容语义：命中即丢弃整句（抑制误报）。
# 注意 lookbehind：“不兼容”“不可共存”“incompatible”内部含“兼容/可共存/compatib”，
# 但它们本身是冲突声明，绝不能被抑制。
_SUPPRESS_RE = re.compile(
    r"不冲突|不会冲突|无冲突|没有冲突|不存在冲突"
    r"|冲突(?:解决|修复|处理|避免|调解)"
    r"|(?<![不无非])兼容"
    r"|可以共存|(?<!不)可共存"
    r"|no\s+conflicts?\b|without\s+(?:any\s+)?conflicts?\b|not\s+conflicts?\b"
    r"|(?:does|do|is|are|will)\s+not\s+conflict\b|doesn'?t\s+conflict\b|won'?t\s+conflict\b"
    r"|conflicts?\s+(?:resolution|fix|manager|detector|patch)\b"
    r"|not\s+(?:override|overwrite)\b"
    r"|(?<!\bin)compatib\w*"
    r"|works\s+well\s+with\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------------ 链接

_STEAM_URL = (
    r"(?:https?://)?(?:www\.)?steamcommunity\.com/"
    r"(?:sharedfiles|workshop)/filedetails/\?id=(\d+)"
)

# <a href="...">文本</a>（引号可省略，属性可有可无）
_LINK_HTML_RE = re.compile(
    r'<a\b[^>]*?href\s*=\s*(["\']?)\s*(' + _STEAM_URL + r'[^"\'\s>]*)\1[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
# [url=...]文本[/url]
_LINK_BBC_RE = re.compile(
    r'\[url\s*=\s*(["\']?)\s*(' + _STEAM_URL + r'[^\s\]]*)\1\s*\](.*?)\[/url\]',
    re.IGNORECASE | re.DOTALL,
)
# [url]裸链接[/url]
_LINK_BBC_BARE_RE = re.compile(
    r"\[url\]\s*(" + _STEAM_URL + r"[^\s\]]*)\s*\[/url\]",
    re.IGNORECASE,
)
# Markdown：[文本](链接)
_LINK_MD_RE = re.compile(
    r"\[([^\]]+)\]\s*\(\s*(" + _STEAM_URL + r"[^)\s]*)\s*\)",
    re.IGNORECASE,
)
# 裸链接（上面各类标记区域被遮罩后，再在剩余文本里找）
_LINK_NAKED_RE = re.compile(
    r"(?<![\w/.:#-])(" + _STEAM_URL + r")",
    re.IGNORECASE,
)

# (正则, id分组, 链接文本分组)
_LINK_SPECS = (
    (_LINK_HTML_RE, 3, 4),
    (_LINK_BBC_RE, 3, 4),
    (_LINK_BBC_BARE_RE, 2, None),
    (_LINK_MD_RE, 3, 1),
)


class _Link(NamedTuple):
    start: int
    end: int
    mod_id: str
    text: str


# ------------------------------------------------------------------ 文本工具

_HTML_TAG_RE = re.compile(r"<[^<>]+>")
_BBCODE_TAG_RE = re.compile(
    r"\[/?\s*(?:url|b|i|u|s|o|color|size|font|quote|code|spoiler|noparse|list|olist|"
    r"table|tr|td|th|img|youtube|yt|hr|center|right|left|justify|h[1-6]|sub|sup|pre|"
    r"em|strong|anchor|bq)\b[^\]]*\]",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
# 名称首尾需要清理的标点
_EDGE_PUNCT_RE = re.compile(r"^[\s。，,、:：;；!！?？.·\-—*()\[\]「」“”\"']+|[\s。，,、:：;；!！?？.·\-—*()\[\]「」“”\"']+$")
# 名称截断点（顿号、分句、关键词复现、常见虚词/连接词）
_NAME_CUT_RE = re.compile(
    r"[。，,、;；！!？?\n.]|"
    r"(?:一起|同时|使用|安装|冲突|兼容|请勿|不要|不可|不能|"
    r"详情|官网|链接|地址|参考|注意|以及|并且|并|和|与|"
    r"and\b|with\b|to\b|of\b|the\b)",
    re.IGNORECASE,
)
# 名称开头若是这些词，说明截出来的不是 mod 名（而是后续说明或关键词本身）
_JUNK_START_RE = re.compile(
    r"^(?:详情|见|官网|链接|地址|请勿|请|谢|注意|参考|如果|若|"
    r"同时|使用|安装|一起|不要|不可|不能|不|"
    r"冲突|兼容|覆盖|互斥|http|www|steamcommunity)",
    re.IGNORECASE,
)
# 关键词之后、名称之前需要跳过的虚词（中英）
_FILLER_RE = re.compile(
    r"^(?:(?:the|a|an|with|and|of|to|for|is|are)\b|[与和跟及了\s、，,:：])+"
)
# “本 mod / 该 mod / 本模组”之类的自称
_SELF_PREFIX_RE = re.compile(r"^(?:本|该|此|这个|这款)?\s*(?:mod|模组|MOD)\b", re.IGNORECASE)


def _to_plain(text: str) -> str:
    """转成可见纯文本：去 HTML/BBCode 标签、还原实体、折叠空白。"""
    t = _HTML_TAG_RE.sub(" ", text)
    t = _BBCODE_TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    return _WS_RE.sub(" ", t).strip()


def _clean_name(text: str) -> str:
    """把链接文本清理成可读名称。"""
    name = _EDGE_PUNCT_RE.sub("", _to_plain(text or ""))
    return name[:60]


def _name_after(plain: str, kw_end: int) -> str:
    """关键词之后的名称候选。"""
    after = _FILLER_RE.sub("", plain[kw_end:])
    cut = _NAME_CUT_RE.search(after)
    if cut:
        after = after[: cut.start()]
    return _EDGE_PUNCT_RE.sub("", after)


def _name_before(plain: str, kw_start: int) -> str:
    """关键词之前的名称候选（中文“与 XXX 冲突”的常见语序）。"""
    seg = plain[:kw_start]
    cut = max(seg.rfind(c) for c in ("与", "和", "跟", "，", ","))
    if cut >= 0:
        seg = seg[cut + 1:]
    seg = _EDGE_PUNCT_RE.sub("", seg)
    return _SELF_PREFIX_RE.sub("", seg)[:60]


def _guess_name(plain: str, kw: re.Match | None) -> str:
    """无链接时，从关键词附近猜一个名称（best-effort 启发式）。

    优先取关键词之后的文本（“请勿同时使用 XXX”语序），
    其次取关键词之前的文本（中文“与 XXX 冲突”语序）；
    若候选以关键词或后续说明开头，则视为无效。
    """
    if not kw:
        return ""
    for cand in (_name_after(plain, kw.end()), _name_before(plain, kw.start())):
        if cand and not _JUNK_START_RE.match(cand):
            return cand[:60]
    return ""


def _find_links(text: str) -> tuple[list[_Link], str]:
    """提取全部工坊链接（含位置），并返回“链接已遮罩”的文本副本。

    标记型链接优先于裸链接；遮罩文本供分句使用，避免链接内部的
    “?”“.”等字符被误当作句子结束符。
    """
    links: list[_Link] = []
    masked = list(text)  # 已被标记覆盖的字符先置空，避免裸链接重复命中
    for rx, id_group, text_group in _LINK_SPECS:
        for m in rx.finditer(text):
            links.append(
                _Link(
                    m.start(),
                    m.end(),
                    m.group(id_group),
                    (m.group(text_group) if text_group else ""),
                )
            )
            for i in range(m.start(), m.end()):
                masked[i] = " "
    masked_text = "".join(masked)
    for m in _LINK_NAKED_RE.finditer(masked_text):
        links.append(_Link(m.start(1), m.end(1), m.group(2), ""))
    links.sort(key=lambda lk: lk.start)
    return links, masked_text


# ------------------------------------------------------------------ 分句

_SENT_SEP_RE = re.compile(
    r"<br\s*/?>|</p\s*>|</div\s*>|</li\s*>|</h[1-6]\s*>|</tr\s*>|</blockquote\s*>"
    r"|\[/list\]|\[/olist\]|\[/quote\]|\[/code\]|\[/spoiler\]|\[\*\]"
    r"|[\n。！？!?]|(?<!\d)\.\s+",
    re.IGNORECASE,
)


def _sentence_spans(masked: str, total_len: int) -> list[tuple[int, int]]:
    """在“链接已遮罩”的文本上按声明边界切分，返回原文的 [(起点, 终点)]。

    遮罩后链接内部的 “?”/“.” 不再被当作句子结束符，位置与原文一一对应。
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_SEP_RE.finditer(masked):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < total_len:
        spans.append((start, total_len))
    return spans


# ------------------------------------------------------------------ 主接口


def extract_conflicts(description: str, appid: str = "") -> list[ConflictInfo]:
    """从 mod 简介提取冲突声明。

    :param description: mod 简介原文（可含 HTML / BBCode / Markdown）。
    :param appid: 当前 mod 自身的物品 id；简介里指向自己的链接会被排除
                  （mod 常在简介里放自己的链接）。
    :return: ConflictInfo 列表，按出现顺序去重。
    """
    if not description or not isinstance(description, str):
        return []

    self_id = str(appid) if appid else ""
    links, masked = _find_links(description)

    out: list[ConflictInfo] = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()

    for s_start, s_end in _sentence_spans(masked, len(description)):
        raw = description[s_start:s_end]
        plain = _to_plain(raw)
        if not plain:
            continue
        if _SUPPRESS_RE.search(plain):
            continue

        hard = _HARD_KW_RE.search(plain)
        soft = None if hard else _SOFT_KW_RE.search(plain)
        kw = hard or soft
        if kw is None:
            continue

        # 本句内的工坊链接（排除指向自身的）
        sent_links = [
            lk
            for lk in links
            if lk.start < s_end and lk.end > s_start and not (self_id and lk.mod_id == self_id)
        ]

        if hard:
            confidence = "high" if sent_links else "medium"
        else:
            confidence = "low"  # 仅命中“覆盖/override”这类语境关键词

        statement = _WS_RE.sub(" ", raw).strip()
        if not statement:
            continue

        if sent_links:
            for lk in sent_links:
                if lk.mod_id in seen_ids:
                    continue
                seen_ids.add(lk.mod_id)
                name = _clean_name(lk.text) or _guess_name(plain, kw)
                out.append(ConflictInfo(lk.mod_id, name, statement, confidence))
        else:
            name = _guess_name(plain, kw)
            key = (name, statement)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(ConflictInfo("", name, statement, confidence))

    if out:
        log.debug("从简介提取到 %d 条冲突声明", len(out))
    return out


# ------------------------------------------------------------------ 本地库对照

_NON_ALNUM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def _normalize(s: str) -> str:
    """归一化用于模糊匹配：小写 + 只留字母数字与 CJK。"""
    return _NON_ALNUM_RE.sub("", (s or "").lower())


def _fuzzy_title_match(title: str, name: str) -> bool:
    """标题与候选名称的宽松匹配（任一方向包含）。"""
    t, n = _normalize(title), _normalize(name)
    if len(n) < 2:
        return False
    return bool(t) and (n in t or t in n)


def check_installed_conflicts(library, conflicts) -> list[ConflictInfo]:
    """对照本地 mod 库，返回用户“已安装”的冲突项。

    :param library: ModLibrary（或同契约对象），需提供 .get(item_id) 与 .search(keyword=...)。
    :param conflicts: extract_conflicts 的结果。
    :return: 命中且已安装的 ConflictInfo 子集。
    """
    if not library or not conflicts:
        return []

    installed: list[ConflictInfo] = []
    for c in conflicts:
        try:
            if c.mod_id:
                rec = library.get(c.mod_id)
                if rec is not None and bool(getattr(rec, "installed", False)):
                    installed.append(c)
                    continue
            if c.name:
                for rec in library.search(keyword=c.name) or []:
                    if bool(getattr(rec, "installed", False)) and _fuzzy_title_match(
                        getattr(rec, "title", "") or "", c.name
                    ):
                        installed.append(c)
                        break
        except Exception as e:  # 库查询失败不应阻断冲突提示
            log.warning("检查已安装冲突失败（%s）：%s", c.mod_id or c.name, e)
    return installed
