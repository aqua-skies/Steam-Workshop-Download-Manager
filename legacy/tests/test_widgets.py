"""swdm/gui/widgets.py 组件冒烟测试（offscreen）。

逐个创建组件、启动动画、setData 塞 mock 数据、断言几何尺寸/可见性不崩。
运行：

    $env:PYTHONUTF8=1; $env:QT_QPA_PLATFORM="offscreen"; python tests/test_widgets.py
"""
from __future__ import annotations

import os
import sys
import time

# ---- 路径 / 平台环境（必须在创建 QApplication 之前设置） ----
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))
)
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, QPropertyAnimation, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from swdm.gui.styles import qss  # noqa: E402
from swdm.gui.widgets import (  # noqa: E402
    ElidedLabel,
    LoadingOverlay,
    LoadingSpinner,
    ModCard,
    SmoothScrollBar,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond), extra))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({extra})" if extra else ""))


def pump(ms: int) -> None:
    """推进事件循环 ms 毫秒（让动画 / 布局真实跑起来）。"""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


app = QApplication.instance() or QApplication(sys.argv)

# ---------------------------------------------------------------- 顶层测试窗口
win = QWidget()
win.setObjectName("central")
win.setWindowTitle("SWDM widgets smoke test")
win.resize(560, 640)
win.setStyleSheet(qss("dark"))
root_lay = QVBoxLayout(win)
root_lay.setContentsMargins(12, 12, 12, 12)
root_lay.setSpacing(10)


def make_dummy_pixmap(w: int = 80, h: int = 80) -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(QColor("#4a6cff"))
    return pm


# ================================================================ 1. LoadingSpinner
print("\n== LoadingSpinner ==")
spinner = LoadingSpinner(size=40, color="#7c5cff")
root_lay.addWidget(spinner)
spinner.start()
check("spinner 固定尺寸 40x40", spinner.width() == 40 and spinner.height() == 40,
      f"{spinner.width()}x{spinner.height()}")
spinner.setSize(56)
check("spinner setSize(56) -> 56x56", spinner.width() == 56 and spinner.height() == 56)
spinner.setColor("#ff5c5c")
spinner.angle = 137.5
check("spinner angle 落在 [0,360)", 0.0 <= spinner.angle < 360.0, f"angle={spinner.angle}")
check("spinner 动画已启动", spinner.isRunning())
pump(450)
check("spinner 旋转中动画仍在运行", spinner.isRunning())
check("spinner 旋转后角度仍在 [0,360)", 0.0 <= spinner.angle < 360.0, f"angle={spinner.angle:.1f}")
spinner.stop()
check("spinner.stop() 后动画停止", not spinner.isRunning())
check("spinner.stop() 后角度归零", spinner.angle == 0.0)
spinner.start()


# ================================================================ 2. LoadingOverlay
print("\n== LoadingOverlay ==")
host = QWidget()
host.setStyleSheet(qss("dark"))
host.resize(400, 300)
host_lay = QVBoxLayout(host)
host_lay.addWidget(QLabel("宿主页面内容（应被遮罩盖住）"))
overlay = LoadingOverlay(host, spinner_size=44)
check("overlay 初始不可见", not overlay.isVisible())
host.show()
overlay.start("正在加载工坊列表…")
pump(80)
check("overlay.start() 后可见", overlay.isVisible())
check("overlay 文本正确", overlay.label.text() == "正在加载工坊列表…",
      overlay.label.text())
check("overlay 覆盖宿主全部区域",
      overlay.geometry() == host.rect(), str(overlay.geometry()))
host.resize(520, 360)
pump(60)
check("overlay 跟随宿主 resize",
      overlay.geometry() == host.rect(), str(overlay.geometry()))
check("overlay 遮罩内 spinner 在运行", overlay.spinner.isRunning())
overlay.stop()
check("overlay.stop() 后不可见", not overlay.isVisible())
check("overlay.stop() 后 spinner 停止", not overlay.spinner.isRunning())
overlay.start("再次加载")
check("overlay 可反复 start", overlay.isVisible())
overlay.stop()


# ================================================================ 3. SmoothScrollBar
print("\n== SmoothScrollBar ==")
area = QScrollArea()
area.setStyleSheet(qss("dark"))
content = QWidget()
clay = QVBoxLayout(content)
for i in range(40):
    clay.addWidget(QLabel(f"列表行 {i}: 一些足够长的内容，用来撑出纵向滚动范围"))
content.setStyleSheet("background: #23232a;")
area.setWidget(content)
area.setWidgetResizable(True)
bar = SmoothScrollBar.install_on(area)
root_lay.addWidget(area, 1)
win.show()
pump(120)
check("SmoothScrollBar 安装成功", isinstance(bar, SmoothScrollBar))
check("QScrollArea 内滚动条范围 > 0", bar.maximum() > 0, f"max={bar.maximum()}")
check("滚动条初始值 0", bar.value() == 0)
target = max(100, bar.maximum() // 2)
bar.setValue(target)
pump(120)
check("滚动动画进行中", bar.isAnimating(), f"value={bar.value()}")
pump(800)
check("QScrollArea 内滚动落到目标值",
      bar.value() == target and not bar.isAnimating(), f"value={bar.value()}")

# 独立滚动条（显式范围，完全确定性）：验证平滑过渡 / 回零 / 连续追踪
solo = SmoothScrollBar(Qt.Orientation.Vertical)
solo.setParent(win)
solo.setRange(0, 1000)
solo.setFixedHeight(200)
solo.setValue(0)
check("独立滚动条范围正确", solo.maximum() == 1000 and solo.value() == 0)
solo.setValue(600)
pump(120)
check("独立滚动条滚动动画进行中", solo.isAnimating(), f"value={solo.value()}")
pump(800)
check("独立滚动条最终落到 600", solo.value() == 600 and not solo.isAnimating(),
      f"value={solo.value()}")
solo.setValue(0)
pump(800)
check("独立滚动条回到 0", solo.value() == 0, f"value={solo.value()}")
# 连续滚动：动画期间目标再次变化 → 追踪
solo.setValue(300)
pump(80)
solo.setValue(900)
pump(1000)
check("连续滚动最终落到 900", solo.value() == 900, f"value={solo.value()}")


# ================================================================ 4. ModCard
print("\n== ModCard ==")
card = ModCard()
card.clicked.connect(lambda: results.append(("card clicked", True, "")))
root_lay.addWidget(card)
card.setData({
    "title": "超能装甲：终结者前线— 一段非常非常长的模组标题用来测试省略",
    "tags": ["武器", "护甲", "剧情", "地图", "其他"],
    "subscriptions": 1234567,
    "preview_pixmap": make_dummy_pixmap(120, 120),
    "installed": True,
    "size_text": "42.3 MB",
})
win.show()
pump(120)
check("ModCard 固定高度 96", card.height() == 96, f"h={card.height()}")
check("ModCard 宽度 > 0", card.width() > 0, f"w={card.width()}")
check("ModCard 标题非空", card.title_label.text() != "", card.title_label.text())
check("ModCard 标题被省略（以 … 结尾）", card.title_label.text().endswith("…"),
      card.title_label.text()[-10:])
check("ModCard 省略时 ToolTip 含全文",
      card.title_label.fullText() in card.title_label.toolTip()
      or card.title_label.toolTip() == "", card.title_label.toolTip()[:20])
check("ModCard 热度小字含订阅数", "1,234,567" in card.meta_label.text(), card.meta_label.text())
check("ModCard 热度小字含大小", "42.3 MB" in card.meta_label.text())
n_chips = card.chips_layout.count() - 1  # 末尾 stretch 不算
check("ModCard chips 数 = 3 + 1 溢出标记", n_chips == 4, f"chips={n_chips}")
check("ModCard 已安装角标", card.status_label.text() == "✓ 已安装" and card.installed)
check("ModCard 缩略图已设置", not card.thumb.pixmap().isNull())
check("ModCard data() 回读", card.data().get("subscriptions") == 1234567)
press = QMouseEvent(
    QEvent.Type.MouseButtonPress,
    QPointF(card.rect().center()),
    Qt.MouseButton.LeftButton,
    Qt.MouseButton.LeftButton,
    Qt.KeyboardModifier.NoModifier,
)
QApplication.sendEvent(card, press)
check("ModCard clicked 信号", any(r[0] == "card clicked" for r in results))

# 未安装 + 无图 + 空数据兜底
card2 = ModCard()
card2.setData({"title": "简单模组", "tags": ["建筑"], "installed": False})
root_lay.addWidget(card2)
card3 = ModCard()
card3.setData({})  # 空字典不应崩溃
root_lay.addWidget(card3)
pump(120)
check("ModCard(未安装) 角标", card2.status_label.text() == "未安装" and not card2.installed)
check("ModCard(空数据) 标题兜底", card3.title_label.text() == "未命名模组",
      card3.title_label.text())
check("ModCard(无图) 占位图非空", not card3.thumb.pixmap().isNull())


# ================================================================ 5. ElidedLabel
print("\n== ElidedLabel ==")
el = ElidedLabel("A".join("标题文字" * 8) + "尾部", win)
el.setFixedHeight(20)
root_lay.addWidget(el)
el.resize(120, 20)
el._apply_elide()
pump(60)
check("ElidedLabel 宽度受限时省略（以 … 结尾）", el.text().endswith("…"),
      el.text()[-8:])
check("ElidedLabel 省略时 ToolTip 含全文",
      el.fullText() in el.toolTip() or el.toolTip() == "")
el2 = ElidedLabel("短文本", win)
el2.setFixedHeight(20)
el2.resize(400, 20)
el2._apply_elide()
check("ElidedLabel 宽度充足时不省略", el2.text() == "短文本", el2.text())
check("ElidedLabel 不省略时无 ToolTip", el2.toolTip() == "")
el3 = ElidedLabel("resize 后应重新省略的较长标题文本")
# 不加入布局，手动控制宽度（布局会强制自己的几何）
el3.setParent(win)
el3.setFixedHeight(20)
el3.resize(300, 20)
el3._apply_elide()
pump(40)
check("ElidedLabel 宽度充足不省略", not el3.text().endswith("…"), el3.text()[-8:])
el3.resize(50, 20)
el3._apply_elide()
pump(40)
check("ElidedLabel resize 后重新省略", el3.text().endswith("…"), el3.text()[-8:])


# ================================================================ 6. QSS 兜底
print("\n== QSS ==")
check("qss('dark') 非空且含 #central 选择器",
      "QWidget#central" in qss("dark") and len(qss("dark")) > 1000)
check("qss('light') 非空且含 #central 选择器",
      "QWidget#central" in qss("light") and len(qss("light")) > 1000)
check("QSS 覆盖 QPushButton/菜单/滚动条/分组框",
      all(k in qss("dark") for k in
          ("QPushButton:hover", "QMenu::item:selected", "QScrollBar::handle:vertical",
           "QGroupBox::title", "QListWidget::item:hover", "QSpinBox", "QComboBox")))


# ================================================================ 结束
def write_report_and_exit() -> int:
    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 60)
    print(f"检查项总数: {len(results)}   通过: {len(results) - len(failed)}   "
          f"失败: {len(failed)}")
    if failed:
        print("失败项:")
        for name, _, extra in failed:
            print(f"  - {name} {extra}")
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_widgets_out.txt"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("FAIL\n" if failed else "PASS\n")
        for name, ok, extra in results:
            f.write(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}\n")
    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def finalize() -> None:
    """事件循环里收尾：截图后退出事件循环（退出码在 exec 返回后处理）。"""
    pump(200)
    # 截图（offscreen 下若不支持则跳过）
    try:
        screen = app.primaryScreen()
        pix = screen.grabWindow(win.winId())
        shot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
        os.makedirs(shot_dir, exist_ok=True)
        pix.save(os.path.join(shot_dir, "widgets.png"), "PNG")
    except Exception as exc:  # noqa: BLE001
        print(f"(截图跳过: {exc})")
    app.quit()


# 让窗口在事件循环里真实渲染一轮（验证 paintEvent 不崩），再收尾
QTimer.singleShot(600, finalize)
# 总超时保护：防止事件循环卡死
QTimer.singleShot(10000, lambda: (print("TIMEOUT"), app.quit()))

code = app.exec()
print(f"事件循环退出 code={code}")
sys.exit(write_report_and_exit())
