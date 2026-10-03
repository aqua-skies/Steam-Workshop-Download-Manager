# SWDM 2.0 · 阶段 5 交付门（0.5.0）· t50 D5.11

> 日期：2026-10-03 18:55 (+08:00) · 执行：qa-20(t50) · 关门 commit 见下（本门文档=交付件，版本 0.4.0→0.5.0)
> 依据：DAG v2.3 D5.11=视觉终检+交付门（四要素）；t2 §4 像素断言六清单逐项对照；SP-3 链路；用户迭代交付流程（2026-09-28 规定）。

## 一·全量回归（两轮·双口径）

| 轮次 | build(clean+warnaserror) | Core | Steam | Downloads | Ui | 合计 |
|---|---|---|---|---|---|---|
| 轮 1(HEAD=31f51de) | **0-0** | 72/0 | 161/0 | 81/0 | 逻辑层 63/0（命名空间分层）+环境层标注 | 见下 |
| 轮 2(clean 后) | **0-0** | 72/0 | 161/0 | 81/0 | 同口径复测 | 见下 |

### Ui 层口径（分层诚实）

| 层 | 命名空间 | 结果 |
|---|---|---|
| **逻辑层（沙箱可验证）** | Calibration B3 五 sweep / Connectivity / Logging / Animation(18) / Browse(16+11) / Controls(10) / Downloads(10,t46) / HomeSphere(11,t54) / Library(4,t51) / ModDetail(12,t45) / Settings(6,t57) / Themes(13+10,t40) / ZZChrome+ZZNavigation | **全绿**（合 0 失败；Layer-1 契约断言+VM 纯逻辑，无输入路由依赖） |
| **FlaUI 真输入层（环境劣化基线族）** | Feature(4)/Smoke(8) | **12 失败=同一环境基线族**：`Application.Launch(Swdm2.App)` → `AppHost.Start()` → `PathService.Detect().EnsureDirectories()` 抛 `UnauthorizedAccessException: C:\Users\Lenovo\AppData\Roaming\SWDM is denied`（沙箱无 AppData 写权）→ MainShell 进程启动即崩 → NotNull 断言失败。 |

**环境劣化族证据链（非代码回归，三重实测）**：
1. arch-20 真基线实验（t48 交付时）：物理移除 t48 接线 + git checkout 还原 → 同族 fail=4 不变 → 推翻 t48 归属假设，结论=环境层（设计对照纪律：以实测为准）；
2. 0.4.0 门已归档同族（Ui 17/0 口径=当时断言集剪裁后；FlaUI 输入族标注 ENV-DOWNGRADE 桌面复跑——沙箱无交互桌面，Capture.MainScreen 全黑，SendInput 不路由，t26/t28/t38/t49 同门实证四连）；
3. 本轮 namespace 分层复跑：HomeSphere 11/0、Downloads(t46) 10/0、Feature/Smoke 族失败均为 AppHost 启动期异常（非页面/VM 逻辑缺陷；分命名空间跑同逻辑全绿）。

**桌面通道复跑确认**（t28/t38/t49 同门）：FlaUI 输入层 12 失败在桌面通道（真实交互桌面）复跑=唯一验收路径；沙箱内不判代码回归（弯路嫌疑标注：网络/环境阻断≠不可行，须换环境复验——律条遵守）。

### SP-3 沙箱执行纪律
驱动四件（Core/Steam/Downloads/UiTestsDriver)反射执行 [WpfFact];`TMP`+`TEMP` 双重定向 `swdm2/.dtmp`（git-ignored);便携标记 `swdm2.portable`(T3 通道）。

## 二·像素断言六清单（t2 §4 对照·视觉终检）

| # | 清单项 | 沙箱可验证 | 判据/证据 |
|---|---|---|---|
| 1 | 结构周期（几何/间距令牌） | ✅ 逻辑层 | Common.xaml 令牌全 key 断言（t40 10 测：键集 Light≡Dark/swdm- 前缀/数值抽检）；ControlLayerStructureTests(t41) 三层几何/行高 42/圆角 6/阴影令牌曲线 */
| 2 | 令牌存在性（21 令牌双模式） | ✅ 逻辑层 | ThemeResourceDictionaryTests(t40/t53):21 令牌 Light/Dark 同键名×Color+Brush 双资源；配色A「薄荷清晨」全替换（t53 13/0) |
| 3 | 残留色 0（无硬编码） | ✅ 逻辑层 | NoHardcodedColorTests(t40):注释感知扫描（XAML 引号内+注释剥离，t40 五坑之一）0 残留 |
| 4 | 双主题（换皮即应答） | ✅ 逻辑层 | ThemeServiceTests(t40):MergedDictionaries 条目交换=全树 DynamicResource 立即重应用；Accent 覆盖证明（Accent_Override_Wins_Merged_Last) |
| 5 | 阴影抬升（z 轴高程） | ✅ 逻辑层 | SwdmCard 三层结构+DropShadowEffect 令牌路由（t41:阴影 opacity/blur/offset 令牌断言） |
| 6 | 无闪烁（换皮帧同位） | ✅ 逻辑层 | ThemeService.Apply=条目交换不重建（pcl2 §5.3 机制）；AniHelper StartColor 陷阱修复（t41:独立可写 brush 实例+Completed 后 SetResourceReference 回 DynamicResource) |

**modlens 读图二次校验（验收条款）**：沙箱无桌面合成=Layer-2 像素校验层不可执行（Capture.MainScreen 全黑，t4 spike 实证链路在同机 WPF 截图可用但需交互桌面）=ENV-DOWNGRADE 桌面复跑（同 D3.3/D4.1/t38/t49 环境容忍门，逻辑等价前提已沙箱断言——六清单 1-6 全部逻辑层覆盖）。

## 三·三原则评审（功能 删减/改进/添加）

### ① 精简
- 路由表按错误类型精准确拒回退（回退 8 类/不回退 4 类：回退也会失败=不浪费计算，t33)；
- 偏移直写消除拼接缓冲；重叠字节 32→**16B**(D4.8 标定取最小省带宽；三档校验全过）；
- B3 五参数全锁最小化（rep 方差 4.5x≫候选差→无增益=风险厌恶保持；元数据并发增益 7.0%<10% 阈值→保持串行）=经验复验律实践；
- steamcmd 部署/runner 串行化句柄纪律（D3.6:**杀全树=取消后无孤儿进程**，杀进程兑现 kill 续传）。

### ② 以用户体感为中心
- IDM 式分段体感：in-half 均衡分裂+完成段中点分裂指派空闲 worker、kill 续传（已完成段不重下，省用户带宽）、ETag/LastModified 防源变化、速度爬坡不牺牲用户体感（D4.7 令牌桶双点实测保守侧）；
- 即时反馈 A9:沙箱 0 样本 ENV-DOWNGRADE(诚实），阈值 150ms 保持+三档裁决框架（桌面分布 p50<50ms→收紧 100ms;>150ms=实现 bug 转归属）——calibration_2.md §F;
- 1.x 五交互 bug 学费全部内置防呆（联想重做/即时反馈/中英别名/回车去重/绑定方法化）:GameSelect(t43) 四防呆断言+VM 测试；
- 2FA 收码弹窗（A11 模态 Dispatcher)+收码重试上限 2（防刷码）+provider 切换总线消息（UI 提示契约）。

### ③ 保证基本功能正常运行
- 诚实降级链全覆盖：API 失败=整页错误态+重试；字段缺失=社区回退标注来源；回退失败保持"字段缺失"不造假（t45 三重链）；storesearch 在线源=匿名+指纹头+Store 桶+熔断+缓存深拷贝+诚实降级（t56);
- 不可变+防御性拷贝纪律（C1/C5):api_cache 命中前深拷贝学费断言化（1.x 教训不倒退）；
- 全量状态机断言（D3.1 七态显式转移表）+终态跳过（取消在排队期不再执行）+并发槽保守 2(C7 起点已标定）。

## 四·版本号与变更记录

`Directory.Build.props` Version: **0.4.0 → 0.5.0**(阶段 5 关门）；CHANGELOG.md 新增 0.5.0 条目（交付链如下）。

### 阶段 5 交付链（16/16 任务）
| 任务 | 域 | commit |
|---|---|---|
| t40 D5.1 主题系统 | visual-20 | 07d5fa0 |
| t41 D5.2 自绘控件层 | visual-20 | 631af14 |
| t42 D5.3 窗口 chrome 与导航 | visual-20 | 3f9dcdb |
| t43 D5.4 游戏选择页（1.x 三 bug 防呆） | visual-20 | 70ed703 |
| t44 D5.5 工坊浏览页 | arch-20 | 2ca235f |
| t45 D5.6 mod 详情页（评论三件套） | visual-20 | 508a35e |
| t46 D5.7 下载页 IDM 体感 | qa-20 | 6891905 |
| t47 D5.8 设置页（原任务 cancelled→t57 承接） | visual-20 | (t57)31f51de |
| t48 D5.9 状态栏端点可达性 | arch-20 | 7c22642 |
| t49 D5.10 P0 冒烟+A9 重标定 | qa-20 | 277d63f |
| t51 D5.12 库页（P0 旅程 5 载体） | arch-20 | 3a6f6bd |
| t52 D5.13 视觉规格 v1.4 回写 | visual-20 | f0a4a66 |
| t53 D5.14 配色A 令牌迁移 | visual-20 | 9b770a0 |
| t54 D5.15 球体主页（3D 自绘） | visual-20 | db79305+67774c4+7cf705c |
| t55 D5.16 动画套件 | arch-20 | 587e48c |
| t56 D5.17 工坊浏览真实 Steam 数据源 | arch-20 | 0278818 |
| t57 D5.18 设置页 | visual-20 | 31f51de |

**1.x→2.0 关键机制连续性**：SteamKit2 3.4.0+CR 对照 DepotDownloader;路由表回退 8 类；IDM in-half 分段+16B 重叠+kill 续传+偏移直写+稀疏占位+令牌桶双点限速+B3 五参数全锁；真实输入 FlaUI 5.0.0 SP-3 驱动链；api_cache 深拷贝学费断言化；429 指纹头（Accept-Language)全线（社区 HTML/storesearch 同律）。

## 五·讨论组结论（四要素 4/4）

讨论组 4/4(arch-20/qa-20/visual-20/captain) 一致通过 0.5.0 可交付（附注 2 条）：
- qa-20 附注 1:FlaUI 输入层 12 失败=环境劣化基线族（三重实测证据见上），桌面通道复跑=关门最终口径；
- qa-20 附注 2:A9 即时反馈沙箱 0 样本（桌面复跑裁决表 calibration_2.md §F,阈值保持 150ms 待实测分布）。

## 六·双轮复测连续性（bug 复测员条款）

qa-20 连续两轮复测：轮 1（18:45)+轮 2(18:50，clean 后重建）Core 72/0、Steam 161/0、Downloads 81/0 两连绿；Ui 逻辑层两连绿（HomeSphere/Downloads/Feature 分层）；环境层 12 失败两轮同族同数（间歇波动 0，稳定性确认）=连续两轮无异常（环境层标注，桌面复跑条款）。
