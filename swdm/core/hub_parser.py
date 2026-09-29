"""新 Steam 之旅 hub 页解析器。

新 hub 页（/workshop/browse/?appid=X）把首屏数据以 React Query 脱水状态
内联在 HTML 里，其中 results 数组含每个物品的完整字段：
publishedfileid / title / preview_url / file_size / subscriptions / tags 等。
文本经过多层 JS+HTML 转义，统一用 unescape 还原后 json.loads。

经典页（旧卡片 HTML）对部分游戏已停止 SSR 渲染（返回 0 卡片），
本解析器用于补齐这些切换到新 hub 的游戏（Rust / DST / DBFZ 等）。
"""
from __future__ import annotations

import json
import re

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_BROWSE_URL = "https://steamcommunity.com/workshop/browse/"


def _unescape(s: str) -> str:
    """把多层转义（\\" 到 \\\\\\"）的 JSON 文本还原为可解析 JSON。"""
    prev = None
    while prev != s:
        prev = s
        s = s.replace('\\"', '"')
    return s


def _find_balanced_end(s: str, start: int, open_ch: str, close_ch: str) -> int | None:
    """从 start 的 open_ch 开始，跳过转义序列，数到匹配的 close_ch。"""
    depth = 0
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def extract_results(html: str) -> tuple[list[dict], int, int]:
    """从 hub 页提取 (物品原始字典列表, total_count, total_pages)。"""
    m = re.search(r'results\\+\\"\s*:\s*\[', html)
    if not m:
        m = re.search(r'"results"\s*:\s*\[', html)
    if not m:
        return [], 0, 0
    arr_start = html.find("[", m.start())
    if arr_start < 0:
        return [], 0, 0
    end = _find_balanced_end(html, arr_start, "[", "]")
    if end is None:
        return [], 0, 0
    try:
        results = json.loads(_unescape(html[arr_start : end + 1]))
    except json.JSONDecodeError:
        return [], 0, 0
    if not isinstance(results, list):
        return [], 0, 0

    def _num(key: str) -> int:
        mm = re.search(key + r'\\+\\"\s*:\s*(\d+)', html)
        if not mm:
            mm = re.search(rf'"{key}"\s*:\s*(\d+)', html)
        return int(mm.group(1)) if mm else 0

    return results, _num("total_count"), _num("total_pages")


def browse_hub(
    appid: str,
    page: int = 1,
    search_text: str = "",
    sort: str = "",
    required_tags: list[str] | None = None,
    language: str = "",
    timeout: int = 30,
    session: requests.Session | None = None,
) -> tuple[list[dict], int, int]:
    """通过新 hub 页获取物品原始字段。返回 (results, total_count, total_pages)。"""
    params: dict[str, object] = {"appid": appid, "p": max(1, page)}
    if search_text:
        params["searchtext"] = search_text
    if sort:
        params["actualsort"] = sort
    if required_tags:
        params["requiredtags[]"] = required_tags
    if language:
        params["l"] = language
    sess = session or requests.Session()
    try:
        r = sess.get(
            _BROWSE_URL, params=params, timeout=timeout, headers={"User-Agent": _UA}
        )
        r.raise_for_status()
        return extract_results(r.text)
    except requests.RequestException:
        return [], 0, 0


if __name__ == "__main__":
    for appid, name in [
        ("252490", "Rust"),
        ("258130", "DST"),
        ("821130", "DBFZ"),
        ("4000", "GMod"),
        ("107410", "Arma 3"),
        ("221100", "DayZ"),
    ]:
        results, total, pages = browse_hub(appid)
        print(f"{name} ({appid}): {len(results)} 物品, total={total}, pages={pages}")
        for it in results[:2]:
            print(f"    {it.get('publishedfileid')}  {it.get('title', '')[:36]}  "
                  f"size={it.get('file_size')} "
                  f"tags={[t.get('tag') for t in it.get('tags', [])][:3]}")
