"""Registry of games that support the Steam Workshop (创意工坊): appid -> name.

Built-in list plus user customizations; unknown appids fall back to ``'AppID N'``.
Used by the game picker (游戏选择器) and for rendering library grouping (库按游戏分类).
"""
from __future__ import annotations

import json
import os

from .logger import get_logger
from .paths import DATA_DIR

log = get_logger("swdm.games")

# 内置的已知支持工坊的游戏（appid -> 名称）。这些通常允许匿名工坊下载。
BUILTIN_GAMES: dict[str, str] = {
    "4000": "Garry's Mod",
    "550": "Left 4 Dead 2",
    "440": "Team Fortress 2",
    "730": "Counter-Strike 2",
    "252490": "Rust",
    "221100": "DayZ",
    "107410": "Arma 3",
    "240": "Counter-Strike: Source",
    "340": "Half-Life 2: Deathmatch",
    "420": "Team Fortress 2 (Beta)",
    "17515": "Zombie Panic! Source",
    "17510": "Age of Chivalry",
    "17520": "Synergy",
    "17530": "Dystopia",
    "17550": "Empires",
    "17700": "Nuclear Dawn",
    "17710": "Dino D-Day",
    "17720": "Vampire Slayer",
    "17730": "The Hidden",
    "17740": "Pirates, Vikings and Knights II",
    "17750": "Age of Empires II",
    "215360": "Killing Floor 2",
    "1250": "Killing Floor",
    "232290": "The Elder Scrolls V: Skyrim",
    "72850": "Skyrim (Old)",
    "433150": "Stardew Valley",
    "594600": "Hollow Knight",
    "108600": "Project Zomboid",
    "600760": "The Escapists 2",
    "381210": "Dead by Daylight",
    "237990": "Space Engineers",
    "244850": "Medieval Engineers",
    "289070": "Sid Meier's Civilization VI",
    "9420": "Civ V",
    "8930": "Sid Meier's Civilization V",
    "204100": "The Elder Scrolls Online",
    "258130": "Don't Starve Together",
    "322330": "Don't Starve Together (Beta)",
    "219740": "Don't Starve",
    "1063730": "Tabletop Simulator",
    "286160": "Tabletop Simulator (Old)",
    "489830": "The Forest",
    "242760": "The Forest (DS)",
    "346110": "ARK: Survival Evolved",
    "821130": "DRAGON BALL FighterZ",
    "1510": "Dishonored",
    "206420": "Sleeping Dogs",
    "257510": "Ryse: Son of Rome",
    "268500": "XCOM 2",
    "8870": "BioShock Infinite",
    "480": "Garry's Mod (HL2)",
    "218620": "PAYDAY 2",
    "304930": "Unturned",
    "548430": "Deep Rock Galactic",
    "646910": "The Sapling",
    "50130": "Cities in Motion 2",
    "255710": "Cities: Skylines",
    "945360": "Among Us",
    "718670": "Cultist Simulator",
    "294100": "RimWorld",
    "288470": "100% Orange Juice",
}

CUSTOM_GAMES_FILE = os.path.join(DATA_DIR, "custom_games.json")


# 中文名 / 常见简称 → appid 的离线别名表。
# 用途：用户输入"饥荒"等中文名时，本地零网络即可命中（storesearch 的
# l=schinese 是权威中文源，别名表是离线/熔断兜底）。
# 键经 normalize_name 归一化后匹配（见 alias_appid）。
GAME_ALIASES: dict[str, str] = {
    # Don't Starve 家族
    "饥荒": "219740",
    "饥荒联机版": "322330",
    "dont starve": "219740",
    "dont starve together": "322330",
    # 常见简称/缩写
    "gmod": "4000",
    "盖瑞模组": "4000",
    "l4d2": "550",
    "求生之路2": "550",
    "tf2": "440",
    "军团要塞2": "440",
    "cs2": "730",
    "反恐精英2": "730",
    # 热门工坊游戏
    "环世界": "294100",
    "边缘世界": "294100",
    "rimworld": "294100",
    "方舟": "346110",
    "方舟生存进化": "346110",
    "ark": "346110",
    "泰拉瑞亚": "105600",
    "terraria": "105600",
    "星露谷物语": "413150",
    "stardew valley": "413150",
    "城市天际线": "255710",
    "天际线": "255710",
    "文明6": "289070",
    "席德梅尔的文明6": "289070",
    "上古卷轴5": "232290",
    "天际省": "232290",
    "skyrim": "232290",
    "七日杀": "251570",
    "群星": "281990",
    "stellaris": "281990",
    "武装突袭3": "107410",
    "arma3": "107410",
    "腐蚀": "252490",
    "rust": "252490",
    "深岩银河": "548430",
    "deep rock galactic": "548430",
    "drg": "548430",
    "太空工程师": "237990",
    "空间工程师": "237990",
    "绿色地狱": "816450",
    "森林": "489830",
    "the forest": "489830",
    "方桌模拟器": "1063730",
    "桌上模拟器": "1063730",
    "tabletop simulator": "1063730",
    "桌游模拟器": "1063730",
    "致命公司": "1966720",
    "雨中冒险2": "632360",
    "risk of rain 2": "632360",
    "杀戮尖塔": "646570",
    "slay the spire": "646570",
    "神界原罪2": "435150",
    "divinity original sin 2": "435150",
}

_GAME_ALIAS_ENTRIES = tuple(GAME_ALIASES.items())


def normalize_name(s) -> str:
    """游戏名归一化（匹配用，非显示用）：NFKC 全角→半角 + 小写 + 仅保留
    字母数字（去空格/撇号/冒号/百分号等）。例：'Don't Starve' → 'dontstarve'。"""
    if s is None:
        return ""
    import unicodedata

    s = unicodedata.normalize("NFKC", str(s)).lower()
    return "".join(ch for ch in s if ch.isalnum())


def alias_appid(text) -> str:
    """输入文本 → appid（本地别名表，零网络）。精确命中优先，子串包含其次。
    返回 '' 表示无命中；storesearch(l=schinese) 是权威中文源，本表作离线兜底。"""
    t = normalize_name(text)
    if not t or len(t) < 2:
        return ""
    for alias, appid in _GAME_ALIAS_ENTRIES:
        if normalize_name(alias) == t:
            return appid
    for alias, appid in _GAME_ALIAS_ENTRIES:
        a = normalize_name(alias)
        if t in a or a in t:
            return appid
    return ""


def list_builtin() -> list[dict]:
    """Built-in known workshop-supporting games, sorted by name."""
    return [{"appid": k, "name": v} for k, v in sorted(BUILTIN_GAMES.items(), key=lambda x: x[1].lower())]


def list_custom() -> list[dict]:
    """User-added custom games from disk (empty list on any read error)."""
    try:
        if os.path.exists(CUSTOM_GAMES_FILE):
            with open(CUSTOM_GAMES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:  # noqa: BLE001
        log.error("读取自定义游戏失败: %s", e)
    return []


def add_custom(appid: str, name: str) -> None:
    """Add or replace a custom game (keyed by appid) and persist to disk."""
    games = list_custom()
    games = [g for g in games if str(g.get("appid")) != str(appid)]
    games.append({"appid": str(appid), "name": name})
    try:
        with open(CUSTOM_GAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(games, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        log.error("保存自定义游戏失败: %s", e)


def remove_custom(appid: str) -> None:
    """Drop the custom game with this appid and persist the result."""
    games = [g for g in list_custom() if str(g.get("appid")) != str(appid)]
    try:
        with open(CUSTOM_GAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(games, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        log.error("删除自定义游戏失败: %s", e)


def all_games() -> list[dict]:
    """Merged built-in + custom games, deduped by appid and sorted by name."""
    seen = {}
    for g in list_builtin() + list_custom():
        seen[str(g["appid"])] = g["name"]
    return [{"appid": k, "name": v} for k, v in sorted(seen.items(), key=lambda x: x[1].lower())]


def game_name(appid: str | int) -> str:
    """Display name for an appid; unknown ids render as ``'AppID N'``."""
    appid = str(appid)
    for g in all_games():
        if g["appid"] == appid:
            return g["name"]
    return f"AppID {appid}"
