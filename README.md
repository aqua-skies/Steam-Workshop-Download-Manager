# SWDM 2.0 · Steam 工坊下载管理器（C# WPF）

2.0 重构：摒弃 1.x Python/PySide6 代码路径，保留弯路教训与 Steam community 机制研究（含下载内核知识）。UI 对标 PCL2，下载内核与下载 UI 对标 IDM。真实输入测试（FlaUI 5.0.0）。

- **2.0 源码**：`swdm2/`（Swdm2.App WPF + Core + Steam + Downloads + UiTests）
- **1.x 遗产**：`legacy/`（Python/PySide6 实现，行为参考）
- **研究与文档**：`docs/`、`research/`

## 当前进度（2026-10-03）

- 版本 **0.6.0**，阶段 1-5 关门（0.1.0→0.5.0)，阶段 6 打包链已交付（Velopack)
- 特性：球体主页（3D 点线球+游戏图标贴图+鼠标光源+液态玻璃）、PCL2 体感动画套件、IDM 三栏下载页、SteamKit2/steamcmd 双下载内核、社区页面回退+指纹头防 429、真实 Steam 数据源
- 构建门：`dotnet clean` + `build -warnaserror` = 0-0；单元/逻辑层回归全绿
- 打包：`swdm2/scripts/pack-velopack.ps1` → `artifacts/`（Setup 81.4MB self-contained）

构建：`dotnet build swdm2/Swdm2.sln`（.NET 8 SDK）

1.x 说明见 [README.1.x.md](README.1.x.md)。
