"""resolve_dependency_tree 逻辑测试：用 mock 的 SteamAPI 验证递归/环路/深度截断/跳过已安装。"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_deptest_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from swdm.core import ModLibrary, SteamAPI, WorkshopItem, ensure_dirs  # noqa: E402

ensure_dirs()
out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


class FakeAPI(SteamAPI):
    """假 API：预设依赖图，不发网络请求。"""

    GRAPH = {
        "A": ["B", "C"],   # A 依赖 B、C
        "B": ["D"],        # B 依赖 D
        "C": [],           # C 无依赖
        "D": ["B"],        # D 依赖 B（环 B->D->B，防循环）
        "E": [],           # 独立
    }

    def __init__(self):
        pass  # 跳过父类初始化（不创建 session）

    def get_dependencies(self, item_id: str):
        return list(self.GRAPH.get(item_id, []))

    def get_file_details(self, item_ids):
        return {
            pid: WorkshopItem(publishedfileid=pid, title=f"mod-{pid}", appid="4000")
            for pid in item_ids
        }


api = FakeAPI()
lib = ModLibrary()

# 场景 1：基本递归（A -> B,C；B -> D）
root = WorkshopItem(publishedfileid="A", appid="4000")
deps, skipped = api.resolve_dependency_tree(root, max_depth=10)
ids = [d.publishedfileid for d in deps]
p("场景1 依赖树:", ids)
check("解析出 B/C/D", set(ids) == {"B", "C", "D"}, str(ids))
check("依赖总数 3", len(ids) == 3, str(len(ids)))
check("A 不在依赖中", "A" not in ids)

# 场景 2：环路安全（B<->D 不会无限递归）
check("环路未导致重复", len(set(ids)) == len(ids))

# 场景 3：深度截断
shallow, _ = api.resolve_dependency_tree(root, max_depth=1)
shallow_ids = [d.publishedfileid for d in shallow]
p("场景3 深度1:", shallow_ids)
check("深度 1 只解析直接依赖", set(shallow_ids) == {"B", "C"}, str(shallow_ids))

# 场景 4：skip_installed 跳过已装依赖
lib2 = ModLibrary()
from swdm.core.mod_library import ModRecord
lib2.upsert(ModRecord(item_id="B", appid="4000", title="mod-B", installed=True))
deps2, skipped2 = api.resolve_dependency_tree(root, max_depth=10,
                                             skip_installed=True, library=lib2)
ids2 = [d.publishedfileid for d in deps2]
p("场景4 跳过已装:", ids2, "skipped:", skipped2)
check("跳过已安装的 B", "B" not in ids2, str(ids2))
check("skipped 记录 B", skipped2 == ["B"], str(skipped2))

# 场景 5：无依赖的物品
leaf = WorkshopItem(publishedfileid="C", appid="4000")
deps5, _ = api.resolve_dependency_tree(leaf)
check("叶子节点无依赖", deps5 == [])

# 场景 6：enqueue_with_dependencies 顺序（依赖在前）
from swdm.core import DownloadManager, SteamCMDEngine
mgr = DownloadManager(SteamCMDEngine(anonymous=True), lib, auto_retry=0)
# 用假入队（不真正启动 steamcmd）
jobs = mgr.enqueue_with_dependencies(
    WorkshopItem(publishedfileid="A", appid="4000"), "4000",
    api=api, auto_deps=True, skip_installed=False,
)
job_ids = [j.id for j in jobs]
p("场景6 入队顺序:", job_ids)
check("入队 4 个作业", len(jobs) == 4, str(len(jobs)))
check("A 最后入队", job_ids[-1] == "A", str(job_ids))
check("B/C/D 在 A 之前", set(job_ids[:3]) == {"B", "C", "D"})

result = "\n".join(out.getvalue().splitlines())
print(result)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_deptree.txt"),
          "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
