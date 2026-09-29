# Steam 创意工坊下载工具 429 限流规避 — 研究报告（竞品篇）

> 调研日期：2026-09-23 · 项目：SWDM（Python + steamcmd 匿名下载器）
> 目标：为"仍易触发 429"的下载机制修复提供竞品依据与可落地清单
> 前置成果：`steam_429_403_research.md`（2026-09-22，本机 34 请求实测）已确认 **详情页 429 = 缺 `Accept-Language` 的请求头指纹**、**403 = IP/边缘层不可控**。本报告不重复实测，只补竞品与社区方案。
>
> ⚠️ **证据分级**：✅ = 本项目实测或官方文档原文；🔍 = 检索所得片段，未能读取完整源码/正文。
> ⚠️ **方法局限**：本次调研无 URL 抓取工具，所有"源码级"结论来自搜索引擎返回的**代码/文档片段**，未逐行核实。凡片段不足以支撑的，一律标注"细节查不到"。

---

## 0. 核心结论（TL;DR）

1. **所有稳定竞品的根本策略是同一件事：不走 steamcommunity.com 网页。** SteamCMD 走 ISteamUGC 二进制协议天然免疫；WorkshopDL 按文件大小在 WebAPI / SteamCMD 间切换；成熟库（steam-user / steam-go / steam.py）都内置客户端限流器。SWDM 的下载链路已如此，**唯一仍碰网页的是依赖解析**。
2. **社区公认的"安全速率"参考值是 ~30 req/min**（Rust `steam-user` 库的全局限流器默认值 `Quota::per_minute(30)`）。这不是 Valve 公布的上限，而是库作者选择的保守值——但它是本次唯一查到的**具体数字**。
3. **官方 Web API 限额 = 100,000 次/天**（Steam Web API Terms of Use 原文）；Valve **不公布**精确的每秒/每分钟上限。**非官方 Storefront API（`store.steampowered.com/api/`）限流更严**，"在远低于官方 API 的量级就返回 429"——SWDM 的 `storesearch` 游戏搜索正在此列。
4. **缺 `Accept-Language` 是反爬行业的通用指纹判据**，不是 Steam 独有（ZenRows 反爬文档明确列出该头缺失为检测项）。SWDM 已补该头 = 已对齐行业基线。
5. **依赖解析没有"无 API key"的纯 API 替代方案**（查证确认）。官方 `IPublishedFileService.GetDetails` 返回 `child_publishedfileid` 依赖字段，但**匿名 401**（本项目实测）。无 key 时只能继续抓详情页或让用户填 key。
6. **登录 cookie 对网页 429 无已知的直接收益**（查证确认）。登录的收益在 steamcmd 下载通道，不在网页通道。
7. **限流规则在持续收紧**：node-steamcommunity 2022-10 加 PR #300 修"Steam 新限流规则"；2026-07-10 McKay 论坛再爆"新请求限制"（33 回复）。⇒ 任何"当前够用"的参数都必须可配置。

---

## 1. 竞品具体做法

### 1.1 请求策略矩阵

| 工具 | 碰社区网页？ | 重试/退避 | 并发/限流 | 缓存 | 证据强度 |
|---|---|---|---|---|---|
| **SteamCMD**（Valve 官方） | ❌ 二进制协议 | 同会话内人工重贴命令直到成功（社区实践） | 无网页请求 | 无 | ✅ 官方 + 🔍 [社区帖](https://steamcommunity.com/discussions/forum/1/215439774859993377) |
| **WorkshopDL** | 基本不碰（元数据走 api.steampowered.com） | **细节查不到**（闭源 Clickteam Fusion 2.5） | **细节查不到** | 不明 | 🔍 [DeepWiki 架构](https://deepwiki.com/imwaitingnow/WorkshopDL/2.2-download-pipeline-and-provider-backends) |
| **steam-user**（Rust 库） | 是（通用 HTTP） | 429 时对限流器施加 **penalty 锁定**（`penalize()`） | **全局 `Quota::per_minute(30)`** + per-host 等待 + 可配置 `rate_limit(req/min, burst)` | 无（限流器在连接间共享 `Arc`） | ✅ [源码片段](https://docs.rs/steam-user/latest/src/steam_user/limiter.rs.html) / [Builder API](https://docs.rs/steam-user/latest/steam_user/client/struct.SteamUserBuilder.html) |
| **steam-go**（Go SDK） | 是 | "conservative request controls"（保守请求控制） | 有专门 Rate-Limiting-Strategy 文档；具体数值**片段未给出** | 不明 | 🔍 [限流策略文档](https://github.com/gofurry/steam-go/blob/main/docs/wiki/en/Rate-Limiting-Strategy.md) |
| **steam.py**（Gobot1234，Python） | 是 | `HTTPClient` 内置请求重试（`http.py`） | **细节查不到**（片段截断） | 不明 | 🔍 [http.py](https://github.com/Gobot1234/steam.py/blob/master/steam/http.py) |
| **node-steamcommunity**（McKay） | 是 | 携带登录 cookie 的 request 实例；遇 Steam 新规则即发版修 | **端点差异化**：`/inventory/SteamID` 明确标注"less rate-limited" | cookie jar 跨实例共享 | ✅ [Wiki](https://github.com/DoctorMcKay/node-steamcommunity/wiki/SteamCommunity) / [PR #300](https://github.com/DoctorMcKay/node-steamcommunity/pull/300) |
| **轻量 Python 包装器**（Geam / shadoxxhd / googprojects / Husko's / notSeilce 等） | 少量（集合页） | **细节查不到**（多为 README 级信息） | 多为单线程顺序下载 | 无 | 🔍 仓库 README |
| **BrettMayson/Arma3Server** | 是（集合解析） | — | — | — | 🔍 [定义了完整 Mac Chrome UA](https://github.com/BrettMayson/Arma3Server/blob/48d218512e8557403b395a4776850a6a25bb4bb3/workshop.py) |
| **SteamDB 工具** | ❌ | — | 集合展开走**官方 API `GetCollectionDetails`** | 服务端 | ✅ [工具页](https://steamdb.com/en/tools/steam-workshop-downloader) |
| **油猴脚本**（Skymods/Modsbase） | 转嫁第三方镜像站 | — | — | — | 🔍 [Greasy Fork](https://greasyfork.org/en/scripts/512908-steam-workshop-downloader-skymods-modsbase) |
| **商业中转**（steamwebapi.com 等） | 服务端代抓 | "buffers, caches and retries across own infrastructure" | 用自家基础设施承担限流 | 服务端缓存 | 🔍 [steamwebapi.com](https://www.steamwebapi.com/steam-429-error) |
| **网页下载器**（steamworkshop.download 系） | 服务端代抓 | — | — | 热门 mod 缓存 | ✅ 2022-05-28 成批倒闭（既有研究） |

### 1.2 可迁移的具体结论

- **✅ 30 req/min 是唯一查到的具体数字**：`steam-user` 的 `Quota::per_minute(30)` 是成熟库的保守取值。作为"社区认为安全"的参考上限，SWDM 的社区页请求频率应对齐到 ≤30/min（即间隔 ≥2s）——与本项目 `/sharedfiles/` 节流的现值同量级。
- **✅ 429 要"惩罚"限流器而非固定等待**：`steam-user` 的做法是 429 时把限流器**锁定一段时间**（penalize），全局生效，而非只让当前请求 sleep。等价于 SWDM 的 `_throttle.bump()` 自适应升档——**方向正确，应保留**。
- **✅ 端点差异化是成熟实践**：McKay 明确把库存调用迁到"限流更轻"的新端点；SWDM 已按路径前缀分档节流（`/sharedfiles/` vs `/workshop/browse/`），与之一致。
- **🔍 轻量包装器几乎没有像样的限流设计**：Geam / shadoxxhd / Husko's 一类工具的 README 只讲"用 steamcmd 下载"，未见任何 429 处理的公开记录。**它们的"能用"靠的是请求量本来就低**，不是策略多好——不可作为效仿对象。
- **🔍 WorkshopDL 的请求头/退避/并发细节确认为查不到**：闭源 Clickteam Fusion 2.5 打包（`.mfa` 源码不公开），DeepWiki 只讲架构分层（小文件 WebAPI / 大文件 SteamCMD / 1GB+ 走 SteamCMD），不讲反爬。任何声称"WorkshopDL 用 XX 头规避 429"的说法都缺源码支撑。
- **🔍 "Hex's Steam Workshop Downloader" 本次检索完全未找到**（多轮关键词 + 多引擎均无命中）。要么已下线，要么名称讹传。**标注为查无此工具**，报告中不引用其任何做法。

---

## 2. Steam 社区页限流规则：按 IP 还是按指纹？

**答案：分层，不同端点维度不同。**

| 层 / 端点 | 限流维度 | 依据 |
|---|---|---|
| **详情页** `/sharedfiles/filedetails/` | **请求头指纹**（非 IP、非速率）。缺 `Accept-Language` 的浏览器形态 UA → 429；补上即 200，8s 慢速仍 429 | ✅ 本项目 34 请求实测（旧报告 §2.1） |
| **浏览页** `/workshop/browse/`、根路径 | **无指纹门控**（坏指纹仍 200） | ✅ 本项目实测（旧报告 K/S 行） |
| **官方 Web API** `api.steampowered.com` | **配额**：100,000 次/天（Terms of Use 原文）；Valve 不公布精确每秒上限 | ✅ [Steam Web API Terms of Use](https://steamcommunity.com/dev/apiterms) / [apis.io](https://apis.io/rate-limits/steam/steam-rate-limits) |
| **非官方 Storefront API** `store.steampowered.com/api/` | **更严格的速率限流**，"在远低于官方 API 的量级就返回 429" | 🔍 [apis.io](https://apis.io/rate-limits/steam/steam-rate-limits) |
| **库存/市场/交易接口** | **按 IP**。换 key、换账号均不解决；"a handful of requests per minute"（每分钟寥寥数次） | 🔍 [steamcommunity 讨论帖](https://steamcommunity.com/discussions/forum/1/601902348018676495) / [steamwebapi.com](https://www.steamwebapi.com/steam-429-error) / [McKay 论坛](https://dev.doctormckay.com/topic/5946-new-request-limits-429-error/) |

**对 SWDM 的含义**：
- 详情页 429 **不是速率问题**——是指纹问题，已解决。用户反馈"仍易触发"，更可能是 **403（IP 层）** 或指纹回归（头被改动/某端点漏头）。
- 游戏搜索用的 `storesearch` 属于**非官方 Storefront API**，限流比官方 API 更狠——旧报告只关注了社区页，这条是**新增的风险点**：400ms 防抖可能仍偏快，建议观察该端点的 429 频率。
- **没有任何来源给出 steamcommunity.com 的官方速率上限**。能引用的只有"30 req/min"这个库作者的保守取值。

---

## 3. 匿名访问的最佳 UA 与请求头

**结论：UA 本身不是开关，`Accept-Language` 才是；但完整浏览器指纹最稳妥。**

| 做法 | 结论 | 依据 |
|---|---|---|
| 用 Chrome 等浏览器 UA 但缺 `Accept-Language` | ❌ 429 | ✅ 本项目实测（旧报告 C/G 行） |
| `curl/8.6.0` UA（无 AL） | ✅ 200 | ✅ 本项目实测（旧报告 E 行）——非浏览器 UA 落在另一档 |
| Steam 客户端 UA（无 AL） | ❌ 429 | ✅ 本项目实测（旧报告 G 行）——**换 UA 无用** |
| 默认 `python-requests` UA（无 AL） | ❌ 429 | ✅ 本项目实测（旧报告 D 行） |
| 任意 UA + 补 `Accept-Language` | ✅ 200（连默认 python UA 都 200） | ✅ 本项目实测（旧报告 N2/V4 行） |
| 竞品实践：完整 Mac Chrome UA | ✅ 业界惯例 | 🔍 BrettMayson/Arma3Server `workshop.py` 定义 `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/...` |
| 反爬通用知识：缺 AL 是经典指纹 | ✅ 印证 | 🔍 [ZenRows](https://www.zenrows.com/blog/bypass-bot-detection)："A missing `Accept-Language` header" 是反爬系统的检查项 |

**推荐头集合**（保持现状即可，均有实测或行业支撑）：
- `User-Agent`：真实 Chrome UA（保留当前值）
- `Accept-Language`：**唯一必需的承重头**（本项目实测）
- `X-Requested-With: XMLHttpRequest`：保留以扩大指纹宽度，但**不可作为豁免的依赖**（旧报告实测 N1：单独它仍 429）
- `Accept`、`Sec-Fetch-*`、`Referer`：锦上添花，不承重

**⚠️ 不要**用 Steam 客户端 UA 试图"伪装成官方客户端"——实测它与 Chrome 无 AL 同档，照样 429。

---

## 4. 依赖解析（Required items）的替代方案

**结论：无 API key 时没有已验证的纯 API 方案；有 key 时 `GetDetails` 的 `children` 是唯一官方路径。**

| 方案 | 可行性 | 依据 |
|---|---|---|
| `IPublishedFileService/GetDetails`（`includechildren`） | ✅ **官方支持**：返回字段含 `child_publishedfileid`（uint64）。但**匿名 401**（本项目实测），**必须有 API key** | ✅ [官方文档](https://partner.steamgames.com/doc/webapi/IPublishedFileService) + 本项目实测 401 |
| `ISteamRemoteStorage/GetPublishedFileDetails` | ✅ 匿名可用（200），但 **`referenced_files` 匿名恒空 → 取不到依赖** | ✅ 本项目实测 |
| `ISteamRemoteStorage/GetCollectionDetails` | 🔍 SteamDB 工具用它展开**集合（collection）**。但集合 ≠ 单个 item 的 Required items，且该端点需要 key。**不能替代详情页依赖解析** | ✅ [SteamDB 工具页](https://steamdb.com/en/tools/steam-workshop-downloader) + 🔍 鉴权要求未核实 |
| AugmentedSteam 扩展的同需求 | 🔍 [Issue #56](https://github.com/IsThereAnyDeal/AugmentedSteam/issues/56) 也想做"required items 检测"，讨论中**未给出 API 端点方案** —— 旁证"无公开 API 捷径" | 🔍 |
| 继续抓详情页 | ✅ 当前方案，指纹正确时稳定 200 | ✅ 本项目实测 |

**落地路径**（与旧报告建议 5 一致，本次未获新证据推翻）：设置页已支持填 API key → 有 key 时优先 `GetDetails(includechildren)` 取 children，无 key 回退网页抓取。**⚠️ children 是否等价于网页的 "Required items"，本次仍无法实测（无 key），落地前必须用真实 key 比对两路结果。**

---

## 5. 登录 cookie 方案：匿名 vs 登录的限流差异

**结论：查证未发现登录 cookie 能降低网页 429 的证据。登录的收益在 steamcmd 通道，不在网页通道。**

| 观察 | 结论 | 依据 |
|---|---|---|
| 详情页匿名即可得完整 111KB 页面 | 网页详情页**不要求登录**，限流与登录态无关 | ✅ 本项目实测 |
| node-steamcommunity 登录后自动带 cookie | 库设计如此，但其 429 讨论集中在**库存/交易**（IP 维度），未见"登录后网页限流放宽"的报告 | ✅ 库行为 + 🔍 限流讨论 |
| steamcmd 从 datacenter IP 匿名下载被当可疑账号 | **登录账号（带 Steam Guard）在 steamcmd 通道有实质收益**（部分游戏如 DayZ 匿名直接不可用） | 🔍 [steam-for-linux#13474](https://github.com/ValveSoftware/steam-for-linux/issues/13474) |
| 项目实测：匿名 cookie（先 GET 首页拿 sessionid + steamCountry）补到详情页请求 | ❌ **无效**（3/3 仍 429） | ✅ 本项目实测（旧报告已记） |

**⇒ 不建议为"降低 429"引入登录态。** 登录会引入账号安全、2FA、令牌管理等大量复杂度，而目标收益（网页限流）查无实证。登录只应在"某些游戏必须登录才能用 steamcmd 下载"时才引入，那是一个独立的需求。

---

## 6. 可落地的限流规避清单（按优先级）

| 优先级 | 措施 | 依据 | 风险 |
|---|---|---|---|
| **P0** | **守住 `Accept-Language`**：它是详情页 429 的唯一开关。把指纹头集合提为模块常量/配置项，规则一变就跟着改（Steam 2022-10 和 2026-07 两度收紧规则） | ✅ 本项目实测 + 🔍 ZenRows | 零 |
| **P0** | **403 走长退避 + 过期缓存兜底**：403 是 IP 层，短重试无效；依赖解析失败时返回过期缓存而非空列表 | ✅ 本项目实测分层结论 | 低 |
| **P1** | **盯住 `storesearch` 端点**：它属非官方 Storefront API，限流比官方 API 更狠，是"仍易触发 429"的新嫌疑点。观察其 429 频率，必要时放慢防抖（400ms → 1s+）或加缓存命中 | 🔍 apis.io | 低 |
| **P1** | **频率对齐 30 req/min**（间隔 ≥2s）：这是社区公认安全值的量级，也是 SWDM `/sharedfiles/` 当前节流的同量级；配合 `bump()` 自适应升档（等价 steam-user 的 penalize 机制） | 🔍 steam-user 源码 | 低 |
| **P1** | **依赖缓存持久化**：`_dep_cache` 内存 TTL 30min → 落盘 JSON。请求总量↓ = 限流风险↓，零行为改变 | ✅ 旧报告建议补遗 | 零 |
| **P2** | **有 key 时 `GetDetails` 取依赖**，绕开详情页；无 key 回退网页 | ✅ 官方文档 + ⚠️ children 语义未实测 | 中 |
| **P2** | **steamcmd 下载失败走"同会话重试"**：社区实践是超时就在同一 steamcmd 会话重贴命令直到成功；程序侧应对应"同一登录会话内重试 N 次"而非重启进程 | 🔍 社区帖 | 低 |
| **P3** | **可选：用户自填代理切换出口 IP**（应对 403 的 IP 层封锁）。不引入内置中转服务 | ✅ 旧报告结论（网页下载器倒闭史） | 中 |

---

## 7. 已证实无效的做法（不要做）

1. ❌ **单靠 `X-Requested-With` 豁免 429** —— 旧报告实测推翻（N1：仍 429）。旧记忆 `mem_2e185069` 已标 superseded。
2. ❌ **补匿名 cookie（先 GET 首页拿 sessionid/steamCountry）** —— 实测 3/3 仍 429。
3. ❌ **补 Referer / Origin** —— 实测无效。
4. ❌ **换 Steam 客户端 UA 伪装官方** —— 实测与 Chrome 无 AL 同档，照样 429。
5. ❌ **换 API key / 换账号解决 IP 维度 429** —— 社区讨论确认无效（指向 IP 维度）。
6. ❌ **服务端代抓/第三方镜像站（skymods、modsbase、steamworkshop.download 系）** —— 网页下载器 2022-05-28 成批倒闭；镜像站单点故障 + 文件注入风险。
7. ❌ **依赖 429 响应的 `Retry-After` 头** —— 详情页 429 从不返回该头（10/10）。

---

## 8. 未确证 / 查不到的（诚实标注）

- 🔍 **Hex's Steam Workshop Downloader** —— 多轮多引擎检索**完全无命中**，标注为查无此工具。
- 🔍 **WorkshopDL 的请求头/退避/并发细节** —— 闭源，DeepWiki 只讲架构分层，反爬细节**查不到**。
- 🔍 **steam-go 的具体限流数值**、**steam.py 的重试参数** —— 片段截断，数值未拿到。
- 🔍 **steamcommunity.com 的官方速率上限** —— Valve 从未公布；"30 req/min"是第三方库的保守取值，非官方数字。
- 🔍 **有 key 时 `GetDetails` 的 children 是否等价网页 Required items** —— 无 key 无法实测。
- 🔍 **登录 cookie 降低网页限流的证据** —— 查无；现有证据指向"网页限流与登录态无关"。
- 🔍 **`GetCollectionDetails` 的匿名可用性** —— 未核实（SteamDB 用它展开集合，但集合≠依赖）。
- ⚠️ **本报告所有源码级结论均基于搜索引擎片段**，未读取完整仓库/正文；引用强度自评 🔍，除标注 ✅ 者外均不应视为确证。

---

## 9. 来源汇总

**官方文档（✅）**
- [Steam Web API Terms of Use](https://steamcommunity.com/dev/apiterms) — 100,000 calls/day
- [IPublishedFileService](https://partner.steamgames.com/doc/webapi/IPublishedFileService) — `child_publishedfileid` 字段
- [Web API Overview](https://partner.steamgames.com/doc/webapi_overview) — api.steampowered.com 走 Akamai 边缘缓存
- [SteamCMD Wiki](https://developer.valvesoftware.com/wiki/SteamCMD)

**竞品源码/文档（🔍 片段）**
- [steam-user limiter.rs](https://docs.rs/steam-user/latest/src/steam_user/limiter.rs.html) — `Quota::per_minute(30)` + penalize
- [steam-user SteamUserBuilder](https://docs.rs/steam-user/latest/steam_user/client/struct.SteamUserBuilder.html) — `rate_limit(req/min, burst)` 可配置
- [steam-go Rate-Limiting-Strategy](https://github.com/gofurry/steam-go/blob/main/docs/wiki/en/Rate-Limiting-Strategy.md)
- [steam.py http.py](https://github.com/Gobot1234/steam.py/blob/master/steam/http.py)
- [node-steamcommunity Wiki](https://github.com/DoctorMcKay/node-steamcommunity/wiki/SteamCommunity) / [PR #300](https://github.com/DoctorMcKay/node-steamcommunity/pull/300)
- [WorkshopDL DeepWiki 2.2](https://deepwiki.com/imwaitingnow/WorkshopDL/2.2-download-pipeline-and-provider-backends) / [2.3 SteamCMD](https://deepwiki.com/imwaitingnow/WorkshopDL/2.3-steamcmd-integration-and-maintenance)
- [BrettMayson/Arma3Server workshop.py](https://github.com/BrettMayson/Arma3Server/blob/48d218512e8557403b395a4776850a6a25bb4bb3/workshop.py) — 完整浏览器 UA
- [SteamDB Workshop Downloader](https://steamdb.com/en/tools/steam-workshop-downloader) — GetCollectionDetails
- 轻量包装器：[Geam](https://github.com/Geam/steam_workshop_downloader) / [shadoxxhd](https://github.com/shadoxxhd/steamworkshopdownloader/) / [googprojects](https://github.com/googprojects/WorkshopDownloader) / [Husko's](https://github.com/Official-Husko/Husko-s-SteamWorkshop-Downloader)
- [Greasy Fork: Steam Workshop Downloader (Skymods/Modsbase)](https://greasyfork.org/en/scripts/512908-steam-workshop-downloader-skymods-modsbase)

**限流讨论（🔍）**
- [apis.io — Steam Rate Limits](https://apis.io/rate-limits/steam/steam-rate-limits/) — 官方无精确上限；Storefront API 更严
- [steamwebapi.com — Steam 429 指南](https://www.steamwebapi.com/steam-429-error) — 按 IP 限流、每分钟寥寥数次
- [McKay 论坛 — New request limits? (2026-07)](https://dev.doctormckay.com/topic/5946-new-request-limits-429-error/)
- [McKay 论坛 — Rate limit on steamcommunity.com](https://dev.doctormckay.com/topic/699-rate-limit-on-steamcommunitycom/)
- [steamcommunity 讨论帖 — Web API constantly rate-limited](https://steamcommunity.com/discussions/forum/1/601902348018676495)
- [steamcommunity 讨论帖 — SteamCMD Download Timeouts（重贴直到成功）](https://steamcommunity.com/discussions/forum/1/215439774859993377)
- [steam-for-linux#13474 — datacenter IP 匿名 steamcmd 被当可疑](https://github.com/ValveSoftware/steam-for-linux/issues/13474)
- [AugmentedSteam#56 — required items 检测需求](https://github.com/IsThereAnyDeal/AugmentedSteam/issues/56)

**反爬通用知识（🔍）**
- [ZenRows — Bypass Bot Detection](https://www.zenrows.com/blog/bypass-bot-detection) — 缺 `Accept-Language` 是经典指纹

**本项目实测（✅，见 `steam_429_403_research.md`）**
- 34 请求指纹矩阵 / 403 复现全部失败 / API 端点匿名鉴权对照
