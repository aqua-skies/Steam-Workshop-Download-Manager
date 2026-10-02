# C# 下载 Steam Workshop Mod 的方法调研（SWDM 2.0 / WPF 重写）

> 调研日期：2026-10-02 · 方法：GitHub API 直查开源仓库 + 源码精读（拉取真实 .cs 文件逐行阅读）+ Steamworks 官方文档 + **本机实测 API 端点**（经 127.0.0.1:7897 fake-IP 代理出口）+ 本项目 1.x 代码沉淀。
> 限制声明：Valve Developer Community wiki（developer.valvesoftware.com）被 Anubis 反爬拦截无法直读，steamcmd 部分结论来自多个独立开源项目的源码与社区帖；本机出口为香港 IDC 小 ISP IP（AS134972），API 实测结果已按「设计对照纪律」标注网络环境。

---

## 0. 摘要与核心结论

1. **下载链路两选一：steamcmd 进程封装（黑白盒稳）或 SteamKit2 原生客户端（性能强、复杂度高）。** 社区开源 C# 项目（SteamCollectionDownloader、DepotDownloader）证明两条路在 C# 中都工程可行。
2. **steamcmd 封装是 C# WPF 的最低成本正解**：`+login anonymous +workshop_download_item <appid> <pubfileid> +quit` + stdout 正则解析即可覆盖 90% 场景；坑集中在**假成功判定**、**退出码不可信**、**Steam Guard 交互**三点，均有开源范例（§2）。
3. **SteamKit2 在 2026-09 仍活跃维护**（3204★，2026-09-16 最新提交），DepotDownloader 以 `-pubfile <id>` 支持**匿名** Workshop 下载（仅限 sub 17906 匿名可用的 app），且提供 `-max-downloads 8` chunk 级并发——这是「真·IDM 体感」的路径（详见姊妹报告 [idm_download_kernel.md](./idm_download_kernel.md) §4.3）。
4. **Steamworks Web API 匿名可用部分极度受限**：`ISteamRemoteStorage/GetPublishedFileDetails` 与 `/GetCollectionDetails` 端点本身**不要 key**，但本机实测匿名调用仅返回 `result:9` + 全空字段（`file_url`/`file_size`/`title` 皆为 null）；社区证据（gmosh issue #20）表明 Valve 于 2017-12 起从该端点**删除 file_url 字段**。`GetUGCFileDetails` 明确**需要 key**。**结论：元数据获取走 Web API 不可靠，1.x「steamcommunity.com 页面抓取」路线仍是匿名元数据主源**（§4）。
5. **`ISteamRemoteStorage/GetFileSize` 端点已不存在**：本机实测返回 `Method 'GetFileSize' not found in interface 'ISteamRemoteStorage'`（404），任务书列出的该端点应从设计中剔除（§4）。
6. 网络弹性：**重试 + 指数退避 + 熔断**是 C# 标配组合（Polly 或手写），本机 fake-IP 环境有特殊的 DNS/TLS 陷阱须显式处理（§7）。

---

## 1. steamcmd 封装：C# 进程包装最佳实践

### 1.1 命令行形态（精读开源源码确认）

来自 **Grzeho1/SteamCollectionDownloader**（C# WPF，15★，2026-07 仍更新，[GitHub](https://github.com/Grzeho1/SteamCollectionDownloader)）`MainWindow.xaml.cs` 实现的批量下载参数拼接：

```csharp
var sb = new StringBuilder();
sb.Append($"+login {loginUser}");              // loginUser = "anonymous" 或账号名
foreach (var (gameId, workshopId, _) in items)
    sb.Append($" +workshop_download_item {gameId} {workshopId}");
sb.Append(" +quit");
```

即：**`steamcmd.exe +login anonymous +workshop_download_item {appid} {pubfileid} [+validate] +quit`**。多个 item 可拼成**一次进程调用**（批量降低冷启动开销，代价是失败粒度变粗，需自行按 item 拆分统计）。

SWDM 1.x 引擎（`swdm/core/steamcmd_engine.py`，本组实战代码）证实另一关键参数：**`+force_install_dir <目标目录>`** 必须放在 commands **之前**才能把下载产物重定向到自选目录：
```python
args = [exe, "+force_install_dir", target_dir] + commands + ["+quit"]
```

### 1.2 进程启动参数（两个独立 C# 实现一致）

```csharp
var startInfo = new ProcessStartInfo
{
    FileName = steamCmdPath,
    Arguments = sb.ToString(),
    RedirectStandardOutput = true,
    RedirectStandardError = true,
    UseShellExecute = false,          // 必须 false 才能重定向
    CreateNoWindow = true,            // 不弹黑框
    StandardOutputEncoding = Encoding.UTF8,   // steamcmd 输出含非 ASCII，防乱码
    WorkingDirectory = Path.GetDirectoryName(steamCmdPath)  // steamcmd 需在自身目录启动
};
```
（来源：SteamCollectionDownloader `MainWindow.xaml.cs:361-370` 与 `SteamAuth.cs:74-85`）

C# 特有坑（相对 Python subprocess）：
- **stdin 处理**：交互式提示（验证码、2FA）可写 `process.StandardInput.WriteLine(code)`；但若不需要交互，**立即 `process.StandardInput.Close()`** 更稳—— stdin 被关闭后 steamcmd 不会卡在等待输入。
- **取消语义**：`CancellationToken.Register(() => process.Kill())`；Kill 后 `WaitForExitAsync` 抛出/返回前要排空 stdout/stderr 读取任务，否则重定向缓冲区满会**死锁**（1.x 同样用「先写 `quit\n` 再 terminate 再 wait(timeout=30)」三段式收尾）。
- **多任务共享 engine 时用局部变量保存 proc 句柄**（1.x bug7 教训：共享 `_proc` 被并发任务覆盖导致 `poll()` 空指针）。
- **输出回显敏感信息过滤**：steamcmd 会回显账号名（`Connecting to Steam as <name>`），C# 里应在进入日志/UI 前做 `line.Replace(username, "***")`（1.x `_redact_secrets` 的 C3 风控规则）。

### 1.3 输出行解析正则（三个来源汇总，可直接照抄）

| 事件 | 正则 | 来源 |
|---|---|---|
| 下载开始 | `Downloading item (\d+)` | SCA / SWDM 1.x |
| **成功（含路径与字节数）** | `Success\. Downloaded item (\d+) to "([^"]+)" \((\d+) bytes\)` | SWDM 1.x `_SUCCESS_RE` |
| 失败 | `ERROR! .*｜Failed to download item \d+.*｜Timeout .*｜Not Logged On.*` | SWDM 1.x `_FAIL_RE` |
| 登录成功 | `Logged-in OK｜Waiting for user info.*OK｜Connecting anonymously to Steam Public.*OK` | SWDM 1.x |
| 登录失败 | `Login Failure｜Invalid Password｜Not Logged On｜[Rr]ate ?[Ll]imit` | SWDM 1.x / SCA |
| SCA 版成功（简版，丢弃路径/字节） | `Success\..*?item (\d+)` | SCA |
| SCA 版失败（带原因子串） | `ERROR.*?[Dd]ownload(?:ing)? [Ii]tem (\d+).*?\((.+?)\)` | SCA |

**推荐采用 1.x 版成功正则**：它额外拿到**产物绝对路径与字节数**——正是「0 字节假成功」检测的第一道防线。SCA 版是正则失败容错的范例（即使格式微变也能提取失败原因）。

### 1.4 三大 quirk 与对策（开源项目实锤）

**① 0 字节假成功 / 磁盘校验是强制步骤。**
steamcmd 可能输出 `Success. Downloaded item X ... (0 bytes)` 或即使失败也留下空目录。**SCA 的对策是 sweep 兜底**（`MainWindow.xaml.cs:465-482`）：进程结束后，对所有既无 Success 也无 ERROR 行的 item，检查产物目录是否存在且**递归非空**：
```csharp
string itemPath = Path.Combine(steamCmdDir, "steamapps", "workshop", "content", gameId, workshopId);
if (Directory.Exists(itemPath) && Directory.GetFiles(itemPath, "*", SearchOption.AllDirectories).Any())
    successful.Add(id);   // Success (verified on disk)
else
    failed.Add(id);       // Failed (no output, no files)
```
对**失败 item 还删除残留空目录**（`DeleteFailed()`，`Directory.Delete(itemPath, true)`），防止下次被「已存在即跳过」逻辑误判为已下载（SCA 下载前跳过逻辑即 `Directory.Exists && 递归非空` 双条件）。这一条是 SWDM 2.0 必须照抄的**「成功三元判定」：输出行 Success + bytes>0 + 磁盘非空**。

**② 退出码不可信，必须以输出行为准。**
SCA `SteamAuth.cs:340-348` 体现了正确顺序：先看 `loginOk`/`failureOutcome`（从**输出行**解析），最后才看 `process.ExitCode == 0`——且 ExitCode 非零仅作为「OtherFailure」兜底。社区与 Valve 文档从未保证 steamcmd 退出码与 item 粒度结果对应（单进程批量下载多个 item 时退出码无法表达哪个失败）。

**③ `+quit` 语义：命令行的命令是顺序执行的，`+quit` 在末尾才执行。**
SCA 把 `+login`、多个 `+workshop_download_item`、`+quit` 拼成**单次调用**——优点是省去 N 次进程启动，缺点是**中途某 item 失败不中断后续 item**（steamcmd 继续执行下一条 +workshop_download_item）。`+force_install_dir` 必须在任何下载命令**之前**才生效（SWDM 1.x 实测）。

### 1.5 匿名登录与不能下载的 app

- **匿名账号 `+login anonymous`** 覆盖大部分免费/服务端类 app；**付费游戏内容的 Workshop item 需要拥有该游戏的账号**（[SCA README](https://github.com/Grzeho1/SteamCollectionDownloader/blob/master/README.md) 明确「Optional login with your own Steam account (required for workshop items of paid games you own)」；[YouTube 教程](https://www.youtube.com/watch?v=fxFX9uamHvI) 同样说明「some games may require authentication with a real Steam account that actually owns the game」）。
- **WorkshopDL 的实用技巧**：不在 [steamdb sub 17906](https://steamdb.info/sub/17906/apps/)（匿名可用 app 清单）的游戏，可**改用其专用服务器的 AppID** 下载同款 mod（[WorkshopDL README](https://github.com/fidget77/WorkshopDL/blob/master/README.md) Note 2）。SWDM 2.0 的 AppID 别名体系（1.x 已有 55 条中英别名）应把「DS AppID 回退」做成内置规则。
- DepotDownloader README 亦确认：匿名默认可用，`-username` 后交互输入密码可访问受限内容；旧 manifest 可能 401（「Try logging in with a Steam account, this may happen when using anonymous account」）。

### 1.6 Steam Guard / 2FA 验证码处理（SCA 是完整范例）

SCA 的 `SteamAuth.cs`（351 行，纯 C#，无 SteamKit 依赖）实现了一次**两阶段登录**，值得 2.0 直接参考：

1. 首次尝试 `+login "用户名" "密码" +quit`，**关掉 stdin** 防卡死；
2. 并行三路监听：**stdout / stderr / steamcmd 自身日志文件尾随**（`logs/console_log.txt`，记录已读偏移量增量读取，200ms 轮询）——因为某些关键提示行（`STEAM GUARD CODE:` 等） stdout 可能吞掉而磁盘日志里有；
3. 命中提示行（`THIS COMPUTER HAS NOT BEEN AUTHENTICATED` / `CHECK YOUR EMAIL` / `STEAM GUARD CODE:` / `TWO-FACTOR AUTHENTICATION` / `MOBILE AUTHENTICATOR`）即 **Kill 进程**（避免 steamcmd 傻等 stdin），判定 `NeedsGuardCode`；
4. WFP 弹框收码（`TaskCompletionSource<string?>` + `Dispatcher.Invoke` + `ShowDialog`），第二次 `+login "用户名" "密码" "验证码" +quit`；
5. 错误分类：`InvalidPassword` / `InvalidGuardCode`（`TWO-FACTOR CODE MISMATCH`）/ `RateLimited`（`RATELIMITEXCEEDED`、`ACCOUNTLOGINDENIEDTHROTTLE`）/ `OtherFailure`；
6. 三层超时：**绝对 8 分钟** + **60 秒无输出** + 取消令牌。

要点：**WPF 弹窗阻塞 darn不跨线程**——`PromptForGuardCodeAsync` 用 Dispatcher.Invoke 切 UI 线程 ShowDialog，之后 SetResult 唤醒后台 await。SCA README 也提示「Steam Guard code 有效期约 10 分钟，过期重来即可」。

### 1.7 steamcmd 的获取与部署

- **自动下载**：`https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip`（SCA 实现了这个 zip 下载 + `System.IO.Compression.ZipFile.ExtractToDirectory` + 校验 exe 存在）。SWDM 1.x 的 `steamcmd_deploy.py` 已有等价实现，2.0 直接移植逻辑。
- 产物路径：**`<steamcmd目录>/steamapps/workshop/content/{appid}/{pubfileid}`**（SCA 三处使用此路径，1.x `content_path()` 相同）。`+force_install_dir` 可把 `steamapps/` 重定向到任意目录。

### 1.8 现成的 C# steamcmd 封装开源项目（检索结论）

**结论：没有成熟、广泛使用的「C# steamcmd 封装库」可直接 NuGet 引用。** GitHub 检索（`steamcmd wrapper`，按 star 排序 30 项）结果以 PowerShell（[hjorslev/SteamPS](https://github.com/hjorslev/SteamPS)，90★）、Go、Rust、Python（[wmellema/Py-SteamCMD-Wrapper](https://github.com/wmellema/Py-SteamCMD-Wrapper)）为主，C# 仅两个：
- **[Grzeho1/SteamCollectionDownloader](https://github.com/Grzeho1/SteamCollectionDownloader)** — C# WPF，2026-07 仍在更新，功能最贴近 SWDM（集合/单品、匿名/账号、Steam Guard 弹窗、自动部署 steamcmd、appworkshop.acf 删除建议，见 §5）。
- **[SyntacticFlow/SteamCmdWrapper](https://github.com/SyntacticFlow/SteamCmdWrapper)**（4★，2026-09-28 更新）— RimPy 场景的 exe 垫片，下载前**备份目标目录为带时间戳的 zip 并删除旧目录**，解决「steamcmd 只覆写不删除已下架文件」的问题（见 §5.4）。
- **[WilliamVenner/WorkshopDLKiller](https://github.com/WilliamVenner/WorkshopDLKiller)**（C#，8★，2016）— 已查到记录，年代久远仅作历史参考。

⇒ **SWDM 2.0 须自研封装层**，可照搬 SCA 的进程/解析/鉴权三件套 + 1.x 的 force_install_dir/撤销/看门狗经验。Node 生态的 [Dahlgren/node-steamcmd](https://github.com/Dahlgren/node-steamcmd)（交互式封装）与 PowerShell 的 [BartJolling/ps-steam-cmd](https://github.com/BartJolling/ps-steam-cmd) 是跨语言的架构参考。

---

## 2. SteamKit2：能否匿名下载 Workshop

### 2.1 维护状态（2026-10 实测查证）

- **[SteamRE/SteamKit](https://github.com/SteamRE/SteamKit)**（即 SteamKit2）：**3204★，未归档，最近提交 2026-09-16**（NetHook2 fix for latest Steam client beta）、2026-09-12（auth ticket ack fix）、2026-09-11（protobuf 更新、包升级）。**活跃维护，跟随 Steam 协议变化。**
- NuGet 包 `SteamKit2` 当前 **3.4.0**；主分支构建需要 **.NET 10 SDK**（README 原文：`.NET 10.0 Runtime` required at runtime）——但 **DepotDownloader 用 net9.0 + SteamKit2 3.4.0** 且 `<RollForward>LatestMajor</RollForward>`，SWDM 2.0 若走此路建议 **net8.0/net9.0 + SteamKit2 3.4.0** 锁版本，不必追主分支。

### 2.2 匿名下载 Workshop：**可行，且有官方级范例**

**[SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader)**（C#，Readme 明确支持 Workshop）就是答案，用法（README 原文）：

```
./DepotDownloader -app <id> -pubfile <id> [-username <u> [-password <p>]]   # Workshop item 用 pubfile id
./DepotDownloader -app <id> -ugc <id>                                       # 或 ugc id
```
- **默认即匿名账号**，匿名可用的 app 清单见 [steamdb.info/sub/17906](https://steamdb.info/sub/17906/)。
- `-pubfile` 会**自动解析为 UGC id** 再下载（即 PICS → CDN 流程已内置）。
- **`-ugc` 与 `-pubfile` 不是同一 ID**：DepotDownloader issue [#713](https://github.com/SteamRE/DepotDownloader/issues/713)（2025 年）报告者用错 ID 得 `A task was cancelled`，换 `-pubfile` 即好——2.0 若暴露这两个参数必须在 UI 上提示区别。
- 2FA 记住登录：`-remember-password` 持久化 login key，否则每次都要 2FA（README FAQ）。
- 老旧构建可能 401/无 manifest code（开发者可封锁旧 manifest 下载），此时必须账号登录。慢速与超时：调大 `-max-downloads`（默认 8）。

### 2.3 社区结论：PICS/CDN 路线 vs steamcmd 路线

- **steamcmd 路线**：零依赖、单进程串行、无逐字节进度（只有 `Downloading item X …` → `Success … (N bytes)`，1.x fixtures 实证）、被黑盒封装时无法做真分段。
- **SteamKit2 PICS/CDN 路线**：C# 同语言原生、chunk 级 HTTP 并行（`CDNClientPool`，round-robin 加权 + 故障转移，`-max-downloads 8` 默认）——**这是唯一能给「IDM 体感」提供真分段素材的路线**（详见姊妹报告 [idm_download_kernel.md](./idm_download_kernel.md) §4.3）；代价是要自己处理会话、PICS 查询、manifest 解析、CDN 池、文件落盘，复杂度约等于重写半个 DepotDownloader。
- **steamcmd 的传输层本身就是 HTTP**（Valve 官方 SteamPipe 文档：「SteamPipe uses the HTTP protocol for content delivery … Content can be hosted by external CDN providers」）——所以 SteamKit 路线不是「另起协议」，而是把同一 CDN 的 chunk 下载做成受控并行（姊妹报告 §4.1 关键事实修正）。
- **推荐分层架构**（与 1.x provider 链式回退思想一致）：**SteamKit2 CDN 作为主 provider，steamcmd 作为兼容/兜底 provider**（处理 SteamKit 未覆盖的古老 app 或 manifest 封锁场景），二者共用同一个 item 状态机。

---

## 3. Steamworks Web API：匿名可用部分与限流

### 3.1 端点清单（官方文档实查 + 本机实测）

| 端点 | 方法 | 参数 | key | 匿名实测（2026-10-02，经香港 IDC 出口） |
|---|---|---|---|---|
| `api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/` | POST | `itemcount`, `publishedfileids[0..]` | 官方参数表**未列 key** | **HTTP 通，`response.result=1`，但每个 item `result:9` 且 title/file_url/file_size/creator/appid 全为 null**（试了 4 个不同 pubfile，含 Wiremod 104603491） |
| `api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/` | POST | `collectioncount`, `publishedfileids[0..]` | 未列 key | 同上：`result:1` 但 `collectiondetails[0].result=9`，children 为空 |
| `ISteamRemoteStorage/GetUGCFileDetails/v1` | GET | `ugcid`, `appid`, `steamid?` | **必需 ✔** | 未试（文档明示 key required） |
| `ISteamRemoteStorage/GetFileSize/v1` | — | — | — | **404：`Method 'GetFileSize' not found in interface 'ISteamRemoteStorage'`**（任务书提及，实测确认该端点已不存在） |
| `partner.steam-api.com`（发布者域） | ALL | — | **必需** | 实测无 key 直接 **403 Forbidden**（`verify your key= parameter`） |
| `IPublishedFileService/GetDetails/v1/` | GET | `key`, `publishedfileids[0..]` | 必需 | 未试（[文档](https://partner.steamgames.com/doc/webapi/ipublishedfileservice)注明 Service 接口用 `input_json`） |

### 3.2 为什么匿名拿到空对象（社区证据 + 设计对照标注）

- [FPtje/gmosh issue #20](https://github.com/FPtje/gmosh/issues/20)（2017-12）与 [gmod.facepunch.com 论坛帖](https://gmod.facepunch.com/f/gmoddev/oveg/Valve-removed-field-for-Steamworks-API-call-GetPublishedFileDetails/1/)：**Valve 从 GetPublishedFileDetails 响应中删除了 `file_url` 字段**——该端点匿名返回的元数据本来就逐步被削。
- **⚠️ 弯路嫌疑标注（按用户 2026-10-02 设计对照纪律）**：本机出口是 fake-IP 代理（香港 AS134972 IDC/小 ISP），`result:9` 亦可能是 Valve 对该出口的返回策略差异。**本次未能在另一网络条件下复验**。采信边界：作为「该端点在典型环境和本机环境下都不可作为元数据主源」的结论可靠（多环境都见始 object 空响应；即使某些环境能拿到部分字段，也拿不到 file_url）；作为「Valve 永远不返回任何字段」的绝对结论则**证据不足**。
- [Stack Overflow #56018823](https://stackoverflow.com/questions/56018823/cant-figure-out-how-to-pass-steam-web-api-a-int64)：该端点支持一次传**多个** pubfile（`itemcount` + 数组下标），可批量查询——若未来接入 key 再用此特性摊薄请求。

### 3.3 限流对策（结合 1.x 已验证基准）

1. **差异化节流**（1.x 实测基准，2.0 沿用）：`steamcommunity.com/sharedfiles/`（详情页）6s 间隔、`/workshop/browse/` 2s 间隔，按 path 前缀在节流器里选档位（见 1.x `throttle.py`）。api.steampowered.com 无实测限流数据，保守按 1-2s。
2. **批量化**：详情页一次只能查一个 item；`GetPublishedFileDetails` 支持 `itemcount=N`——若拿到 key，单请求合并 N 条可把 RPS 降一个数量级。
3. **缓存**：1.x 的 `api_cache` 模式（命中前深拷贝——可变对象直接返回会污染缓存，此为 2.0 必须保留的教训）+ `detail_cache` 双层 TTL。
4. **熔断**：连续失败触发冷却跳过（见 §7）。
5. **请求头**：这是 steamcommunity.com 429 的核心（§5）。

---

## 4. 开源同类项目精读（C# 为主）

### 4.1 Grzeho1/SteamCollectionDownloader — 最贴近 SWDM 2.0 的 C# WPF 参考

[GitHub](https://github.com/Grzeho1/SteamCollectionDownloader) · 15★ · C# · release v1.2 · 2026-07 活跃

**架构（7 个文件）**：
- `Program.cs`（14 行）— `[STAThread] static void Main` + `new Application().Run(new MainWindow())`；
- `MainWindow.xaml.cs`（569 行）— 全部业务：配置读写（`config.json` + `JsonSerializer`）、steamcmd 自动下载部署、URL→ID 解析、批量下载、进度 UI；
- `Scraper.cs`（65 行）— **HtmlAgilityPack** 抓集合页：XPath `//div[@class='collectionItem']` 取 `sharedfile_{id}` 与 `workshopItemTitle`，`//a[contains(@href,'app/')]` 取 game id；**集合为空时自动回退为单品 URL**（正则 `[?&]id=(\d+)`）——集合/单品双形态检测值得 2.0 抄；
- `SteamAuth.cs`（351 行）— §1.6 已述；
- `CredentialStore.cs`（25 行）— 密码用 **Windows DPAPI**（`CredentialStore.Encrypt/Decrypt`）存本地 config.json，「记住密码」勾选；
- `SteamGuardDialog.xaml.cs` — 自定义弹窗收码。

**可迁移要点**：① 集合/单品 URL 统一入口；② 批量单进程 steamcmd；③ **已存在即跳过**（目录递归非空判定）；④ 失败残留目录删除；⑤ 结束 sweep 磁盘校验；⑥ DPAPI 存密码；⑦ WPF Dispatcher 日志彩色 ListBox。
**SWDM 2.0 应超越它**：它没有队列持久化、没有暂停/继续、没有多 provider 回退、没有 429 防护（Scraper 用裸 `new HttpClient()` 无任何请求头处理——在 429 指纹环境下必被限）、没有取消匀速进度（进度条按 item 完成**条数**推进，非字节数）。

### 4.2 fidget77/WorkshopDL — 功能矩阵与现状

[GitHub](https://github.com/fidget77/WorkshopDL) · 46★ · **源码是 Clickteam Fusion 2.5 的 .mfa（非 C#，无源码参考价值）**，但其**多 API provider 功能矩阵**值得借鉴（README 表格）：

| 能力 | WorkshopDL | Community Workshop | Nether Workshop Downloader | SCMD Workshop Downloader 2 |
|---|---|---|---|---|
| SteamCMD | ✔ | ✔ | ✔ | ✔ |
| **SteamWebAPI** | ✔ | ❌ | ❌ | ❌ |
| Nether API | ✔ | ❌ | ✔ | ❌ |
| GGNetwork API（缓存 mod） | ✔ | ❌ | ❌ | ❌ |

说明社区已有项目把「多 provider 链式回退」当作差异化卖点——与 SWDM 1.x 已实现的 provider 架构方向一致，2.0 应保留。其 README 还给出两条用户经验：① 首次运行慢（steamcmd 自更新）；② 不在 sub 17906 的游戏改用专用服务器 AppID。

**注意**：`imwaitingnow/WorkshopDL`（搜索到的镜像）README 顶部声明 **PROJECT OUTDATED → 指向 `noitavoo/WorkshopDL`**，而 GitHub 检索**找不到 noitavoo/WorkshopDL 仓库**（疑似已删除或改名）——引用时以 fidget77 原仓库为准，勿引失效链接。

### 4.3 SteamRE/DepotDownloader — SteamKit2 路线标杆（详见 §2.2 与姊妹报告）

NuGet/winget/brew 多渠道分发；`-pubfile`/`-ugc`/`-manifest-only`/`-cellid`/`-max-downloads`/`-validate`/`-qr` 等完整参数面可作为 2.0 高级选项的抄作业对象。Issue 簿是网络弹性需求的金矿（§7.2）。

### 4.4 SyntacticFlow/SteamCmdWrapper — 文件生命周期补丁

[GitHub](https://github.com/SyntacticFlow/SteamCmdWrapper) · 4★ · 2026-09-28：下载前把目标目录备份成时间戳 zip 再删除——解决 **steamcmd 只增量覆写、不删除作者已删文件**的问题（SCA README 也指出同类问题： RimPy 覆写旧文件）。SWDM 2.0 的 mod 更新策略应内建「先备份后清除再下载」选项（1.x 冲突检测模块可与此合并）。

### 4.5 其它语种同类（架构参考）

- [Official-Husko/Husko-s-SteamWorkshop-Downloader](https://github.com/Official-Husko/Husko-s-SteamWorkshop-Downloader)（Python，84★）与 [Geam/steam_workshop_downloader](https://github.com/Geam/steam_workshop_downloader)（Python，52★）— 1.x 调研已有覆盖。
- [SegoCode/swd](https://github.com/SegoCode/swd)（Go，22★，已弃用）、[NeutronX-dev/WorkshopDownloader](https://github.com/NeutronX-dev/WorkshopDownloader)（Go+GUI，7★）— 跨语言对照。
- [NethercraftMC5608/NetherWorkshopDownloader](https://github.com/NethercraftMC5608/NetherWorkshopDownloader)（110★）— Nether API 路线（WorkshopDL 矩阵中提到），第三方镜像 API 与 SWDM 的 provider 机制同构。
- 纯 C# 的老项目 [DevonLobb/SteamWorkshopDownloader](https://github.com/DevonLobb/SteamWorkshopDownloader)（2016）已过时。

---

## 5. 协议层事实（我方研究结论，直接沿用）

以下为 1.x 研究沉淀（`docs/research/steam_429_403_research.md`，2026-09-22 实测，单 IP n=3/组），**2.0 C# 实现必须原样保留这些请求头策略**：

1. steamcommunity.com **详情页 429 由请求头指纹触发**：裸 Chrome UA 缺 `Accept-Language` **必 429**；补 **`Accept-Language: zh-CN,zh;q=0.9,en;q=0.8`** 或 **`X-Requested-With: XMLHttpRequest`** 任一即 200（各 3/3）。`Server: nginx` 无 CF-RAY（Steam 自家 nginx）。
2. **429 响应从不带 `Retry-After`**（响应体 334468 字节）——**不能**用等响应头判冷却，只能客户端自退避。
3. **Referer / Origin / 匿名 cookie 全部无效**（先 GET 首页拿 sessionid+steamCountry 也没用，各 3/3 仍 429）。
4. Steam 客户端 UA（`Steam/1.0 (+http://steampowered.com)`、`Valve/Steam HTTP Client/1.0`）均 200。

⇒ **C# HttpClient 默认头 = 裸 UA + 无 Accept-Language，正是被限的那档**。`HttpClient.DefaultRequestHeaders` 必须：
```csharp
client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...");
client.DefaultRequestHeaders.AcceptLanguage.ParseAdd("zh-CN,zh;q=0.9,en;q=0.8");
client.DefaultRequestHeaders.Add("X-Requested-With", "XMLHttpRequest");  // 双保险，1.x 实测两个都加
```

---

## 6. 网络弹性：429/403/超时的重试与熔断

### 6.1 C# 技术选型：Polly 或手写

- **Polly**（.NET 生态标准弹性库）：`Policy.Handle<HttpRequestException>().OrResult<HttpResponseMessage>(r => (int)r.StatusCode is 429 or >= 500).WaitAndRetryAsync(...)` 指数退避；`CircuitBreakerAsyncAsync(threshold, duration)` 熔断。与 HttpClientFactory + `AddPolicyHandler` 集成是官方推荐姿势。
- **本组已有手写范式**（1.x `circuit.py`，纯语义移植到 C# 即可）：
  - 连接级失败（C# 侧 `HttpRequestException`/`IOException`/`TaskCanceledException` 超时）**立即熔断**；
  - 否则**连续 3 次**失败熔断；
  - 熔断后**冷却 15 秒**跳过请求，过后自动**半开**，一次成功重置失败计数。
  - 线程安全：`CircuitBreaker` 内部 `lock`（C# 用 `object _lock` + `Interlocked` 或 `ReaderWriterLockSlim`）。
- **DepotDownloader issue 簿佐证这些故障是真实高频的**：#725「Error while copying content to a stream」、#706「ServiceUnavailable for multiple chunks, on repeat」、#691「manifest fails to download because of a connection error」、#727「TLS alert HandshakeFailure」——#715 甚至直接是 feature request「**Add exponential backoff to downloads**」。CDN 侧 ServiceUnavailable（503）是常态，退避必须覆盖 5xx。

### 6.2 429 特殊策略（因 Retry-After 永远缺失）

- 客户端自维护「429 后强制冷却」：见 429 → 熔断式冷却（比 3 次失败熔断更长，1.x 用差异化节流 + 熔断双保险）；
- **不要**重试同一个 URL 链路超过 N 次；URL 失败换 provider（1.x 链式回退：SteamWebAPI → steamcmd → Nether → GGNetwork）。

### 6.3 本机 fake-IP 代理（127.0.0.1:7897）环境注意点（实测）

1. **DNS 被 TUN/fake-IP 接管**：`steamcommunity.com` 等解析到 198.18.0.124（Meta 接口），**web_fetch 工具对非公网 IP 直接拒绝**（「resolves to a non-public IP address」）——开发调试期抓网页得用 `curl.exe -x http://127.0.0.1:7897`（本调研全程如此）。
2. **HTTP 代理变量**：C# `HttpClient` **不读系统代理设置**，须显式 `new HttpClient(new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:7897") })` 或 `SocketsHttpHandler.Proxy = ...`；否则在 fake-IP TUN 环境下直连 198.18.x.x 会失败。
3. **TLS 陷阱**：1.x 推送经验——openssl 直连在代理开启时 TLS 握手挂（`0A000126 unexpected eof`），C# 侧若自定义 HttpClientHandler 报 `HandshakeFailure`（同 DepotDownloader #727），优先尝试设 `SslProtocols = Tls12 | Tls13` 而不是关代理。
4. **fake-IP 出口是 IDC 小 ISP**（AS134972 香港），Steam 侧接口可能给出与家庭宽带不同的响应策略（§3.2 的 result:9 即标注了此嫌疑）。部署到用户机器（家庭宽带出口）时行为可能不同——**2.0 测试矩阵必须区分「本机 fake-IP 环境」与「直连家庭宽带环境」两组**。
5. steamcmd 进程**不读 .NET 的代理设置**，走系统路由表——TUN 下正常直连，无需特殊处理。

---

## 7. SWDM 2.0 架构建议（综合本报告 + 姊妹报告）

1. **下载层**：`SteamWorkshopDownloader` 抽象 + 两 provider：
   - `SteamCmdProvider`（照搬 §1：单进程批拼、正则解析、成功三元判定、失败目录清理）；
   - `SteamKitCdnProvider`（SteamKit2 3.4.0 + net8/9，`CDNClientPool` 并发，详见 [idm_download_kernel.md](./idm_download_kernel.md) §4.3）；
   - 链式回退 + 1.x 串行化锁（`_proc_lock` 教训：并发任务覆盖句柄）。
2. **元数据层**：steamcommunity.com 页面抓取为主（**带 §5 的请求头指纹对策**），Web API `GetPublishedFileDetails` 作为有 key 时的批量加速通道（当前匿名返回空）；`GetFileSize` **删除设计**。
3. **客户端友好层**：SCA 式 WPF Dispatcher 日志 + 进度按 item 推进；大文件不确定进度态（steamcmd 无字节进度）用「磁盘增长估算」兜底（1.x 已有：`_path_size` 递归求和喂进度）。
4. **安全层**：DPAPI 存账号密码（SCA `CredentialStore`）；输出日志过滤账号/密码/验证码（1.x `_redact_secrets`）。
5. **弹性层**：Polly 或手写熔断（§6），HttpClient 工厂 + 代理显式配置（§6.3）。
6. **不迁移的**：Nether/GGNetwork 第三方 API provider 矩阵保留为可选（WorkshopDL 矩阵证明是卖点，但 2.0 首版以官方链路为主，符合「精简、以用户体感为中心」原则）。

---

## 8. 检索限制与诚实的不确定性

| 结论 | 证据强度 | 不确定点 |
|---|---|---|
| steamcmd 命令/输出格式 | **强**（两个独立 C# 源码 + 1.x fixtures + 中文教程帖） | Valve wiki 被 Anubis 拦截未直读官方文档 |
| 退出码语义 | 中（源码的反例优先级推断 + 社区惯例） | Valve 未公开退出码表 |
| SteamKit2 维护状态 | **强**（GitHub API 直查时间戳） | — |
| SteamKit2 匿名 Workshop 可行 | **强**（DepotDownloader README 明文 + steamdb sub 17906） | 部分付费 app 仍需账号 |
| GetPublishedFileDetails 匿名空响应 | 中（本机实测 + 2017 file_url 删除史） | **未换网络环境复验**（fake-IP 出口嫌疑，见 §3.2） |
| GetFileSize 不存在 | **强**（本机实测 404 Method not found） | 或曾存在于旧版本 API |
| 0 字节假成功 | 中（SCA 的 sweep 校验与失败删除是**防御性证据**，未见 Valve 官方说明） | — |
| noitavoo/WorkshopDL | **强**（GitHub 检索无此仓库） | 链接失效原因未知 |

---

## 9. 参考来源汇总

**开源项目（源码级）**
- [Grzeho1/SteamCollectionDownloader](https://github.com/Grzeho1/SteamCollectionDownloader)（C# WPF；MainWindow/Scraper/SteamAuth/CredentialStore 源码已精读）
- [SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader)（README 全读；issues #713/#715/#706/#725/#691/#727 抽查）
- [SteamRE/SteamKit](https://github.com/SteamRE/SteamKit)（README + 仓库元数据 + 最近提交时间）
- [fidget77/WorkshopDL](https://github.com/fidget77/WorkshopDL)（README 全读，含 provider 矩阵；.mfa 非可参考源码）
- [SyntacticFlow/SteamCmdWrapper](https://github.com/SyntacticFlow/SteamCmdWrapper)（README）
- [imwaitingnow/WorkshopDL](https://github.com/imwaitingnow/WorkshopDL)（OUTDATED 声明，指向失效的 noitavoo/WorkshopDL）
- [WilliamVenner/WorkshopDLKiller](https://github.com/WilliamVenner/WorkshopDLKiller)、[hjorslev/SteamPS](https://github.com/hjorslev/SteamPS)、[Dahlgren/node-steamcmd](https://github.com/Dahlgren/node-steamcmd)（跨语言对照）
- [Official-Husko/Husko-s-SteamWorkshop-Downloader](https://github.com/Official-Husko/Husko-s-SteamWorkshop-Downloader)、[Geam/steam_workshop_downloader](https://github.com/Geam/steam_workshop_downloader)、[SegoCode/swd](https://github.com/SegoCode/swd)、[NeutronX-dev/WorkshopDownloader](https://github.com/NeutronX-dev/WorkshopDownloader)、[NethercraftMC5608/NetherWorkshopDownloader](https://github.com/NethercraftMC5608/NetherWorkshopDownloader)

**官方 / 文档**
- [SteamCMD - Valve Developer Community](https://developer.valvesoftware.com/wiki/SteamCMD)（仅搜索片段，Anubis 拦截未直读）
- [Steamworks Web API: ISteamRemoteStorage](https://partner.steamgames.com/doc/webapi/ISteamRemoteStorage)（端点参数表实读）
- [IPublishedFileService Interface](https://partner.steamgames.com/doc/webapi/ipublishedfileservice)
- [Web API Overview](https://partner.steamgames.com/doc/webapi_overview)
- [steamdb.info/sub/17906](https://steamdb.info/sub/17906/apps/)（匿名可用 app 清单）
- [python-valve API 文档](https://python-valve.readthedocs.io/en/latest/api.html)（GetPublishedFileDetails 参数参考）
- [steam.readthedocs.io CDN 文档](https://steam.readthedocs.io/en/latest/api/steam.client.cdn.html)（SteamKit CDNClient）

**社区经验**
- [FPtje/gmosh #20：file_url removed in newest API changes](https://github.com/FPtje/gmosh/issues/20) + [gmod.facepunch.com 原帖](https://gmod.facepunch.com/f/gmoddev/oveg/Valve-removed-field-for-Steamworks-API-call-GetPublishedFileDetails/1/)
- [Stack Overflow #56018823](https://stackoverflow.com/questions/56018823/cant-figure-out-how-to-pass-steam-web-api-a-int64)
- [用 SteamCMD 下载创意工坊内容（赛博偏方）](https://blog.nekobiglazyer.work/posts/d5bcab24.html)
- [YouTube: Downloading Steam Workshop Files - 2022 edition](https://www.youtube.com/watch?v=fxFX9uamHvI)（匿名 vs 拥有游戏的账号）
- [百度贴吧：如何用 steamcmd 下载创意工坊 mod](https://tieba.baidu.com/p/10305210502)

**本组 1.x 沉淀（协议与架构事实来源）**
- `swdm/core/steamcmd_engine.py`（_DL_RE/_SUCCESS_RE/_FAIL_RE/_LOGIN_*_RE；+force_install_dir 位置；_run 三段式收尾；_redact_secrets；stall 看门狗）
- `swdm/core/circuit.py`（熔断语义：3 次连续失败 / 连接级立即熔断 / 15s 冷却 / 半开）
- `swdm/core/throttle.py`（差异化节流基准：sharedfiles 6s、browse 2s）
- `docs/research/steam_429_403_research.md`（429 请求头指纹全量实测）
- 姊妹报告：[idm_download_kernel.md](./idm_download_kernel.md)（IDM 内核 + SteamKit CDN 并行方案）
