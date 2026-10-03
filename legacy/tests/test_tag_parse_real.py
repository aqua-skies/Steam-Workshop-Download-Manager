"""浏览页标签解析实测（bug14 根因修复）。

用 Wayback Machine 抓取的三份真实浏览页 HTML 快照验证：
  - research/_browse_legacy.html  （2022 经典版）
  - research/_browse_2024.html     （2024 经典版）
  - research/_browse_snapshot.html （2026-09 React SSR 新版）
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from swdm.core.page_parser import (  # noqa: E402
    parse_available_tags,
    parse_available_tags_with_counts,
)

RESEARCH = os.path.join(ROOT, "research")
SNAPSHOTS = [
    ("2022 经典版", "_browse_legacy.html"),
    ("2024 经典版", "_browse_2024.html"),
    ("2026 React SSR", "_browse_snapshot.html"),
]

# 快照里的真实标签（人工核对，用于断言）
_EXPECTED = {
    "_browse_legacy.html": {"Gamemode", "Map"},
    "_browse_2024.html": {"Gamemode", "Map", "Addon"},
    "_browse_snapshot.html": {"Achievements", "Characters"},   # guide_tags
}

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

for label, fname in SNAPSHOTS:
    path = os.path.join(RESEARCH, fname)
    if not os.path.exists(path):
        check(f"{label}: 快照缺失", False, path)
        continue
    html = open(path, encoding="utf-8", errors="ignore").read()
    tags = parse_available_tags(html)
    counts = parse_available_tags_with_counts(html)
    exp = _EXPECTED[fname]
    got = set(tags)
    check(f"{label}: 解析出标签 ({len(tags)} 个)", len(tags) > 0,
          str(tags[:8]))
    check(f"{label}: 含已知真实标签", exp & got, str(sorted(exp - got)))
    check(f"{label}: 无 cookie/隐私/导航污染",
          not any(k in " ".join(tags).lower()
                  for k in ("cookie", "隐私", "商店", "客服", "注销")),
          str([t for t in tags if "cookie" in t.lower() or "隐私" in t][:5]))
    check(f"{label}: counts 与 tags 一致且计数为 0",
          [t for t, _ in counts] == tags and all(c == 0 for _, c in counts))

# 结构性单测：旧版表单控件
form_html = '''
<form name="TagsFilterForm" id="TagsFilterForm" action="https://steamcommunity.com/workshop/browse/">
  <select class="selectTagsFilter" name="requiredtags[]" onchange="FilterByTags();">
    <option value="-1">< none specified ></option>
    <option value="Addon"  >Addon</option>
    <option value="Save"  >Save</option>
  </select>
  <div class="filterOption"><label for="12091">
    <input onclick="IncludeTag( this );" type="checkbox" name="requiredtags[]" id="12091" value="Map" class="inputTagsFilter" />
    Map</label></div>
</form>
<a href="/about">关于</a><a href="/privacy">隐私政策</a><a href="/cookie">Cookie 设置</a>
'''
t = parse_available_tags(form_html)
check("旧版表单：取 checkbox+select value", set(t) == {"Addon", "Save", "Map"}, str(t))
check("旧版表单：链接文本不污染", "隐私政策" not in t and "Cookie 设置" not in t, str(t))

# 结构性单测：新版 SSR（用 json.dumps 双重序列化，避免手写转义出错）
import json as _json

_inner = {
    "declaredTags": {
        "guide_tags": [
            {"name": "#SharedFiles_GameGuides", "tags": [
                {"id": "13373", "name": "Achievements",
                 "display_name": "Achievements", "admin_only": False},
                {"id": "13088", "name": "Characters",
                 "display_name": "Characters", "admin_only": False},
            ]}
        ],
        "video_tags": [],
    }
}
_blob = _json.dumps(_json.dumps(_inner))
ssr_html = (
    '<script nonce="x">window.SSR={};window.SSR.loaderData = ['
    + _blob + '];</script>'
)
t2 = parse_available_tags(ssr_html)
check("新版 SSR：解析 declaredTags", set(t2) == {"Achievements", "Characters"}, str(t2))
check("新版 SSR：跳过 # 前缀占位分组名", "#SharedFiles_GameGuides" not in t2, str(t2))

# 空页面
check("空页面返回 []", parse_available_tags("") == [])
check("无标签页面返回 []", parse_available_tags("<html><body>nothing</body></html>") == [])

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
