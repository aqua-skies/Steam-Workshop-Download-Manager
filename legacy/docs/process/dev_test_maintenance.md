# SWDM 开发 / 测试 / 维护全流程（继任者接手文档）

> 面向：继任者 AI（新会话、零上下文）。目标：**读了就能跑**——按本文档可以从需求一路跑到交付。
> 维护人：process-doc（swdm-142 t5）· 2026-10-01
> 上游情报：`docs/engineering_log.md`（1.3.8-1.3.9 完整任务流水）· `docs/changelog_1.4.0.md`~`docs/changelog_1.4.1.md` · `docs/git_workflow.md` · `docs/research/*`
> 本文件与 `docs/process/team_organization.md`（组织规矩）、`docs/process/user_interaction_scenarios.md`（用户侧场景剧本）互为姊妹篇。

---

## 〇、三分钟速览（先跑通这一节）

```powershell
cd "C:\Users\Lenovo\Desktop\程序设计\steam mod program"

# 1. 跑单个脚本式测试（任何测试都必须带这两个环境变量）
$env:PYTHONUTF8 = "1"; $env:QT_QPA_PLATFORM = "offscreen"
python tests\test_user_interaction.py        # 看 stdout 最后一行 RESULT: ALL PASS

# 2. 跑全量离线回归（~64 脚本，串行，10-30 分钟）
powershell -File tests\run_all.ps1           # 输出 tests\_run_all_*.log 风格的逐行 PASS/FAIL + SUMMARY

# 3. 构建（双端版本号先核对：swdm\core\paths.py:13 + installer\swdm.iss:14）
python -m PyInstaller swdm.spec --noconfirm --workpath build --distpath build\dist
& "C:\Users\Lenovo\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\swdm.iss
# 产物：installer\Output\SWDM-Setup-x.y.z.exe（~45MB）

# 4. 冒烟（从工作区 exe 沙箱陷阱开始——见 §四.4）
copy "build\dist\SWDM\SWDM.exe" "$env:TEMP\smoke-SWDM.exe"
& "$env:TEMP\smoke-SWDM.exe"                 # 窗口标题应为「Steam 工坊下载管理器 v<x.y.z>」，8-10 秒稳定不退出
```

**判定的唯一口径**：脚本式测试以 stdout 的 `RESULT:` 行为准（`ALL PASS` / `PASS`），进程退出码不可信（见 §四.3）。

---

## 一、迭代全流程（八阶段）

用户 2026-09-28 规定的**交付四要素**贯穿全程，缺一不可：

1. **全量回归**：迭代完成后必须全量回归测试所有功能（含新增）及功能之间的关联交互，**不得只测改动点**。
2. **讨论组**：必须开讨论组按三原则（**精简 · 以用户体感为中心 · 保证基本功能正常运行**）评审功能删减/改进/添加的可行性。
3. **版本号**：每次迭代必须升级版本号并保留清晰可追溯的变更记录。
4. **双闸门**：最终交付需讨论组一致认为可交付，**且 bug 测试员连续两轮复测均无异常**。

历史闭环范例：1.3.8（t1-t10）· 1.3.9（t11-t20）· 1.4.0（t21-t28）· 1.4.1（t31-t48）。

### 阶段 1：需求输入

- 来源：用户直接报告的 bug（如 1.3.9 的 U1-U12、1.4.2 的用户交互层 4 bug）；只读调研报告（`docs/research/*`、`docs/competitor_research_*.md`、`docs/ux_audit_*.md`、`docs/core_audit_*.md`）；上版评审遗留项（`docs/feature_review_*.md` 的「延后」节）。
- 调研纪律（用户级规则）：主动调研同类竞品，不等用户点名；每次迭代规划时检查是否该做新一轮竞品调研。**复用已存在的调研 subagent**（`list_agents` 先过一遍，inactive 的可 `send_message` 唤醒追问，勿新开重复读源码）。

### 阶段 2：规划与分派

- 产出 `docs/plan_<版本>_draft.md` → 讨论组裁决 → `docs/plan_<版本>.md`（去 draft）→ captain 拆任务。
- 每个任务必须写清：目标、 inFile 行号锚点、约束（不碰什么）、验证命令、依赖。任务规模控制在 1-4 小时（SPOQ 实践，见 `team_organization.md` §三）。
- 分派按成员专精（m1-m7 域），写域分离（同文件串行，见 `team_organization.md` §六）。
- **依赖图**：任务间依赖在创建时声明（`dependencies: [tX, ...]`），调度器按 DAG 波次放行——无依赖的 Wave 0 并行，依赖上游的等其完成。

### 阶段 3：修复 / 实现

- 成员收到任务 → `agent_teams_claim_task` → in_progress → 干活（只能改自己任务 in-scope 的文件）→ 自测（每小项配测试，脚本式 `check()` + `sys.exit`）→ `agent_teams_update_task(status=completed)` → `agent_teams_send_message(to=captain)` 报告。
- **执行接地**（硬纪律）：任何代码改动必须通过沙盒执行（跑测试）才能视为完成——"我认为改对了"不算，`RESULT: ALL PASS` 才算。测试与代码同批产出。
- **用户可见功能必须同时交付 QTest 真按键交互测试**：直调 `setText` / 方法的 API 层断言不算数（1.4.1 的 86+111 项复测全是 API 层、用户上手撞 4 个交互 bug 的直接教训；1.4.2 `test_user_interaction.py` 真按键一跑就抓到 SIGSEGV）。
- **结构化开发纪律**（用户 2026-10-01 明定）：单模块行数上限约 **800 行**，超出必须拆分（现行反例：`workshop_tab.py` 1749 / `detail_dialog.py` 1222 / `downloader.py` 894，由 t3 架构契约列为 2.0 重构目标）；公共 API + docstring **契约先行**（先于实现写定）；修复发现结构性根因时**优先重做结构**，禁止在腐坏结构上堆补丁。
- **2.0 准备**：新增功能 / 修复须在代码注释标注「临时性 / 迁移友好」；核心逻辑文档化交给架构契约文档（t3，stab-fixer）。
- 环境陷阱见 §四；不改可执行逻辑的文档任务（如本任务）不受测试约束，但产出文件须可被引用核验。

### 阶段 4：讨论组（功能评审）

- 时机：与修复并行（不等修完），主持方由 captain 指派（如 1.3.8 t9 installer-fixer、1.4.0 t23、1.4.1 t31）。
- 方式：主持方向各专精成员发讨论邀请，成员逐条回复议题（A-Z），主持方汇总为 `docs/feature_review_<版本>.md`（结论速览表 + 逐条各方意见）。
- 裁决选项：纳入 / 延后 / 砍掉 / 改进后纳入；**零原则性反对方可过**。计划外提问由主持方当场裁决并写入正式 plan（"不能沉默，否则下轮评审重新争议"——t31 教训）。
- 讨论组发现的技术债（如 1.4.0 t23 评审中发现熔断器 inert）当场决议收或留，决议执行人明确到任务。

### 阶段 5：两轮连续复测（交付闸门之一）

- **开发者自测 ≠ 复测**：任务内 `check()` 是开发者自测；交付闸门要求**独立复测员**（不写产品代码，如 1.4.2 qa-indept / 历史 gui-tester+core-tester）做两轮视角互补的复测：
  - 第一轮：**GUI / 用户视角**（如 1.4.1 t44：56+30 项 + exe 冒烟 10s 存活；1.3.8 t6：48 脚本基线 + `test_cross_features.py` 26 项跨功能关联）。
  - 第二轮：**核心逻辑独立视角**（如 1.4.1 t45：111 项独立检查，**刻意不复用各功能任务的自测 mock**，用独立夹具重验）。
- 两轮都必须跑 `run_all.ps1` 全量回归，与上版基线**逐项核对**，口径：**零新增失败 + 既有非回归逐项核对**（实网测试在 FAIL/PASS 间漂移是环境问题，不是代码回归）。
- 复测产出 `docs/retest_round1_gui_<版本>.md` 与 `docs/retest_round2_core_<版本>.md`。

### 阶段 6：版本号

双端同步（漏一端即为发布阻塞——1.4.1 手册 E11 教训：三处链接指向不存在的文件）：

| 位置 | 行号 | 示例 |
|---|---|---|
| `swdm/core/paths.py` | `APP_VERSION` | `"1.4.2"` |
| `installer/swdm.iss` | `#define SWDMVersion` | `"1.4.2"`（AppVersion / VersionInfoVersion / OutputBaseFilename 一并联动） |
| `README.md` / `README.en.md` | 版本 badge | shields.io 静态 badge 同步 |
| 用户手册扉页 | `docs/manual/SWDM用户手册.md` | 版本声明（手册随包，见 §阶段 8） |

### 阶段 7：changelog

- `docs/changelog_<版本>.md`，结构沿用 1.4.1 十六节模板：英文摘要 → 版本概要 → 逐功能（任务号 + 责任人 + 文件:行号 + 验证数字）→ 版本号与构建 → **回归统计表**（轮次/脚本数/PASS/FAIL/NORESULT/FAIL 定性）→ 已知限制与下一步 → **交付评审小节**（四要素核对表 + 功能逐条过审表 + 六方投票表 + 闸门结论）。
- changelog 与 commit 互为佐证：changelog 记用户视角，commit 记工程视角（`git_workflow.md` §一）。
- 诚实披露原则：未验证的能力明说（如 GGNetwork 1.4.0 "从未实测"后被 t32 推翻并回填），已知限制单列一节。

### 阶段 8：打包与交付

```
1. 冲突检查：python -m compileall -q swdm tests tools（exit 0）
   + 新模块独立注册核对 + 共改文件交叉点核对（参照 changelog_1.4.1 §十四）
2. PyInstaller：python -m PyInstaller swdm.spec --noconfirm --workpath build --distpath build\dist
3. ISCC：& "C:\Users\Lenovo\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\swdm.iss
   （ISCC 不在 PATH，必须全路径）
4. 冒烟：copy build\dist\SWDM\SWDM.exe %TEMP%\smoke-SWDM.exe 后运行
   （直接跑工作区 exe 会被沙箱拦截——见 §四.4）
   窗口标题含正确版本号 + 进程 8-10 秒稳定存活
5. 评审：六方投票（主持 + captain + 打包 + GUI 复测 + 核心复测 + 文档），6/6 零反对
6. 收口：engineering_log 追加交付闸门链全记录 → captain git commit + tag vX.Y.Z + 推送
7. 交付时提醒用户人工目检 offscreen 截图（本机读图工具全失效，见 §四.7）
```

手册随包检查（1.4.1 教训）：`build\dist\SWDM\_internal\manual\SWDM-用户手册.html` 的 MD5 必须与 `docs/manual/dist/` 一致；F1 /「帮助 > 用户手册」可打开。

---

## 二、分支与提交规范

> 完整版见 `docs/git_workflow.md`（recorder 制定于 t29）。此处是继任者必读的最小子集。

- **main 单线**：不建功能分支（小团队 + 单仓库，并行冲突靠讨论组 + 任务依赖 + 写域分离规避）。
- **每次交付后打 tag**：`v1.3.8` … `v1.4.1` 已过，下一个由交付评审通过后由 captain 打。
- **commit 格式**：`类型(范围): 摘要`（≤72 字符，中文按 2 字符宽）+ 正文（改了什么 + 为什么 + 验证），**正文必填关联任务编号 tXX**。类型：feat / fix / refactor / perf / docs / test / chore / revert。范围：downloader / providers / steamcmd / gui / library / search / installer / docs 等。
- **一个 commit 不得跨多个无关任务**——拆成多个 commit；一个任务可拆多个 commit。
- **推送分工（硬性纪律）**：recorder（或当值文档成员）负责 `git add` / `git commit`；**captain 独占 `git push`（含 tag），token 只在 captain 处**。成员不得向任何人索要 token，不得把 token 写进任何文件 / 任务描述 / 日志 / 聊天。
- **推送通道（本机实测唯一成功组合）**：

  ```powershell
  git push -c http.sslBackend=schannel -c http.proxy=http://127.0.0.1:7897 <url> main
  ```

  本机系统代理 127.0.0.1:7897（Steam fake-IP 用）；openssl 直连在代理开启时 TLS 握手挂（`0A000126 unexpected eof`），必须 schannel + 代理。
- **.gitignore**：已忽略 `build/` `dist/` `installer/Output/` `__pycache__/` `*.log` `tests/shots/` `.agent-teams/` `.dsh-memory/` 等。成员产出新类型产物（新目录 / 新文件模式）时，当值文档成员及时补规则。**不得提交**：含密钥/token 的文件、构建产物、`.agent-teams/` 团队状态。
- **提交节奏**：收到成员改动通知后 30 分钟内规范 commit 并消息通知 captain 推送；打包任务 commit 单独成笔（含版本号变更与安装包验证结论）；交付评审通过后 changelog 回填评审小节 + 打 tag，一次 commit 完成。

---

## 三、测试体系（怎么写、怎么跑）

### 3.1 脚本式测试（项目主流形态）

所有 GUI/交互测试都是独立可执行脚本，头部固定套式（照抄 `tests/test_user_interaction.py`）：

```python
from __future__ import annotations
import os, sys, tempfile
_TMP = tempfile.mkdtemp(prefix="swdm_xxx_")
os.environ["APPDATA"] = _TMP                      # import swdm 前设，隔离配置/库 DB
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
_WINFONTS = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
if os.path.isdir(_WINFONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", _WINFONTS)   # 见 §四.1 字体陷阱
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ... 测试体 ...
def check(name, cond, e=""): ...                  # 计数 ok/failed
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)                          # 退出码仅礼貌，判定看 RESULT 行
```

- **API 测试 vs 用户交互测试**：直调 `setText` / 方法 = API 测试；`QTest.keyClicks` / `keyClick` / `QInputMethodEvent` 才算用户交互测试（`test_user_interaction.py` 头部公约）。
- 网络全部桩化（GameSearchClient / BrowseWorker 注入 fake），场景自闭合；实网测试单独隔离（见 §四.8）。

### 3.2 全量回归

```powershell
powershell -File tests\run_all.ps1
```

- 串行执行（**并发会制造 flaky 误报**——t4/t5 踩过，机器并发负载让 `test_throttle` 时限性失败）。
- `$skip` 列表跳过实网 / 压力 / 冒烟脚本（`test_acceptance` `test_smoke` `test_deps_live` `test_real_download` `test_stress` 等 21 个）；网络挂时它们会 hang/timeout，属环境问题。
- 判定：逐脚本抓 stdout 匹配 `RESULT:` 行；`ALL PASS` / `RESULT: PASS` 计 PASS，无 RESULT 行计 NORESULT。
- **run_all.ps1 必须保持 ASCII-only**（1.4.1 教训：UTF-8-no-BOM 中文注释被 powershell.exe 5.1 按 ANSI 错码页解析，会把最后一行注释并进 `$skip` 赋值，skip 列表静默失效，90 个脚本含挂死网络脚本全跑）。

### 3.3 回归口径（用户规则的具体化，t23 讨论组确认）

- 全量回归所有功能 **+ 功能间关联交互**（`test_cross_features.py` 26 项跨功能：搜索+标签叠加、翻页+排序联动、下载中切 Tab、closeEvent 三分判定）。
- 口径 = **零新增失败 + 既有非回归逐项核对**，不追绝对 PASS 数。
- 既有非回归登记表（逐版滚动维护）：1.4.1 时点为 `test_stress`（1_SLOW 性能标记，环境性）+ `test_game_dir_e2e`（真实 e2e 下载 SUCCESS，FAIL 仅为测试自身 300s 看门狗被慢实网触发 + 测试桩误置 `on_finished` 固件缺陷）；1.4.0 时点为 `test_legacy_format`（mock 字节数漂移：真实 mod 被作者更新）+ `test_page_parser`（旧标签结构夹具，已被 Wayback 实证推翻）。
- flake 三项（`test_stress` / `test_game_dir_e2e` / 实网脚本）单独重跑确认环境性后方可判过。

---

## 四、环境陷阱清单（踩过的坑，逐条有解药）

### 4.1 offscreen 字体豆腐块：QT_QPA_FONTDIR + 雅黑

- **症状**：offscreen 截图中文全是豆腐块；极端时 Qt 加载默认字体失败。
- **解药**（两件套，缺一不可）：

  ```powershell
  $env:QT_QPA_FONTDIR = "C:\Windows\Fonts"      # 或在脚本内 setdefault，见 §3.1
  # 脚本内再显式设应用字体：
  app.setFont(QFont("Microsoft YaHei", 9))
  ```

- 1.4.1 截图豆腐块修复已落库（commit 2a7585b，9/9 视觉验证通过）。

### 4.2 控制台乱码 ≠ 文件损坏

- Windows 中文系统 pwsh 的 stdout 按 GBK 输出；UTF-8 文件经 `Get-Content` 打印显示 GBK 误解乱码（如"工作"→"宸ュ潑"）。
- **这是显示层问题，文件本身完好**。验证用 `python -c "print(open(f, encoding='utf-8').read())"` 或比对 MD5，不要看到乱码就去"修编码"。

### 4.3 Qt 退出崩溃噪声 + 脚本式判定 RESULT

- **症状**：测试脚本跑完后进程退出码 -1073740791（SIGSEGV）或 1，伴随 `QThread: Destroyed while thread still running`。
- **根因**：Qt 在解释器关闭时拆卸仍在运行的线程（downloader / ImageLoader 等后台线程），是**既有环境崩溃**，1.3.8 起逐版一致。
- **判定标准**：**stdout 的 RESULT 行**。仅当 RESULT 行缺失且死在断言之前，才算真崩。
- 1.4.2 的真硬崩溃与之同指纹但不同性质：`test_user_interaction.py` 真按键模拟抓到 SIGSEGV 发生在**断言之前**（`_do_game_search` 覆盖运行中 QThread 引用致 GC 销毁 C++ 线程）——区分靠"RESULT 行是否产出"。

### 4.4 工作区 exe 沙箱：复制到 %TEMP% ASCII 路径跑

- **症状**：在工作区目录内直接运行未知 exe（如安装包、`build\dist\SWDM\SWDM.exe`）向 `%TEMP%` / AppData 写数据时，本机沙箱报**错误 5**（Inno 引擎自解压建 `is-xxx.tmp` 被拦截）。schtask 通道曾假性"成功"，实因当时同时做了 `%TEMP%` 拷贝（混杂变量）。
- **根因**：镜像路径判定——沙箱拦截"位于工作区目录内"的未知 exe 写系统位置。
- **解药**：把 exe 复制到工作区外 ASCII 路径再跑：

  ```powershell
  copy "installer\Output\SWDM-Setup-1.4.2.exe" "$env:TEMP\SWDM-Setup-launch-tmp.exe"
  & "$env:TEMP\SWDM-Setup-launch-tmp.exe"
  ```

- 已交付工具：`installer\launch-setup.bat`（模板入库；发布流程：打包后复制到 `installer\Output\` 即可）。它自动选最新 `SWDM-Setup-*.exe` → 优雅 taskkill SWDM → 拷 `%TEMP%` → `start /wait` → 清理。用户侧双击 `installer\Output\安装-SWDM.bat` 即用。

### 4.5 时间戳文件与 Git

- 测试 / 工具会产出**带时间戳的瞬时文件**：`tests/shots/*.png`（offscreen 截图）、`tests/_*.txt` / `tests/_*_run*.log`（脚本输出转储）、`docs/screenshots/` 成图、手工复测记录。
- **纪律**：
  1. 这些一律不进 git（`.gitignore` 已覆盖 `tests/shots/`、`tests/_*.txt`、`*.log`）。
  2. 产出**新文件模式**时，当值文档成员立刻补 `.gitignore` 规则（`git_workflow.md` §四）。
  3. commit 前过 `git status`，timestamped 产物混入即 `git restore --staged` 剔除。
  4. 需要留存证据的复测产物（如 `docs/retest_round*.md`）**摘结论入 markdown**，不提交二进制 / 大日志。

### 4.6 QTabWidget 可见性陷阱

- 非当前页整页被隐藏，页面内子件 `isVisible()` 恒返回 False。
- 空态 / 几何断言须先 `setCurrentWidget(tab)` 再量化，或用 `isHidden()`（显式 hide 语义，与祖先可见性解耦）。

### 4.7 读图工具全失效 → 几何量化兜底

- `read_image`：sharp 模块 ERR_DLOPEN_FAILED（win32-x64 原生库加载失败，重装 sharp 亦无效）；`modlens_read_image`：Gemini API key invalid。
- **后果**：GUI 视觉类 bug（挤压 / 重叠 / 裁切）不能靠截图识别；9 张 offscreen 截图（README 4 + 手册 5）交付用户前**需人工目检**。
- **兜底口径**：`mapTo(ref, QPointF(0,0))` 相对坐标 + 显式行高 / 间距断言（如设置页"无压扁控件"断言：展开分组标题按钮与首个内容控件间距 ≥ 8px）；规则存在性检查。

### 4.8 实网脚本漂移

- 本机 steamcommunity.com 走 fake-IP 代理（DNS→198.18.0.124，Meta 接口），出口香港 IDC；api.steampowered.com 常被 SNI 阻断；429 由请求头指纹触发（裸 Chrome UA 缺 Accept-Language 必被限，加 `Accept-Language: zh-CN,...` 或 `X-Requested-With` 即 200——已落库 `steam_api.py`）。
- 实网测试在 FAIL / PASS / NORESULT 间漂移是**环境问题，不是代码回归**；`run_all.ps1` 的 `$skip` 基线隔离它们；复测时单独重跑定性。

### 4.9 模拟 QMessageBox 不是真实阻塞

- 把 `QMessageBox.question/information` 换成普通函数后，调用方（如 `_on_check_updates_done` 的「询问 → 入队 → 清标红」）会同步执行完。
- 断言"弹窗时状态"必须在桩函数**内部**捕获（`marked["ids"] = set(tab._updated_ids)`），弹窗返回后再查已被清空。

### 4.10 PYTHONUTF8=1

- 任何跑中文 / ⚠✓ 字符的 print 必须先 `$env:PYTHONUTF8 = "1"`，否则 GBK 控制台 print 假崩。

---

## 五、维护节奏（迭代之间的常规动作）

1. **每轮迭代结束**：四要素闭环 → changelog 收口 → engineering_log 追加 → captain 提交 + tag + 推送 → 提醒用户人工目检项。
2. **研讨与预研**：新功能落地前派只读调研（`docs/research/`），方案预研细化到文件:行号 + 工时（范例 `docs/research/plan_1.4.2_impl.md`），**不写代码**。
3. **审计滚动**：UX 审计（U 类）· 核心静态审计（P 类）· 竞品调研（S 类）三份只读输入 → plan draft → 讨论组裁决。
4. **变量监控**（每轮复查）：Valve issue steam-for-linux#13474（scoped server token，若采纳将重估 C3 私人账户 provider 与"需正版账号"启发式）；竞品 sefrawe / Streamline 动态。
5. **记忆系统**：实质性工作后写 `memory_log`；跨会话结论进 `memory_note`；跑通的可复用多步流程写 `memory_procedure`（先 `memory_procedure_list` 查重）。
6. **已知限制诚实披露**：读图工具失效 / offscreen 不验托盘与真实剪贴板 / GGNetwork 结论仅对当时环境与后端版本有效——逐版在 changelog「已知限制」节滚动维护。

---

## 六、互链

- 组织规矩（Team Topologies / SPOQ / 执行接地 / SDET 分工 / 写域分离 / captain 边界）：`docs/process/team_organization.md`
- 用户侧场景剧本（操作步骤 + 期望反馈 + 自动化覆盖 + 人工补测清单）：`docs/process/user_interaction_scenarios.md`
- Git 细则：`docs/git_workflow.md` · 历史任务流水：`docs/engineering_log.md` · 变更记录：`docs/changelog_*.md`
