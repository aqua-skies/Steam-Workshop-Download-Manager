"""生成 SWDM 应用图标（多尺寸 .ico）。

使用 Pillow 绘制一个简约的“下载/工坊”风格图标：
深蓝 Steam 风背景 + 向下箭头（下载语义）。
输出：swdm/resources/icon.ico（含 16/32/48/64/128/256 多尺寸）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
BG = (27, 40, 56, 255)          # #1b2838 Steam 深蓝
BG_INNER = (42, 71, 94, 255)    # 内圈
ACCENT = (102, 192, 244, 255)   # #66c0f4 Steam 亮蓝
WHITE = (255, 255, 255, 255)


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(2, size // 16)
    radius = size // 5
    _rounded(draw, [margin, margin, size - margin, size - margin], radius, BG)

    # 内部圆环
    inset = int(size * 0.20)
    ring_w = max(2, size // 26)
    draw.ellipse(
        [inset, inset, size - inset, size - inset],
        outline=BG_INNER,
        width=ring_w,
    )

    # 中心向下箭头（下载）
    cx, cy = size // 2, size // 2
    w = int(size * 0.14)          # 箭杆半宽
    stem_top = int(size * 0.32)
    head_at = int(size * 0.60)
    head_w = int(size * 0.19)
    # 箭杆
    draw.rectangle([cx - w, stem_top, cx + w, head_at], fill=ACCENT)
    # 箭头三角
    draw.polygon(
        [
            (cx - head_w, head_at - max(1, size // 32)),
            (cx + head_w, head_at - max(1, size // 32)),
            (cx, int(size * 0.74)),
        ],
        fill=ACCENT,
    )
    # 顶部小横线点缀
    draw.line(
        [(cx - head_w, int(size * 0.26)), (cx + head_w, int(size * 0.26))],
        fill=WHITE,
        width=max(2, size // 32),
    )
    return img


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "swdm" / "resources" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]
    base = images[-1]
    base.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    images[-1].resize((64, 64), Image.LANCZOS).save(
        out.parent / "icon_preview.png", format="PNG"
    )
    print(f"icon written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
