"""设计令牌渲染自检（m4 · 1.4.2）。

offscreen 截图无法依赖读图工具（本机 sharp ERR_DLOPEN_FAILED / modlens
不稳定），改用**令牌色像素级断言**验证 QSS 令牌是否真正落到渲染层：
不读图、只比对设计令牌色在截图中的存在性与结构周期。

用法：
    python tools/make_readme_shots.py     # 先生成 docs/screenshots/*.png
    python tools/verify_design_shots.py   # 再跑本工具（dark 结构断言）
    python tools/verify_design_shots.py --light  # light 主题断言（现场渲染）

断言内容（dark）：
  - 卡片结构周期：canvas → 1px 描边 → 卡片 bg → 描边 → 6px 间隙重复出现
  - 卡片 bg #1E1E24 与画布 #16161C 精确可区分（tol=1，防止误判）
  - 输入框 / 状态栏 / 各文本色 / 链接色 / 强调色 / 悬停色存在
  - 无 #EFEFEF 面板级残留（1.4.1 遗留的视口 autoFill 亮灰，>50像素/行即判坏）

token 定义为单一事实来源：docs/design/design_tokens.md
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

SHOTS = os.path.join(_ROOT, "docs", "screenshots")


def _is(c, t, tol=3):
    return all(abs(c[i] - t[i]) <= tol for i in range(3))


def _px(img, x, y):
    return tuple(img.pixelColor(x, y).getRgb()[:3])


def verify_dark() -> int:
    """读 workshop.png，断言卡片令牌结构。"""
    from PySide6.QtGui import QImage

    path = os.path.join(SHOTS, "workshop.png")
    img = QImage(path)
    if img.width() == 0:
        print(f"FAIL 无法读取 {path}（先运行 tools/make_readme_shots.py）")
        return 1

    checks = []
    canvas = (0x16, 0x16, 0x1C)
    card = (0x1E, 0x1E, 0x24)
    border = (0x2E, 0x2E, 0x37)
    input_bg = (0x26, 0x26, 0x2E)
    hover = (0x25, 0x25, 0x2D)

    # 列 x=640 的颜色周期：canvas / border / card / border / gap
    runs, prev = [], None
    for y in range(190, min(760, img.height())):
        c = _px(img, 640, y)
        lbl = ("canvas" if _is(c, canvas) else "border" if _is(c, border)
               else "card" if _is(c, card) else "hover" if _is(c, hover) else "other")
        if lbl != prev:
            runs.append((y, lbl))
            prev = lbl
    checks.append((f"卡片结构周期（card runs={len([r for r in runs if r[1] == 'card'])}）",
                   len([r for r in runs if r[1] == "card"]) >= 5))
    checks.append((f"卡片间隙为画布色（gaps={len([r for r in runs if r[1] == 'canvas'])}）",
                   len([r for r in runs if r[1] == "canvas"]) >= 5))
    checks.append((f"1px 描边存在（border runs={len([r for r in runs if r[1] == 'border'])}）",
                   len([r for r in runs if r[1] == "border"]) >= 8))
    checks.append(("卡片 bg 精确 = #1E1E24",
                   any(_is(_px(img, 640, y), card, tol=1) for y in range(200, min(760, img.height())))))
    checks.append(("画布间隙精确 = #16161C",
                   any(_is(_px(img, 640, y), canvas, tol=1) for y in range(200, min(760, img.height())))))

    # 工具栏输入完好（没被透明化打穿）
    input_rows = [
        y for y in range(20, 160)
        if sum(1 for x in range(0, img.width(), 4) if _is(_px(img, x, y), input_bg)) > 200
    ]
    checks.append(("输入框 #26262E 完好", bool(input_rows)))

    def hits(color, step=3):
        return sum(1 for y in range(0, img.height(), step)
                   for x in range(0, img.width(), step) if _is(_px(img, x, y), color))

    for name, c, expect in [
        ("accent #7C5CFF", (0x7C, 0x5C, 0xFF), 100),
        ("cardHover #25252D", hover, 100),
        ("cardTitle #E8EAF0", (0xE8, 0xEA, 0xF0), 10),
        ("cardMeta #9AA3AF", (0x9A, 0xA3, 0xAF), 10),
        ("cardTags Steam蓝 #66C0F4", (0x66, 0xC0, 0xF4), 3),
    ]:
        n = hits(c)
        checks.append((f"{name}（{n}）", n >= expect))

    # 1.4.1 遗留：视口 autoFill #EFEFEF 亮灰面板残留
    bad = [y for y in range(img.height())
           if sum(1 for x in range(0, img.width(), 2)
                  if _is(_px(img, x, y), (239, 239, 239))) > 50]
    checks.append((f"无 #EFEFEF 面板残留（坏行 {len(bad)}）", len(bad) == 0))
    checks.append(("状态栏 #121218", _is(_px(img, 640, img.height() - 8), (0x12, 0x12, 0x18))))

    fails = []
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), "-", name)
        if not ok:
            fails.append(name)
    print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({fails})")
    return 0 if not fails else 1


def verify_light() -> int:
    """现场 offscreen 渲染 light 主题并断言（不污染 README 截图）。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PYTHONUTF8", "1")
    winfonts = os.path.join(os.environ.get("WINDIR") or r"C:\Windows", "Fonts")
    if os.path.isdir(winfonts):
        os.environ.setdefault("QT_QPA_FONTDIR", winfonts)
    tmp = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), "swdm_vds_light")
    os.makedirs(tmp, exist_ok=True)
    os.environ["APPDATA"] = tmp

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))

    from swdm.gui.design_system import design_qss
    from swdm.gui.main_window import MainWindow
    from swdm.core.steam_api import WorkshopItem

    win = MainWindow()
    win.setStyleSheet(design_qss("light"))
    win.resize(1280, 800)
    items = [
        WorkshopItem(publishedfileid="2537001001", title="Wiremod 进阶工具包 E2 扩展",
                     creator_name="AuthorA", appid="4000", file_size=24_500_000,
                     subscriptions=128_400, tags=["wiremod", "tool", "e2"]),
        WorkshopItem(publishedfileid="2537001002", title="RP 城市地图暮光之城 v3.2",
                     creator_name="AuthorB", appid="4000", file_size=310_400_000,
                     subscriptions=86_700, tags=["map", "roleplay"]),
        WorkshopItem(publishedfileid="2537001003", title="道具合成系统",
                     creator_name="AuthorC", appid="4000", file_size=1_200_000,
                     subscriptions=42_300, tags=["tool"]),
    ]
    win.workshop_tab._populate(items)
    win._tabs.setCurrentIndex(0)
    win.show()
    app.processEvents()
    img = win.grab().toImage()
    win.close()

    checks = []
    canvas = (0xF2, 0xF3, 0xF6)
    card = (0xFF, 0xFF, 0xFF)

    checks.append(("light 画布/pane = #F2F3F6", _is(_px(img, 640, 60), canvas)))

    runs, prev = [], None
    for y in range(190, 760):
        c = _px(img, 640, y)
        lbl = "card" if _is(c, card, tol=1) else ("canvas" if _is(c, canvas) else "other")
        if lbl != prev:
            runs.append((y, lbl))
            prev = lbl
    checks.append((f"light 白卡周期（runs={len([r for r in runs if r[1] == 'card'])}）",
                   len([r for r in runs if r[1] == "card"]) >= 3))
    checks.append(("light 卡片 = 纯白 #FFFFFF",
                   any(_is(_px(img, 640, y), card, tol=1) for y in range(190, 760))))

    def hits(color, step=3):
        return sum(1 for y in range(0, img.height(), step)
                   for x in range(0, img.width(), step) if _is(_px(img, x, y), color))

    checks.append((f"light 链接 #1F7EB8（{hits((0x1F, 0x7E, 0xB8), 2)}）",
                   hits((0x1F, 0x7E, 0xB8), 2) > 0))
    checks.append((f"light accent #6D4AFF（{hits((0x6D, 0x4A, 0xFF))}）",
                   hits((0x6D, 0x4A, 0xFF)) > 50))

    bad = [y for y in range(img.height())
           if sum(1 for x in range(0, img.width(), 2)
                  if _is(_px(img, x, y), (239, 239, 239), tol=2)) > 50]
    checks.append((f"light 无 #EFEFEF 面板残留（坏行 {len(bad)}）", len(bad) == 0))

    fails = []
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), "-", name)
        if not ok:
            fails.append(name)
    print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({fails})")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="SWDM 设计令牌渲染自检")
    ap.add_argument("--light", action="store_true", help="light 主题断言（现场渲染）")
    args = ap.parse_args()
    return verify_light() if args.light else verify_dark()


if __name__ == "__main__":
    sys.exit(main())
