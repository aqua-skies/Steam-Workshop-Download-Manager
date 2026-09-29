"""生成应用图标（256x256，多尺寸 ico）。"""
import os
import sys

sys.path.insert(0, ".")

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "swdm", "resources", "icon.png")
OUT_ICO = OUT.replace(".png", ".ico")


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角背景：深蓝渐变近似
    radius = size // 6
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=(47, 111, 208, 255))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, outline=(90, 160, 250, 255), width=max(2, size // 80))
    # 工坊"扳手+齿轮"意象：用 W 字母 + 下载箭头
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.52))
    except OSError:
        font = ImageFont.load_default()
    text = "W"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2.4 - bbox[1]), text,
           fill=(255, 255, 255, 255), font=font)
    # 下载箭头（底部）
    aw = size // 5
    cx = size / 2
    ay = size * 0.72
    d.polygon([(cx - aw / 2, ay), (cx + aw / 2, ay), (cx, ay + aw)], fill=(255, 255, 255, 255))
    d.rectangle([cx - aw // 8, ay - aw * 0.55, cx + aw // 8, ay + aw * 0.15], fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    base = make(512)
    base.save(OUT)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(OUT_ICO, format="ICO", sizes=sizes)
    print("saved:", OUT, OUT_ICO)
