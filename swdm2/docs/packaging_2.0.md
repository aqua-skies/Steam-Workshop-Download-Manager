# SWDM 2.0 打包规格（D6.1 · t58 · Velopack)

> 对标 1.x 交付链（PyInstaller 48.3MB）；2.0 = Velopack（vpk pack) + .NET 8。
> 版本同源：`swdm2/Directory.Build.props`（C4 版本号双端同步纪律——程序 Assembly + Velopack 包 + Release 三处同源）。

## 1. 分发形态裁决：SelfContained（自包含）

| 项 | SelfContained | FrameworkDependent | 裁决 |
|---|---|---|---|
| 用户机前置 | 无（装完即用） | 需 .NET 8 Desktop Runtime x64 | **SelfContained** |
| 体积 | ~150-170MB | ~10-20MB | 体积劣势明确接受 |
| 风险 | 无运行时缺失投诉 | WPF 桌面运行时缺失=黑屏崩（1.x PySide6 同理由自带运行时） | FD 用户教育成本高 |

**依据（用户 2026-10-02 产品优先级原则）**：用户体验优先于安装包体积——1.x 安装包 48.3MB 已含完整 Python 运行时且零运行时投诉；不为压缩体积牺牲"装完即用"。**不裁剪**（`PublishTrimmed=false`):WPF 反射 + SteamKit2 + XAML 资源裁剪兼容风险 > 体积收益（1.x 同样未裁）。

## 2. vpk 工具链记录（本机实证，t58)

- `dotnet tool install -g velopack` **本机阻断**（SDK 8.0.425）：NuGet 下载成功（83ms)但 `ToolPackageInstance` 枚举 `.store\velopack\1.2.161\velopack\1.2.161\tools` 抛 `DirectoryNotFoundException`，自/自定义路径均复现 → **SDK 工具安装器路径枚举 bug**，非网络问题（设计对照纪律：网络可达已证，不误读为不可行）。
- **正解**：`velopack` nuget id = 运行时库；vpk **工具** id = `vpk`。直接下 nupkg 解包使用：
  `https://api.nuget.org/v3-flatcontainer/vpk/1.2.161/vpk.1.2.161.nupkg` → `tools/net8.0/any/vpk.dll` → `dotnet vpk.dll pack ...`
  （版本与架构契约 `Velopack 1.2.161` 一致；库 vpk pack `--exclude .*\.pdb` 默认开）
- 代理：`HTTPS_PROXY=http://127.0.0.1:7897`(NuGet 直连 TLS 挂同 0.x 记忆）。

## 3. 打包命令（scripts/pack-velopack.ps1)

```powershell
.\swdm2\scripts\pack-velopack.ps1 -Version 0.6.0            # 当前版本
.\swdm2\scripts\pack-velopack.ps1 -Version 0.5.0 -Baseline  # 基线（升级路径用）
```

- 发布：`dotnet publish -c Release -r win-x64 --self-contained true -p:PublishTrimmed=false -p:Version=$V`
- 打包：`vpk pack --packId Swdm2 --packVersion $V --packDir <publish> --mainExe Swdm2.App.exe --channel win --outputDir artifacts/`
- 产物落 `artifacts/<channel>/`:Setup.exe（安装器）+ 全量包（.nupkg/.zip)+ 增量 delta（BestSpeed 默认，仅同 packDir 有前版时生成）。
- **不签名**：无代码签名证书 → SmartScreen 首次拦截告知（架构 D6.3 内置提示卡留"取得证书即移除"活口；决策 10 同构）。

## 4. 安装与升级路径验证

- **首次安装**：`Setup.exe /S`（静默）→ `%LOCALAPPDATA%\Swdm2\` 落盘 + StartMenu 快捷方式；验证 installed version 文件。
- **升级**：先装 0.5.0 基线（channel=win-baseline 独立产物），再跑 0.6.0 `Setup.exe /S` → Velopack 安装器同 packId 识别既有安装=原地升级（版本号翻转 + 旧版 hook 清理）。
- **自动更新（UpdateManager)**：D6.3 范围（VelopackApp.Build().Run() 钩子 + releases feed + SmartScreen 提示卡），本任务仅验安装器级路径。
- **沙箱限制诚实标注（ENV-DOWNGRADE)**：沙箱无双桌面会话时，安装/启动以进程级与文件级断言替代桌面可视实测（WPF 无消息泵同 FlaUI 输入族基线），实测条款写交付回执。

## 5. 运行时依赖保留清单（产品优先级原则）

- steamcmd 可执行（兜底 provider 链 D4.4)：运行时按需下载落盘，不进包（包内只放引导）；**体积不受裁剪约束**（决策 10)。
- WPF-UI 4.3.0 / SteamKit2 3.4.0 / Serilog / MSDI:全部随 self-contained 发布保留。
- appsettings.json 随 `CopyToOutputDirectory=PreserveNewest` 入包。

## 6. t58 实测记录（2026-10-03,沙箱）

**已验证**：
- 打包全链：publish(175.2MB,272 files) → vpk pack → artifacts:`Swdm2-win-Setup.exe`(81.4MB)+full.nupkg(74.2MB)+Portable.zip(74.2MB)+RELEASES/releases.win.json(SHA256 索引）。
- **首次安装实测**:`Setup.exe /S`（须从**纯 ASCII 路径**执行）→ 落 `%LOCALAPPDATA%\Swdm2`(current/+packages/+Update.exe+`SWDM 2.0...exe`)+开始菜单快捷方式 `SWDM 2.0 - Steam Workshop Download Manager.lnk`;app 程序集版本=发布版本号。
- **同通道两版打包**：0.5.0→0.6.0 同 channel(win) 顺序打包，releases 索引双版本 SHA256 齐备（升级源就绪）。

**沙箱限制（ENV-DOWNGRADE 诚实标注）**：
- **CJK 路径触发 os error 5**:Setup.exe 放含 CJK（`程序设计`）路径下执行=安装目录判定阶段 `PermissionDenied` 重试至失败；复制到 ASCII 路径（`C:\swdm58\Setup.exe`)即过。**根因=Velopack 安装器对 CJK 路径的访问被拒**（交互探测 LOCALAPPDATA/注册表/StartMenu 均可写=非权限问题本身）→ 桌面用户从下载目录（通常 CJK 路径）双击 Setup 可能同症；**缓解=发布时随附 ASCII 路径安装指引或自动拷贝到 ASCII 临时目录再拉起**（D7 发布流程前置条件）。
- **0.6.0 Setup 覆盖安装 0.5.0**:`Directory already exists, and user cancelled overwrite`(silent 自动取消）= Velopack 设计行为，覆盖安装非升级路径；正式升级走 UpdateManager(releases feed)+`VelopackApp.Build().Run()` 钩子（已在 App.OnStartup 最开头接线，t58)——**自动更新检查 UI/releases 托管=D6.3** 范围（GitHub Releases + 未签名 SmartScreen 提示卡）。
- **zstd 增量 delta 失败**:`Creating delta 0.5.0 -> 0.6.0` 对 `Swdm2.App.deps.json` 等文件 `Failed to create zstd diff`(StdErr 空；vpk 1.2.161+本机）→ 采取 vpk 建议 `--delta none`（脚本默认）=全量包升级；增量包大小不受体积约束（决策 10）保留，zstd 问题标为弯路嫌疑待复验（换网络/换机）。
- 桌面会话实测：沙箱无双桌面 → 已安装 App 无法做首次运行可视实测；落盘+版本+快捷方式+Update.exe 存在性为文件级证据（同 FlaUI 输入族基线 ENV-DOWNGRADE 条款，桌面复跑条款由 D7 发布门承担）。

**基线包注记**：0.5.0 基线由当前源码 `-p:Version=0.5.0` 重打（程序集 FileVersion 残留 0.6.0.0=Directory.Build.props 三同步优先级；仅用于升级路径模拟，真实 0.5.0 已发布）。
