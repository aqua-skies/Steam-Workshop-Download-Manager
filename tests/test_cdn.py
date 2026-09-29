"""CDN 直链通道测试：URL 解析、HTTP 下载、断点续传、匿名回退。

用本地 HTTP 服务器（不依赖外部网络）覆盖核心逻辑。
"""
from __future__ import annotations

import http.server
import os
import socket
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix="swdm_cdn_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from swdm.core import WorkshopItem  # noqa: E402
from swdm.core.cdn_downloader import (  # noqa: E402
    download_file,
    download_item_cdn,
    resolve_file_url,
)

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# ---- 本地 HTTP 服务器（支持 Range）----
PAYLOAD = os.urandom(2 * 1024 * 1024)  # 2MB 随机内容

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            data = PAYLOAD[start:]
            self.send_response(206)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
        else:
            data = PAYLOAD
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()

class _Server(http.server.HTTPServer):
    allow_reuse_address = True

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
    _s.bind(("127.0.0.1", 0))
    PORT = _s.getsockname()[1]

srv = _Server(("127.0.0.1", PORT), _Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"

import requests  # noqa: E402

sess = requests.Session()
sess.headers["User-Agent"] = "SWDM-test/1.0"

# 1) 完整下载
dest = os.path.join(_TMP, "full.bin")
r = download_file(BASE + "/full.bin", dest, session=sess)
check("完整下载成功", r["ok"], r["message"])
check("字节数正确", r["bytes"] == len(PAYLOAD), str(r["bytes"]))
check("内容一致", open(dest, "rb").read() == PAYLOAD)

# 2) 断点续传：先写一半，再下载
half = os.path.join(_TMP, "resume.bin")
with open(half, "wb") as f:
    f.write(PAYLOAD[:len(PAYLOAD)//2])
progress = []
r = download_file(BASE + "/resume.bin", half, session=sess,
                  on_progress=lambda pct, done, msg: progress.append((pct, done)))
check("断点续传成功", r["ok"], r["message"])
check("续传后字节数正确", r["bytes"] == len(PAYLOAD), str(r["bytes"]))
check("续传后内容一致", open(half, "rb").read() == PAYLOAD)
check("续传有进度回调", len(progress) > 0,
      f"{len(progress)} 次，首次 pct={progress[0][0]:.0f}")

# 3) 匿名场景：file_url 为空 → 明确失败 + 回退提示
item = WorkshopItem(
    publishedfileid="999", appid="4000", title="t", file_size=1024,
)
res = download_item_cdn(item, os.path.join(_TMP, "cdn_dir"), api=None)
check("匿名 CDN 返回 FAILED", res.status.value == "failed",
      str(res.status))
check("失败消息含回退提示", res.message and "回退" in res.message, res.message[:40])

# 4) 有 file_url 时 CDN 下载成功
item2 = WorkshopItem(
    publishedfileid="998", appid="4000", title="t2", file_size=len(PAYLOAD),
    file_url=BASE + "/item.bin",
)
res2 = download_item_cdn(item2, os.path.join(_TMP, "cdn_dir2"))
check("有 file_url 时 CDN 下载成功", res2.status.value == "success",
      str(res2.status))
check("CDN 下载内容一致",
      os.path.isfile(res2.path) and open(res2.path, "rb").read() == PAYLOAD,
      res2.path or "")

# 5) resolve_file_url：优先用物品自带 url
check("resolve 优先用自带 file_url",
      resolve_file_url(item2) == BASE + "/item.bin")

srv.shutdown()
result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
