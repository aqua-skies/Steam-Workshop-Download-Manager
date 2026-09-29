# SWDM — Steam 工坊下载管理器

> 一套桌面程序：浏览/搜索 Steam 创意工坊、**无需 Steam 账号**匿名下载 mod、本地 mod 库分类管理，并打包为完整安装包。

## 核心能力

| 需求 | 实现 |
|---|---|
| ① 指定游戏拉取工坊列表，分类/搜索/热度排名 | 游戏选择器（可收藏/自定义 AppID）→ `/workshop/browse/` 抓取 + `GetPublishedFileDetails` 批量补全元数据；支持关键词搜索、标签过滤、6 种排序（趋势/最新/订阅/评分/浏览/收藏），元数据补全后客户端重排保证"热度排名"准确；分页浏览 |
| ② 下载的 mod 便于分类/检索 | SQLite 本地库：按游戏/分类/标签/状态/关键词多维检索；mod 目录旁写 `swdm_meta.json` 元数据；批量启用/禁用、分类、删除、打开目录 |
| ③ 功能全面的 GUI | PySide6 五标签页：工坊浏览 / 下载队列（实时进度条） / 我的 mod 库 / 设置（高级） / 调试（实时日志流）；系统托盘、单实例、全局崩溃日志 |
| ④ 无账号下载免验证 mod | SteamCMD `login anonymous` + `workshop_download_item`，**实测匿名下载成功**；匿名失败时可切换手动登录（含 Steam Guard、keyring 加密存密码） |

## 快速开始

```bash
pip install -r requirements.txt
python -m swdm.app        # 或 python swdm/app.py
```

首次启动自动检测系统已安装的 SteamCMD（如 `C:\Program Files (x86)\steamcmd\steamcmd.exe`）；
若未安装可在「设置 → SteamCMD 引擎」一键部署（从官方 CDN 下载解压）。

## 技术架构

```
swdm/
├── app.py                     # 入口（main + 单实例 + 高 DPI）
├── core/                      # 核心层（GUI 无关，可独立测试）
│   ├── steam_api.py           # Web API 客户端（免 key 元数据/合集/浏览抓取/图片缓存）
│   ├── steamcmd_engine.py     # SteamCMD 子进程托管（匿名登录/进度解析/自动部署/登录测试）
│   ├── downloader.py          # 下载队列 + 并发调度 + 自动重试 + 入库
│   ├── mod_library.py         # SQLite mod 库（检索/分类/启用禁用/元数据旁车）
│   ├── auth.py                # 匿名 / 手动登录（keyring 加密）
│   ├── config.py              # 持久化配置（JSON，递归合并）
│   ├── games.py               # 内置 59 个支持工坊的游戏 + 自定义游戏
│   ├── logger.py              # 轮转文件日志 + 内存环形缓冲 + GUI 订阅
│   └── paths.py               # 数据目录（支持便携模式）
├── gui/                       # PySide6 界面
│   ├── main_window.py         # 主窗口/托盘/菜单/异常处理
│   ├── workshop_tab.py        # 浏览/搜索/下载卡片
│   ├── downloads_tab.py       # 进度队列与历史
│   ├── library_tab.py         # mod 库管理
│   ├── settings_tab.py        # 全部设置 + 登录
│   ├── debug_tab.py           # 实时日志
│   ├── workers.py             # QThread/QThreadPool 桥接核心回调
│   ├── services.py            # 服务容器
│   └── styles.py              # 深色/浅色主题
└── resources/icon.ico

tests/   冒烟测试（核心链路 + GUI 自动化）
installer/swdm.iss   Inno Setup 安装包脚本
swdm.spec            PyInstaller 打包规格
```

## 关键技术决策（均经实测）

1. **HTTPS 证书**：本机存在 TLS 拦截，certifi 不可用 → 强制 `truststore.inject_into_ssl()` 走系统证书存储。
2. **浏览器 UA**：默认 python-requests UA 访问社区页面返回错误页 → 全局 Chrome UA。
3. **免 key API**：`GetPublishedFileDetails` / `GetCollectionDetails` 不需要 API key（`itemcount` + `publishedfileids[i]` 下标格式）；`QueryFiles` 需要 key，作为可选增强（用户在设置中填入）。
4. **HTML 抓取**：社区站已 React 重构、类名随机混淆 → 只用稳健的 `<a href=?id=><img alt=标题 src=预览图>` 正则提 ID/标题/图，其余元数据全部走 API。
5. **下载引擎**：SteamCMD 匿名模式为主，解析 `Success. Downloaded item {id} to "..." ({bytes} bytes)`；失败时按消息区分（登录失败/不支持匿名/超时），支持自动重试与取消。
6. **Qt 线程安全**：QPixmap 只在主线程构造，子线程仅做网络 I/O 与路径解析。

## 数据目录

- Windows：`%APPDATA%\SWDM\`（config.json、logs/、library.db、cache/、mods/、steamcmd/）
- 便携模式：项目根目录放 `portable.marker` 文件，数据改存 `<根>/data/`

## 测试

```bash
python tests/test_smoke.py    # 核心链路：浏览→元数据→匿名下载→入库→检索（23 项断言）
python tests/test_gui.py      # GUI 自动化：启动→浏览→下载→各页截图→退出（输出 tests/shots/）
```

## 打包

```bash
python -m PyInstaller swdm.spec          # 产出 build/dist/SWDM/
ISCC installer\swdm.iss                  # 产出安装包（需 Inno Setup 6）
```

详见 `docs/打包说明.md`。

## 已知限制

- 匿名下载仅支持"工坊内容不需要游戏所有权验证"的游戏（实测 Garry's Mod 支持；部分付费游戏会失败，此时切换手动登录）。
- 工坊浏览页分类标签由 API 返回的 `tags` 字段提供客户端过滤；服务端标签筛选依赖 `requiredtags[]` 参数。
- 首次使用某个游戏的工坊时 SteamCMD 可能需更新自身，耗时较长。
