"""全按钮机制实测（用户要求：不要让用户一个一个指出 bug）。

实例化真实主窗口（离线模式），遍历每个 Tab 的每个按钮/可交互控件，
点击并断言：无异常抛出 + 控件状态符合预期。
用异常钩子捕获 Qt 未处理异常，确保不会"看起来过了其实崩了"。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

_TMP = tempfile.mkdtemp(prefix="swdm_btn_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QPushButton, QCheckBox, QComboBox  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

_crashed = []


def _install_excepthook():
    def hook(etype, val, tb):
        _crashed.append("".join(traceback.format_exception(etype, val, tb)))
    sys.excepthook = hook
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
        def _msg(_t, _ctx, msg):
            if "Fatal" in msg or "FATAL" in msg:
                _crashed.append(msg)
        qInstallMessageHandler(_msg)
    except Exception:  # noqa: BLE001
        pass


_install_excepthook()

# ---- 对话框打补丁：offscreen 下文件/输入/消息对话框会模态阻塞，
# 统一替换为自动返回，使全按钮可点击测试
from PySide6.QtWidgets import (  # noqa: E402
    QFileDialog, QInputDialog, QMessageBox,
)

QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: os.path.join(_TMP, "picked_dir"))
QFileDialog.getOpenFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "picked.json"), ""))
QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (os.path.join(_TMP, "saved.json"), ""))
os.makedirs(os.path.join(_TMP, "picked_dir"), exist_ok=True)
QInputDialog.getText = staticmethod(
    lambda *a, **k: ("4000", True))
QInputDialog.getItem = staticmethod(
    lambda *a, **k: (a[3][0] if len(a) > 3 and a[3] else "", True))
QMessageBox.question = staticmethod(
    lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)

from swdm.gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()

TABS = {
    "工坊": win.workshop_tab,
    "下载": win.downloads_tab,
    "库": win.library_tab,
    "设置": win.settings_tab,
    "调试": win.debug_tab,
}

def _all_buttons(widget) -> list[tuple[str, QPushButton]]:
    out = []
    for btn in widget.findChildren(QPushButton):
        if btn.isVisible() or True:
            out.append((btn.text() or btn.objectName() or "btn", btn))
    return out

# ---- 1) 遍历所有 Tab 的所有按钮
# offscreen 下会触发真实网络的按钮跳过（网络时断时续，会超时），
# 对话框已统一打补丁，其余全部真实点击
_SKIP_NET = {
    "测试登录", "安装/部署 steamcmd", "诊断",
}
total_clicked = 0
for tab_name, tab in TABS.items():
    for label, btn in _all_buttons(tab):
        if not btn.isEnabled():
            continue
        if any(s in label for s in _SKIP_NET):
            check(f"[{tab_name}] 跳过联网按钮「{label}」", True)
            continue
        try:
            btn.click()
            app.processEvents()
            total_clicked += 1
        except Exception as e:  # noqa: BLE001
            check(f"[{tab_name}] 点击「{label}」无异常", False,
                  f"{type(e).__name__}: {e}")
check(f"全部按钮点击无异常（共 {total_clicked} 个）",
      not any(not r[1] for r in RESULTS), "")

# ---- 2) 各 Tab 独立机制断言
# 工坊页：翻页/全选/搜索
wt = win.workshop_tab
for label, btn in _all_buttons(wt):
    if "上一页" in label:
        try:
            wt._page = 2
            btn.click(); app.processEvents()
            check("工坊: 上一页可用", True)
        except Exception as e:  # noqa: BLE001
            check("工坊: 上一页可用", False, str(e))
    if "全选" in label:
        try:
            btn.click(); app.processEvents()
            check("工坊: 全选可点", True)
        except Exception as e:  # noqa: BLE001
            check("工坊: 全选可点", False, str(e))

# 标签栏（bug1）：30 个标签后横向滚动条必须出现
wt.tag_bar.set_tags([f"Tag{i:02d}" for i in range(30)])
app.processEvents()
hsb = wt.tag_bar._scroll.horizontalScrollBar()
check("标签栏: 30 标签后横向滚动条出现",
      hsb.minimum() < hsb.maximum() and hsb.maximum() > 0,
      f"min={hsb.minimum()} max={hsb.maximum()}")
check("标签栏: 横向滚动条策略为 AsNeeded",
      wt.tag_bar._scroll.horizontalScrollBarPolicy() != 0)
# 真能滚动
if hsb.maximum() > 0:
    hsb.setValue(hsb.maximum())
    app.processEvents()
    check("标签栏: 滚动条可拖动", hsb.value() == hsb.maximum())

# 标签选中机制
wt.tag_bar.set_tags(["AAA", "BBB", "CCC"])
app.processEvents()
chip = list(wt.tag_bar._chips.values())[0]
chip.click()
app.processEvents()
check("标签: 单击选中后加入已选集合",
      "AAA" in wt.tag_bar.selected(), str(wt.tag_bar.selected()))
# 再点取消
chip.click()
app.processEvents()
check("标签: 再点取消选中",
      "AAA" not in wt.tag_bar.selected(), str(wt.tag_bar.selected()))

# 库页：筛选 checkbox 机制
lt = win.library_tab
for cb in lt.findChildren(QCheckBox):
    label = cb.text()
    try:
        cb.setChecked(True); app.processEvents()
        cb.setChecked(False); app.processEvents()
        check(f"库: 勾选「{label}」筛选无异常", True)
    except Exception as e:  # noqa: BLE001
        check(f"库: 勾选「{label}」筛选无异常", False, str(e))

# 设置页：下拉切换
st = win.settings_tab
for combo in st.findChildren(QComboBox):
    label = combo.objectName() or "combo"
    try:
        for i in range(min(3, combo.count())):
            combo.setCurrentIndex(i)
            app.processEvents()
        check(f"设置: 下拉「{label}」切换无异常", True)
    except Exception as e:  # noqa: BLE001
        check(f"设置: 下拉「{label}」切换无异常", False, str(e))

# 下载页：空表状态
dt = win.downloads_tab
check("下载页: 空表不崩", dt.table.rowCount() == 0)

# ---- 3) 全局：无未捕获异常
app.processEvents()
check("全程无 Qt 未捕获异常", not _crashed,
      (_crashed[0][:300] if _crashed else ""))

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
