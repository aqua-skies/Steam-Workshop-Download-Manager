# C5 · GGNetwork 真下载补测与后端登录态探测（t32）

> **结论时效**：本文所有结论只对「本次环境（本机 fake-IP 代理出口，steamcommunity 被 SNI 重置阻断）+ 本次后端版本（steam.request，2026-09-29 实测）」成立。GGNetwork 是第三方服务，行为可能随时改变。
>
> 执行人：search-fixer（t32，attempt 2） · 日期：2026-09-29 · 前置：1.4.0 诚实披露「GGNetwork 实网端到端未实测」、t25 复测遗留、bypass 报告（research/bypass_ownership_research_1.4.1.md）

## 0. 环境前提修正（最重要的认知更正）

1.4.0 记录「本机 fake-IP 代理环境，live-network 脚本全失败」，据此假定本机无法实测 GGNetwork。**本次实测推翻该假定**：

| 主机 | 本机可达性 | 说明 |
|---|---|---|
| `api.ggntw.com` | ✅ 直连 200，~0.3-2s | GGNetwork API 本身不在 steamcommunity 的 fake-IP/SNI 阻断范围内 |
| `cdn.ggntw.com` | ✅ 直连 200 | 真实文件 CDN（荷兰节点），实测 1.21 MB/s |
| `api.steampowered.com` | ✅ 匿名可用（部分端点） | `GetPublishedFileDetails` 匿名可用；`QueryFiles` 需 key（超时） |
| `steamcommunity.com` | ❌ DNS fake-IP + 真 IP SNI 重置 | 工坊浏览页抓不到（受限 App 物品 id 发现受阻的根本原因） |
| `store.steampowered.com` / `steamdb.info` / `archive.org` / `r.jina.ai` | ❌ 超时或 403 | 公共代理/存档通道全部不可用 |

**结论 C0**：1.4.0「本机做不了」的判断适用于 steamcommunity 抓取，**不适用于 GGNetwork API/CDN**。C5 五条测试设计在本机直接完成，无需派给干净网络一方。

## 1. 后端登录态探测（关键未知）

**结论 C1：公开内容仍是匿名解析，后端未要求登录。** 公开 GMod 物品 `POST /steam.request` 返回 `result=1` + 可用下载令牌，全程无账号、无 token、无 Cookie。后端虽有完整账号体系（`login.ggntw.com/auth`、`user.session`、`premium`），但 `/steam.request` 对公开物品保持匿名开放。`/steam.collection` 才要求 `Access-Token`（回 `{"status":0,"msg":"token not correct"}`）。

**结论 C2（受限 App 问题）：无证据表明 GGNetwork 能解析受限 App 物品 → 不触发 🟡→🔴 升级。**

- bypass 报告点名的受限 App = DayZ(221100) / Barotrauma(602960)。
- 本机无法获得这两款游戏的工坊物品 id：steamcommunity 浏览页被 SNI 重置阻断，搜索引擎不返回工坊物品页 URL，社区站（rustlabs/wiki/memento 存档）全部 403 或不可达。**受限 App 样本数 = 0**，这是本次测试的明确盲区。
- 间接证据指向「不能」：Rust(252490) 物品 2551690809 经 `GetPublishedFileDetails` 验证真实存在（consumer_appid=252490），GGNetwork 对其返回 `{"result":3,"game":252490}`（无 url、无 error），而同一时刻对 GMod 物品全部成功。**Rust 已被实测证伪为受限 App**（steamcmd 匿名下载成功，见 §3），说明 `result=3` 是物品级失败而非受限 App 特征，但仍证明后端对部分真实物品解析失败。
- **风险定级维持 🟡**（第三方代理 ToS 风险），不上调 🔴：未观测到服务端账号池行为；GGNetwork 未被纳入默认通道（默认 = steamcmd），UI 标注「实验性」，无用户侧暴露。
- **对 C2（失败原因枚举，t41）的输入**：GGNetwork 的行为**不得**用作「需正版账号」启发式的判定依据——后端错误串（如 `need login to account`）与真实账号需求无关（实测该串出现在一个已被 Steam 删除的物品上，见 §4）。通用 steamcmd I/O 失败也绝不可映射为「需正版账号」（Valve issue steam-for-linux#13474 证据，见 bypass 报告）。

## 2. 真实排队路径（测试设计 ③）

1.4.0 只做了离线 mock。实测：**每个成功响应都同时带 `queue.position=1` 和有效 url**（10/10 次：8 次无间隔突发 + 2 次 25 秒后复轮询）。`position` 在有 url 时不是「未就绪」信号。

落地页 JS（实测抓取）证实流程：`api` 返回 `https://ggntw.com/download/<token>`（HTML：服务器选择器 + 5 秒倒计时），真实文件在 `https://cdn.ggntw.com/<token>`。无 url 且 `position>0` 才是真正的排队态（本次未观测到）。

**发现 bug-1（严重）**：1.4.0 `resolve()` 的守卫「`position>0` → 返回空串」（ggnetwork.py:148）会把**每个真实物品的 url 丢弃**。用 1.4.0 打包的类直接对 live 物品调用验证：`resolve()` 返回 `''`，而原始 API 明明带 url——**该通道在 1.4.0 中对任何真实物品都会静默失败并回退 steamcmd**。因默认链不经过它，用户无感知，但功能从未生效。

## 3. 端到端真下载（测试设计 ①②④）

物品样本（均经 `GetPublishedFileDetails` 匿名验证 result=1）：

| 物品 | App | 类型 | GGNetwork 结果 |
|---|---|---|---|
| 160250458 Wiremod | 4000 GMod | 公开对照 | ✅ result=1 + url |
| 3803871160 Coldridge Prison | 4000 GMod | 公开对照 | ✅ result=1 + url |
| 2497853525 | 4000 GMod | 公开对照 | ✅ result=1 + url |
| 2551690809 Juggernaut Supplies | 252490 Rust | 公开（**steamcmd 匿名下载成功**，非受限 App） | ⚠️ `result=3`，无 url（物品级失败） |
| 2537024972（旧固定探测 id） | — | **Steam 侧 result=9（已被删除）** | ❌ `{"result":10,"error":"need login to account"}`（误导文案） |

**端到端实测（修复后通过项目自身 provider 类跑完整链路）**：

```
resolve(160250458) → https://cdn.ggntw.com/<token>          # 落地页→CDN 改写生效
download() → SUCCESS
最终文件: 160250458.gma = 20,685,180 bytes, 魔数 GMAD        # 与 Steam 声明尺寸 delta=0
原始传输: 6,397,843 字节 zip → 解压 → .gma（1.21 MB/s，荷兰 CDN）
```

1.4.0 的 zip 解压 + .gma 魔数 + >1% 尺寸校验三件套在真实数据上**全部正确**（zip 内 `160250458_wiremod/160250458.gma`，精确解包）。

**限速器（设计 ④）**：8 次无间隔突发请求全部 HTTP 200、无 429。后端实测不对短时突发限流；项目自限 20/min（令牌桶 burst=3）在真实延迟（0.3-2s/请求）下安全且有余量，无需调整。

**steamcmd 对照实验**：`steamcmd +login anonymous +workshop_download_item` 对 Rust 252490/2551690809 与 GMod 4000/160250458 **均匿名下载成功**（96607 / 20685180 字节）。本机 steamcmd 内容链路可用，且证伪了「Rust 是受限 App」的假设。

## 4. 发现的 bug 与本次修复（代码改动）

| # | 严重度 | 问题 | 修复（ggnetwork.py） |
|---|---|---|---|
| 1 | 🔴 严重 | `resolve()` 在 `queue.position>0` 时丢弃 url → 通道对任何真实物品都失效 | url 优先：有 url 即用（并改写 CDN）；仅「无 url 且 position>0」才判排队回退 |
| 2 | 🔴 严重 | api 返回的 url 是 HTML 落地页，直接当文件下载只会存下 19KB 网页 | `ggntw.com/download/<token>` → `cdn.ggntw.com/<token>` 改写 |
| 3 | 🟡 中 | 固定探测 id 2537024972 已被 Steam 删除；`probe()` 只判 HTTP 200，错误体也报 OK | 探测物品轮换（3 个实测可用 id）+ 响应须带可用 url 且无 error 才判 OK |
| — | 附带 | 1.4.0「未实测」披露与「本机做不了」前提 | 模块 docstring 改为实测结论（含时效声明）；changelog_1.4.0 回填（见下） |

**技术债并入（t32 设计 ②）**：ggnetwork 探测动态化已随 bug-3 落地。

## 5. 测试

- `tests/test_providers.py`：**89/89 ALL PASS**（原 84 + 新增 5 项：position>0 带 url 取直链、无 url 排队回退、error 体返回空、落地页改写 CDN、probe 健康判定 2 项）。语义翻转项按实测改判，非削弱断言。
- **live E2E**（_c5_stage19.py，本机真实网络）：resolve→CDN 改写→下载→zip 解压→.gma 校验全链路 SUCCESS，最终文件 20685180 字节 GMAD 精确匹配。
- 全量回归：见文末「回归统计」。

## 6. 结论汇总

| # | 结论 |
|---|---|
| C0 | api/cdn.ggntw.com 本机直连可达，1.4.0「本机做不了」前提作废（该判断只适用于 steamcommunity） |
| C1 | 公开内容匿名解析正常，后端不要求登录；`/steam.request` 匿名开放，集合接口才需 token |
| C2 | 受限 App 样本数 0（发现通道被环境阻断），无证据 GGNetwork 解析受限 App 内容 → **维持 🟡，不上调 🔴**；已向 C2(t41) 传递「不得用 GGNetwork 行为做『需正版账号』判定」 |
| C3 | 修复后 GGNetwork 通道**首次真正可用**（1.4.0 因 bug-1/2 从未实际生效）；E2E 实测通过 |
| C4 | 后端错误串不可信（`need login to account` 出现在已删除物品上），任何失败原因枚举不得依赖后端文案 |
| C5 | 限速器在真实延迟下安全（8 突发无 429），自限 20/min 保守有据 |

**风险声明（取代「未实测」）**：GGNetwork 为第三方代理通道，ToS §5.2.2 对负载有限制；后端行为可变（本次实测仅对 2026-09-29 的版本有效）；保持「实验性」标注、不进默认链、匿名范围内使用。受限 App 下载仍需用户自有账号（Valve 设计），见 t38（C3 私人账户 provider）。

## 7. 回填 1.4.0 诚实披露

docs/changelog_1.4.0.md 第 9 节原「GGNetwork 实网端到端未实测（本机 fake-IP 代理环境）」已按上述结论改写为明确风险声明 + 实测结论 + bug 修复记录。本节即该披露的闭环。

## 8. 回归统计

- `tests/test_providers.py`：89/89 ALL PASS
- 全量 `tests/run_all.ps1`（本次实测，pwsh-387）：**pass=60 / fail=1 / noresult=0，total=61**（基线在 t36 网络可用时为 63/63；本次 test_bulk_games 因本机 steamcommunity 代理出口超时 FAIL——1.4.0 起既有环境性失败，t21 起每轮记录在案，与本次改动无关；该脚本不触及 ggnetwork 代码）
- **零新增失败**：本次只改 `swdm/core/providers/ggnetwork.py` 与 `tests/test_providers.py`，语义翻转项已同步按实测改判
- 1.4.0 既有非回归（test_legacy_format / test_page_parser）已在 t36 修复夹具，本轮持续 PASS

## 9. 遗留与下一步

- 受限 App（DayZ/Barotrauma）GGNetwork 行为仍是盲区：需干净网络一方或用户提供物品 id 才能补测；当前按「无证据可解析」保守处理。
- 若未来 GGNetwork 后端改版（url 形状、登录要求），`resolve()` 的落地页改写与 url 优先逻辑需复测；建议作为 1.4.2 的周期性巡检项。
