# -*- mode: python ; coding: utf-8 -*-
"""SWDM PyInstaller 打包脚本（onedir / windowed）。

构建命令（项目根目录执行）：
    python -m PyInstaller swdm.spec --noconfirm `
        --workpath build --distpath build/dist

产物：build/dist/SWDM/SWDM.exe（绿色版目录，可直接运行排错）。
再由 installer/swdm.iss 打成安装包。
"""

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

# ---- hidden imports -------------------------------------------------------
# truststore / keyring 在代码里是函数内延迟导入，PyInstaller 静态分析会漏掉，
# 必须显式声明；keyring 的 Windows 后端同理。
hiddenimports = [
    "truststore",
    "keyring",
    "keyring.backends",
    "keyring.backends.chainer",  # keyring 25+ 由 chained 改名而来
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "keyring.backends.null",
    "vdf",
    "steam",
    "bs4",
    "lxml.etree",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
]

# ---- 收集第三方包的数据文件 / 子模块 -------------------------------------------------
# 注意：PySide6 不做暴力 collect_all。PyInstaller 内置的 hook-PySide6.* 会按
# 实际导入的 Qt 模块自动收集所需插件（platforms / imageformats / styles / tls），
# 避免把 WebEngine / Multimedia 等未使用的大模块（约 300MB）塞进安装包。
datas = []
binaries = []
hiddenimports += collect_submodules("truststore")
hiddenimports += collect_submodules("keyring")
hiddenimports += collect_submodules("steam")
hiddenimports += collect_submodules("vdf")

datas += collect_data_files("truststore")

# 随程序分发的官方 steamcmd（需求 2：安装即自带，用户无需自装；
# 首次使用时自动解压到数据目录）
datas += [("swdm/resources/steamcmd.zip", "swdm/resources")]

# A1（t42）：用户手册单文件交付物随包打入 manual/；
# 菜单「帮助 > 用户手册」打开 HTML，PDF 作为离线/打印回退
MANUAL_HTML = "docs/manual/dist/SWDM-用户手册.html"
MANUAL_PDF = "docs/manual/dist/SWDM-用户手册.pdf"
datas += [
    (MANUAL_HTML, "manual"),
    (MANUAL_PDF, "manual"),
]

# 包的元数据（keyring / truststore 的 entry point 依赖）
datas += copy_metadata("keyring")
datas += copy_metadata("truststore")
datas += copy_metadata("steam")

a = Analysis(
    ["swdm/app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pytest",
        "unittest",
        "pydoc",
        # GUI 只用 QtCore/QtGui/QtWidgets/QtNetwork；以下 Qt 大模块未使用，排除以减小体积
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickLayouts",
        "PySide6.QtQuickTemplates2",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DExtras",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
        "PySide6.QtBluetooth",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSerialBus",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtStateMachine",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtUiTools",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SWDM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 压缩 Qt 二进制容易触发杀软误报，关闭
    console=False,  # windowed：无控制台黑框
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="swdm/resources/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SWDM",
)
