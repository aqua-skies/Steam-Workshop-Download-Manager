"""抓取真实工坊详情页 HTML 存盘，分析 Required items 区块的实际结构。
带 429 退避；成功后把 HTML 写到 tests/fixtures/。
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
os.makedirs(FIX, exist_ok=True)

# 已知存在依赖的著名 mod（Rust 的常见依赖组合 / GMod 大型 addon）
CANDIDATES = [
    # Rust: "Juggernaut Supplies" 之类
    ("252490", "2551690809"),
    # GMod: 热门 addon
    ("4000", "3803871160"),
    # Cities: Skylines: 常见资产依赖
    ("255710", "3802011408"),
    # L4D2
    ("550", "3803864823"),
]


def get(url, params=None, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            r = sess.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"net error: {e}, retry")
            time.sleep(min(5 * attempt, 20))
            continue
        if r.status_code == 429:
            wait = min(45 * attempt, 180)
            print(f"429, waiting {wait}s (attempt {attempt}/{max_retries})")
            time.sleep(wait)
            continue
        return r
    return None


saved = 0
for appid, pid in CANDIDATES:
    if saved >= 2:
        break
    r = get("https://steamcommunity.com/sharedfiles/filedetails/", {"id": pid})
    if r is None:
        print(f"{pid}: failed")
        continue
    html = r.text
    path = os.path.join(FIX, f"detail_{appid}_{pid}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    has_ri = "requiredItem" in html
    has_req = bool(re.search(r"Required", html))
    print(f"{appid}/{pid}: saved {len(html)} bytes, requiredItem={has_ri}, Required={has_req}")
    saved += 1
    time.sleep(3)

print("saved pages:", saved)
sys.exit(0 if saved else 1)
