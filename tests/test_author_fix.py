"""作者名修复回归（bug3）：用真实抓取页面片段实证过的结构验证。

diag 已证实：真实页每张卡带 "作者：<昵称>" 文本，即使作者链接是
profiles/<steamid>。旧正则只认 id/ 链接导致这类卡片 creator_name 空。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_author_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from html import unescape  # noqa: E402

from swdm.core.steam_api import SteamAPI  # noqa: E402

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

api = SteamAPI()

# 真实页面结构：卡片 + 作者文本 + myworkshopfiles 链接（profiles 版）
CARD_TMPL = (
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id={pid}"'
    ' class="x"><img src="https://x/{pid}.jpg" alt="{title}"/></a>'
    '<div class="meta">'
    '<a href="https://steamcommunity.com/profiles/{steamid}/myworkshopfiles/">作者主页</a>'
    '<div class="authorLine">作者：{author}</div>'
    '</div>'
)

def build_html(cards):
    return "".join(CARD_TMPL.format(**c) for c in cards)

# case 1: profiles 链接 + 作者文本（真实页最常见，旧代码抓不到名字）
html1 = build_html([
    {"pid": "3805670012", "title": "Angry Birds", "steamid": "76561198146839798",
     "author": "Balamut"},
    {"pid": "3804541133", "title": "gm_combine", "steamid": "76561199000000001",
     "author": "woop woop (rafi0101)"},
])
items = api._parse_cards(html1)
check("profiles 卡片数 2", len(items) == 2, str(len(items)))
check("卡片1 作者=Balamut",
      items[0].creator_name == "Balamut", repr(items[0].creator_name))
check("卡片1 creator=steamid",
      items[0].creator == "76561198146839798", repr(items[0].creator))
check("卡片2 作者带括号",
      items[1].creator_name == "woop woop (rafi0101)",
      repr(items[1].creator_name))

# case 2: 只有 id/ 自定义昵称链接，无作者文本（旧页兼容）
html2 = (
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=111"'
    ' class="x"><img src="https://x/111.jpg" alt="Mod A"/></a>'
    '<a href="https://steamcommunity.com/id/Rafi00101/myworkshopfiles/">作者</a>'
)
items2 = api._parse_cards(html2)
check("id 链接兜底有效",
      items2[0].creator_name == "Rafi00101", repr(items2[0].creator_name))

# case 3: HTML 实体作者名（真实页有 &#x27; 撇号）
html3 = (
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=222"'
    ' class="x"><img src="https://x/222.jpg" alt="Mod B"/></a>'
    '<div>作者：Kirbin&#x27;s Stuff</div>'
)
items3 = api._parse_cards(html3)
check("HTML 实体作者名解码",
      items3[0].creator_name == "Kirbin's Stuff", repr(items3[0].creator_name))

# case 4: 英文页 Author: 前缀
html4 = (
    '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=333"'
    ' class="x"><img src="https://x/333.jpg" alt="Mod C"/></a>'
    '<div>Author: MasterMellow</div>'
)
items4 = api._parse_cards(html4)
check("英文页 Author: 前缀",
      items4[0].creator_name == "MasterMellow", repr(items4[0].creator_name))

# case 5: 卡片作者名缺失时回退 steamid（不显示空）
check("卡片标题解析",
      items3[0].title == "Mod B", repr(items3[0].title))

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
