# 用户视觉 instruction 逐条核对表（t62 D5.19)

> 用户原话（2026-10-03 裁定 v1.4 + 本次整改指令）逐条核对。
> 三态：✅已实现 / 🟡部分实现（含待标定） / ❌未实现（排 D5.20+）。
> 截图证据见 docs/process/shots/t62_*.png。

| # | 用户 instruction | 状态 | 实现锚点（文件/提交） | 备注 |
|---|---|---|---|---|
| 1 | 右上 -× 钮放大 | ✅ | Ui/Chrome/TitleButtonHover.cs(t55 A5,commit 587e48c);MainWindow.xaml BtnClose/BtnMin `TitleButtonHover.Enable`+显式 ScaleTransform | hover 1.1/150ms Quintic;离开复原 |
| 2 | 页面切换流畅动画（上→下渲染半透明→凝实；抽屉下拉） | 🟡 | Navigation/PageNavigationService.cs(t2 §2.5):RunExit+110ms swap→+30ms opacity 凝实+RunEnter 双段位移+OutBack 回弹 stagger;DrawerSlide(t55 A2,设置页 Custom 抽屉） | **半透明→凝实+过冲回弹✓；页面级"抽屉下拉"未统一**（仅设置页 A2 抽屉） |
| 3 | mod 详情打开编排（左选项文字抽离/选项卡左抽让位/切页右拉+半透明凝实） | 🟡 | Navigation/PageTransitionOrchestrator.cs(t55 A3 四相 TextFade/TabDrawer/MainYield/DetailEnter,可断言相序） | **骨架+状态机就位，未接线到 SphereHome→ModDetail 实际导航**（t54 已记终值待对齐；排 D5.20) |
| 4 | 配色活跃轻松轻盈（当前看不清=不达标） | ✅本次修复 | ThemeService.cs Current=Dark→**Light「薄荷清晨」**(t62);App.xaml 合并 Dark→Light;token v1.4 实算（深字 #052E1F on accent 7.89✓,白字 1.88✗ 已弃） | **根因=默认 Dark 与亮色裁定相悖**；LibraryPage/SettingsPage 等按钮已 TextOnAccent |
| 5 | 主页默认游戏卡（名/图标在上/开始钮/下载mod直通/空态灰字前往设置） | ✅ | Ui/Pages/SphereHomePage.xaml(t54 db79305):DefaultGameCard 四槽位 Title/Icon/Start/DownloadMod+EmptyHint;t57 接线空态点击跳设置 | 图标 sample 路径（真实游戏图标绑 D6.x) |
| 6 | 圆弧连接全局 | ✅ | Themes/Common.xaml RadiusXs/Sm/Md/Lg=4/6/6/8(t53);卡片/按钮/提示卡 CornerRadius 全令牌化 | PCL2 数值（5/3/2)不照搬，本体系 4/6/6/8 |
| 7 | 球体主页（13 子项） | | Ui/Controls/HomeSphere/*(t54 3 commit) | 逐子项见下表 |

## 球体主页 13 子项明细（instruction 7)

| 子项 | 状态 | 锚点 |
|---|---|---|
| 透视右下 | ✅ | PerspectiveCamera 右下象限（camera distance 4.6) |
| 点线三角面 | ✅ | wiremodel;IcosahedronGeometry 12/20/30+细分 |
| 图标贴图透视贴边 | ✅ | tiledModel 贴图 |
| 无贴图透明 | ✅ | 透明材质槽位 |
| 液态玻璃半透明黑底 | ✅ | #14000000 Opacity 0.92 |
| 缓顺时针自转 | ✅ | 6°/s ⚠️[待标定] |
| 节点 1/r² 振荡影响 | ✅ | SpherePhysics(t54 物理修复 commit 67774c4) |
| 透视远暗近亮 | 🟡 | PointLight 薄荷光源在位；深度衰减渐变未做 |
| 鼠标光源+拖拽加速 | ✅ | MouseFieldStrength+拖拽惯性 0.92 |
| 贴图 hover 放大+点击跳该游戏 mod 选择页 | ✅ | hover 位移 0.012+TileClicked→GameSelectPage |
| 底色换图标虚化液态玻璃 | 🟡 | 底色换图标在位；虚化液态玻璃后处理未做 |
| 对话泡泡游戏名移开复原 | ✅ | GameBubble(t54) |
| 切页=球后移虚化→左侧文字左移虚化→选项卡左抽消失 | ❌ | 同 #3=Orchestrator 终值待对齐（D5.20) |

## 本次整改行为清单（t62)

1. **默认主题 Dark→Light**（ThemeService.Current + App.xaml 合并）：用户裁定"薄荷清晨"=亮色系；Dark 默认与"活跃轻松轻盈"相悖=「看不清」根因。
2. **导航重排中文化+下载入口强调**：MainShell_Nav_HomeButton「主页」+ MainShell_Nav_DownloadsButton「⬇ 下载」=accent 底双主钮（用户"找不到下载功能在哪"=入口不明确修复）;Library/Settings/Mod detail 英文混杂全部中文化；契约 id 全保留。
3. 关闭/最小化钮显式 ScaleTransform 声明（A5 hover 放大载体稳固）。

## 未实现排期（D5.20+）

- #3 + #7 切页编排接线（PageTransitionOrchestrator→SphereHome/ModDetail 实际导航；终值对齐）
- 页面级抽屉下拉统一（当前仅设置页 A2)
- 球体深度衰减渐变+图标虚化后处理
- 真实游戏图标绑定（D6.x 数据源）

## PCL2 源码提取（只读参考，GPL 隔离，数值/结构/手法借鉴）

- MyCard.cs：CornerRadius=5;阴影 idle 0.07→hover 0.4;半透明背景 brush
- MyHint.xaml:BorderThickness=3,0,0,0 左色条+CornerRadius=2;LineHeight=16 Padding 12,9
- MyButton.xaml:CornerRadius=3;**Foreground=BorderBrush 绑定（自对比机制）**;FontSize=13;TextFormattingMode=Display
- MyListItem.xaml:ScaleTransform 驻点+网格列 2/0/4/auto/1*/4
- ThemeManager.cs:LCH 色彩空间明度系（0.84/0.96 ×darkLight)=对比度保证
## t62 第二批整改（死钮 bug + 切页编排接线,2026-10-04)
1. 死钮修复（captain 实锤：返回钮 DISABLED @632,398):PageNavigationService.Navigate/GoBack/Initialize 调 InvalidateRequerySuggested + ViewModelBase.RaisePropertyChanged 统一传播同病治理；回归 DeadButton 2/0
2. 切页编排接线：SphereHomePage.OnLoaded 拦截贴图命令先跑 PageTransitionOrchestrator 前进三相对 LeftTabStrip+SphereHostControl 再导航（失败降级）
3. 环境层诚实：沙箱真实鼠标点击不路由（两次点击浏览均未导航，同 FlaUI 输入族基线）=桌面复跑条款
4. 对比度实算表 contrast_real.md(math_computation):全 token 合格
5. Updates 集成测改动态版本断言（feed=ignored 构建产物随发布门变 0.6.0->2.0.0 硬编码漂移假失败）
截图：C:\tmp\swdm2fix2\app.png/app5.png=沙箱无桌面合成=z-order 遮挡错位（像素青/暗墨绿色系非 SWDM 渲染）=真机复跑条款
