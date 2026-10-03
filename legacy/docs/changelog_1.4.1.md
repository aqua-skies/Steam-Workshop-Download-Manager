# SWDM 1.4.1 变更记录

> **English summary**: 1.4.1 is the documentation/performance/account-safety iteration planned in t31. It closes the GGNetwork real-network gap (and two severe bugs that had made that channel inert), adds detail-page disk caching, next-page prefetch, clipboard queueing, QSS polish, library update checks, item-level failure reasons, and a compliant private-account provider, then ships the nine-chapter user manual with an in-app help entry. Version markers are synchronized to 1.4.1 and the installer is rebuilt. Full details below in Chinese.

> 打包任务：t43（packager，attempt 3fb1e7df）· 2026-09-30
> 前置：t31 功能评审（installer-fixer 主持，五方零反对）+ t32-t42 功能/文档任务
> 评审文档：`docs/feature_review_1.4.1.md`（12 项裁决，纳入 10 项、延后 3 项、砍掉 0 项）
> 手册：`docs/manual/SWDM用户手册.md` / `docs/manual/dist/SWDM-用户手册.html` / `.pdf`
> 上版记录：`docs/changelog_1.4.0.md`

---

## 一、版本概要

1.4.1 落实 t31 评审的 10 个纳入项，主线是**用户体感、性能与合规分层**：

- 详情页回退不再重新加载（B1 磁盘缓存）；
- 翻页更顺（B2 下一页预取）；
- 复制工坊链接即可入队（B3 + B5 批量粘贴）；
- 界面更现代且空队列/空库不再无路可走（A2 QSS + B6 空态引导）；
- mod 库可检查更新并一键入队（C1）；
- 下载失败原因从通用串变成可读分类，且绝不用通用 I/O 误报“必须买游戏”（C2）；
- 受限内容可通过**用户自己的 Steam 账号**下载（C3）；
- GGNetwork 从“未实测”变为实测可用，并修复使其此前从未生效的两个严重缺陷（C5/t32）；
- README 补齐能力清单、截图与诚实限制（A3/t39）；
- 用户手册九章节随包，程序内 F1 /「帮助 > 用户手册」可打开（A1/t42 打包侧）。

默认下载链仍以匿名 steamcmd 为兜底；未登录账号时，C3 通道不在默认链中，匿名用户行为与 1.4.0 一致。

---

## 二、C5 GGNetwork 真下载补测（t32，search-fixer）

**最重要的认知更正**：1.4.0 记录“本机 fake-IP 代理做不了 GGNetwork 实测”。实测发现 `api.ggntw.com` / `cdn.ggntw.com` 不在 steamcommunity 的 fake-IP/SNI 阻断范围内，本机可直接完成补测。

**修复的两个严重 bug**：

| # | 问题 | 修复 |
|---|---|---|
| 1 | `resolve()` 在 `queue.position>0` 时丢弃 url。实测每个成功响应都同时带 `position=1` 和有效 url，因此该通道对任何真实物品都会静默失败并回退 steamcmd。 | 有 url 即使用，并改写为 CDN 直链；只有“无 url 且 position>0”才判排队回退。 |
| 2 | API 返回的 `ggntw.com/download/<token>` 是 HTML 落地页，直接当文件下载会存成网页。 | 改写为真实文件地址 `cdn.ggntw.com/<token>`。 |

**端到端结果**：Wiremod 160250458 成功下载并解包；最终 `160250458.gma` 为 20,685,180 字节，GMAD 魔数正确，与 Steam 声明尺寸 delta=0。实测 8 次突发解析无 429；自限速 20 次/分钟（突发 3）在真实延迟下有余量。

**风险定级维持 🟡**：公开内容匿名可用，未观测到服务端账号池行为；受限 App（DayZ 221100 / Barotrauma 602960）样本因本机 steamcommunity 浏览页被阻断而未取得。该通道仍保持实验性、不进默认链。

**文件**：`swdm/core/providers/ggnetwork.py`；测试 `tests/test_providers.py`（89/89）；详细记录 `docs/ggnetwork_retest_1.4.1.md`；1.4.0 changelog 的“未实测”条目已由 t32 回填。

---

## 三、B1 详情页磁盘缓存（t33，core-tester）

新模块 `swdm/core/detail_cache.py`：

- 缓存渲染后的详情页 HTML。命中时回退详情页零网络请求，解决“返回上一页重新加载”的卡顿。
- **双失效**：TTL（默认 24 小时，`network.detail_cache_ttl_hours`）+ `time_updated` 比对；mod 在 Steam 更新后立即丢弃旧缓存，避免显示过期内容。
- **深拷贝纪律延伸到磁盘层**：命中返回 `copy.deepcopy(html)`，调用方修改不污染缓存。写入使用临时文件 + `os.replace` 原子替换。
- **损坏容忍**：JSON 非法、缺字段、文件缺失、磁盘读写失败一律按 miss 处理并尝试清理脏文件，不把异常抛进 UI。
- 手动刷新强制 bypass 缓存：详情弹窗「🔄 刷新」清内存条目并以 `force_refresh=True` 重建 worker。

**配置与 UI**：`swdm/core/config.py` 新增 `network.detail_cache_enabled`（默认 True）与 `network.detail_cache_ttl_hours`（默认 24）；`swdm/gui/settings_tab.py` 提供开关、TTL 微调框和清除按钮；`swdm/gui/detail_dialog.py` 接入缓存读写。

**验证**：`tests/test_t33_detail_cache.py` 33 项 ALL PASS；详细约束见各任务记录。

---

## 四、B2 下一页预取（t34，core-tester）

- 新增共享熔断器 `swdm/core/circuit.py`：连接级错误立即熔断，或连续 3 次失败熔断；冷却 15 秒，成功重置失败计数。语义与 t22 搜索熔断一致。
- `swdm/core/game_search.py` 与 `swdm/core/steam_api.py` 的既有熔断逻辑改为委托同一 `CircuitBreaker`，未改变原行为。
- `swdm/gui/workshop_tab.py` 在当前页渲染完成后调度下一页预取：
  1. 只在本页满 30 条、可能有下一页时预取；
  2. 熔断冷却期跳过，断网时预取线程不空转；
  3. 用户点击/依赖下载在飞时礼让重排；
  4. 请求前后两次校验代际，旧预取静默丢弃；
  5. 预取只调 `browse()` 暖 ApiCache，复用既有深拷贝路径，结果从不渲染、绝不覆盖当前页。
- 预取使用 daemon 线程而非 QThread，避免退出阶段被在途网络请求挂住；开始翻页时停止未触发的预取定时器。

**验证**：`tests/test_t34_nextpage_prefetch.py` 25 项 ALL PASS；`test_rettest_140.py` 中过时的 B6 断言已同步修正。

---

## 五、B3 剪贴板入队 + B5 批量粘贴（t35，gui-tester）

- `general.clipboard_watch`（默认开启）监听 `QClipboard.dataChanged`。复制工坊链接后自动解析、补全并加入下载队列；成功仅在状态栏提示 5 秒，失败静默。
- 防御性设计：剪贴板原文不记录、不缓存、不写日志；只流转解析出的 `(appid, item_id)`；非工坊文本零成本跳过。
- 去重基于 `DownloadManager.snapshot()` 的 queued/active/done 三组；重复复制不二次入队。
- AppID 回退顺序：链接携带值 → `get_file_details` 返回值 → 当前工坊页游戏；三者皆空时仍按既有“导入 URL”行为兜底。
- B5 批量粘贴并入同一入口：`swdm/gui/workshop_tab.py` 的批量导入框按 token 解析、去重并跳过无效值。
- 顺带收掉 1.4.0 技术债“搜索冷却结束后自动重发一次待选词”，改词作废。
- 设置页开关即时生效；`swdm/gui/main_window.py` 的连接/解绑与处理函数均有二次配置校验。

**验证**：`tests/test_b3_clipboard.py` 34 项 ALL PASS。offscreen 平台不产生真实 `dataChanged`，托盘态/真实桌面复制行为见 `docs/clipboard_watch_notes.md` 的 5 条人工确认清单。

---

## 六、A2 QSS 界面美化 + B6 空态引导（t36，gui-tester）

- **P1 滚动条**：深色/浅色双主题、纵向/横向把手描边、圆角、hover 与 pressed 状态。
- **P2 表头**：最小高度、hover/pressed 背景、右侧分隔线；只改 `QHeaderView::section`，未触碰数据行几何。
- **P3 进度条终态色**：成功绿色、失败红色，并同步边框色；`swdm/gui/downloads_tab.py` 在终态设置 `status` 属性并触发 `unpolish/polish` 重绘。
- **P4 跟随系统**：`auto` 主题读取 `QGuiApplication.styleHints().colorScheme()`；系统配色切换即时换肤，主题切换不再要求重启。设置页下拉新增“跟随系统”。
- **P5/B6 空态**：
  - 库页空库显示“前往工坊浏览”；
  - 有库但筛选无结果显示“清除筛选条件”；
  - 下载页空队列显示“前往工坊浏览”；
  - 空态以表格/列表实际内容为判据，避免与快照漂移。
- 顺带归还两项 1.4.1 技术债：通道未配置时设置页显示“（未配置，链内自动跳过）”；`test_page_parser` / `test_legacy_format` 夹具按当前 Steam 表单与网络感知行为修正。

**文件**：`swdm/gui/styles.py`、`swdm/gui/main_window.py`、`swdm/gui/library_tab.py`、`swdm/gui/downloads_tab.py`、`swdm/gui/settings_tab.py` 等。

**验证**：新增 `tests/test_qss_p1_p5.py` 36 项；GUI sweep / offline / all buttons / cross features / providers / rettest 等关键回归全部通过。该任务在本地网络可用时曾达到 run_all 63/63 历史首次零失败。

---

## 七、C1 mod 库更新检查（t37，core-tester）

- 新增 `SteamAPI.check_updates(records, progress=None, cancel=None)`：按库记录的 `time_updated` 与 Steam 当前值批量比对，每批 50 条。
- 检查走 `get_file_details → _api_post` 直连，**不经 api_cache**，保证比对的是 Steam 当前值而不是旧缓存。
- 每批前执行 `/ISteamRemoteStorage/` 端点节流；单批异常按“该批判未知”跳过，不传播、不误标。
- 库页新增「🔍 检查更新」按钮：daemon 线程执行，避免 UI 卡死与重入；进度经 GUI 线程实时更新为「检查中 x/y」；cancel 可中止。
- 结果仅标红（🔄 前缀 + 红色），随后询问是否加入下载队列；同意后从库记录重建物品并走标准 `DownloadManager.enqueue`， downloader 无新增状态机；入队后清除标红。
- 大库进度反馈有测试覆盖：500 条分 10 批、进度单调递增、cancel 中止。
- **交付前修复 A6**：worker 原先用 `QMetaObject.invokeMethod(..., Q_ARG(list, ...))` 回 GUI 线程；bare Python list 在本机 PySide6 无 QMetaType，调用抛 `RuntimeError`，完成回调从未触发，按钮永久卡在「检查中」、无标红、无询问窗。现改为 `updates_checked = Signal(list)` 和 `check_progress = Signal(int, int)`，worker 直接 emit，由 Qt 自动排队到 GUI 线程；失败也 emit，UI 必恢复。新增 `tests/test_a6_check_updates_thread.py` 覆盖按钮点击 → daemon worker → 完成回调的真实线程路径；`tests/test_qarg_list_repro.py` 与 `tests/test_t44_retest_gui.py` 的 A6 组同步改为断言修复后行为。

**文件**：`swdm/core/steam_api.py:446`、`swdm/gui/library_tab.py:165-463`、`swdm/core/steam_api.py:307-316` 等。

**验证**：`tests/test_t37_lib_updates.py` 34 项（核心 15 + GUI 19）ALL PASS。

---

## 八、C3 私人账户 provider（t38，search-fixer）

**合规定位**：本通道**不是**公有账户池。公有账户池仍是“保留接口、不启用”；C3 落地的是合规分层低风险端：用户自己的账号下载自己有权的内容。

- 新增 `swdm/core/providers/account_steamcmd.py`：`AccountSteamCMDProvider`，`priority=90`，`supports_account=True`，登录态自动加入链且位于匿名兜底之前；未登录时 `is_configured()` 为 False，默认链不含。
- `swdm/core/providers/base.py` 新增 `supports_account` 与 `breaker_exempt` 元数据。
- 共享/兜底 steamcmd 引擎恒为匿名；账号凭据只存在于账号通道的专属引擎实例。两个引擎共用串行锁，两个 steamcmd 进程永不并发。
- 四条风控：
  1. `SteamCMDEngine._redact_secrets()` 在日志与行回调前过滤用户名/密码/验证码；`AuthManager.login_user` 日志不再含账号名；
  2. Steam Guard 首登弹验证码输入框，文案明确“仅需一次”；
  3. 账号失败通过 `breaker_exempt` 与会话级失活与通道熔断解耦，账号问题不熔断匿名兜底；
  4. 凭据与 api_key 同等处理：keyring 优先、本地混淆回退，密码不进 config/auth/导出包。
- 设置页账号分组常驻隐私明示：“账号仅本地存储、仅本人使用”。

**验证**：`tests/test_account_provider.py` 72 项 ALL PASS，覆盖默认链不含、日志/导出无凭据、熔断解耦、Guard 流程、匿名行为不变等。

---

## 九、A3 README 截图、能力清单与已知限制（t39，installer-fixer）

- `README.md` / `README.en.md` 各新增 7 枚 shields.io 静态 badge；1.4.1 打包时版本 badge 同步为 1.4.1。
- 新增「功能速览 / Feature Overview」四组共 18 条，并同步双语。
- 截图由 `tools/make_readme_shots.py` 用固定夹具数据 offscreen 渲染：`docs/screenshots/` 下 workshop / downloads / library / settings 四张 1280×800 PNG。
- 已知限制由 4 条扩至 5 条，明确受限 App（如 DayZ 221100）需要拥有该游戏的 Steam 账号；并标注集合下载、图标体系、缩略图缓存排在 1.4.2。
- 本机读图工具不可用，截图以“生成不崩溃 + 尺寸非空”为自动化口径，成图需人工目检；这一限制已写入 README。

---

## 十、技术债：cdn_downloader.py 门面移除（t40，installer-fixer）

- 删除 `swdm/core/cdn_downloader.py` 兼容门面；生产代码零引用。
- 三个测试迁移到 `CDNProvider` 直连 API：
  - `tests/test_cdn.py`：`download_file→http_download`、`download_item_cdn→download`、`resolve_file_url→resolve`；
  - `tests/test_core_sweep.py` 第 5 节；
  - `tests/test_providers.py` 第 11 节。
- `README`、`docs/project_structure.md`、`docs/plan_1.4.1.md` 中的门面移除条目标记为已完成。
- 该项虽是技术债，但减少了 1.4.0 遗留的重复 API 表面，使新代码只通过 provider 抽象访问 CDN。

---

## 十一、C2 item 级失败原因枚举（t41，search-fixer）

新增 `swdm/core/failure_reason.py`（纯函数、无 Qt 依赖，与熔断器正交）：

| 桶 | 用户可读结论 |
|---|---|
| `DISK_FULL` | 磁盘空间不足，请清理后重试 |
| `EMPTY_SUCCESS` | 本程序自产的 0 字节假成功，透出原文 |
| `RATE_LIMITED` | 触发 Steam 限流，请稍后重试 |
| `NETWORK` | 网络超时或无法连接 Steam 服务器 |
| `LOGIN_FAILED` | 凭据/Steam Guard 问题，与所有权区分 |
| `ITEM_GONE` | 物品不存在或已下架 |
| `ACCOUNT_NEEDED` | 仅两条正向信号：受限 App + 匿名下载未开始；或重试后仍同一错误且本次运行无限流/超时信号 |
| `GENERIC` | steamcmd 未区分权限/网络/限流，建议重试并见日志 |

**误报红线**：`ERROR! I/O Operation Failed`、`Failed to download item …`、`Not Logged On` 等通用串一律落入 GENERIC 或 NETWORK，绝不映射“需正版账号”。账号提示使用“可能”，并说明“若你已拥有该游戏，失败原因可能并非权限问题”。

**接线**：`swdm/core/downloader.py` 的 `DownloadJob` 新增 `signals`、`attempt_messages`、`failure_bucket`；线程局部当前 job 把限流/超时信号归到正在执行的任务；终态失败使用归类文案，原文保留在日志与历史记录中；熔断/退避路径完全不变。

**验证**：`tests/test_failure_reason.py` 42 项 ALL PASS，含 5 项误报红线和账号失败与熔断解耦覆盖。

---

## 十二、A1 用户手册与帮助入口（t42 + t43 打包侧）

**手册源与构建**（t42，scribe）：

- 源文件：`docs/manual/SWDM用户手册.md`（九章，扉页声明版本与许可证）。
- 构建工具：`tools/build_manual.py`，输出单文件 HTML（内嵌 base64 截图）与 PDF；`tools/make_manual_shots.py` 用固定夹具数据生成 5 张截图。
- 产物：`docs/manual/dist/SWDM-用户手册.html`、`docs/manual/dist/SWDM-用户手册.pdf`。
- 回归测试：`tests/test_manual.py`，覆盖源文件存在、版本绑定、图片存在、目录锚点、HTML/PDF 产物与帮助入口。

**打包侧落地（t43）**：

- `swdm/gui/main_window.py` 新增「帮助(&H) > 用户手册(&M)」，快捷键 F1；`_open_user_manual()` 用 `QDesktopServices.openUrl()` 打开随包 HTML，HTML 缺失时回退 PDF。
- `swdm.spec` 把 HTML 与 PDF 打入 PyInstaller 数据目录 `manual/`；Inno Setup 已按 `build\dist\SWDM\*` 递归纳入，安装后用户无需联网即可查看手册。
- 手册与 `docs/changelog_1.4.1.md` 互链；界面状态按代码冻结后版本核对，包括调试 Tab 默认隐藏、暂停/继续合并按钮、通道下拉与账号入口。

---

## 十三、版本号与构建

- `swdm/core/paths.py:13`：`APP_VERSION = "1.4.1"`
- `installer/swdm.iss:14`：`#define SWDMVersion "1.4.1"`
- README 双语版本 badge 同步为 1.4.1。
- PyInstaller 构建：`python -m PyInstaller swdm.spec --noconfirm --workpath build --distpath build/dist`
- Inno Setup 构建：`ISCC.exe installer\swdm.iss`
- 安装包：`installer\Output\SWDM-Setup-1.4.1.exe`
- 冒烟：运行 `build\dist\SWDM\SWDM.exe`，确认窗口标题为「Steam 工坊下载管理器 v1.4.1」且进程稳定后停止。

---

## 十四、汇总验证与全量回归

**冲突检查**：

1. `python -m compileall -q swdm tests tools` exit 0。
2. `swdm` 与 `tests` 无重复模块/类定义；新模块 `detail_cache.py`、`circuit.py`、`failure_reason.py`、`providers/account_steamcmd.py` 各自独立注册，未覆盖既有 provider。
3. 共改文件交叉点核对：
   - `steam_api.py`：search fallback、缓存深拷贝、CircuitBreaker 委托、check_updates、端点节流共存；
   - `workshop_tab.py`：搜索回退、下一页预取、批量粘贴、QSS 空态兼容共存；
   - `main_window.py`：托盘退出、剪贴板监听、系统主题、帮助菜单共存；
   - `settings_tab.py`：缓存、剪贴板、主题、账号、通道控件共存；
   - `library_tab.py`：既有库管理与 C1 更新检查共存；
   - `downloader.py`：provider 链、取消竞态、账号引擎路由与 C2 失败枚举共存。

**回归**：`tests/run_all.ps1`，三组统计全部在位，零新增失败、零 NORESULT：

| 轮次 | 脚本数 | PASS | FAIL | NORESULT | FAIL 定性 |
|---|---|---|---|---|---|
| t43（打包终态） | 88 | 87 | 1 | 0 | `test_stress` 1_SLOW 性能标记，三次单跑结果一致，判环境性（机器被挂死的实网测试拖慢） |
| t44（GUI 复测轮） | 89 | 87 | 2 | 0 | `test_stress` 同上 + `test_game_dir_e2e`——真实 e2e 下载实际 SUCCESS（JobStatus.SUCCESS / 已入库 / local_path 正确 / 内容目录 7 文件），FAIL 仅为测试自身 300s 看门狗被慢实网触发 + 测试桩误置 `on_finished` 的固件缺陷 |
| t45（核心复测轮，skip 基线） | 69 | 69 | 0 | 0 | 已知 flake 三项（`test_stress` / `test_game_dir_e2e` / 实网脚本）单独重跑全部确认环境性 |

任何失败均经逐项定位确认为既有环境/测试固件项，非代码回归。

---

## 十五、已知限制与下一步

- GGNetwork 为第三方代理通道，结论仅对本次环境与后端版本有效；受限 App 行为因无法取得样本而未验证。
- 本机读图工具不可用，README/手册截图仍需最终人工目检；offscreen 不能验证真实桌面剪贴板与托盘态。
- steamcmd 账号通道每次任务都登录；持久会话与批量场景优化留待后续。
- 打包前审计发现两项非阻塞缺陷，已裁决归 1.4.2：C1 检查更新的「取消」在 UI 层是不可达死代码（核心 API cancel 契约本身有效）；最大并发下载配置修改后调度门未同步生效。
- 1.4.2 候补：图标体系、集合/批量下载、缩略图磁盘缓存、以上两项审计修复。
- t44 GUI 复测与 t45 核心复测均已通过（`docs/retest_round1_gui_1.4.1.md` / `docs/retest_round2_core_1.4.1.md`）；t46 六方评审 6/6 零反对，闸门通过，见第十六节。**1.4.1 正式交付**，待 captain 提交并打 tag `v1.4.1`。

---

## 十六、t46 六方交付评审（闸门结论）

> 评审任务：t46（fixer 主持，attempt 40372c6c）· 2026-09-30
> 评委：fixer（主持）· captain · packager · gui-checker · core-checker · scribe（六方）
> 评审对象：1.4.1 打包终态（`installer\Output\SWDM-Setup-1.4.1.exe` 47,756,369B / 45.5MB，ProductVersion 1.4.1；`build\dist\SWDM\SWDM.exe` 8,613,764B + 随包手册 `_internal/manual/` HTML 140,006B + PDF 1,404,127B）
> 三原则：精简 · 以用户体感为中心 · 保证基本功能正常运行

**总结论：六方一致同意交付 1.4.1，零反对，交付闸门通过。**

### 16.1 交付条件四要素核对（用户规定）

| 条件 | 状态 | 证据 |
|---|---|---|
| 全量回归所有功能（含新增）及关联交互 | ✓ | 三组统计见第十四节回归表；零新增失败、零 NORESULT；t45 skip 基线 69/69 零失败；flake 三项全部单独重跑确认环境性/固件项 |
| 版本号升级 + 可追溯变更记录 | ✓ | 双端 1.4.1（`paths.py:13` + `swdm.iss:14`，安装包内嵌 ProductVersion 实测 1.4.1）+ 本 changelog 十六节；手册三处互链可达（t48 修订后核实） |
| bug 测试员连续两轮复测无异常 | ✓ | t44 GUI/用户视角：56 + 30 项全 PASS + exe 冒烟（gui-checker 会话 pid=11184，8s/10s 双检查点存活）；t45 核心视角：111 项独立检查全 PASS（独立 mock，刻意不复用各功能任务自测） |
| 讨论组一致认为可交付 | ✓ | t31 开发前评审五方零反对（10 项纳入）；本节六方投票 6/6 零反对 |

### 16.2 功能逐条过审（t31 十项 + 技术债一项，结论全部通过）

| # | 功能 | 执行 | 复测覆盖 | 结论 |
|---|---|---|---|---|
| A1 | 用户手册九章 + 构建链 + F1 帮助入口 + 随包 | t42 scribe / t43 打包侧 | test_manual；t44 帮助入口断言；t48 勘误 16/16 + 重构建 | 通过 |
| A2 | QSS P1-P5 + B6 空态引导 | t36 gui-tester | t44 P5/P6 组 16 项 | 通过 |
| A3 | README badge/截图/能力清单/已知限制 | t39 installer-fixer | t44 打包表版本号行 | 通过 |
| B1 | 详情页磁盘缓存（双失效 + 深拷贝 + 损坏容忍） | t33 core-tester | t44 P1 6 项 + t45 A 组 13 项 | 通过 |
| B2 | 下一页预取（熔断 + 礼让 + 代际丢弃） | t34 core-tester | t44 P2 3 项 + t45 B 组 11 项 | 通过 |
| B3+B5 | 剪贴板入队 + 批量粘贴 | t35 gui-tester | t44 P3/P4 9 项 + t45 关联交互 | 通过 |
| C1 | mod 库更新检查（50 条/批，bypass api_cache） | t37 core-tester | A6 修复经 t44 真实线程路径 8 项 + t45 C 组 15 项 | 通过（A6 修复在打包前完成并验证） |
| C2 | item 级失败原因枚举 + 误报红线 | t41 search-fixer | t45 D 组 24 项（含误报红线×3） | 通过 |
| C3 | 私人账户 provider（四风控） | t38 search-fixer | t45 E 组 20 项 | 通过 |
| C5 | GGNetwork 真下载补测（2 严重 bug + live E2E delta=0） | t32 search-fixer | t45 F 组 15 项 | 通过 |
| 技术债 | cdn_downloader 门面移除 | t40 installer-fixer | 迁移测试三套 PASS | 通过 |

**A6（交付前修复项）**：`library_tab.py` 的 `QMetaObject.invokeMethod(..., Q_ARG(list, ...))` 在本机 PySide6 无 QMetaType → 完成回调从未触发。修复为 `Signal(list)` + `Signal(int, int)`，worker 直接 emit；t44 沿真实线程路径复测 8 项全 PASS（t37 直调收尾盲区已覆盖）。

### 16.3 三项补充议程裁决

1. **t44 复测结论裁决（U3 检查更新取消死代码 / P0-4 并发配置静默失败）**：两项均经 t44 特征化确认属实——U3：`library_tab.py` `_check_cancel` 恒 False（UI 层死接线），核心 API cancel 契约层真实有效（n=3/out=100）；P0-4：`refresh_engine` 后 `max_concurrent` 3→6 但调度门 `_max` 构造时固化，真实派发观测上限=旧值 3，调低不降。两项均不崩溃、不卡死（A6 修复后 C1 端到端可用；并发默认值安全），captain 裁决 **归 1.4.2 修复池**（本 changelog §15 已留痕；`docs/plan_1.4.2_draft.md` 收为 P0；`docs/research/plan_1.4.2_impl.md` 已登记翻转断言）。→ **1.4.1 按现状交付。**
2. **三份 1.4.2 输入报告分发确认**：`docs/competitor_research_1.4.2.md`（S1-S9）、`docs/ux_audit_1.4.2.md`（U1-U13 + E1-E16）、`docs/core_audit_1.4.2.md`（P0×4 + P1×3 + P2×9 + P3×13）均已在案，t49 综合为 `docs/plan_1.4.2_draft.md`（建议纳入池 10 项 + 议程草稿 A-G）。分发确认完成。
3. **手册勘误修订验证（t48）**：16 条全处置（13 条纯文档 + E5 与 U1 联动 + E3 与 U2 联动 + E11 changelog 创建后解除）+ 重构建 `docs/manual/dist/`（16:46）。本轮主持方实测核验：`build\dist\SWDM\_internal\manual\SWDM-用户手册.html` MD5 = `ABB3462D736BB7FA046D93FCA589A32A` 与 dist 完全一致（PDF 亦一致），5 项修正字符串（「下载内容为空」/「单击或双击托盘图标」/「手动登录后」/「前置依赖策略」/「累计下载」）在随包 HTML 中全部存在 → **勘误已并入打包终态**。scribe 投票时独立复验同一 MD5。

### 16.4 六方投票表

| 成员 | 票 | 关键依据（每人一手核实） |
|---|---|---|
| captain | 同意交付 | 亲自跑 PyInstaller/ISCC 构建链 + A6 修复验证；四要素独立核实；U3/P0-4 裁决归 1.4.2；诚实披露四项接受为非阻塞 |
| packager | 同意交付 | 独立核对：compileall exit 0；SWDM.exe 8,613,764B；安装包 47,756,369B；随包手册；版本双端；A6/test_manual 纳入评审材料 |
| gui-checker（t44 执行人） | 同意交付 | 一手复测：56+30 项 ALL PASS；exe 冒烟 10s 存活；2 FAIL 定位为环境/固件项（test_game_dir_e2e 真实下载 SUCCESS）；A6 真实线程路径验证；U3/P0-4 特征化确认不阻塞 |
| core-checker（t45 执行人） | 同意交付 | 一手复测：111 项独立检查全 PASS；skip 基线 69/69；flake 三项环境性确认；新模块在 exe 归档 TOC 存在；U3/P0-4 同意归 1.4.2 |
| scribe（t42/t47/t48 责任人） | 同意交付 | 独立复验随包手册 MD5 一致 + 勘误确证并入；版本双端；changelog 互链可达；三组回归数字零代码回归 |
| fixer（主持） | 同意交付 | 主持评审：三项补充议程实测核验（含手册 MD5 + errata 字符串在包内存在）；四要素凭据链完整；功能逐条过审无遗漏 |

### 16.5 闸门结论

**1.4.1 交付闸门通过：六方 6/6 同意交付、零反对。** 用户规定四要素全部满足（全量回归零新增 / 双端版本号 + 十六节 changelog / t44+t45 连续两轮复测无异常 / 讨论组一致通过）。诚实披露四项均经评议接受为非阻塞：GGNetwork 受限 App 样本未取得（结论仅对本次环境与后端版本有效）；offscreen 不验托盘态/真实剪贴板（`docs/clipboard_watch_notes.md` 5 条人工清单）；9 张 offscreen 截图（4 README + 5 手册）本机读图工具全失效，仅验证「生成不崩溃 + 尺寸非零」，交付用户前需人工目检；U3/P0-4 归 1.4.2 修复池。

**交付收口动作**：scribe 收口工程记录（`engineering_log` 追加 t43-t46 交付闸门链全记录）→ captain 执行 git 提交 + tag `v1.4.1` + 推送 → 交付时提醒用户对 9 张截图人工目检。1.4.2 规划输入已就位（三份审计 + `plan_1.4.2_draft.md` + 四份 `docs/research/` 预研），讨论组议程草稿待 captain 指派主持。
