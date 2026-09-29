# SWDM 第三方下载 Provider 调研

> 收尾版本 · 2026-09-28 · 调研员：provider 接入研究员（第三棒）
> 前置：GGNetwork 已由前序调研员端到端验证（匿名可用、CDN zip 下载）。本文复核其 ToS/速率，并补齐 steamwebapi / steamworkshop.download / Nether / SWD 四项。
> 方法：实网页面直取（pwsh Invoke-WebRequest）+ 页面内 JS bundle 逆向定位后端 API + 搜索引擎交叉验证。所有引用均为实测响应原文。
> 配套设计：`research/provider_adaptation.md`（provider 抽象与链式回退设计）。

---

## 1. steamwebapi.com —— Steam 经济类 API，**不是**工坊下载服务（排除）

### 身份
"All-in-One Steam API – Market, Inventory, Skin Prices & Trade for CS2, Rust, Dota 2 & more."（首页 meta description 原文）。是做**市场物价 / 库存 / 皮肤磨损 / 交易**的第三方 API 商，不做 Workshop 下载。

### 端点（实测从文档页 `https://www.steamwebapi.com/api/steam/documentation` 提取的全部 `/steam/api/*` 路径）
```
apps / apps/{appid} / apps/{appid}/players / apps/filters / apps/metrics
item / items / items/history / items/preview / info/items / info/markets
info/steamid / info/platform-players
inventory / inventory/batch / profile / profile/batch / profile/games
profile/risk / profile/trades / profile/trade-eligibility / friendlist
float / float/assets / float/create-inspectlink / float/screenshot
history / market-index/cs2 / market-index/cs2/history / market-index/cs2/compare
complete/items / cs/collection/{slug} / cs/collections / cs/containers
guard/*（Steam 手机令牌操作）/ trade/*（交易操作）/ steamloginsecure
```
全文检索结论：文档页正文中 `workshop` **仅出现 2 次**，且都是 `/steam/api/apps` 的**应用元数据标志位**说明（"Store metadata per game (images, DLC / workshop / market flags, categories, prices) is intentionally NOT included"）。**没有任何工坊文件下载/解析端点**。`download` 关键字 19 次全部指图片格式参数（`format=download` 下载截图）、maFile 附件、gzip/zip 压缩响应——与工坊内容无关。

### 认证
需要 API Key。文档示例：`curl -H "X-Api-Key: YOUR_API_KEY"`。免费层 CTA 是 "Login with Steam"（用 Steam 登录领 Key）。

### 定价（实测从定价页单行 HTML 正则提取，货币 EUR，26 个套餐）
| 套餐 | 月付 | 年付 | 一次性(30天) | Global 限速 /分钟 | /天 | /月 |
|---|---|---|---|---|---|---|
| **Free**（"Free for ever - but no Items included!"） | €0.00 | €0.00 | 不可用 | **2** | **5** | **10** |
| Free+（需小额验证费） | €1.00 | €12.00 | 不可用 | 10 | 50 | 50 |
| Starter | €25.00 | €225.00 | €30.00 | 20 | 2,000 | 10,000 |
| Starter+（Most Popular） | €30.00 | €288.00 | €35.00 | 40 | 5,000 | 20,000 |
| Pro | €50.00 | €480.00 | €60.00 | 40 | 12,500 | 100,000 |
| Pro+ | €120.00 | €1,296.00 | €125.00 | 1,000 | 50,000 | 1,000,000 |
| Enterprise | 定制 | — | — | "higher or unlimited rate limits" | | |

- 免费层确实存在（€0、免卡、永久），但 **Items 端点配额为 0/0/0**（"items" endpoint is now restricted to subscribers only），Global 仅 2 次/分钟、5 次/天、10 次/月。
- 计费走 Stripe；Subscription（月/年自动续费）与 One-Time（单次 30 天不续费）两种；套餐按端点族分（balanced / inventory / item / float / assets / profile / history）组合购买。
- 免费层 FAQ 原文："The Free Plan includes limited requests per minute and per day as listed on the pricing page. These limits ensure fair usage for all developers."

### 结论
**与 SWDM 的下载需求完全无关——排除。** 它是 Steam 经济圈（CS2 皮肤/市场/库存）的数据 API，没有工坊下载端点；其价值仅在于将来若做"mod 价格/物品信息"增强时可考虑，且免费层 2 次/分钟基本只够测试。**建议从 provider_adaptation.md 的四个第三方名单中移除**，`providers/steamwebapi.py` 无需创建。

---

## 2. steamworkshop.download（SWD）—— 活着，但纯网页/HTTP-only，无 API

### 身份确认
SWD 就是 `steamworkshop.download`（页面 `<title>SteamWorkshop.download</title>`，footer "Powered By ABCVG Network"）。无独立服务。

### 现状（实测）
| 协议 | 结果 |
|---|---|
| `https://steamworkshop.download/` 与 `https://www.steamworkshop.download/` | **连接失败**（"基础连接已经关闭: 发送时发生错误"——TLS 握手即断，HTTPS 已不可用） |
| `http://steamworkshop.download/` | **200**，旧的 PHP 表单页，正常运行 |

### 匿名下载实测（2026-09-28）
```
POST http://steamworkshop.download/
Content-Type: application/x-www-form-urlencoded
url=https://steamcommunity.com/sharedfiles/filedetails/?id=377856298
```
响应为 HTML 物品页（200，无登录、无 Key、无验证码），正文含物品元数据与直链：
```
Download: Tales from the Borderlands | Sasha [LR]  [Source Filmmaker]
Size: 8MB  Views: 3615  Create: 19.01.2015  Update: 07.07.2015
Subscribers: 1528  Favorites: 57
Filename: models/ca75c889-a341-4c47-ab7a-8ef38e49ad27.zip
<a href='https://cdn.steamusercontent.com/ugc/689398577964331827/10DED0DB.../'>Download</a>
```
**匿名可用成立**：返回的直链就是 Steam 官方 CDN（cdn.steamusercontent.com），与本程序 CDN 通道 resolve 出的是同一类 URL——SWD 本质是一个"工坊 URL → 官方 CDN URL"的解析代理。

### 端点 / API 形态
- **无 JSON API**。唯一入口是上面这个表单（HTML 抓取），另有 `http://steamworkshop.download/download/view/<id>` 物品页（官方 userscript `st.abcvg.info/swd/steamwd.user.js` v0.0.1 只是在工坊页加一个跳转按钮，指向该 view 页）。
- 无 Key、无 Token、无文档、无状态页。

### 速率 / ToS
未找到任何公开速率限制或服务条款。站点极简（首页 2.4KB），无 ToS 页。

### 风险
1. **仅 HTTP 明文**——任何集成都会在链路上暴露用户查询的 mod URL；且 HTTPS 挂掉说明维护停滞。
2. 社区评价偏负面：Reddit r/civ 置顶帖 "[PSA] Do not use steamworkshop.download for mods (Outdated)"；GreasyFork 上的替代脚本自述"replacing the deprecated or free space left from steamworkshop.download"。
3. 无 SLA、无状态页、随时可能整站下线。

### 结论
**能匿名下载，但只能 HTML 抓取、只能 HTTP 明文、服务半废弃。** 价值是作为"GGNetwork 不可用时的二级解析回退"——但它返回的同样是官方 CDN URL，而本程序的 CDN 通道自己就能 resolve（只要修好 `services.py:78` 的 api 注入，见 provider_adaptation.md §1.2）。**因此 SWD 的增量价值很低**，建议列入"可选外部引导（EXTERNAL）"而非主链，优先级低于 GGNetwork。

---

## 3. GGNetwork（ggntw.com）—— 已验证，本次补齐 ToS 与速率

### 端点（实测确认，来自 GreasyFork 用户脚本 `Steam Workshop Downloader (GGNetwork)` v5.0 MIT by Cerulean，并自行复测）
```
POST https://api.ggntw.com/steam.request
Content-Type: application/json
{ "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=<publishedfileid>" }
```
实测响应（2026-09-28，本机直连）：
```json
{"result":1,"id":"377856298","game":1840,"name":"Tales from the Borderlands | Sasha [LR]",
 "image":"https://images.steamusercontent.com/ugc/.../","size":"8 MB",
 "queue":{"position":0,"total":0},"status":1,"server":0,"update":"07.07.2015 20:21",
 "url":"https://cdn.steamusercontent.com/ugc/689398577964331827/10DED0DB.../","test":2}
```
- 返回字段 `url` = **Steam 官方 CDN 直链**（cdn.steamusercontent.com），与本程序 CDN 通道同一目标；另有 `id/game/name/size/update` 可做元数据交叉校验。
- `queue` 字段提示：未缓存的物品可能进入服务端排队（服务端用自有 Steam 账号代下），此时需轮询；用户脚本 @connect 里列了 `cdn.ggntw.com`，说明部分物品走 GGNetwork 自有 CDN（转存压缩包 zip，与前序调研"直接 CDN zip 下载"一致）。
- 用户脚本提示链接"it will expire soon"——解析出的直链有过期时间，**拿到 URL 后应立即下载，不能长期缓存**。

### 认证 / 匿名可用性
**无需任何 Key/Token**：实测不带任何凭据，仅带 `Origin/Referer: https://ggntw.com/` 即返回 200。响应头 `Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods: POST, GET, OPTIONS`——浏览器侧第三方接入在 CORS 层面完全放行。`Server: gginx`，`X-Server: HK-1`（香港节点）。

### ToS（实测从站点 JS bundle 逆向出后端 API 后直取，英文机翻版，版本 2025-10-01）
后端接口：`GET https://api.ggntw.com/webapi/support.docs.php?id=support_docs_terms&lang=en`（返回 Editor.js JSON 块）。关键条款：
- **§1.2.2**：协议为公开要约，"Use of any Site services, **including without account registration**, implies agreement with these Rules" —— **匿名使用被 ToS 明确覆盖，不违规**。
- **§2.3.1**：未登录用户，"Administration has the right to **limit or completely block** User access" —— 匿名可用但官方保留限流/封禁权（无前置通知义务）。
- **§4.2.1**：无订阅用户只能下载" previously uploaded by any other User"的文件（即服务端已缓存的）；免费游戏有例外条款。
- **§5.2.1/5.2.2**：禁止"bypass technical restrictions"；禁止"Abuse of special functions or Site resources, **including creating excessive server load**" —— **这是针对滥用/过载的兜底条款，等价于隐式速率限制**。
- **§7.1.1**：不保证服务连续性（无 SLA）。
- 全文**没有**"禁止第三方 API 集成/自动化访问"的明文条款，也**没有**"允许"的明文条款——属灰色地带：CORS `*` 与匿名开放接口是事实上的允许，但 ToS 无授权承诺。

### 速率
- **无任何公开数值限制**：响应头中**没有** `X-RateLimit-*` / `Retry-After`，文档（terms/privacy/payments/hosting 四篇）与支持站均无速率说明，`status.ggntw.com` 状态页不涉限流。
- 实测两次连续请求均 200，未触发限流；但 §5.2.2 的"excessive server load"条款意味着**集成方必须自律限速**。建议沿用本程序既有节流（社区公认安全值 ~30 req/min，见 `research/steam_429_research.md`），并对 GGNetwork 单独分桶限速，触发 429/封禁时熔断降级（provider_adaptation.md §6.2）。

### 结论
**唯一真正可用的第三方 provider**：匿名、无 Key、JSON API、返回官方 CDN 直链、CORS 全开。风险是 ToS 无明文授权 + 无 SLA + 无公布速率 + 匿名权可被单方面限制（§2.3.1）。接入时必须：保守限速、熔断缓存、失败静默回退 steamcmd、不在 UI 承诺可用性。

---

## 4. Nether（NetherWorkshopDownloader / NWD）—— 闭源桌面应用 + 公共账号爬虫，不可接入

### 身份
GitHub `NethercraftMC5608/NetherWorkshopDownloader`（README 原文自述），配套站点 `netherworkshop.download`（实测 **HTTPS 连接失败**）。Firefox 扩展 "Nether Workshop Downloader" 说明它走 NWD 站点下载集合。NWD5 开发中（"Nether Spider API searches everywhere for public accounts"）。

### 机制（README 原文）
- 核心是**专有爬虫 NetherSpider**："scours Steam game sharing websites to find **public accounts**"，用自定义登录处理器 + 代理登录大量账号建库，再借 **Valve Family Sharing** 下载——**包括非匿名（需拥有游戏）的 mod**。这是它相对其他下载器的卖点。
- **API 与客户端均专有闭源**："Why is the API and client proprietary? The program obviously is a crawler, and no website owner likes crawling. So it would be kept secret for no patching."
- 客户端是 Windows 安装包（Releases 页），下载走自带 sandboxed Steam 客户端 / steamctl，不开放 HTTP 接口。

### 是否提供 Workshop 下载 API
**否。** 没有任何公开/文档化的第三方 API；集成只能"装它的桌面应用"，无法作为 SWDM 的 provider 通道。免费、靠捐赠维持代理服务器。

### 合规风险（重要）
- 抓取公共账号 + Family Sharing 代下，与 Valve Steam 订阅协议直接冲突；README 自己写"use this tool responsibly and in accordance with Steam's terms of service. For educational use"，免责声明承认风险。
- 对 SWDM 而言，接入这类服务会把"匿名下载 mod"变成"使用来路不明的第三方共享账号"，**法律与安全风险远超收益**。

### 结论
**不可接入，建议从 provider 名单移除。** 若坚持支持，只能做"打开它的桌面应用/站点"的外部引导（provider_adaptation.md §6.4 第 1 条的 EXTERNAL 型），不能进下载链。

---

## 5. SWD 身份归并

**SWD = steamworkshop.download**，无第二个服务（第 2 节已合并结论）。四个候选 provider 实际只有三个独立服务：GGNetwork / steamworkshop.download / NetherWorkshopDownloader，加上 steamwebapi.com（实为经济类数据 API，非下载服务）。

---

## 6. 接入优先级建议

| 优先级 | Provider | 建议 | 理由 |
|---|---|---|---|
| **1** | **GGNetwork** | **首个试点 provider**（provider_adaptation.md §7 第 5 步） | 唯一匿名 + JSON API + 官方 CDN 直链；已端到端验证；CORS `*`；匿名受 ToS §1.2.2 覆盖。须配自律限速（~30 req/min 量级）+ 60s 探测缓存 + 熔断（§2.3.1 允许单方限匿名）。`ProviderKind.PROXY`，`requires_key=False`，`anonymous_ok=True`。 |
| **2** | **steamcmd（官方内置）** | 链尾永久兜底 | 匿名可靠、零依赖第三方；provider 抽象化后仍是最稳通道。**同时修复 `services.py:78` 未传 api 的缺陷**——CDN 通道恢复后，多数物品根本不需要第三方。 |
| **3** | **CDN 直链（官方）** | 修复 api 注入后自然恢复 | 与 GGNetwork 返回同一官方 CDN URL；登录态下是最佳通道。 |
| **4** | **steamworkshop.download** | EXTERNAL/抓取型兜底，默认禁用 | 匿名可用但 HTTP-only、无 API、半废弃、社区口碑差；只在 GGNetwork 与官方通道全部失败时作为"解析官网 CDN URL 的最后手段"，且必须明文风险提示。 |
| — | **Nether** | **移除** | 无 API、闭源、账号爬虫，合规风险。 |
| — | **steamwebapi.com** | **移除**（保留记录） | 非 Workshop 下载服务（经济/市场数据 API），免费层 2 次/分钟且 Items 端点 0 配额。将来做物价/库存功能时再单独评估。 |

### 对 provider_adaptation.md 的具体修订建议
1. `providers/` 目录去掉 `steamwebapi.py` 与 `nether.py`（或保留为 `EXTERNAL` 型占位但默认 disabled），本轮试点只做 **GGNetwork**。
2. `config.providers` 节：`ggnetwork` 保留 `enabled/base_url/timeout`，去掉 `api_key`（匿名无需）；新增 `rate_limit_per_minute` 字段（默认 20-30），provider 内部令牌桶限速，避免触发 §5.2.2。
3. GGNetwork provider 实现要点：`resolve()` 调 `steam.request` 拿 `url` 字段；`queue.position > 0` 时轮询（每 2-3s，上限 ~60s）或直接回退；拿到的 URL 立即下载（过期机制）；失败 message 明确区分"服务端排队超时"（可回退）与"物品不存在"（不回退）。
4. 匿名可用性提示文案：GGNetwork 下拉项可标"✓匿名可用"，但 tooltip 需注明"第三方服务无 SLA，可能随时限流，失败自动回退 SteamCMD"。

---

## 附：实测证据文件（research/_tmp/，调研中间产物）

- `swa_pricing.html` / `swa_docs.html`：steamwebapi 定价页与文档页原文（定价表正则提取自此）
- `ggntw_terms_en.json`：GGNetwork 英文 ToS 全文（API 逆向后直取）
- `ggnetwork_gf.html`：GGNetwork 用户脚本源码（API 端点出处）
- `swd_post.html`：steamworkshop.download 匿名 POST 响应（含官方 CDN 直链）
- `nether_gh.html`：NetherWorkshopDownloader README 全文
