"""Settings tab: network / download / auth / library dirs and other advanced settings (设置页).

Includes the download-channel dropdown generated dynamically from
``ProviderRegistry.list_channels()`` (1.4.0) with a tooltip explaining chain fallback,
the SteamCMD engine deploy block, the per-game install directory table, the "open data dir"
button (t16 决议 B②) and the debug-panel visibility toggle (t22 B④).
"""
from __future__ import annotations

import os
import subprocess
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from swdm.core.auth import AuthManager
from swdm.core.config import get_config
from swdm.core.game_dirs import (
    clear_game_dir,
    configured_game_dirs,
    game_dir_entries,
    set_game_dir,
)
from swdm.core.games import all_games, game_name
from swdm.core.logger import get_logger
from swdm.core.paths import LIBRARY_DIR
from swdm.gui.widgets import CollapsibleSection
from swdm.gui.workers import LoginWorker

log = get_logger("swdm.gui.settings")


class SettingsTab(QWidget):
    """高级设置页。"""

    settings_changed = Signal()

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self.svc = services
        self.auth: AuthManager = services.auth
        self._build()
        self._load_values()

    # ------------------------------------------------------------- 布局
    def _build(self) -> None:
        # 内容较多，外层套滚动区域，避免窗口高度不足时控件被压扁
        # （此前 bug：无 ScrollArea 时 QVBoxLayout 把输入框压到 0-16px 高，
        # 表现为"字符拥挤重叠、无法编辑"）
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- 账号（常用，默认展开）---
        acc = QGroupBox("Steam 账号（登录方式）")
        acc_lay = QVBoxLayout(acc)
        acc_lay.setContentsMargins(9, 9, 9, 9)
        acc_lay.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("匿名自动登录（无需账号）", "anonymous")
        self.mode_combo.addItem("手动登录（用户名密码）", "user")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("登录方式:", self.mode_combo)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Steam 用户名")
        self.username_edit.setEnabled(False)
        form.addRow("用户名:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Steam 密码（加密存于系统凭据库）")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setEnabled(False)
        form.addRow("密码:", self.password_edit)

        self.guard_edit = QLineEdit()
        self.guard_edit.setPlaceholderText("Steam Guard 验证码（如需要）")
        self.guard_edit.setEnabled(False)
        form.addRow("验证码:", self.guard_edit)

        self.remember_check = QCheckBox("记住密码（keyring 加密存储）")
        self.remember_check.setChecked(True)
        self.remember_check.setEnabled(False)
        form.addRow("", self.remember_check)
        acc_lay.addLayout(form)

        btns = QHBoxLayout()
        self.test_login_btn = QPushButton("🔗 测试登录")
        self.test_login_btn.clicked.connect(self._test_login)
        btns.addWidget(self.test_login_btn)
        self.apply_acc_btn = QPushButton("保存账号设置")
        self.apply_acc_btn.clicked.connect(self._apply_account)
        btns.addWidget(self.apply_acc_btn)
        acc_lay.addLayout(btns)
        self.login_status = QLabel("🟢 匿名模式：无需任何账号即可下载")
        self.login_status.setStyleSheet("color:#5f8fd0; padding:4px;")
        acc_lay.addWidget(self.login_status)
        sec_acc = CollapsibleSection("Steam 账号（登录方式）", expanded=True)
        sec_acc.addWidget(acc)
        root.addWidget(sec_acc)

        # --- 网络与下载（高级，默认收起）---
        net = QGroupBox("网络与下载")
        net_lay = QFormLayout(net)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("可选：Steam Web API Key（增强搜索）")
        net_lay.addRow("API Key:", self.api_key_edit)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("如 http://127.0.0.1:7890")
        net_lay.addRow("代理:", self.proxy_edit)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" 秒")
        net_lay.addRow("请求超时:", self.timeout_spin)
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 8)
        self.concurrency_spin.setSuffix(" 并发")
        net_lay.addRow("最大并发下载:", self.concurrency_spin)
        sec_net = CollapsibleSection("网络与下载（高级）", expanded=False)
        sec_net.addWidget(net)
        root.addWidget(sec_net)

        # --- steamcmd（常用，默认展开）---
        sc = QGroupBox("SteamCMD")
        sc_lay = QFormLayout(sc)
        # 下载通道：按 provider 注册表动态生成（1.4.0）
        self.channel_combo = QComboBox()
        self._channel_rows: list[tuple[str, str, str]] = []  # (name, display, avail)
        self._refresh_channel_combo()
        self.channel_combo.setToolTip(
            "所选通道不可用时自动沿链回退，SteamCMD 永远兜底。\n"
            "匿名会话下 CDN 直链不可用（Steam 不开放 file_url）。"
        )
        sc_lay.addRow("下载通道:", self.channel_combo)
        self.steamcmd_edit = QLineEdit()
        self.steamcmd_edit.setPlaceholderText("留空自动检测或从内置部署")
        sc_lay.addRow("steamcmd.exe 路径:", self.steamcmd_edit)
        sc_btns = QHBoxLayout()
        browse = QPushButton("浏览…")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self._browse_steamcmd)
        sc_btns.addWidget(browse)
        deploy_btn = QPushButton("自动部署内置 steamcmd")
        deploy_btn.setProperty("secondary", True)
        deploy_btn.clicked.connect(self._deploy_steamcmd)
        sc_btns.addWidget(deploy_btn)
        sc_lay.addRow("", sc_btns)
        self.validate_check = QCheckBox("下载后验证文件（+validate，较慢）")
        sc_lay.addRow("", self.validate_check)
        sec_sc = CollapsibleSection("SteamCMD 与下载通道", expanded=True)
        sec_sc.addWidget(sc)
        root.addWidget(sec_sc)

        # --- 前置依赖（高级，默认收起）---
        dep = QGroupBox("前置依赖（Required Items）")
        dep_lay = QFormLayout(dep)
        self.auto_deps_check = QCheckBox("下载时自动带上下递归解析出的前置依赖")
        dep_lay.addRow("", self.auto_deps_check)
        self.ask_deps_check = QCheckBox("有依赖时弹窗确认（关闭则静默全部下载）")
        dep_lay.addRow("", self.ask_deps_check)
        self.skip_installed_deps_check = QCheckBox("跳过已安装的依赖")
        dep_lay.addRow("", self.skip_installed_deps_check)
        self.dep_depth_spin = QSpinBox()
        self.dep_depth_spin.setRange(1, 20)
        self.dep_depth_spin.setSuffix(" 层")
        dep_lay.addRow("依赖树最大深度:", self.dep_depth_spin)
        sec_dep = CollapsibleSection("前置依赖策略（高级）", expanded=False)
        sec_dep.addWidget(dep)
        root.addWidget(sec_dep)

        # --- 库（常用，默认展开）---
        lib = QGroupBox("Mod 库")
        lib_lay = QFormLayout(lib)
        self.library_edit = QLineEdit()
        self.library_edit.setPlaceholderText(f"默认: {LIBRARY_DIR}")
        lib_lay.addRow("库根目录:", self.library_edit)
        lb_btns = QHBoxLayout()
        lb_browse = QPushButton("浏览…")
        lb_browse.setProperty("secondary", True)
        lb_browse.clicked.connect(self._browse_library)
        lb_btns.addWidget(lb_browse)
        lib_lay.addRow("", lb_btns)
        self.organize_check = QCheckBox("按游戏分目录存放")
        lib_lay.addRow("", self.organize_check)
        self.sidecar_check = QCheckBox("写入元数据 JSON（便于迁移与离线检索）")
        lib_lay.addRow("", self.sidecar_check)
        self.auto_import_check = QCheckBox("下载完成后自动登记到库")
        lib_lay.addRow("", self.auto_import_check)

        # 游戏专属下载目录（可按游戏单独指定）
        gd_label = QLabel(
            "为不同游戏单独指定 mod 下载目录（留空使用上方库根目录）："
        )
        lib_lay.addRow("", gd_label)
        self.game_dirs_table = QTableWidget(0, 3)
        self.game_dirs_table.setHorizontalHeaderLabels(["游戏", "AppID", "下载目录"])
        self.game_dirs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.game_dirs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.game_dirs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.game_dirs_table.verticalHeader().setVisible(False)
        # 首行行高保底：小行高在真实 DPI/中文字体下会让首行内容
        # 紧贴甚至裁切表头（用户报告"首行与下方方框挤压"）
        self.game_dirs_table.verticalHeader().setDefaultSectionSize(30)
        self.game_dirs_table.verticalHeader().setMinimumSectionSize(24)
        self.game_dirs_table.setMinimumHeight(140)
        lib_lay.addRow("", self.game_dirs_table)

        gd_btns = QHBoxLayout()
        self.gd_add_btn = QPushButton("➕ 添加游戏…")
        self.gd_add_btn.setProperty("secondary", True)
        self.gd_add_btn.clicked.connect(self._add_game_dir)
        gd_btns.addWidget(self.gd_add_btn)
        self.gd_edit_btn = QPushButton("✏️ 修改目录…")
        self.gd_edit_btn.setProperty("secondary", True)
        self.gd_edit_btn.clicked.connect(self._edit_game_dir)
        gd_btns.addWidget(self.gd_edit_btn)
        self.gd_del_btn = QPushButton("🗑 清除")
        self.gd_del_btn.setProperty("danger", True)
        self.gd_del_btn.clicked.connect(self._del_game_dir)
        gd_btns.addWidget(self.gd_del_btn)
        lib_lay.addRow("", gd_btns)
        # B②：一键打开数据目录（配置/库/日志/缓存都在这里，
        # 与 u10 删除互通呼应：删除残留文件时不用到处找目录）
        self.open_data_btn = QPushButton("📁 打开数据目录")
        self.open_data_btn.setToolTip(
            "在文件管理器中打开配置、mod 库、日志与缓存所在目录")
        self.open_data_btn.clicked.connect(self._open_data_dir)
        lib_lay.addRow("", self.open_data_btn)
        sec_lib = CollapsibleSection("Mod 库与下载目录", expanded=True)
        sec_lib.addWidget(lib)
        root.addWidget(sec_lib)

        # --- 外观/日志（高级，默认收起）---
        misc = QGroupBox("外观与日志")
        misc_lay = QFormLayout(misc)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("浅色", "light")
        misc_lay.addRow("主题:", self.theme_combo)
        self.loglevel_combo = QComboBox()
        for lv in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.loglevel_combo.addItem(lv, lv)
        misc_lay.addRow("日志级别:", self.loglevel_combo)
        # B④：调试面板开关（默认隐藏，需重启生效）
        self.debug_panel_check = QCheckBox("显示调试面板（重启后生效）")
        misc_lay.addRow("", self.debug_panel_check)
        # F7：标题过滤词（逗号分隔）
        self.hide_kw_edit = QLineEdit()
        self.hide_kw_edit.setPlaceholderText("如：Dead, 废弃, Outdated")
        misc_lay.addRow("隐藏标题含词:", self.hide_kw_edit)
        sec_misc = CollapsibleSection("外观与日志（高级）", expanded=False)
        sec_misc.addWidget(misc)
        root.addWidget(sec_misc)

        apply = QPushButton("💾 保存全部设置")
        apply.clicked.connect(self._apply_all)
        root.addWidget(apply)
        root.addStretch()

        # 装入滚动区域：内容超出窗口高度时可滚动，控件不再被压扁
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------- 逻辑
    def _load_values(self) -> None:
        cfg = self.svc.config
        self.api_key_edit.setText(cfg.get("network", "api_key") or "")
        self.proxy_edit.setText(cfg.get("network", "proxy") or "")
        self.timeout_spin.setValue(int(cfg.get("network", "timeout") or 30))
        self.concurrency_spin.setValue(int(cfg.get("network", "max_concurrent_downloads") or 2))
        self.steamcmd_edit.setText(cfg.get("steamcmd", "exe_path") or "")
        ch = cfg.get("download", "channel", default="steamcmd") or "steamcmd"
        self._refresh_channel_combo()
        idx = self.channel_combo.findData(ch)
        self.channel_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.validate_check.setChecked(bool(cfg.get("steamcmd", "validate", False)))
        self.library_edit.setText(cfg.get("general", "library_dir") or "")
        self.organize_check.setChecked(bool(cfg.get("library", "organize_by_game", True)))
        self.sidecar_check.setChecked(bool(cfg.get("library", "auto_write_metadata", True)))
        self.auto_import_check.setChecked(bool(cfg.get("library", "auto_import_on_complete", True)))
        self.auto_deps_check.setChecked(bool(cfg.get("dependencies", "auto_download", True)))
        self.ask_deps_check.setChecked(bool(cfg.get("dependencies", "ask_before_download", True)))
        self.skip_installed_deps_check.setChecked(bool(cfg.get("dependencies", "skip_installed", True)))
        self.dep_depth_spin.setValue(int(cfg.get("dependencies", "max_depth") or 10))
        self._load_game_dirs()
        self.loglevel_combo.setCurrentIndex(
            self.loglevel_combo.findData(cfg.get("logging", "level") or "INFO")
        )
        # F7：标题过滤词
        kws = cfg.get("hide_keywords", default=[]) or []
        self.hide_kw_edit.setText(", ".join(kws))
        # B④：调试面板开关状态
        self.debug_panel_check.setChecked(
            bool(cfg.get("logging", "show_debug_panel", default=False))
        )
        theme = cfg.get("general", "theme") or "dark"
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme))

        if self.auth.is_anonymous():
            self.mode_combo.setCurrentIndex(0)
            self._on_mode_changed(0)
            self.login_status.setText("🟢 匿名模式：无需任何账号即可下载")
        else:
            self.mode_combo.setCurrentIndex(1)
            self._on_mode_changed(1)
            self.username_edit.setText(self.auth.account.username)
            self.login_status.setText(
                f"🔵 手动登录：{self.auth.account.username}"
                f"（密码{'已保存' if self.auth.account.has_password else '未保存'}）"
            )

    def _on_mode_changed(self, idx: int) -> None:
        is_user = idx == 1
        self.username_edit.setEnabled(is_user)
        self.password_edit.setEnabled(is_user)
        self.guard_edit.setEnabled(is_user)
        self.remember_check.setEnabled(is_user)
        if not is_user:
            self.login_status.setText("🟢 匿名模式：无需任何账号即可下载")

    def _apply_account(self) -> None:
        if self.mode_combo.currentData() == "anonymous":
            self.auth.login_anonymous()
        else:
            user = self.username_edit.text().strip()
            pw = self.password_edit.text()
            guard = self.guard_edit.text().strip()
            if not user:
                QMessageBox.warning(self, "提示", "请填写用户名")
                return
            if not pw and not self.auth.account.has_password:
                QMessageBox.warning(self, "提示", "请填写密码")
                return
            if pw:
                self.auth.login_user(
                    user, pw, guard_code=guard, remember=self.remember_check.isChecked()
                )
            else:
                # 只改用户名/验证码（沿用已存密码）
                self.auth.account.username = user
                self.auth.account.guard_code = guard
                self.auth._save()
        self.svc.refresh_engine()
        self.settings_changed.emit()
        QMessageBox.information(self, "已保存", "账号设置已保存并生效。")

    def _test_login(self) -> None:
        self.test_login_btn.setEnabled(False)
        self.login_status.setText("⏳ 正在测试登录…")
        worker = LoginWorker(
            lambda: self.svc.engine  # 用当前引擎配置（refresh 已同步）
        )
        worker.result.connect(self._on_login_result)
        worker.start()
        self._login_worker = worker   # 保持引用

    def _on_login_result(self, ok: bool, msg: str) -> None:
        self.test_login_btn.setEnabled(True)
        color = "#3fae6f" if ok else "#e06060"
        self.login_status.setText(f"<span style='color:{color}'>{msg}</span>")
        self.login_status.setTextFormat(Qt.TextFormat.RichText)

    # ------------------------------------------------------------- 文件选择
    def _refresh_channel_combo(self) -> None:
        """按 provider 注册表动态生成通道下拉（1.4.0）。

        显示名后缀可用性状态；探测失败（UNREACHABLE）的通道仍保留可选
        （用户可强制选用，运行时链会自动回退），但给⚠标记。
        """
        from swdm.core.providers import get_registry

        self.channel_combo.blockSignals(True)
        prev = self.channel_combo.currentData()
        self.channel_combo.clear()
        self._channel_rows = []
        try:
            rows = get_registry().list_channels()
        except Exception:  # noqa: BLE001
            rows = [("steamcmd", "SteamCMD（匿名下载，推荐）", None)]
        avail_label = {
            "ok": "",
            "no_key": "（需配置 Key/登录）",
            "unreachable": "（⚠ 当前不可用）",
            "disabled": "（已禁用）",
        }
        for name, display, avail in rows:
            tag = avail_label.get(getattr(avail, "value", ""), "")
            self.channel_combo.addItem(f"{display}{tag}", name)
            self._channel_rows.append((name, display, str(avail)))
        if prev:
            idx = self.channel_combo.findData(prev)
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)
        self.channel_combo.blockSignals(False)

    def _browse_steamcmd(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 steamcmd.exe", "", "可执行文件 (steamcmd.exe)"
        )
        if path:
            self.steamcmd_edit.setText(path)

    def _browse_library(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 Mod 库根目录", LIBRARY_DIR)
        if folder:
            self.library_edit.setText(folder)

    def _deploy_steamcmd(self) -> None:
        """部署随程序分发的内置 steamcmd（安装包已自带，离线秒装）。"""
        from PySide6.QtWidgets import QApplication

        from swdm.core.steamcmd_deploy import deploy

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            path = deploy(force=True)
            self.steamcmd_edit.setText(path)
            QMessageBox.information(
                self, "部署完成",
                f"内置 steamcmd 已就绪（随安装程序附带，无需联网）：\n{path}\n\n"
                "首次下载时 steamcmd 会自动更新补齐组件。",
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "部署失败", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _apply_all(self) -> None:
        cfg = self.svc.config
        cfg.set("network", "api_key", self.api_key_edit.text().strip())
        cfg.set("network", "proxy", self.proxy_edit.text().strip())
        cfg.set("network", "timeout", self.timeout_spin.value())
        cfg.set("network", "max_concurrent_downloads", self.concurrency_spin.value())
        cfg.set("steamcmd", "exe_path", self.steamcmd_edit.text().strip())
        cfg.set("download", "channel", self.channel_combo.currentData())
        cfg.set("steamcmd", "force_install_dir", "")
        cfg.set("steamcmd", "validate", self.validate_check.isChecked())
        cfg.set("general", "library_dir", self.library_edit.text().strip())
        cfg.set("library", "organize_by_game", self.organize_check.isChecked())
        cfg.set("library", "auto_write_metadata", self.sidecar_check.isChecked())
        cfg.set("library", "auto_import_on_complete", self.auto_import_check.isChecked())
        cfg.set("dependencies", "auto_download", self.auto_deps_check.isChecked())
        cfg.set("dependencies", "ask_before_download", self.ask_deps_check.isChecked())
        cfg.set("dependencies", "skip_installed", self.skip_installed_deps_check.isChecked())
        cfg.set("dependencies", "max_depth", self.dep_depth_spin.value())
        cfg.set("logging", "level", self.loglevel_combo.currentData())
        # B④：调试面板开关（重启后生效）
        cfg.set("logging", "show_debug_panel", self.debug_panel_check.isChecked())
        # F7：标题过滤词（去空、去重）
        kws = [k.strip() for k in self.hide_kw_edit.text().split(",") if k.strip()]
        cfg.set("hide_keywords", sorted(set(kws)))
        old_theme = cfg.get("general", "theme")
        cfg.set("general", "theme", self.theme_combo.currentData())
        cfg.save()

        # 让核心层即时生效
        self.svc.refresh_api()
        self.svc.refresh_engine()
        self.settings_changed.emit()

        msg = "设置已保存并生效。"
        if old_theme != self.theme_combo.currentData():
            msg += "\n（主题切换需重启程序以完整应用）"
        QMessageBox.information(self, "已保存", msg)

    # ------------------------------------------------- 游戏专属下载目录
    def _load_game_dirs(self) -> None:
        """从配置加载游戏目录表。"""
        self.game_dirs_table.setRowCount(0)
        for e in game_dir_entries():
            row = self.game_dirs_table.rowCount()
            self.game_dirs_table.insertRow(row)
            self.game_dirs_table.setItem(row, 0, QTableWidgetItem(e["name"]))
            self.game_dirs_table.setItem(row, 1, QTableWidgetItem(e["appid"]))
            self.game_dirs_table.setItem(row, 2, QTableWidgetItem(e["dir"]))

    def _selected_game_row(self) -> int:
        rows = {i.row() for i in self.game_dirs_table.selectedIndexes()}
        return rows.pop() if rows else -1

    def _add_game_dir(self) -> None:
        """添加游戏并指定其下载目录。"""
        # all_games() 返回 [{"appid":..., "name":...}]，遍历出的是 dict；
        # 旧代码 for a in all_games() 拿到 dict，放入集合触发
        # unhashable type: 'dict'（全按钮实测发现）
        names = sorted({(g["name"] or g["appid"], g["appid"])
                        for g in all_games()})
        # 排除已配置的
        existing = set(configured_game_dirs())
        choices = [(n, a) for n, a in names if a not in existing]
        if not choices:
            QMessageBox.information(self, "提示", "所有内置游戏均已配置目录")
            return
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getItem(
            self, "选择游戏", "要为哪款游戏指定下载目录？",
            [n for n, _ in choices], 0, False,
        )
        if not ok or not name:
            return
        appid = next((a for n, a in choices if n == name), "")
        if not appid:
            return
        folder = QFileDialog.getExistingDirectory(
            self, f"选择 {name} 的 mod 下载目录", LIBRARY_DIR
        )
        if not folder:
            return
        set_game_dir(appid, folder)
        self._load_game_dirs()
        QMessageBox.information(
            self, "已设置", f"{name} 的 mod 将下载到：\n{folder}"
        )

    def _edit_game_dir(self) -> None:
        row = self._selected_game_row()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中选择一行")
            return
        appid = self.game_dirs_table.item(row, 1).text()
        name = self.game_dirs_table.item(row, 0).text()
        cur = self.game_dirs_table.item(row, 2).text()
        folder = QFileDialog.getExistingDirectory(
            self, f"选择 {name} 的 mod 下载目录", cur or LIBRARY_DIR
        )
        if not folder:
            return
        set_game_dir(appid, folder)
        self._load_game_dirs()
        QMessageBox.information(
            self, "已更新", f"{name} 的 mod 将下载到：\n{folder}"
        )

    def _del_game_dir(self) -> None:
        row = self._selected_game_row()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中选择一行")
            return
        appid = self.game_dirs_table.item(row, 1).text()
        name = self.game_dirs_table.item(row, 0).text()
        btn = QMessageBox.question(
            self, "清除目录配置",
            f"清除 {name} 的专属目录配置？\n（已下载的文件不会删除；"
            f"该游戏将回退到库根目录）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if btn != QMessageBox.StandardButton.Yes:
            return
        clear_game_dir(appid)
        self._load_game_dirs()

    def _open_data_dir(self) -> None:
        """在系统文件管理器中打开数据目录（配置/mod 库/日志/缓存）。"""
        import sys

        from swdm.core.paths import DATA_DIR, ensure_dirs

        try:
            ensure_dirs()
            path = os.path.abspath(DATA_DIR)
            if not os.path.isdir(path):
                raise FileNotFoundError(path)
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S602
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)  # noqa: S603
            else:
                subprocess.run(["xdg-open", path], check=False)  # noqa: S603
        except Exception as e:  # noqa: BLE001
            log.warning("打开数据目录失败：%s", e, exc_info=True)
            QMessageBox.warning(
                self, "打开失败", f"无法打开数据目录：{e}")
