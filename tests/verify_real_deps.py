"""用真实保存的依赖页面验证解析器，并输出真实结构供正则校准。"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.deps_parser import parse_required_items, parse_required_items_robust  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
pages = sorted(f for f in os.listdir(FIX) if f.startswith("deps_"))
print("saved dep pages:", pages)

for fn in pages:
    html = open(os.path.join(FIX, fn), encoding="utf-8").read()
    print(f"===== {fn} ({len(html)} bytes) =====")
    # 真实结构片段
    m = re.search(r'requiredItemsContainer[^>]*id="RequiredItems".{0,600}', html, re.DOTALL)
    if m:
        print("  REAL STRUCTURE (first 600 chars):")
        print("   ", re.sub(r"\s+", " ", m.group(0))[:500])
    ids = parse_required_items(html)
    ids_robust = parse_required_items_robust(html)
    print(f"  parse_required_items: {ids}")
    print(f"  robust:               {ids_robust}")
