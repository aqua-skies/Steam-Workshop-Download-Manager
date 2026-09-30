# 工坊拉取速度优化与易用性研究报告（SWDM 1.4.1 输入）

调研对象：SWTools 2.0.8（C#/WPF）、Steam-Workshop-Monitor（Python/Discord bot）、Husko 1.7（Python/CLI）。
源码级精读 + 本机实测历史（research/steam_429_403_research.md）。

## 一、三家速度优化手段（源码级）

**SWTools（`SWTools.Core/`）**
1. **解析结果持久化缓存**（`Cache/Parse.cs`）：解析成功的 Item 序列化到 `cache/parse.json`，启动加载；`ParseAll()` 先走 `ParseWithCache()`（纯本地、零网络，末尾固定 `Task.Delay(500)` 占位）再走网络，命中条目完全不发请求。颗粒度=ItemId，只存"信息完备"的条目。
2. **一次批量请求 + 二级降级**（`ItemList.Parse.cs`）：`GetPublishedFileDetails` 把队列里**全部** Pending id 打成一个 POST（`itemcount` + `publishedfileids[i]`），一次拿完；失败才降级到第三方 `steamworkshopdownloader.io/api/details/file`（`SwDownloader`）。降级链="官方批量 → 第三方批量"。
3. **预览图本地目录**（`Constants.PreviewDir = cache/previews/`）：`DownloadImage` 按 Content-Type 判后缀落盘。
4. **GitHub 代理数组**（`Http.MakeGithubGet`）：`["", gh.llkk.cc, ghproxy.net, gitproxy.click]` 顺序试探，任一成功即返回——只加速自身仓库 API（更新公告/账户配置），**不加速 Steam**。
5. **CheckBytes 轮询**（`Item.Core.cs:189`）：steamcmd 退出后若目录字节数为 0，每 1000ms 重取目录大小，最多 10 次（缓解 steamcmd 写盘延迟误判失败）。
6. **短板（反例）**：`Http.cs` 每个请求 `using HttpClient client = new()`——**无连接复用**，每次 TLS 握手；下载队列 `QueueLaunch` 严格串行，无并发。

**Monitor（`WorkshopMonitor.py`）**
1. **Redis 透传缓存**：`GetModUpdated`/`GetGuild`/`GetLinkUpdated` 先 `cc.hget`，miss 回源 MySQL 再 `cc.hset`+`cc.expire(ttltime)`（环境变量，约定 3600s）；启动 `FillRedis()` 全量预热。
2. **健康门**（`APICheck`）：每轮先打 `ISteamWebAPIUtil/GetServerInfo/v1/`，非 200 直接跳过本轮，避免对已降级 API 发无效应答。
3. **批量端点带全部 id**（`CheckAll`）：同 SWTools，一个 POST 携带全量 ModID。
4. **增量比对**：拿 `time_updated` 与库内值比对，仅变化的条目触发通知——**不重发未变化的数据**。
5. **自适应节拍**：`sleeptime = ctime - runtime`，补偿本轮耗时，且下限 60s 防 API 溢出。
6. **短板**：`httpx.AsyncClient()` 每次新建（未池化）；`CollectionToConfig` 展开集合后对每个 child 串行 `CheckOne`（1 id/请求，N 次往返）。

**Husko（`bot.py`）**
1. **后端节点探测**（`node_checker`）：对 `node01..08.steamworkshopdownloader.io` 并发 POST 探活（5s 超时），只保留 200 的节点，后续随机选用——可用节点池。
2. **集合一次展开**：详情响应里的 `children` 数组直接解析、全部 append 进队列，一次 API 拿到合集全部 child id（但 child 仍逐个发详情请求）。
3. **下载准备态轮询**：`while status != "prepared": sleep(2)` 每 2s 轮 `/download/status`（后台异步打包，不阻塞 Steam 侧）。
4. **随机 UA + 免费代理池**（6 个 proxy-list 源随机抽一个抓取）——规避第三方服务限流，但牺牲稳定性和速度（免费代理质量差）。
5. **短板**：代码质量差（`if x == 944330 or 400750` 恒真、`strip()` 当正则切 URL），串行、无缓存。

**横评结论**：SWDM 的 HTTP 底座（`requests.Session` 复用连接、`Accept-Language` 破 429、端点差异化节流、`_page_cache` + `api_cache` 双层内存缓存、`get_file_details` 50 条/批）**已优于三家**。三家的增量价值在：持久化磁盘缓存（SWTools）、健康门 + 增量比对（Monitor）、节点池探活（Husko）。速度优化的下一程是**压缩/缓存分层/预取/并发**，不是连接复用。

## 二、Steam API 匿名访问提速最佳实践

- **连接复用**：`requests.Session` 已用（SWDM ✅，三家 ✗）。进一步可 `session.mount` 自定义 `HTTPAdapter(pool_connections=10, pool_maxsize=20)` 并设 `Retry`（总重试 3、退避 1→2→4）。
- **gzip**：requests 默认发 `Accept-Encoding: gzip, deflate` 且自动解压——**已自带**，无需改造（HTTPS 页面 ~110KB 压缩后传输显著变小）。确保不要在 headers 里覆盖掉该头即可。
- **HTTP/2**：需换 `httpx`/`hyper`；对 Steam 收益小（同域请求少、TLS 握手已被连接池消除），**不推荐**为它换栈。
- **ETag/304**：steamcommunity HTML 不带 ETag/Last-Modified（实测无），**不可用**；`api.steampowered.com` JSON 也不带。放弃该路径。
- **并发边界（关键）**：429 由**请求头指纹**触发（本机实测，见 research 报告），已用 Accept-Language 破解；在此前提下同 IP 对 `/workshop/browse/` 的并发容忍约 2-3 并发（间隔 2s 基准），详情页 3s 基准。可用线程池 2-3 并发 + **AIMD**（200 增窗、429/超时减半、下限 1）做自适应限流；但收益 = 分页/补全的端到端时间 ÷ 并发数，需实测兜底。
- **缓存分层**：内存 LRU（SWDM 已有 api_cache/_page_cache）→ 加**磁盘 TTL 缓存**（SWTools 的 parse.json 思路：详情 JSON 落盘，重启零网络）。
- **增量更新**：`time_updated` 比对，只对变化条目重抓（Monitor 的核心手段，SWDM 库更新检查可直接复用）。

## 三、SWDM 提速方案（五场景 × 可行性）

**S1 首屏加载**
- 方案：`_page_cache` 已覆盖二次进入；新增**启动预取**（程序启动后台异步拉首页，与窗口初始化并行）+ 首屏先用列表卡片的 title/预览图占位，详情 enrich 完再回填。
- 收益：二次进入已近 0ms；首屏冷启 -30~50%。可行性：高。侵入点：`browse()` 调用层（gui browse tab）。工作量：**小**（<1 天）。

**S2 翻页**
- 方案：**预取下一页**——用户在第 N 页时后台拉第 N+1 页存 `_page_cache`（低优先级，礼让用户点击槽位，`_priority_pending` 已有此机制）。
- 收益：翻页 -60~90%（命中时 0 网络等待）。可行性：高。侵入点：`browse()` + 页码变更回调。工作量：**小**。

**S3 搜索**
- 方案：联想缓存复用（0.7s 间隔已优）；把搜索结果的 enrich 从"全量 50 条一批"改为**首屏 12 条优先 enrich**（首批先返回渲染，其余后台补全）；搜索词命中 api_cache 时直接出。
- 收益：搜索结果出现 -30%。可行性：中高。侵入点：`enrich()` 分段 + gui 列表增量刷新。工作量：**中**（1-3 天）。

**S4 详情补全**
- 方案 A（推荐）：**详情磁盘缓存**——`get_file_details` 结果按 id 拼键写 JSON 到缓存目录，TTL（如 24h，`time_updated` 变化时失效），重启后 enrich 命中零网络（SWTools parse.json 的可迁移核心）。
- 方案 B：enrich 并发化——2 并发线程跑 50 条分批 + AIMD 限流（需实测 429 边界）。
- 收益：A 首次后 -100%、B 首次 -40%。可行性：A 高（api_cache 已是内存版，加磁盘层即可，注意**深拷贝纪律**）、B 中（有 429 风险，需灰度）。工作量：A **小-中**、B **中**。

**S5 缩略图**
- 方案：`fetch_image` 增加**磁盘缓存**（URL hash → 文件，LRU 清理上限如 200MB）+ QThreadPool 异步加载（不阻塞 UI 线程，已有 size 参数）。
- 收益：二次浏览 -100%（无重复下载）、滚动不卡。可行性：高。侵入点：`fetch_image()` + gui 图片加载回调。工作量：**中**。

## 四、集成性与易用性方案（每条可行性五项）

**B1 剪贴板监听自动入队**
- 技术可行性：高（PySide6 `QClipboard.dataChanged` 信号 + `resolve_any_url()` 已能解析工坊链接）。
- 架构兼容性：高（`resolve_any_url` 已存在，接 GUI 剪贴板信号即可）。
- 工作量：**小**（<1 天，含开关项——默认开，设置可关，避免误触发）。
- 三原则：精简 ✅（零界面新增）、用户体感 ✅（复制链接→自动提示入队，"发送到 SWDM"的最省事路径）、基本功能 ✅。
- **建议：采纳（最高性价比）**。

**B2 自定义协议 `swdm://` + 浏览器集成**
- 技术可行性：中（注册表写 `HKCU\Software\Classes\swdm`；浏览器跳转需用户手动允许协议，且 steamcommunity 网页内不能直接唤起，只能靠书签/油猴脚本）。
- 架构兼容性：中（需单实例机制配合：已有托盘，需加 `QLocalServer` 单实例锁 + 参数转发）。
- 工作量：**大**（>3 天，含单实例、协议注册、卸载清理、安装包适配）。
- 三原则：精简 ✗（路径长、隐蔽）、体感 中（仅重度用户受益）、基本功能 无增益。
- **建议：不采纳（1.4.1）。** 剪贴板方案 B1 已覆盖 95% 该场景。

**B3 便携版（单文件/绿色）**
- 技术可行性：高（PyInstaller `--onefile`；配置与缓存目录用 `paths.py` 相对化——已按 APPDATA/EXE 目录分治，核对即可）。
- 架构兼容性：高（`paths.py` 已是路径收敛点）。
- 工作量：**中**（onefile 体积+启动慢需权衡；建议保留 onedir 安装版为主，另出便携 zip 包）。
- 三原则：精简 ✅（不新增界面）、体感 ✅（U 盘携带、重装不丢配置）、基本功能 ✅。
- **建议：采纳为打包选项（出 portable zip，不替安装版）。**

**B4 系统集成：开机自启 + 文件关联**
- 开机自启：可行性高（注册表 `Run` 项，托盘最小化已具备），工作量小；建议加设置页开关。**采纳**。
- `.swdm` mod 包关联（双击导入）：可行性高（注册表 Classes + `sys.argv` 转发 + 单实例）；复用已有 mod 包导入；工作量中。**建议采纳**（与 B3 便携版共用单实例机制时才有价值——若 B2 不做单实例，此项也需要单实例，故两项捆绑评估）。

**B5 导入导出与同步**
- 批量从文本粘贴：可行性高（多行 id/链接解析，复用 `resolve_any_url` + 批量 `get_file_details`），工作量小。**建议采纳**（与 B1 同一入口，粘贴框=手动版剪贴板）。
- 订阅列表/收藏导入（Steam 个人页 HTML 解析）：可行性中（需登录态或公开 profile 抓取，匿名受限）；工作量大。**建议 1.4.1 不采纳**。
- mod 列表导出分享：可行性高（已有 mod 库导出能力，加"分享为文本/id 列表"），工作量小。**建议采纳**（与已有导出合并）。

**B6 首次使用引导**
- 技术可行性：高（QWizard 或空状态提示卡片）。
- 架构兼容性：高（新增独立组件，不改 core）。
- 工作量：**小**（空状态提示优先于完整向导：浏览页空时提示"复制工坊链接自动入队 / 粘贴 id 批量下载"）。
- 三原则：体感 ✅（首日留存核心）、精简 ✅（不做多步向导，只做空状态+一条提示）。
- **建议：采纳空状态提示（不做向导）。**

## 五、优先级排序建议

| 级别 | 项 | 类型 | 工作量 |
|---|---|---|---|
| P0 | S4-A 详情磁盘缓存（TTL+time_updated 失效） | 速度 | 小-中 |
| P0 | S2 预取下一页 | 速度 | 小 |
| P0 | B1 剪贴板监听入队 | 易用 | 小 |
| P1 | S5 缩略图磁盘缓存+异步加载 | 速度 | 中 |
| P1 | B6 空状态提示 | 易用 | 小 |
| P1 | B5 批量粘贴导入 / 导出分享 | 易用 | 小 |
| P2 | S1 启动预取 + 首屏分段 enrich | 速度 | 小/中 |
| P2 | B4 开机自启开关 | 易用 | 小 |
| P2 | B3 便携 zip 包 | 易用 | 中 |
| P3 | S4-B enrich 并发+AIMD（需实测 429 边界） | 速度 | 中 |
| 不做 | B2 `swdm://` 协议注册 | 易用 | 大 |
| 不做 | B5 订阅列表导入（匿名受限） | 易用 | 大 |

落地顺序建议：P0 三项同批进入 1.4.1（S4-A 直接吃下 SWTools 的核心优势且不碰并发红线；S2 复用已有 `_priority_pending` 礼让机制；B1 复用 `resolve_any_url`），全部为"小工作量、零新增界面"，符合精简原则。S4-B 的并发改造留到 429 边界实测有结论后再排期。
