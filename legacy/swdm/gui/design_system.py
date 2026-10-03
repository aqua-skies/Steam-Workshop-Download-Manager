"""SWDM Design System 2.0 tokens + QSS overlay loader (设计令牌系统).

令牌的单一事实来源是 docs/design/design_tokens.md；本模块是它的 Python 副本，
供自绘控件（paintEvent / QGraphicsDropShadowEffect / QPropertyAnimation）取用，
保证 QSS 与自绘视觉一致。QSS 副本为 swdm/resources/qss/{dark,light}.qss。

装配关系（「保留旧 qss 兼容」）：
    design_qss(theme) = styles.qss(theme)  [1.x 旧 QSS，签名/行为不变]
                     + 主题 overlay        [本模块加载的 2.0 层，级联后者胜出]
资源文件缺失或读取异常时静默降级为纯旧 QSS，不抛异常。

开关：config.general.ui_style，modern（默认）→ 2.0；classic → 纯 1.x。
"""

from __future__ import annotations

import os

from swdm.core.paths import resource_path
from swdm.gui.styles import qss as _legacy_qss, _resolve_theme

# ============================================================ 设计令牌（Python 副本）
# 与 docs/design/design_tokens.md 保持一致；改令牌必须三处同步：
# 文档 / resources/qss/*.qss / 本字典。

DARK_TOKENS = {
    # 表面阶梯（canvas 深一档，卡片浮起的前提）
    "surface": {
        "canvas": "#16161C",
        "sidebar": "#1A1A20",
        "card": "#1E1E24",
        "card_hover": "#25252D",
        "input": "#26262E",
        "raised": "#2B2B34",
        "selected": "#32285E",
    },
    # 描边
    "stroke": {
        "hairline": "#2B2B33",
        "card": "#2E2E37",
        "input": "#3A3A45",
        "hover": "#4A4A57",
        "focus": "#7C5CFF",
    },
    # 文本
    "text": {
        "primary": "#E8EAF0",
        "secondary": "#9AA3AF",
        "tertiary": "#6E757F",
        "disabled": "#5A6068",
        "on_accent": "#FFFFFF",
    },
    # 强调与语义
    "accent": {"400": "#8F74FF", "500": "#7C5CFF", "600": "#6A48F0"},
    "link": {"default": "#66C0F4", "hover": "#8CD4FF"},
    "success": "#43B581",
    "danger": "#F04747",
    "warning": "#FAA61A",
}

LIGHT_TOKENS = {
    "surface": {
        "canvas": "#F2F3F6",
        "sidebar": "#E9EBEF",
        "card": "#FFFFFF",
        "card_hover": "#F7F8FA",
        "input": "#FFFFFF",
        "raised": "#FFFFFF",
        "selected": "#E7E0FB",
    },
    "stroke": {
        "hairline": "#DDE1E6",
        "card": "#E3E6EB",
        "input": "#C8CCD2",
        "hover": "#B6BCC5",
        "focus": "#6D4AFF",
    },
    "text": {
        "primary": "#23272E",
        "secondary": "#5A6169",
        "tertiary": "#8A919A",
        "disabled": "#AAB0B8",
        "on_accent": "#FFFFFF",
    },
    "accent": {"400": "#7D5CFF", "500": "#6D4AFF", "600": "#5B3CE0"},
    # 浅色链接深化至 ≥4.5:1（#66C0F4 在白底仅 2.4:1）
    "link": {"default": "#1F7EB8", "hover": "#1463A0"},
    "success": "#2F9E6B",
    "danger": "#D63C3C",
    "warning": "#C77E00",
}

# 圆角：xs 3（chip/缩略图，Steam）/ sm 5（item，PCL2）/ md 6（按钮/输入）
# / lg 8（卡片/对话框）/ pill 999
RADIUS = {"xs": 3, "sm": 5, "md": 6, "lg": 8, "pill": 999}

# 间距：4pt 栅格
SPACING = {1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32}

# 字号（px）与字重
TYPE = {
    "caption": (10, 400),
    "body_sm": (11, 400),
    "body": (12, 400),
    "title_sm": (13, 600),
    "title": (15, 600),
    "title_lg": (18, 600),
    "hero": (22, 700),
}

# 动效令牌（QSS 无 transition，动画由 Python 侧实现）
# 时长取自 PCL2 实测甜点；曲线 ease-fluent-out ≈ QEasingCurve.OutQuint
MOTION = {
    "color": 90,      # 悬停颜色过渡
    "fast": 150,      # 高度/缩放/进入
    "base": 200,      # 淡入淡出/退出
    "slow": 250,      # 旋转/大位移
    "spring": 300,    # 强调反馈（收藏/撤销）
}

# 字体族（Windows 中英文双覆盖）
FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'


def tokens(theme: str) -> dict:
    """按主题名取令牌字典（"auto" 解析系统配色，未知主题回退 dark）。"""
    return LIGHT_TOKENS if _resolve_theme(theme) == "light" else DARK_TOKENS


def ui_style() -> str:
    """配置开关：general.ui_style = modern（默认）/ classic。"""
    try:
        from swdm.core.config import get_config

        style = get_config().get("general", "ui_style", default=None)
        return "classic" if style == "classic" else "modern"
    except Exception:  # noqa: BLE001
        return "modern"


# ============================================================ QSS overlay 装配

def _overlay_path(theme: str) -> str:
    return resource_path("swdm", "resources", "qss", f"{theme}.qss")


def _load_overlay(theme: str) -> str:
    """读取 2.0 overlay QSS；失败返回空串（降级为纯旧 QSS）。"""
    resolved = _resolve_theme(theme)
    path = _overlay_path(resolved)
    try:
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return ""


def design_qss(theme: str) -> str:
    """装配完整主题 QSS：1.x 旧 QSS + 2.0 overlay。

    - classic 开关或 overlay 缺失 → 纯旧 QSS（1.4.1 观感，兼容回退）。
    - modern（默认）→ 旧 QSS 垫底 + overlay 叠加，级联后者胜出。
    """
    legacy = _legacy_qss(theme)
    if ui_style() != "modern":
        return legacy
    overlay = _load_overlay(theme)
    if not overlay.strip():
        return legacy
    return legacy + "\n" + overlay


def overlay_available(theme: str) -> bool:
    """2.0 overlay 资源是否就位（诊断/测试用）。"""
    return bool(_load_overlay(theme).strip())


def prepare_scroll_area(scroll) -> None:
    """滚动区透明化：QSS 到不了的 autoFillBackground 坑（1.4.1 遗留）。

    根因：QAbstractScrollArea 的视口与其内容件 autoFillBackground=True，
    palette 沿用 QApplication 亮色默认（#efefef），在深色主题上画出整块浅灰。
    QSS 层无法覆盖（`#qt_scrollarea_viewport` 规则不匹配内容件；
    `QScrollArea { background: transparent }` 反把视口解析成实色黑），
    故在代码侧关闭 autofill，露出画布/面板色，卡片靠表面阶梯浮起。

    用法：QScrollArea 完成 setWidget 之后调用一次。
    """
    try:
        vp = scroll.viewport()
        if vp is not None:
            vp.setAutoFillBackground(False)
        content = scroll.widget()
        if content is not None:
            content.setAutoFillBackground(False)
    except (AttributeError, RuntimeError):  # noqa: BLE001
        pass
