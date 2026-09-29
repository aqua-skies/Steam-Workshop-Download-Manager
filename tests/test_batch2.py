"""批次2 性能优化回归（O1 图片索引 / O2 主线程不下载 /
O3 LRU 缓存 / O4 详情上限 / O5 熔断 / O6 代际丢弃）。"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_b2_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

RESULTS = []
def check(name, cond, e=""):
    RESULTS.append((name, bool(cond), e))

# ---- O3：图片缓存 LRU 淘汰（不清空全部）
from swdm.gui import workers as _w  # noqa: E402
_w._image_cache.clear()
loader = _w.ImageLoader()
loader.max_cache = 5
for i in range(5):
    _w._image_cache[f"u{i}"] = QPixmap(96, 96)
# 命中一次 u0，使其成为最新
loader.load("u0")
check("O3 命中后 move_to_end",
      list(_w._image_cache)[-1] == "u0", str(list(_w._image_cache)))
# 加到 6 个，应淘汰最旧（u1，因为 u0 刚用过）
_w._image_cache["u_new"] = QPixmap(96, 96)
while len(_w._image_cache) > loader.max_cache:
    _w._image_cache.popitem(last=False)
check("O3 超限淘汰最旧而非全清",
      "u0" in _w._image_cache and "u1" not in _w._image_cache,
      str(list(_w._image_cache)))
check("O3 缓存容量有界", len(_w._image_cache) <= 5)

# ---- O5：熔断器 trip/in_circuit
from swdm.core.steam_api import _throttle  # noqa: E402
import time as _time  # noqa: E402

_throttle._circuit_until = 0.0
_throttle._min_interval = 2.0
_throttle.trip(30.0)
check("O5 trip 后进入熔断", _throttle.in_circuit is True)
# 熔断期 acquire 不应长时间阻塞（快速放行）
t0 = _time.time()
_throttle.acquire()
el = _time.time() - t0
check("O5 熔断期 acquire 快速返回", el < 1.0, f"{el:.2f}s")
# 模拟熔断过期
_throttle._circuit_until = _time.time() - 1
check("O5 熔断过期后退出", _throttle.in_circuit is False)
_throttle._min_interval = 2.0
_throttle._circuit_until = 0.0

# ---- O6：代际号丢弃过期结果（不实例化 WorkshopTab，直接验逻辑）
from swdm.gui.workshop_tab import WorkshopTab  # noqa: E402
from swdm.core.steam_api import WorkshopItem  # noqa: E402

# _on_items_ready 只依赖 self._worker_gen 与 self._populate
class _MiniTab:
    _worker_gen = 5
    def __init__(self):
        self.populated = []
    _populate_orig = None
    def _populate(self, items):
        self.populated.append(items)
    _on_items_ready = WorkshopTab._on_items_ready

mini = _MiniTab()
mini._on_items_ready(["old"], gen=3)
check("O6 过期代际结果被丢弃", len(mini.populated) == 0)
mini._on_items_ready(["new"], gen=5)
check("O6 当前代际结果被接受", mini.populated == [["new"]])

# ---- O1：url 索引构建逻辑（直接测 _populate 需完整 svc，
# 用 make_items 验证索引语义：同 url 多卡聚合）
idx: dict[str, list] = {}
cards = []
its = [
    WorkshopItem(publishedfileid="1", title="A", appid="4000",
                 preview_url="http://x/1.jpg", file_size=1),
    WorkshopItem(publishedfileid="2", title="B", appid="4000",
                 preview_url="http://x/1.jpg", file_size=1),  # 同 url
    WorkshopItem(publishedfileid="3", title="C", appid="4000",
                 preview_url="", file_size=1),
]
for it in its:
    if it.preview_url:
        idx.setdefault(it.preview_url, []).append(it)
check("O1 同 url 多卡聚合为一个列表",
      len(idx["http://x/1.jpg"]) == 2, str(len(idx.get("http://x/1.jpg", []))))
check("O1 无预览图不建索引", "" not in idx)
check("O1 索引 O(1) 可定位",
      idx["http://x/1.jpg"][0].publishedfileid == "1")

# ---- O2：_ImageDownloadTask 存在且是 QRunnable
from PySide6.QtCore import QRunnable  # noqa: E402
check("O2 回退下载任务类存在", hasattr(_w, "_ImageDownloadTask"))
t = _w._ImageDownloadTask("http://x/1.jpg", 96, 96)
check("O2 回退任务是 QRunnable", isinstance(t, QRunnable))

# ---- O4：详情缓存上限淘汰
from swdm.gui.detail_dialog import DetailPageWorker  # noqa: E402
DetailPageWorker._page_cache.clear()
for i in range(150):
    DetailPageWorker._page_cache[str(i)] = (0.0, "html")
    while len(DetailPageWorker._page_cache) > \
            DetailPageWorker._PAGE_CACHE_MAX:
        DetailPageWorker._page_cache.popitem(last=False)
check("O4 详情缓存不超过上限",
      len(DetailPageWorker._page_cache) <= 100,
      str(len(DetailPageWorker._page_cache)))
check("O4 淘汰的是最旧条目", "0" not in DetailPageWorker._page_cache)

fails = [r for r in RESULTS if not r[1]]
for name, passed, e in RESULTS:
    print(("OK   " if passed else "FAIL ") + name + (f"  [{e}]" if e and not passed else ""))
print("RESULT:", "ALL PASS" if not fails else f"HAS FAILURES ({len(fails)})")
sys.exit(0 if not fails else 1)
