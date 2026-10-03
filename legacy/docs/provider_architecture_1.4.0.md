# SWDM 1.4.0 多 Provider 下载架构

> **English summary**: This document specifies SWDM's multi-provider download architecture
> (introduced in 1.4.0). A download runs a *channel chain* built by `ProviderRegistry`:
> the user's preferred channel first, then other enabled channels by priority, always with
> `steamcmd` as the terminal fallback. One chain counts as one attempt — failing over inside
> the chain does not consume the auto-retry budget. A circuit breaker (3 failures → 60s
> cooldown) skips channels that are currently failing. Channel set: `steamcmd` (ENGINE,
> anonymous, terminal), `cdn` (HTTP direct link, needs login), `ggnetwork` (anonymous
> third-party PROXY, experimental, rate-limited to 20 req/min, bad-package detection with
> in-chain fallback). The legacy `cdn_downloader.py` remains as a compatibility facade until
> 1.4.1. Sections below are in Chinese.

> 状态：已实现（t21），1.4.0 已交付（t27 六方一致）。设计依据：research/provider_adaptation.md · 调研：research/provider_research.md
> 测试：tests/test_providers.py（84 项 ALL PASS）+ 全量回归零新增失败

## 1. 架构

```
DownloadManager._exec_job
   └─ _run_channel_chain(job, install_dir, smoother)
        ├─ _build_channel_chain(preferred)   ← ProviderRegistry.build_chain()
        │     顺序：用户首选 → 其余启用通道（按 priority）→ steamcmd 链尾兜底
        │     跳过：用户禁用 / 未配置 key / 熔断冷却中
        └─ 遍历链：成功即返；should_fallback()=False 中断；stop_event 停链
              一条链 = 一次 attempt（回退不消耗 auto_retry）
```

`swdm/core/providers/`：

| 文件 | 职责 |
|---|---|
| `base.py` | ABC `DownloadProvider`（probe/download/cancel/resolve/should_fallback/is_configured）+ `ProviderMeta`（key 需求/匿名可用性/priority/terminal）+ 通用件 `http_download`（Range 续传 + stop_event 轮询取消 + 429 上报）+ `_session`（复用 SteamAPI session） |
| `registry.py` | `ProviderRegistry` 单例：注册、`build_chain`（链构造）、60s 探测缓存、`_Circuit` 熔断（3 次失败冷却 60s，半开期一次失败即重熔）、`list_channels`（UI 下拉） |
| `cdn.py` | CDN 直链通道（自 `cdn_downloader.py` 平迁） |
| `steamcmd.py` | SteamCMD 包装（`terminal=True` 链终结者，行为与 1.3.9 一致） |
| `ggnetwork.py` | GGNetwork 试点（匿名 PROXY） |

兼容门面：`swdm/core/cdn_downloader.py` 保留 `resolve_file_url` / `download_file` / `download_item_cdn`，test_cdn / test_core_sweep 零改动。

## 2. 通道清单

| name | 型 | 匿名 | key | priority | 说明 |
|---|---|---|---|---|---|
| `cdn` | HTTP | ✗（需登录态 file_url） | 否 | 10 | 登录态高速直链；匿名自动回退 |
| `ggnetwork` | PROXY | ✓ | 否 | 20 | POST `api.ggntw.com/steam.request` 换官方 CDN 直链 |
| `steamcmd` | ENGINE | ✓ | 否 | 100 | 链尾兜底，`terminal` |

匿名可用性是核心卖点：需 key 的通道未配置时 `is_configured()=False`，链构造直接跳过（不报错、不中断下载）。默认通道仍为 `steamcmd`（稳定），用户可在设置页下拉切换。

## 3. GGNetwork 试点要点

- **自律限速**：令牌桶 `_RateLimiter`，默认 20 req/min + 突发 3（ToS §5.2.2 禁 excessive server load）
- **熔断**：429 经 `on_throttle_signal` 上报 manager 退避；连续失败由 registry `_Circuit` 冷却
- **压缩包**：`_maybe_extract` 检测 zip → 解压取 `.gma` 到 `content/<appid>/<itemid>`，删原包
- **弱校验**：`.gma` 魔数 `GMAD`；实际大小与声明差异 >1% → 消息带 ⚠（仅提示，不回退）

## 4. config 扩展

```json
"download": {
  "channel": "steamcmd",
  "providers": {
    "steamcmd": {"enabled": true},
    "cdn": {"enabled": true},
    "ggnetwork": {"enabled": true, "rate_limit_per_minute": 20}
  }
}
```

`_merge` 三层嵌套合并：用户只改 `ggnetwork.rate_limit_per_minute` 不会丢失其他通道配置。设置页 `channel_combo` 由 `registry.list_channels()` 动态生成（不探测网络，只反映启用态）。

## 5. 顺带修复

`services.py:78`：`DownloadManager` 构造未传 `api` → 登录态 CDN 通道无法补全 `file_url`，几乎必然回退。已补 `api=api`。

## 6. 关键设计决策

- **steamcmd 永远链尾且 terminal**：`should_fallback()=False`，链到它即终止。默认通道=steamcmd 时链只有一条，行为与 1.3.9 完全一致。
- **回退不消耗 auto_retry**：链内回退是通道切换，不是重试；只有整条链失败才进入重试计数。
- **取消双层**：非 steamcmd provider 靠 `job._stop` 每 chunk 轮询（http_download 内）；steamcmd 靠 engine.cancel()（既有链路）。
- **should_fallback 结构化判定**：替代 1.3.9 的"消息含'回退'"字符串判定，子类可收窄（如"key 无效"类配置错误不回退）。

## 7. 待办（1.4.1 后）

- ~~`ProviderKind.EXTERNAL` 占位~~ → **已按 t23 讨论组决议移除**（2:1，YAGNI）；steamworkshop.download 兜底**移出路线图**（调研结论：低增量价值——返回同一官方 CDN URL，本程序 CDN 通道自己能 resolve；HTTP-only、无 API、半废弃、社区口碑差；匿名场景已被 ggnetwork 覆盖）
- ggnetwork 探测目前用固定物品 id（2537024972），服务端变更后需换
- 端到端实网验证（本机出口 IP 曾被限，匿名接口需实测确认 20/min 自律值）
- `cdn_downloader.py` 兼容门面 1.4.1 移除（新代码直接用 `swdm.core.providers.cdn`）

## 8. t28 打包前清理（2026-09-29）

t23 讨论组决议的 7 项打包前清理，详见 `docs/feature_review_1.4.0.md`：

1. 删 `downloader.py` 死方法 `_download_via_cdn`（链改造后零调用方）
2. 删 registry 的 60s 探测缓存 + `list_channels(probe_results=...)` 参数（UI 只用配置态，零生产探测路径）
3. 删 `ProviderKind.EXTERNAL` 占位（本文档第 7 节同步）
4. ggnetwork 尺寸差异 >1% 从 ⚠ 提示升级为**判失败 + 链内回退**（比较解压后 .gma 实际字节 vs Steam 声明原始值；坏包清残留后回退 steamcmd，不消耗 auto_retry）
5. ggnetwork `resolve()` 加 `queue.position>0` 守卫（服务端排队中返空串干净回退，不轮询）
6. `cdn_downloader.py` 顶部加"1.4.1 移除"注释
7. **熔断器接生产调用方**：链循环里 SUCCESS→`record_success`、FAILED→`record_failure`（CANCELLED 与 terminal 通道豁免）——评审发现 `_Circuit` 此前 inert（永不 trip）
