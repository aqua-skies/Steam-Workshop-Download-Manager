"""真实页面依赖解析验证：找一个确实有 Required items 的工坊物品。

策略：从各游戏工坊浏览页抓物品 id，逐个检查详情页是否含 requiredItem 区块。
带节流与重试，遇到 429 按指数退避等待。
"""
from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from swdm.core.deps_parser import parse_required_items_robust  # noqa: E402

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
sess = requests.Session()
sess.headers["User-Agent"] = _UA


def get(url: str, params=None, max_retries: int = 4):
    """GET with 429 backoff."""
    attempt = 0
    while True:
        attempt += 1
        try:
            r = sess.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  net error attempt {attempt}: {e}")
            time.sleep(min(5 * attempt, 20))
            continue
        if r.status_code == 429:
            wait = min(30 * attempt, 120)
            print(f"  429, waiting {wait}s (attempt {attempt})")
            time.sleep(wait)
            if attempt > max_retries:
                return None
            continue
        return r


# Rust / Cities / Project Zomboid 依赖高发
APPS = ["252490", "255710", "108600", "4000", "221100"]
checked = 0
found = []

for appid in APPS:
    print(f"=== appid {appid} ===")
    r = get("https://steamcommunity.com/workshop/browse/", {"appid": appid})
    if r is None:
        print("  browse failed, skip")
        continue
    ids = []
    seen = set()
    for pid in re.findall(r"sharedfiles/filedetails/\?id=(\d+)", r.text):
        if pid not in seen:
            seen.add(pid)
            ids.append(pid)
    print(f"  {len(ids)} items on page 1")
    for pid in ids[:12]:
        time.sleep(2.5)  # 节流
        d = get("https://steamcommunity.com/sharedfiles/filedetails/", {"id": pid})
        if d is None:
            continue
        checked += 1
        deps = parse_required_items_robust(d.text)
        title_m = re.search(r'<div class="workshopItemTitle">([^<]+)</div>', d.text)
        title = title_m.group(1)[:40] if title_m else "?"
        if deps:
            print(f"  [FOUND] {pid} {title!r} -> {len(deps)} deps: {deps[:5]}")
            found.append((appid, pid, deps))
            if len(found) >= 2:
                print(f"\nchecked {checked} pages, found {len(found)} with deps")
                sys.exit(0)
        else:
            print(f"  [--] {pid} {title!r} no deps")
    if found:
        break

print(f"\nchecked {checked} detail pages, found with deps: {len(found)}")
for appid, pid, deps in found:
    print(f"  {appid}/{pid}: {deps}")
sys.exit(0 if found else 1)
