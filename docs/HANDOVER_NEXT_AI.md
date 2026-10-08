# SWDM 交接实验报告 v2（下一任 AI 读此文件即刻完全接手）

**生成**：2026-10-08 · **工作区**：`C:\Users\Lenovo\Desktop\程序设计\steam mod program`
**仓库**：GitHub `aqua-skies/Steam-Workshop-Download-Manager`,origin/main=0fe2624
**产品状态**：**SWDM 2.0.2 已发布**（tag v2.0.2 + release id=406791614,Setup 81.4MB+Portable 74.2MB+nupkg 74.2MB;Portable 实测 FileVersion 2.0.2.0 启动存活 Responding=True)。历史：2.0.1(release 403163902)、2.0.0(402577370 已标作废=启动崩）。**产品无已知阻塞断点。**

---

## 0. 一句话现状

2.0(C# WPF 重写）已交付发布至 **2.0.2**;e2e「选游戏→浏览→详情→下载」真实物理输入链**七通一拦**——唯一拦=DSH 沙箱测试驱动进程对 %APPDATA% 只写 ACL 拒 steamcmd 部署（**用户真机不受限**，10-04 16:24 正常权限完整 bootstrap 为证）。2.0.2 收口发布完成，项目归档。

---

## 0.5 下一任第一小时操作手册（即刻上手）

```pwsh
# 1) 验证仓库干净基线（应 ~0 wip)
cd "C:\Users\Lenovo\Desktop\程序设计\steam mod program"
git log --oneline -5          # 期望看到 62bcc90 或更新
git status --porcelain swdm2 | Measure-Object   # wip 计数

# 2) 干净构建（0 错 0 警为铁律基线）
cd swdm2
dotnet clean Swdm2.sln -v q
dotnet build Swdm2.sln -warnaserror   # 期望 Build succeeded,0 Warning(s)

# 3) 跑四域逻辑测试（控制台驱动=SP-3 模式，沙箱内 xUnit testhost 会崩）
dotnet run --project tests/CoreTestsDriver      # 全绿应为 72/0 量级
dotnet run --project tests/SteamTestsDriver     # 174/0 量级（Online 类夜间熔断=白天补跑)
dotnet run --project tests/DownloadsTestsDriver # 84/0 量级
dotnet run --project tests/UiTestsDriver        # UI 逻辑域

# 4) 桌面启动存活（发布门强制项，v2.0.0 教训：测试绿但桌面崩）
#    发布到 C:\tmp 再跑（ASCII 路径!CJK 静默装必失败）
# 5) 推送（唯一可靠组合；夜网失败改直连 schannel)
git -c http.sslBackend=schannel -c http.proxy=http://127.0.0.1:7897 push origin main
```

**先读**:本文件 → `swdm2/docs/process/e2e_2.0.1.md`（七通一拦证据）→ `swdm2/docs/architecture_2.0.md` §6(DAG)。
**不要做**:自己写产品代码修 bug（captain 只协调，派给域 owner);重启 12h 定时关机规则（用户已删）;夜间跑 FlaUI/UIA 全量（无交互桌面会挂死）;输出用 pwsh 管道（用 cmd /c 直重定向）。
**超时纪律**：所有阻塞等待/`job_output`/后台任务超时**不超过 2 分钟**（240000ms 上限，默认更短）；超时即查进度文件再决定，不干等。

---

## 1. 目录结构

- 1.x(Python/PySide6,1.4.2,demo 提交用）:`legacy/`(361 文件，README=legacy/README.1.x.md）
- 2.0(C# WPF):`swdm2/`
  - `docs/`:architecture_2.0.md(636 行）/visual_system_2.0.md(371)/test_system_2.0.md(738)/packaging_2.0.md/calibration_1-2.md/connectivity_probe_2.2.md/design_baseline_2.0.md
  - `docs/process/`:实测报告链（e2e_2.0.1.md、button_sweep_2.0.md、sphere_framing.md、instruction_check.md、review_2.0_0.3.0→2.0.1.md 发布门五篇、plan_stage3_0.3.0.md、contrast_real.md)
  - `src/`:Swdm2.App(WPF)+Swdm2.Core+Swdm2.Steam+Swdm2.Downloads
  - `tests/`:Swdm2.Core.Tests/Swdm2.Steam.Tests/Swdm2.Downloads.Tests/Swdm2.UiTests + 四个控制台驱动（CoreTestsDriver/SteamTestsDriver/DownloadsTestsDriver/UiTestsDriver)
  - `spike/`:D0.2 基座实证（SpikeWpf+SpikeFlaUiTests)
- 根：README.md(1.4.2 演示口径）、LICENSE、demo/(1.4.2 材料+4 截图）、`docs/research2/`（PCL2 研究）、`research/`（1.x 期 Steam 实测）

---

## 2. 团队（AgentTeams team "swdm2")

captain 只协调+记录+评审，不写产品代码（用户 2026-10-02 23:15 二次重申，"速度和质量都上不来"）。
- **arch-20**[架构/Steam/下载内核/ModDetail]:Swdm2.Steam 全、Swdm2.Downloads 全、App/ViewModels 逻辑。idle，名下空，待派。
- **visual-20**[UI/视觉]:App/Ui(Themes/Controls/Pages/HomeSphere)、Views、动画件、布局。idle。
- **qa-20**[真实输入测试/发布门]:tests/UiTests+E2E+四驱动、发布门执行、两轮回归。idle(t69/t70 终态）。
- t1-t71 全记录在 AgentTeams 任务板。**t66(failed) 曾卡 team loop,裁定=t69 全量取代，已附 evidence 终态**;若再卡，用 `agent_teams_update_task` 追加证据整理。
- **bug 归属制**：bug 交回开发该域的成员修（不设泛修复专员；Team Topologies stream-aligned）。

---

## 3. 构建/发布事实

- .NET 8 SDK 8.0.425；`dotnet build Swdm2.sln -warnaserror` 必 0-0。
- **SP-3 驱动模式**：沙箱 xUnit testhost 崩→四个控制台驱动反射执行同一批 [WpfFact];输出 `cmd /c ... > out.txt 2>&1` 直重定向（pwsh 的 Out-String/Start-Job/Start-Process 管道在本沙箱会挂、吞输出）。
- **发布门**=clean+warnaserror 0-0 + 全量回归两轮绿 + **桌面启动存活**(v2.0.0 曾经测试门全绿但桌面启动即崩，此后强制）；讨论组三原则评审（精简/用户体感/基本功能）。
- Velopack 打包脚本见 `swdm2/docs/packaging_2.0.md`;CJK 路径静默安装必失败→**只走 ASCII 路径装测**；装后 `%LOCALAPPDATA%\Swdm2\current`。
- 版本三同步=csproj+CHANGELOG.md+git tag;release 资产上传=PAT 从 `git credential fill`(x-access-token)+Invoke-RestMethod(uploads.github.com)。
- 推送：代理通时 `git -c http.sslBackend=schannel -c http.proxy=http://127.0.0.1:7897 push origin main`;夜网代理挂=直连 schannel 成；tag 推送 `git tag v2.0.2 <sha>` + `push origin main v2.0.2`。

**GitHub release 资产上传（体系化方法，实测 2026-10-08 版）**：
1. **PAT 提取**（关键坑：本机工具链里 `` `n `` 是字面量不是换行！）：
```pwsh
$nl=[char]10
$s="protocol=https$($nl)host=github.com$($nl)username=x-access-token$($nl)"
[System.IO.File]::WriteAllText("$PWD\swdm2\.dtmp\cred_in.txt",$s)   # 必须真实换行
cmd /c "git credential fill < swdm2\.dtmp\cred_in.txt > swdm2\.dtmp\cred_out.txt 2>&1"
# 从 cred_out.txt 取 password= 行（开头必须是 protocol=/host=，不是 URL,否则 invalid credential line)
```
2. **建 release**：`Invoke-RestMethod -Method Post -Headers @{Authorization="Bearer $token";Accept="application/vnd.github+json";"X-GitHub-Api-Version"="2022-11-28"} -Body (ConvertTo-Json @{tag_name;name;body;draft=$false;prerelease=$false}) -ContentType application/json`。
3. **传资产**：`https://uploads.github.com/repos/<owner>/<repo>/releases/<id>/assets?name=<file>&label=<label>`，Body=`[System.IO.File]::ReadAllBytes(...)`，ContentType=application/octet-stream（每个 74MB 资产约 1-2min)。
4. 三资产=Setup.exe+Portable.zip+<ver>-full.nupkg（同 Velopack `--outputDir artifacts` 产物）。

---

## 4. 用户硬约束（用户级规则，必须遵守）

1. **按键与设计有效性（2026-10-04）**：每个按键/设计元素在每个页面都必须真实有效且经**真实鼠标/键盘**测试；非必要不添加按键；死按键禁止交付。
2. **计划先行（10-02)**：编码前详实计划（架构契约/任务拆分/验收/验证）经 captain 认可；研究骨架不算开发。
3. **经验复验（10-02)**：参数类经验（退避/节流/并发）移植必实测重标定；先问"能否更短/更小"。
4. **设计对照（10-02)**：结论与原方案逐条对照；网络失败不得误读"不可行"=弯路嫌疑+换源复验。
5. **迭代四要素（09-28)**：全量回归（含关联交互）+讨论组三原则评审+版本号同步+bug 员连续两轮复测无异常，缺一不可。
6. **产品优先级（10-02)**：用户体验优先于安装包体积；瘦身只动冗余产物。
7. **主动竞品调研**：定期 GitHub 搜同类（下载器/mod 管理器/SteamCMD GUI)。
8. **域 owner 稳定**，换帅仅限长期不可用/域被吞并/连续两轮质量不达标。
9. **关机令**："弄完自动关机"=全部完成+四要素齐+复检后 `shutdown /s /t 60`(`shutdown /a` 可取消）;12h 定时关机规则已按用户令删除，勿重建。

---

## 5. 里程碑证据链（commit 链）

| 交付 | commit | 要点 |
|---|---|---|
| 2.0.0 发布 | a77cb02 | release 402577370,**启动崩已作废**（勿让用户下到） |
| 崩根修复 | bdaa9c8 | SettingsPage 只读 UpdateDownloadProgress 用了 TwoWay→APPCRASH;改 OneWay |
| 视觉整改×2 | 36ff177 / 9df149e | Light 薄荷清晨+中文导航；死钮修=PageNavigationService 三处 InvalidateRequerySuggested+ViewModelBase |
| ModDetail 真实化 t63 | fea4062 | TryLoad(PublishedFileId)+示例横幅+实物下载钮 |
| 设置绑定游戏 t64 | 9ed69db | DefaultGameService 即时响应 |
| instruction 收口 t65 | bf7c707 | 相接线+球深度衰减+真实 CDN 图标 |
| 浏览重做 t67 | a93f5c5 | 名字优先+示例横幅+顶栏快切游戏+217 元素全按钮扫描+StartGame 死钮→steam://run/{appid} |
| 真源真实落盘 t68 | 4989904 | CommunityWorkshopBrowseSource(30 真实 L4D2)+GMod 17906 匿名 steamcmd 落盘 |
| 2.0.1 发布 t69 | 4f074be+5c20727 | 三同步+三资产+v2.0.0 作废+review_2.0_2.0.1.md |
| e2e 修复 | 84ea955 / 62bcc90 | visual:IME 禁用+下载钮入区；arch:router 逃逸异常→显式 Failed;ModDetail API401→社区 HTML 回退 |
| **e2e 终局** | b4fe1cc | **七通一拦**：启动球体/打 gmod 选中 Garry's Mod/真源 30 条目 2.4s/详情真名 xdReanimsBase(L4D2) Anim Mods base/物理鼠标 5.6s 入队 autoNav/回归全绿 |
| 球体取景 t71 | 88752bf | 相机 pos(3.46,-2.66,5.32)+look(-2.81,3.11,-5.52),球心右下 0.618W/0.58H 半径 152 完整入画 |
| PCL2 研究 | docs/research2 | pcl2_pages.md(1115 行）+pcl2_modules_controls.md(363)+pcl2_xaml_patterns.md(748) |

**回归基线**：Core 72/0 + Downloads 84/0 + Steam 174/0 + Ui 四域全绿。

---

## 6. Steam Community 机制实测数据（全部复现验证）

- **429 唯一开关=缺 Accept-Language**(10/10 复现；与 UA/速率无关，8s 慢速仍 429)。判定=「浏览器形态 UA 却缺 AL」自动化指纹。**X-Requested-With 单独不再豁免（推翻旧结论）**。
- 429 响应从不带 Retry-After;冷却 >24s(8s 间隔连 3 发全 429)→代码 20s 基准退避偏短。
- **IPublishedFileService/GetDetails 匿名=401**(curl 实测死路，必 key)→详情主源改社区 HTML(EnrichDetailAsync 整体回退+字段来源诚实标注+双失败合计 ErrorMessage)。
- **403 本机无法复现**:HEAD→404/伪ID→200/Host篡改→400/HTTP1.0→200/明文 80→200。分层：429=请求头层（可控）,403=IP/边缘层（不可控，疑似共享代理出口被边缘封锁，推断未确证）。
- 门控边界：仅 `/sharedfiles/filedetails/` 受指纹门控；`/workshop/browse/` 与根路径不受影响。403 判别：无 `Server: nginx` 或非 ~340KB SSR 体=代理中间层非 Steam。
- **游戏搜索**：`GET https://store.steampowered.com/api/storesearch/?term=xxx&l=schinese&cc=CN` 匿名可用（gmod→4000 Garry's Mod / csgo→730 / l4d2→550)。速率=**连接熔断**（12 连发 2-3 成功，WinSock 10053,静置 15s 恢复，非 HTTP 429)→防抖 350ms+最小 2 字+缓存 300s+在途取消；图片 CDN 优先 shared.akamai(282ms,cloudflare 首 9.4s);中文名不可靠仅商店中文名有效；count 参数被忽略须客户端截断+过滤 type=="app"。
- 本机环境：steamcommunity.com 走 fake-IP 代理（DNS→198.18.0.124 Meta 接口），出口 43.243.192.92（香港 AS134972 IDC/小 ISP)。
- 竞品口径：Rust steam-user 全局限流 Quota::per_minute(30) 为公认安全值；官方 API 限额 100,000/天；货架 store API 限流更狠（storesearch 属此列）。

---

## 7. 下载内核（对标 IDM)

- `DownloadProviderRouter`:主 SteamKitCdn→回退 SteamCmd;**主/回退 try/catch 逃逸异常→显式 Failed 消息+EnsureAsync IO 异常同报**（根因=逃逸异常被 scheduler 静默吞 10min 卡死；环境触媒=沙箱 ACL)。
- SteamKit 链：Steam/Cdn/(SteamKitSessionManager+SteamKitCdnClient manifest+并行分块 SHA)。
- SteamCmd 链：SteamCmdDeployer(bootstrap→%APPDATA%\SWDM\steamcmd)+SteamCmdRunner(workshop_download 匿名）。
- 队列：IDownloadQueue+DownloadScheduler(AppHost 装配），DownloadStateMachine(Pending/Queued/Downloading/Paused/Failed/Completed)。
- 多段：SegmentPlanner+HttpSegmentDownloader+ResumeStore（断点续传）；Disk 三件套稀疏预分配/偏移写/卷探测；TokenBucketSpeedLimiter 限速；DownloadEventBus 进度聚合。
- **有意双目录设计（非分叉)**:PathService `AppFolderName="SWDM"`=全库唯一目录常量；数据根 %APPDATA%\SWDM(steamcmd+workshop content+配置+日志共用同一 paths 实例）；%LOCALAPPDATA%\Swdm2\current=Velopack exe 目录。用户机落盘=%APPDATA%\SWDM\steamcmd\steamapps\workshop\content\<appid>\<pubfile>。

---

## 8. 环境层陷阱（踩过的坑，避雷）

1. **沙箱前台锁**吞合成物理点击（曾误判死钮）；InvokePattern=沙箱内验证口径，**真实用户点击才是最终证据**。
2. 夜间无交互桌面→UIA 树遍历无限阻塞；FlaUI/UIA 全量只能白天交互桌面跑。
3. 沙箱驱动进程对 %APPDATA%/C:\tmp 只写 ACL(UnauthorizedAccess 实测）→steamcmd 部署在沙箱必失败（用户机不受限）。分层证据法判定：文件系统时间戳+bootstrap_log 无新条目=部署从未启动。
4. 读图工具全不可用（read_image sharp ERR_DLOPEN_FAILED;modlens Gemini key invalid)→视觉 bug 用几何量化兜底（mapTo 相对坐标+显式断言）。
5. 控制台 GBK 乱码≠文件损坏；Select-Object -First 截管道杀上游 dotnet;Add-Type 编译坑（WindowsBase 显式引用/namespace 旧语法/变量插值括号）。
6. **captain 会话 >460k token→工具自动审查（duanyan 复审）拒绝一切调用**（报 sensitive content/CONTEXT_WINDOW_EXCEEDED)=环境层，**开新会话即恢复**。上一轮即因此中断多时；本报告为续接所留。
7. e2e 测试假绿事件（报 PASS 但下载未完成）已治理：timeout→failure、demo 标题→failure、落盘按 PathService ApplicationData+"SWDM"（不是 LocalApplicationData+"Swdm2")。
8. 异步富化坑：STEP4 详情真名 2-4s 才到，轮询 ≤10s 等非 demo 标题，勿一次读快照误判。

---

## 9. 2.0.2 发布记录（已归档）

2026-10-08 完成：版本三同步（0fe2624)+两轮全量回归绿（Core 72/0+Downloads 84/0+Steam 174/0+Ui 逻辑层全绿）+讨论组三原则 3/3 PASS(arch/visual/qa)+Velopack 打包三资产+Portable 实测安装（ASCII 路径 C:\swdmpack)=FileVersion 2.0.2.0+启动存活 Responding=True+GitHub release v2.0.2(id 406791614) 三资产上传+tag 推送。
- Setup.exe 在本沙箱静默装遇 os error 5（Velopack "Determining install directory" 环境门；2.0.1 夜间曾成功=沙箱 ACL 漂移）→Portable 路径实测兜底，CHANGELOG 已诚实标注。
- 环境门红线（2.0.2 归档证据）:ZZChrome/ZZNavigation/Feature 三族=UiTestsDriver 进程内 XamlParseException(TitleButtonHover 解析）=A/B 实证预存（stash 版本号改动前后同失败），产品实机正常。

**项目状态：归档。** 无遗留必需工作。如未来续做：用户实机复核下载主链一次（arch-20 附注，非阻塞）+ZZChrome/ZZNavigation/Feature 驱动环境门 someday 排查（可选）。

---

# 第二部分：工程地图（源码/模块/测试/人员）

路径相对 `swdm2/`。依赖链单向 Core←Steam←Downloads←App(Downloads→Steam 一补线）。解决方案 `swdm2/Swdm2.sln`。

## A. 模块总表（src/)

### A1. Swdm2.Core — 基础设施与领域原语（无 WPF 依赖）
- `Domain/`:强类型 ID 与值对象 AppId/PublishedFileId/UgcId/DownloadTaskId/DownloadTask/GameInfo/WorkshopItem/CollectionDetails/ModLibraryEntry（不可变）
- `Results/`:Result<T>/DownloadError/SteamError 显式错误传播（**不许吞异常=铁律**，源自 router 静默吞 bug)
- `Paths/`:IPathService/PathService/PathMode;**AppFolderName="SWDM"=全库唯一目录常量**；数据根 %APPDATA%\SWDM,exe 目录 %LOCALAPPDATA%\Swdm2\current
- `Options/`:DownloadOptions/SteamOptions/PathOptions/ProxyMode
- `Caching/`:AsyncCache/IAsyncCache（联想缓存 300s)
- `Credentials/`:DpapiCredentialStore/ICredentialStore(DPAPI 用户级凭据）
- `Logging/`:IRedactionPolicy/RegexRedactionPolicy（日志脱敏）

### A2. Swdm2.Steam — Steam 一切通信（arch-20 域）
- `Web/`:SteamHttpClientFactory(**Accept-Language 指纹防护**+shared.akamai 优选）、SteamHttpHeaders、SteamWebApiClient(IPublishedFileService 匿名 401 死路）、StoreSearchClient（游戏搜索真源）
- `Workshop/`:**CommunityWorkshopBrowseSource(社区 HTML 真源=30 真实 L4D2 条目，绕开 401)**、StoreSearchWorkshopBrowseSource（降级）、IWorkshopBrowseSource/WorkshopBrowseEntry/WorkshopBrowseQuery/WorkshopUpdateChecker/ModUpdateCandidate/InstalledModSnapshot
- `Community/`:CommunityHtmlParser/CommunityPageSource/ICommunitySource（详情富化回退 EnrichDetailAsync 同一解析）
- `SteamCmd/`:SteamCmdDeployer(bootstrap)+SteamCmdRunner(workshop_download 匿名）+两接口
- `Cdn/`:SteamKitSessionManager、SteamKitCdnClient(manifest+并行分块 SHA)、ManifestModels
- `Connectivity/`:EndpointProbe+contracts（连通性状态机）
- `Resilience/`:Throttler（连接熔断自适应档；重标定见 calibration_1/2.md)

### A3. Swdm2.Downloads — 下载内核对标 IDM(arch-20 域）
- `Providers/`:IDownloadProvider+**DownloadProviderRouter（主 SteamKitCdn→回退 SteamCmd;逃逸异常→显式 Failed)**+SteamKitCdnProvider/SteamCmdProvider/HttpDirectProvider/DownloadProviderException
- `Queue/`:DownloadQueue/DownloadScheduler/DownloadStateMachine/IDownloadQueue
- `Segments/`:SegmentPlanner/HttpSegmentDownloader/ResumeStore（断点续传）/SegmentModels
- `Disk/`:SparseFileAllocator（稀疏预分配）/OffsetFileWriter（并发偏移写）/VolumeCapabilityProbe
- `Limiter/`:TokenBucketSpeedLimiter
- `Events/`:DownloadEventBus/IDownloadEventBus/ProgressSnapshot/ProgressTracker

### A4. Swdm2.App — WPF 前端（visual-20 主导 UI,arch-20 写 VM 逻辑）
- `Boot/AppHost.cs`:DI 装配根（同一 PathService 实例贯穿 SteamCmdDeployer)
- `Chrome/`+`Ui/Chrome/`:自绘标题栏 CustomChromeFallback+TitleButtonHover
- `Navigation/`:PageNavigationService(**三处 InvalidateRequerySuggested=死钮修复点**)+PageTransitionOrchestrator(PCL2 式过场 130ms 交换+30ms 进入）
- `Ui/Themes/`:Light.xaml（薄荷清晨）/Dark/Accent/Common+ThemeService(DynamicResource 全局换；NoHardcodedColorTests 守护）
- `Ui/Controls/`:SwdmCard/ModListItem/Hint/SmartScreenHintCard+SmoothScrollViewer/SmoothScrollAttach+动画件 AniHelper/AnimationFrameSampler/DrawerSlide/Overshoot（回弹物理）/StaggeredEntrance（错落进入）
- `Ui/Controls/HomeSphere/`:HomeSphereControl(xaml+cs)+IcosahedronGeometry（三角网格）+SphereGameTile（贴面游戏图标）+SpherePhysics（节点直径振荡+距离平方耦合；鼠标光源+拖拽加速旋转）；**相机=88752bf:pos(3.46,-2.66,5.32)+look(-2.81,3.11,-5.52)**
- `Ui/Pages/`:SphereHomePage（球体主页）、WorkshopBrowsePage、Download/DownloadPage、Settings/SettingsPage、PageBase
- `Views/`:GameSelectPage、ModDetailPage(**粘性底部下载栏=84ea955**）、DownloadsPage、LibraryPage、DownloadCompleteDialog、SteamGuardDialog、ProxyConfigDialog
- `ViewModels/`:MainShellViewModel（导航+真源接线，SampleData 两处已删）、WorkshopBrowsePageViewModel+WorkshopBrowseItem、ModDetailPageViewModel(**TryLoadAsync 真实化+EnrichDetailAsync 社区回退**）、DownloadsPageViewModel+DownloadTaskRowViewModel、GameSelectPageViewModel、SettingsPageViewModel、LibraryPageViewModel、SphereHomePageViewModel、ConnectivityBarViewModel、RelayCommand/ViewModelBase、GameAliasTable
- 其它：Community/（评论）、Configuration/、Connectivity/ConnectivityStateService、Games/DefaultGameService、Library/LocalLibraryScanner、Logging/SwdmLogging+RedactingTextFormatter、Session/WpfSteamGuardPrompter、Updates/(VelopackUpdateManager/UpdateService/NullUpdateManager)

## B. 测试总表（tests/)

**SP-3 运行纪律**：沙箱 xUnit testhost 崩→四控制台驱动反射执行同一批 [WpfFact](Core/Steam/Downloads/UiTestsDriver 各 Program.cs);输出 cmd /c 直重定向文件；Online 类夜间连接熔断=白天补跑条款；FlaUI/UIA 全量只能白天交互桌面。

**B1. Swdm2.Core.Tests（逻辑无 UI)**:Caching/AsyncCacheTests、Credentials/DpapiCredentialStoreTests、Domain/StrongIdsTests+ImmutabilityTests、Logging/RegexRedactionPolicyTests、Options/OptionsBindingTests、Paths/PathServiceTests（**双目录常量守护**）、Results/ResultTests

**B2. Swdm2.Downloads.Tests（下载内核）**:Disk/SparseAllocatorTests、Events/EventBusTests、Limiter/SpeedLimiterTests、**Providers/DownloadProviderRouterTests(84 测，逃逸异常→Failed 可见守护）**、Providers/RouterFallbackOnlineIntegrationTests、Providers/SteamCmdProviderTests、Queue/DownloadStateMachineTests、Segments/HttpSegmentKestrelTests(Kestrel 内服务器测分段）

**B3. Swdm2.Steam.Tests**:Cdn/(SteamKitCdnClientTests/ChunkTests/OnlineTests+SteamSessionManagerTests/OnlineTests)、SteamCmd/(DeployerTests+**DeployerOnlineTests bootstrap+真实落盘口径**、RunnerTests/RunnerOnlineTests)、Web/(HttpClientFactoryTests、SteamWebApiClientTests/OnlineTests 401 实证、StoreSearchClientTests)、Workshop/(CommunityBrowseSourceTests 30 条目解析、**RealModDownloadLandingOnlineTests GMod 17906 匿名落盘 size>0**、StoreSearchWorkshopBrowseSourceTests、WorkshopUpdateCheckerTests)、Community/(CommunitySourceTests+CountingStub)、Connectivity/(EndpointProbeTests+ConnectivityStateTests)、Resilience/ResilienceTests

**B4. Swdm2.UiTests(UI/WPF,[WpfFact]+FlaUI)**
- Calibration/:B3ConcurrencyCalibration、MetadataApiConcurrencyCalibration（参数重标定）
- Smoke/:AppLaunchSmoke（启动存活）、P0MainJourneySmoke、GameSelectJourneySmoke、DownloadJourneySmoke、DownloadMainJourneyP0、UiTestHelpers（公共工具）
- Browse/:WorkshopBrowsePageViewModelTests、WorkshopBrowseItemActionsTests(+Desktop)、BrowseItemActionsDesktopTests、WorkshopBrowseD9Tests、BrowseRealSourceJourneyTests（真源旅程）、WorkshopBrowseRealSourceVMTests（失败链 4 测）、WorkshopBrowsePageVirtualizationTests
- ModDetail/:ModDetailPageViewModelTests、ModDetailTryLoadTests(t63)、**ModDetailStickyDownloadButtonTests（下载钮入区守护）**
- Settings/:SettingsPageViewModelTests、Games/DefaultGameTests(t64)
- HomeSphere/:SphereHomeTests、SphereCameraFramingTests（取景常量 4 断言）、SphereFrameSamplingTests
- **E2E/E2EJourneyRealInputTests.cs**:七通一拦终局测试；物理 RealClick/Keyboard+截图+UIA 副证；假绿治理=timeout→failure、demo 标题→failure、落盘按 PathService ApplicationData+"SWDM"
- Sweep/ButtonSweepDesktopTests(217 元素→button_sweep_2.0.md,8 页）
- Themes/:NoHardcodedColorTests、ThemeResourceDictionaryTests、ThemeServiceTests
- Controls/:ControlLayerStructureTests（双层 PanBack/PanFore 守护）、WpfUiApiReflectionTests
- Transition/TransitionWiringTests、Animation/AnimationKitTests、DeadButton/GoBackDeadButtonTests、Downloads/DownloadsPageIdmViewModelTests、Feature/(DownloadRowExperience/StatusBarConnectivity/SteamGuardDialog)、Library/(LibraryPageViewModel+LibraryUpdate)、GameSelect/GameSelectPageViewModelTests、Updates/(UpdateService+VelopackFeed)、ZZChrome/ChromeCompositionTests、ZZNavigation/PageNavigationTests（死钮修复回归）、Connectivity/ConnectivityStateServiceTests、Logging/RedactingTextFormatterTests

**B5. 驱动**：CoreTestsDriver/SteamTestsDriver/DownloadsTestsDriver/UiTestsDriver（各自 Program.cs,反射执行对应测试集，SP-3 沙箱唯一可跑口径）

**B6. 文档（docs/,实测报告不可删）**:规格三件套（architecture_2.0.md 含 DAG v2.3 65 任务/7 阶段、visual_system_2.0.md、test_system_2.0.md FlaUI 5.0.0 实证）、design_baseline_2.0.md、calibration_1/2.md、connectivity_probe_2.2.md、packaging_2.0.md、process/ 全实测链。

## C. 人员分配表

| 成员 | 域 | 范围 | 状态 |
|---|---|---|---|
| arch-20 | 架构/Steam/下载内核/ModDetail | Swdm2.Steam 全、Swdm2.Downloads 全、App/ViewModels 逻辑 | idle，名下空，待派 |
| visual-20 | UI/视觉 | App/Ui(Themes/Controls/Pages/HomeSphere)、Views、动画件、布局 | idle |
| qa-20 | 真实输入测试/发布门 | tests/UiTests+E2E+四驱动、发布门、两轮回归 | idle(t69/t70 终态） |
| captain | 统筹/记录/评审 | 不写产品代码 | 本报告作者 |

近期交付对应：arch-20(4989904/62bcc90/t63-t64-t68-t69)、visual-20(36ff177/9df149e/bf7c707/88752bf/84ea955)、qa-20(b60178f/0a284be/2535363/b4fe1cc+发布门执行）。

## D. PCL2 对标研究可迁移要点（docs/research2/)

- 页面切换=MyPageLeft 逐个错落+MyPageRight 10 态状态机+FormMain.PageChangeAnim(110ms 两段式+AniControlEnabled 闸门）；无独立 Transition 组件。
- 动画引擎完全自研帧驱动（非 Storyboard):增量应用、同名组打断重开、结束回落 SetResourceReference；带初速度缓动公式 (alpha+1)*p/(1+alpha*p)。
- 自绘控件=PanBack 命中层/PanFore 视觉层双层；列表放弃 ItemsControl 虚拟化改 StackPanel 手工列表（悬停/勾选/滑动多选/右键全控+SharedSizeGroup 跨项对齐），性能靠懒创建子控件+InitLate 懒绑+不可见跳过。
- 搜索双档防抖（350ms/75-50ms)+Interlocked 取消令牌；滑动多选 SwipeSelect;MyCard 三档高度动画策略。

## E. 索引

- 本文件：`docs/HANDOVER_NEXT_AI.md`（第一部分状态总览+第二部分工程地图）
- `swdm2/docs/process/e2e_2.0.1.md`（七通一拦+退货归属+6 张截图清单）
- `swdm2/docs/process/button_sweep_2.0.md`(8 页 217 元素全表）
- `swdm2/docs/process/sphere_framing.md`（球体取景参数+像素证据）
- `swdm2/docs/review_2.0_2.0.1.md` + review_2.0_2.0.0.md（发布门）
- `swdm2/docs/architecture_2.0.md` / `visual_system_2.0.md` / `test_system_2.0.md`
- PCL2:`docs/research2/pcl2_pages.md` + `pcl2_modules_controls.md` + `pcl2_xaml_patterns.md`
- Steam 实测：`research/steam_429_403_research.md` + `steam_429_download_research.md` + `steam_game_search.md`（部分在 legacy/research/)
- 白板账本：`.dsh-memory/workspaces/--C--Users-Lenovo-Desktop-程序设计-steam-mod-program--/handoff/PLAN.md` + handoff/*.md
