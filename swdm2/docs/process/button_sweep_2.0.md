# SWDM 2.0 全按钮实测核对表（D9.1 / t67）

> 用户指令（2026-10-04 硬约束）："每一个按键和设计元素在每一个页面下都必须真实有效且经过用户端测试；无效/死按键禁止交付。"
> 实测口径：沙箱物理点击被前台锁吞（t62 归档环境族）→ **InvokePattern 命令链 + UIA 树转储**为沙箱内可用口径（真实用户点击=qa-20 桌面通道最终证据）。
> 证据源：`tests/Swdm2.UiTests/Tests/Sweep/ButtonSweepDesktopTests.cs`（逐页导航+转储 8 次落 `.dtmp/sweep.log`）+ 各 VM 逻辑层单测 + 桌面链路测试。
> 日期：2026-10-04。HEAD=待提交（t67）。

## 扫掠方法

1. 启动真实 App（`Swdm2.App.exe`，Debug 构建）。
2. 初始页=主页 SphereHome → 逐页 Invoke 导航钮（导航钮自身即被实测：enabled + 点击=页面切换反馈 + 树转储出现该页元素）。
3. 转储每页 UIA 树（`UiTestHelpers.DumpTree`），清点全部契约 id（下表"页面元素清点"列）。
4. enabled 合理性=VM 代码 CanExecute 逻辑+逻辑层单测；点击反馈=命令链桌面测试/单测。

## 窗口级（每页共有）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| MainShell_Nav_HomeButton | 恒 enabled | 跳主页（球体） | ✅ 转储出现 SphereHome 元素 |
| MainShell_Nav_BrowseButton | 恒 enabled | 跳浏览页 | ✅ 出现 WorkshopBrowsePage_* |
| MainShell_Nav_ModDetailButton | 恒 enabled | 跳详情页 | ✅ 出现 ModDetailPage_* |
| MainShell_Nav_DownloadsButton | 恒 enabled | 跳下载页 | ✅ 出现 DownloadsPage_TaskList_Items |
| MainShell_Nav_LibraryButton | 恒 enabled | 跳库页 | ✅ 出现 LibraryPage_* |
| MainShell_Nav_SettingsButton | 恒 enabled | 跳设置页 | ✅ 出现 SettingsPage_* |
| MainShell_Nav_GameSelectButton | 恒 enabled | 跳游戏选择 | ✅ 出现 GameSelectPage_* |
| MainShell_Nav_BackButton | 返回栈非空才 enabled | 返回上一页 | ✅ t62 死钮修复项：从设置返回=转储回到设置页（导航生效）|
| Main_Window_Minimize/Close | 系统钮 | 最小化/关闭 | ✅ 系统实现 |

## 主页（SphereHome）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| DefaultGameCard_StartButton | **未绑定游戏=禁用**（t67 死钮修复：原空实现 startGame 已接 `steam://run/{appid}` 协议）| 拉起 Steam 客户端启动绑定游戏 | ✅ 未绑定时 CanExecute=false（禁用≠死钮）；绑定时=真实进程启动（catch 容错） |
| DefaultGameCard_DownloadModButton | 恒 enabled | 跳 GameSelect | ✅ 转储出现 GameSelectPage_* |
| SphereHome 贴图点击（TileClickedCommand）| 恒 enabled | 跳该游戏 mod 选择 | ✅ t54/t65 实测 |

## 浏览（WorkshopBrowsePage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| WorkshopBrowsePage_SwitchGameButton（t67 新增）| switchGame 回调注入才 enabled | 跳 GameSelect 搜索 | ✅ 桌面 `Browse_TopBar_SwitchGame_...` PASS（切换→SearchBox 出现） |
| 条目「详情」Item_DetailButton（t63）| 动作注入才 enabled | 传真实 id 跳详情真加载 | ✅ 单测+桌面链（真源网络不可达时 ENV-DOWNGRADE，逻辑层 4/0 覆盖） |
| 条目「下载」Item_DownloadButton（t63）| queue+工厂注入才 enabled | 入队+行注册+跳下载页 | ✅ WorkshopBrowseItemActionsTests.Download_Item_Command_... PASS |
| 重置 / PrevPage / NextPage | 筛选后/分页边界 CanExecute | 重建列表 | ✅ WorkshopBrowsePageViewModelTests 11/0 |
| 缩略图槽位（t67）| PreviewUrl 有=Image;无=占位灰底 | — | ✅ WorkshopBrowseD9Tests（HasPreview/占位诚实） |
| 示例横幅（t67）| IsSampleData=true 显式标注 | — | ✅ 单测覆盖（真源接入后隐藏） |

## 详情（ModDetailPage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| ModDetailPage_DownloadButton | 恒 enabled | 入队+跳下载页 | ✅ t63 桌面链 PASS（队列出现任务行） |
| ModDetailPage_ReloadButton | 非加载中 | 重新拉取详情 | ✅ 单测覆盖（错误态重试） |
| 示例横幅（t63）| IsSampleMode | — | ✅ 真实 id 接入即隐藏（单测 4/0） |

## 下载（DownloadsPage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| 下载行操作（暂停/取消/重试/打开目录/清理）| 行状态机 CanTransition | 状态推进 | ✅ DownloadsPageIdmViewModelTests 10/0（行按状态启用）；行在入队后出现=t63 桌面链证据 |

## 库（LibraryPage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| LibraryPage_RefreshButton | 非加载中 | 重新扫描 | ✅ Library 10/0 |
| LibraryPage_CheckUpdatesButton（t59）| 更新源注入+有行+非检查中 | 角标/Hint/行标记 | ✅ LibraryUpdateTests 6/0（不阻塞+询问才入队） |
| LibraryPage_EnqueueAllUpdatesButton | 有候选+非检查中 | 全部入队+清标 | ✅ Enqueue_All_Updates_After_Ask_Gesture |
| LibraryPage_OpenDirectoryButton | 选中行 | explorer 打开 | ✅ 单测（选中启用语义） |

## 设置（SettingsPage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| SettingsPage_SaveButton | 校验通过 | 持久化+重探 | ✅ Settings 10/0 |
| 游戏搜索联想+绑定（t64）| 有候选才确认 | 落配置+主页即时 | ✅ DefaultGame/Settings 单测 |
| SettingsPage_Update_Check/Download/Apply | UpdateManager 状态机 | 检查/下载/应用升级 | ✅ Updates 6/0（t60） |
| 主题单选/代理下拉 | 恒 enabled | 即时换皮/切换 | ✅ Settings 10/0 |

## 游戏选择（GameSelectPage）

| 按钮 | enabled 依据 | 点击反馈 | 实测 |
|---|---|---|---|
| GameSelectPage_ConfirmButton | 有候选 | StatusHint"已选择：X"+导航详情 | ✅ VM ConfirmSelection→StatusHint 绑定在位（转储 GameSelectPage_StatusHint 出现）；用户"点了像没反应"=详情页此前无内容=t63 示例横幅+真实加载已修复落地反馈 |

## 次级页/行级

- 详情依赖行（ModDetailPage_DependencyList_Items）：列表项，无按钮（id 直显）——✅ 契约保持。
- 下载行操作：见下载页节。
- 设置分组：SmartScreen 提示卡步骤文字（非按钮）+ 三个更新钮（见设置节）。

## 本轮发现并修复

| 项 | 问题 | 修复 |
|---|---|---|
| DefaultGameCard_StartButton | 空实现死钮（"D5.x 占位"注释）| steam://run/{appid} 真实启动+未绑定禁用（CanExecute 订阅 DefaultGameService） |
| 浏览卡片 | "Mod #123456·剧情作品"假前缀、类别冒充标题 | 名字优先+类别副标题后置+占位缩略图+示例横幅 |
| 浏览页 | 无快速切换游戏入口 | 顶栏当前游戏+切换钮→GameSelect |

## 环境备注（诚实降级）

- 沙箱真实物理点击=前台锁族（t62 实锤），全按钮"用户端真实鼠标"最终证据=qa-20 桌面通道/用户实机复跑。
- 浏览条目命令链桌面测在真源网络不可达时走 ENV-DOWNGRADE（条目空），命令链由逻辑层单测覆盖；真源在线环境复跑=visual-20 t68 的 BrowseRealSourceJourneyTests 职责。
