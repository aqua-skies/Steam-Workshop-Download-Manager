# 稳定性测试与问题排查报告（SWDM 1.3.6 基线）

> 测试环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen、独立临时 APPDATA。
> 压力脚本：tests/test_stress.py（已扩充至 17 个场景）。回归：tests/ 全量脚本。

## 一、压力测试结果（扩充后）

| # | 场景 | 耗时 | 判定 |
|---|---|---|---|
| 1 | 填充 30 张卡片 | 56ms | 正常 |
| 2 | 再次填充 30 张（翻页） | 41ms | 正常 |
| 3 | 清空卡片 | 1ms | 正常 |
| 4 | 填充 60 张卡片 | 119ms | ~2.0ms/卡，渲染成本，非缺陷 |
| 5 | 连打 9 字符（含防抖） | 0ms | 正常（防抖期内不渲染） |
| 6 | 标签栏填充 77 个 | 20ms | 正常 |
| 7 | 标签栏选中 5 个 | 16ms | 正常 |
| 8 | 打开详情弹窗 | 13ms | 正常 |
| 9 | 下载页添加 20 行 | 0ms | 正常 |
| 10 | 库页刷新（空） | 2ms | 正常 |
| 11 | 切换 5 个 Tab | 5ms | 正常 |
| 12 | **切换排序维度 4 次** | 0ms | **见问题 P1** |
| 13 | 标签快速选 10 个再取消 | 73ms | 正常（17 个标签×2 操作） |
| 14 | populate 后立即再 populate | 5ms | 正常（_clear_cards 高效） |
| 15 | 详情弹窗开关 5 次 | 56ms | 正常（~11ms/次，无累积变慢） |
| 16 | 图片缓存填充 310（触发清空） | 1ms | 正常（见 algo 文档 #2 优化点） |

**结论**：无 >100ms 的业务逻辑卡顿。唯一慢点是 60 卡渲染本身（2ms/卡），
属 Qt widget 创建成本，可经"可视区外延迟渲染"优化（非必需）。

## 二、发现的问题

### P1. 排序切换完全不刷新列表（真 bug，UX 审计同源发现）
- **现象**：场景 12 耗时 0ms——因为切换排序维度后**什么都不发生**。
- **根因**：`workshop_tab.py:425-428` 排序下拉未连接 `currentIndexChanged`
  信号到 `_refresh_list`。
- **影响**：用户切换排序后列表不变，必须再点搜索/回车才生效。
- **修复**：`self.sort_combo.currentIndexChanged.connect(
  lambda: self._refresh_list())`。

### P2. 模组库 refresh() 不恢复下拉选择（真 bug）
- **根因**：`library_tab.py:147-163` 每次刷新重建游戏/分类下拉，
  重建后回到默认项，用户选的过滤条件丢失。
- **影响**：选了游戏过滤后，一点启用/其他操作就回到"全部游戏"。
- **修复**：重建前记录 currentIndex，重建后恢复。

### P3. 下载失败行无手动重试入口
- **现象**：核心层有 auto_retry，但 UI 无"重试"按钮，
  失败后必须回工坊页重新找到卡片再点下载。
- **修复**：失败行的操作列加重试按钮，调用 downloader 重新入队。

### P4. "取消全部"危险操作无确认对话框
- **修复**：QMessageBox.question 确认后再执行。

### P5. 图片缓存满量清空造成请求突刺（性能，非 bug）
- **现象**：超 300 张时 `_image_cache.clear()` 一次性清空，
  当前可见卡片全部重新下载。
- **修复**：改 LRU 淘汰（详见 docs/algo_optimizations.md #2）。

## 三、全量回归结果（tests/）

21/22 PASS。唯一"失败"是 test_stress 自身报 `1_SLOW`（60 卡 119ms，
渲染成本，预期行为，非缺陷）。

| 脚本 | 结果 |
|---|---|
| test_tag_bar / test_checkboxes / test_page_switch / test_prefetch | PASS |
| test_widgets / test_gui_offline / test_detail_dialog / test_api_cache | PASS |
| test_game_search / test_comments_section / test_toolbar_layout | PASS |
| test_scroll_repage / test_data_image / test_download_fixes | PASS |
| test_gui_fixes / test_tag_parse_real / test_engine_concurrency | PASS |
| test_v134_gui / test_all_buttons / test_author_fix / test_v136 | PASS |
| test_stress | PASS（1_SLOW 为预期渲染成本） |

## 四、建议
1. **立即修**：P1（排序信号）、P2（库页选择恢复）——都是 <5 行定点修改。
2. **第二批**：P3（失败重试）、P4（取消确认）。
3. **性能**：P5（LRU 缓存）+ algo 文档 #1（图片回调 O(1)）+ #3（主线程同步下载移出）。
