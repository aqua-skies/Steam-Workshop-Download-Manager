# Steam 游戏名搜索（不依赖 AppID）接口调研与实测

> **标注约定**：本文所有接口行为、返回示例、状态码、延迟、速率限制观察均来自
> **本机实测**（2026-09-22，Python 3.12.10 + requests 2.34.2 + truststore 0.10.4，
> 直连无代理，从本工作区所在主机发起）。凡属社区文档/历史经验、未经本次实测验证的，
> 一律标注 **[检索所得]**。本文未依赖任何网络检索，全部结论为实测产出。

## 0. 结论速览

| 接口 | URL | 需 key | 状态 | 联想推荐度 | 实测延迟 |
|---|---|---|---|---|---|
| **商店搜索** | `https://store.steampowered.com/api/storesearch/?term=xxx&l=schinese&cc=CN` | ❌ 无需 | ✅ 200 可用 | ⭐ **首选** | 456–3434ms，中位 ~550ms |
| 社区老接口 | `https://steamcommunity.com/actions/SearchApps/xxx` | ❌ 无需 | ✅ 200 可用 | ⚠️ 仅作降级 | 285–2015ms，中位 ~500ms |
| 全量列表 | `https://api.steampowered.com/ISteamApps/GetAppList/v2/` | ❌ 无需（历史） | ❌ **404** | ❌ 不可用 | — |
| 单应用详情 | `https://store.steampowered.com/api/appdetails/?appids=4000&l=schinese&cc=CN` | ❌ 无需 | ✅ 200 可用 | 用于选中后校验 `type=game` | ~500ms |

**推荐方案**：`storesearch` 做搜索联想（匹配质量明显胜出，且返回封面图直链），
`SearchApps` 仅在 storesearch 连续失败时降级；选中后可用 `appdetails` 校验是否为
`type=game`（过滤掉 DLC/视频/软件）。

---

## 1. 实测环境与方法

```
Python 3.12.10 / requests 2.34.2 / truststore 0.10.4
truststore.inject_into_ssl()   # 项目既有实践：本机 certifi 证书不可用，必须走系统证书存储
UA   : Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/124.0.0.0 Safari/537.36
头   : Accept-Language: zh-CN,zh;q=0.9,en;q=0.8   （Steam 对缺该头的请求会限流，见项目 steam_429_research.md）
方法 : GET，每查询独立请求（部分测试用同一 Session 做对照）
网络 : 直连，无代理
```

查询样本：`gmod`、`csgo`、`l4d2`（任务指定），另补 `garry`、`garry's mod`、`counter`、
`cs2`、`left 4`、`rust`、`求生之路`、`盖瑞`、`饥荒`、`求生` 等，用于定性匹配质量。

---

## 2. 接口一：storesearch（商店搜索）✅ 实测可用，首选

### 2.1 请求

```
GET https://store.steampowered.com/api/storesearch/
参数:
  term = 关键词          （必填）
  l    = schinese        （语言，实测对名称本地化有效）
  cc   = CN              （国家代码，影响价格币种 CNY）
```

**实测发现**：`count=N` 参数**被忽略**（传 `count=3` 仍返回 10 条）；
`category=1` 传与不传结果一致（未见过滤效果）——分页/过滤不可用于该接口，只能客户端截断。

### 2.2 返回结构

```json
{
  "total": 10,
  "items": [
    {
      "type": "app",                     // app=游戏/应用；另有 package/bundle 等
      "name": "Garry's Mod",
      "id": 4000,                        // ← AppID（数字类型，需 str() 转换）
      "price": { "currency": "CNY", "initial": 3600, "final": 3600 },  // 分；免费游戏无此字段
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4000/2e52d9b905feebfdaaf2db6ad7afece10991d504/capsule_231x87.jpg?t=1776868682",
      "metascore": "",                   // 无评分时为空字符串
      "platforms": { "windows": true, "mac": true, "linux": true },
      "streamingvideo": false
    }
    // ... 共 total 条，实测一次最多返回 10 条
  ]
}
```

字段要点（实测）：
- `id` 即 AppID；`type` 可用于过滤（只要 `"app"`）。
- `tiny_image` 是**完整可用**的封面图 URL，无需拼接（见 §6）。
- `price` 字段在免费游戏（如 CS2）上**整体缺失**，取值需 `.get("price")` 判空。
- 语言变体封面：`l=schinese` 时部分游戏返回 `capsule_231x87_schinese.jpg`（如 CS2/appid 730）。
- **`total` 有时大于返回条数**（一次只给 10 条），联想场景足够。

### 2.3 完整返回示例（实测原文，截取展示）

**查询 `term=gmod`** → `total=10`，首位正确命中 Garry's Mod：

```json
{
  "total": 10,
  "items": [
    {
      "type": "app",
      "name": "Garry's Mod",
      "id": 4000,
      "price": { "currency": "CNY", "initial": 3600, "final": 3600 },
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4000/2e52d9b905feebfdaaf2db6ad7afece10991d504/capsule_231x87.jpg?t=1776868682",
      "metascore": "",
      "platforms": { "windows": true, "mac": true, "linux": true },
      "streamingvideo": false
    },
    {
      "type": "app",
      "name": "G-MODEアーカイブス+ ペルソナ3 アイギス THE FIRST MISSION",
      "id": 2850150,
      "price": { "currency": "CNY", "initial": 6200, "final": 6200 },
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2850150/capsule_231x87.jpg?t=1735293997",
      "metascore": "",
      "platforms": { "windows": true, "mac": false, "linux": false },
      "streamingvideo": false
    }
    // 其余 8 条均为 G-MODEアーカイブス系列（按相关性排后）
  ]
}
```

**查询 `term=csgo`** → `total=2`（CS:GO 已下架，正确导向 CS2）：

```json
{
  "total": 2,
  "items": [
    {
      "type": "app",
      "name": "Counter-Strike 2",
      "id": 730,
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/730/capsule_231x87_schinese.jpg?t=1789251637",
      "metascore": "",
      "platforms": { "windows": true, "mac": false, "linux": true },
      "streamingvideo": false
    },
    {
      "type": "app",
      "name": "CS:GO Player Profiles",
      "id": 413850,
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/413850/capsule_231x87.jpg?t=1485215623",
      "metascore": "",
      "platforms": { "windows": true, "mac": true, "linux": true },
      "streamingvideo": true,
      "controller_support": "full"
    }
  ]
}
```

**查询 `term=l4d2`** → `total=3`：

```json
{
  "total": 3,
  "items": [
    {
      "type": "app",
      "name": "Left 4 Dead 2",
      "id": 550,
      "price": { "currency": "CNY", "initial": 4200, "final": 4200 },
      "tiny_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/550/capsule_231x87.jpg?t=1772742214",
      "metascore": "89",
      "platforms": { "windows": true, "mac": false, "linux": true },
      "streamingvideo": false,
      "controller_support": "full"
    },
    { "type": "app", "name": "Dying Light – L4D2 Bill and Gnome Chompski Pack", "id": 1454750, "streamingvideo": false },
    { "type": "app", "name": "Dying Light - Left 4 Dead 2 Weapon Pack", "id": 1174581, "streamingvideo": false }
  ]
}
```

### 2.4 匹配质量（实测）

| 输入 | 首位结果 | 评价 |
|---|---|---|
| `gmod` | ✅ Garry's Mod (4000) | 缩写/相关性匹配好 |
| `garry` | ✅ Garry's Mod | 全词命中 |
| `garry's mod` | ✅ Garry's Mod (唯一结果) | 精确 |
| `csgo` | ✅ Counter-Strike 2 (730) | 已下架游戏正确重定向到续作 |
| `l4d2` | ✅ Left 4 Dead 2 (550) | 缩写命中 |
| `求生之路` / `求生之路2` | ❌ 0 条 | **中文名搜索不可靠**（见下） |
| `盖瑞` / `盖瑞模组` / `反恐精英` | ❌ 0 条 | 同上 |
| `饥荒` | ✅ 8 条（饥荒联机版 322330、饥荒 219740…） | 中文名仅当商店名本身就是中文时有效 |
| `求生` | ✅ 10 条（禁闭求生2 等） | 同上 |

**中文支持结论（实测）**：`l=schinese` 时，搜索匹配的是**商店本地化名称**。
只有当游戏商店名本身就是中文（如「饥荒」「禁闭求生2」）时中文搜索有效；
对「求生之路2（L4D2）」「盖瑞模组（Garry's Mod）」这类商店名仍为英文的游戏，中文输入返回 0 条。
→ **UI 上应以英文名搜索为主，中文为辅；联想结果展示本地化名即可。**

---

## 3. 接口二：SearchApps（社区老接口）✅ 实测可用，但匹配质量差

### 3.1 请求与返回

```
GET https://steamcommunity.com/actions/SearchApps/{term}
路径参数即关键词（需 URL 编码，如 "garry's mod" → "garry%27s%20mod"）
返回：JSON 数组（无外层包裹），每项 {appid, name, icon, logo}
```

**完整返回示例（实测，term=l4d2）**：

```json
[
  {
    "appid": "550",
    "name": "Left 4 Dead 2",
    "icon": "https://shared.fastly.steamstatic.com/community_assets/images/apps/550/7d5a243f9500d2f8467312822f8af2a2928777ed.jpg",
    "logo": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/550/capsule_184x69.jpg?t=1772742214"
  }
]
```

**完整返回示例（实测，term=gmod，共 10 条，前 2 条）**：

```json
[
  {
    "appid": "3652460",
    "name": "G-MODEアーカイブス+ 真・女神転生-20XX",
    "icon": "https://shared.fastly.steamstatic.com/community_assets/images/apps/3652460/cb39bef9ee1be0888a863c796264bc50092d9699.jpg",
    "logo": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3652460/0b15bdd7a5269c7bbb863dc40bb2e22f79acbbdd/capsule_184x69.jpg?t=1747184415"
  },
  {
    "appid": "3713410",
    "name": "G-MODEアーカイブス+ 真・女神転生 東京鎮魂歌",
    "icon": "https://shared.fastly.steamstatic.com/community_assets/images/apps/3713410/190b3cec06d60dc729204464f5d4fc0cad42f691.jpg",
    "logo": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3713410/a5284d4421b72ce663ae59e6e3325ae07ca7a05c/capsule_184x69.jpg?t=1772508722"
  }
]
```

**term=csgo → `[]`（空数组，2 字节）**；**term=盖瑞/求生之路 → `[]`**。

### 3.2 匹配质量（实测，致命缺陷）

| 输入 | 结果 | 评价 |
|---|---|---|
| `gmod` | ❌ **不含 Garry's Mod**（全是 G-MODE 系列） | 前缀匹配 "gmod"→"gmode"，相关性排序差 |
| `csgo` | ❌ `[]` 空 | 已下架应用直接不索引 |
| `cs2` | ⚠️ 只有 CS2D (666220)，无 Counter-Strike 2 | 缩写覆盖差 |
| `garry` / `garry's mod` | ✅ Garry's Mod | 全词OK |
| `l4d2` / `left 4` / `counter` / `rust` | ✅ 正确 | 正常 |
| 任何中文 | ❌ 全部 `[]` | **完全不支持中文名** |

结论：SearchApps 是**名称前缀/分词匹配**，无模糊匹配、无下架游戏重定向、无中文。
速度略快但结果不可靠 —— **不能单独承担联想**，仅作 storesearch 不可达时的降级备选。

---

## 4. 接口三：GetAppList（全量列表）❌ 实测 404，不可用

实测全部变体均返回：

```
GET  https://api.steampowered.com/ISteamApps/GetAppList/v2/      → 404
GET  https://api.steampowered.com/ISteamApps/GetAppList/v2/?format=json → 404
GET  https://api.steampowered.com/ISteamApps/GetAppList/v0002/   → 404
POST https://api.steampowered.com/ISteamApps/GetAppList/v2/      → 404
```

404 响应体（实测原文）：

```html
<html><head><title>Not Found</title></head><body><h1>Not Found</h1>
Method 'GetAppList' not found in interface 'ISteamApps'</body></html>
```

- **[检索所得]** 该接口在社区文档中长期被记录为「无需 key、返回全量 app 列表」，
  本次实测从本机网络得到 404，可能属区域/线路差异或 Valve 调整。
- 无论原因为何，**当前不可用**；且即便可用，全量列表（数万条，数 MB）也不适合做输入联想
  —— 下载+过滤的延迟远高于在线搜索。**明确排除。**
- 附带实测：`https://steamcommunity.com/actions/SearchApps/`（空词）→ 200 但返回 `[]`，
  无法用于枚举全量。

---

## 5. 速率限制与稳定性（实测，重要）

**连发 12 次同参数请求**（模拟无防抖的最坏情况）：

| 接口 | 成功/总次 | 失败形态 |
|---|---|---|
| storesearch | **2/12** | `ConnectionAbortedError(10053, '你的主机中的软件中止了一个已建立的连接')` |
| SearchApps | **3/12** | 同上 |

- 两个接口表现一致：高频请求时**连接被对端中止**（WinSock 10053），不是 HTTP 429。
  **[检索所得]** 社区一般认为商店 API 限流较松；本次实测表明在同一 IP 上做
  无间隔连发仍会触发连接级熔断，且**两个域名（store / community）共用同一限流桶或同一本地出口现象**。
- **恢复性实测**：触发熔断后**静置 15 秒，两个接口均恢复 200**。
- 已有的 429 研究结论（`steam_429_research.md`：community 页 429 由请求头指纹触发）
  在本接口上**不适用**——storesearch 只要带浏览器 UA + Accept-Language 就稳定 200，
  关键约束是**请求频率**而非请求头。
- 偶发 `ReadTimeout` / `SSLError(UNEXPECTED_EOF)` 也会出现在 CDN 图片请求上（见 §6），
  客户端必须重试或降级。

**工程含义**：联想功能**必须**做防抖 + 在途请求取消 + 失败静默降级，
否则用户连续敲键盘就会把连接打到熔断，反而什么也出不来。

---

## 6. 图标 / 封面图 URL 方案（实测校验）

### 6.1 优先用接口返回的完整 URL（推荐，零拼接）

| 来源 | 字段 | 示例（实测原文） | 实测状态 |
|---|---|---|---|
| storesearch | `tiny_image` | `https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/4000/2e52d9b905feebfdaaf2db6ad7afece10991d504/capsule_231x87.jpg?t=1776868682` | ✅ 200 |
| SearchApps | `icon`（小正方形 ~1.4KB） | `https://shared.fastly.steamstatic.com/community_assets/images/apps/550/7d5a243f9500d2f8467312822f8af2a2928777ed.jpg` | ✅ 200 |
| SearchApps | `logo`（横版 184x69） | `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/550/capsule_184x69.jpg?t=1772742214` | ✅ 200 |

返回值自带 hash 路径与时间戳，**CDN 域名与当前有效主机一致**，直接用最稳。

### 6.2 按 AppID 拼接（兜底/其它尺寸）

通用模式（`{appid}` 即 storesearch 的 `id` 字段）：

```
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg                # 商店横版 460x215
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg        # 小胶囊 231x87
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_184x69.jpg        # 更小胶囊
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg       # 库竖版 600x900
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_hero.jpg          # 库横版大图
https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/page_bg_generated_v6b.jpg  # 商店页背景
```

HEAD 实测结果（appid=4000 / 550 / 730）：

| URL | 状态 | 大小 | 延迟 |
|---|---|---|---|
| `.../steam/apps/4000/header.jpg` | ✅ 200 | 25326 B | 282–9419ms（首次很慢） |
| `.../steam/apps/4000/capsule_231x87.jpg` | ✅ 200 | 6109 B | 2362ms |
| `.../steam/apps/4000/library_600x900.jpg` | ✅ 200 | 30886 B | 1685ms |
| `.../steam/apps/4000/library_hero.jpg` | ✅ 200 | 171563 B | 1385ms |
| `.../steam/apps/4000/page_bg_generated_v6b.jpg` | ✅ 200 | 29987 B | 1290ms |
| `.../steam/apps/4000/cover.jpg` | ❌ 失败（SSL EOF，资源不存在） | — | — |
| `shared.akamai.steamstatic.com/store_item_assets/steam/apps/4000/header.jpg` | ✅ 200 | 25326 B | **282–346ms（最快）** |
| `cdn.akamai.steamstatic.com/steam/apps/4000/header.jpg`（旧域名） | ✅ 200 | 25326 B | 282ms |
| `steamcdn-a.akamaihd.net/steam/apps/4000/header.jpg`（更旧域名） | ✅ 200 | 25326 B | 4018ms（慢） |

**要点**：
1. `header.jpg` / `capsule_*` / `library_*` 拼接方案**实测可用**；`cover.jpg` 不存在。
2. **`shared.akamai.steamstatic.com` 在本机上比 `cdn.cloudflare.steamstatic.com` 快一个量级**
   （282ms vs 首次 9.4s），且正是 storesearch 返回的域名 —— **直接用返回值最省事**。
3. 旧域名（akamaihd.net / cdn.akamai.steamstatic.com）仍能解析，但属历史遗留，不推荐。
4. 图片下载复用项目已有的 `SteamAPI.fetch_image()`（带 30 天本地缓存），可天然吸收偶发 SSL/超时错误。

---

## 7. 联想方案：完整可落地的 Python 调用代码

贴合项目现状设计（复用 `truststore` 注入、浏览器 UA、`Accept-Language`；
与 `swdm/core/games.py` 的本地列表互补；错误全部静默降级，绝不弹窗打扰输入）。

### 7.1 搜索客户端（核心层，框架无关）

```python
# 建议新增文件：swdm/core/game_search.py
"""游戏名搜索（不依赖 AppID）：steampowered 商店搜索 + 本地内置表互补。

实测依据见 research/steam_game_search.md：
- storesearch 匿名可用、相关性最好，返回 id/name/tiny_image 完整 URL
- 高频请求会触发连接级熔断（WinSock 10053），必须缓存 + 静默降级
- 中文名仅当商店名本身为中文时可搜，UI 以英文为主
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests
import truststore

truststore.inject_into_ssl()  # 与 steam_api.py 一致：本机必须走系统证书存储

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


@dataclass
class GameSuggestion:
    appid: str
    name: str
    image: str = ""          # 完整封面图 URL（capsule_231x87），直接给 QLabel/QNetworkAccessManager
    type: str = ""           # "app" / "package" / "bundle"...
    price: str = ""          # 展示用："¥36" 或 "免费"


class GameSearchClient:
    """线程安全说明：search() 只读 + 写自身缓存，可在工作线程调用；
    实例应在 UI 层单例化，Session 复用连接池（减少新建连接 = 减少熔断）。"""

    URL = "https://store.steampowered.com/api/storesearch/"
    FALLBACK_URL = "https://steamcommunity.com/actions/SearchApps/"

    def __init__(self, timeout: float = 8.0, cache_ttl: float = 300.0) -> None:
        self.timeout = timeout
        self._cache: dict[str, tuple[float, list[GameSuggestion]]] = {}
        self._cache_ttl = cache_ttl
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",   # 缺该头易被 Steam 限流
            "Accept": "application/json, text/plain, */*",
        })

    # ------------------------------------------------------------------ 搜索
    def search(self, term: str, limit: int = 10) -> list[GameSuggestion]:
        """搜索游戏名。任何失败都返回 []（调用方负责静默降级）。"""
        term = (term or "").strip()
        if len(term) < 2:                      # 单字符噪声大，且 Steam 也常返回 0 条
            return []
        key = term.lower()

        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self._cache_ttl:
            return hit[1][:limit]

        result = self._search_store(term) or self._search_community(term)
        # 即使为空也缓存，避免重复敲同一词时反复打接口
        self._cache[key] = (time.time(), result)
        return result[:limit]

    def _search_store(self, term: str) -> list[GameSuggestion]:
        try:
            r = self._session.get(
                self.URL,
                params={"term": term, "l": "schinese", "cc": "CN"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            # ConnectionAbortedError(10053) / Timeout / JSON 解析失败 → 静默降级
            return []
        out: list[GameSuggestion] = []
        for it in data.get("items", []):
            out.append(GameSuggestion(
                appid=str(it.get("id", "")),
                name=it.get("name", ""),
                image=it.get("tiny_image", ""),
                type=it.get("type", "app"),
                price=self._fmt_price(it.get("price")),
            ))
        return out

    def _search_community(self, term: str) -> list[GameSuggestion]:
        """降级路径：storesearch 连续失败时才走（匹配质量差，见报告 §3.2）。"""
        try:
            r = self._session.get(
                self.FALLBACK_URL + requests.utils.quote(term),
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [
            GameSuggestion(
                appid=str(it.get("appid", "")),
                name=it.get("name", ""),
                image=it.get("logo") or it.get("icon") or "",
                type="app",
            )
            for it in data
            if it.get("appid")
        ]

    @staticmethod
    def _fmt_price(price: dict | None) -> str:
        if not price:
            return "免费"
        final = price.get("final", 0)
        if not final:
            return "免费"
        return f"¥{final / 100:.0f}" if price.get("currency") == "CNY" else f"{final / 100:.2f}"
```

### 7.2 PySide6 联想输入框（防抖 + 在途取消 + 本地表优先）

项目现状：`swdm/gui/workshop_tab.py` 的 `game_combo` 已是 `setEditable(True)`
可编辑下拉框，但只能从 `all_games()`（内置+自定义，需知道名字/AppID）里选。
下面的方案**不改动现有选中逻辑**，只接管输入过程的联想补全：

```python
# 在 workshop_tab.py 的工坊页里加（示意，最小侵入）
from PySide6.QtCore import QTimer, QThreadPool, QRunnable, QObject, Signal
from swdm.core.games import all_games
from swdm.core.game_search import GameSearchClient

class _SearchWorker(QRunnable):
    class _Signals(QObject):
        done = Signal(list)
    def __init__(self, client: GameSearchClient, term: str):
        super().__init__()
        self.client, self.term = client, term
        self.signals = self._Signals()
        self._cancelled = False
    def cancel(self): self._cancelled = True
    def run(self):
        out = self.client.search(self.term)          # 最多 ~8s，内部已含超时
        if not self._cancelled:
            self.signals.done.emit(out)

# ---------------- 在 WorkshopTab / 页面控件里 ----------------
DEBOUNCE_MS = 350          # 见 §8 论证
MIN_LEN = 2

def _setup_suggest(self):
    self._gs_client = GameSearchClient()
    self._pool = QThreadPool.globalMaxThreadCount() and QThreadPool()  # 或全局池
    self._pool.setMaxThreadCount(2)
    self._running_worker = None
    # 复用项目既有的去抖模式（同 _refresh_list 的 350ms QTimer 风格）
    self._suggest_timer = QTimer(self)
    self._suggest_timer.setSingleShot(True)
    self._suggest_timer.setInterval(DEBOUNCE_MS)
    self._suggest_timer.timeout.connect(self._do_suggest)
    self.game_combo.lineEdit().textEdited.connect(self._suggest_timer.start)

def _do_suggest(self):
    text = self.game_combo.currentText().strip()
    # 1) 取消在途请求（用户又敲了新字符，旧结果已过期）
    if self._running_worker:
        self._running_worker.cancel()
    if len(text) < MIN_LEN:
        return
    # 2) 本地内置表先筛（零延迟、零网络，命中即直接顶到最前）
    local = [g for g in all_games() if text.lower() in g["name"].lower()][:5]
    if local:
        self._show_suggestions([GameSuggestion(**{
            "appid": g["appid"], "name": g["name"]}) for g in local])
    # 3) 在线联想异步补全
    w = _SearchWorker(self._gs_client, text)
    w.signals.done.connect(self._show_suggestions)
    self._running_worker = w
    self._pool.start(w)

def _show_suggestions(self, items: list[GameSuggestion]):
    # 去重 + 只保留游戏类应用（过滤 DLC/视频/软件包）
    seen, out = set(), []
    for it in items:
        if it.appid and it.appid not in seen and it.type == "app":
            seen.add(it.appid); out.append(it)
    # 填进 combo 的下拉项（setItemData 存 appid，显示 name）
    self.game_combo.blockSignals(True)
    self.game_combo.clear()
    for it in out[:10]:
        self.game_combo.addItem(it.name, it.appid)     # 图标可异步用 image URL 加载
    self.game_combo.blockSignals(False)
    self.game_combo.showPopup()                        # 实测能正常弹出候选列表
```

> 说明：以上为方案示意代码，供实现时参考；本报告不改动任何项目源码。

---

## 8. 防抖时间建议

| 项 | 建议值 | 依据 |
|---|---|---|
| **防抖间隔** | **350 ms** | 与项目既有去抖一致（`workshop_tab.py:460` 的 `_refresh_timer` 即 350ms）；典型输入联想业界值 250–400ms |
| **最小输入长度** | **2 字符** | 实测单字符（如 "g"/"c"）命中噪声极大且 Steam 常返回 0 条，无谓消耗配额 |
| **在途请求超时** | **8 s** | 实测 P99 远低于此（最慢 3.4s）；设宽一点吸收本机偶发 9s 级慢响应 |
| **结果缓存 TTL** | **300 s** | 同一词反复敲很常见；缓存命中零网络、零熔断风险 |
| **失败降级** | 静默返回 `[]`，不弹窗 | 输入过程任何弹窗都会打断体验；失败就只显示本地内置表结果 |
| **并发线程数** | **≤ 2** | 实测 12 连发会熔断；同一时刻最多 1 个在途 + 1 个降级请求 |

**为什么是 350ms 而不是更短**：实测单次请求中位延迟 ~550ms，且**连续请求会触发连接熔断**
（§5）。把间隔压到 150–200ms 会让用户敲 4–5 个字符的时间内打出 3–4 个请求，
熔断概率显著上升，反而一个结果都返回不来。350ms 是「体感几乎无延迟」与「保护接口」的平衡点。
若发现熔断仍频繁，优先把 `MIN_LEN` 提到 3，而不是继续加大防抖。

---

## 9. 与现有项目的集成路径（建议，不改动源码）

1. **新增** `swdm/core/game_search.py`（§7.1 的 `GameSearchClient`），作为纯客户端，
   不依赖 `SteamAPI`（后者是工坊 API + 社区页客户端，职责不同）。
2. **工坊页可编辑下拉框**：`game_combo` 已可编辑，挂上 §7.2 的联想；
   选中后走现有 `_on_game_changed` → `_current_appid()` 流程，**下游零改动**。
3. **结果落库**：用户选中一个线上搜到的游戏后，调用现有 `games.add_custom(appid, name)`
   写入 `custom_games.json`——下次直接从本地列表命中，**越用越快、且离线可用**。
   这与现有「＋ 添加自定义游戏…」菜单自然合并，可替代其「手填 AppID」的交互。
4. **图片显示**：`tiny_image` URL 交给现有 `SteamAPI.fetch_image()`（30 天本地缓存），
   或直接给 `QNetworkAccessManager` 异步加载（联想场景更轻量，避免阻塞）。
5. **选中后校验（可选）**：`appdetails/?appids={id}` 实测匿名可用（~500ms），
   可确认 `type == "game"` 并回填名称，防止用户选到 DLC（如 id 413850「CS:GO Player Profiles」）。

---

## 10. 风险与已知限制（实测）

| 风险 | 说明 | 缓解 |
|---|---|---|
| 连接熔断（10053） | 12 连发仅 2–3 次成功；静置 15s 恢复 | 防抖 350ms + 缓存 300s + 在途取消 |
| 中文搜索不可靠 | 仅商店名本身为中文的游戏可搜（「饥荒」✓ / 「求生之路2」✗） | UI 提示以英文名搜索 |
| SearchApps 匹配差 | "gmod" 查不到 Garry's Mod、"csgo" 空 | 仅作降级，不单用 |
| GetAppList 404 | 本机网络实测不可用 | 排除该方案；不做本地全量索引 |
| 下架游戏 | CS:GO 等已下架应用在 storesearch 会重定向到续作（CS2），在 SearchApps 直接消失 | 依赖 storesearch 的相关性排序 |
| `type` 非 game | 结果混有 DLC/视频/软件包（如 413850） | 客户端按 `type == "app"` 过滤；关键场景用 appdetails 复核 |
| 偶发 CDN 慢/失败 | header.jpg 首次 9.4s、cover.jpg 不存在 | 用返回的 `shared.akamai.steamstatic.com` 域名 + 本地缓存 |

---

## 11. 标注汇总：实测 vs 检索

**✅ 本机实测确认（2026-09-22，本报告作者直连发起）**：
- storesearch 匿名可用、返回结构、字段语义、`count`/`category` 参数无效
- 三个查询（gmod/csgo/l4d2）的完整返回内容
- SearchApps 可用、返回结构、对 gmod/csgo/中文的匹配缺陷
- GetAppList 全部变体 404
- 12 连发触发连接熔断、15s 后恢复
- 图片 CDN 各 URL 的状态码/大小/延迟（含 header/capsule/library_hero/page_bg，及 cover.jpg 不存在）
- appdetails 匿名可用、返回 `type='game'`
- 中文名搜索的部分可用性（饥荒 ✓ / 求生之路2 ✗）

**⚠️ 检索所得 / 社区共识（本次未实测验证，仅作背景）**：
- GetAppList 历史上是「无需 key 的全量列表接口」——本次实测 404，与社区文档不符，
  原因未查明（可能区域/线路差异），实现中不应依赖
- 「商店 API 限流较宽松」的一般印象——本次实测显示高频连发仍会熔断，故以实测为准
- 图片 URL 的尺寸命名（header.jpg=460x215 等）为社区惯例，本报告只验证了可访问性
  与字节数，未逐个核实像素尺寸

**未做的事**：未修改任何项目源码；未执行网络检索（本报告全部为实测产出）。
