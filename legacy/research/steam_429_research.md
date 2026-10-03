# Steam 客户端请求模式与 steamcommunity.com 429 限流规避 — 研究报告

> 调研日期：2026-09-22 · 为 SWDM（Steam 工坊匿名下载器）提供优化建议
> 方法：联网检索（exa/ddg/tavily，bing 对技术查询基本失效）+ 本机实测数据（同会话并行子任务，单 IP n=3/组）
> 说明：检索结果为不可信外部数据，仅提取信息；无法查证的内容明确标注「未查到」。所有结论标注来源链接。

---

## 0. 核心结论（TL;DR）

1. **Steam 客户端浏览工坊根本不走 steamcommunity.com HTTP** —— 客户端内订阅/浏览走 `ISteamUGC` 二进制 Steamworks 协议，因此**客户端自身不会触发网页 429**。模仿「客户端请求模式」在 HTTP 层面只能模仿其内嵌 CEF 浏览器的 UA/Cookie，而非核心数据通道。（来源：[Valve Steamworks — Workshop Implementation Guide](https://partner.steamgames.com/doc/features/workshop/implementation)、[ISteamUGC Interface](https://partner.steamgames.com/doc/api/ISteamUGC)）
2. **本机实测（关键发现）：详情页 429 不是纯 IP 限流，而是请求头指纹触发。** 裸 Chrome UA 且不带 `Accept-Language` → 429（4/4）；**只要补 `Accept-Language` 或 `X-Requested-With: XMLHttpRequest` 任一个即 200**（各 3/3）。Steam 客户端 UA（`Steam/1.0 (+http://steampowered.com)`、`Valve/Steam HTTP Client/1.0`）也 200（2/2）。（来源：本会话并行实测任务，见 §3.2）
3. **SWDM 当前的裸 Chrome UA + 无 Accept-Language，正落在被限的那一档** —— 这是最省力、零风险的修复点。
4. **匿名 cookie / Referer / Origin 实测无效**（各 3/3 仍 429）——社区流传的「带 sessionid 即可」说法在本机详情页场景被证伪。
5. 429 响应体约 334KB、`Server: nginx`、无 `CF-RAY`（Steam 自家 nginx，非 Cloudflare）、**从不带 `Retry-After`** —— 当前代码里读 `Retry-After` 的分支实际上是死代码，退避只能自定。

---

## 1. Steam 客户端的请求模式

### 1.1 工坊数据通道：二进制，非 HTTP

Valve 官方文档明确：消费工坊内容的方式是 `ISteamUGC` 接口（C++ Steamworks SDK），这是客户端与 Steam 服务器之间的**二进制连接**（Steamworks 客户端连接，走 CM 服务器），不是对 `steamcommunity.com` 的 HTTP 请求。

- 来源：[Steam Workshop Implementation Guide](https://partner.steamgames.com/doc/features/workshop/implementation)（"The process to share and consume User Generated Content is by using the ISteamUGC API"）、[ISteamUGC Interface](https://partner.steamgames.com/doc/api/ISteamUGC)
- 推论：**Steam 客户端没有「对 steamcommunity.com 的请求模式」可供完整模仿**。客户端拿工坊元数据不经网页，所以天然不受网页 429 影响。SteamCMD 下载同理（`workshop_download_item` 走的也是这条二进制通道，这也是 SWDM 匿名下载链路稳定的原因）。

### 1.2 客户端内嵌浏览器（CEF）的 UA

Steam 客户端 UI 基于 Chromium Embedded Framework（CEF），用户在客户端内打开的网页（含一些工坊/商店页面）由内嵌浏览器渲染，其 UA 带 Valve 标识。实测/数据库中可见的 UA 字符串：

| UA 字符串 | 说明 |
|---|---|
| `Mozilla/5.0 (Windows; U; Windows NT 10.0; en-US; Valve Client/1668138960; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36` | Windows 客户端（旧版形态，`Valve Client/<构建号>`） |
| `Mozilla/5.0 (Windows NT 10.0; Win64; x64; Valve Steam Client/default/1690583737) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/... Safari/537.36` | Windows 客户端（较新形态，`Valve Steam Client/default/<构建号>`） |
| `Mozilla/5.0 (X11; Linux x86_64; Valve Steam Client/Steam Deck [Steam Deck Stable]/default/0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36` | Steam Deck |
| `Mozilla/5.0 (Macintosh; U; MacOS X 10_11_6; en-US; Valve Client/1618256785; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36` | macOS 客户端 |

- 来源：[user-agents.net — Valve Client UA](https://user-agents.net/string/mozilla-5-0-windows-u-windows-nt-10-0-en-us-valve-client-1668138960-applewebkit-537-36-khtml-like-gecko-chrome-85-0-4183-121-safari-537-36)、[useragents.io — Valve Corporation 设备](https://useragents.io/explore/devices/types/desktop/maker/valve-corporation-457)、[udger.com — Steam Client UA 列表](https://udger.com/resources/ua-list/browser-detail?browser=Steam+Client)、[Valve Developer Community — CEF](https://developer.valvesoftware.com/wiki/Chromium_Embedded_Framework)、[Steambrew 文档 — Steam 运行于 CEF](https://docs.steambrew.app/developers/environment)

### 1.3 非客户端 HTTP 组件的 UA

Steam 的 HTTP 客户端库/工具发出的 UA 是另一个形态，本机实测可用：

- `Steam/1.0 (+http://steampowered.com)` —— 早期 Steam HTTP 组件 UA
- `Valve/Steam HTTP Client/1.0` —— Valve HTTP 客户端标识
- 两者在本机详情页实测均返回 200（各 2/2）。
- 参考形态（Rust `steam-user` 库的默认 UA 为 Chrome 风格）：[docs.rs steam-user client.rs](https://docs.rs/steam-user/latest/src/steam_user/client.rs.html)

### 1.4 Cookie 机制（登录态相关）

- `steamcommunity.com` 与 `store.steampowered.com` **共享登录域**：登录 cookie 主要是 `sessionid`、`sessionid_secure`、`steamLogin_secure`（新版登录后由 `Set-Cookie` 下发，`steamLogin` 旧项已退役）。node-steamcommunity 明确记录了这套 cookie 的管理方式，并指出请求实例在登录/设置 cookie 后会携带它们。
- 匿名访问时，首次 GET 会下发匿名 `sessionid`、`steamCountry` 等 cookie；但**本机实测：携带匿名 cookie 对详情页 429 完全无效**（3/3 仍 429）。
- 来源：[node-steamcommunity Wiki — SteamCommunity](https://github.com/DoctorMcKay/node-steamcommunity/wiki/SteamCommunity)、[McKay Development — Cookies (updated for 2023)](https://dev.doctormckay.com/topic/4584-cookies-updated-for-2023/)、[steamLoginSecure update](https://dev.doctormckay.com/topic/4506-steamloginsecure-update/)

---

## 2. 429 限流机制分析

### 2.1 判定维度

| 维度 | 证据 | 结论 |
|---|---|---|
| **IP** | Steam 官方论坛多人确认："Too many requests is an IP rate limit"，且 2022 年 10 月初为市场/库存新增；重装系统、关 VPN、换浏览器均不解决，换 IP/等数天才恢复 | 确实存在 IP 维度，且对市场/库存页很重 |
| **请求头指纹（非 IP）** | 本机实测：同 IP 同 URL，裸 Chrome UA 无 `Accept-Language` → 429（4/4）；补 `Accept-Language` 或 `X-Requested-With` → 200（3/3） | **详情页当前的主要触发维度是请求头指纹**，不是 IP |
| **账号/session** | 详情页 429 时匿名 cookie 无效；市场限流则与登录态无关（IP 维度） | 详情页不按账号判，按客户端指纹判 |
| **UA** | Steam 客户端 UA、Valve HTTP UA 均 200；裸 Chrome UA 429 | UA 是指纹的一部分（但单独换 UA 未在裸 UA 基础上叠加验证，见 §3.2 局限） |

- 来源（IP 维度）：[Steam 论坛 — "Too many requests" is an IP rate limit](https://steamcommunity.com/discussions/forum/1/597413522044081333/)、[Steam 论坛 — Still getting "Too Many Requests" after 10 days](https://steamcommunity.com/discussions/forum/1/628941617404955013/)、[Steam 论坛 — "Too many requests"（2022-10 新增）](https://steamcommunity.com/discussions/forum/7/3801650156484807057/)
- 来源（市场库存端）：[node-steamcommunity PR #300 — New rate limit rule from steam（count>2000 触发）](https://github.com/DoctorMcKay/node-steamcommunity/pull/300)、[Issue #265 — Avoid 429 when loading large inventory](https://github.com/DoctorMcKay/node-steamcommunity/issues/265)、[McKay 论坛 — New request limits (429)](https://dev.doctormckay.com/topic/5946-new-request-limits-429-error/)、[StackOverflow — Steam get inventory returns 429 after few requests](https://stackoverflow.com/questions/74999554/steam-get-inventory-of-user-returns-429-after-few-requests)

### 2.2 阈值

- **未查到** Valve 公布的 steamcommunity.com 精确速率阈值。第三方汇总（[apis.io — Steam Rate Limits](https://apis.io/rate-limits/steam/steam-rate-limits/)）明确写「Valve does not publish a precise per-second cap on Steam Web API calls in the public Steamworks docs」。
- 社区经验值（市场/库存，IP 维度）：连续快速请求数十次即触发；触发后冷却时间长（小时～天级，需换 IP）。
- 本机详情页实测：**触发与速率关系弱、与指纹关系强** —— 间隔 8s 慢速请求，裸 Chrome UA 依旧 429；补齐指纹头后同样速率即 200。说明详情页当前更像「指纹黑名单 + 速率」的组合，而非单纯速率桶。
- **429 响应特征（实测）**：状态码 429，响应体 ~334,468 字节（是个完整错误页），`Server: nginx`，**无 `CF-RAY`（非 Cloudflare）**，**从不返回 `Retry-After` 头**。
  - ⇒ SWDM 现有代码 `int(r.headers.get("Retry-After", "20"))` 永远走默认 20s 分支；对详情页该分支实际无效，退避策略需自定（当前渐进退避是合理设计，但可基于「指纹修复后几乎不再触发」重新调参）。

### 2.3 详情页 vs 浏览页差异（推测）

- 浏览页 `/workshop/browse/` 实测宽松、详情页 `/sharedfiles/filedetails/` 极重 —— 检索**未查到** Valve 对此的官方说明。
- 可信推测：详情页是反爬重点（评论/数据聚合页，爬虫价值高），限流规则更激进；浏览页作为入口页较宽松。两者共享同一限流后端但规则不同。
- 本机 TCP 阻断史（Steamcommunity 302 修复后详情页持续 429）与「IP 被标记」一致；但实测证明**当前已退化为指纹维度**，换指纹头即可绕过，不必换 IP。

---

## 3. 可落地手段清单（按 可行性/风险/收益 排序）

### 🥇 第 1 档：立即可做，零风险，收益最高

#### 3.1 补 `Accept-Language` 头（最推荐）

- **做法**：`_community_get` 的 session 默认头加 `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8`。
- **依据**：本机实测补此头即 200（3/3）。机制推测：真实浏览器 UA 必带 `Accept-Language`，缺失即被识别为非浏览器自动化指纹。
- **风险**：无。这是最标准的浏览器行为，完全属于「普通浏览请求模式」。
- **来源**：本会话并行实测（同 IP，n=3/组）。

#### 3.2 补 `X-Requested-With: XMLHttpRequest`

- **做法**：`X-Requested-With: XMLHttpRequest`。
- **依据**：实测单独加此头即 200（3/3）。
- **风险**：低。该头常用于 ajax 请求标识；对整页 GET 加它略不合语义，但 Steam 端接受。**建议与 3.1 二选一或叠加**，并做一次实测确认。
- **局限**：此结论来自本机单 IP；是否为长期稳定策略未知，建议加到实测脚本里定期回归。

#### 3.3 改用 Steam 客户端 / Valve HTTP UA

- **做法**（任选其一，建议作为可配置项）：
  - `Steam/1.0 (+http://steampowered.com)`
  - `Valve/Steam HTTP Client/1.0`
  - `Mozilla/5.0 (Windows NT 10.0; Win64; x64; Valve Steam Client/default/1690583737) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`
- **依据**：本机实测前两者 200（2/2）；UA 数据库佐证后者为真实客户端 UA。
- **风险**：低～中。UA 本身不涉及身份伪造（无账号），属「表明自己是 Steam 客户端」；但**若叠加其它规避手段可能被视为绕限流器**。单独换 UA 属常见做法。
- **注意**：换 UA 后 `_CARD_RE` 正则解析需回归（Steam 客户端 CEF 渲染的 DOM 与 Chrome 一致，但保险起见跑一次 `test_online_parse`）。

### 🥈 第 2 档：架构优化，中低风险，收益高

#### 3.4 详情页职责迁移到 api.steampowered.com（IPublishedFileService/GetDetails）

- **关键发现**：`IPublishedFileService/GetDetails` **匿名无 key 可用**（多个库明确声明 "No API Key is required to fetch details for public items"）。这与 `QueryFiles` 需要 key 不同。
  - 来源：[K4ryuu/steam-workshop-ts README](https://github.com/K4ryuu/steam-workshop-ts)（"No API Key is required to fetch details for public items" / "Requires a Steam Web API Key" 仅用于 collection 查询）、[Rust steam-workshop-api lib.rs](https://docs.rs/steam-workshop-api/latest/src/steam_workshop_api/lib.rs.html)（"To access any web api that requires no authentication (file details)"）
- **调用形式**（[Postman 样例](https://www.postman.com/digital-descent/development-resources/request/w0eoqi4/getdetails)）：
  ```
  GET https://api.steampowered.com/IPublishedFileService/GetDetails/v1/?input_json={"publishedfileids":[ID],"includetags":true,...}
  ```
- **能力边界（依据 protobuf 定义，[SteamTracking](https://raw.githubusercontent.com/SteamDatabase/SteamTracking/master/Protobufs/steammessages_publishedfile.steamclient.proto)）**：`CPublishedFile_GetDetails_Request` 17 字段，含 `includetags`、`includemetadatas`、`includechildren`（**可拿依赖**）、`includevotes`、`short_description`、`language` 等。
  - ⚠️ **能否匿名拿到 children/描述，检索无法确证** —— 需本机实测 `includechildren=true` 匿名返回是否非空（项目既有结论是 `ISteamRemoteStorage` 的 `referenced_files` 匿名恒空，但 `IPublishedFileService/GetDetails` 是**另一个接口**，行为可能不同）。**这是最高价值的待验证项**：若匿名能拿到 children，`get_dependencies()` 可整体迁移到 api 域，详情页 429 痛点直接消失。
- **风险**：无（官方 API 的正常匿名调用）。

#### 3.5 评论 ajax 端点与详情页同域，沿用同一指纹策略

- 评论端点（如 `ajaxcommentopinion` / 评论分页）与详情页同在 steamcommunity.com，限流同源。补同样的指纹头即可。
- 来源：[ColdNorthAdmin — Getting all comments from workshop projects](https://coldnorthadmin.com/posts/steam_comments_getter/)（评论抓取的端点与分页机制）、[gist — Load all comments from steam workshop](https://gist.github.com/ostr00000/ecb7a07480cda4f2ffad18ee1d955aa4)

#### 3.6 缓存与去重（已做，继续加固）

- browse 结果缓存 3 分钟、依赖缓存 30 分钟已落地，方向正确。建议：**依赖树解析时按整棵树批量化**（先收集全部待解析 id，`GetDetails` 一次批量取 children，减少详情页请求量），配合 3.4。

### 🥉 第 3 档：有效但有代价，按需启用

#### 3.7 代理 / 多 IP 轮换

- **做法**：`requests.Session` 已支持 `proxies`（`SteamAPI(proxy=...)` 已实现）。触发 429 后切换出口 IP。
- **依据**：IP 维度限流确凿（市场/库存场景），换 IP 是社区公认解法（[Reddit — FIXED "You've made too many requests"](https://www.reddit.com/r/steamsupport/comments/1og4sm5/fixed_youve_made_too_many_requests_recently_steam/)）。
- **风险**：中。需用户提供代理；免费公共代理不可靠且可能被 Steam 封禁整段；**本机实测已证明详情页不必换 IP 即可恢复**，故此项降级为兜底手段而非首选。

#### 3.8 镜像/备用域

- 检索**未查到** steamcommunity.com 有可替代的官方镜像域。`store.steampowered.com` 与社区共享登录但**不承载 `/sharedfiles/` 详情页**。社区加速工具（Steamcommunity 302）是 hosts/302 重定向方案，解决连通性而非限流。
- **结论**：此路不通，不做。

---

## 4. 不建议的手段及原因

| 手段 | 不建议原因 |
|---|---|
| **携带匿名 cookie（sessionid/steamCountry 等）** | 本机实测无效（3/3 仍 429）；徒增复杂度。来源：本会话实测 |
| **伪造 Referer / Origin** | 本机实测无效（3/3 仍 429）；且伪造来源头比缺失头更接近「规避检测」语义 |
| **撞库式高并发 + 换 IP 池** | 属明确绕限流器行为，违反 ToS 精神；IP 段易被整体封禁；本场景无必要 |
| **伪造登录态/账号 cookie 匿名使用** | 涉及凭证伪造，跨越 ToS 红线；且详情页限流与账号无关，无收益 |
| **抓取第三方中转站（steamworkshop.download 类）** | 该类站点已**成批倒闭**（API 2022-05-28 关闭），单点故障 + 文件被注入风险（见既有 `competitor_analysis.md` §2） |
| **解析混淆类名** | 与 429 无关，但既有研究已证 React 重构后类名混淆，应继续用正则（项目已如此） |

---

## 5. 对 SWDM 的具体建议（`steam_api.py` `_community_get`）

当前代码（`steam_api.py:75-78`、`172-175`、`225-266`）的问题点与改法：

### 5.1 立即改：session 默认头补指纹

```python
# steam_api.py — SteamAPI.__init__ 中
self._session.headers.update({
    "User-Agent": _UA,          # 保留 Chrome UA 或换 Valve 客户端 UA
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",   # ← 关键：实测补此头即 200
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    # 可选叠加（实测单独也有效）：
    # "X-Requested-With": "XMLHttpRequest",
})
```
- 收益：详情页 429 大概率直接消失，`/sharedfiles/` 的 6s 端点间隔可回落到 2s，依赖树解析速度显著提升。
- 风险：零。纯属浏览器标准行为。

### 5.2 Retry-After 分支的现实

- 详情页 429 从不带 `Retry-After`（实测），现有 `max(10.0, min(float(ra), 120.0))` 恒走默认 20s。**不必删**（别的端点可能带），但调参应基于「自定退避」假设；指纹修复后触发频率会大降，`cap 90s / 4 次` 可维持。

### 5.3 高价值验证项：`IPublishedFileService/GetDetails` 匿名取依赖

```python
# 待验证（一次实测即可定夺）：
GET https://api.steampowered.com/IPublishedFileService/GetDetails/v1/
    ?input_json={"publishedfileids":[ID],"includetags":true,
                 "includechildren":true,"includevotes":false,
                 "short_description":true,"language":"schinese"}
```
- 若匿名 `children` 非空 → `get_dependencies()` 迁出 steamcommunity.com，详情页限流痛点根除。
- 若为空 → 维持网页抓取（已补指纹头，够用），并把该结论写回 `research/workshop_api_research.md`。

### 5.4 退避参数建议

- 指纹修复后，`_ENDPOINT_INTERVALS` 的 `/sharedfiles/` 6s 建议先实测再调（可能可降回 2s）；保留 `_throttle.bump/decay` 自适应机制。
- 建议把「指纹头组合」做成可配置（设置页或 config），便于 Steam 调整规则后快速切换，不写死单一策略。

---

## 6. 法律 / ToS 边界

- **允许（低风险）**：使用官方 Web API 的公开端点（GetPublishedFileDetails / GetCollectionDetails / 匿名 GetDetails）；以标准浏览器请求模式抓取公开页面（合理速率、真实 UA、不绕检测）；用户自填 API key 调用需 key 的端点。
- **灰区（需注意）**：UA 切换、请求头补全 —— 属「使请求看起来像正常浏览器」，社区普遍实践，Valve 未明确禁止；但**配合大规模抓取时可能被视为自动化爬取**。建议保持低速率 + 缓存，不做高并发。
- **有风险（不建议）**：IP 池轮换规避限流、伪造账号凭证、逆向绕限流器逻辑、第三方中转分发版权内容。
- 检索**未查到** Valve 针对 steamcommunity.com 网页抓取的专门 ToS 条款；[Steam 订户协议](https://store.steampowered.com/subscriber_agreement/) 通用条款限制「自动化访问干扰服务」。本报告建议保守：只做低频匿名浏览式抓取。
- 参考既有竞品分析的同类结论（`competitor_analysis.md` §7 风险表：坚持本地客户端直连官方接口、不自建中转、不做盗版分发）。

---

## 7. 来源汇总

**Steam 客户端协议与 UA**
- [Valve Steamworks — Workshop Implementation Guide](https://partner.steamgames.com/doc/features/workshop/implementation)
- [ISteamUGC Interface](https://partner.steamgames.com/doc/api/ISteamUGC)
- [user-agents.net — Valve Client UA](https://user-agents.net/string/mozilla-5-0-windows-u-windows-nt-10-0-en-us-valve-client-1668138960-applewebkit-537-36-khtml-like-gecko-chrome-85-0-4183-121-safari-537-36)
- [useragents.io — Valve Corporation](https://useragents.io/explore/devices/types/desktop/maker/valve-corporation-457) · [udger — Steam Client UA](https://udger.com/resources/ua-list/browser-detail?browser=Steam+Client) · [user-agents.net — Steam Deck UA](https://user-agents.net/string/mozilla-5-0-x11-linux-x86-64-valve-steam-client-steam-deck-steam-deck-stable-default-0-applewebkit-537-36-khtml-like-gecko-chrome-109-0-5414-120-safari-537-36)
- [Valve Developer Community — CEF](https://developer.valvesoftware.com/wiki/Chromium_Embedded_Framework) · [Steambrew — Environment](https://docs.steambrew.app/developers/environment)
- [docs.rs steam-user 默认 UA](https://docs.rs/steam-user/latest/src/steam_user/client.rs.html)

**429 限流机制**
- [Steam 论坛 — IP rate limit 说明](https://steamcommunity.com/discussions/forum/1/597413522044081333/) · [10 天未恢复案例](https://steamcommunity.com/discussions/forum/1/628941617404955013/) · [2022-10 新增限流](https://steamcommunity.com/discussions/forum/7/3801650156484807057/)
- [node-steamcommunity PR #300 — 新限流规则](https://github.com/DoctorMcKay/node-steamcommunity/pull/300) · [Issue #265 — 大库存 429](https://github.com/DoctorMcKay/node-steamcommunity/issues/265) · [McKay — New request limits](https://dev.doctormckay.com/topic/5946-new-request-limits-429-error/)
- [StackOverflow — 库存 429](https://stackoverflow.com/questions/74999554/steam-get-inventory-of-user-returns-429-after-few-requests) · [StackOverflow — 市场 429](https://stackoverflow.com/questions/37473064/does-the-steamcommunity-market-block-the-client-after-multiple-tries) · [SO — Web API 429 规避](https://stackoverflow.com/questions/51795457/avoiding-error-429-too-many-requests-steam-web-api)
- [apis.io — Steam Rate Limits（Valve 未公布精确阈值）](https://apis.io/rate-limits/steam/steam-rate-limits/)

**API 能力**
- [K4ryuu/steam-workshop-ts（GetDetails 无需 key）](https://github.com/K4ryuu/steam-workshop-ts) · [README](https://github.com/K4ryuu/steam-workshop-ts/blob/main/README.md)
- [xPaw — IPublishedFileService 文档](https://steamapi.xpaw.me/IPublishedFileService) · [Valve 官方 IPublishedFileService](https://partner.steamgames.com/doc/webapi/IPublishedFileService)
- [SteamTracking — CPublishedFile_GetDetails_Request protobuf（17 字段）](https://raw.githubusercontent.com/SteamDatabase/SteamTracking/master/Protobufs/steammessages_publishedfile.steamclient.proto) · [docs.rs steam-vent-proto](https://docs.rs/steam-vent-proto/latest/steam_vent_proto/steammessages_publishedfile_steamclient/struct.CPublishedFile_GetDetails_Request.html)
- [Postman — GetDetails 调用样例](https://www.postman.com/digital-descent/development-resources/request/w0eoqi4/getdetails)

**Cookie / 登录域**
- [node-steamcommunity Wiki](https://github.com/DoctorMcKay/node-steamcommunity/wiki/SteamCommunity) · [McKay — Cookies 2023](https://dev.doctormckay.com/topic/4584-cookies-updated-for-2023/) · [steamLoginSecure update](https://dev.doctormckay.com/topic/4506-steamloginsecure-update/)

**评论端点**
- [ColdNorthAdmin — 工坊评论抓取](https://coldnorthadmin.com/posts/steam_comments_getter/) · [gist — Load all comments](https://gist.github.com/ostr00000/ecb7a07480cda4f2ffad18ee1d955aa4)

**本机实测（本会话并行子任务，单 IP n=3/组）**
- 详情页 429 与请求头指纹关系矩阵：裸 Chrome UA 4/4 → 429；补 `Accept-Language` 或 `X-Requested-With` 3/3 → 200；Steam 客户端 UA 2/2 → 200；匿名 cookie / Referer / Origin 各 3/3 仍 429；429 响应 ~334KB、`Server: nginx`、无 `CF-RAY`、无 `Retry-After`。

---

## 8. 未查到 / 待验证清单

- Valve 对 steamcommunity.com 网页抓取的**专门 ToS 条款** —— 未查到，按通用订阅户协议保守处理。
- 详情页 429 的**精确速率阈值** —— 未查到（Valve 不公布）；本机实测表明详情页当前主要由指纹触发，非速率。
- `IPublishedFileService/GetDetails` **匿名 `includechildren` 是否非空** —— 检索无法确证，列为最高价值待验证项（§5.3）。
- 详情页 vs 浏览页限流差异的**官方说明** —— 未查到，仅有实测差异。
- Steam 客户端内嵌浏览器打开工坊页面时的**完整请求头集合**（Accept-Language 等）—— 未查到一手抓包；建议用本机 CEF 抓包或直接按 §5.1 标准浏览器头补全。
