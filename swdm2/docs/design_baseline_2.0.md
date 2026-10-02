# SWDM 2.0 设计基线（Design Baseline）

> 版次：v1.0 · 2026-10-02 · 维护：captain · 用途：**所有研究结论与阶段总结的对照锚点**
> 纪律（用户 2026-10-02 明定）：任何总结必须与本文档逐条对照；网络不稳定造成的获取失败/空结果不得误读为"不可行"；与基线冲突的发现标"弯路嫌疑"并换源复验后才能写进结论。

---

## 一、用户指令基线（不可变，来自 2026-10-02 14:19 原话）

1. **路线**：C# WPF 重构（路线①，覆盖此前报告推荐的路线④）。
2. **摒弃**：一切已有开发路径（Python/PySide6 代码与架构）。
3. **保留**：① 开发期间走过的弯路与教训；② Steam community 机制研究（含下载内核知识）。
4. **设计参考**：PCL2（UI 与拉取设计）、IDM（下载 UI 与下载内核设计）。
5. **自由度**：摆脱 1.0 一切限制，重新开发。
6. **资源授权**：不限量 subagent、不限量截图读图、不限 token。
7. **测试纪律**：bug 测试必须模拟真实用户端鼠标点击与键盘输入，禁止假测试；研究要多方检索人类经验，不要自以为是。

## 二、已锁定决策（研究/实测定型，变更须走讨论组）

| # | 决策 | 依据 |
|---|---|---|
| 1 | .NET 8 SDK（8.0.425，本机 winget 装入） | LTS、WPF 成熟支持 |
| 2 | 解决方案骨架 `swdm2/`：App(WPF net8.0-windows) / Core / Steam / Downloads(类库 net8.0) / UiTests(xunit net8.0-windows)，引用已接线、build 0 警告 0 错误 | 域边界即类库边界（域 owner 直映） |
| 3 | UI 测试：**FlaUI 6.0.0（2026-08-13 发布，fallback 5.0.0）UIA3 + xUnit + Xunit.StaFact，进程外 `Application.Launch` 启被测 exe**；选择器一律 AutomationId；显式等待（Retry.While/Wait.Until，禁 Sleep）；Screen Object 模式；失败截图 FlaUI.Capturing | docs/research2/wpf_ui_testing.md + captain 换源复验（agent 标注的版本漏项已纠） |
| 4 | 中文输入：ValuePattern Enter 为主 + Unicode 键事件/Ctrl+V 真实路径；**IME 拼音模拟不做** | 同上（与 1.x QTest CJK 限制同源，WPF 侧方案更优） |
| 5 | 视觉校验：被测进程内 Windows.Media.Ocr（中文）+ 像素 diff 补盲区；截图读图（modlens 桥，本机已恢复）作二次校验 | 同上 + 2026-10-02 实测 |
| 6 | CI：本机交互会话运行（FlaUI issue #168：托管 runner Session 0 无桌面） | 同上 |
| 7 | 团队：swdm-2.0 沿用域 owner 线（arch-owner 架构/稳定性、visual-owner 视觉/UI、qa-owner 独立复测；captain 集成/构建/交付）——专人专项非必要不换人（用户 2026-10-02 重申） | 用户规矩 |
| 8 | **下载域双 provider**（2026-10-02 复验后锁定）：SteamKit `CDNClientPool` 真·IDM 内核为主（depot chunk 级并行、默认 8、chunk 自带 SHA 校验——比 IDM 更强；DepotDownloader 源码实证 `isUgc` 路径支持 Workshop 内容）；steamcmd 兜底（无逐字节进度/0 字节假成功等 quirk 保留）；HTTP 直链场景用 bezzad/Downloader 式分段+`.download` 尾部元数据续传；磁盘 IO 单文件偏移直写+NTFS 稀疏占位（不支持则 SetLength 降级） | docs/research2/idm_download_kernel.md + captain 换源复验（DepotDownloader GitHub 主源） |

> 对基线 §四功能范围的影响：下载域从"steamcmd 单源 + 体感映射"升级为"真并行内核"，IDM 体感（速度/ETA/分段数/限速/队列）全部为真功能；steamcmd 路径分段数诚实降级 N/A。

## 三、保留资产清单（2.0 必须继承的"学费"）

来自 docs/architecture/system_contracts.md 与历史教训：
- **参数类经验必须实测重标定**（用户 2026-10-02 纪律）：下列数值仅作起点，不得照抄——429 退避（1.x 用 30s 起/90s 封顶）、端点节流间隔（详情 3s / browse 2s / RemoteStorage 3s）、并发上限（1.x 单源串行）。2.0 交付前必须有基准实测任务（见 §四验收）回答"能否更短/更小"，实测后才可锁参数。
- **429 指纹层**：裸 Chrome UA 缺 Accept-Language 必 429；补 `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8` 即 200（34 次实测）；429 响应从不带 Retry-After；Referer/Origin/匿名 cookie 全无效。
- **403 = IP/代理边缘层**：快速失败抛限定错误，用过期缓存兜底，重试无用。
- **节流纪律**：端点差异化间隔（详情 3s / browse 2s / RemoteStorage 3s）；锁覆盖 read-sleep-write 全程；用户点击 priority 绕过等待、低优先级让出槽位。
- **缓存命中必深拷贝**（可变数据 + 就地 enrich 的污染事故）。
- **steamcmd quirk**：无逐字节进度、0 字节假成功、downloads 临时目录、输出行解析、退出码语义；**mod 更新不删除已删文件**（SteamCmdWrapper/RimPy 案例：需 wrapper 做时间戳 zip 备份解决——docs/research2/scw_readme.md）。
- **版本号双端同步**纪律（程序 + 安装器）。
- **凭据不落日志/不进配置**（DPAPI/keyring 方向在 C# 侧重做）。
- **UI 层教训**：联想模型原地更新（勿 clear() 重建）；每个用户操作要有即时反馈（≤150ms）；中英别名/归一化搜索；隐式单例显式化。
- **Web API 复验纠错（2026-10-02 实测，推翻 csharp_steam_workshop.md §0.4 结论）**：`ISteamRemoteStorage/GetPublishedFileDetails` 匿名**可用且完整**——以真实在线 id 3808352517 实测返回 result:1 + title/description/file_size 4930110/creator/preview_url；此前 result:9 系测试 id 已失效（104484086），非端点不可用。⇒ **2.0 元数据主源 = Web API（结构化），社区页面降为回退源**（浏览列表/依赖 referenced_files 等 API 未覆盖项）。`GetFileSize` 端点确实 404 不存在（剔除）。file_url 字段为空（2017 年移除，下载仍走 steamcmd/CDN）。
- **端点可达性矩阵（用户 2026-10-02 提出的部署约束）**：用户主机分"有代理/无代理"两类——无代理（典型大陆直连）主机：`api.steampowered.com` 通常直连可用、`steamcommunity.com` 常被 DNS 污染/SNI 重置、`store.steampowered.com/api` 通常可用；有代理主机全通。⇒ Steam 域架构：① Web API 为元数据主源；② 社区页面回退（仅代理可用时）；③ 启动期三端点探测 + 状态栏如实显示（直连/系统代理/自定义代理）；④ 失败引导用户配代理，不静默失败。**C# HttpClient 不读系统代理——须显式接管代理设置。**

## 四、功能范围基线（1.x 对等 + 2.0 增强）

对等（不退化）：游戏选择（联想/中英/别名）、工坊浏览（分页/标签/排序/搜索/作者筛选）、mod 详情（依赖/冲突/评论）、下载（队列/暂停/继续/取消/重试/限速/断点续传/provider 链回退）、mod 库管理（分类/导入导出/更新检查）、设置（目录/账号/引擎参数）、匿名模式。

增强（2.0 目标）：PCL2 级视觉（卡片/阴影/双段缓动/明度阶梯）、IDM 级下载体感（行级速度/ETA/分段数、队列调度、限速、完成通知）、部分支持接入 Steam 官方。

## 五、对照协议（每份研究/阶段总结必填）

```
## 对照基线结论
- 与基线一致的部分：（逐条）
- 与基线冲突/超出的发现：（标注）
- 弯路嫌疑（可能因网络不稳误读）：（复验状态：换源/换条件）
- 采信/搁置/复验的决定：（理由）
```

## 六、当前进行

- 研究冲刺（5 路）：wpf_ui_testing ✅（版本漏项已纠）；wpf_stack / csharp_steam_workshop / idm_download_kernel / pcl2_xaml_patterns 进行中。
- 骨架：swdm2/ 解决方案 build 绿。
- 下一步：研究齐 → arch-owner 出 2.0 架构说明书（对照本基线）→ 团队任务分阶段。
