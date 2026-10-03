"""SmoothScrollBar 翻页 bug 回归测试。

原始 bug：翻页 clear() 使内容范围收缩、value 被钳制（如 500→0），但滚动条
基准值 _prev 仍是 500；下次滚轮时动画从 500 起步 → viewport offset 与 item
布局错位 → 翻页后部分项消失、滚动后列表空白。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

app = QApplication.instance() or QApplication(sys.argv)

from swdm.gui.widgets import SmoothScrollBar  # noqa: E402

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

def pump(ms: int = 150) -> None:
    import time
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()

def build_list(n: int) -> tuple[QListWidget, SmoothScrollBar]:
    lw = QListWidget()
    for i in range(n):
        QListWidgetItem(f"item-{i}", lw)
    bar = SmoothScrollBar.install_on(lw)
    return lw, bar

win = QMainWindow()
win.resize(400, 300)
central = QWidget()
win.setCentralWidget(central)
lay = QVBoxLayout(central)

# --- 场景 1：滚动到中部 → 翻页清空 → 重填 → 滚动 ---
lw, bar = build_list(200)
lay.addWidget(lw)
win.show()
pump(120)

check("初始可滚动范围 > 0", bar.maximum() > 0, f"max={bar.maximum()}")
pump(600)  # 等初始动画结束

# 滚动到中部
mid = bar.maximum() // 2
bar.setValue(mid)
pump(900)
check("滚到中部后基准值同步", bar._prev == mid, f"_prev={bar._prev} value={bar.value()}")
pump(300)

# 翻页：清空（范围收缩，value 被钳制到 0）
lw.clear()
pump(60)
check("清空后 value 钳制为 0", bar.value() == 0, f"value={bar.value()}")
pump(60)
check("清空后基准值已同步为 0", bar._prev == 0, f"_prev={bar._prev}")

# 重填新页
for i in range(150):
    QListWidgetItem(f"new-{i}", lw)
pump(120)
check("重填后项数正确", lw.count() == 150, str(lw.count()))
pump(60)
check("重填后基准值仍是 0", bar._prev == 0, f"_prev={bar._prev}")

# 滚动：动画必须从当前值(0)起步，不能从旧值(mid)跳跃
bar.setValue(120)
pump(30)
anim = bar._anim
if anim.state() == anim.State.Running:
    sv = anim.startValue()
    check("动画起点是 0（非旧页位置）", sv == 0, f"start={sv}")
else:
    # 动画可能在 singleShot 回调前已被处理；直接验证 value 未跳跃
    check("value 未从旧值跳跃", 0 <= bar.value() <= 120, f"value={bar.value()}")
pump(900)
check("滚落后落在 120", bar.value() == 120, f"value={bar.value()}")

# --- 场景 2：独立滚动条连续追踪不受影响 ---
solo = SmoothScrollBar(Qt.Orientation.Vertical)
solo.setParent(win)
solo.setRange(0, 1000)
solo.setFixedHeight(200)
solo.setValue(0)
pump(120)
solo.setValue(300)
pump(80)
solo.setValue(900)
pump(1000)
check("连续追踪最终落到 900", solo.value() == 900, f"value={solo.value()}")

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
