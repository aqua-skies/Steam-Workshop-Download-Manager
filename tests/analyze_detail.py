"""分析保存的真实详情页 HTML：找 Required/依赖相关结构的真实锚点。"""
from __future__ import annotations

import os
import re
import sys

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

for fn in sorted(os.listdir(FIX)):
    if not fn.endswith(".html"):
        continue
    path = os.path.join(FIX, fn)
    html = open(path, encoding="utf-8").read()
    print(f"===== {fn} ({len(html)} bytes) =====")
    # 页面标题确认是真实页面
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    print("title:", (m.group(1).strip()[:60] if m else "?"))
    # 找所有含 require/depend/前置 的文本片段
    for pat in ["require", "Require", "depend", "Depend", "前置", "依赖", "prerequisite"]:
        hits = len(re.findall(pat, html))
        if hits:
            print(f"  pattern {pat!r}: {hits} hits")
            # 打印上下文
            for mm in list(re.finditer(pat, html))[:3]:
                ctx = html[max(0, mm.start() - 80): mm.end() + 80]
                ctx = re.sub(r"\s+", " ", ctx)
                print(f"     ctx: ...{ctx}...")
    # 看页面主要结构 class 名
    classes = re.findall(r'class="([^"]{3,40})"', html)
    interesting = [c for c in dict.fromkeys(classes)
                   if any(k in c.lower() for k in ["detail", "workshop", "section", "item", "body"])]
    print("  interesting classes:", interesting[:20])
