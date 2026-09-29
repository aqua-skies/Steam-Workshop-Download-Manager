# SWDM — Steam 工坊下载管理器

> 一套桌面程序：浏览/搜索 Steam 创意工坊、**无需 Steam 账号**匿名下载 mod、本地 mod 库分类管理。

## 核心能力

| 需求 | 实现 |
|---|---|
| ① 指定游戏拉取工坊列表，分类/搜索/热度排名 | 游戏选择器（可收藏/自定义 AppID）→ `/workshop/browse/` 抓取 + `GetPublishedFileDetails` 批量补全元数据；支持关键词搜索、标签过滤、6 种排序（趋势/最新/订阅/评分/浏览/收藏），元数据补全后客户端重排保证"热度排名"准确；分页浏览 |
| ② 下载的 mod 便于分类/检索 | SQLite 本地库：按游戏/分类/标签/状态/关键词多维检索；mod 目录旁写 `swdm_meta.json` 元数据；批量启用/禁用、分类、删除、打开目录 |
| ③ 功能全面的 GUI | PySide6 五标签页：工坊浏览 / 下载队列（实时进度条） / 我的 mod 库 / 设置（高级） / 调试（实时日志流）；系统托盘、单实例、全局崩溃日志 |
| ④ 无账号下载免验证 mod | 基于 SteamCMD `login anonymous` + `workshop_download_item`; 匿名失败时可切换手动登录（含 Steam Guard、keyring 加密存密码） |

## 快速开始

```bash
pip install -r requirements.txt
python -m swdm.app        # 或 python swdm/app.py
```

首次启动自动检测系统已安装的 SteamCMD ；
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

```

## 数据目录

- Windows：`%APPDATA%\SWDM\`（config.json、logs/、library.db、cache/、mods/、steamcmd/）
- 便携模式：项目根目录放 `portable.marker` 文件，数据改存 `<根>/data/`

## 已知限制

- 匿名下载仅支持"工坊内容不需要游戏所有权验证"的游戏。
- 工坊浏览页分类标签由 API 返回的 `tags` 字段提供客户端过滤；服务端标签筛选依赖 `requiredtags[]` 参数。
- 首次使用时 SteamCMD 可能需更新自身，耗时较长。
