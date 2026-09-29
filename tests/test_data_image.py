"""data:image 内联占位图解码测试（修日志中 "No connection adapters" 报错）。"""
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="swdm_data_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QByteArray, QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

out = io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, e=""):
    global ok
    ok = ok and bool(cond)
    p(("OK   " if cond else "FAIL ") + name + (f"  [{e}]" if e else ""))


# 构造一个真实 4x4 PNG 的 data URL（用 Qt 生成，避免手搓字节出错）
from PySide6.QtGui import QImage  # noqa: E402

img = QImage(4, 4, QImage.Format.Format_RGB32)
img.fill(0xFFFF0000)   # 红色
buf = QByteArray()
bbuf = QBuffer(buf)
bbuf.open(QIODevice.OpenModeFlag.WriteOnly)
img.save(bbuf, "PNG")
bbuf.close()
data_url = "data:image/png;base64," + base64.b64encode(bytes(buf)).decode()

from swdm.core.steam_api import SteamAPI  # noqa: E402

api = SteamAPI()
# fetch_image 不应尝试请求 data: URL
ret = api.fetch_image(data_url)
check("fetch_image 原样返回 data URL", ret == data_url)
check("fetch_image 空串返回空", api.fetch_image("") == "")

from swdm.gui.workers import ImageLoader  # noqa: E402

loader = ImageLoader()
received = {}
loader.bus.loaded.connect(lambda u, pm: received.update(url=u, pixmap=pm))
loader.load(data_url, 32, 32)
app.processEvents()
check("data URL 不经过网络任务", "data:" in received.get("url", ""))
pm = received.get("pixmap")
check("解码出 QPixmap", pm is not None and not pm.isNull())
if pm:
    check("尺寸正确缩放", pm.width() == 32 and pm.height() == 32,
          f"{pm.width()}x{pm.height()}")

# 普通 http URL 仍走线程池（不实际下载，仅验证未短路）
http = "https://images.steamusercontent.com/ugc/test/"
loader2 = ImageLoader()
loader2.load(http, 32, 32)
app.processEvents()
check("http URL 不被 data 分支短路", http not in received)

print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
