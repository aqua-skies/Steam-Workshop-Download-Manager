# SWDM 1.4.1 功能删减/改进/添加可行性评审

> 讨论组任务：t31（installer-fixer 主持，attempt 7a68a501）· 2026-09-29
> 评委：search-fixer · core-tester · gui-tester · recorder（四方）+ installer-fixer（主持）
> 评审输入：`docs/plan_1.4.1.md`（12 项候选）· `research/speed_usability_research_1.4.1.md` · `research/bypass_ownership_research_1.4.1.md` · `docs/competitor_research_1.4.1.md`
> 三原则：精简 · 以用户体感为中心 · 保证基本功能正常运行

---

## 〇、评审背景与结论

1.4.0 已正式交付（t27 六方一致 6/6 零反对，安装包 42.69MB）。1.4.1 基于三份深度调研 + 用户四轮需求输入，候选 12 项分三主题：A 文档与界面（4 项）、B 性能（3 项，均标 P0）、C 功能（5 项）。

**总结论：12 项裁决一致，零原则性反对。** 纳入 10 项（其中 6 项附改进点/硬约束）、延后 1.4.2 两项（+ 主持方裁决 S5 延后共 3 项）、砍掉 0 项。C5 真下载补测定为最先执行的先决项。两处计划外提问由主持方裁决（见第五节）。

**关键调研结论（评审基线，不重新论证）**：
- 速度报告：SWDM 的 HTTP 底座已优于三家竞品；增量价值在磁盘缓存 / 增量比对 / 预取。B1/B2/B3 标 P0；S4-B 并发是唯一 429 风险项**本期不做**
- 绕过报告：**不存在合规的"绕过正版限制"方案**（三层设防：license 检查 / file_url 签名 / depot key）。C3 私人账户 provider 是唯一合规解法（🟢）；C5 须探测 GGNetwork 后端登录态（若能解析受限物品 = 实质服务端账号池，🟡→🔴 须重新定位）
- 竞品报告：A1 是用户明确要求；A2 纯 QSS 零依赖（styles.py 已有 token 体系）；PyQt-Fluent-Widgets 因 GPL 传染仅借鉴不引入

---

## 一、主题 A：文档与界面

| # | 功能 | 裁决 | 票数 | 关键依据 / 改进点 |
|---|---|---|---|---|
| A1 | 用户手册（9 章，Markdown 源 → PDF+HTML 随安装包 + 程序内入口） | **纳入** | 5/5 | 用户明确要求。⚠️ **时序：代码冻结后写**（search-fixer）——界面状态（调试 Tab 开关 / 暂停继续合并 / 通道下拉）随实现漂移，文档骗人比没有更伤。打包侧 installer-fixer 接 ISS 加文件 + 帮助入口；recorder 接 docs/manual/ 源与 changelog 互链；**须列入回归范围**（帮助入口可打开 + 随包 PDF/HTML 存在），不能只当附件 |
| A2 | QSS 界面美化 P1-P5（纯 QSS 不引第三方库） | **纳入** | 5/5 | 用户明确要求；零依赖。⚠️ **硬约束：QSS padding/margin 一改动 GUI 几何**（U9 首行挤压就是 padding 类 bug）——每批改动后**立即**跑 test_gui_sweep + 几何量化（core-tester/search-fixer），不能等打包一次性验。P5 空状态引导与速度报告 B6 同一件事，**并入 A2 不单列**（gui-tester）。另加「主题切换不崩溃」「高 DPI 不挤压」两项断言 |
| A3 | README 截图 + badge 墙 + 能力清单 + 已知限制段 | **改进后纳入** ⚠️ | 5/5 | badge 墙 SVG 代码生成（零验证成本，installer-fixer 做）；截图用**固定夹具数据** offscreen 批量渲染（不跑实网，本机代理不稳会截到错误页），**最终人工目检**（本机读图工具全不可用，三方实证）。测试侧只保证「生成不崩溃 + 尺寸非零」。能力清单 + 已知限制段零风险直接做 |
| A4 | 图标体系（Material/Fluent SVG 子集，随主题着色） | **延后 1.4.2** | 5/5 | 本机视觉验证能力为零，SVG 着色盲改无法兜底（gui-tester 实证）；且与 A2 主题耦合 + 会 churn 图标断言基线（双重不可验证），合并 1.4.2 一起做更稳（core-tester） |

### A 方逐条表态

**search-fixer**：A1 纳入（时序：代码冻结后写，t22 改的三处界面状态最容易写错）；A2 纳入（styles.py:132/224 token 体系复用，每批改动即跑几何断言）；A3 改进后纳入（截图固定夹具 + 用户肉眼过一遍）；A4 延后（盲改 + 基线重写双重不可验证）。

**core-tester**：A1 纳入（core 零侵入）；A2 纳入附测试约束（字号/行高/间距影响 t13 u9 行高保底与 test_gui_sweep 像素基准，实施时必须重跑 test_gui_sweep + test_gui_offline）；A3 改进后纳入**标记争议**（offscreen 能渲染但无法程序化目视验证，只能人工兜底，写入已知限制段）；A4 延后（与 A2 主题耦合，合并更稳）。

**gui-tester**：A1 纳入（测试侧断言帮助入口存在性 + 随包文件可打开）；A2 纳入（逐条配几何量化回归，复用 t25 A-U9 模式 + 主题切换/高 DPI 两项）；A3 改进后纳入（badge SVG 零验证成本；截图只保证生成冒烟）；A4 延后（本机视觉验证能力为零，盲改引入测不出的回归）。

**recorder**：A1 纳入（我接 docs/manual/ Markdown 源，九章对齐 plan，版本与 changelog 互链；须列入回归范围）；A2 纳入（每条 P1-P5 配一个几何断言用例）；A3 改进后纳入（badge shields.io 静态 SVG；截图 QPixmap 程序化出图 + 标注"需人工目检"，由 captain 或 gui-tester 目检后入库，不入版本管理噪声）；A4 延后。

**installer-fixer（主持）**：A1 纳入（打包侧接 PDF+HTML 随安装包 + 程序内"帮助"入口）；A2 纳入（纯 QSS 零依赖）；A3 改进后纳入（本机读图工具不可用，badge 用 SVG 代码生成，截图留人工）；A4 延后 1.4.2（无法视觉验证 SVG 着色，盲改风险高）。

---

## 二、主题 B：性能（用户明确要求）

| # | 功能 | 裁决 | 票数 | 关键依据 / 硬约束 |
|---|---|---|---|---|
| B1 | 详情页磁盘缓存（TTL + time_updated 双失效；接入点 detail_dialog.py:373 / workshop_tab.py:1085） | **纳入 P0** | 5/5 | 用户明确要求"回退不重新加载 + **缓存及时清除**"——"及时清除"是硬约束。三条：① **深拷贝纪律延伸到磁盘层**（用户级硬规则：WorkshopItem 可变，enrich 就地改列表，反序列化进上层前必须深拷贝，core-tester t26 验证过 browse() 已做）② TTL（建议默认 24h）+ time_updated 双失效**都要可配置**，time_updated 变化立即丢弃（否则用户拿过期 mod 比无缓存更糟）③ **损坏容忍**：JSON 解析失败当 miss 走网络，不许崩（杀软/用户手改可能损坏文件）。手动刷新强制 bypass 缓存（search-fixer） |
| B2 | 预取下一页入 `_page_cache`（复用 `_priority_pending` 礼让） | **纳入 P0** | 5/5 | 速度报告 S2。三条：① 预取**必须复用 GameSearchClient 熔断退避**（ConnectionError/连续失败 → 冷却 15s），否则网络已断时预取线程空打占 CPU（search-fixer）；② 预取命中返回路径与 browse() **共用同一份深拷贝**，不开未防护新路径（core-tester）；③ 预取结果不得覆盖当前页——代际丢弃机制（gui-tester t25 A-U5 已验证，照搬） |
| B3 | 剪贴板监听工坊链接一键入队（`QClipboard.dataChanged` + `resolve_any_url`） | **纳入 P0**（含 B5 批量粘贴并入） | 5/5 | 速度报告 B1。三条改进：① **去重 + 静默失败**——dataChanged 会重复触发，按已解析 item id 对当前队列去重，resolve 失败（非工坊链接）静默不弹模态（search-fixer）；② 只在"工坊链接匹配"时触发，**不记录/不缓存剪贴板任何内容**（recorder 防御性设计）；③ 入队走现有 DownloadManager 队列路径复用去重/状态机，不新增队列概念（core-tester）。默认开 + 设置开关。**B5 批量粘贴导入并入本项**（主持方裁决，见第五节）。⚠️ 测试限制：offscreen 平台 dataChanged 可能不触发，托盘态行为需人工确认（core-tester） |
| — | enrich 并发 + AIMD 限流（S4-B） | **本期不做** | 5/5 | 唯一 429 风险项，待边界实测后另排，不列入 1.4.1 |

### B 方逐条表态

**search-fixer**：B1 纳入 P0（深拷贝纪律写进实现验收；"及时清除"是用户原话硬约束，双失效 + 手动刷新 bypass；损坏容忍）；B2 纳入 P0（预取复用熔断退避防空打，t15 礼让机制不动）；B3 纳入 P0（去重 + 静默失败，只对工坊链接匹配触发）。

**core-tester**：B1 纳入 P0 附两条硬约束（深拷贝延伸磁盘层——磁盘层是新入口同样规则；双失效都可配置 + time_updated 变化立即丢弃）；B2 纳入 P0（礼让三态语义 t26 验证过；命中路径共用深拷贝）；B3 纳入 P0（入队走现有队列路径零状态机改动；⚠️ offscreen dataChanged 可能不触发，托盘态需人工确认）。

**gui-tester**：B1 纳入 P0（测试三条：TTL 到期失效 / time_updated 变化失效 / 手动清除立即生效；深拷贝纪律沿用，命中用「_community_get 零调用计数」断言，复用 t25 A-U12 模式）；B2 纳入 P0（礼让 + 代际丢弃，照搬 t25 A-U5）；B3 纳入 P0（dataChanged → resolve → 入队提示链路 + 开关关闭零触发；**建议 B5 批量粘贴并入**）。

**recorder**：B1 纳入 P0（TTL 默认 24h + time_updated 双条件，TTL 进设置页可配；必须带深拷贝纪律）；B2 纳入 P0（用户点击槽位永远优先，被礼让时静默丢弃不报错，t15 语义不变）；B3 纳入 P0（不记录/不缓存剪贴板任何内容；同一链接去重防重复弹窗）。

**installer-fixer（主持）**：B1 纳入 P0（"及时清除"硬约束，TTL + time_updated 双失效必须可配置）；B2 纳入 P0（复用 _priority_pending 礼让）；B3 纳入 P0（复用 resolve_any_url，默认开 + 设置开关，B5 并入）。

---

## 三、主题 C：功能

| # | 功能 | 裁决 | 票数 | 关键依据 / 硬约束 |
|---|---|---|---|---|
| C1 | mod 库更新检查（time_updated 比对，手动按钮版） | **纳入** | 5/5 | 竞品最高性价比，三零件已齐备（steam_api.py:417 get_file_details 50 条/批 / mod_library time_updated 字段 / downloader 快照写入）。三条：① **必须 bypass api_cache**（否则比旧快照，是静默失效——plan 已列，gui-tester 强调）；② **大库进度反馈**（500 条 = 10 批，须有进度态不能假死，search-fixer）；③ 首版只标红/角标 + 一键入队，不做自动重下。批 50 条/批复用现有 `_throttle` 端点基准（`_ENDPOINT_INTERVALS` 加前缀，core-tester） |
| C2 | item 级失败原因枚举 + 受限物品清晰提示登录 | **纳入**（时序在 C5 后定稿） | 5/5 | issue #13474 公认痛点。⚠️ **误报红线（search-fixer + core-tester 一致）**：steamcmd "I/O Operation Failed" **不区分** entitlement / auth / Steam Guard / 限流——**不能把通用 I/O 失败映射成"需正版账号"**（会让用户误以为必须买游戏，误报比不报更伤）。保守分类：通用 I/O → "下载失败，steamcmd 未区分权限/网络/限流，建议重试"；只有**正向信号**（匿名 file_url 为空 + 已知受限 App 名单，或重试后仍同错且网络正常）才提示"可能需正版账号"。与熔断器**正交**（熔断管通道健康度、枚举管单物品可读结论）。受限提示文案须含登录引导且不误导。时序：steamcmd 错误串分类可与 C5 并行先行，受限提示文案在 C5 结论后定稿（core-tester/recorder） |
| C3 | 私人账户 provider（steamcmd `+login`，ProviderMeta `supports_account`，默认链不含） | **纳入** | 5/5 | 绕过报告**唯一合规方案**（🟢 用户自己账号下自己有权内容）。四条风控：① **账号不得进日志**——logger 捕获 steamcmd stderr 含账号名，必须显式过滤（search-fixer）；② **Steam Guard 首登流程**须给验证码输入入口并提示"仅需一次"（search-fixer）；③ 账号失败（密码错/Guard）与通道熔断**解耦**——账号配额问题不熔断 steamcmd 兜底（与 t28 terminal 豁免同理，core-tester）；④ 凭据本地存储与 api_key 同等对待（keyring 优先 + 本地混淆回退，目前 config 明文），UI 明示"账号仅本地存储、仅本人使用"（五方一致）。build_chain 断言默认链不含。测试侧查日志和导出包防泄漏（gui-tester）。changelog 须记清这是"公有账户池保留接口不启用"的合规分层落地（recorder） |
| C4 | 集合/批量下载（children 展开 + 队列分组语义） | **延后 1.4.2** | 5/5 | 中工作量 + 队列分组语义是状态机侵入；且依赖 C5 结论（若 GGNetwork 是服务端账号池，集合解析的合规定位会变，core-tester）。技术债提醒：steam_api.py:501 resolve_dependency_tree 的 BFS 队列实现，children 展开应**复用同一棵树遍历**，不要新写平行 walker（search-fixer） |
| C5 | GGNetwork 真下载补测（含后端登录态探测） | **纳入 · 最先执行** | 5/5 | 1.4.0 遗留 + t25 诚实披露的尾巴。关键未知 = 后端登录态：若能解析受限 App 物品 = **实质服务端账号池**（🟡→🔴 风险升级，须重新定位甚至移除该通道，且**反过来影响 C2 的"需正版账号"启发式判定**，core-tester）。测试设计（search-fixer 五条）：① 10-20 个已知受限 App 物品（DayZ 221100 / Barotrauma，bypass 报告点名）；② 探测固定 id 2537024972（GMod）要换掉，覆盖多 app；③ queue.position>0 **真实排队路径**（1.4.0 只做离线 mock）；④ 限速器在真实延迟下行为；⑤ **环境前提**：本机 fake-IP 代理做不了（1.4.0 实证），须派给干净网络一方或交用户跑；**若都不行 plan 必须写明 fallback**（保持实验性标注 + 不作为默认通道），否则 C5 卡死整条链。结论须标注时效（只对"本次环境 + 本次后端版本"成立，core-tester）。无论结论为何都要回填 1.4.0 诚实披露——"未实测"要么闭环要么升级为明确风险声明，不能悬置（recorder） |

### C 方逐条表态

**search-fixer**：C1 纳入（bypass api_cache / 大库进度态 / 首版不自动重下）；C2 纳入附**误报红线**（通用 I/O 不能映射"需正版账号"，只有正向信号才提示）；C3 纳入（账号不得进日志 / Steam Guard 首登入口 / UI 明示 + 默认链不含）；C4 延后（复用 resolve_dependency_tree，不新写平行 walker）；C5 纳入最先（五条测试设计 + 环境 fallback 前提，否则卡死整条链）。

**core-tester**：C1 纳入（比对结果入队走标准队列零状态机改动；批 50 条复用 `_ENDPOINT_INTERVALS`）；C2 纳入附诚实性约束（#13474 明确不区分原因，枚举不能假装精确，高置信度启发式 + "原因不明确详见日志"）；C3 纳入（账号失败与熔断解耦；凭据与 api_key 同等对待）；C4 延后（状态机侵入 + 依赖 C5 结论）；C5 纳入最先（网络稳定窗口实测 + 结论标注时效 + 反影响 C2 启发式，时序 C5 早于 C2 定稿符合）。

**gui-tester**：C1 纳入（测试三条：旧值无更新 / 新值标红 / **断言请求绕过 api_cache**）；C2 纳入（枚举与熔断正交，提示文案含登录引导不误导）；C3 纳入（默认链不含断言 + supports_account 标记 + **安全测试：凭据不得明文落日志、不得随导出包泄漏**）；C4 延后（1.4.1 已 9 项饱满）；C5 纳入最先（t25 留的尾巴，结论驱动后续时序必须先跑）。

**recorder**：C1 纳入（三零件齐备，首版纯手动按钮不做自动重下）；C2 纳入（时序接受 C5 之后，但 steamcmd 错误串分类可并行先行）；C3 纳入（强制要求 UI 明示 + changelog 记清是"公有账户池保留接口不启用"的合规分层落地，避免日后误读）；C4 延后；C5 纳入最先（🟡→🔴 升级时 UI 实验性标记重估 + changelog 改写 + 可能默认链移除；**无论结论何都要回填 1.4.0 诚实披露**）。

**installer-fixer（主持）**：C1 纳入；C2 纳入（误报红线与 C5 时序）；C3 纳入（唯一合规方案🟢，默认链不含，UI 明示本地存储）；C4 延后 1.4.2（依赖 C5 集合解析结论）；C5 纳入且最先（后端登录态是关键未知，结论驱动 GGNetwork 去留）。

---

## 四、时序与分期

**五方一致同意**（search-fixer 仅加一条：A1 手册排在代码冻结后，不与功能项并行开写）：

```
C5 最先（先决，结论驱动 GGNetwork 去留 + 反影响 C2/C4 定位）
  ↓
并行批：B1 / B2 / B3（含 B5 并入）/ A2（含 B6 空状态并入）/ C1 / C3
  ↓
收尾批：A1 手册（代码冻结后）+ C2（受限提示文案在 C5 结论后定稿）
  ↓
随时：A3（badge + 截图 + 能力清单）
  ↓
延后 1.4.2：A4 图标体系 / C4 集合批量下载 / S5 缩略图磁盘缓存
  ↓
技术债顺带（不占主位，见第五节裁决 2）
```

---

## 五、争议项与计划外提问（主持方裁决）

### 争议项（标记，未强行一致）

| 争议 | 内容 | 处置 |
|---|---|---|
| A3 截图验证 | offscreen 能批量渲染 PNG，但本机读图工具全不可用（sharp ERR_DLOPEN_FAILED / modlens Gemini key invalid），**无法程序化目视验证**（core-tester 标记争议，三方实证） | 接受为**已知限制**：测试侧只保证"生成不崩溃 + 尺寸非零"，成图用固定夹具数据 + 最终人工目检（captain 或 gui-tester），写入 README 已知限制段。非阻塞 |
| B3 托盘态测试 | QClipboard.dataChanged 在 offscreen 平台可能不触发，托盘态行为需人工确认（core-tester） | 接受为**测试限制说明**，写入文档。非阻塞 |

### 计划外提问 · 主持方裁决

**提问 1（search-fixer + gui-tester）：速度报告 P1/P2 项为何没进 12 项清单？**

- **S5 缩略图磁盘缓存（报告 P1）→ 延后 1.4.2。** 理由：1.4.1 纳入 10 项已饱满；B1 磁盘层基础设施先行，S5 可复用同套 URL hash 文件缓存机制（1.4.2 并入成本极低）。**plan_1.4.1.md 须补写延后理由**（gui-tester 要求"不能沉默，否则下轮评审重新争议"）
- **B5 批量粘贴导入（报告 P1）→ 并入 B3。** gui-tester 与 search-fixer 均建议：同一 `resolve_any_url` 入口、同一粘贴框，是 B3 的手动版，成本几乎为零且体感连续。**B3 裁决改为"纳入（含批量粘贴框）"**，不单列
- **B3 便携 zip / B4 开机自启（报告 P2）→ 本期不做，显式补入不做清单。** 12 项饱满，速度报告自身也只标 P2

**提问 2（search-fixer）：1.4.0 changelog 第十节遗留与 12 项重叠如何折叠？**

主持方裁决：**折叠进 1.4.1，作技术债小节，不占 12 项主位**——

| 1.4.0 遗留项 | 1.4.1 处置 |
|---|---|
| ggnetwork 探测动态化（固定 id 2537024972） | **并入 C5**（同源，补测时一并换掉固定 id，search-fixer 测试设计②已覆盖） |
| cdn_downloader.py 门面移除 | **收进 1.4.1**（t28 已标注"1.4.1 移除"，含 3 测试 import 迁移，installer-fixer 接） |
| list_channels 显示"未配置"状态 | 收进 1.4.1 技术债（与 A2 同批，展示层小改） |
| 搜索冷却结束自动重发待选词 | 收进 1.4.1 技术债（gui-tester 非阻塞建议，与 B3 入队链路同批） |
| test_legacy_format + test_page_parser 夹具修复 | 收进 1.4.1 技术债（既有非回归，修夹具使基线转 PASS） |

---

## 六、五方表态汇总

| 成员 | A1 | A2 | A3 | A4 | B1 | B2 | B3 | C1 | C2 | C3 | C4 | C5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| search-fixer | 纳入 | 纳入 | 改进 | 延后 | P0 | P0 | P0 | 纳入 | 纳入 | 纳入 | 延后 | 最先 |
| core-tester | 纳入 | 纳入 | 改进⚠️ | 延后 | P0 | P0 | P0 | 纳入 | 纳入 | 纳入 | 延后 | 最先 |
| gui-tester | 纳入 | 纳入 | 改进 | 延后 | P0 | P0 | P0 | 纳入 | 纳入 | 纳入 | 延后 | 最先 |
| recorder | 纳入 | 纳入 | 改进 | 延后 | P0 | P0 | P0 | 纳入 | 纳入 | 纳入 | 延后 | 最先 |
| installer-fixer（主持） | 纳入 | 纳入 | 改进 | 延后 | P0 | P0 | P0 | 纳入 | 纳入 | 纳入 | 延后 | 最先 |

**零原则性反对项。** 唯二分歧点是 A3 截图验证与 B3 托盘态测试的"人工兜底"接受度——均作为已知限制记录，不阻塞交付。

---

## 七、决议总表

**纳入 1.4.1（10 项）**：
- **纯纳入**：A1 用户手册 · A2 QSS 美化 · C1 mod 库更新检查 · C3 私人账户 provider
- **纳入（含改进点/硬约束）**：A3 README 截图+badge（SVG 生成 + 人工目检）· B1 详情磁盘缓存（深拷贝 + 双失效可配 + 损坏容忍）· B2 预取下一页（熔断退避 + 共用深拷贝 + 代际丢弃）· B3 剪贴板入队（去重 + 静默失败 + 不记录剪贴板 + **B5 批量粘贴并入**）· C2 失败原因枚举（误报红线 + 时序在 C5 后定稿）
- **先决项**：C5 GGNetwork 真下载补测（最先执行，结论驱动去留）

**延后 1.4.2（3 项）**：A4 图标体系 · C4 集合批量下载（复用 resolve_dependency_tree）· S5 缩略图磁盘缓存（plan 须补写延后理由）

**砍掉（0 项）**：无。不做清单沿用 plan_1.4.1.md + 补充：公有账户池（保留接口不实现）· 🔴 注入类工具（DRM 绕过 = 违法红线，DMCA §1201 + SSA）· `swdm://` 协议注册（B3 覆盖 95%）· Nexus/ModDB/Paradox provider（解决不了工坊独占痛点）· ETag/304（实测不支持）· 标签页切换动画（违背精简）· S4-B enrich 并发（唯一 429 风险，待边界实测）· B3 便携 zip / B4 开机自启（P2，本期饱满）

**技术债顺带（不占主位）**：cdn_downloader.py 门面移除（installer-fixer）· list_channels 未配置态（与 A2 同批）· 搜索冷却自动重发（与 B3 同批）· legacy_format + page_parser 夹具修复 · ggnetwork 探测动态化（并入 C5）

**执行时序**：C5 最先 → B1/B2/B3(+B5) + A2(+B6) + C1 + C3 并行 → A1（代码冻结后）+ C2（C5 后定稿）收尾 → A3 随时 → A4/C4/S5 延后 1.4.2

---

## 八、对 t32+ 任务拆分的建议

供 captain 拆分开发任务，建议粒度：

| 建议任务 | 内容 | 建议归属 |
|---|---|---|
| C5 补测（最先） | 10-20 受限 App 物品实测 + 后端登录态探测 + 真实排队 + 限速器真实延迟；环境前提：干净网络或交用户，fallback = 保持实验性标注 | search-fixer / core-tester（网络允许时） |
| B1 详情磁盘缓存 | TTL+time_updated 双失效可配 + 深拷贝 + 损坏容忍；测试三条 | core-tester |
| B2 预取下一页 | 熔断退避 + 共用深拷贝 + 代际丢弃 | core-tester |
| B3 剪贴板 + B5 批量粘贴 | 去重 + 静默失败 + 不记录剪贴板 + 设置开关 + 粘贴框 | search-fixer |
| A2 QSS P1-P5 | 纯 QSS + 每批跑几何断言 + B6 空状态并入 | gui-tester / search-fixer |
| C1 mod 库更新检查 | bypass api_cache + 进度态 + 节流基准前缀 | core-tester |
| C3 私人账户 provider | +login + supports_account + 日志过滤 + Guard 首登 + keyring | search-fixer |
| C2 失败原因枚举 | 误报红线 + 正向信号启发式 + 文案（C5 后定稿） | search-fixer |
| A1 用户手册（代码冻结后） | 9 章 Markdown + PDF/HTML 构建 + 帮助入口 | recorder + installer-fixer（打包） |
| A3 README（随时） | badge SVG + 夹具截图 + 能力清单 + 已知限制 | installer-fixer + recorder |
| 技术债 | 门面移除 / list_channels 未配置态 / 冷却自动重发 / 夹具修复 | 随各批次 |
