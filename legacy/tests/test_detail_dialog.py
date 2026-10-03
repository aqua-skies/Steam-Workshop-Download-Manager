"""ModDetailDialog 自动化测试（offscreen 模式）。

验证：
  - 非模态弹窗可创建并 show()
  - 标题/作者/订阅/大小/更新时间正确渲染
  - 标签 chips 正确排列
  - set_comments / set_dependencies / set_conflicts 异步填充正确
  - 空态友好（评论/依赖/冲突为空时有提示）
  - 底部按钮可点击不崩；下载（含依赖）触发 downloader.enqueue
  - HTML 解析器（简介/评论/依赖）对真实页面结构有效
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from swdm.core import WorkshopItem  # noqa: E402
from swdm.gui.detail_dialog import (  # noqa: E402
    Comment,
    CommentWidget,
    DepRowWidget,
    ModDetailDialog,
    comment_total,
    parse_comments,
    parse_description,
)

app = QApplication.instance() or QApplication(sys.argv)

out_lines: list[str] = []


def p(*a) -> None:
    out_lines.append(" ".join(str(x) for x in a))


results: list[tuple[str, bool]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond)))
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def _all_text(w) -> str:
    """收集控件及其全部子 QLabel 的文本（跨 widget 类型通用）。"""
    from PySide6.QtWidgets import QLabel

    parts: list[str] = []
    if isinstance(w, QLabel):
        parts.append(w.text())
    for child in w.findChildren(QLabel):
        parts.append(child.text())
    return "\n".join(parts)


# ------------------------------------------------------------------ 测试数据
def make_item(**kw) -> WorkshopItem:
    base = dict(
        publishedfileid="1234567890",
        title="测试 Mod 标题",
        description="这是简介第一行\n第二行内容",
        creator="76561198000000000",
        creator_name="测试作者",
        appid="4000",
        file_size=1024 * 1024 * 12.5,
        subscriptions=98765,
        preview_url="",
        tags=["Build", "Roleplay", "Half-Life 2", "Map"],
        time_updated=1789976314,
    )
    base.update(kw)
    return WorkshopItem(**base)


class FakeDownloader:
    def __init__(self) -> None:
        self.queued: list[tuple[str, str]] = []   # (publishedfileid, appid)

    def enqueue(self, item, appid: str):
        self.queued.append((item.publishedfileid, str(appid)))
        return None


class FakeLibrary:
    def __init__(self, installed_ids: set[str] | None = None) -> None:
        self._installed = set(installed_ids or [])

    def get(self, item_id: str):
        if str(item_id) in self._installed:
            class _Rec:
                item_id = str(item_id)
                title = f"已安装 {item_id}"
                installed = True
            return _Rec()
        return None

    def search(self, keyword: str = ""):
        return []


# ------------------------------------------------------------------ 基础渲染
item = make_item()
dl = FakeDownloader()
dlg = ModDetailDialog(item, library=FakeLibrary(), downloader=dl)
dlg.show()

check("非模态弹窗创建并 show",
      dlg.windowModality() == Qt.WindowModality.NonModal and dlg.isVisible())
check("窗口标题含 mod 标题",
      "测试 Mod 标题" in dlg.windowTitle())
check("标题渲染", "测试 Mod 标题" in dlg.title_label.text())
check("作者渲染", "测试作者" in dlg.author_label.text())
check("订阅数渲染", "98,765" in dlg.meta_label.text())
check("文件大小渲染", "12.5 MB" in dlg.meta_label.text())
check("更新时间渲染", "2026" in dlg.meta_label.text() or "未知" in dlg.meta_label.text())
check("简介渲染（保留换行）",
      "这是简介第一行" in dlg.desc_edit.toPlainText()
      and "第二行内容" in dlg.desc_edit.toPlainText())
check("标签 chips 数量", dlg.tags_layout.count() == 4, f"n={dlg.tags_layout.count()}")
check("标签 chip 文本含 #", "#Build" in _all_text(dlg.tags_host))

# ------------------------------------------------------------------ 空态
dlg2 = ModDetailDialog(make_item(tags=[], description=""))
dlg2.show()
check("无标签时显示占位", "暂无标签" in _all_text(dlg2.tags_host))
check("空简介显示占位", dlg2.desc_edit.toPlainText() == "")
check("评论初始为加载中占位", "评论加载中" in _all_text(dlg2.comments_host))
check("依赖初始为加载中占位", "前置依赖加载中" in _all_text(dlg2.deps_host))
check("冲突区默认隐藏", not dlg2.conflict_frame.isVisible())

# ------------------------------------------------------------------ set_comments
comments = [
    Comment(author="张三", time="2026-09-20 12:38", content="好图，支持一下！"),
    Comment(author="李四", time="2026-09-19 09:12", content="这个 mod 真不错\n第二行"),
    {"author": "王五", "time": "2026-09-18", "content": "字典格式也可以"},
]
dlg.set_comments(comments)
check("评论渲染数量", dlg.comments_layout.count() == 3 + 1,   # +1 stretch
      f"n={dlg.comments_layout.count()}")
cws = [dlg.comments_layout.itemAt(i).widget() for i in range(3)]
check("评论控件类型", all(isinstance(w, CommentWidget) for w in cws))
check("评论作者渲染", "张三" in _all_text(cws[0]))
check("评论内容渲染", "好图，支持一下！" in _all_text(cws[0]))
check("评论换行保留", "这个 mod 真不错" in _all_text(cws[1]))

dlg.set_comments([])
check("空评论显示暂无评论", "暂无评论" in _all_text(dlg.comments_host))

# ------------------------------------------------------------------ set_dependencies
deps = [
    {"id": "1111111111", "title": "VJ Base"},
    ("2222222222", "[F76] SheepSquatch"),
    WorkshopItem(publishedfileid="3333333333", title="The Ability To Read"),
]
dlg.set_dependencies(deps)
check("依赖渲染数量", dlg.deps_layout.count() == 3 + 1, f"n={dlg.deps_layout.count()}")
drows = [dlg.deps_layout.itemAt(i).widget() for i in range(3)]
check("依赖控件类型", all(isinstance(w, DepRowWidget) for w in drows))
check("依赖 id 渲染", drows[0].id_label.text().find("1111111111") >= 0)
check("依赖标题渲染", "VJ Base" in drows[0].title_label.text())
check("依赖下载按钮可点击", drows[0].btn.isEnabled())
check("依赖下载按钮点击入队",
      (drows[0].btn.click(), dl.queued.count(("1111111111", "4000")) == 1)[1])

dlg.set_dependencies([])
check("空依赖显示暂无前置依赖", "暂无前置依赖" in _all_text(dlg.deps_host))

# ------------------------------------------------------------------ set_conflicts
conflicts = [
    {"id": "9999999999", "title": "冲突 Mod A", "reason": "本地库已安装此 mod，重复下载会覆盖现有版本"},
    ("9999999998", "冲突 Mod B", "内容冲突"),
]
dlg.set_conflicts(conflicts)
check("冲突区显示", dlg.conflict_frame.isVisible())
check("冲突标题渲染", "冲突 Mod A" in _all_text(dlg.conflict_list_host))
check("冲突原因渲染", "重复下载会覆盖" in _all_text(dlg.conflict_list_host))

dlg.set_conflicts([])
check("空冲突隐藏区域", not dlg.conflict_frame.isVisible())

# ------------------------------------------------------------------ 底部按钮
dlg.set_dependencies(deps)
dl.queued.clear()
dlg.dl_btn.click()
check("下载（含依赖）入队：依赖在前", dl.queued[0] == ("1111111111", "4000"),
      str(dl.queued[:2]))
check("下载（含依赖）入队：本 mod 在后",
      dl.queued[-1] == ("1234567890", "4000"), str(dl.queued[-2:]))
check("下载（含依赖）入队总数 = 依赖+1", len(dl.queued) == 4, str(dl.queued))
check("下载后按钮禁用", not dlg.dl_btn.isEnabled())

dl.queued.clear()
dlg.queue_btn.click()
check("加入队列仅本 mod", dl.queued == [("1234567890", "4000")], str(dl.queued))

close_hit = []
dlg.closeEvent = lambda e: close_hit.append(True)
# 关闭按钮（不真正关闭，避免影响后续测试）
btn_texts = [b.text() for b in dlg.findChildren(type(dlg.queue_btn))]
check("含关闭按钮", any("关闭" == t for t in btn_texts), str(btn_texts))

# ------------------------------------------------------------------ 预览图
dlg3 = ModDetailDialog(make_item(preview_url=""))
dlg3.show()
check("无预览 URL 显示占位", "暂无预览图" in dlg3.preview_label.text())

pix = QPixmap(64, 64)
pix.fill(Qt.GlobalColor.blue)
dlg3.set_preview_pixmap(pix)
check("预览图设置成功",
      dlg3.preview_label.pixmap() is not None
      and not dlg3.preview_label.pixmap().isNull())
dlg3._on_image_failed("测试失败")
check("图片失败显示占位", "预览图加载失败" in dlg3.preview_label.text())

# ------------------------------------------------------------------ HTML 解析
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
detail_path = os.path.join(FIX, "detail_4000_3803871160.html")
if os.path.isfile(detail_path):
    html = open(detail_path, encoding="utf-8").read()
    desc = parse_description(html)
    check("真实页面简介解析非空", len(desc) > 100, f"len={len(desc)}")
    check("真实页面简介含标题片段", "Coldridge Prison" in desc)

    total = comment_total(html)
    check("真实页面评论总数", total == 41, f"total={total}")

    cmts = parse_comments(html)
    check("真实页面评论解析非空", len(cmts) >= 5, f"n={len(cmts)}")
    if cmts:
        p(f"      首条评论: author={cmts[0].author!r} time={cmts[0].time!r} "
          f"content={cmts[0].content[:40]!r}")
        check("真实页面评论作者非空", cmts[0].author != "")
        check("真实页面评论时间非空", cmts[0].time != "")
        check("真实页面评论内容非空", cmts[0].content != "")
else:
    p("[SKIP] 无真实详情页 fixture，跳过 HTML 解析回归")

check("空 HTML 解析安全", parse_description("") == "" and parse_comments("") == []
      and comment_total("") == 0)

# ------------------------------------------------------------------ 事件循环收尾
def _finish() -> None:
    result = "\n".join(out_lines)
    print(result)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {'ALL PASS' if not failed else 'HAS FAILURES: ' + str(failed)}")
    app.quit()
    sys.exit(0 if not failed else 1)


QTimer.singleShot(300, _finish)
code = app.exec()
log_exit = code
sys.exit(0 if not any(not ok for _, ok in results) else 1)
