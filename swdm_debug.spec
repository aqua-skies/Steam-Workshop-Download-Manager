# -*- mode: python ; coding: utf-8 -*-
"""调试打包脚本（console=True，用于捕获启动 traceback）。正式构建用 swdm.spec。"""

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

hiddenimports = [
    "truststore",
    "keyring",
    "keyring.backends",
    "keyring.backends.chainer",
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

datas = []
binaries = []
hiddenimports += collect_submodules("truststore")
hiddenimports += collect_submodules("keyring")
hiddenimports += collect_submodules("steam")
hiddenimports += collect_submodules("vdf")

datas += collect_data_files("truststore")

datas += [("swdm/resources/steamcmd.zip", "swdm/resources")]

MANUAL_HTML = "docs/manual/dist/SWDM-用户手册.html"
MANUAL_PDF = "docs/manual/dist/SWDM-用户手册.pdf"
datas += [
    (MANUAL_HTML, "manual"),
    (MANUAL_PDF, "manual"),
]

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
    name="SWDMDebug",
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    name="SWDMDebug",
)
