# SWDM 项目结构索引

> **English summary**: A per-file responsibility index of all 40 Python modules under `swdm/`
> (core / providers / gui layers), each entry carrying its iteration provenance (t1–t28).
> Maintained by the recorder from actual source reads, not guesses. Sections below in Chinese.

> 维护人：recorder · 制定于 t29 · 2026-09-29 · 基于 1.4.0 源码实测（读源码写，非猜测）
> 迭代溯源提取自 `docs/engineering_log.md` 与 `docs/changelog_1.3.8~1.4.0.md`

## 顶层布局

```
steam mod program/
├── swdm/                  # 应用主包（Python 3.12 + PySide6）
├── tests/                 # 测试套（59 脚本，run_all.ps1 串行）
├── docs/                  # 文档（changelog、评审、工程日志、架构）
├── research/              # 调研报告与抓取快照
├── installer/             # Inno Setup 打包（swdm.iss + Output/）
├── README.md / README.en.md   # 双语说明
├── requirements.txt
├── swdm.spec              # PyInstaller 规格
└── portable.marker        # （可选）存在则切换便携模式
```

---

## swdm/ 应用主包

### `swdm/app.py` — 入口
- `main()`：QApplication 装配（高 DPI）、`install_exception_handler()` 全局崩溃处理、`MainWindow` 构建与托盘启动。
- 交互：`gui/main_window.py`、`core/logger.py`、`core/paths.py`。
- 溯源：t1（mutex 单实例）→ t11（托盘退出与 main 的 quit 链路）。

### `swdm/core/` — 核心层（GUI 无关，可独立测试）

#### `steam_api.py` — Web API 客户端（最大的核心模块）
- `_Throttle`：熔断器（min_interval 节流 + `trip/in_circuit/decay` 冷却）。
- `WorkshopItem`：工坊物品 dataclass（`to_dict`/`from_dict`）。
- `SteamAPI`：匿名免 key 客户端。
  - `_endpoint_throttle(path, priority)`：**端点差异化节流 + 优先级礼让**（`/sharedfiles/` 3s，低优先级分片睡眠让槽给用户点击）。
  - `_community_get`：带 429 退避的社区页抓取（`Accept-Language` + `X-Requested-With` 反指纹限流）。
  - `get_file_details` / `get_collection_details` / `get_dependencies` / `resolve_dependency_tree`：元数据与依赖链。
  - `browse` / `_parse_hub_inline` / `_parse_cards` / `enrich`：工坊列表抓取与富化（元数据补全后客户端重排）。
  - `filter_items_by_tags` / `apply_browse_search_fallback` / `title_hit_rate`：客户端过滤/回退。
  - `fetch_image`：图片缓存（LRU）。
  - `resolve_any_url`：粘贴分享链接解析（appid/itemid）。
  - `ping`：连通性检测。
- 交互：`gui/workshop_tab.py`（浏览）、`gui/detail_dialog.py`（详情）、`core/downloader.py`（依赖下载）、`providers/*`。
- 溯源：t1/t4（搜索回退 + 核心 bug）→ t12（搜索体验 4 修）→ t15（端点节流优先级）。

#### `steamcmd_engine.py` — SteamCMD 子进程托管
- `SteamCMDEngine`：`resolve_exe`（查找/部署）、`deploy`（一键部署）、`_run`（子进程行回调）、`download_item`（匿名 `login anonymous` + `workshop_download_item` + 进度解析）、`ensure_partial`（断点续传检查）、`cancel`、`test_login`（含 Steam Guard）、`content_path`。
- `DownloadResult` / `DownloadStatus` / `SteamCMDError`：结果与异常。
- 溯源：t2（卸载残留/mutex）→ t4（引擎并发）→ t11（取消与引擎 stop_event 拦截）→ t21（被 `providers/steamcmd.py` 包装，本体不动）。

#### `downloader.py` — 下载队列 + 状态机（核心）
- `JobStatus` / `DownloadJob`（`percent` 字节判定：`bytes_done>=total_bytes` 直返 100）。
- `DownloadManager`：单工作线程队列。
  - `enqueue` / `enqueue_many` / `enqueue_high_priority` / `enqueue_with_dependencies`。
  - `cancel`（**同锁内先 `_cancelling.add` 再 `_stop.set`**）/ `cancel_all` / `retry` / `retry_all_failed` / `pause_all` / `resume_all` / `clear_completed`。
  - `_build_channel_chain` / `_run_channel_chain`（**provider 链式回退**：链内回退不消耗 auto_retry；熔断器接线 SUCCESS→record_success / FAILED→record_failure，CANCELLED 与 terminal 通道豁免）。
  - `_exec_job`（入链前早退 + 终态判定块与 cancel 全程互斥）/ `_retire_cancelled`（单次登记）/ `_register_to_library`（入库 + `swdm_meta.json` 旁车）/ `_normalize_content_path`。
  - `_on_throttle_signal`（订阅列表式，append 注册）。
- 交互：`providers/*`、`steamcmd_engine.py`、`mod_library.py`、`throttle.py`、`gui/downloads_tab.py`。
- 溯源：t1（回退判定）→ t4（并发与重试）→ t11/t15（取消与竞态移交）→ t14（速度采样 + 卡 99%）→ **t21（链式回退改造）→ t22（A-P1 微秒窗口正式修复）→ t28（熔断器接线 + 删 `_download_via_cdn` 死方法）**。

#### `mod_library.py` — SQLite mod 库
- `ModRecord`（dataclass）/ `ModLibrary`。
- `upsert` / `delete(remove_files=)` / `set_enabled` / `set_category` / `set_favorite` / `set_notes` / `search`（多维：游戏/分类/标签/状态/关键词，sort=appid）/ `categories` / `all_tags` / `stats`。
- `log_job` / `job_history`（下载历史）、`organize_path` / `write_metadata_sidecar`、`import_existing`（导入既有 mod 目录）。
- 交互：`downloader.py`（入库）、`gui/library_tab.py`、`gui/downloads_tab.py`（删除互通）。
- 溯源：t4（库检索）→ t14（库按游戏分类 game_name 渲染）→ t13（删除双向信号）。

#### `auth.py` — 账号
- `Account` / `AuthManager`：`login_anonymous` / `login_user`（Steam Guard、keyring 加密存密码，fallback 明文文件）、`get_credentials` / `clear_stored`。
- 溯源：t4（登录测试）→ t11（托盘退出与登录态清理）。

#### `config.py` — 持久化配置
- `Config` 单例：`load` / `_merge`（**三层嵌套递归合并**：`download.channel` + `download.providers.{name}.{enabled,...}`）/ `save` / `get` / `set` / `reset`。
- 溯源：t4 → **t21（通道化扩展）** → t22（B④ 调试 Tab 默认隐藏 config 默认 False）。

#### `paths.py` — 数据目录
- `_user_data_root`（`%APPDATA%\SWDM\`，`portable.marker` 存在则 `<根>/data/`）、`ensure_dirs`、`resource_path`（PyInstaller 资源）、`bundled_steamcmd_zip` / `deployed_steamcmd_exe`。
- **`paths.py:9` `APP_VERSION`**：版本号双端之一（t24 改 1.4.0）。

#### `games.py` — 游戏名录
- `list_builtin`（**内置 59 个支持工坊的游戏**）/ `list_custom` / `add_custom` / `remove_custom` / `all_games` / **`game_name(appid)`**（未知回退 `'AppID N'`）。
- 交互：`gui/workshop_tab.py`（游戏选择器）、`gui/library_tab.py`（库分类渲染）。
- 溯源：t12（游戏输入识别/联想）→ t14（库游戏名渲染）。

#### `logger.py` — 日志
- `_RingHandler`（内存环形缓冲）+ `setup_logger`（轮转文件日志）+ `subscribe`/`unsubscribe`/`snapshot`（GUI 订阅）+ `DebugChannel`。
- 交互：`gui/debug_tab.py`。

#### `throttle.py` — 节流与退避工具箱
- `Backoff`（指数退避 + `nudge`/`record_success`）、`AdaptiveConcurrency`（自适应并发）、`classify_steamcmd_line`（steamcmd 输出分类）、`ProgressSmoother`（**deque 滚动窗口速度采样**，`feed(bytes_done, total, now=)` 返回快照 dict）。
- 溯源：t4（熔断器雏形）→ **t14（ProgressSmoother 滚动窗口重写）**。

#### `page_parser.py` — 工坊详情页解析
- `parse_description` / `parse_creator_name`（锚点 `class="creatorName"`）/ `parse_comments` / `fetch_comments` / `parse_available_tags` / `parse_available_tags_with_counts`（SSR loader + form inputs 双路）。
- 溯源：t4 → t15（详情页解析性能基线：4.5ms/页）。

#### `hub_parser.py` — 工坊浏览页解析
- `extract_results`（卡片列表 + 分页 + 总数）、`browse_hub`。
- 溯源：t1（搜索无关结果修复）→ t4。

#### `deps_parser.py` — 依赖解析
- `parse_required_items` / `parse_required_items_with_titles` / `parse_required_items_robust`（从详情页 HTML 提取 Required items）。
- 溯源：t4（依赖自动下载）。

#### `conflict_extractor.py` — 冲突检测
- `ConflictInfo`、`extract_conflicts`（从描述提取"与 XX 冲突"链接）、`check_installed_conflicts`（对已安装库做模糊标题匹配）。
- 交互：`gui/workshop_tab.py`（卡片冲突标记）、`gui/detail_dialog.py`。

#### `game_search.py` — 游戏搜索（storesearch）
- `GameSearchClient`：`search`（`GET store.steampowered.com/api/storesearch`，匿名无 key）、`cached`、**间隔 0.7s + 熔断退避**（连续 3 次失败或 ConnectionError 冷却 15s）。
- 溯源：t12（搜索体验）→ **t22（D 间隔 1.2s→0.7s + 熔断退避）**。

#### `game_dirs.py` — 游戏安装目录
- `game_install_dir` / `game_content_root` / `set_game_dir` / `clear_game_dir` / `configured_game_dirs` / `game_dir_entries`。
- 交互：`gui/settings_tab.py`（目录表）、`gui/workshop_tab.py`（目录标签）。

#### `steamcmd_deploy.py` — SteamCMD 部署
- `is_deployed` / `has_bundled_zip` / `deploy`（解压自带 zip）/ `ensure_steamcmd` / `deployment_status`。

#### `api_cache.py` — API 缓存
- `ApiCache`（TTL + LRU + `get_or_compute` + `invalidate`）、`get_api_cache()`、`make_cache_key`。
- **纪律**：`browse()` 返回的 `WorkshopItem` 是可变 dataclass，`enrich()` 就地修改——**缓存命中返回前必须深拷贝**，否则污染缓存。

#### `cdn_downloader.py` — CDN 兼容门面（**1.4.1 移除**）
- `resolve_file_url` / `download_file` / `download_item_cdn`：平迁自 `providers/cdn.py` 的兼容层，顶部已标注"新代码请用 `swdm.core.providers.cdn`"。
- 存在理由：旧测试（test_cdn / test_core_sweep）零改动，1.3.9 回归基线直接复用。

### `swdm/core/providers/` — 下载 provider 抽象层（**1.4.0 新增**）

#### `base.py` — 抽象基类
- `ProviderKind`（HTTP / PROXY / ENGINE 枚举；**EXTERNAL 占位已按 t23 决议删除**）、`Availability`（AVAILABLE / DEGRADED / UNAVAILABLE）、`ProviderMeta`（key 需求/匿名可用性/priority/terminal）。
- `DownloadProvider`（ABC）：`probe` / `download` / `cancel` / `resolve` / `should_fallback` / `is_configured`。
- 通用件：`_session`（复用 SteamAPI session）、`http_download`（**Range 断点续传 + stop_event 每 chunk 轮询取消 + 429 上报 `_report_throttle`**）。

#### `registry.py` — 注册表与熔断
- `_Circuit`（连续 3 次失败 → 60s 冷却 → half-open 探活）。
- `ProviderRegistry` 单例：`register` / `get_provider` / `record_failure` / `record_success` / **`build_chain(preferred, api)`**（用户首选 → 其余启用通道按 priority → steamcmd 链尾；跳过禁用/未配置/熔断冷却）/ `list_channels`（配置态通道列表供 UI 下拉）。
- `get_registry()` + `_register_builtin`（注册 cdn/ggnetwork/steamcmd）。

#### `cdn.py` — CDN 直链通道
- `CDNProvider`：`resolve`（需登录态 file_url）/ `download` / `should_fallback` / `cancel`。匿名自动回退。

#### `steamcmd.py` — SteamCMD 通道（链尾兜底）
- `SteamCMDProvider`：包装 `SteamCMDEngine`；**`terminal=True`，`should_fallback()=False`**——链到它即终止；默认通道=steamcmd 时链只有一条，行为与 1.3.9 逐字节一致。

#### `ggnetwork.py` — GGNetwork 匿名通道（试点）
- `GGNetworkProvider`：POST `api.ggntw.com/steam.request` 换官方 CDN 直链，无需 key。
- `_RateLimiter`（令牌桶 **20 req/min + 突发 3**，只限 resolve 的 POST 不限 CDN 传输；`rate_limit_per_minute` 用户可调）。
- `resolve`（**queue.position>0 返空串干净回退，不轮询**）/ `download` / `_maybe_extract`（zip 解压取 .gma）/ **`_verify_content`**（GMAD 魔数 + **>1% 尺寸差异 → FAILED 链内回退**，消息写明回退原因 + `_safe_remove` 清坏包残留）/ `should_fallback` / `cancel`。
- **诚实披露**：从未做过实网端到端验证（仅离线 mock）。

### `swdm/gui/` — PySide6 界面

#### `main_window.py` — 主窗口
- `MainWindow`：五标签页装配（工坊/下载/库/设置/调试，**调试 Tab 默认隐藏**，config 开关 + 条件 addTab，`debug_tab` 实例始终创建保住测试耦合）、系统托盘（`_build_tray`/`_show_from_tray`/`_notify_download_finished` 下载完成通知）、**`_real_quit`/`_do_real_quit`**（托盘真正退出）、`_create_app_mutex`/`_release_app_mutex`（单实例）、`closeEvent`、主题切换、状态栏。
- 信号接线：`library_changed`（无参槽 `_on_library_changed`）、`records_removed`→`remove_rows_for`。
- 溯源：t2（closeEvent/mutex）→ t11（托盘真正退出）→ t13（删除互通接线）→ t22（B④ 调试 Tab 隐藏）。

#### `workshop_tab.py` — 工坊浏览页（最大的 GUI 模块）
- `WorkshopTab`：游戏选择器（收藏/自定义 AppID/搜索联想下拉 `_fill_search_results`/`_on_game_enter` 回车待选链路）、标签栏（`_fetch_tags`/`_pick_tags`/`_on_tag_selection_changed`）、分页、卡片列表（`ModCardWidget` + `_ElidedLabel` 字符挤压）、批量勾选下载、**依赖下载**（`_download_with_deps`/`_on_deps_resolved`）、**详情页弹窗**（`_show_detail`/`_open_detail`）、**悬停预取**（`_do_prefetch_detail`，有用户请求在飞时跳过）、URL 导入（`_import_url`）、冲突标记（`_detect_conflicts`）。
- `_TagsFetchWorker`：标签抓取 QThread。
- 交互：`core/steam_api.py`、`core/game_search.py`、`gui/workers.py`、`gui/detail_dialog.py`、`gui/tag_bar.py`。
- 溯源：t1 → t3（GUI bug）→ t12（搜索 4 修）→ t13（切游戏清标签）→ t15（预取礼让）。

#### `downloads_tab.py` — 下载队列页
- `DownloadsTab`：实时进度行（`_ensure_row`/`_update_row`）、批量按钮（**`_toggle_pause_all` 暂停/继续合并单按钮**、重试失败、清除已完成、取消全部带确认）、`_remove_row`（已入库成功任务弹「同时从 mod 库移除？」）、`remove_rows_for`、`library_changed` 信号、`_sync_batch_buttons`（恒启用）。
- 溯源：t3 → t13（删除互通）→ t14（速度显示）→ t22（C② 按钮合并）。

#### `library_tab.py` — mod 库页
- `LibraryTab`：多维筛选（游戏/分类/标签/状态/关键词，`_current_filter`）、`refresh`（`_restore_combo` 恢复选择）、批量启用/禁用/分类/删除（右键菜单 `_context_menu`）、打开目录、**导出当前筛选结果**（`_export_list`）、导入列表、`records_removed` 信号、游戏名渲染（`games.game_name()`）。
- 溯源：t4 → t14（库分类）→ t13（删除互通）→ t16 决议 B③（导出筛选结果）。

#### `settings_tab.py` — 设置页
- `SettingsTab`：账号（匿名/手动登录、`_test_login`、keyring）、**通道动态下拉**（`_refresh_channel_combo` 由 `registry.list_channels()` 生成，tooltip 说明链式回退）、SteamCMD 部署、库目录、游戏安装目录表（增删改）、**打开数据目录**（`_open_data_dir`）、显示调试面板开关。
- `CollapsibleSection` 分组（内容上边距 10px，t13 间距加固）。
- 溯源：t3/t4 → t13（首行间距）→ t16 决议 B②（打开数据目录）→ **t21（通道动态列表）→ t28（list_channels 调用同步）**。

#### `detail_dialog.py` — mod 详情弹窗
- `ModDetailDialog`：描述/作者/评论/依赖/冲突/预览图（`PreviewImageWorker` 独立 QThread，`FlowLayout` 流式布局）。
- `DetailPageWorker`：详情页抓取 QThread（**传 `priority=True` 绕过端点等待**）。
- 解析器：`parse_description`/`parse_comments`/`comment_total`/`_norm_dep`/`_norm_conflict`。
- 依赖下载 `_download_dep` + 带依赖下载 `_on_download_with_deps`。
- 溯源：t3 → **t15（详情页性能：弹窗先 show 非模态 + 简介/占位先填 + 优先级）**。

#### `debug_tab.py` — 调试 Tab（默认隐藏）
- `DebugTab`：实时日志流（订阅 logger）、自动滚动开关、导出日志、下载历史（`_load_job_history`）、诊断（`_run_diagnostics`）。
- 溯源：t4 → t22（默认隐藏，开关在设置页）。

#### `tag_bar.py` — 标签筛选栏
- `TagBar`（横向滚动 chip 流）/ `TagChip` / `filter_nav_tags`（过滤导航类标签）/ `set_tags`/`clear_selection`/`selected`。
- 溯源：t3 → t12（标签精确过滤）→ t13（切游戏 clear_selection）。

#### `workers.py` — QThread/QThreadPool 桥接
- `BrowseWorker`（列表抓取，代际号丢弃过期结果）、`ImageLoader`（`_ImageTask`/`_ImageDownloadTask` + LRU 缓存 + `_ImageSignalBus` url→索引 O(1) 回调）、`DownloadEventBridge`（下载事件桥接 GUI）、`LoginWorker`、`DependencyResolveWorker`。
- 溯源：t3 → t4（图片 O2 主线程下载移入子线程）。

#### `widgets.py` — 通用组件
- `CollapsibleSection`、`LoadingSpinner`、`LoadingOverlay`、`SmoothScrollBar`（动画滚动）、`ElidedLabel`（省略号标签）、`ModCard`（浏览卡片，setData/data/mousePressEvent）。
- 溯源：t3 → t13（CollapsibleSection 间距）→ t1.3.7 手感批次（`ElidedLabel` 字符挤压）。

#### `styles.py` — 主题
- `qss(theme)`：深色/浅色 QSS 字符串。

#### `services.py` — 服务容器
- `Services`：聚合 api/engine/library/downloader 实例；`refresh_engine`/`refresh_api`。
- **`build_services():78` 构造 `DownloadManager` 传 `api=api`**（t21 修复的 1.3.9 缺陷：CDN 通道缺 api 几乎必然回退）。

---

## tests/ — 测试套

- **入口**：`run_all.ps1`（串行，`QT_QPA_PLATFORM=offscreen` + `PYTHONUTF8=1`，读 RESULT 行）。
- **规模**：59 脚本，1.4.0 基线 57 PASS / 2 FAIL（`test_legacy_format` 字节数漂移、`test_page_parser` 旧标签夹具——1.3.8 起既有非回归）/ 0 NORESULT。
- **核心套**：`test_core_sweep` / `test_download_fixes` / `test_cdn` / `test_throttle`（脚本式 `check()+sys.exit`）/ `test_batch1-3`。
- **GUI 套**：`test_gui_sweep`（118 项）/ `test_gui_offline` / `test_gui_fixes` / `test_all_buttons` / `test_cross_features`（关联交互）/ `test_widgets`。
- **1.4.0 新增**：`test_providers.py`（**84 项**，t21 建 74 项 + t28 扩 10 项）、`test_ap1_cancel_race.py`（16 项）、`test_t22_1310.py`（27 项）。
- **1.3.9 新增**：`test_rettest_139.py`（42 项）、`test_game_search_fix.py`（38 项）、`test_download_stats.py`（40 项）、`test_detail_perf.py`（17 项）、`test_uninstall_fix.py`（22 项）。
- 工具脚本（不入库类）：`save_detail_pages.py`/`analyze_detail.py`/`find_deps_page.py`/`verify_real_deps.py`/`_probe_detail_timing.py`（夹具与实测辅助）。

---

## docs/ — 文档

- **changelog**：`changelog_1.3.8.md` / `changelog_1.3.9.md` / `changelog_1.4.0.md`（十节，含评审占位由 t27 回填）。
- **评审**：`feature_review_1.3.8.md` / `feature_review_1.3.9.md` / `feature_review_1.4.0.md`（五方零反对）。
- **工程日志**：`engineering_log.md`（510 行，t1-t28 全记录，recorder 维护）。
- **架构**：`provider_architecture_1.4.0.md`（provider 六件套设计 + 待办 + t28 清理记录）。
- **规范**：`git_workflow.md`（本系列：提交规范/语言政策）。
- 历史：`algo_optimizations.md`/`ux_improvements.md`/`net_optimizations.md`/`new_features.md`/`qa_report.md`/`improvement_plan_1.3.7.md`/`打包说明.md`。

---

## research/ — 调研

- **provider**：`provider_research.md`（4 provider 实测：GGNetwork 唯一匿名可用；steamwebapi.com/Nether/SWD 排除理由）、`provider_adaptation.md`（适配设计：15 处硬编码清单 + providers/ 包设计）。
- **429 系列**：`steam_429_research.md`/`steam_429_403_research.md`/`steam_429_download_research.md`（请求头指纹限流实证）。
- **其他**：`steam_game_search.md`（storesearch 选型）、`steam_tag_filter_research.md`（Wayback 三快照实证标签结构）、`workshop_api_research.md`/`competitor_analysis.md`。
- 快照：`_browse_snapshot.html`/`_browse_legacy.html`/`_browse_2024.html`（抓取夹具，忽略入库）。

---

## installer/ — 打包

- `swdm.iss`：Inno Setup 脚本（**`SWDMVersion` 在 :14**，t24 改 1.4.0）。
- `make_icon.py`：图标生成。
- `Output/`：安装包产物（忽略入库）；**1.4.0：`SWDM-Setup-1.4.0.exe` 42.69 MB**。
- 构建链：`python -m PyInstaller swdm.spec --noconfirm` → ISCC（49.4s）→ 安装包；providers/ 全静态 import，spec 无需改动即可收集新子包。
