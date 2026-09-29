# 竞品研究报告（1.4.1 规划输入）

> 2026-09-29 · 三家同类工具调研：King-zzk/Steam-Workshops-Tools-SWTools、Official-Husko/Husko-s-SteamWorkshop-Downloader、UrekD/Steam-Workshop-Monitor
> 方法：GitHub API + raw 源码精读 + README 写作分析

## 一、三家概览

| | SWTools (King-zzk) | Husko (Official-Husko) | Monitor (UrekD) |
|---|---|---|---|
| 定位 | WPF 桌面下载器（输入 ID 下载） | CLI 下载脚本 | Discord 通知 bot（**只监控不下载**） |
| 语言 | C# / .NET 10 WPF | Python 单文件 594 行 | Python 单文件 ~900 行 |
| star / fork | 248 / 13 | 84 / 10 | 25 / 8 |
| **状态** | **已归档**（2026-07） | **已归档 3 年**（2022-09） | **已归档**（2024-03） |
| 累计下载 | 24,471（26 个 Release） | 5 个 Release | — |
| 许可 | GPL-2.0 | 非标准（NOASSERTION） | GPL-3.0 |

**三家归档的原因各异，但都指向"路线不可持续"**：
- **SWTools**：靠**明文共享 Steam 账户池**（仓库托管 7 个账户密码，捐赠+邀请码维持）覆盖需正版 App → 被 Steam 封号停更
- **Husko**：下载链**完全外包给单一第三方后端** steamworkshopdownloader.io → 后端关停，工具直接死亡
- **Monitor**：Discord 机器人审核被拒 → 作者停更

**对 SWDM 的核心启示**：匿名访问 + provider 链式回退（GGNetwork → CDN → steamcmd 兜底）+ 熔断器的路线，在合规性与抗单点故障上明显优于以上三种模式。**这是 1.4.0 架构价值的 externally 验证。**

## 二、实现机制对比

| | SWTools | Husko | Monitor | SWDM（对照） |
|---|---|---|---|---|
| 下载机制 | file_url 直链 → 托管账户 steamcmd → anonymous steamcmd | 第三方后端 API 全包（已死） | **无下载能力** | provider 链：GGNetwork→CDN→steamcmd 兜底 |
| 匿名策略 | 共享账户池（违规） | 公共代理池 + 44 个 UA 随机 | 匿名调 ISteamRemoteStorage | 请求头治理（Accept-Language）+ provider 回退 |
| 工坊浏览 | **无**（只能输 ID） | 无 | 无 | ✅ 分类/搜索/排序/翻页 |
| mod 库管理 | 无 | 无 | 无 | ✅ 分类/导入导出/冲突检测 |
| 队列管理 | 串行队列 | 单线程写死 | — | ✅ 串行化 + 批量按钮 + 重试 |
| 更新监控 | 无 | 无 | ✅ time_updated 比对 | ❌ **缺失** |
| 集合下载 | 无 | ✅ children 展开 | 部分（未完成） | ❌ 缺失 |
| 测试/工程 | 少量 | **零测试、裸 except** | 无 | ✅ 61 脚本 / 双轮复测闸门 |

**SWDM 的独家优势**：工坊浏览搜索、mod 库管理、依赖下载、冲突检测、mod 包导入导出——三家全都没有。SWDM 是同类中唯一"浏览+下载+管理"一体的匿名工具。

## 三、可迁移建议（按优先级）

### 高优先级 · 纳入 1.4.1

**1. mod 库更新检查（手动按钮版）** — 来自 Monitor，**投入产出比最高**
- Monitor 的核心范式：匿名批量调 `ISteamRemoteStorage/GetPublishedFileDetails/v1` 取 `time_updated`，与库内旧值比对，变化即通知
- **SWDM 零件已齐备，只差调度层**：`steam_api.py:417 get_file_details()` 批量封装已就绪；`mod_library` 表已有 `time_updated` 字段（mod_library.py:45）；下载完成时 downloader.py:805 已写入快照
- 落地：mod 库标签页加"检查更新"按钮 → 批量比对 → 有更新的条目标红/角标 → 一键加入下载队列（复用现有队列路径，零状态机改动）
- 侵入点注意：① 监控请求须绕过 api_cache（否则比的是旧快照）；② `_throttle` 需为 `/ISteamRemoteStorage/` 补节流基准；③ 首版不做自动重下，只做一键入队
- 工作量：小（<1 天）。三原则：真需求——库里有几十上百条 mod，用户无法肉眼逐条比对版本
- 定时自动检查 + 托盘通知 → 长远路线图（需先观察 Steam 对该端点的轮询容忍度/429 频次）

**2. README 截图/GIF 直出** — 三家共识，GUI 工具转化率硬伤
- SWTools 最大的 README 缺陷正是无截图；Husko 只靠一张 GIF；Monitor 截图直出
- SWDM 五标签页（工坊浏览/下载队列/mod 库/设置/调试）各放一张截图，offscreen 渲染能力可批量出图
- 工作量：小—中（1 天）。零代码侵入

**3. README badge 墙** — 来自 SWTools（11 个 shields badge）
- license / 最新版本 / Release 下载量 / Python 3.12 / PySide6 / last-commit / issues
- SWDM 已有 14 个 Release，badge 有数据源。工作量：<0.5 天

**4. "支持的能力/通道"清单段** — 来自 SWTools 的游戏清单
- SWDM 应明示：全 App 匿名支持 + provider 链覆盖（GGNetwork 标"实验性"、CDN/steamcmd 标实测状态），把已知限制单列
- 比 SWTools 的账户驱动清单更有说服力。工作量：小（0.5 天）

**5. README 已知限制/状态透明段** — 来自 Husko + Monitor
- 1.4.0 changelog 已有内容（GGNetwork 实网未实测、默认链路不经该通道、读图工具限制），抽到 README
- Monitor 的 Personal note 式坦诚反而建立可信度。工作量：<2 小时

**6. 发布流程清单 release-steps.md** — 来自 SWTools
- 版本号双端一致检查（paths.py:9 + swdm.iss:14）→ 打包 → tag → Release 上传，与"迭代交付四要素"用户规则天然契合
- 工作量：小（0.5 天）

### 中优先级 · 纳入 1.4.1+（"下载可靠性"主题）

**7. 下载完成字节数校验** — 来自 SWTools CheckBytes
- workshop API 的 `file_size` 已在 enrich 数据里；下完后比对 `os.path.getsize`。steamcmd 通道另有 manifest 交叉验证
- 侵入点：provider 层之上、队列状态机判 done 之前。**关键：校验失败不得直接判失败**（SWTools 的 LockingFailed 误判教训），应标记警告 + 允许重试
- 工作量：中（1—2 天）

**8. item 级失败原因枚举 + 可读提示** — 来自 SWTools EFailReason
- 分类：网络不可达 / 通道熔断 / 物品不存在或已删 / 需正版账号 / 磁盘不足 / 校验未通过
- 与熔断器正交：熔断管通道健康度，枚举管单物品的可读结论
- 工作量：中（1—3 天，跨 core+GUI+测试）

**9. 集合下载 + 批量下载** — 来自 Husko
- 匿名解析集合 children → 展开为子任务入队（组内串行、失败隔离），下载复用现有 provider 链，无需新端点
- 侵入点：队列状态机需从"单物品状态"扩展"组概念"
- 工作量：中（1—3 天）

### 低优先级 / 长远路线图

**10. AppID 新手引导**（Husko）：README 放"如何找到 AppID"小节（store 链接 → AppID），SWDM 的 storesearch 端点可佐证。纯文档，小
**11. 自动更新检查**（Husko/SWTools）：启动时查 GitHub Releases 比对版本 → 提示跳转 Release 页。设置页开关默认关。低于功能迭代优先级
**12. issue 模板分流**（Husko）：bug_report / feature_request / game-support-request。等仓库 issue 量起来再补，当前可能空转
**13. 第三方库声明 THIRD-PARTY-NOTICE.md**（SWTools）：**被许可证决策阻塞**，需先确定 SWDM 开源许可证（PySide6 LGPL/GPL、requests Apache-2.0 兼容性表述）

### 明确不采纳

| 建议 | 来源 | 不采纳理由 |
|---|---|---|
| ~~共享 Steam 账户池（永不纳入）~~ → **已按用户决策修订，见下** | SWTools | 明文共享账户直接导致 SWTools 被封号停更——风险已实证；但用户指出"大部分来找本工具的人就是为了无法匿名下载的游戏 mod"，故**保留接口、当前不启用** |

### 【用户决策修订 2026-09-29】公有账户池：保留接口，暂不启用

用户原话："建议还是要留下公有账户池的接口，毕竟大部分来找这个工具的人都是为了这种无法匿名下载的游戏 mod 来的，这个接口可以先放着，等到 steam 放开限制再做进一步研究。"

据此将"共享账户池"从"永不纳入"调整为**保留接口、当前不启用**：

- **风险分层**：
  - **私人账户接口**（用户自己的 Steam 账户填入设置，steamcmd `+login` 自带能力）：低风险、用户自担，属 provider 链的自然扩展点
  - **公有账户池**（仓库/服务端托管公共账户供多人使用）：高风险，SWTools 正因此被封号停更——**仅留接口，不实现池**
- **落地点**：provider 抽象层天然支持——steamcmd provider 的 ProviderMeta 增加 `supports_account` 标记，registry 支持注册"账户版 steamcmd provider"但**默认链不含它**；池源管理/配额/轮换不在任何近期版本实现
- **触发条件**：待 Steam 对匿名下载的限制放开后，重新评估池源的合规与可持续方案
| 公共代理池 + UA 随机 | Husko | 公开代理列表质量差、延迟不可控、中间人风险；SWDM 的请求头治理 + provider 回退是更稳的方向；crack/piracy 色彩不利于合规定位 |
| Discord RPC | Husko | 工具属性软件晒下载状态是伪需求，且引入依赖与崩溃面（Husko 为此单独修过崩溃） |
| 游戏特化安装路径 | Husko | 5 个 if-elif 硬编码 + 裸 except 不可维护；SWDM 的 mod 库 + 用户配置目录已更通用 |
| SVG 状态徽章 / 多租户配额 | Monitor | Discord bot 运营场景特有，单机桌面应用无对应场景 |

## 四、三家 README 写作对比

| | SWTools | Husko | Monitor |
|---|---|---|---|
| 结构 | badge 墙 → 定位 → 使用指南 → 游戏清单 → 声明 → 许可 → Star History | 停更声明 → 简介 → GIF → AppID 教程 → Features → Known/Planned → Disclaimer | 归档声明 → How it works → 截图 → docker-compose → Personal note |
| 亮点呈现 | 游戏清单承载 | **一张 GIF** | **截图直出（斜杠命令 + 通知消息）** |
| 最大短板 | **无截图**（GUI 工具致命） | 无 badge/目录/安装/配置/许可 | 太简略 |
| 最值得学 | badge 墙、维护文档体系（CONTRIBUTING/DEVELOPMENT/release-steps/用户手册随包分发） | 删除线管理 Known/Planned（进度透明）、顶部醒目状态声明 | Personal note 式坦诚、docker-compose 式可直接复制的部署示例 |

**SWDM README 现状**：中英双语 + 语言切换 + 架构树 + 多通道链章节（t29 产出）。**缺**：截图/GIF、badge 墙、能力清单、已知限制段、AppID 新手引导。

## 五、1.4.1 规划建议

基于以上，1.4.1 建议分两个主题：

**主题 A：文档与可读性（与 t30 注释适配同批）**
- README 截图直出（5 标签页）+ badge 墙 + 能力清单 + 已知限制段 + AppID 引导
- 发布流程清单 release-steps.md

**主题 B：功能（按性价比排序）**
1. mod 库更新检查（手动按钮版）— 零件齐备只差调度，<1 天
2. 字节数校验 + item 级失败原因枚举 — "下载可靠性"主题，中工作量
3. 集合下载 + 批量下载 — 队列分组语义，中工作量

**GGNetwork 真下载补测**（1.4.0 已知限制）应优先于主题 B 的 2/3——先补测确认试点通道真的能用，再围绕它扩展功能。

---

数据来源：GitHub API（仓库元信息 / git trees / releases）、raw.githubusercontent.com 精读源码（SWTools: Item.Core.cs / AccountManager.cs / Steamcmd.cs / API/*.cs；Husko: bot.py 全文；Monitor: WorkshopMonitor.py 全文 + db.sql）、各 README 全文。
