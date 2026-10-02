# IDM 下载内核设计调研与 C#/.NET 8 复刻方案（SWDM 2.0）

> 调研日期：2026-10-02
> 方法：多引擎检索（exa / tavily / bing / baidu）+ 官方文档镜像 + 开源项目（bezzad/Downloader、SteamRE/DepotDownloader、SteamKit）+ SuperUser / Stack Overflow / Reddit / 论坛人类经验。
> 说明：web_fetch 在本机 fake-IP 代理环境下对绝大多数站点 DNS 解析失败（详见下文"检索限制"），本文档以搜索引擎返回的**原文片段**为主要证据来源，凡属推断处均明确标注。

---

## 0. 摘要与核心结论

1. **IDM 的加速本质**是"动态分段 + 连接复用 + HTTP Range"，官方称之为 *Dynamic File Segmentation*，采用"in-half division rule"（对半分割规则）：分段在下载**过程中**动态创建，而非开始前一次性切好；某连接完成自己的分段后，若下一分段尚未开始下载，IDM 会**把该分段重新指派给已完成的连接**，实现"full reuse of connections … without additional connect and stages"（无重连开销的连接复用）。[来源：IDM 官方 Dynamic Segmentation 页](https://www.internetdownloadmanager.com/support/segmentation.html)
2. **默认连接数约 8**，官方建议不要超过 4–8，过高会劣化传输性能；连接数可在 Options→Connection 按**服务器例外表**单独设置（针对限制单客户端连接数的服务器/FTP）。[Options 镜像](https://mirror5.internetdownloadmanager.com/support/options.html) / [helpdeskgeek 分析](https://helpdeskgeek.com/does-internet-download-manager-increase-download-speed/)
3. **续传状态**落盘为分段临时文件（`%AppData%\IDM\DwnlData\*` 下的 `.idm.tmp` 文件），完成后"rebuild"拼接并删除临时目录；续传时对相邻分段**多请求若干字节并做首尾比对**以校验拼接完整性（官方 FAQ 自述）。[eightforums](https://www.eightforums.com/threads/dwnldata-in-internet-download-manager.32311/) / [官方 FAQ problems9](https://www.internetdownloadmanager.com/register/new_faq/problems9.html) / [TrueSight 分析](https://tsight.io/articles/9366930)
4. **对 SWDM 2.0 最重要的发现**：steamcmd 的内容传输层**本身就是 HTTP**（Valve 官方 SteamPipe 文档："SteamPipe uses the HTTP protocol for content delivery … Content can be hosted by external CDN providers"）。因此"IDM 体感"在 Workshop 场景**不必靠假象**——用 **SteamKit 的 CDNClient（C#）在 depot chunk 级别做真正的并行 HTTP 分块下载**是可行路径（DepotDownloader 即用 `CDNClientPool` + `-max-downloads`，默认 **8 个 chunk 并发**，与 IDM 默认 8 连接遥相呼应）。[Steamworks 上传文档](https://partner.steamgames.com/doc/sdk/uploading) / [DepotDownloader README](https://github.com/SteamRE/DepotDownloader/blob/master/README.md)
5. **C# 直接可用的开源基座**：[bezzad/Downloader](https://github.com/bezzad/Downloader)（v5.x，面向 .NET 8/9/10，分段下载 + 续传 + 限速 + 实时进度，续传元数据**嵌入 `.download` 文件尾部**，与 IDM 的"状态即文件"思想一致）。[NuGet 文档](https://www.nuget.org/packages/Downloader)
6. **磁盘 IO 最优解**：单文件 + 偏移量写入（免拼接）+ NTFS 稀疏文件占位（`FSCTL_SET_SPARSE`）+ 元数据尾部追加；IDM 式"临时文件再拼接"只在个别场景（网络盘/安全软件冲突）才必要。

---

## 1. IDM 内核机制

### 1.1 多连接分段下载

**机制（官方自述）**：IDM 不在下载开始前固定切分，而是随下载推进动态分段；进度条上 **粉色线 = 分段起点，蓝色 = 已下载数据，白色 = 待下载段**。当某连接把本段下完（蓝条抵达粉线）且下一段尚未开始时，IDM 把该段重新指派给这个已空闲的连接，连接被**完全复用**、无需重建 TCP/TLS。分段大小还随文件**大小与类型**变化：大文件分更多段。[官方分段页](https://www.internetdownloadmanager.com/support/segmentation.html) / [Medium 分析](https://medium.com/@osmanwriter007/maximizing-download-efficiency-with-internet-download-manager-idm-8520a3aa3542)

**为什么能加速（人类经验共识）**：单 TCP 连接常受服务器单流限速、拥塞窗口增长慢、丢包恢复慢等限制；4–8 个并行连接常能逼近带宽上限（Reddit r/networking 实测 4–8 流达 94–97Mbps）。但若单连接已饱和，多连接无收益，反而徒增服务器拒绝/限速风险（Reddit r/Roms、r/explainlikeimfive 讨论）。机制本质见 [Stack Overflow #12583465](https://stackoverflow.com/questions/12583465/how-is-idm-and-flashget-are-working-maximum-speed-download)：多连接 + HTTP `Range` 头。

**默认连接数与调参**：
- 默认约 **8 连接/8 段**（[helpdeskgeek](https://helpdeskgeek.com/does-internet-download-manager-increase-download-speed/)："It splits a file into eight segments"）。
- 官方建议 `Max Connection Number` **不要大于 4–8**："Large number of connections (file segments) can deteriorate file transfer performance"（[Options 镜像](https://mirror5.internetdownloadmanager.com/support/options.html)）；界面可选到 16/24/32，仅建议高性能机器使用，且可能影响同网他人（[wikiHow](https://www.wikihow.com/Speed-Up-Downloads-when-Using-Internet-Download-Manager-(IDM))、[dealarious](https://www.dealarious.com/blog/idm-unknown-features)）。
- **按服务器例外**：Options→Connection 的 "Exceptions:" 表可为特定主机单独设连接数——用于限制同客户端连接数的服务器与 FTP（[options.html](https://internetdownloadmanager.com/support/using_idm/options.html)）。**这是 SWDM 复刻时值得照抄的设计**：默认值 + 每主机覆盖表。

### 1.2 下载队列与调度

- 两个内建队列：**下载队列** 与 **同步队列**；可创建任意数量的附加队列；队列可设定开始/停止时间，也可手动启停（[IDM Queues](https://www.internetdownloadmanager.com/support/idm-scheduler/idm_queues.html)）。
- 主列表有 **"Q" 列**标识文件是否在队列中；右键 "Add to Queue / Delete from Queue"（[Main Dialog](https://www.internetdownloadmanager.com/support/main.html)）。
- 新 URL 加入列表时**自动进下载队列**，下完后从队列移除（[Scheduler 对话框](https://www.internetdownloadmanager.com/support/schedulerD.html)）。
- **"一次只下一个文件"只能通过 Scheduler 实现**：把下载加入队列（"Download Later"），在 Scheduler 里设置并发数（[官方 FAQ functions5](https://www.internetdownloadmanager.com/register/new_faq/functions5.html)）——即队列并发数是调度器级配置。
- 调度器还支持：定时拨号连接、下完断线/关机、周期性同步（[features2](https://help.internetdownloadmanager.com/features2.html)）。
- 分类树与队列联动：队列列表在 "Categories" 窗格的右键菜单中编辑（[Scheduler](https://secure.internetdownloadmanager.com/support/idm-scheduler/idm_scheduler.html)）。

### 1.3 断点续传与分段状态文件

**状态存储（经验观察为主）**：
- 进行中的下载保存在临时目录（默认 `%AppData%\IDM\DwnlData\<hash>\`），只有未完成的部分；下载成功后 IDM 自动删除该目录（[eightforums](https://www.eightforums.com/threads/dwnldata-in-internet-download-manager.32311/)）。
- 临时文件以 `.idm.tmp` 为后缀，形如 `example.zip.idm.tmp`；每个分段对应一个临时文件，全部下完再**合并（rebuild）**成完整文件（[TrueSight 深度剖析](https://tsight.io/articles/9366930)）。
- 若目标盘为网络盘/外置盘或被安全软件干预，IDM 可能无法写入目标而滞留临时目录（[官方 FAQ](https://www.internetdownloadmanager.com/register/new_faq/IDM-stores-file-in-temporary-folder.html)）；"rebuild temporary files" 很慢通常是 AV/防火墙 hook 磁盘行为所致（[problems5](https://secure.internetdownloadmanager.com/register/new_faq/problems5.html)）。
- **.idm 文件**：暂停/异常时 IDM 会在目标文件同目录留下与目标同名的 `.idm` 文件，用于下次续传（社区经验、[Apeaksoft 恢复指南](https://www.apeaksoft.com/recover-data/recover-deleted-files-on-idm/)）。其**二进制结构没有公开文档**——SWDM 不应尝试兼容 .idm 格式，只复刻其**语义**（见 §3.3）。

**续传的完整性校验（官方 FAQ 自述，极重要）**：
> "When IDM downloads a file using several connections, It requests **several bytes more** for every file part to match the adjacent file part data … When IDM resumes a download, it **falls back on several bytes and compares the beginning of new data with the end of** [old data]."
> ——即每个分段**多请求若干重叠字节**，续传时回退这若干字节、把新数据起点与旧数据尾部做**字节级比对**，确认拼接点吻合。（[problems9.html](https://www.internetdownloadmanager.com/register/new_faq/problems9.html)）

这一"重叠 + 比对"策略是 IDM 对"分段边界写错/服务器返回不一致"的防御，**SWDM 的 HTTP 分段实现应直接照抄**。

**链接失效处理**：临时链接类站点续传时会要求从头下载（[sites2_6](https://www.internetdownloadmanager.com/register/new_faq/sites2_6.html)）；续传时若服务器返回网页而非文件（链接已失效），IDM 会报错（[SuperUser #320402](https://superuser.com/questions/320402/resuming-a-download-using-internet-download-manager)）。用户社区普遍认为 IDM 会保存**来源页面 URL**，续传失败时回到来源页刷新下载链接（[SuperUser #657720](https://superuser.com/questions/657720/how-does-idm-resume-a-paused-http-download)）——此为社区推断而非官方确认，但对 SWDM 的启发是：**把"来源页/解析参数"随任务持久化，续传失败时重新解析而非直接报错**。

### 1.4 分段拼接与文件完整性

- 完成后 rebuild = 把各 `.idm.tmp` 顺序拼接、重命名为目标文件、删除临时目录（[eightforums](https://www.eightforums.com/threads/dwnldata-in-internet-download-manager.32311/)）。
- 拼接正确性靠 §1.3 的重叠字节比对 + 服务器必须支持 Range（Resumable）；下载进度对话框直接显示"**服务器是否支持续传**"（见 §2）。
- 规避策略：延迟到完成后一次性拼接，避免边下边写的目标文件被破坏（与"直接偏移量写入单文件"的方案是两种不同取舍，见 §5）。

### 1.5 错误重试与连接迁移

- 代理失效 → Options→Proxy/Socks 切换/关闭代理后重试（[problems1](https://www.internetdownloadmanager.com/register/new_faq/problems1.html)）。
- 拨号/VPN 断线重连后 IDM 可继续（digit 论坛经验）；Options 有 "Dial-Up" 与 "Sounds" 选项卡，说明内核内建**连接类型感知**。
- 自动续传Broken 下载需借助 Scheduler（社区结论："You have to do it through Scheduler" [digit](https://geek.digit.in/community/threads/does-idm-auto-resume-broken-download.197174)）——即 IDM 默认是**手动恢复**，调度器才做自动重试循环。**SWDM 应做得更好**：内核级自动重试 + 指数退避。

### 1.6 速度计算与进度刷新

**有据可查的字段语义**（官方/中文镜像）：
- 主列表列：**文件大小、状态、预计完成时间、当前下载速度、文件描述**（可排序、可自定义列）。
- 下载进度对话框：**下载进度、平均下载速度、预计完成时间、当前下载状态、服务器是否支持续传**，外加**每段下载进度的图表**（粉/蓝/白如 §1.1）。
- 来源：[idmchina](https://www.idmchina.net/jiaocheng/idm-ehgk.html)、[idmxiazai 主界面文档](https://idmxiazai.com/docs/%e4%bd%bf%e7%94%a8%e6%95%99%e7%a8%8b/%e4%b8%bb%e7%95%8c%e9%9d%a2/)、[官方 Main Dialog](https://www.internetdownloadmanager.com/support/main.html)。

**IDM 没有公开速度公式与刷新频率**（诚实声明）。基于字段语义与通用工程实践，SWDM 应实现的公式（推断）：
- 平均速度 = 已下载字节 / 已耗时（与 IDM 对话框 "average download speed" 语义一致）
- 当前速度 = 滑动窗口（如近 1–2 秒）或 EMA 平滑的瞬时速率；观察上 IDM 列表速度列约 1 次/秒刷新（*社区普遍体感，非官方数据*）
- 剩余时间 = 剩余字节 / 当前速度
- 刷新频率建议：UI 层 500ms–1s 节流（进度事件底层可更频繁，渲染必须节流，WPF 尤其要避免 Dispatcher 拥塞）

---

## 2. IDM 下载 UI 设计——值得复刻的具体元素

值得 SWDM 2.0 直接照抄/本地化的元素（均有官方或镜像出处）：

1. **主列表行级信息**：文件名、大小、状态文案、剩余时间、速度、描述；列头点击排序；右键菜单（加入/移出队列、属性）。[idmchina](https://www.idmchina.net/jiaocheng/idm-ehgk.html)
2. **"Q" 列**：一个极轻量的队列标记（复选/字母 Q），把"是否排队"做成一列而非弹窗——SWDM 的任务表建议照此设计。[Main Dialog](https://www.internetdownloadmanager.com/support/main.html)
3. **下载进度对话框**：总进度条 + **分段进度可视化**（粉=段起点、蓝=已下载、白=待下载）——这是 IDM 最具辨识度的元素。SWDM 在 HTTP 直连/SteamKit chunk 场景可真实显示 N 段；steamcmd 场景退化为"单流 + 段数 N/A"（见 §4.3）。[官方分段页](https://www.internetdownloadmanager.com/support/segmentation.html)
4. **对话框显隐策略**：可设为前台弹出 / 最小化显示 / 完全不显示（"Don't show" in Start view）——SWDM 应提供同等的三档通知强度。[options.html](https://www.internetdownloadmanager.com/support/options.html)
5. **类别树**（左侧窗格）：内建分类（压缩包/音频/视频/程序/文档等），右键 "Add Category" 自建；每个类别绑定独立下载目录；Options→Save To 定义各类别默认目录。[functions12](https://secure.internetdownloadmanager.com/register/new_faq/functions12.html) / [options](https://internetdownloadmanager.com/support/using_idm/options.html)
   - 对 SWDM：类别树映射为"游戏 → mod 文件夹"，类别.DownloadFolder 映射为 `steamapps/workshop/content/<appid>`。
6. **队列窗格与调度**：多队列（下载队列/同步队列/自建）、定时启动、完成后关机、并发数仅由调度器控制。[idm_queues](https://www.internetdownloadmanager.com/support/idm-scheduler/idm_queues.html)
7. **完成通知**：Sounds 选项卡（声音提示）+ 完成后动作（关机/断线）——SWDM 可映射为 toast 通知 + 系统托盘。
8. **按钮态**：控制按钮（Add URL / Resume / Stop / Stop All / Delete / Delete Completed / Options / Scheduler / Start Queue / Stop Queue）随当前选中项**动态启用/禁用**——这是"状态机驱动 UI"的优秀范式。[using_idm](https://help.internetdownloadmanager.com/support/using_idm/using_idm.html)

---

## 3. C#/.NET 8 实现方案

### 3.1 HttpClient / SocketsHttpHandler 连接池做 Range 分段下载

**关键要点（全部有 Microsoft 官方出处）**：
- **单一 HttpClient 实例 + 各实例独立连接池**：HttpClient 是"一组设置的集合"，每个实例有自己的连接池，复用实例可避免 socket 耗尽（[HttpClient guidelines](https://learn.microsoft.com/en-us/dotnet/fundamentals/networking/http/httpclient-guidelines)）。
- **同主机并发上限**：默认每服务器端点并发连接数有限制，分段下载必须显式提高 `SocketsHttpHandler.MaxConnectionsPerServer`（等功能于旧 `HttpClientHandler.MaxConnectionsPerServer`，**按服务器端点计数**：256 表示对每个主机各 256）——[文档](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler.maxconnectionsperserver?view=net-9.0)。若不调，8 路并行 Range GET 会被池限流排队。
- **KeepAlive**：.NET Core 2.1+ 的连接池内建连接寿命管理，`PooledConnectionLifetime` 周期性重建连接以反映 DNS 变化（[Dave Mateer 博客](https://davemateer.com/2020/10/14/httpclient-connection-pooling)）——分段复用连接时天然 KeepAlive，无需手工管理。
- **HTTP/2 vs 1.1**：HTTP/2 在**单连接上多流复用**，没有 HTTP/1.1 那种每域名连接数上限（[dev.to](https://dev.to/sibiraj/understanding-http2-parallel-requests-streams-vs-connections-3anf)、[Cloudflare](https://blog.cloudflare.com/http/2-for-web-developers)），且 HTTP/2 下 "domain sharding" 反而有害。所以：
  - 若服务器/CDN 走 HTTP/2，**少量连接即可多流并行 Range**（`EnableMultipleHttp2Connections` 控制是否允许对同一服务器开多条 HTTP/2 连接——[SocketsHttpHandler 文档](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler?view=net-10.0)）。
  - 但**分段加速的经典收益来自多条 TCP 连接**（绕过单流限速）；HTTP/2 单连接复用方**一个拥塞控制域**，单服务器限速时收益不同。**SWDM 策略**：探测协议，HTTP/1.1 → N 条连接各一个 Range GET（IDM 式）；HTTP/2 → 复用单连接多流并按需 `EnableMultipleHttp2Connections`。一切以**服务器实际行为**为准（按主机例外表，见 §1.1）。

**注意点（实战）**：
- 下载前先 `HEAD`（或带 Range 的轻探测）确认 `Accept-Ranges: bytes` 与 `Content-Length`，并记录 ETag/Last-Modified 用于续传时校验文件未变（bezzad/Downloader 的 `RemoteFileResolver` 即"single lightweight header probe"思路，[README](https://github.com/bezzad/Downloader)）。
- 分段失败/服务器返回 200 而非 206 → 服务器不支持 Range，应**整段回退单流**（[bezzad/Downloader issue #119](https://github.com/bezzad/Downloader/issues/119)讨论了主机限制下的降级处理，含 min block size 相关经验值 8000 字节）。
- 分块大小下限要有保护：chunk 太小会让 HTTP 开销占比过高（同上 issue 的经验）。

### 3.2 开源参考实现

**[bezzad/Downloader](https://github.com/bezzad/Downloader)**（首选基座，C#，MIT 类生态，v5.x 显式面向 .NET 8/9/10）：
- 分段（multipart）并行下载 + 实时异步进度事件 + 异步暂停/恢复 + 限速（`MaxSpeedBytesPerSecond` 类配置）+ 可注入自定义 `HttpClient`/`HttpMessageHandler`（支持 `IHttpClientFactory` 与 delegating handler）。
- **续传设计极值得借鉴**：PR #212 引入 `EnableAutoResumeDownload`，把下载元数据**直接嵌入 `.download` 文件尾部**（"download metadata is embedded inside the `.download` file — no extra files"，[PR #212](https://github.com/bezzad/Downloader/pull/212)、[commit c79df6f](https://github.com/bezzad/Downloader/commit/c79df6f46c71935538eba3e618c97feb9076167b)）。续传流程（[NuGet 5.9.6 文档](https://www.nuget.org/packages/Downloader)）：
  1. 检测同名 `.download` 文件存在；
  2. **从文件尾部读取元数据**恢复 `DownloadPackage` 状态（各 chunk 的位置/进度）；
  3. 校验服务器仍支持 Range 且文件大小未变，然后断点续传。
  ——这与 IDM ".idm 状态文件随目标文件驻留"的语义一致，且比 IDM 更优雅（**无需解析未公开二进制格式，自定义 JSON/MessagePack 尾部即可**）。
- `Chunk` / `ChunkDownloader` 分层（[Chunk.cs](https://github.com/bezzad/Downloader/blob/e4ab807a2e107c9ae4902257ba82f71b33494d91/src/Downloader/Chunk.cs)）；chunk 级 `blockTimeout` 默认 5 秒（[commit 3a805ab](https://github.com/bezzad/Downloader/commit/3a805ab9e7bd08104e6772c028699c6dd3e293a2)），即**块级超时重试**粒度。
- 集成测试含 `StopResumeDownloadTest`（[IntegrationTests](https://github.com/bezzad/Downloader/blob/master/src/Downloader.Test/IntegrationTests/DownloadIntegrationTest.cs)），可直接作为 SWDM 的测试模板。

**[SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader) + [SteamKit](https://github.com/SteamRE/SteamKit)**（Workshop/SteamPipe 场景的 C# 正解，见 §4）：
- `CDNClientPool`：对 Steam CDN 端点的**连接池**，服务器选择为"round-robin + 加权分布"，含失败处理（[DeepWiki CDN Management](https://deepwiki.com/SteamRE/DepotDownloader/3.3-cdn-management)）——这就是 Steam 版的 IDM 连接池。
- 下载引擎"two-level parallelization"（文件级 + chunk 级两级并行，queue-based，[DeepWiki Parallel Download System](https://deepwiki.com/SteamRE/DepotDownloader/3.2.2-parallel-download-system)）。
- PR #132 "Implement per-chunk downloads"：把文件 IO 与 chunk 下载都任务化、先校验已有文件再下载（[PR #132](https://github.com/SteamRE/DepotDownloader/pull/132)）。
- 命令行 `-max-downloads <#>`：**最大并发 chunk 数，默认 8**（[README](https://github.com/SteamRE/DepotDownloader/blob/master/README.md)）。
- SteamKit 的 `CDNClient` 提供 manifest 与 chunk 的 HTTP 下载 API（[steam.readthedocs.io](https://steam.readthedocs.io/en/latest/api/steam.client.cdn.html)），PR #1471 进一步把"原始 CDN manifest/chunk 获取"拆成可复用函数（[PR #1471](https://github.com/SteamRE/SteamKit/pull/1471)）。

**关于任务书提及的 "Xelon"**：多引擎检索（exa + tavily + GitHub）**未找到**任何与此名称相关的 C# 下载库（结果均为瑞士 Xelon AG 等无关公司）。可行替代即上两者；如任务书指的是其他名称（如 Xelon=某私有项目），需用户澄清。

### 3.3 对 IDM 机制的 C# 映射（设计骨架）

| IDM 机制 | C#/.NET 8 实现 |
|---|---|
| 动态分段（in-half division） | 初始 N=8 chunk；每 chunk 完成后从**最大未完成 chunk 中点分裂**出新 chunk 指派给空闲 worker（复用同一 HttpClient 连接池，=true 连接复用） |
| 连接数默认 8 + 每主机例外表 | `SocketsHttpHandler.MaxConnectionsPerServer` 默认 8；`Dictionary<string,int>` 主机覆盖表，`HttpClient` 按表分组实例化 |
| .idm 状态文件 | 单一目标文件 + `.swdm.meta`（或同 IDM 语义的尾部元数据，见 §3.2 bezzad 方案）：chunk 列表 (start,end,done)、ETag/Last-Modified、URL、来源页参数 |
| 续传重叠字节比对 | 每段结束/续传起点回退 16–64 字节做 SHA 或字节比对（学 **官方 FAQ problems9** 的防线） |
| 链接失效重解析 | 持久化"来源页/解析参数"；续传 200-with-HTML 或 403 时触发重解析而非报错（社区经验，SuperUser #657720/#320402） |
| 队列/调度器并发数 | 调度器层 `MaxConcurrentDownloads`（IDM 的并发只归 Scheduler 管）；手动"立即下载"绕过队列 |
| 速度/进度 | 平均速度=总量/耗时；当前速度=EMA；剩余时间=剩余/当前；UI 500ms–1s 节流刷新 |
| 错误重试 | chunk 级超时（如 5s，bezzad 经验值）+ 指数退避 + 代理/端点切换（学 CDNClientPool 的 round-robin 加权） |

---

## 4. Workshop 场景适配

### 4.1 关键事实修正（对任务书前提的重要补充）

任务书设定"steamcmd 二进制协议不能 HTTP Range 分段"——**对 steamcmd 进程本身成立**（它独占 CM 连接与内容流，外部无法注入 Range/并发），但需要补充一个关键事实：**SteamPipe 的内容交付层就是 HTTP**。Valve 官方文档明言：
> "SteamPipe uses the HTTP protocol for content delivery. Since downloads are regular web traffic, any third-party HTTP cache between the customer and Steam servers will increase download speed. Content can be hosted by external CDN providers."
> ——[Steamworks: Uploading to Steam](https://partner.steamgames.com/doc/sdk/uploading)

**推论（SWDM 2.0 架构图）**：想要真·IDM 体感，正确路径不是黑盒调控 steamcmd，而是**用 C# 原生客户端走 SteamKit CDN 路线**（见 §4.3）；steamcmd 保留为兼容/兜底 provider（SWDM 1.x 已有串行化 + provider 链式回退经验）。

### 4.2 steamcmd 驱动下载的"假 IDM 体感"映射

steamcmd（`workshop_download_item`）单进程独占流，无法插入 Range 分段。已知限制（人类经验汇总）：
- **限速**：社区普遍报告 steamcmd 下载约 100 Mbps 上限（"The steamcmd is limited to 100 Mbps download"，[ValveSoftware/steam-for-linux #6321](https://github.com/ValveSoftware/steam-for-linux/issues/6321)）。
- 大文件超时/断流（同 issue 与 [Steam 社区讨论](https://steamcommunity.com/discussions/forum/1/215439774859993377)）。
- 部分 mod **匿名账号不可用**，需拥有游戏的账号（[Reddit r/steamsupport](https://www.reddit.com/r/steamsupport/comments/v6ddu1/steam_cmd_error_when_downloading_workshop_content)、同 #6321）。
- 无进度回调协议、无限速参数、无并发参数——**只有"开始/完成/失败"三态**（解析 stdout 兜底，SWDM 1.x 已有经验）。

映射表（"假象"设计）：

| IDM 体感元素 | steamcmd 场景的等价实现 |
|---|---|
| 速度（当前/平均） | 解析 steamcmd stdout 的进度行（百分比/字节数）→ 同一套 EMA/平均公式；无进度行时以"状态=下载中+已耗时"兜底显示 |
| 剩余时间 | 仅当能拿到稳定速度时显示，否则显示"未知"——**诚实降级，不要伪造数字** |
| 分段数列 | 显示 `N/A`（单流）。真正想显示段数→走 §4.3 SteamKit 路线 |
| 限速 | 无法对 steamcmd 真限速（属"假象"：UI 上可设"优先级/错峰"，实际是调度层控制steamcmd 进程的启动时机与并发数） |
| 队列/优先级/类别树 | **完全真实**：队列、并发数、类别、Q 列在 SWDM 侧都是真功能（这部分 IDM 体感与传输层无关） |
| 断点续传 | steamcmd 自己有 manifest 校验（`validate`）；SWDM 侧记录已完成 mod 与文件清单做应用级续传 |
| 错误重试/换源 | provider 链式回退（SWDM 1.x 已实现）+ 账号匿名双模式 |

### 4.3 真分段场景（推荐：SteamKit CDN 路线）

**这是把 IDM 体感变成真功能的路径**：
1. 用 SteamKit（C#，同语言生态）建立 Steam 会话（匿名或账号），取得 Workshop item 的 depot/manifest（DepotDownloader 的 `DownloadAppAsync(..., isUgc: true)` 即处理 UGC 路径，[ContentDownloader.cs](https://github.com/SteamRE/DepotDownloader/blob/b96125f9cbbb0f63d47e14784929f255f6c21ce1/DepotDownloader/ContentDownloader.cs)）。
2. manifest 给出**文件→chunk 列表**（chunk 为 steam 清单级分块，各有 SHA 校验）——天然就是 IDM 的"分段"。
3. 经 `CDNClientPool` 并行 HTTP 拉 chunk（`-max-downloads` 默认 8 并发，[README](https://github.com/SteamRE/DepotDownloader/blob/master/README.md)）：**真正的多连接并行 + 连接池复用 + 服务器加权轮换 + 失败转移**——这就是 Steam 世界的 IDM 内核。
4. 速度/并发/限速/进度全部在 SWDM 掌控之内：限速用令牌桶在 chunk 调度层实现（真限速，非假象）。
5. chunk 有 SHA 校验 → 完整性验证天然存在，比 IDM 的重叠字节比对更强。

**HTTP 直链场景（可真分段）**：Workshop 的**预览图/预览视频**等静态资源走 HTTP 直链 CDN（steamuserimages / steamstatic），可直接用 §3 的 HttpClient Range 分段方案。Mod 内容本体不是直链——**任务书所说"Mod 页直接 CDN"应澄清为预览资源**；mod 内容的真分段只能走 §4.3 的 SteamKit chunk 路线。

---

## 5. 磁盘 IO：分段预分配与拼接策略

### 5.1 三种策略对比

| 策略 | 代表 | 优点 | 缺点 |
|---|---|---|---|
| A. 每段独立临时文件 + 完成后拼接 | IDM（`.idm.tmp` + rebuild） | 目标文件不受下载中断污染；网络盘友好 | 大文件需整份二次写盘（rebuild 慢；被 AV hook 时更慢，[problems5](https://secure.internetdownloadmanager.com/register/new_faq/problems5.html)） |
| B. 单文件 + 偏移量直写（免拼接） | bezzad/Downloader | 零拼接 IO；速度最快 | 目标文件在下载中被"看见"；需额外元数据 |
| C. B + NTFS 稀疏占位 | 推荐 | 先按总大小占位（`SetLength` 或 sparse），多 worker 各自 Seek+Write 互不竞争；AV 友好（不频繁创建新句柄） | 需 P/Invoke |

### 5.2 C# 实现（NTFS Sparse）

- 原生 API：`DeviceIoControl` + **`FSCTL_SET_SPARSE`** 把文件标记为稀疏——"Space for nonzero data will be allocated as needed as the file is written"（[Win32 文档](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_sparse)）；稀疏区间可用 `FSCTL_SET_ZERO_DATA` 显式置零但不分配（[Sparse File Operations](https://learn.microsoft.com/en-us/windows/win32/fileio/sparse-file-operations)）。
- .NET 无托管封装，需 P/Invoke（[SO #17817746](https://stackoverflow.com/questions/17817746/how-to-create-fast-and-efficient-filestream-writes-on-large-sparse-files)）——示例代码已存在：`NTFS.Sparse.SparseFile.Create(filename)` + `SetSparseBlock(handle, startIx, 128*1024)`（[Microsoft Learn 归档博客](https://learn.microsoft.com/en-us/archive/blogs/codedebate/ntfs-sparse-files-with-c)）。
- **前置检查**：`GetVolumeInformation` 取 `FILE_SUPPORTS_SPARSE_FILES` 位，不支持（exFAT/FAT32/部分网盘）则降级为普通 `SetLength` 全分配（[fsutil sparse 文档](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-sparse)）。
- **不可逆警告**：文件一旦标记稀疏就**无法转回**（只能整份复制脱帽）——故只在下载期文件上用，**不要**对用户既有库文件操作（SO #17817746 经验）。
- **默认行为建议**：偏移量直写（策略 B）为主，稀疏占位（策略 C）为大文件可选，拼接（策略 A）仅作网络盘/特殊场景回退——与 IDM 的"滞留临时目录"故障案例（§1.3）背离的原因正是拼接路径重。

### 5.3 元数据尾部追加（续传状态）

仿 bezzad/Downloader：目标文件正常写入；续传元数据（chunk 表 + URL + ETag + 来源页）以**定长头 + 偏移指针**写入**文件尾部**，下次下载先读尾部、校验、恢复 chunk 状态。优点：单文件自包含、无外部状态文件丢失风险、续穿校验与文件本体绑定（[PR #212](https://github.com/bezzad/Downloader/pull/212)、[NuGet 文档](https://www.nuget.org/packages/Downloader)）。

---

## 6. 检索限制与诚实的不确定性

1. **web_fetch 不可用**：本机 fake-IP 代理 DNS 环境下，`internetdownloadmanager.com`、`stackoverflow.com`、`nuget.org`、`raw.githubusercontent.com`、`context7.com` 等全部报 "resolves to a non-public IP address"。本文所有引用内容均来自搜索引擎（exa/tavily/bing/baidu）返回的**站点原文片段**，已核对语义；未获取的全文以片段为准。
2. **IDM 内核为闭源商业软件**：分段临时文件的字节级结构、`.idm` 二进制格式、速度公式与刷新频率**均无官方文档**；本文标注的均为社区经验或官方 FAQ 的**功能性自述**（如重叠字节校验）。
3. **"Xelon" 未检索到**对应 C# 下载库（见 §3.2 末）。
4. **steamcmd 100 Mbps 限制**为社区报告（GitHub issue #6321 等），非 Valve 官方声明。
5. Valve Developer Community 的 SteamCMD 页面被 Anubis 反爬拦截，steamcmd 行为以社区经验 + Steamworks 官方文档为准。

---

## 7. 参考来源汇总

**IDM 官方**：
- [Dynamic Segmentation and Performance](https://www.internetdownloadmanager.com/support/segmentation.html)
- [Options Dialog（连接数建议/例外表）](https://mirror5.internetdownloadmanager.com/support/options.html)
- [Main program window dialog](https://www.internetdownloadmanager.com/support/main.html)
- [IDM Queues](https://www.internetdownloadmanager.com/support/idm-scheduler/idm_queues.html) / [Scheduler](https://www.internetdownloadmanager.com/support/idm-scheduler/idm_scheduler.html) / [schedulerD](https://www.internetdownloadmanager.com/support/schedulerD.html)
- [features2（调度器能力）](https://help.internetdownloadmanager.com/features2.html)
- [FAQ: 文件损坏/重叠字节校验 problems9](https://www.internetdownloadmanager.com/register/new_faq/problems9.html)
- [FAQ: rebuild 临时文件慢 problems5](https://secure.internetdownloadmanager.com/register/new_faq/problems5.html)
- [FAQ: 临时链接从头下载 sites2_6](https://www.internetdownloadmanager.com/register/new_faq/sites2_6.html)
- [FAQ: 代理故障 problems1](https://www.internetdownloadmanager.com/register/new_faq/problems1.html)
- [FAQ: 一次下一个文件 functions5](https://www.internetdownloadmanager.com/register/new_faq/functions5.html)
- [FAQ: 添加分类 functions12](https://secure.internetdownloadmanager.com/register/new_faq/functions12.html)
- [FAQ: 临时目录 functions17](https://www.internetdownloadmanager.com/register/new_faq/functions17.html)

**社区经验**：
- [Stack Overflow #12583465：IDM/FlashGet 机制](https://stackoverflow.com/questions/12583465/how-is-idm-and-flashget-are-working-maximum-speed-download)
- [SuperUser #657720：IDM 续传与链接刷新](https://superuser.com/questions/657720/how-does-idm-resume-a-paused-http-download)
- [SuperUser #320402：续传返回网页报错](https://superuser.com/questions/320402/resuming-a-download-using-internet-download-manager)
- [eightforums：DwnlData 临时目录行为](https://www.eightforums.com/threads/dwnldata-in-internet-download-manager.32311/)
- [TrueSight：IDM 临时文件深度剖析](https://tsight.io/articles/9366930)
- [helpdeskgeek：是否真的加速](https://helpdeskgeek.com/does-internet-download-manager-increase-download-speed/)
- [wikiHow：连接数调整](https://www.wikihow.com/Speed-Up-Downloads-when-Using-Internet-Download-Manager-(IDM)) / [dealarious](https://www.dealarious.com/blog/idm-unknown-features)
- [Reddit r/networking：4–8 流实测](https://www.reddit.com/r/networking/comments/4s5hy5/single_streams_connection_issue/) / [r/explainlikeimfive](https://www.reddit.com/r/explainlikeimfive/comments/1jq4knt/eli5_how_do_download_managers_accelerate_download/) / [r/Roms](https://www.reddit.com/r/Roms/comments/16wpi50/do_idms_speed_up_downloads/) / [r/software](https://www.reddit.com/r/software/comments/ty2k62/need_help_with_idm_internet_download_manager/)
- [digit 论坛：自动续传需 Scheduler](https://geek.digit.in/community/threads/does-idm-auto-resume-broken-download.197174)
- [Apeaksoft：IDM 文件恢复（.idm 语义）](https://www.apeaksoft.com/recover-data/recover-deleted-files-on-idm/)
- 中文镜像（UI 字段）：[idmchina 主对话](https://www.idmchina.net/jiaocheng/idm-ehgk.html)、[idmxiazai 主界面](https://idmxiazai.com/docs/%e4%bd%bf%e7%94%a8%e6%95%99%e7%a8%8b/%e4%b8%bb%e7%95%8c%e9%9d%a2/)、[cninternetdownloadmanager](https://www.cninternetdownloadmanager.com/help-884.html)

**C#/.NET**：
- [HttpClient guidelines for .NET](https://learn.microsoft.com/en-us/dotnet/fundamentals/networking/http/httpclient-guidelines)
- [MaxConnectionsPerServer](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler.maxconnectionsperserver?view=net-9.0) / [SocketsHttpHandler](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler?view=net-10.0)
- [Dave Mateer：HttpClient 连接池](https://davemateer.com/2020/10/14/httpclient-connection-pooling)
- [Cloudflare：HTTP/2 for Web Developers](https://blog.cloudflare.com/http/2-for-web-developers) / [dev.to HTTP/2 streams vs connections](https://dev.to/sibiraj/understanding-http2-parallel-requests-streams-vs-connections-3anf)
- [bezzad/Downloader](https://github.com/bezzad/Downloader) / [NuGet 文档（续传流程）](https://www.nuget.org/packages/Downloader) / [PR #212 尾部元数据](https://github.com/bezzad/Downloader/pull/212) / [issue #119 不支持 Range 的降级](https://github.com/bezzad/Downloader/issues/119) / [Chunk.cs](https://github.com/bezzad/Downloader/blob/e4ab807a2e107c9ae4902257ba82f71b33494d91/src/Downloader/Chunk.cs)
- [NTFS Sparse Files with C#（MS Learn 归档）](https://learn.microsoft.com/en-us/archive/blogs/codedebate/ntfs-sparse-files-with-c) / [FSCTL_SET_SPARSE](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_sparse) / [Sparse File Operations](https://learn.microsoft.com/en-us/windows/win32/fileio/sparse-file-operations) / [SO #17817746](https://stackoverflow.com/questions/17817746/how-to-create-fast-and-efficient-filestream-writes-on-large-sparse-files)

**Steam/SteamKit**：
- [Steamworks：Uploading to Steam（SteamPipe=HTTP）](https://partner.steamgames.com/doc/sdk/uploading)
- [DepotDownloader README（-max-downloads 默认 8）](https://github.com/SteamRE/DepotDownloader/blob/master/README.md) / [ContentDownloader.cs](https://github.com/SteamRE/DepotDownloader/blob/master/DepotDownloader/ContentDownloader.cs) / [PR #132 per-chunk](https://github.com/SteamRE/DepotDownloader/pull/132) / [DeepWiki 并行系统](https://deepwiki.com/SteamRE/DepotDownloader/3.2.2-parallel-download-system) / [DeepWiki CDN 管理](https://deepwiki.com/SteamRE/DepotDownloader/3.3-cdn-management)
- [SteamKit PR #1471：原始 CDN manifest/chunk API](https://github.com/SteamRE/SteamKit/pull/1471) / [steam cdn 文档](https://steam.readthedocs.io/en/latest/api/steam.client.cdn.html)
- [ValveSoftware/steam-for-linux #6321：steamcmd 限速/超时](https://github.com/ValveSoftware/steam-for-linux/issues/6321)
- [Reddit：匿名账号限制](https://www.reddit.com/r/steamsupport/comments/v6ddu1/steam_cmd_error_when_downloading_workshop_content)
