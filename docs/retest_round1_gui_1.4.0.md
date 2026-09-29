# SWDM 1.4.0 复测报告 · 第一轮（GUI / 用户视角）

- 复测人：gui-tester（t25，attempt 3c34fb73-f63e-44cf-8582-f56e4fef77a4）
- 复测时间：2026-09-29
- 复测对象：**1.4.0 打包终态**（installer\Output\SWDM-Setup-1.4.0.exe，42.69 MB，
  2026-09-29 13:30；版本号双端 1.4.0：paths.py:9 + swdm.iss:14）
- 测试环境：PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen，import swdm 前设 APPDATA 临时目录
- 结论：**无异常通过**。55 项用户视角检查全 PASS；全量回归 61 脚本
  59 PASS / 2 既有非回归 / 0 NORESULT，零新增失败。

## 一、打包终态确认

| 项目 | 值 |
|---|---|
| 安装包 | installer\Output\SWDM-Setup-1.4.0.exe，42.69 MB |
| paths.py APP_VERSION | 1.4.0 |
| swdm.iss SWDMVersion | 1.4.0（OutputBaseFilename=SWDM-Setup-1.4.0） |

## 二、全量回归（tests/run_all.ps1）

```
SUMMARY: pass=59 fail=2 noresult=0 total=61
FAILED: test_legacy_format, test_page_parser
```

- 2 FAIL 为 **1.3.8 起既有非回归**（legacy_format 字节漂移、page_parser 旧 fixture），
  1.3.9（t18）与 1.4.0（t24/t26）各轮结果一致，非本次新增。
- 0 NORESULT。test_rettest_140（本轮新增）在 run_all 内 PASS。
- 旁证：未过滤的 75 脚本裸跑额外失败的脚本（test_game_dir_e2e / test_multi_game /
  test_stress / test_widgets / test_acceptance 等）全部属于 run_all.ps1 的
  live-network skip 名单，是本机 fake-IP 代理环境所致，非产品缺陷。

## 三、用户视角检查（tests/test_rettest_140.py，55 项 ALL PASS）

### A. U1–U12 回归（t21/t22 改动未破坏 1.3.9 既有修复）

| 检查 | 结果 |
|---|---|
| U1 托盘隐藏态直退（_real_quit 触发 quit + _force_quit 置位 + _do_real_quit 存在） | PASS ×3 |
| U4 回车待选链路（_pending_enter_select 挂载 → _on_search_ready 自动选中首项） | PASS ×2 |
| U5 标签精确过滤（交集，过滤后卡片 = 预期子集） | PASS |
| U6 切游戏清标签 + 清过滤输入 | PASS ×2 |
| U7 速度采样（滚动窗口 1–30 MB/s 合理 / 达 total 直返 100% / 10Hz 有有效快照下发） | PASS ×3 |
| U8 突发 20 MB 被摊平（峰值 <50 MB/s，无 2–300 MB/s 假速度） | PASS |
| U9 设置页几何（分组区存在 / 相对坐标非负无挤压 / 目录表行高 ≥24） | PASS ×3 |
| U10 删除互通（库真实删除 → records_removed → 下载页行清除） | PASS |
| U11 删除后列表无残留 + 库行游戏名行内渲染（Garry's Mod） | PASS ×2 |
| U12 详情页缓存命中不走网络（_page_cache，_community_get 零调用，<0.5 s） | PASS |

### B. provider 链新行为（1.4.0 核心）

| 检查 | 结果 |
|---|---|
| B1 通道下拉含 steamcmd/cdn/ggnetwork 三通道 + 可用性标记文案 | PASS ×2 |
| B2 通道切换写入 config.download.channel | PASS |
| B3 CDN 匿名无直链 → FAILED + 回退提示含「SteamCMD」+ should_fallback=True | PASS ×3 |
| B4 链尾永远是 steamcmd / 首选通道在链首 / **terminal 通道豁免熔断** | PASS ×3 |
| B5 cdn 连续失败 3 次后被链构造跳过，链尾仍是 steamcmd | PASS ×2 |
| B6 ggnetwork queue.position>0 → resolve 返空串（干净回退，不轮询） | PASS |
| B7 坏包（>1% 尺寸差异）消息含回退原因 + should_fallback=True | PASS ×2 |
| B8 ggnetwork requires_key=False（匿名可用，无需配置 Key） | PASS |

**B4c 说明**：terminal 豁免通过生产路径验证——把 _run_provider 桩成全失败跑真实
_run_channel_chain，之后 build_chain("steamcmd") 仍含 steamcmd（熔断器未被累计）；
作为对照，cdn 同样路径连续 3 次失败后确实被链构造跳过（B5）。

### C. t22 GUI 项

| 检查 | 结果 |
|---|---|
| C1 默认无调试 Tab / debug_tab 实例常在 / 开关默认关闭 / 开关写入 config | PASS ×4 |
| C2 暂停/继续单按钮（文本正确切换）+ 重试失败/清除已完成独立 + mgr.paused 复位 | PASS ×5 |
| C3 搜索最低间隔 0.7 s / ConnectionError → 15 s 冷却 / 冷却内返空 / 缓存即时 / 本地联想即时 | PASS ×5 |

### D. 关联交互

| 检查 | 结果 |
|---|---|
| D1 链内回退不消耗 auto_retry（一次 attempt 跑通首通道）+ job.channel 记录实际通道 | PASS ×2 |
| D2 _current_filter 存在（导出当前筛选）+ 导出按钮可触发导出路径 | PASS ×2 |

## 四、诚实披露

1. **GGNetwork 真下载未实测**：本机 steamcommunity.com 走 fake-IP 代理（DNS→
   198.18.0.124），run_all 的 live-network 脚本全在本环境失败，无法完成真实下载
   冒烟。本轮验证的是 ggnetwork 的匿名可用性（requires_key=False）、排队守卫
   （B6）、坏包回退（B7）与链内位置（B1/B4），**未验证真实端到端下载成功率**。
   建议在 1.4.1 前由有真实网络环境的一方补测，或维持当前只读型匿名试点定位。
2. **读图工具本机不可用**（sharp ERR_DLOPEN_FAILED / modlens key 无效）：
   GUI 视觉类检查以几何量化兜底（mapTo 相对坐标 + 行高断言），未做像素级截图比对。
3. 既有非回归 test_legacy_format / test_page_parser 仍保持 1.3.8 起的失败状态，
   与版本基线一致，未修复也未恶化。

## 五、结论

1.4.0 打包终态从 GUI / 用户视角复测**无异常**：12 项用户 bug 修复全部保持、
provider 链新行为（通道 UI / 匿名降级 / 链尾兜底 / 熔断 / 坏包回退）按设计工作、
t22 GUI 三项落地且无回归、关联交互正常。交付闸门 GUI 侧第一轮复测通过。
