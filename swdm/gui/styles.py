"""Application themes: dark / light QSS stylesheets (应用主题).

The dark theme follows VS Code / Discord styling: #1e1e22 background family, a blue-violet
accent, 8px corner radii, thin borders. Color constants live centrally in DARK_COLORS and are
reused by widgets.py so custom-drawn controls stay visually consistent with the QSS.
"""

# ============================================================ 深色配色
DARK_COLORS = {
    "bg": "#1e1e22",            # 窗口底色
    "bg_panel": "#23232a",      # 面板 / 表格头 / 标签页
    "bg_input": "#2a2a31",      # 输入框 / 下拉 / 菜单
    "bg_hover": "#2e2e37",      # 悬停
    "bg_selected": "#3a3160",   # 选中（半透明强调色观感）
    "border": "#33333b",        # 细边框
    "border_light": "#383841",  # 输入框等稍亮边框
    "border_hover": "#4d4d59",
    "text": "#e3e3ea",          # 主文本
    "text_dim": "#9aa0aa",      # 次要文本
    "accent": "#7c5cff",        # 蓝紫强调色
    "accent_hover": "#8f74ff",
    "accent_pressed": "#6543e0",
    "success": "#43b581",
    "danger": "#f04747",
    "warning": "#faa61a",
}

# ============================================================ 浅色配色
LIGHT_COLORS = {
    "bg": "#f6f7f9",
    "bg_panel": "#eef0f3",
    "bg_input": "#ffffff",
    "bg_hover": "#e8eaee",
    "bg_selected": "#e3dcfb",
    "border": "#d5d9e0",
    "border_light": "#c8ccd2",
    "border_hover": "#b6bcc5",
    "text": "#23272e",
    "text_dim": "#5a6169",
    "accent": "#6d4aff",
    "accent_hover": "#7d5cff",
    "accent_pressed": "#5b3ce0",
    "success": "#2f9e6b",
    "danger": "#d63c3c",
    "warning": "#d68f00",
}

DARK_QSS = """
/* ==================== SWDM 深色主题（VS Code / Discord 风格） ==================== */
/* --- 窗口与通用面板（保留 QWidget#central 对象选择器） --- */
QMainWindow, QWidget#central { background-color: #1e1e22; }
QWidget { color: #e3e3ea; }

/* --- 标签页 --- */
QTabWidget::pane { border: 1px solid #33333b; background: #23232a; border-radius: 8px; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: #25252c; color: #9aa0aa;
    padding: 8px 18px; border: 1px solid #33333b;
    border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px;
    margin-right: 2px; min-width: 24px;
}
QTabBar::tab:selected { background: #7c5cff; color: #ffffff; }
QTabBar::tab:hover:!selected { background: #2e2e37; color: #d5dae2; }
QTabBar::tab:selected:hover { background: #8f74ff; }

/* --- 输入 / 列表 / 表格 / 下拉 / 数字框 --- */
QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QTableWidget, QTreeWidget,
QComboBox, QSpinBox {
    background: #2a2a31; color: #e3e3ea; border: 1px solid #383841; border-radius: 8px;
    selection-background-color: #7c5cff; selection-color: #ffffff;
    padding: 4px 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QListWidget:focus,
QTableWidget:focus, QTreeWidget:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #7c5cff;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #2a2a31; border: 1px solid #383841; border-radius: 6px;
    selection-background-color: #7c5cff; selection-color: #ffffff;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button { background: transparent; border: none; width: 16px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #2e2e37; }
QTableWidget::item, QListWidget::item { padding: 4px; border-radius: 6px; }
QListWidget::item:hover, QTableWidget::item:hover { background: #2e2e37; }
QListWidget::item:selected, QTableWidget::item:selected,
QTreeWidget::item:selected { background: #3a3160; color: #ffffff; }
QHeaderView::section { background: #23232a; color: #9aa0aa; padding: 6px; border: none;
    border-bottom: 1px solid #383841; }

/* --- 按钮（悬停 / 按下 / 禁用 / secondary / danger 属性选择器保持不变） --- */
QPushButton {
    background: #7c5cff; color: white; border: none; padding: 7px 16px;
    border-radius: 8px; font-weight: 500;
}
QPushButton:hover { background: #8f74ff; }
QPushButton:pressed { background: #6543e0; }
QPushButton:disabled { background: #35353d; color: #6a7078; }
QPushButton[secondary="true"] { background: #2e2e36; color: #d5dae2; }
QPushButton[secondary="true"]:hover { background: #383841; }
QPushButton[secondary="true"]:pressed { background: #33333b; }
QPushButton[danger="true"] { background: #f04747; }
QPushButton[danger="true"]:hover { background: #f46060; }
QPushButton[danger="true"]:pressed { background: #d63c3c; }

/* --- 进度条 --- */
QProgressBar { border: 1px solid #383841; border-radius: 6px; background: #1a1a1f;
    height: 14px; text-align: center; color: #e3e3ea; font-size: 10px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #7c5cff, stop:1 #4a9bff); border-radius: 5px; }

/* --- 复选 / 单选 --- */
QCheckBox, QRadioButton { color: #e3e3ea; spacing: 6px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid #4a4a55; background: #2a2a31;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border: 1px solid #7c5cff; }
QCheckBox::indicator:checked { background: #7c5cff; border: 1px solid #7c5cff; }
QRadioButton::indicator { border-radius: 8px; }
QRadioButton::indicator:checked { background: #7c5cff; border: 1px solid #7c5cff; }

/* --- 标签 --- */
QLabel { color: #e3e3ea; background: transparent; }
QLabel#cardTitle { font-weight: 600; font-size: 13px; color: #e8ecf2; background: transparent; }

/* --- 分组框 --- */
QGroupBox { border: 1px solid #383841; border-radius: 8px; margin-top: 12px;
    padding-top: 12px; color: #9aa0aa; background: transparent; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; padding: 0 6px; background: transparent; }

/* --- 滚动条（细滑块，hover 变亮） --- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3d3d47; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #4d4d59; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0; background: transparent; border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #3d3d47; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #4d4d59; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0; background: transparent; border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* --- 状态栏 / 菜单 / 工具按钮 / 提示 --- */
QStatusBar { background: #1a1a1f; color: #9aa0aa; border-top: 1px solid #33333b; }
QStatusBar::item { border: none; }
QMenu { background: #2a2a31; color: #e3e3ea; border: 1px solid #383841;
    border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: #7c5cff; color: #ffffff; }
QMenu::separator { height: 1px; background: #383841; margin: 4px 8px; }
QSplitter::handle { background: #33333b; }
QToolButton { background: transparent; color: #9aa0aa; padding: 5px; border-radius: 6px; }
QToolButton:hover { background: #2e2e37; color: #e3e3ea; }
QToolTip { background: #2a2a31; color: #e3e3ea; border: 1px solid #383841;
    border-radius: 6px; padding: 4px 6px; }
"""

LIGHT_QSS = """
/* ==================== SWDM 浅色主题 ==================== */
QMainWindow, QWidget#central { background-color: #f6f7f9; }
QWidget { color: #23272e; }

QTabWidget::pane { border: 1px solid #d5d9e0; background: #ffffff; border-radius: 8px; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab { background: #e8eaee; color: #5a6169; padding: 8px 18px;
    border: 1px solid #d5d9e0; border-bottom: none;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }
QTabBar::tab:selected { background: #6d4aff; color: #ffffff; }
QTabBar::tab:hover:!selected { background: #dfe2e8; color: #23272e; }

QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QTableWidget, QTreeWidget,
QComboBox, QSpinBox {
    background: #ffffff; color: #23272e; border: 1px solid #c8ccd2; border-radius: 8px;
    selection-background-color: #6d4aff; selection-color: #ffffff; padding: 4px 6px;
}
QLineEdit:focus, QListWidget:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #6d4aff;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #c8ccd2;
    border-radius: 6px; selection-background-color: #6d4aff; selection-color: #ffffff; outline: 0; }
QTableWidget::item, QListWidget::item { padding: 4px; border-radius: 6px; }
QListWidget::item:hover, QTableWidget::item:hover { background: #e8eaee; }
QListWidget::item:selected, QTableWidget::item:selected { background: #e3dcfb; color: #23272e; }
QHeaderView::section { background: #eef0f3; color: #5a6169; padding: 6px; border: none;
    border-bottom: 1px solid #d5d9e0; }

QPushButton { background: #6d4aff; color: white; border: none; padding: 7px 16px;
    border-radius: 8px; font-weight: 500; }
QPushButton:hover { background: #7d5cff; }
QPushButton:pressed { background: #5b3ce0; }
QPushButton:disabled { background: #c8ccd2; color: #8a8f96; }
QPushButton[secondary="true"] { background: #e2e5ea; color: #23272e; }
QPushButton[secondary="true"]:hover { background: #d5d9e0; }
QPushButton[danger="true"] { background: #d63c3c; }
QPushButton[danger="true"]:hover { background: #e04848; }

QProgressBar { border: 1px solid #c8ccd2; border-radius: 6px; background: #eef0f3;
    height: 14px; text-align: center; color: #23272e; font-size: 10px; }
QProgressBar::chunk { background: #6d4aff; border-radius: 5px; }

QCheckBox, QRadioButton { color: #23272e; spacing: 6px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid #b6bcc5; background: #ffffff;
}
QCheckBox::indicator:checked { background: #6d4aff; border: 1px solid #6d4aff; }
QRadioButton::indicator { border-radius: 8px; }
QRadioButton::indicator:checked { background: #6d4aff; border: 1px solid #6d4aff; }

QLabel { color: #23272e; background: transparent; }
QLabel#cardTitle { font-weight: 600; font-size: 13px; color: #23272e; background: transparent; }

QGroupBox { border: 1px solid #d5d9e0; border-radius: 8px; margin-top: 12px;
    padding-top: 12px; color: #5a6169; background: transparent; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; padding: 0 6px; background: transparent; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #c8ccd2; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #aab1ba; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #c8ccd2; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #aab1ba; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QStatusBar { background: #eef0f3; color: #5a6169; border-top: 1px solid #d5d9e0; }
QMenu { background: #ffffff; color: #23272e; border: 1px solid #c8ccd2;
    border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: #6d4aff; color: #ffffff; }
QSplitter::handle { background: #d5d9e0; }
QToolButton { background: transparent; color: #5a6169; padding: 5px; border-radius: 6px; }
QToolButton:hover { background: #e8eaee; }
QToolTip { background: #ffffff; color: #23272e; border: 1px solid #c8ccd2;
    border-radius: 6px; padding: 4px 6px; }
"""


def qss(theme: str) -> str:
    """按主题名返回 QSS（未知主题一律回退到深色）。"""
    return LIGHT_QSS if theme == "light" else DARK_QSS
