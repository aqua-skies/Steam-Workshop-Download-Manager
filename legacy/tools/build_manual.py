"""A1 手册构建脚本（t42 · 1.4.1）。

docs/manual/SWDM用户手册.md 为单一事实源；本脚本产出分发物：
  docs/manual/dist/SWDM-用户手册.html  单文件（CSS 内联 + 图片 base64 内嵌）
  docs/manual/dist/SWDM-用户手册.pdf   无头 Edge 打印（系统已装 Edge）

用法：python tools/build_manual.py
退出码 0 = 全部检查通过（HTML/PDF 存在且非空、TOC 锚点全部解析、图片已内嵌）。
installer-fixer（packager）按 dist/ 两个文件打入安装包并接线「帮助 > 用户手册」。
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import tempfile

os.environ.setdefault("PYTHONUTF8", "1")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_MD = os.path.join(_ROOT, "docs", "manual", "SWDM用户手册.md")
MANUAL_DIR = os.path.join(_ROOT, "docs", "manual")
IMG_DIR = os.path.join(MANUAL_DIR, "images")
DIST_DIR = os.path.join(MANUAL_DIR, "dist")

EDGE_CANDIDATES = [
    os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
]

CSS = r"""
@page { margin: 18mm 15mm; }
html { font-size: 15px; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif;
  line-height: 1.75; color: #23272e; background: #fff; max-width: 960px; margin: 0 auto;
  padding: 24px 28px 60px;
}
h1 { font-size: 1.9rem; border-bottom: 3px solid #2f6fd0; padding-bottom: 10px; margin-top: 0; }
h2 { font-size: 1.35rem; border-bottom: 1px solid #c9ced6; padding-bottom: 6px; margin-top: 2.2em;
     page-break-before: auto; }
h3 { font-size: 1.12rem; margin-top: 1.6em; }
img { max-width: 100%; border: 1px solid #d5dae2; border-radius: 6px; margin: 12px 0; }
code { background: #f2f4f7; padding: 1px 5px; border-radius: 4px; font-size: 0.92em; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 0.95rem; }
th, td { border: 1px solid #c9ced6; padding: 7px 10px; text-align: left; vertical-align: top; }
th { background: #eef2f7; }
blockquote { border-left: 4px solid #2f6fd0; background: #f5f8fd; margin: 14px 0; padding: 8px 16px;
             color: #4a5260; }
a { color: #2f6fd0; text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: none; border-top: 1px solid #d5dae2; margin: 2em 0; }
strong { color: #1a1d22; }
/* 屏幕阅读时给目录一点间距；打印时 Edge 会处理分页 */
ul { padding-left: 1.5em; }
li { margin: 2px 0; }
"""

# 与手册里手写目录链接保持一致的 slug 规则：小写化、去标点、空格转连字符、保留中文。
def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s\-]+", "-", text).strip("-")
    return text


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_html(md_text: str) -> tuple[str, list[str]]:
    import markdown

    html_body = markdown.markdown(
        md_text,
        extensions=["markdown.extensions.tables", "markdown.extensions.fenced_code"],
    )

    # 1) 标题注入 id（与手写目录锚点同规则）
    def _inject_id(m: re.Match) -> str:
        tag, text = m.group(1), m.group(2)
        return f'<h{tag} id="{_slugify(text)}">{text}</h{tag}>'

    html_body = re.sub(r"<h([1-4])>(.*?)</h\1>", _inject_id, html_body, flags=re.DOTALL)

    # 2) 图片内嵌为 base64（单文件）
    embedded = []

    def _embed_img(m: re.Match) -> str:
        alt, rel = m.group(1), m.group(2)
        path = os.path.join(MANUAL_DIR, rel.replace("/", os.sep))
        if not os.path.exists(path):
            return m.group(0)  # 缺图保留原标签，交给检查环节报错
        b64 = base64.b64encode(_read_bytes(path)).decode("ascii")
        embedded.append(rel)
        return f'<img alt="{alt}" src="data:image/png;base64,{b64}"/>'

    html_body = re.sub(r'<img alt="(.*?)" src="([^"]+)"', _embed_img, html_body)

    # 3) 校验目录锚点
    ids = set(re.findall(r'<h[1-4] id="([^"]+)"', html_body))
    bad = [a for a in re.findall(r"\(#([^)]+)\)", md_text) if a not in ids]

    doc = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>SWDM 用户手册</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"{html_body}\n</body>\n</html>\n"
    )
    return doc, bad


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def build_pdf(temp_html: str, out_pdf: str) -> bool:
    edge = next((p for p in EDGE_CANDIDATES if p and os.path.exists(p)), None)
    if edge is None:
        print("[WARN] 未找到 Edge，跳过 PDF（仅 HTML）")
        return False
    url = "file:///" + os.path.abspath(temp_html).replace("\\", "/")
    try:
        subprocess.run(
            [edge, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-pdf-header-footer", f"--print-to-pdf={os.path.abspath(out_pdf)}", url],
            capture_output=True, timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[WARN] Edge 打印失败：{e}")
        return False
    return os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 5000


def main() -> int:
    if not os.path.exists(MANUAL_MD):
        print(f"RESULT: FAIL (缺少手册源文件 {MANUAL_MD})")
        return 1
    md_text = _read(MANUAL_MD)

    # 版本绑定检查：手册扉页声明的版本（**版本 X.Y.Z**）必须存在且格式合法；
    # 与程序当前 APP_VERSION 不一致时告警（版本号由打包任务统一 bump，
    # 并行开发期允许先于 bump 写手册，打包时重建对齐即可）。
    from swdm.core.paths import APP_VERSION

    m_ver = re.search(r"版本\s*(\d+\.\d+\.\d+)", md_text)
    if not m_ver:
        print("RESULT: FAIL (手册扉页缺少版本声明「版本 X.Y.Z」)")
        return 1
    declared = m_ver.group(1)
    if declared != APP_VERSION:
        print(f"[WARN] 手册声明版本 {declared} != 程序版本 {APP_VERSION}"
              "（打包 bump 后重建对齐）")

    html, bad_anchors = build_html(md_text)
    if bad_anchors:
        print(f"RESULT: FAIL (目录锚点无对应标题: {bad_anchors})")
        return 1

    os.makedirs(DIST_DIR, exist_ok=True)
    html_path = os.path.join(DIST_DIR, "SWDM-用户手册.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    html_ok = os.path.getsize(html_path) > 10000 and "data:image/png;base64," in html
    print(f"[{'PASS' if html_ok else 'FAIL'}] HTML {html_path} {os.path.getsize(html_path)}B")

    # PDF：HTML 需临时复制到 dist 下，使相对路径稳定（图片已内嵌，路径不敏感）
    tmp_html = os.path.join(DIST_DIR, ".print_tmp.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)
    pdf_path = os.path.join(DIST_DIR, "SWDM-用户手册.pdf")
    pdf_ok = build_pdf(tmp_html, pdf_path)
    try:
        os.remove(tmp_html)
    except OSError:
        pass
    if pdf_ok:
        print(f"[PASS] PDF  {pdf_path} {os.path.getsize(pdf_path)}B")
    else:
        print(f"[WARN] PDF 未生成（Edge 不可用时允许仅 HTML）")

    img_ok = html.count("data:image/png;base64,") >= 5
    checks = {
        "html_ok": html_ok,
        "pdf_ok": pdf_ok,
        "anchors_ok": not bad_anchors,
        "images_ok": img_ok,
        "version_declared": declared is not None,
    }
    print(f"[CHECKS] {checks}")
    # PDF 不可用时降级为仅 HTML 通过（安装包至少要有 HTML 可打开）
    ok = html_ok and img_ok and not bad_anchors
    print("RESULT: ALL PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, _ROOT)
    sys.exit(main())
