"""t42（A1 用户手册）回归测试：手册交付物与帮助入口。

断言（脚本式，check() + RESULT: ALL PASS）：
- 手册源文件 docs/manual/SWDM用户手册.md 存在且扉页声明版本 == APP_VERSION
- 手册引用的图片全部存在于 docs/manual/images/
- 手写目录锚点全部能解析到标题（与构建脚本同 slug 规则）
- 构建产物存在：dist/SWDM-用户手册.html 非空、内嵌 >=5 张 base64 图、
  以 <!DOCTYPE html> 开头；Edge 可用时 PDF 非空；dist 缺失时自动重建
- 帮助入口：若 MainWindow 已接线「帮助 > 用户手册」动作，则其目标文件存在
  （当前由 installer-fixer/packager 负责接线，未接线时 SKIP 并提示打包后复测）
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_manual_t_")
os.environ["APPDATA"] = _TMP
os.environ["PYTHONUTF8"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

import io as _io  # noqa: E402

out = _io.StringIO()
ok = True


def p(*a):
    print(*a, file=out)


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


# ------------------------------------------------------------------ 源文件与版本
MANUAL_MD = os.path.join(_ROOT, "docs", "manual", "SWDM用户手册.md")
IMG_DIR = os.path.join(_ROOT, "docs", "manual", "images")
DIST_DIR = os.path.join(_ROOT, "docs", "manual", "dist")

check("手册源文件存在", os.path.exists(MANUAL_MD), MANUAL_MD)
md_text = ""
if os.path.exists(MANUAL_MD):
    with open(MANUAL_MD, encoding="utf-8") as f:
        md_text = f.read()

from swdm.core.paths import APP_VERSION  # noqa: E402

m_ver = re.search(r"版本\s*(\d+\.\d+\.\d+)", md_text)
declared = m_ver.group(1) if m_ver else None
check("扉页版本声明存在", declared is not None, declared or "")
check("扉页版本 == APP_VERSION（版本绑定）", declared == APP_VERSION,
      f"{declared} vs {APP_VERSION}")

# ------------------------------------------------------------------ 图片与锚点
imgs = re.findall(r"!\[.*?\]\(([^)]+)\)", md_text)
check("手册引用 >=5 张截图", len(imgs) >= 5, f"{len(imgs)} 张")
missing = [i for i in imgs if not os.path.exists(os.path.join(_ROOT, "docs", "manual", i))]
check("引用图片全部存在", not missing, "缺: " + ",".join(missing))

import build_manual  # noqa: E402  复用构建脚本的 slug 规则与 HTML 构建

headings = re.findall(r"^#{1,4}\s+(.+)$", md_text, re.MULTILINE)
ids = {build_manual._slugify(h) for h in headings}
anchors = re.findall(r"\(#([^)]+)\)", md_text)
bad = [a for a in anchors if a not in ids]
check("目录锚点全部解析", not bad, "坏锚点: " + ",".join(bad))

# ------------------------------------------------------------------ 构建产物
html_path = os.path.join(DIST_DIR, "SWDM-用户手册.html")
pdf_path = os.path.join(DIST_DIR, "SWDM-用户手册.pdf")

if not (os.path.exists(html_path) and os.path.exists(pdf_path)):
    p("[INFO] dist 产物缺失，调用 build_manual.main() 重建")
    build_ok = build_manual.main() == 0
    check("重建构建退出码 0", build_ok)
if os.path.exists(html_path):
    html = open(html_path, encoding="utf-8").read()
    check("HTML 非空且为文档头", len(html) > 10000 and html.lstrip().startswith("<!DOCTYPE html>"),
          f"{len(html)}B")
    check("HTML 内嵌全部截图", html.count("data:image/png;base64,") >= len(imgs),
          f"{html.count('data:image/png;base64,')} 张")
else:
    check("HTML 存在", False, html_path)

edge_here = any(os.path.exists(p_) and os.path.isfile(p_)
                for p_ in build_manual.EDGE_CANDIDATES)
if edge_here:
    check("PDF 存在且非空", os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 5000,
          f"{os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0}B")
else:
    p("[SKIP] 本机无 Edge，PDF 检查让位（HTML 为最低交付物）")

# ------------------------------------------------------------------ 帮助入口
# packager/installer-fixer 负责「帮助 > 用户手册」接线和随包打入 dist 产物。
# 未接线时本节 SKIP 且不实例化 MainWindow（规避 Qt 拆卸偶发崩溃污染基线）；
# 一旦 main_window.py 出现「用户手册」字样（接线完成），本节自动转为硬断言。
_mw_src = os.path.join(_ROOT, "swdm", "gui", "main_window.py")
wire_present = os.path.exists(_mw_src) and "用户手册" in open(
    _mw_src, encoding="utf-8").read()
if not wire_present:
    p("[SKIP] 帮助 > 用户手册 未接线（packager 负责接线+随包打入 dist），"
      "接线后（main_window.py 含「用户手册」）本节自动转为硬断言")
else:
    try:
        from PySide6.QtWidgets import QApplication  # noqa: E402

        app = QApplication.instance() or QApplication(sys.argv)
        from swdm.gui.main_window import MainWindow  # noqa: E402

        win = MainWindow()
        help_actions = []

        def _collect(actions, prefix=""):
            for a in actions:
                t = a.text() if hasattr(a, "text") else ""
                if any(k in t for k in ("手册", "帮助", "Help")):
                    help_actions.append((prefix + t, a))
                if a.menu() is not None:
                    _collect(a.menu().actions(), prefix + t + " > ")

        _collect(win.menuBar().actions())
        check("帮助入口动作存在", bool(help_actions),
              ",".join(t for t, _ in help_actions))
        if help_actions:
            check("帮助入口目标（dist HTML）存在", os.path.exists(html_path))
        win.close()
    except Exception as e:  # noqa: BLE001
        check("帮助入口检查未抛异常", False, str(e))

print(out.getvalue().rstrip(), flush=True)
# MainWindow 的 Qt 线程拆卸可能产生退出码噪音/硬崩溃（既有测试同类问题，
# 判定标准为 stdout RESULT 行），故提前 flush 保证 RESULT 不丢
print("RESULT: ALL PASS" if ok else "RESULT: FAIL", flush=True)
sys.stdout.flush()
sys.exit(0 if ok else 1)
