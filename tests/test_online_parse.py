"""联网实测：标签拉取 / 简介 / 评论 / 依赖（302 恢复 steamcommunity 后）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truststore  # noqa: E402

truststore.inject_into_ssl()

from swdm.core import SteamAPI, RateLimitError, ensure_dirs  # noqa: E402
from swdm.core.page_parser import (  # noqa: E402
    parse_available_tags,
    parse_comments,
    parse_description,
)

ok = True
skipped = []
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

api = SteamAPI()

# 1) GMod 浏览页标签
html = api._community_get("/workshop/browse/", {"appid": "4000"})
tags = parse_available_tags(html)
check("GMod 可用标签数 > 0", len(tags) > 0, f"{len(tags)} 个: {tags[:6]}")

# 2) Cultist Simulator 标签
html2 = api._community_get("/workshop/browse/", {"appid": "718670"})
tags2 = parse_available_tags(html2)
check("Cultist 标签数 > 0", len(tags2) > 0, f"{len(tags2)} 个: {tags2[:5]}")

# 3) 详情页简介 + 评论（GMod 有依赖的物品）——限流时跳过
try:
    dhtml = api._community_get("/sharedfiles/filedetails/", {"id": "3805232163"})
except RateLimitError:
    dhtml = ""
    skipped.append("详情页（IP 限流，解析已由真实 fixtures 验证）")

if dhtml:
    desc = parse_description(dhtml)
    check("简介非空", len(desc) > 50, f"{len(desc)} 字符: {desc[:40]}…")
    comments = parse_comments(dhtml)
    check("评论数 > 0", len(comments) > 0,
          f"{len(comments)} 条，首条: {comments[0]['author'] if comments else ''}")
    # 4) 依赖（该物品有 VJ Base + SheepSquatch）
    from swdm.core.deps_parser import parse_required_items_with_titles  # noqa: E402

    deps = parse_required_items_with_titles(dhtml)
    check("依赖数 >= 2", len(deps) >= 2, str(deps))
else:
    print("[SKIP] 简介 / 评论 / 依赖（详情页限流）")

if skipped:
    print("跳过:", "; ".join(skipped))
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
