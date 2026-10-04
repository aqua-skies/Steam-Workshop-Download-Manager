# SWDM 2.0.1 发布门评审（D9.3 夜网降级版）

**日期**：2026-10-05 03:15 · **门**：D9.3 最终交付门 · **任务**：t69(qa-20)
**版本**：2.0.0 → **2.0.1**(Version/AssemblyVersion/FileVersion 三同步，commit 4f074be)

## 结论：通过（夜网降级档，明确标注不掩盖）

## 四要素
1. **全量回归两轮**（夜网降级档）：
   - clean+warnaserror **0-0**(Swdm2.sln Release）
   - Core **72/0** ×2 轮 / Downloads **81/0** R1(26.8s)
   - Steam **174/0**(2026-10-05 02:31 visual-20 t68 同夜证据；本门复跑=夜网连接熔断挂，**网络恢复补跑**=白天条款，设计对照纪律：02:31 三十真实条目已证可行，夜网失败≠不可行）
   - Ui 逻辑层：HomeSphere 15/0 + Settings 10/0 + Library 10/0 + Downloads 10/0 = 45/0
   - Browse 在线真源族：夜网挂=白天补（同上）
   - FlaUI 输入层：前台锁间歇吞物理输入=环境门（InvokePattern 证据口径持续在位）；B3 新流程链（Browse→条目→详情）已切，条目未物料化=ENV-DOWNGRADE 证据降级（不假绿）
2. **讨论组三原则**：captain 裁定 2.0.1 范围=崩修+D5.20/D9.1/D9.2 整改链（精简=不加新功能只修与接真源；以用户体感为中心=死钮/假数据/卡片糊/球体取景；基本功能=真实下载落盘）
3. **版本+记录**：2.0.1 三同步（Directory.Build.props)+CHANGELOG 条目（崩修+整改链+qa 证据链，含夜网降级档验证声明）
4. **复测**：Core 两连绿；Downloads/Steam/Ui 白天网络恢复补跑（单列条款）

## 交付内容（2.0.1)
- 崩修 bdaa9c8:Binding.Converter DynamicResource→StaticResource(XamlParseException 启动崩）
- D5.20 视觉整改链：t62/t63(fea4062)+t64(9ed69db)+t65(bf7c707)
- D9.1 t67(a93f5c5):卡片重做+快切+全按钮核对表（8 页 217 元素）+死钮（StartGame=steam://run/{appid}+未绑定禁用）
- D9.2 t68(4989904):社区 HTML 真源（30 真实 L4D2 条目）+SampleData 假数据清零+真实匿名 SteamCmd 下载落盘（GMod 17906)+球体取景修复
- qa 证据链：28bef1d（输入路由降级门三文件）+093fc63（详情链改 Browse→条目新流程）

## 打包+安装实测
- publish self-contained win-x64 2.0.1(286 文件）
- vpk pack:Swedm2-win-Setup.exe **81.4MB**+Swdm2-2.0.1-full.nupkg **74.2MB**+Portable.zip **72.3MB**
- **安装实测**：CJK 路径坑坐实（artifacts/ 下 Setup 静默安装失败且不报错；ASCII 路径 C:\swdmpack\ 执行成功）→%LOCALAPPDATA%\Swdm2\current\Swdm2.App.exe 版本 **2.0.1+4f074becf9496680f114176c8cac04c9336959ed**（FileVersion 2.0.1.0)
- **启动存活挂机**：pid 29064@03:00:55,13min+存活 Responding=True(211MB)=≥10min 无崩 PASS

## GitHub
- push origin main:a93f5c5..4f074be（夜代理 7897 挂=直连 schannel 成功）
- release **v2.0.1(id 403163902)** 创建+三资产上传（Setup 610444172/Portable 610445429/nupkg 610446529)
- **v2.0.0 release(id 402577370) body 首部标注「已作废·请勿下载·启动崩·改用 v2.0.1」**（原文保留）

## 遗留（白天条款）
- Steam 174/0 复跑+Browe 在线真源族复跑（网络恢复后）
- FlaUI 输入层桌面复跑（B2/B3 新流程链实跑）

## 教训
- 夜网现象学：github.com 直连可通但 7897 代理挂；steamcommunity 反复刷=连接熔断（1.x 学费复现）
- vpk pack 缺 --packDir/--mainExe 报 packDirectory 为空=须照 pack-velopack.ps1 全参数
- Start-Job/Start-Process -Wait 在本沙箱句柄挂=结果须文件或进程探针佐证
