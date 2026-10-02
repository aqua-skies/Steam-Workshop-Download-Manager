# SWDM 2.0 变更记录（CHANGELOG）

> 规则：每次迭代/阶段交付门升级一次版本号并追加条目（迭代交付四要素之一）。
> 版本号单一事实源：`swdm2/Directory.Build.props`（Version 字段）+ 本文件。
> 阶段版本映射（DAG architecture_2.0.md §6）：0.1.0=阶段 1 · 0.2.0=阶段 2 · 0.3.0=阶段 3 · 0.4.0=阶段 4 · 0.5.0=阶段 5 · 0.6.0=阶段 6 · 2.0.0=正式版。
> 条目溯源格式：任务号 + 交付内容 + 验证证据。

---

## [0.2.0] · 2026-10-02 · 阶段 2：Steam 域基础设施（D2.7 交付门）

**四要素**：全量回归 155/0（build 0-0+SteamTestsDriver 78/0+CoreTestsDriver 72/0+UiTestsDriver 5/0，SP-3 沙箱驱动，TEMP+TMP 双重重定向）· 讨论组评审 `docs/process/review_2.0_0.2.0.md`（三原则，arch-20/qa-20/visual-20 投票）· 版本 0.2.0（`Directory.Build.props`）· 本变更记录。

### 新增（Steam 域：Web/Connectivity/Resilience/Community）

- **D2.1 HttpClient 工厂与代理显式接管**（t15,4e2ab4a):`Steam/Web`(IHttpClientFactory+SteamHttpClientFactory:ProxyMode 三态注入 SocketsHttpHandler——Direct 显式禁用/SystemProxy 系统代理/Custom 显式 WebProxy+URL 校验>InvalidConfiguration)+`SteamHttpHeaders` 指纹头四件套（UA/Accept/Accept-Language **承重头**/X-Requested-With 冗余层——1.x 429 学费实证移植，X-Requested-With 旧结论经 research_2 复测推翻标注）+MaxConnectionsPerServer 参数化（SteamOptions 新增，C7)。
- **D2.2 端点可达性探测**（t16,0a18be7):`Steam/Connectivity`(IEndpointProbe:GET+ResponseHeadersRead 轻探不读体/超时 5s;403→Blocked、超时-DNS-TLS→Unreachable、其余可达、429 归可达限流归 D2.4)+IConnectivityState(Unknown 初值/变更触发 Changed 同值不触发 latency 变=状态变/快照不可端）。双网络环境真实探测 `docs/connectivity_probe_2.2.md`:A(代理 Custom 7897)三端 ViaProxy;B(Direct 经 TUN)三端 Direct——诚实标注预判“直连不可达”未成立（fake-IP 为 TUN SNI 网关）。
- **D2.3 Web API 客户端**（t17,9652cb2):GetPublishedFileDetails(batch `itemcount=N` 批封包）+GetCollectionDetails(children sortorder 排序+嵌套递归 BFS 展开+**999↔200 环引用 visited 保护**)+storesearch；失败映射 8 类 SteamError(429/403/404/401/5xx+网络/JSON/超时/取消/result:9);IConnectivityGate 门（Api 不可达 0 请求发出）。真实在线验证 id 3808352517 result:1+title"KFC - Chicken Bucket"(captain 代理直连补验；沙箱在线测试网络阻断时驱动诚实标注“环境阻断非实现缺陷”）。
- **D2.4 节流器与熔断器**（t18,f13a379):`Steam/Resilience/Throttler.cs` 单文件全量——IThrottler（bucket 差异化+每 bucket SemaphoreSlim 全程锁=同 bucket 串行+锁内 DelayAsync 强制最小间隔+跨 bucket 不互阻）;ICircuitBreaker(Closed→阈值 5→Open→冷却 60s→HalfOpen 单试探→成功 Closed/失败 Open 重计）;ITimeProvider/System/FakeTimeProvider（假钟 seam:逻辑推进真实毫秒不流逝）;ResiliencePipeline 门面（开态/排队后复检 IsOpen→Result.Fail(CircuitOpen) 不抛+acquire→门→请求→结果计熔断）。客户端集成（api/store bucket 注入，默认 null 不破坏现有调用）。
- **D2.5 社区页面回退**（t19,43da3f0):`Steam/Community`——Browse 列表+详情富化+**可达门（S4:Community 未验证可达=Fail(Network) 0 请求）**+D1.6 缓存出口深拷贝；CommunityHtmlParser 只锚稳定结构（**实测研究结论**：browse 页 React 改版旧 workshopItem 类消失=混淆 CSS→锚 filedetails/?id=N+img src/alt;detail 页 workshopItemTitle/creatorsBlock 旧类仍稳；AppId 锚 myworkshopfiles/?appid=N——评论区 JSON 内 appid 为转义串不可直接正则）。真实 fixture（代理 7897 抓取 browse 679KB/30 物品含 KFC - Chicken Bucket;detail 109KB）内嵌资源。

### 变更（参数重标定，D2.6 用户"经验复验纪律"）

- **D2.6 B1+B2 实测重标定**（t20,ab803fb):CalibBench 独立控制台 86 分钟/436 条原始记录（`docs/calibration_1.{csv,json,md}`）。
  - **B1**：诱导 429（裸 burst,体 330034B)→等 5-90s×3→指纹头复测 **24/24 全 200**=解除机制是**头指纹（Accept-Language）非等待时长**——1.x 退避假设复验推翻但保留作防御默认（BackoffInitial 5000/BackoffMax 90000 不变，依据改为"防御性"）。
  - **B2**:0.5s×20 连发**零失败**（0.5s 档连过 30 次=r1 全 20+r2 前 10);1s+ 档通过/失败按累计预算跨轮移动（非间隔驱动，详见 calibration_1.md 修正后逐轮表）——**限流=会话窗口累计请求天花板（~117 次请求）非间隔维度**。8s 档轮内部分恢复（单轮跨 160s)=**时间恢复机制的直接证据**，与"天花板非间隔"结论相互印证。天花板恰由 D2.4 熔断器兜底（120s 冷却≈重置 20 次预算）。
  - **参数锁定**：`ThrottleMs[0]/[1]` 6000/2000 → **1000/1000**（appsettings.json+Throttler.DefaultIntervals+SteamOptions 文档三同步；ResilienceTests 默认间隔断言同改）。
- **误诊撤回**：20:21 曾判"Steam 端点对出口 IP 限流"，实为用户关闭代理软件（用户 20:50 告知）——诊断网络失败先确认本地代理/出口状态再归因远端。

### 验证

- SP-3 沙箱驱动模式（xUnit testhost 崩溃→控制台驱动反射同一测试方法）：build 0-0;SteamTestsDriver 78/0(D2.1 17+D2.2 11+D2.3 21+D2.4 17+D2.5 12);CoreTestsDriver 72/0;UiTestsDriver 5/0。
- 跨内容关联：客户端←工厂指纹头（stub 字节级断言）←可达门←节流桶←熔断器←缓存深拷贝；在线=result:1+双环境探测+三档标定全真实网络。

### 已知保留（C7 待重标定，不阻碍 0.2.0)

- api bucket 100ms/store bucket 250ms 未在 B2 覆盖（非 429 敏感路径）→D3/D4 或 0.3 迭代覆盖。
- 标定天花板数值（~117）为单出口 IP 单轮观测值，跨环境须复测。
- B1 退避值 5000/90000 为防御默认（实测无必要性证据，亦无反证）。

---

## [0.1.0] · 2026-10-02 · 阶段 1：Core 域契约（D1.7 交付门）

**四要素**：全量回归 77/0 绿（SP-3 沙箱驱动模式）· 讨论组评审 `docs/process/review_2.0_0.1.0.md`（三原则）· 版本 0.1.0（`Directory.Build.props`）· 本变更记录。

### 新增

- **D0.2 骨架接线**（t6）：Downloads→Steam ProjectReference（依赖链 Core←Steam←Downloads 单向无环）；UiTests 按 t3 §2.1 包清单接线（FlaUI 5.0.0 + xunit 2.9.0 + runner 2.8.2 + Xunit.StaFact——规格 1.2.1 实测不存在于 NuGet，实证替代 2.1.7 并通报 qa-20 回写 t3；`xunit.runner.json` 强制串行）；App 空白窗口 + `AutomationId=MainWindow`（A7 可靠载体）+ `AppLaunchSmokeTests`（[WpfFact] 进程外启动断言）。
- **D1.1 领域模型与结果模型**（t7）：`Core/Domain`（AppId/PublishedFileId/UgcId/DownloadTaskId 强类型 id，C6 类型级隔离 + 枚值校验 + TryParse；WorkshopItem/GameInfo/DownloadTask/ModLibraryEntry 不可变 record，集合防御性拷贝 + 结构性相等重写）；`Core/Results`（`Result<T,TErr>` 双分支结果模型 + SteamError/DownloadError 各 10 码）。`Swdm2.Core.Tests` 单测项目落地。
- **D1.2 路径服务**（t8）：`Core/Paths`（便携=exe 同级 / 安装=%APPDATA%\SWDM，C3 构造期锁定；WorkshopContent 与 SCA 同构 `<Root>/steamcmd/steamapps/workshop/content/<appid>`；DownloadStaging 纯函数确定性；EnsureDirectories 幂等；Detect 按 `swdm2.portable` 标记自动判模式）。
- **D1.3 配置与选项骨架**（t9）：`Core/Options`（ProxyMode 三态 + SteamOptions/DownloadOptions/PathOptions，全部数值 ⚠️[参数待重标定] C7 三重标注 + DataAnnotations 范围验证）；App 侧 appsettings.json + SwdmConfiguration（reloadOnChange + 运行时 ConfigFile 叠加 + IOptionsMonitor 热更新）。
- **D1.4 凭据存储**（t10）：`Core/Credentials`（ICredentialStore 契约 C2 + DpapiCredentialStore：ProtectedData.CurrentUser、原子写入、单写者锁、ZeroMemory、异常文安化、账号键归一、删除幂等、空密码拒绝、不存在=返回 null）。
- **D1.5 日志契约与脱敏 sink**（t11）：`Core/Logging`（RegexRedactionPolicy：键值标记/授权头/账号型三正则，中英双语）+ `App/Logging`（RedactingTextFormatter 两层防线：属性名 17 黑名单 + 渲染后文本正则兜底；SwdmLogging 启动期单点装配：File formatter + RollingInterval.Day + UTF8）。
- **D1.6 缓存抽象**（t12）：`Core/Caching`（IAsyncCache 契约 C5 + AsyncCache：ConcurrentDictionary + 每键 SemaphoreSlim single-flight + TTL；**双向深拷贝隔离**——命中克隆出口（消费侧，1.x enrich() 污染对价）+ 插入克隆入存（生产侧），默认 System.Text.Json 往返克隆器；负缓存 + 异常不毒化）。
- **版本基础设施**（D1.7）：`swdm2/Directory.Build.props` 全项目统一 Version/AssemblyVersion/FileVersion（+ SourceRevisionId 指向 git 提交）。
- **测试基础设施**（D1.7）：`tests/CoreTestsDriver/` 控制台反射驱动（SP-3 沙箱 testhost 崩溃的替代路径，captain 搭建）；`tests/UiTestsDriver/` 同模式 STA 驱动（本门新增，交 qa-20 审；纯反射特性匹配规避 xunit.core/xunit.v3.core CS0433 二义 + 引入 D1.5r 假绿教训的 IsAssignableFrom 兜底）。

### 修复

- **D1.5r 脱敏回归修复**（t14，commit 25086c0，D1.7 门回归抓出 + bug 归属制闭环）：
  - RegexRedactionPolicy 替换串硬编码不保留原分隔符（密码 `/`+中文冒号等形态被截断）→ 按原文分隔符形态重组；
  - 键表缺裸 `code`（验证码场景）→ 补齐；
  - 暗坑 ①：撇号紧贴敏感词尾部时截断泄漏（`P@ss...Don't` → `***'t`）；
  - 暗坑 ②：JSON 闭合引号形态的尾分隔符隔断，导致 `"token":` 整段完全不脱敏。
  - 根因坦承：历史"63/63 全绿"为假绿——自写驱动按特性 `Type.Name` 精确匹配筛方法，TheoryAttribute 派生自 FactAttribute 但 Name 不同，9 个 [Theory] 行被静默跳过。教训入过程纪律：自写测试驱动必须 IsAssignableFrom 匹配 + Theory/InlineData 展开 + 第二人独立复跑计数对账。
- **D1.3 ConfigurationBinder 坑**（t9 内修）：预填数组默认值与 JSON 绑定是追加而非替换（静默拼接错误配置）→ 类默认 `Array.Empty<T>` + 起点值只由 appsettings.json 承载。
- **D1.4 遗漏路径**（t11 内修）：FormatException（Base64 损坏密文）未走包装路径 → 纳入 CredentialStoreException 安全文案。

### 验证（0.1.0 全量回归，SP-3 沙箱驱动模式）

| 命令 | 结果 |
|---|---|
| `cd swdm2; dotnet build Swdm2.sln -c Debug --nologo -v q` | 0 警告 0 错误 |
| `dotnet run --project tests/CoreTestsDriver` | pass=**72** fail=0 skip=0（=63 [Fact] + 9 [Theory] 行，真数；历史 63/63 为驱动假绿） |
| `dotnet run --project tests/UiTestsDriver` | pass=**5** fail=0 skip=0（4 脱敏管道 + 1 AppLaunch 真实进程冒烟，Application.Launch → UIA3 定位 MainWindow） |
| 环境要点 | dotnet 派生进程的 `%TEMP%`/`%TMP` 双重重定向至 `swdm2/.dtmp`（GetTempPath 读 TMP 优先，仅重定向 TEMP 无效） |

**关联交互回归覆盖**（功能间关联，非单点）：D1.4+D1.5 联合（凭据明文不入日志文件管道）；D1.2+D1.3（路径/选项在双模式与热更新下的组合）；D1.6 C5 双向缓存隔离（消费侧 + 生产侧变异）；D1.1 C6 类型隔离（编译期 + 反射断言）。

### 已知非阻塞项

- t2 视觉规格 v1.1 回写（A7 载体表同步：SwdmCard/Hint 根元素 UserControl 化等）由 visual-20 于 D5 前自办（评审记录 `docs/process/review_2.0_plan.md` 遗留项）。
- t3 测试规格 v1.x 回写（StaFact 2.1.7 实证约束 + Calibration 迁 Core.Tests + §7.2 映射同步）由 qa-20 自办中。
- WPF-UI 4.3.0 API 表面按 A8b 于首次使用前反射实测（SP-1 已实证两处 API 漂移：SymbolRegular 无 Regular 后缀 / ui:Card 无 Header）。
- 参数类数值全部 ⚠️[参数待重标定]：B1/B2→D2.6，B3→D4.8（t3 §5 基准），A9 即时反馈阈值→D5.10。

---

> 0.1.0 为基础设施版本，不发布给最终用户（无 Velopack 打包/安装器）；首版对外交付 = 2.0.0（D7.4）。
