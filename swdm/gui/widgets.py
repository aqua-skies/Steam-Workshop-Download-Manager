"""SWDM 可复用 GUI 组件。

全部使用 PySide6 原生绘制，不依赖任何外部图片资源（gif/png 一律代码生成）；
ModCard 通过 setData(dict) 接收数据，不导入核心层类型，避免循环依赖。

组件清单：
  - LoadingSpinner   旋转加载圈（QPainter 画弧 + QPropertyAnimation 转 angle）
  - LoadingOverlay   半透明遮罩（盖在父组件上，中央 spinner + 一行文字）
  - SmoothScrollBar  平滑滚动条（value 跳变时 QPropertyAnimation 缓动过渡）
  - ModCard          模组列表卡片（缩略图 / 标题 / 标签 chips / 热度 / 状态角标）
  - ElidedLabel      单行自动省略标签（末尾 …，省略时把全文放进 ToolTip）
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Property,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# 与 styles.py 深色主题一致的组件级配色（组件自用，主题切换时仍可读）
ACCENT = "#8f74ff"
CARD_BG = "#25252c"
CARD_BORDER = "#33333b"
CARD_BORDER_HOVER = "#4d4d59"
TEXT_PRIMARY = "#e8ecf2"
TEXT_DIM = "#9aa0aa"
CHIP_BG = "#33333f"
CHIP_FG = "#b9bfc9"
THUMB_BG = "#26262d"
INSTALLED_BG = "#2f6b4f"
INSTALLED_FG = "#c8f0d8"
NOT_INSTALLED_BG = "#35353d"
NOT_INSTALLED_FG = "#9aa0aa"


# ============================================================ 可折叠分组
class CollapsibleSection(QWidget):
    """可折叠分组面板：标题按钮（带 ▸/▾ 箭头）+ 内容区。

    用于设置页等"选项多但不能全堆给用户"的场景：常用分组默认展开，
    高级分组默认收起，点击标题切换。
    """

    def __init__(self, title: str, parent=None, expanded: bool = True) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._title_btn = QPushButton(f"{'▾' if expanded else '▸'}  {title}")
        self._title = title
        self._title_btn.setCheckable(True)
        self._title_btn.setChecked(expanded)
        self._title_btn.setObjectName("collapsibleTitle")
        self._title_btn.setStyleSheet(
            "QPushButton#collapsibleTitle {"
            " text-align: left; background: #26262e; border: 1px solid #34343e;"
            " border-radius: 8px; padding: 8px 12px; font-weight: 600;"
            " color: #d5dae2;"
            "}"
            "QPushButton#collapsibleTitle:hover { background: #2e2e38; }"
            "QPushButton#collapsibleTitle::indicator { width: 0; height: 0; }"
        )
        self._title_btn.toggled.connect(self._on_toggled)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 10, 0, 8)
        self._content_layout.setSpacing(8)
        self._content.setVisible(expanded)

        lay.addWidget(self._title_btn)
        lay.addWidget(self._content)

    def addWidget(self, widget) -> None:
        self._content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    def setExpanded(self, expanded: bool) -> None:
        self._title_btn.setChecked(expanded)

    def set_title(self, title: str) -> None:
        """更新标题（保持当前展开状态对应的箭头）。"""
        self._title = title
        self._title_btn.setText(
            f"{'▾' if self._title_btn.isChecked() else '▸'}  {title}"
        )

    def _on_toggled(self, checked: bool) -> None:
        self._title_btn.setText(
            f"{'▾' if checked else '▸'}  {self._title}"
        )
        self._content.setVisible(checked)


# ============================================================ LoadingSpinner
class LoadingSpinner(QWidget):
    """纯代码绘制的旋转加载圈。

    用 QPainter 画一段圆弧，角度由 QPropertyAnimation 驱动 ``angle`` 属性
    连续旋转；可嵌入任意布局，支持 setColor / setSize 动态修改外观。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        size: int = 32,
        color: str | QColor = ACCENT,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._size = max(8, int(size))
        self._angle = 0.0
        self._want_running = False
        self.setFixedSize(self._size, self._size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setDuration(900)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setLoopCount(-1)

    # ---------------------------------------------------------- angle 属性
    @Property(float)
    def angle(self) -> float:  # pragma: no cover - 供 QPropertyAnimation 读写
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        self._angle = float(value) % 360.0
        self.update()

    # ---------------------------------------------------------- 公共接口
    def start(self) -> None:
        """开始旋转（不可见时暂不消耗 CPU，show 时自动恢复）。"""
        self._want_running = True
        if self._anim.state() != QPropertyAnimation.State.Running:
            self._anim.start()

    def stop(self) -> None:
        """停止旋转并复位角度。"""
        self._want_running = False
        self._anim.stop()
        self._angle = 0.0
        self.update()

    def isRunning(self) -> bool:
        return self._anim.state() == QPropertyAnimation.State.Running

    def setColor(self, color: str | QColor) -> None:
        self._color = QColor(color)
        self.update()

    def setSize(self, size: int) -> None:
        self._size = max(8, int(size))
        self.setFixedSize(self._size, self._size)

    # ---------------------------------------------------------- 显示事件
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._want_running and self._anim.state() != QPropertyAnimation.State.Running:
            self._anim.start()

    def hideEvent(self, event) -> None:
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        super().hideEvent(event)

    # ---------------------------------------------------------- 绘制
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        if side < 4:
            return
        margin = max(2, side // 12)
        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)
        pen_w = max(2.0, side / 10.0)

        # 淡色轨道（整圈）
        track = QColor(self._color)
        track.setAlpha(70)
        p.setPen(
            QPen(track, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        p.drawArc(rect, 0, 360 * 16)

        # 旋转弧（约 110°，顺时针）
        p.setPen(
            QPen(
                QColor(self._color),
                pen_w,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        start = int(self._angle * 16)
        p.drawArc(rect, -start, 110 * 16)
        p.end()


# ============================================================ LoadingOverlay
class LoadingOverlay(QWidget):
    """半透明遮罩：盖在父组件上，中央显示 LoadingSpinner + 一行说明文字。

    用法::

        overlay = LoadingOverlay(self.list_widget)
        overlay.start("正在加载工坊列表…")
        ...
        overlay.stop()

    遮罩会跟随父组件尺寸变化（事件过滤器监听父级 Resize），并挡住父组件
    上的鼠标事件，起到“模态加载”效果。
    """

    def __init__(
        self,
        parent: QWidget,
        spinner_size: int = 40,
        radius: int = 10,
        overlay_color: str = "rgba(18, 18, 22, 180)",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self._radius = radius
        self._overlay_color = overlay_color
        # 不使用 WA_TranslucentBackground（只对顶层窗口生效），
        # 半透明效果完全由 paintEvent 里的 rgba 绘制完成。
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.spinner = LoadingSpinner(self, size=spinner_size)
        self.label = QLabel("加载中…", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            "color: #dfe2ea; font-size: 13px; background: transparent;"
        )
        self.label.setMaximumWidth(320)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)
        lay.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label, 0, Qt.AlignmentFlag.AlignCenter)

        self.setVisible(False)
        if parent is not None:
            parent.installEventFilter(self)

    # ---------------------------------------------------------- 公共接口
    def start(self, text: str = "正在加载…") -> None:
        """显示遮罩并开始旋转。text 为中央说明文字。"""
        self.label.setText(text)
        self._fit_to_parent()
        self.raise_()
        self.show()
        self.spinner.start()

    def stop(self) -> None:
        """隐藏遮罩并停止旋转。"""
        self.spinner.stop()
        self.hide()

    def setText(self, text: str) -> None:
        self.label.setText(text)

    # ---------------------------------------------------------- 内部
    def _fit_to_parent(self) -> None:
        p = self.parent()
        if p is None:
            return
        self.setGeometry(p.rect())

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._fit_to_parent()
        return super().eventFilter(obj, event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._overlay_color))
        p.drawRoundedRect(self.rect(), self._radius, self._radius)
        p.end()


# ============================================================ SmoothScrollBar
class SmoothScrollBar(QScrollBar):
    """平滑滚动条：value 发生跳变时用 QPropertyAnimation 缓动过渡。

    - 滚轮 / 点击页码 / 键盘翻页 → 220ms OutCubic 缓动，下拉上滑跟手不生硬；
    - 直接拖动滑块（isSliderDown）→ 立即跟手，不补动画；
    - 动画期间目标再次变化 → 动态更新 endValue，平滑追踪连续滚动。
    """

    _DURATION = 220

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(self._DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._prev = self.value()
        self.valueChanged.connect(self._on_value_changed)
        self.rangeChanged.connect(self._on_range_changed)

    # ---------------------------------------------------------- 范围变化
    def _on_range_changed(self, _minimum: int, _maximum: int) -> None:
        # 翻页清空 / 内容增减：停止进行中的动画，并延迟到 value 被 Qt
        # 钳制到新范围后再同步基准值，避免下次滚动从过时位置起步
        self._anim.stop()
        QTimer.singleShot(0, self._sync_baseline)

    def _sync_baseline(self) -> None:
        self._prev = self.value()

    # ---------------------------------------------------------- 滚动平滑
    def _on_value_changed(self, value: int) -> None:
        # 拖动滑块：直接跟手
        if self.isSliderDown():
            self._anim.stop()
            self._prev = value
            return

        running = self._anim.state() == QPropertyAnimation.State.Running
        if running:
            # 动画自身回写值（与动画当前插值一致）→ 忽略，避免反馈循环
            if value == self._anim.currentValue():
                return
            # 连续滚轮/快速操作：从当前插值位置重新规划到新目标的完整缓动。
            # 旧实现只 setEndValue 不重置 duration → 动画在剩余时间内追赶
            # 长距离，快速滚动时跳帧（bug1）。
            cur = self._anim.currentValue()
            self._anim.stop()
            if value != cur:
                self._anim.setStartValue(cur)
                self._anim.setEndValue(value)
                self._anim.setDuration(self._DURATION)
                self._prev = value
                self._anim.start()
            else:
                self._prev = value
            return

        if value == self._prev:
            return
        self._anim.setStartValue(self._prev)
        self._anim.setEndValue(value)
        self._prev = value
        self._anim.start()

    def isAnimating(self) -> bool:
        return self._anim.state() == QPropertyAnimation.State.Running

    @staticmethod
    def install_on(
        area: QAbstractScrollArea,
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
    ) -> "SmoothScrollBar":
        """把平滑滚动条安装到已有滚动区域上（替换原生滚动条）。"""
        bar = SmoothScrollBar(orientation, area)
        if orientation == Qt.Orientation.Vertical:
            area.setVerticalScrollBar(bar)
        else:
            area.setHorizontalScrollBar(bar)
        bar._prev = bar.value()
        return bar


# ============================================================ ElidedLabel
class ElidedLabel(QLabel):
    """单行文本自动省略标签。

    宽度不足以显示全文时自动在末尾加 “…”；同时把完整文本放进 ToolTip，
    鼠标悬停即可查看全文。
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._shown = ""
        self.setWordWrap(False)
        # 允许收缩到比文本更窄（布局中才会触发省略）
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(0)
        self.setText(text)

    def sizeHint(self) -> QSize:
        fm: QFontMetrics = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full_text), fm.height())

    def minimumSizeHint(self) -> QSize:
        fm: QFontMetrics = self.fontMetrics()
        return QSize(0, fm.height())

    def setText(self, text: str) -> None:
        self._full_text = "" if text is None else str(text)
        self._apply_elide()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        w = self.width()
        if w <= 0:
            # 还没布局，先给全文（sizeHint 按全文计算，避免布局抖动）
            if self._shown != self._full_text:
                self._shown = self._full_text
                super().setText(self._full_text)
            return
        fm: QFontMetrics = self.fontMetrics()
        elided = fm.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, w
        )
        if elided != self._shown:
            self._shown = elided
            super().setText(elided)
        if elided != self._full_text:
            self.setToolTip(self._full_text)
        else:
            self.setToolTip("")


# ============================================================ ModCard
class ModCard(QFrame):
    """模组列表项卡片。

    左侧缩略图（无图时代码生成占位图）、中间标题 + 标签 chips + 热度小字、
    右侧安装状态角标。所有数据通过 setData(dict) 传入，字段：

    - ``title`` (str)            标题
    - ``tags`` (list[str])       标签
    - ``subscriptions`` (int)    订阅数（热度）
    - ``preview_pixmap`` (QPixmap | None)  缩略图
    - ``installed`` (bool)       是否已安装
    - ``size_text`` (str)        体积描述，如 "42.3 MB"
    """

    clicked = Signal()

    _THUMB = 80
    _HEIGHT = 96
    _MAX_CHIPS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(self._HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setStyleSheet(
            f"""
            QFrame#modCard {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
            QFrame#modCard:hover {{
                border: 1px solid {CARD_BORDER_HOVER};
            }}
            """
        )
        self._data: dict = {}
        self._installed = False
        self._build()

    # ---------------------------------------------------------- 布局
    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # 缩略图
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(self._THUMB, self._THUMB)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet(
            f"background: {THUMB_BG}; border-radius: 8px;"
        )
        self.thumb.setPixmap(self._placeholder(self._THUMB))
        lay.addWidget(self.thumb)

        # 中间：标题 / 标签 / 热度
        mid = QVBoxLayout()
        mid.setSpacing(3)
        mid.setContentsMargins(0, 0, 0, 0)

        self.title_label = ElidedLabel("", self)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setStyleSheet(
            f"font-weight: 600; font-size: 13px; color: {TEXT_PRIMARY};"
            " background: transparent;"
        )
        self.title_label.setFixedHeight(20)
        mid.addWidget(self.title_label)

        self.chips_container = QWidget(self)
        self.chips_container.setStyleSheet("background: transparent;")
        self.chips_layout = QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(5)
        self.chips_layout.addStretch()
        self.chips_container.setFixedHeight(18)
        mid.addWidget(self.chips_container)

        self.meta_label = QLabel("", self)
        self.meta_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;"
        )
        self.meta_label.setFixedHeight(16)
        mid.addWidget(self.meta_label)

        lay.addLayout(mid, 1)

        # 右侧：安装状态角标
        self.status_label = QLabel("未安装", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedHeight(22)
        self.status_label.setMinimumWidth(58)
        self._apply_status_style(False)
        lay.addWidget(self.status_label)

    def _apply_status_style(self, installed: bool) -> None:
        if installed:
            bg, fg = INSTALLED_BG, INSTALLED_FG
        else:
            bg, fg = NOT_INSTALLED_BG, NOT_INSTALLED_FG
        self.status_label.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 8px;"
            " padding: 2px 8px; font-size: 11px;"
        )

    @classmethod
    def _placeholder(cls, size: int) -> QPixmap:
        """代码生成缩略图占位（渐变底 + 简笔图片图标）。"""
        pm = QPixmap(size, size)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor("#2b2b33"))
        grad.setColorAt(1.0, QColor("#1e1e24"))
        pm.fill(QColor(THUMB_BG))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(pm.rect(), QBrush(grad))
        edge = QColor("#4d4d59")
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(edge, max(1.5, size * 0.045)))
        m = size * 0.22
        p.drawRect(QRectF(m, m, size - 2 * m, size - 2 * m))
        p.setBrush(edge)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(
            QPointF(size * 0.38, size * 0.38), size * 0.055, size * 0.055
        )
        poly = QPolygonF(
            [
                QPointF(size * 0.30, size * 0.72),
                QPointF(size * 0.47, size * 0.50),
                QPointF(size * 0.61, size * 0.64),
                QPointF(size * 0.71, size * 0.54),
                QPointF(size * 0.71, size * 0.72),
            ]
        )
        p.drawPolygon(poly)
        p.end()
        return pm

    # ---------------------------------------------------------- 标签 chips
    def _clear_chips(self) -> None:
        while self.chips_layout.count() > 1:  # 保留末尾 stretch
            item = self.chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_chip(self, text: str) -> None:
        chip = QLabel(text, self.chips_container)
        chip.setStyleSheet(
            f"background: {CHIP_BG}; color: {CHIP_FG};"
            " border-radius: 8px; padding: 1px 8px; font-size: 10px;"
        )
        chip.setFixedHeight(16)
        self.chips_layout.insertWidget(self.chips_layout.count() - 1, chip)

    # ---------------------------------------------------------- 数据
    def setData(self, item: dict) -> None:
        """填充卡片数据（字典接口，不依赖核心层类型）。"""
        data = item or {}
        self._data = dict(data)

        title = str(data.get("title") or "").strip() or "未命名模组"
        tags = data.get("tags") or []
        if not isinstance(tags, (list, tuple)):
            tags = [tags]
        tags = [str(t).strip() for t in tags if str(t).strip()]

        try:
            subs = int(data.get("subscriptions") or 0)
        except (TypeError, ValueError):
            subs = 0

        size_text = str(data.get("size_text") or "").strip()
        installed = bool(data.get("installed"))

        # 缩略图
        pm = data.get("preview_pixmap")
        if isinstance(pm, QPixmap) and not pm.isNull():
            self.thumb.setPixmap(
                pm.scaled(
                    self.thumb.width(),
                    self.thumb.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.thumb.setPixmap(self._placeholder(self.thumb.width()))

        # 标题 / 标签 / 热度
        self.title_label.setText(title)
        self._clear_chips()
        for t in tags[: self._MAX_CHIPS]:
            self._add_chip(t)
        if len(tags) > self._MAX_CHIPS:
            self._add_chip(f"+{len(tags) - self._MAX_CHIPS}")

        meta = f"🔥 {subs:,} 订阅" if subs else "订阅数未知"
        if size_text:
            meta += f"  ·  {size_text}"
        self.meta_label.setText(meta)

        # 状态角标
        self._installed = installed
        self.status_label.setText("✓ 已安装" if installed else "未安装")
        self._apply_status_style(installed)

        self.update()

    def data(self) -> dict:
        return self._data

    @property
    def installed(self) -> bool:
        return self._installed

    # ---------------------------------------------------------- 事件
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
