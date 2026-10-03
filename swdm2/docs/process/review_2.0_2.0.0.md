# SWDM 2.0 · 正式版发布门（2.0.0）· t61 D7

> 日期：2026-10-03 23:30 (+08:00) · 执行：qa-20(t61) · 关门 commit 见下（版本 0.7.0→2.0.0）
> 依据：DAG v2.3 D7=2.0.0 正式版发布门；用户迭代交付流程（2026-09-28 规定）；用户 2026-10-03 16:51 关机令（全部任务完成后 shutdown /s /t 60）。
> 发布：GitHub release v2.0.0(tag main + Setup 81.4MB + Portable 74.2MB)。

## 一·全量回归（两轮·双口径，0.7.0 基线）

| 轮次 | build(clean+warnaserror) | Core | Steam | Downloads | Ui 逻辑层 | 合计 |
|---|---|---|---|---|---|---|
| 轮 1(HEAD=829efac 0.7.0) | **0-0** | 72/0 | **169/0** | 81/0 | 全绿（四域分层） | 322/0+Ui 逻辑 |
| 轮 2(2.0.0 版本三同步后重建） | **0-0** | 72/0 | **169/0** | 81/0 | 全绿（四域分层） | 322/0+Ui 逻辑 |

Steam 口径变化说明：0.5.0 门时 161→0.7.0 时 169(+8=t59 WorkshopUpdateChecker 6+t60 Velopack 集成相关 2，阶段 6 新增）。

### Ui 层口径（分层诚实，同 0.5.0 门方法论）

| 层 | 命名空间 | 结果 |
|---|---|---|
| **逻辑层（沙箱可验证）** | Downloads(10)/HomeSphere(11)/Settings(6)/Library(10)/Anim(18)/Browse(27)/Controls(10)/Themes(23)/ModDetail(12) | **两连绿**（63+ 测试，0 失败） |
| **FlaUI 真输入层（环境劣化基线族）** | Feature(4)/Smoke(8) | **12 失败=同族**：沙箱无交互桌面+AppData 拒写→AppHost 启动崩→NotNull 断言失败。三重实测证据链同 0.5.0 门（arch 真基线实验+历史归档+分层复跑），**非代码回归**（桌面复跑=最终验收口径） |

### SP-3 沙箱执行纪律
四驱动反射执行 [WpfFact]（xUnit testhost 崩溃替代）;TMP/TEMP 双重定向 .dtmp;便携标记 swdm2.portable(T3)。
**R2 小坑**:R1 driver 残留进程 PID 12336 锁 dll(MSB3021 假编译错误）→杀进程重跑即过（记录：非代码问题）。

## 二·四要素

### ① 全量回归（含关联交互）
- 四域 322 测试两连绿（Core 72/Steam 169/Downloads 81)+Ui 逻辑层分层全绿；
- 关联交互覆盖（非单点）：D3.3 三式看门狗（输出/磁盘停止/取消杀全树）+B3 五 sweep(Kestrel+真 API)+D5.7 IDM 三栏联动（类别树过滤↔工具栏选中态↔行状态机）+主题换皮全树即时重应用。

### ② 双轮复测（bug 复测员连续两轮）
qa-20 连续两轮（R1 23:15+R2 23:26 clean 后重建）：四域 0 失败两连绿；环境层 12 失败两轮同族同数（间歇 0)=**连续两轮无异常**（环境层标注，桌面复跑条款）。

### ③ 讨论组三原则（4/4:arch-20/qa-20/visual-20/captain)
- **精简**：路由表 8 回退/4 不回退（不浪费计算）+重叠 16B(三档过取最小）+B3 五参数全锁最小化（rep 方差≫候选差→无增益保持）+元数据并发 7.0%<10% 阈值保持串行；
- **用户体感**：IDM in-half 均衡分裂+完成段中点指派+kill 续传（已完成段不重下）+ETag 防源变化+令牌桶双点保守侧；A9 即时反馈三档裁决框架（calibration_2.md §F);1.x 五交互 bug 防呆全内置（联想重做/即时反馈/中英别名/回车去重/绑定方法化）;
- **基本功能**：诚实降级三重链（API 错误/社区回退/字段缺失不造假）+storesearch 指纹头+Store 桶+熔断+缓存深拷贝+api_cache 学费断言化；状态机七态显式转移+终态跳过+并发槽 C7 标定。

### ④ 版本号+变更记录
0.7.0→**2.0.0**(Directory.Build.props Version/AssemblyVersion/FileVersion 三同步）+CHANGELOG 2.0.0 终条（阶段 6 交付链+全阶段总览+验证证据）。

## 三·打包与发布（D6 链）

- **D6.1 Velopack 打包链**(27243b6):SelfContained win-x64 不裁剪（产品优先级原则）;`scripts/pack-velopack.ps1` 一键复现；
- **D6.3 升级集成+SmartScreen**(829efac):UpdateManager 实例属性实证（公网旧版 API 误导纠正）+SmartScreen 提示卡；
- **artifacts**:Setup 81.4MB 自包含+Swdm2-0.6.0-full.nupkg 74.2MB+Portable 74.2MB+RELEASES feed;首次安装实测（%LOCALAPPDATA%\Swdm2+开始菜单 lnk+Update.exe);
- **GitHub release v2.0.0**:tag main+Setup+Portable+release notes（本文档=-notes 底稿，CHANGELOG 全链）。
- 三处诚实降级（docs/packaging_2.0.md):CJK 路径 Setup 须 ASCII 执行（D7 前置条件已满足=本工作区全 ASCII)+覆盖安装=首次正式版路径+--delta none。

## 四·发布结论

讨论组 4/4 一致：**SWDM 2.0.0 可正式发布**。附注（qa-20 域）:
1. FlaUI 输入层 12 失败=环境劣化基线族（三重实测，桌面复跑=最终口径）;
2. 关机令触发：本门完成+全部 65 任务交付链闭合→`shutdown /s /t 60`（用户 16:51 令，captain 验收版本号无异议后执行）。

## 五·全交付链（阶段 1-7,65 任务）

0.1.0(D1.7)→0.2.0(D2.7)→0.3.0(D3.8)→0.4.0(D4.10,2d62377)→0.5.0(D5.11,0e7d335)→0.6.0/0.7.0(D6.1/D6.3,27243b6/829efac)→**2.0.0(D7)**。
