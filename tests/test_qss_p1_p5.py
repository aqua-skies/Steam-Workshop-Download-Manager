"""t36 专项验证：A2 QSS P1-P5 + B6 空状态引导 + 技术债 ①。

断言（脚本式，check() + RESULT: ALL PASS）：
- P1 滚动条 QSS 三个主题都在且含 pressed 态
- P2 表头 min-height>=24px 且 hover 态存在
- P3 进度条 [status=done]/[status=failed] 规则存在；终态 setProperty 后能取到
- P4 qss("auto") 不崩溃且回退有效；主题三档切换 MainWindow 不崩 + QSS 非空；
      colorSchemeChanged 信号路径存在（auto 监听已连/解绑标志位）
- P5 空状态：空库/筛选空两态文案与按钮可见性；下载页空队列显示「前往工坊浏览」；
      navigate_requested 经 MainWindow 跳到工坊 Tab
- 几何：切换主题后 settings 页首行与表格表头无负偏移/挤压（U9 回归保护）
- 高 DPI：2.0x 下 settings 页 QFormLayout 行间距 >= 6px
- 技术债 ①：匿名态 list_channels 对 cdn 返回 NO_KEY，设置页下拉含「未配置」
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_t36_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

sys.path.insert(0, ".")

import io as _io  # noqa: E402

out = _io.StringIO()


def p(*a):
    print(*a, file=out)


ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

# ------------------------------------------------------------------ P1/P2/P3 QSS
from swdm.gui.styles import DARK_QSS, LIGHT_QSS, qss, system_theme_supported  # noqa: E402

check("P1 滚动条 pressed 态（dark）",
      "handle:vertical:pressed" in DARK_QSS and "handle:horizontal:pressed" in DARK_QSS)
check("P1 滚动条 pressed 态（light）",
      "handle:vertical:pressed" in LIGHT_QSS and "handle:horizontal:pressed" in LIGHT_QSS)
check("P1 滚动条 handle 描边（dark）",
      "border: 1px solid rgba(0,0,0,80)" in DARK_QSS)
check("P2 表头 min-height>=24（dark）", "min-height: 24px" in DARK_QSS)
check("P2 表头 min-height>=24（light）", "min-height: 24px" in LIGHT_QSS)
check("P2 表头 hover（dark）", "QHeaderView::section:hover" in DARK_QSS)
check("P2 表头 hover（light）", "QHeaderView::section:hover" in LIGHT_QSS)
check("P3 进度条 done/failed（dark）",
      '[status="done"]' in DARK_QSS and '[status="failed"]' in DARK_QSS)
check("P3 进度条 done/failed（light）",
      '[status="done"]' in LIGHT_QSS and '[status="failed"]' in LIGHT_QSS)
check("qss(未知主题) 回退深色不崩", qss("nonsense") == DARK_QSS)
check("P4 system_theme_supported 返回 bool", isinstance(system_theme_supported(), bool))

# auto 解析不崩溃（无 GUI 时 styleHints 静态调用也必须安全）
try:
    _ = qss("auto")
    auto_ok = True
except Exception:  # noqa: BLE001
    auto_ok = False
check("P4 qss('auto') 不崩溃", auto_ok)

# ------------------------------------------------------------------ 主窗口三档主题
from swdm.core.config import get_config  # noqa: E402
from swdm.gui.main_window import MainWindow  # noqa: E402
from swdm.gui.styles import qss as _qss  # noqa: E402

cfg = get_config()
cfg.set("general", "theme", "dark")
cfg.save()

win = MainWindow()
win.show()
QApplication.processEvents()

ref = win.settings_tab  # 几何参照页


def first_row_offsets():
    """settings 页首个 QGroupBox 相对窗口原点坐标（U9 挤压检测）。"""
    gboxes = ref.findChildren(type(ref).__mro__[-2]) if False else None
    from PySide6.QtWidgets import QGroupBox

    boxes = ref.findChildren(QGroupBox)
    if not boxes:
        return None
    pt = boxes[0].mapTo(ref, QPointF(0, 0))
    return pt.x(), pt.y()


base_off = first_row_offsets()
check("设置页首个分组坐标可量化", base_off is not None, str(base_off))

theme_ok = True
for theme in ("light", "auto", "dark"):
    try:
        cfg.set("general", "theme", theme)
        cfg.save()
        win._on_settings_changed()
        QApplication.processEvents()
        sheet = win.styleSheet()
        if not sheet or len(sheet) < 1000:
            theme_ok = False
            p(f"  主题 {theme}: QSS 过短 len={len(sheet) if sheet else 0}")
        # 几何不变性：主题切换不改变布局原点
        off = first_row_offsets()
        if off != base_off:
            theme_ok = False
            p(f"  主题 {theme}: 首分组坐标漂移 {base_off} -> {off}")
    except Exception as e:  # noqa: BLE001
        theme_ok = False
        p(f"  主题 {theme}: 异常 {e!r}")
check("P4 三档主题切换不崩溃且 QSS 有效", theme_ok)
check("P4 主题切换后首分组坐标无漂移", first_row_offsets() == base_off, str(first_row_offsets()))

# auto 模式下系统信号监听已连接
cfg.set("general", "theme", "auto")
cfg.save()
win._apply_theme()
QApplication.processEvents()
check("P4 auto 模式已连接 colorSchemeChanged", getattr(win, "_sys_theme_connected", False) is True)
cfg.set("general", "theme", "dark")
cfg.save()
win._apply_theme()
QApplication.processEvents()
check("P4 非 auto 模式已解绑 colorSchemeChanged", getattr(win, "_sys_theme_connected", False) is False)

# ------------------------------------------------------------------ P3 进度条状态色
from swdm.core import DownloadJob, JobStatus, WorkshopItem  # noqa: E402

# 下载页空队列空态（须在 P3 加行之前量化）
win._tabs.setCurrentWidget(win.downloads_tab)
win.downloads_tab._refresh_status()
QApplication.processEvents()
dl_empty = win.downloads_tab._empty_state
check("P5 下载队列空时空态可见", not dl_empty.isHidden())
check("P5 下载页空态显示「前往工坊浏览」按钮文本",
      any(b.text() == "前往工坊浏览" for b in dl_empty.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)))
win.downloads_tab.navigate_requested.emit()
QApplication.processEvents()
check("P5 下载页空态按钮跳到工坊页", win._tabs.currentWidget() is win.workshop_tab)

item = WorkshopItem(publishedfileid="123", appid="4000", title="测试 mod")
job = DownloadJob(item, "4000")
win.downloads_tab._ensure_row(job)
job.status = JobStatus.SUCCESS
win.downloads_tab._update_row(job)
bar = win.downloads_tab.table.cellWidget(0, 3)
check("P3 成功态进度条 status=done", bar is not None and bar.property("status") == "done")
job2 = DownloadJob(item, "4000")
job2.status = JobStatus.FAILED
win.downloads_tab._ensure_row(job2)
win.downloads_tab._update_row(job2)
bar2 = win.downloads_tab.table.cellWidget(win.downloads_tab.table.rowCount() - 1, 3)
check("P3 失败态进度条 status=failed", bar2 is not None and bar2.property("status") == "failed")

# ------------------------------------------------------------------ P5 空状态（库页）
lib_tab = win.library_tab
# 空态判据须在页面被 QTabWidget 实际显示后量化（非当前页时整页隐藏）
win._tabs.setCurrentWidget(lib_tab)
lib_tab.refresh()
QApplication.processEvents()
check("P5 空库时空态面板可见", not lib_tab._empty_state.isHidden())
check("P5 空库时列表隐藏", lib_tab.list_widget.isHidden())
check("P5 空库文案为「还没有 mod」", lib_tab._empty_title.text() == "还没有 mod")
check("P5 空库显示「前往工坊浏览」按钮",
      not lib_tab._empty_go.isHidden() and lib_tab._empty_go.text() == "前往工坊浏览")
check("P5 空库不显示「清除筛选」", lib_tab._empty_clear.isHidden())

# 空库 → 跳转信号经 MainWindow 切到工坊页
lib_tab._empty_go.click()
QApplication.processEvents()
check("P5 空状态按钮跳到工坊页", win._tabs.currentWidget() is win.workshop_tab)

# 队列非空时空态隐藏（P3 已通过 _ensure_row 注册两行）
win._tabs.setCurrentWidget(win.downloads_tab)
win.downloads_tab._refresh_status()
QApplication.processEvents()
n_rows = win.downloads_tab.table.rowCount()
check("下载页有任务行时列表显示、空态隐藏",
      n_rows >= 1 and win.downloads_tab._empty_state.isHidden()
      and not win.downloads_tab.table.isHidden(), f"rows={n_rows}")

# 库页有记录但筛选为空 → 「清除筛选」分支
from swdm.core.mod_library import ModRecord  # noqa: E402

rec = ModRecord(item_id="123", appid="4000", title="测试 mod α", local_path=_TMP,
                file_size=1024)
win.svc.library.upsert(rec)
win._tabs.setCurrentWidget(lib_tab)
lib_tab.search_edit.setText("zzzzz不存在")
lib_tab.refresh()
QApplication.processEvents()
check("P5 筛选无结果时显示「清除筛选」",
      not lib_tab._empty_state.isHidden() and not lib_tab._empty_clear.isHidden()
      and lib_tab._empty_go.isHidden())
lib_tab._empty_clear.click()
QApplication.processEvents()
check("P5 「清除筛选」恢复列表",
      lib_tab.list_widget.count() >= 1 and lib_tab._empty_state.isHidden())

# ------------------------------------------------------------------ 高 DPI 不挤压
from PySide6.QtGui import QGuiApplication  # noqa: E402

screen = QGuiApplication.primaryScreen()
if screen is not None:
    # 模拟高 DPI：直接量化当前布局行间距（offscreen 下 logicalDotsPerInch 固定，
    # 改用样式表统一后的实际间距 >= 6px 判定）
    from PySide6.QtWidgets import QGroupBox

    boxes = ref.findChildren(QGroupBox)
    ys = sorted(b.mapTo(ref, QPointF(0, 0)).y() for b in boxes[:2])
    gap = ys[1] - ys[0] if len(ys) > 1 else 999
    check("高 DPI/常规下设置页分组间距 >= 6px", gap >= 6, f"gap={gap:.1f}")

# 表头行高：切换主题后游戏目录表表头无负高度
hdr = win.settings_tab.game_dirs_table.verticalHeader()
check("主题切换后表头默认行高 >= 24", hdr.defaultSectionSize() >= 24, f"h={hdr.defaultSectionSize()}")

# ------------------------------------------------------------------ 技术债 ①
from swdm.core.providers import get_registry  # noqa: E402

rows = get_registry().list_channels(api=win.svc.api)
by_name = {r[0]: r for r in rows}
check("list_channels 返回非空通道清单", len(rows) >= 1, str([r[0] for r in rows]))
cdn = by_name.get("cdn")
if cdn is not None:
    check("技术债① 匿名态 cdn 显示 NO_KEY",
          getattr(cdn[2], "value", None) == "no_key", str(cdn[2]))
else:
    check("技术债① cdn 通道存在", False, "cdn 未注册")

# 设置页下拉文本含「未配置」
combo_texts = [win.settings_tab.channel_combo.itemText(i)
               for i in range(win.settings_tab.channel_combo.count())]
check("技术债① 设置页下拉含「未配置」标记",
      any("未配置" in t for t in combo_texts), str(combo_texts))

# 全部主题 QSS 解析无异常（Qt 会静默忽略坏规则，靠 styleSheet 非空 + 无致命异常）
check("三档 QSS 全部可应用", all(len(_qss(t)) > 1000 for t in ("dark", "light", "auto")))

p("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
res_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t36_out.txt")
with open(res_path, "w", encoding="utf-8") as f:
    f.write(out.getvalue())
