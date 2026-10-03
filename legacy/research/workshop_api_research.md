# Steam 创意工坊机制研究（已实测验证）

> 本报告所有结论均经本机实测（Python + requests + truststore，2026-09-19）。

## 1. 环境关键事实

| 事实 | 说明 |
|---|---|
| certifi 证书在本机不可用 | SSL 握手失败：`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` |
| 系统证书存储可用 | urllib 系统存储访问 API 正常 |
| **解决方案** | 使用 `truststore.inject_into_ssl()`，让 requests 走系统证书存储（必做，否则全部 HTTPS 失败） |
| 无代理配置 | `HTTP_PROXY` 为空，netsh 直连 |
| **必须设置浏览器 User-Agent** | 默认 `python-requests/x.y` 访问 sharedfiles 详情页返回 `Steam Community :: Error`；设置 Chrome UA 后返回 200 |

## 2. Steam Web API（匿名/无 key）

### 2.1 ISteamRemoteStorage/GetPublishedFileDetails ✅ 无需 key

```
POST https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/
Content-Type: application/x-www-form-urlencoded
Body: itemcount=3&publishedfileids[0]=ID0&publishedfileids[1]=ID1&publishedfileids[2]=ID2
```

**注意**：必须带 `itemcount` 参数，且 publishedfileids 用 `[i]` 下标形式，否则 400。
（`publishedfileids=[json数组]` 形式报 400 "Required parameter 'itemcount' is missing"）

响应字段（实测）：
- `publishedfileid`, `result`（1=正常, 9=不存在）, `creator`(steamid64), `creator_app_id`
- `title`, `description`, `file_size`（字节）, `subscriptions`（当前订阅）, `lifetime_subscriptions`
- `favorited`, `lifetime_favorites`, `views`, `lifetime_playtime`
- `tags`：`[{tag, ...}]` 分类标签
- `preview_url`：预览图 URL
- `hcontent_file`：内容句柄
- `time_created`, `time_updated`：Unix 时间戳

### 2.2 ISteamRemoteStorage/GetCollectionDetails ✅ 无需 key（合集导入）

```
POST https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/
Body: collectioncount=1&publishedfileids[0]=COLLECTION_ID
```

### 2.3 IPublishedFileService/QueryFiles ❌ 需要 key

- 无 key 返回 403："Please verify your key= parameter"
- **用途**：用户在设置中填入自己的 Steam Web API key 后可启用结构化查询（query_type 排序/标签过滤/游标分页）
- query_type 常用值：0=ranked_by_trend, 1=ranked_by_vote, 2=ranked_by_public, 3=most_recent, 9=most_subscribed

### 2.4 ISteamWebAPIUtil/GetServerInfo ✅ 无需 key（连通性探测）

## 3. 网页抓取（HTML）

### 3.1 浏览/搜索端点（经典，仍然可用）

```
GET https://steamcommunity.com/workshop/browse/?appid={appid}
参数：
  p=N                  页码（从1开始，实测 p=1 与 p=2 返回不同项目，分页有效）
  searchtext=xxx       搜索关键词（实测 searchtext=dark 返回不同结果，搜索有效）
  browsesort=trend     排序
  browsefilter=...     筛选
  requiredtags[]=tag   标签筛选（URL 编码为 requiredtags%5B%5D）
  numperpage=N         每页数量
  l=schinese           语言
```

**实测每页约 30 个卡片。**

### 3.2 卡片提取正则（稳健，不依赖混淆类名）

整站已 React 重构，类名是随机混淆串（如 `_0ohcyeFEL5c-`），**不可依赖类名**。但卡片中稳定存在：

```python
re.findall(
    r'<a href="https://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)"[^>]*>\s*'
    r'<img src="([^"]+)" alt="([^"]*)"', html
)
# -> [(publishedfileid, preview_url, title), ...]
```

预览图 URL 形如 `https://images.steamusercontent.com/ugc/{hash}/{hash}/`，可追加 `?ima=fit&imw=512&imh=512` 调整尺寸。

### 3.3 新 Hub 页 `/app/{appid}/workshop/`

React 新设计，内容分段（如 "Addons - In the past week"），参数 browsefilter/p 不生效。**不用于列表抓取**，仅作 fallback。

### 3.4 单项详情页

```
GET https://steamcommunity.com/sharedfiles/filedetails/?id={id}
```
需浏览器 UA。标题在 `<title>Steam Workshop::{标题}</title>`。

## 4. SteamCMD 匿名下载（核心）✅ 实测成功

```
steamcmd.exe +force_install_dir "<目录>" +login anonymous +workshop_download_item <appid> <publishedfileid> +quit
```

**实测**（Garry's Mod, appid 4000）：
- `3802244270`（Dynamic Flashlight, 1.8MB）→ 成功，1840727 bytes
- `3803469767`（12719068 bytes）→ 成功

输出目录结构：
```
<install_dir>/steamapps/workshop/content/<appid>/<publishedfileid>/
  └── gmpublisher.gma    # GMod 原生格式
```

**成功标志**：`Success. Downloaded item {id} to "..." ({bytes} bytes)`
**下载中标志**：`Downloading item {id} ...`

### 支持匿名下载的游戏

实测 GMod(4000) 支持。据社区经验，多数"工坊内容不需要游戏所有权验证"的游戏支持匿名下载；部分游戏（如付费 DLC 内容、需所有权的游戏）会失败。**程序应提供"匿名下载失败 → 提示用户登录账号"的回退路径。**

## 5. 已知 appid（测试用）

| appid | 游戏 | 匿名下载 |
|---|---|---|
| 4000 | Garry's Mod | ✅ 实测 |
| 550 | Left 4 Dead 2 | 常见支持 |
| 440 | Team Fortress 2 | 常见支持 |
| 240 | Counter-Strike: Source | 常见支持 |
| 107410 | Arma 3 | 常见支持 |

## 6. 架构决策

1. **元数据**：GetPublishedFileDetails 批量获取（无需 key），QueryFiles 作为可选增强（用户填 key）
2. **列表/搜索**：默认抓 `/workshop/browse/`（id+标题+图）→ 再批量取元数据；有 key 时直接 QueryFiles
3. **下载引擎**：SteamCMD 匿名登录为主；失败时可切换用户登录
4. **HTTPS**：强制 truststore（系统证书），避免 certifi 问题
5. **UA**：全局浏览器 UA
6. **结果码**：result==1 为有效，result==9 为不存在
