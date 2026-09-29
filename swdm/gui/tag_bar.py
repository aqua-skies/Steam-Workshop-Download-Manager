"""Tag bar: horizontally scrollable tag selection strip under the search bar (标签栏组件).

Requirements (user bug2):
- Integrated under the search bar, fetched automatically when a game is selected
  (no more "button + scroll dialog")
- Horizontal scroll; single click to select (multi-select)
- Selected tags are highlighted in the bar with a trailing ✕; clicking again (or the ✕)
  deselects
- Each tag shows its popularity count (number of mods carrying the tag; omitted when unknown)
- Navigation junk ("创意工坊/商店") is filtered out
- No duplicate tags added
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# 无关导航项（parse_available_tags 全页面兜底会把页脚/顶栏链接
# 误算为标签，如 cookie 设置、隐私政策等，bug14）
_NAV_TAGS = frozenset({
    "商店", "主页", "探索队列", "愿望单", "点数商店", "新闻", "排行榜",
    "社区", "讨论", "创意工坊", "市场", "实况直播", "关于", "客服",
    "安装 Steam", "登录", "注销", "商店主页", "社区主页",
    "查看个人资料", "我的愿望单", "我的点数", "账号明细", "游戏",
    "软件", "硬件", "视频", "Steam Deck", "礼品卡",
    # 页脚法律/政策链接
    "cookie", "cookies", "cookie 设置", "隐私政策", "隐私", "用户协议",
    "法律", "steam 在线行为", "合作伙伴", "jobs", "valvesoftware",
    "关于 valve", "steamworks", "steam 发行", "分销协议", "退款",
    "消费者隐私", "加州隐私通知", "eu privacy",
})

# cookie/隐私/法律类模糊关键词（小写匹配）
_LEGAL_KEYWORDS = ("cookie", "隐私", "隐私政策", "协议", "条款", "refund")


def filter_nav_tags(tags: list[str]) -> list[str]:
    """过滤无关导航标签 + 去重保序。"""
    out, seen = [], set()
    for t in tags or []:
        t = (t or "").strip()
        if not t or t in seen:
            continue
        low = t.lower()
        if t in _NAV_TAGS or low in _NAV_TAGS:
            continue
        # 语言名（带括号说明的，如 "日本語（日语）"）
        if "（" in t and "语）" in t:
            continue
        if any(kw in low for kw in _LEGAL_KEYWORDS):
            continue
        seen.add(t)
        out.append(t)
    return out


class TagChip(QPushButton):
    """单个标签 chip：可选中，已选时高亮 + 右侧 ✕。"""

    toggled_ = Signal(str, bool)   # (tag_name, checked)

    def __init__(self, name: str, count: int = 0, parent=None) -> None:
        text = name if count <= 0 else f"{name} ({count:,})"
        super().__init__(text, parent)
        self._name = name
        self._count = count
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setObjectName("tagChip")
        self.toggled.connect(lambda on: self.toggled_.emit(self._name, on))
        self._refresh_style()

    @property
    def tag_name(self) -> str:
        return self._name

    def _refresh_style(self) -> None:
        if self.isChecked():
            self.setStyleSheet(
                "QPushButton#tagChip{background:#5b4dff;border:1px solid #8f74ff;"
                "border-radius:12px;color:#fff;padding:3px 10px;"
                "font-size:12px;font-weight:600;}"
                "QPushButton#tagChip:hover{background:#6f5cff;}"
            )
        else:
            self.setStyleSheet(
                "QPushButton#tagChip{background:#262b32;border:1px solid #3a4048;"
                "border-radius:12px;color:#b8bec9;padding:3px 10px;font-size:12px;}"
                "QPushButton#tagChip:hover{background:#2e3440;border-color:#5b4dff;}"
            )

    def setChecked(self, on: bool) -> None:  # type: ignore[override]
        super().setChecked(on)
        self._refresh_style()


class TagBar(QWidget):
    """横向滚动标签栏：自动拉取、单击多选、已选高亮带 ✕。"""

    selection_changed = Signal(list)   # list[str] 当前选中的标签

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chips: dict[str, TagChip] = {}
        self._selected: list[str] = []
        self._build()
        self.setEnabled(False)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._header = QLabel("标签")
        self._header.setStyleSheet("color:#8a909a; font-size:11px;")
        root.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        # bug1：内容超宽时显示横向滚动条；AlwaysOff 会彻底禁用滚动
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setFixedHeight(40)
        self._host = QWidget()
        self._row = QHBoxLayout(self._host)
        self._row.setContentsMargins(2, 0, 2, 0)
        self._row.setSpacing(6)
        # bug3：layout 不压缩子项，内容总宽超出视口时 QScrollArea 才横向滚动
        self._row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self._row.addStretch()
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll)

        # 已选标签行（高亮 + ✕，点击 ✕ 删除）
        self._sel_host = QWidget()
        self._sel_host.setVisible(False)
        self._sel_row = QHBoxLayout(self._sel_host)
        self._sel_row.setContentsMargins(2, 0, 2, 0)
        self._sel_row.setSpacing(6)
        root.addWidget(self._sel_host)

    # --------------------------------------------------------------- 数据
    def set_tags(self, tags) -> None:
        """填充标签列表。tags 为 (name, count) 元组列表或字符串列表。"""
        self._clear_chips()
        norm = []
        for t in tags or []:
            if isinstance(t, (tuple, list)) and len(t) >= 2:
                norm.append((str(t[0]), int(t[1] or 0)))
            else:
                norm.append((str(t), 0))
        names = filter_nav_tags([n for n, _ in norm])
        counts = {n: c for n, c in norm}
        for name in names:
            chip = TagChip(name, counts.get(name, 0))
            chip.toggled_.connect(self._on_chip_toggled)
            self._chips[name] = chip
            self._row.insertWidget(self._row.count() - 1, chip)
        self.setEnabled(bool(names))
        # bug3：内容总宽超出视口时启用横向滚动
        self._host.adjustSize()
        self._host.setMinimumWidth(self._row.sizeHint().width())
        self._header.setText(f"标签（{len(names)}）" if names else "标签")
        # 恢复之前选中状态（切换游戏后保留选中）
        for name in list(self._selected):
            chip = self._chips.get(name)
            if chip:
                chip.setChecked(True)
        self._render_selected()

    def set_loading(self, on: bool) -> None:
        self._header.setText("标签拉取中…" if on else "标签")

    def set_selected(self, tags: list[str]) -> None:
        """直接设置选中集合（去重保序，不重复添加）。"""
        self._selected = []
        for t in tags or []:
            t = (t or "").strip()
            if t and t not in self._selected:
                self._selected.append(t)
        for name, chip in self._chips.items():
            chip.setChecked(name in self._selected)
        self._render_selected()

    def selected(self) -> list[str]:
        return list(self._selected)

    def clear_selection(self) -> None:
        self.set_selected([])

    # --------------------------------------------------------------- 内部
    def _clear_chips(self) -> None:
        for chip in list(self._chips.values()):
            self._row.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()

    def _on_chip_toggled(self, name: str, on: bool) -> None:
        if on:
            if name not in self._selected:   # 不重复添加
                self._selected.append(name)
        elif name in self._selected:
            self._selected.remove(name)
        self._render_selected()
        self.selection_changed.emit(list(self._selected))

    def _render_selected(self) -> None:
        # 清空已选行
        while self._sel_row.count():
            item = self._sel_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self._selected:
            self._sel_host.setVisible(False)
            return
        self._sel_host.setVisible(True)
        for name in self._selected:
            chip = QPushButton(f"{name}  ✕")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton{background:#4a3d9e;border:1px solid #8f74ff;"
                "border-radius:12px;color:#e8ecf2;padding:3px 10px;"
                "font-size:12px;font-weight:600;}"
                "QPushButton:hover{background:#5b4dff;color:#fff;}"
            )
            chip.clicked.connect(lambda _=False, n=name: self._remove_tag(n))
            self._sel_row.addWidget(chip)
        self._sel_row.addStretch()

    def _remove_tag(self, name: str) -> None:
        """点已选标签的 ✕ 取消选择。"""
        chip = self._chips.get(name)
        if chip:
            chip.setChecked(False)   # 触发 _on_chip_toggled 同步集合
        elif name in self._selected:
            self._selected.remove(name)
            self._render_selected()
            self.selection_changed.emit(list(self._selected))
