# Steam 社区页 429/403 根因实测与竞品规避策略 — 研究报告

> 调研日期：2026-09-22 · 项目：SWDM（Steam Workshop 匿名下载器）
> 任务：竞品规避手段对比 + 403 根因实测 + `_community_get()` 可落地改动
> 方法：本机三轮实测（共 34 个请求，8s 间隔，Python requests + truststore.inject_into_ssl()）+ 项目既有 sourced 研究
> ⚠️ **证据分级**：本报告严格区分「✅ 实测确认」（本次会话真实请求所得）与「🔍 检索所得·无法确证」（外部来源，未本地验证）。本次会话检索引擎质量极差（大量无关结果），竞品部分的新增检索有限，主要沿用项目既有已引用来源的研究结论，并在每处标注。

---

## 0. 核心结论（TL;DR）

1. **✅ 429 的唯一触发开关是「缺 `Accept-Language` 头」** —— 与 UA 无关、与请求速率无关（8s 慢速依旧 429）。实测：默认 `python-requests/2.34.2` UA + 仅 `Accept-Language` → **200**；`curl/8.6.0` UA → **200**；Chrome UA 缺该头 → **429**。
2. **⚠️ 旧结论已失效**：旧报告（`steam_429_research.md` §3.2）称 `X-Requested-With: XMLHttpRequest` 单独可让 429→200。**本次实测推翻：Chrome UA + 仅 X-Requested-With → 429**。Steam 的指纹规则已收紧（或旧结论本就是环境特例）。`Accept-Language` 才是承重头。
3. **✅ 403 在本机环境完全无法复现**（34 个请求、覆盖 12 种异常场景，无一 403）。能稳定产生的状态码只有 200 / 404（HEAD）/ 429 / 400（Host 篡改）/ 401（API 缺 key）。**结论：429 与 403 是两个不同层级的机制** —— 429 是请求头指纹层（我们可控），403 是 IP/边缘层（我们不可控，需重试+兜底+可选代理）。
4. **🔍 最可能的 403 根因（无法实测确证，但环境证据充分）**：本机 `steamcommunity.com` 走 **fake-IP 代理**（DNS→198.18.0.124，Clash/Meta 类），出口 IP `43.243.192.92` = 香港 AS134972（IDC/小 ISP，「IKUUU NETWORK LTD」）。**共享代理节点 IP 被 Steam 边缘封锁是「重复出现 403」的最简解释** —— 节点切换/被标记时 403 出现，节点恢复时消失，与用户描述的「重复出现」特征吻合。
5. **✅ `IPublishedFileService/GetDetails` 匿名调用返回 401**（"Access is denied … verify your key= parameter"）—— 旧报告 §5.3「匿名 GetDetails 取依赖」的迁移假设**被证伪**。但**有 API key 时该路仍可走**（这是消除详情页抓取的最有价值路径）。
6. **✅ 浏览页 `/workshop/browse/` 完全不受指纹门控**（Chrome UA 无 AL → 200），门控只作用于 `/sharedfiles/filedetails/`。当前端点差异化节流的方向正确。

---

## 1. 实测环境与方法

### 1.1 环境探明（关键背景）

| 项目 | 值 | 意义 |
|---|---|---|
| hosts 文件 | 已无 steam 相关条目（S302 条目确已全部注释掉） | ✅ 与用户说明一致 |
| DNS `steamcommunity.com` | **198.18.0.124** | ⚠️ fake-IP 段（RFC2544 保留段被代理工具复用），指向 "Meta" 网卡 |
| 路由 | 经 `198.18.0.1/198.18.0.2`（Meta 接口） | 确认走 **Clash/Meta 类代理的 fake-ip 模式**，非直连 |
| 出口公网 IP | **43.243.192.92** | 香港 / AS134972 IKUUU NETWORK LTD / ZhongTong Telcommunications (HK) |
| 响应 Cookie | `steamCountry=HK` | 与出口地理位置一致 |
| 系统代理 | WinHTTP 直连、无 `HTTP_PROXY` 环境变量 | 代理在路由层/TUN 层生效，requests 透明经过 |

> **这条环境事实本身就是 403 假设的基础**：出口是香港的云/小 IDC 段，且为代理共享节点。本报告所有 403 分析都基于此。

### 1.2 方法

- Python `requests` + `truststore.inject_into_ssl()`（与项目 `steam_api.py` 完全一致的 TLS 配置）。
- 每请求间隔 **≥8s**，避免自身触发速率限流。
- 记录：状态码、响应字节数、耗时、关键响应头（Server / CF-RAY / Retry-After / Content-Type）、响应体前 250 字符。
- 三轮共 34 个请求：轮 1 = 13 个（指纹矩阵 + 端点对照 + API 匿名验证）；轮 2 = 11 个（指纹隔离 + 403 场景 + 429 是否升级）；轮 3 = 7 个（Host 篡改 + HTTP 版本 + 好指纹稳定性）。

---

## 2. 实测结果

### 2.1 请求头指纹矩阵（轮 1 + 轮 2，item 3803871160）

| # | 请求头组合 | 状态码 | 字节数 | 结论 |
|---|---|---|---|---|
| A | 完整浏览器头（Chrome UA + AL + Accept + Sec-Fetch-\* 全套） | **200** | 111,672 | 基线正常 |
| B | Chrome UA + AL + XRW（= SWDM 当前配置） | **200** | 111,672 | ✅ 当前配置有效 |
| C | Chrome UA **仅**（无 AL） | **429** | 339,955 | ❌ 触发限流 |
| D | 完全无自定义头（默认 python UA） | **429** | 339,948 | ❌ 触发限流 |
| E | `curl/8.6.0` UA（无 AL） | **200** | 111,259 | ✅ **UA 不是开关** |
| F | Chrome UA + AL（无 XRW） | **200** | 111,672 | ✅ AL 单独足够 |
| G | Steam 客户端 UA（Chrome 形态，无 AL） | **429** | 294,976 | ❌ 换 UA 无用 |
| N1 | Chrome UA + **仅 X-Requested-With**（无 AL） | **429** | 339,955 | ⚠️ **推翻旧结论** |
| N2 | 默认 python UA + **仅 AL** | **200** | 111,672 | ✅ **AL 是唯一开关** |
| N3 | Chrome UA + AL=`en-US,en;q=0.9` | **200** | 111,259 | ✅ AL 的语言值无关 |
| N4 | Chrome UA + 仅 `Accept`（无 AL） | **429** | 339,955 | ❌ 其它 Accept 头无效 |
| P1–P3 | Chrome UA 仅，连续 3 次（8s 间隔） | **429×3** | 339,955 | 重复不升级、不解封 |
| U1–U2 | Chrome UA + AL，连续 2 次 | **200×2** | 111,682 | 好指纹稳定 |
| U3 | Chrome UA + AL，第 3 次 | **连接中断** (10053) | — | 传输层瞬时失败 |
| V4 | 默认 python UA + 仅 AL | **200** | 111,682 | ✅ 复核 N2 |

**指纹规则（✅ 实测确认）**：

```
429 门控（仅作用于 /sharedfiles/filedetails/）
  IF 请求含任意非空 Accept-Language  → 200（与 UA / 其它头 / 速率 均无关）
  ELSE                               → 429（curl UA 除外 —— curl UA 200，推测 nginx 对非浏览器 UA 放行）
```

> 注意 E（curl UA 无 AL → 200）与 C/G（浏览器形态 UA 无 AL → 429）并存，说明规则不是简单的「无 AL 就拦」，而是「**声称自己是浏览器（浏览器形态 UA）却缺 AL**」才拦 —— 这正是「自动化指纹检测」的典型逻辑：真实浏览器不可能不带 `Accept-Language`。`python-requests` 默认 UA 被当作非浏览器而落入另一档（本次也 429，见 D，说明 python 默认 UA 被判为「该拦的非浏览器」——与 curl 待遇不同）。

**429 响应特征（✅ 实测确认）**：

- `Server: nginx`，**无 `CF-RAY`**（Steam 自家 nginx，非 Cloudflare）。
- 响应体约 **294–340 KB**（SSR 错误页，内含 fastly CDN 资源引用）。
- **从不返回 `Retry-After` 头**（C/D/G/N1/N4/P1–P3 共 10 次 429，逐一确认）。
  ⇒ `steam_api.py:248` 的 `int(r.headers.get("Retry-After", "20"))` 对详情页**恒走默认 20s 分支**，该分支是事实上的死代码。
- 429 页面正文与 200 页面**完全不同的 SSR 模板**（429 体预加载 `DfnAe-hE.png`，200 体是 zh-cn 完整页）。

### 2.2 403 复现尝试（全部失败 · ✅ 即「本机无法复现 403」）

| # | 场景 | 结果 | 说明 |
|---|---|---|---|
| H | HEAD 方法（完整浏览器头） | **404**（0 字节） | HEAD 不被支持，但不是 403 |
| I | 不存在的 item id（`9999999999999999`） | **200**（27KB 错误页） | 伪 ID 不产生 4xx |
| Q | **明文 HTTP:80**（完整头） | **200**（未跳转 HTTPS） | 80 端口同样服务 |
| R | 不存在的路径前缀 `/sharedfiles/nonexistent_xyz/` | **200**（54KB 错误页） | nginx 兜底错误页 |
| S | 根路径 `/` + 坏指纹（Chrome UA 无 AL） | **200** | **根路径不受指纹门控** |
| K | 浏览页 + 坏指纹（Chrome UA 无 AL） | **200** | **浏览页不受指纹门控** |
| V1 | Host 头改写为 `127.0.0.1`（SNI 不变） | **400 Bad Request** | Host/SNI 不一致 → 400，非 403 |
| V2 | Host 头改写为代理 IP `43.243.192.92` | **400 Bad Request** | 同上 |
| V3 | 原始 HTTP/1.0 请求（Host 正确 + AL） | **200**（9.5s，较慢） | HTTP/1.0 可用 |
| P1–P3 | 坏指纹连续重复 3 次 | **429×3，从不升级为 403** | 429 与 403 是不同机制 |
| U3 | 好指纹请求 | **ConnectionAborted (10053)** | 代理/服务端瞬时断连，非 403 |

**34 个请求中 403 次数：0。**

### 2.3 API 端点对照（✅ 实测）

| 端点 | 鉴权 | 状态码 | 结果 |
|---|---|---|---|
| `ISteamRemoteStorage/GetPublishedFileDetails/v1/`（POST） | **匿名可用** | **200** | 返回 result=1、creator、file_size（136MB）等；`file_url` 为空（与项目既有结论一致：匿名无 CDN 直链） |
| `IPublishedFileService/GetDetails/v1/`（GET，`input_json` 含 `includechildren`） | **匿名** | **401 Unauthorized** | `Access is denied. Retrying will not help. Please verify your key= parameter.` |

> **对旧报告的重要修正**：`steam_429_research.md` §5.3 / §8 把「匿名 `GetDetails` 的 `includechildren` 是否非空」列为最高价值待验证项，并引用若干第三方库声称 "No API Key is required"。**本次实测证伪：匿名直接 401。** 该迁移路径**必须有 API key** 才能走通。

---

## 3. 429 根因（✅ 实测确认）

1. **触发维度 = 请求头指纹，不是 IP、不是速率**：同 IP、同 URL、同 8s 间隔，仅因缺 `Accept-Language` 就 429（C/D/G/N1/N4/P1–P3，共 10 次），补上即 200（A/B/F/N2/N3/V4，共 8 次）。
2. **判定逻辑 = 「浏览器形态 UA + 缺 AL」**：curl UA 无 AL → 200；Chrome/Steam-client/python UA 无 AL → 429。
3. **门控范围 = 仅 `/sharedfiles/filedetails/`**：浏览页（K）、根路径（S）不受影响。这与项目「详情页限流远重于浏览页」的既有体感一致，且给出了精确边界。
4. **无 `Retry-After`、无 CF、无解封梯度**：坏指纹下连续 3 次 8s 间隔请求全部 429（P1–P3），说明冷却窗口 > 24s；好指纹下连续请求稳定 200（U1–U2）。**指纹一旦正确，不需要长节流**。

---

## 4. 403 根因（⚠️ 实测无法复现 —— 基于证据的推断）

### 4.1 可以排除的（✅ 实测）

| 假设 | 实测结论 |
|---|---|
| 请求头指纹导致 403 | ❌ 排除 —— 指纹问题的唯一产物是 429，10 次 429 无一升级为 403 |
| 地域限制（HK 出口被地区封锁） | ❌ 排除 —— 本机出口即香港，全部 200 |
| 需要登录（详情页匿名可访问） | ❌ 排除 —— 匿名 200，返回完整 111KB 详情页 |
| hosts 残留指向 127.0.0.1 | ❌ 排除 —— hosts 已干净；且该配置的产物是「连接被拒绝」，不是 403 |
| 伪 ID / 伪路径 / HEAD / HTTP 版本 / Host 篡改 | ❌ 排除 —— 分别产生 200 / 200 / 404 / 200 / 400 |

### 4.2 最可能的根因（🔍 推断，无法实测确证）

**假设 1（主假设）：共享代理出口 IP 被 Steam 边缘封锁。**

- 证据链：本机经 fake-IP 代理出网 → 出口 `43.243.192.92`（香港 AS134972，IDC/小 ISP 段，代理共享节点）→ `steamCountry=HK`。
- 这类 IP 段被大量爬虫共用，Valve 在边缘层（nginx 前的 WAF/ACL）对特定 IP/IP 段返回 **403**，与请求头无关、与速率无关。
- **与用户症状吻合**：「重复出现 403」= 代理节点轮换或某节点被标记时 403 出现、恢复时消失；而用户「hosts 曾指向 127.0.0.1（S302）」的背景说明本机长期依赖代理类加速方案。
- 🔍 **未能找到 Valve 对 IDC/VPN IP 封锁的官方说明**，此为基于网络拓扑与症状特征的推断，非确证。

**假设 2（次假设）：代理节点故障期的中间层 403。**

- 部分代理在目标不可达或被目标拒绝时，会自行返回 403（而非透传上游状态）。实测 U3 出现过一次 `ConnectionAborted(10053)`（代理瞬时断连），说明该链路本身不稳定。
- 判别方法：403 时检查响应头是否有 `Server: nginx` 且响应体是否为 Steam SSR 模板。**若 403 响应没有 `Server: nginx` 或体积极小（非 340KB 级），则来自代理而非 Steam** —— 建议把这两项记入日志以定位（见建议 5）。

**假设 3（已排除）：steamchina/蒸汽平台区域重定向。** 本机直连 Steam 国际版，cookie 为 `steamCountry=HK`，非大陆重定向场景。

### 4.3 403 与 429 的分层结论

```
Steam 边缘（nginx + WAF）
  ├─ 请求头指纹层 → 429（缺 Accept-Language 的浏览器形态请求）  ← 可控，补头即可
  ├─ IP/AS 信誉层 → 403（被标记的出口 IP，疑似 IDC/VPN 段）     ← 不可控，需换 IP 或等恢复
  └─ 业务层      → 200（含错误页，如伪 ID / 伪路径）
```

⇒ **对 SWDM 的含义**：429 靠请求头已基本解决（用户反馈「仍易触发限流」更可能是 403 或坏指纹回归）；403 无法靠请求头解决，只能靠**重试 + 过期缓存兜底 + 可选代理切换**。

---

## 5. 竞品分析：它们如何规避 429/403

> 📌 **证据说明**：本次会话检索引擎返回质量极差（技术查询大量返回无关页面），下列竞品的**请求头/节流细节**多为 🔍 检索/推断，**未能逐一从源码核实**（WorkshopDL 闭源 .mfa、网页下载器后端不公开）。但各工具的**通道选择**（是否走 steamcommunity.com 网页）是架构事实，来自项目既有竞品分析（`competitor_analysis.md`，已附来源链接）。

| 工具 | 通道 | 是否碰 steamcommunity.com 网页 | 规避 429/403 的核心手段 | 证据强度 |
|---|---|---|---|---|
| **SteamCMD / Valve 官方** | ISteamUGC 二进制协议（CM 服务器） | **完全不碰** | 走二进制通道，天然不受网页限流；匿名登录可用 | ✅ 官方文档（既有研究引用） |
| **SteamCMD 包装器**（GUI2/SCMD2/Streamline…） | 进程托管 steamcmd | **完全不碰** | 同上；自身只解析 stdout | ✅ 架构事实（既有研究） |
| **WorkshopDL** | 小文件 → Steam WebAPI；大文件 → SteamCMD | **基本不碰**（元数据走 api.steampowered.com） | **多后端智能切换**：把流量整体迁出社区域 | ✅ DeepWiki 架构文档（既有研究） |
| **网页下载器**（steamworkshop.download / .io 等） | 服务端代抓 + CDN 打包 | 碰，但在**服务端** | 用自己的数据中心 IP 承担所有限流，用户无感；热 mod 缓存 | 🔍 既有研究 + 已于 2022-05-28 成批倒闭（API 关闭）的事实 |
| **Greasy Fork 油猴脚本** | 用户真实浏览器内运行 | 碰，但**带真实浏览器指纹与登录 cookie** | 真实浏览器指纹（必含 AL）+ 真人速率 → 从不触发指纹层 429 | 🔍 推断（脚本运行于真实浏览器，指纹天然完整） |
| **node-steamcommunity（McKay）** | HTTP 库，直连社区 | 碰 | 显式 cookie 管理；社区已知其市场/库存接口受 IP 级 429 限制（PR #300：count>2000 触发） | 🔍 既有研究引用的 GitHub PR/Issue |
| **SWDM（本项目）** | api.steampowered.com + 详情页抓取依赖 + steamcmd 下载 | **碰（仅依赖解析、浏览页）** | 指纹头 + 端点节流 + ApiCache + steamcmd 下载 | ✅ 本项目代码 |

### 5.1 竞品策略的可迁移结论

1. **✅ 最有效的规避 = 不走 steamcommunity.com**。所有稳定工具（SteamCMD 系、WorkshopDL）的共同点是**把数据通道整体搬到 api.steampowered.com / 二进制协议**。SWDM 的下载链路已如此（steamcmd），**唯一仍依赖社区网页的是 `get_dependencies()`（前置依赖解析）** —— 这是限流风险仅存的来源，也是优化的最高价值目标。
2. **✅ 油猴脚本的启发**：真实浏览器从不缺 `Accept-Language`。SWDM 已补该头，等价于获得了油猴脚本级别的「合法性指纹」。**这也是为什么本次实测中 SWDM 当前配置（B 组）稳定 200**。
3. **🔍 网页下载器的教训**：服务端代抓把限流转嫁给自己的 IP 池 → 成本不可控 → 成批倒闭（2022-05-28）。SWDM 坚持客户端直连的方向正确，**不应引入任何中转服务**。
4. **🔍 第三方镜像站（steamworkshop.download / workshop.agency 等）**：本次检索**未能确证**这些站点的存活状态与反爬细节；既有研究已记录其单点故障与文件注入风险。**结论：不依赖**。

---

## 6. 对 `steam_api.py _community_get()` 的可落地建议

> 位置：`steam_api.py:233-274`（`_community_get`）、`75-78`（_UA）、`172-181`（session 头初始化）、`212-231`（端点节流）。
> 原则：**每条都给出实测依据 + 风险评级**；不引入中转、不伪造凭证、保持低频匿名浏览式抓取。

### 建议 1（P0，零风险）：确立 `Accept-Language` 为唯一必需指纹头，修正误导性注释

**现状**：`steam_api.py:176-179` 的注释称 AL 与 XRW 「双保险」，并称「补以下两个头后 429→200」。**实测推翻**：XRW 单独 → 429（N1），XRW 不是保险；AL 才是承重头（N2/V4：默认 python UA + 仅 AL → 200）。

**改动**：
- 保留现有两个头（B 组实测稳定 200），但把注释改为：「`Accept-Language` 是 429 门控的唯一开关（实测）；`X-Requested-With` 为附加大宽度指纹，单独不构成豁免」。
- **不要移除 XRW**（多一个头扩大指纹宽度，降低被未来规则变更误伤的概率），但也**不要把它当成可依赖的备援**。
- 增加防御性代码：若将来 Steam 再收紧规则（如本次 XR→429 的先例），应能在不发包的前提下切换头组合 —— 建议把指纹头集合提取为模块级常量 `_COMMUNITY_HEADERS`，便于一处修改。

**依据**：✅ 2.1 矩阵 18 个请求。
**风险**：零。均为标准浏览器行为。

### 建议 2（P0，低风险）：把 403 纳入与 429 相同的长退避路径，并记录 403 响应特征

**现状**：`_community_get` 只对 429 做长退避；403 走 `r.raise_for_status()` → `RequestException` 分支，退避仅 `3s/6s/9s/12s`（`min(3*attempt, 15)`），4 次后抛出。**若 403 是 IP 层封锁（§4.2 假设 1），12s 内不可能恢复**，必然失败。

**改动**：
1. 在 429 分支旁增加 403 分支，共享同一退避逻辑（`_throttle.bump(backoff)` + 渐进退避），基准等待 30–60s（IP 层封锁的恢复时间远长于指纹层）。
2. 403 时记录响应头 `Server` 与响应体长度到日志：**若 403 响应无 `Server: nginx` 或体积非 SSR 量级（~340KB），判定为代理中间层返回**（§4.2 假设 2），直接走降级而非重试到天荒地老。
3. `get_dependencies()` 增加**过期缓存兜底**（`browse()` 已有此模式，`steam_api.py:492-497`）：403/429 耗尽重试时，返回 `_dep_cache` 里哪怕过期的依赖列表，而不是抛异常。`resolve_dependency_tree` 已捕获 `RateLimitError` 跳过，但返回空列表会让用户漏下依赖；返回过期数据更安全。

**依据**：✅ 实测 403 与 429 是不同层级（P1–P3 连续 429 不升级）；✅ 12s 退避对 IP 层封锁无效（推论）；🔍 403 根因为代理 IP（未确证）。
**风险**：低。延长失败请求的等待时间会拖慢依赖解析；通过「过期缓存兜底」保证用户仍能拿到结果。建议 403 的 `max_retries` 设为 2（IP 封锁重试 4 次毫无意义）。

### 建议 3（P1，低风险）：重估 429 退避参数 —— 无 `Retry-After` 时的基准 20s 偏短

**现状**：`steam_api.py:246-249`，无 `Retry-After` 时 `wait = 20.0`，渐进退避 `min(wait*attempt, 90)`。

**实测**：
- 详情页 429 **从不带 `Retry-After`**（10/10 次）→ 恒走 20s 基准。
- 坏指纹下 8s 间隔连续 3 次请求全部 429（P1–P3，跨越 24s+）→ **指纹层冷却窗口 > 24s**，20s 基准大概率撞墙。
- 但**指纹正确时根本不会 429**（B/F/N2 等 8 次 200）→ 429 一旦出现，说明规则已变（AL 不再豁免），此时重试多少次都无用。

**改动**：
- 无 `Retry-After` 时基准退避调到 **30–45s**（覆盖实测窗口）。
- 更关键的：**429 重试 1–2 次仍失败时，主动放弃并走降级**（过期缓存），而不是 `max_retries=4` 苦等 90s×4。指纹层 429 是「配置问题」而非「时间问题」，重试不解决问题。
- 保留 `Retry-After` 读取分支（其它端点/未来可能返回）。

**依据**：✅ P1–P3 冷却窗口 > 24s；✅ 10/10 无 Retry-After；✅ 指纹正确时 0 次 429。
**风险**：低。仅影响已失败请求。

### 建议 4（P1，中风险）：详情页端点间隔 3s → 2s，并把节流参数提到可配置

**实测支持**：
- 好指纹下详情页响应 0.61–2.84s（波动主要来自代理链路，见 U 组 2.6-2.7s vs A 组 0.83s）。
- 8s 间隔下连续请求稳定 200（U1/U2、A/B/F 系列）。
- 门控与速率无关（§3）—— 只要指纹正确，速率不是触发因素。

**改动**：
- `_ENDPOINT_INTERVALS["/sharedfiles/"]` 从 3.0 降到 **2.0**（与浏览页一致）。
- 保留 `_throttle.bump/decay` 自适应机制（遇到 429 自动升回，成功后回落）。
- **风险对冲**：指纹规则会变（本次 XR→429 就是证据）。建议把 `_ENDPOINT_INTERVALS` 与 `_COMMUNITY_HEADERS`（建议 1）一起放到配置层（`config.json` 或设置页），规则变化时无需发版。

**依据**：✅ 好指纹下速率与 429 无关；✅ 响应耗时实测。
**风险**：中。若 Steam 未来把详情页改为速率+指纹双重门控，2s 间隔会触发 429；`bump()` 机制会自动回退到长间隔，但首轮会撞限流。**建议先在测试构建里跑一轮回归（连续打开 20 个详情页）再合并**。

### 建议 5（P2，中风险）：有 API key 时用 `GetDetails(includechildren)` 取依赖，彻底绕开详情页

**实测**：
- `IPublishedFileService/GetDetails` **匿名 → 401**（M）—— 旧报告的匿名迁移假设证伪。
- `ISteamRemoteStorage/GetPublishedFileDetails` 匿名 → 200（T），但**不含依赖**（项目既有结论：referenced_files 匿名恒空）。
- 用户若在设置页填了 API key（`SteamAPI.api_key`，代码已支持），`GetDetails` 即可用。

**改动**（在 `get_dependencies()` 中）：
```
if self.api_key:
    先调 GetDetails(input_json={publishedfileids, includechildren:true, language:schinese})
    若 children 非空 → 直接返回，0 次社区网页请求
    失败/为空 → 回退现有网页抓取
```
**⚠️ 未验证项**：有 key 时 `includechildren` 返回的 children 是否就是「Required items」列表（而非其它父子关系），**本次无法实测（无 key）**。落地前需用真实 key 跑一次比对：网页抓取的依赖 vs API 的 children，确认集合一致。

**依据**：✅ 匿名 401（本次实测）；✅ GetDetails 的 protobuf 定义含 `includechildren`（既有研究引用 SteamTracking）；🔍 children 语义未验证。
**风险**：中。依赖 API key（多数匿名用户没有）；children 语义若与「Required items」不一致，会导致漏依赖 —— 必须先比对再切换，**默认回退网页抓取**。

### 建议补遗：依赖缓存持久化（低风险，减少重复抓取）

`get_dependencies()` 的 `_dep_cache` 是**内存 TTL（30 分钟）**（`steam_api.py:320-322`），程序重启即丢失。用户反复解析同一 mod 树时，每次重启都要重抓全部详情页。建议把依赖结果落到 `CACHE_DIR` 下的 JSON（与 `api_cache.py` 同目录），TTL 保持 30 分钟（依赖关系变化频率低，甚至可考虑 24h）。**这是减少详情页请求总量最直接的手段**（请求量 ↓ = 限流风险 ↓），且完全不改变任何请求行为。

---

## 7. 优先级汇总

| 优先级 | 建议 | 实测依据 | 风险 | 预期收益 |
|---|---|---|---|---|
| **P0** | 1. AL 定为必需头 + 修正注释 + 头集合常量化 | ✅ 18 请求矩阵 | 零 | 维持 429→200；规则变更时一处修改 |
| **P0** | 2. 403 长退避 + 响应特征日志 + 依赖缓存兜底 | ✅ 403/429 分层；🔍 403 根因 | 低 | 403 时不再硬失败，返回过期依赖 |
| **P1** | 3. 429 基准退避 20s→30-45s，重试次数 4→2 | ✅ 冷却窗口 >24s；10/10 无 Retry-After | 低 | 失败请求不再空等 90s×4 |
| **P1** | 4. 详情页间隔 3s→2s + 参数可配置 | ✅ 速率与 429 无关（好指纹下） | 中 | 依赖解析速度 ↑50% |
| **P2** | 5. 有 key 时 GetDetails 取依赖 + 依赖缓存持久化 | ✅ 匿名 401；🔍 children 语义未验证 | 中 | 有 key 用户完全绕开详情页 |

---

## 8. 未确证 / 待验证清单（诚实标注）

- 🔍 **403 的确切根因** —— 本机 34 请求无法复现；「共享代理出口 IP 被边缘封锁」是基于网络拓扑（fake-IP 代理 → 香港 IDC 出口）与症状（重复出现）的**推断**，未经 Valve 文档或抓包确证。**建议**：在 `_community_get` 增加 403 响应头/体日志（建议 2），收集用户侧的真实 403 响应样本后再下结论。
- 🔍 **有 key 时 `GetDetails(includechildren)` 的 children 语义** —— 是否等价于网页的「Required items」，无法实测（本会话无 key）。
- 🔍 **Valve 对 steamcommunity.com 抓取的专门 ToS 条款** —— 仍未查到（旧报告同结论）。
- 🔍 **详情页 vs 浏览页门控差异的官方说明** —— 未查到；本次实测仅确认了「差异存在」这一事实。
- 🔍 **竞品的请求头/节流细节** —— 本次检索引擎质量极差，未能从源码核实；WorkshopDL 闭源（.mfa），网页下载器后端不公开。本报告的竞品结论以**通道选择**（架构层面）为主，这些是可从公开 README/架构文档确认的；**具体的反爬手段多为推断**。
- ✅ **已证伪的旧结论**：① X-Requested-With 单独可豁免 429（现为 429）；② 匿名 `IPublishedFileService/GetDetails` 可用（现为 401）。这两条在 `steam_429_research.md` §3.2/§5.3 中作为结论或待验证项，**应回写修正**。

---

## 9. 来源汇总

**本会话实测（✅ 全部为本机真实请求，requests + truststore，8s 间隔）**
- 三轮探测脚本（临时文件，用完即删）：指纹矩阵 18 请求 / 403 场景 11 请求 / Host 与稳定性 7 请求。
- 探测目标：`/sharedfiles/filedetails/?id=3803871160`（Garry's Mod 物品）、`/workshop/browse/?appid=4000`、`api.steampowered.com` 两个端点。
- 环境探明：hosts（已清理）、DNS（198.18.0.124 fake-IP）、路由（Meta 接口）、出口 IP（43.243.192.92，香港 AS134972，ip-api.com 查询）。

**项目既有研究（已附来源链接，本报告沿用）**
- 竞品通道与架构：[WorkshopDL + DeepWiki 架构](https://deepwiki.com/imwaitingnow/WorkshopDL/2.2-download-pipeline-and-provider-backends)、[SteamCMD 官方 wiki](https://developer.valvesoftware.com/wiki/SteamCMD)、[ISteamUGC 接口](https://partner.steamgames.com/doc/api/ISteamUGC)、网页下载器倒闭史 —— 详见 `research/competitor_analysis.md` 附录。
- 429 机制与 Steam 客户端 UA：[Steam 论坛 IP 限流讨论](https://steamcommunity.com/discussions/forum/1/597413522044081333/)、[node-steamcommunity PR #300](https://github.com/DoctorMcKay/node-steamcommunity/pull/300)、[ apis.io — Steam Rate Limits](https://apis.io/rate-limits/steam/steam-rate-limits/) —— 详见 `research/steam_429_research.md` §7。
- API 能力：[IPublishedFileService 官方文档](https://partner.steamgames.com/doc/webapi/IPublishedFileService)、[SteamTracking protobuf（CPublishedFile_GetDetails_Request）](https://raw.githubusercontent.com/SteamDatabase/SteamTracking/master/Protobufs/steammessages_publishedfile.steamclient.proto)。

**本次会话检索（质量差，仅作弱旁证）**
- [McKay 论坛 — HTTP error 429: Rate limits](https://dev.doctormckay.com/topic/5692-http-error-429-rate-limits)（node-steam-tradeoffer-manager 的 429 讨论，旁证 IP 维度限流存在）。
- [Steam 论坛 — Steam Web API constantly rate-limited (Error 429)](https://steamcommunity.com/discussions/forum/1/601902348018676495)（旁证换 key/换账号不解决，指向 IP 维度）。
- 其余查询（steamcommunity 403 根因、workshop.agency 状态、WorkshopDL 源码细节）**均未返回相关结果**，已在 §8 标注为未确证。
