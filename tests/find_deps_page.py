"""定向找真正带 Required items 的详情页。
策略：抓"前置 mod"高发游戏的多个页面（Rust 插件、Cities 资产、GMod addon），
只要页面出现 requiredItem 立即存盘。
"""
from __future__ import annotations

import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
sess = requests.Session()
sess.headers["User-Agent"] = _UA

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def get(url, params=None, max_retries=4):
    for attempt in range(1, max_retries + 1):
        try:
            r = sess.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(min(5 * attempt, 20))
            continue
        if r.status_code == 429:
            wait = min(40 * attempt, 160)
            print(f"  429 wait {wait}s")
            time.sleep(wait)
            continue
        return r
    return None


def scrape_ids(appid, pages=2):
    out, seen = [], set()
    for p in range(1, pages + 1):
        r = get("https://steamcommunity.com/workshop/browse/",
                {"appid": appid, "p": p, "actualsort": "mostsubscribed"})
        if r is None:
            continue
        for pid in re.findall(r"sharedfiles/filedetails/\?id=(\d+)", r.text):
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
        time.sleep(3)
    return out


# Rust 插件/Oxide 生态依赖最常见
APPS = ["252490", "252490", "4000"]
found = 0
for appid in ["252490", "4000", "255710", "108600"]:
    ids = scrape_ids(appid)
    print(f"appid {appid}: {len(ids)} items")
    for pid in ids[:20]:
        r = get("https://steamcommunity.com/sharedfiles/filedetails/", {"id": pid})
        if r is None:
            continue
        html = r.text
        if "requiredItem" in html:
            path = os.path.join(FIX, f"deps_{appid}_{pid}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            m = re.search(r'requiredItem[^>]*>.{0,400}', html, re.DOTALL)
            print(f"  [FOUND] {pid} -> saved; snippet: {m.group(0)[:200] if m else '?'}")
            found += 1
            if found >= 2:
                print("done, found", found)
                sys.exit(0)
        time.sleep(3)
    if found:
        break

print("found with deps:", found)
sys.exit(0 if found else 1)
