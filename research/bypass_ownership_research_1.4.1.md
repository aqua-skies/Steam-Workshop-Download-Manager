# 绕过 Steam 正版限制与 mod 镜像生态研究报告

> 2026-09-29 · SWDM 1.4.1 调研输入 · 方法：web_search/exa + GitHub API + 仓库既有实测复核 + Valve 官方 issue 原文
> 声明：本研究只调查机制与现状，未下载任何破解工具、未获取任何账户凭据、未实施绕过。

## 一、steamcmd anonymous 能力边界与正版校验机制

**判据在 App 级，不在物品级。** 工坊物品下载（`workshop_download_item`）与游戏下载走同一条内容管道；匿名会话只持有"匿名可下载"app 的 license（entitlement）。某 app 的工坊内容是否对匿名开放，由该 app 的 depot 配置/Valve 策略决定，**没有公开的"anonymous downloadable"标志清单，API 也查不到**——`IPublishedFileService/GetDetails` 匿名直接 401（项目实测，见 [research/steam_429_403_research.md](steam_429_403_research.md)），连"该物品是否需要所有权"都无法预判，只能下载失败时才知道。

**实证（三档）**：
- ✅ 匿名可用：GMod(4000) 等多数"工坊内容不校验所有权"的游戏（项目实测 + [workshop_api_research.md](workshop_api_research.md) §4）
- ❌ 匿名不可用：**DayZ(app 221100)**——Valve 官方 issue [steam-for-linux#13474](https://github.com/ValveSoftware/steam-for-linux/issues/13474)（2026-07-31，仍开）原文："For DayZ specifically, anonymous SteamCMD does not work… **A Steam account is required, and Workshop downloads are tied to the owning account** for app 221100"；Barotrauma issue #7707 同样匿名失败（2021）
- ⚠️ 该 issue 还指出：`workshop_download_item` 报 `I/O Operation Failed` 时不区分 entitlement / auth / Steam Guard / 限流——**失败原因不可读是公认痛点**，对 SWDM 的"item 级失败原因枚举"是直接需求佐证。

## 二、CDN 直链的匿名边界

**CDN 直链不是绕过手段，它本身就是正版校验的一环。** 项目既有实测（[steam_429_403_research.md](steam_429_403_research.md) §107）：`ISteamRemoteStorage/GetPublishedFileDetails/v1` 匿名返回 200（含 file_size/creator），但 **`file_url` 恒为空**；带签名的 CDN 直链（cdn.steamusercontent.com 等）只在登录态下发。代码佐证：`providers/cdn.py:3`「For anonymous users the resolved file_url is empty (a Steam restriction)」、`settings_tab.py:158`、`steam_api.py:183`。

结论：**Valve 把所有权校验前置到了 file_url 签名发放环节**。匿名能拿到 file_url 的物品 = steamcmd 匿名也能下的物品，权限同源。本次环境 api.steampowered.com 被 SNI 阻断（TCP 443 通、TLS 握手失败），无法补测"受限物品 file_url 是否存在"，但既有实测已给出答案：匿名恒空，与物品是否受限无关。

## 三、其他工具 / 代下服务的机制与兴衰

**DepotDownloader / SteamKit（SteamRE，C#）**：Steam3 会话 → `RequestDepotKey` 请求 depot 密钥 → `AccountHasAccess` 校验。depot key **只发给拥有该 app license 的账号**，匿名拿到空 key → 内容 chunk 无法解密。这说明：**付费 app 的所有权校验在内容解密层**；而工坊物品是公开未加密内容，所以工坊的限制**纯在 license 检查**这一层。

**🔴 合规红线 — 注入类工具（原理层面，仅研究，不获取）**：
- **CreamAPI / SmokeAPI / ScreamAPI**：替换/钩挂 `steam_api.dll`，伪造"用户拥有该 App/DLC"的 Steam API 返回（来源描述："a DLL file replacement program designed to bypass the Steam DRM"）——本地伪装，不产生真实下载权
- **GreenLuma**：修改 Steam 客户端 DLL 解锁 app 清单，同属 DRM 绕过
- **Steamless**：SteamStub DRM 脱壳
- **法律定性**：绕过技术保护措施（DMCA §1201 及各国同类法）+ 违反 [Steam 订阅协议](https://store.steampowered.com/subscriber_agreement/)反向工程禁止条款（[TOS Tracker](https://tostracker.app/document/steam/clause/reverse-engineering)）= **违法红线**。SWDM 是公开仓库的匿名工具，**任何此类方案不得纳入**。

**代下服务兴衰（一条被持续封堵的路）**：
| 服务 | 兴衰 | 证据 |
|---|---|---|
| steamworkshopdownloader.io | 2022 年下载账号被 Steam **批量禁用**（"The steam accounts u/swd_io used to fetch downloads… are getting disabled"）；2026-03 **域名被售/过期** | [r/swd_io](https://www.reddit.com/r/swd_io/comments/urw9pm/)、[r/gmod](https://www.reddit.com/r/gmod/comments/1rforiz/) |
| steamworkshop.download | 2024-09 起 "no longer works"；早有缓存过期问题（ PSA 2020）；HTTP 明文、无 API | [r/CrackSupport](https://www.reddit.com/r/CrackSupport/comments/1c687vb/)、[r/civ](https://www.reddit.com/r/civ/comments/h7ihps/) |
| Husko 依赖 swd.io | 后端关停 → 工具死亡 | 前轮竞品调研 |

**规律**：代下服务 = 把账号池从仓库搬到服务端，**合规风险不变（SSA 禁止账户共享）**，只是延迟爆发。Valve 2022 封号潮 → 2026 域名出售，说明这条路被持续打击。WorkshopDL README 的定论最具代表性："**most of the popular workshop downloading websites have shutdown or instruct users to download & use SteamCMD**"。

## 四、镜像站与社区存档生态现状

**不存在成熟的公共工坊镜像站。** 全网检索 "workshop mirror / backup / archive" 只有个体项目，且全部依赖 steamcmd：

| 项目 | star | 机制 |
|---|---|---|
| wertercatt/steam-workshop-scraper | 5 | Python 存档脚本 |
| ethdew19/SteamWorkshopArchiver | 1 | 存入本地 SQLite |
| pairofcrocs/steam-workshop-archiver | 0 | 自托管 web app（steamcmd + 定时任务） |
| c-ridgeway/node-workshop-downloader | — | 全量下载公共工坊物品 |

**关键结论：这些项目全部受同一正版限制约束**——它们不是绕过渠道，只是"自托管私有镜像"模式（用户自己下过的 mod 自存自用）。

**下载器生态现状（GitHub top）**：shadoxxhd/steamworkshopdownloader（361★，steamcmd 封装）、dane-9/Streamline（147★）、Apricityx/WorkshopAndroidDownloader（133★）、NethercraftMC5608/NetherWorkshopDownloader（110★）、Drackrath/Aurelia（69★，Rust 无头 Steam 客户端，steamcmd 替代）、ChadKevin/WallpaperEngineWorkshopDownloader（23★）、notSeilce/SteamWorkshopDownloader（22★）。**WorkshopDL（fidget77，46★）的策略是合规范围内最成熟的折中**：小文件匿名 WebAPI + 大文件/受限游戏才提示用户登录（前轮 [competitor_analysis.md](competitor_analysis.md) 已研究）。

**替代分发渠道**：Nexus Mods（[REST API](https://api-docs.nexusmods.com/) + GraphQL v2，需免费 API key；下载需账号登录，大文件需 Premium）、CurseForge（需 API key）、ModDB（直链免登录但需 HTML 解析）、Paradox Mods（官方，需登录）。这些是**与工坊并行的独立分发渠道，不是工坊镜像**——只覆盖"作者双投"的 mod，覆盖率低，解决不了"工坊独占且需所有权"的核心痛点。

## 五、对 SWDM 的方案清单

> 合规标注：🟢 绿=匿名公开内容/本人账号合规；🟡 黄=违反 ToS 风险但非盗版；🔴 红=违法（DRM 绕过/盗版分发）

| # | 方案 | 技术可行性 | 合规 | 架构侵入点 | 工作量 | 建议 |
|---|---|---|---|---|---|---|
| 1 | **私人账户 provider**（用户自填账号 → steamcmd `+login`） | ✅ steamcmd 原生；`ProviderMeta.supports_account` 标记已设计（竞品调研修订小节） | 🟢 用户自己账号下自己有权内容，SSA 允许本人使用 | `providers/steamcmd.py` 扩展 + registry 注册账户版 provider，**默认链不含** | 小（<1天） | **纳入 1.4.1**。唯一能合规解决"需所有权物品"的方案——用户自己买游戏自己下。UI 须明示"账号仅本地存储、仅本人使用" |
| 2 | **匿名优先 + 受限时清晰提示登录**（WorkshopDL 式分层） | ✅ 零新通道 | 🟢 | item 级失败原因枚举（"需正版账号"分类，与竞品建议 #8 合并）+ 引导文案 | 中（1-3天） | **纳入 1.4.1**。不解决根问题，但消除"莫名失败"——issue #13474 证明这是公认痛点 |
| 3 | **GGNetwork 匿名代理**（已有试点） | ✅ 已验证匿名可用、返回官方 CDN 直链 | 🟡 ToS §1.2.2 覆盖匿名使用，但无明文授权、无 SLA，可被单方限制（§2.3.1） | `ProviderKind.PROXY` 已就位 | 小（补测） | **1.4.1 先补测覆盖边界**。⚠️ 关键未知：其后端是否有登录态？能否解析**受限 App**的工坊物品？前轮未测——若能，实质就是"服务端账号池"（🟡→🔴 风险升级，须重新定位）。抽 10-20 个已知受限 App 物品实测，结论驱动去留 |
| 4 | **自托管镜像 provider**（steam-workshop-archiver 模式） | ✅ provider 抽象支持镜像型 provider | 🟢 自存自用；**公开共享镜像 = 🔴 盗版分发** | 新 ProviderKind.MIRROR + manifest 同步 | 大（>3天，含服务端） | **长远观察**。当前无成熟镜像源可接入；私人场景 SWDM 的 mod 包导入导出已覆盖 |
| 5 | **Nexus / ModDB / Paradox 官方站点 provider** | ⚠️ 逐站适配：Nexus 需用户 API key + 登录下载；ModDB 需 HTML 解析 | 🟢 官方站点正常 API | 每站一个 provider，registry 注册 | 大（每站 1-3 天 + 持续维护解析规则） | **不采纳（近期）**。核心痛点（受限 App 的工坊独占 mod）解决不了，投入产出比低 |

### 核心结论

**不存在合规的"绕过正版限制"技术方案。** 所有权校验三层设防：license 检查（steamcmd 通道）、file_url 签名发放（CDN 通道，匿名恒空）、depot key 解密（depot 通道，匿名空 key）。匿名只在 Valve 明确开放的 app 上可用，这是设计而非缺陷。

**1.4.1 行动项**：① 私人账户 provider（小，合规绿）；② 受限物品失败原因枚举 + 登录引导（中，体验补齐）；③ GGNetwork 覆盖边界实测（小，结论驱动定位）。

**长远观察项**：Valve issue #13474 正在诉求 **scoped server token**（只允许下载指定 app 的工坊内容、不能买游戏/交易/聊天、可吊销）。**若 Valve 采纳该提案，"受限 App 工坊匿名下载"将被官方层面解决**——这是唯一可能真正改变格局的变量，建议每轮迭代复查该 issue 状态。

---
来源：[steam-for-linux#13474](https://github.com/ValveSoftware/steam-for-linux/issues/13474)（Valve 官方，2026-07-31 仍开）· [Barotrauma#7707](https://github.com/Regalis11/Barotrauma/issues/7707) · [SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader)（AccountHasAccess / RequestDepotKey 源码索引）· [Nexus Mods API](https://api-docs.nexusmods.com/) · GitHub API 仓库检索（161+17+95+17 条）· 项目既有实测：[steam_429_403_research.md](steam_429_403_research.md)、[provider_research.md](provider_research.md)、[workshop_api_research.md](workshop_api_research.md)、[competitor_research_1.4.1.md](../docs/competitor_research_1.4.1.md)
