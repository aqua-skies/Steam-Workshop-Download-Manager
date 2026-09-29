# SWDM Git 工作流规范

> 维护人：recorder（仓库管理员）· 制定于 t29 · 2026-09-29
> 仓库：aqua-skies/Steam-Workshop-Download-Manager（公开，main 单线）

## 一、提交信息格式

格式：`类型(范围): 摘要`，正文换行后**必填关联任务编号**（tXX）。

### 类型

| 类型 | 用途 |
|---|---|
| `feat` | 新功能（新通道、新页面、新能力） |
| `fix` | bug 修复 |
| `refactor` | 重构（行为不变，如链式回退改造） |
| `perf` | 性能优化（如详情页节流优先级） |
| `docs` | 文档（changelog、评审记录、本文件） |
| `test` | 新增/修复测试 |
| `chore` | 打包配置、版本号、清理 |
| `revert` | 回滚 |

### 范围（scope）

用模块名：`downloader` / `providers` / `steamcmd` / `gui` / `library` / `search` / `installer` / `docs` 等。

### 示例

```
fix(downloader): 修复取消与自动重试的微秒竞态窗口

t22 A-P1：_cancelling 集合同锁内先 add 再 set，_exec_job 入链前早退，
终态判定块与 cancel() 全程互斥串行。验证 test_ap1_cancel_race 16 项。
```

```
feat(providers): 新增 GGNetwork 匿名通道试点

t21：令牌桶 20/min + 突发 3，zip 解压，GMAD 弱校验 >1% 回退（t28 升级）。
test_providers 84 项 ALL PASS。
```

### 硬性要求

- **每个 commit 必须能追溯到任务编号**（AgentTeams 任务 tXX）。一个任务可拆多个 commit，但一个 commit 不得跨多个无关任务——拆成多个 commit。
- 摘要行 ≤72 字符（中文按 2 字符宽计），祈使句，句末不加句号。
- 正文写**改了什么 + 为什么 + 验证**（测试数字/回归结论），不写实现细节流水账。
- changelog 与 commit 互为佐证：changelog 记用户视角的变更，commit 记工程视角的改动。

## 二、分支模型

- **main 单线**。不建功能分支（五人小团队 + 单仓库，并行冲突由讨论组+任务依赖规避）。
- **每次交付后打 tag**：`v1.3.8` / `v1.3.9` 已过，下一个 `v1.4.0` 由交付评审（t27）通过后打。
- tag 由 captain 在推送时一并打；recorder 只准备本地 tag 不推送（见三）。

## 三、推送分工（硬性纪律）

- **recorder 负责**：`git add` / `git commit`（本地）。
- **captain 负责**：`git push`（含 tag）。**token 只在 captain 处。**
- recorder **不得**向任何成员索要 token，**不得**把 token 写入任何文件、任务描述、日志或聊天消息。
- 完成 commit 后，recorder 向 captain 发消息附**变更摘要**（改了哪些文件、为什么），captain 推送。
- 推送通道（captain 实测）：`git push -c http.sslBackend=schannel -c http.proxy=http://127.0.0.1:7897 <url> main`。

## 四、.gitignore 维护

已忽略：`build/`、`dist/`、`installer/Output/`、`__pycache__/`、`*.log`、`tests/shots/`、`.agent-teams/`、`.dsh-memory/`。

规则：
- 成员产出**新类型产物**（新目录/新文件模式）时，recorder 及时补 `.gitignore` 规则。
- 临时调试脚本、转储文件、抓取快照（如 `research/_browse_*.html`、`tests/_*.txt`）不入库——用后即删或保持忽略。
- **不得提交**：任何含密钥/token/密码的文件；构建产物；`.agent-teams/` 团队状态（内部协调数据）。

## 五、注释与文档语言规范（中英文适配政策）

用户要求"中文和英文的适配都搞一下，包括仓库的"。政策：

### 5.1 语言分工

| 场景 | 语言 | 理由 |
|------|------|------|
| 模块级 docstring | **英文为主**，关键业务术语附中文括注（如 `Steam Workshop (工坊)`、`前置依赖`） | 面向公开仓库的外部读者；中文术语保留可检索性 |
| 公共 API（非 `_` 前缀的类/函数）docstring | **英文**，含 Args/Returns/Raises 语义；中文术语括注仅限 Steam 专有概念 | 公开契约，供 IDE 与外部读者 |
| 私有成员（`_` 前缀）docstring | 中文或英文均可，随模块 | 只面向维护者 |
| 行内注释 | **中文为主**；纯算法/协议推导可用英文 | 面向项目维护者，中文表达最精确 |
| changelog / 评审文档 / 工程日志 / 讨论组纪要 | **中文** | 面向用户与团队，中文表达更精确 |
| commit 信息 | 中文摘要 + 英文术语（模块名/类名/文件名用英文原样） | 团队沟通 + 自动化可读 |
| README | 双语：`README.md`（中文主）+ `README.en.md`（英文），顶部互相链接，内容同步 | 公开仓库门面 |
| 关键架构文档（如 `provider_architecture_1.4.0.md`） | 中文主体 + 顶部英文摘要段 | 外部读者快速定位，细节仍用中文 |
| GUI 界面文案 | **中文，不做 i18n** | 更大的产品决策，属后续迭代 |

### 5.2 docstring 内容要求（写法示范）

- **模块级**：一句话说职责 + 2-6 条设计要点/真实锚点/实测结论。不要复述文件名。
- **公共类**：一句话说它代表什么 + 关键不变式或并发约定。
- **公共函数**：一句话说做什么 + 参数/返回值/异常（能从签名看出的不重复罗列）。
- **禁止**：写 `"""pass"""` 之类无信息 docstring；把实现细节写进公共 API 契约（那应放在私有注释里）。
- 准确性优先：拿不准的实现细节找该模块作者（t1-t28 对应成员）确认，不猜。

### 5.3 t30 落地范围（1.4.1 首项）

- `swdm/` 下 40 个 `.py`：模块级 docstring 全部英化完成；30 处缺失的公共 API docstring 补齐。
- 只加注释/docstring，**不改任何可执行逻辑**；如发现必须改的代码问题，报告 captain 建任务，不顺手改。
- 每完善完一批模块跑相关测试确认零回归（本机须带 `PYTHONUTF8=1`，否则 ⚠/✓ 字符在 GBK 控制台 print 会假崩）。

## 六、提交节奏

- 每收到成员改动通知，**30 分钟内**规范 commit 并消息通知 captain 推送。
- 打包任务（如 t24）的 commit 单独成笔，含版本号变更（`paths.py` + `swdm.iss`）与安装包验证结论。
- 交付评审通过后，changelog 回填评审小节 + 打 tag，一次 commit 完成。
