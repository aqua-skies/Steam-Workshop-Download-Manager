"""内置 steamcmd 部署：随程序分发的官方 steamcmd.zip，首次使用时自动解压。

需求 2：内置 steamcmd 下载模式，提高泛用性——用户无需自行下载安装
steamcmd，安装程序已内附；首次下载时自动解压到数据目录（steamcmd 首次
运行会自更新补齐组件，全程匿名、无需账号）。
"""
from __future__ import annotations

import os
import zipfile

from .logger import get_logger
from .paths import (
    DEPLOYED_STEAMCMD_EXE,
    STEAMCMD_DIR,
    bundled_steamcmd_zip,
    deployed_steamcmd_exe,
    ensure_dirs,
)

log = get_logger("swdm.core.steamcmd_deploy")


def is_deployed() -> bool:
    """内置 steamcmd 是否已解压就绪。"""
    return os.path.isfile(deployed_steamcmd_exe())


def has_bundled_zip() -> bool:
    """随程序分发的 steamcmd.zip 是否存在。"""
    return os.path.isfile(bundled_steamcmd_zip())


def deploy(force: bool = False) -> str:
    """解压内置 steamcmd.zip 到数据目录。返回 steamcmd.exe 路径。

    已部署且未要求强制重做时直接返回现有路径。
    无内置 zip 时抛 RuntimeError。
    """
    exe = deployed_steamcmd_exe()
    if is_deployed() and not force:
        return exe

    zip_path = bundled_steamcmd_zip()
    if not os.path.isfile(zip_path):
        raise RuntimeError(
            f"未找到随程序分发的 steamcmd 安装包：{zip_path}\n"
            "请在设置页指定已有的 steamcmd.exe 路径，或从官网下载 steamcmd。"
        )

    ensure_dirs()
    os.makedirs(STEAMCMD_DIR, exist_ok=True)
    log.info("正在解压内置 steamcmd 到 %s", STEAMCMD_DIR)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(STEAMCMD_DIR)

    if not os.path.isfile(exe):
        raise RuntimeError(f"解压后未找到 steamcmd.exe：{exe}")
    log.info("内置 steamcmd 部署完成：%s", exe)
    return exe


def ensure_steamcmd() -> str:
    """确保 steamcmd 可用：已部署则返回，否则自动部署。返回 exe 路径。"""
    if is_deployed():
        return deployed_steamcmd_exe()
    if has_bundled_zip():
        return deploy()
    raise RuntimeError(
        "未找到可用的 steamcmd，且程序未内附安装包。\n"
        "请在设置页指定 steamcmd.exe 路径。"
    )


def deployment_status() -> dict:
    """供 UI 展示的部署状态。"""
    return {
        "deployed": is_deployed(),
        "bundled": has_bundled_zip(),
        "exe": deployed_steamcmd_exe() if is_deployed() else "",
        "dir": STEAMCMD_DIR,
        "zip": bundled_steamcmd_zip() if has_bundled_zip() else "",
    }
