"""实测详情页请求耗时（定位 bug3 慢的瓶颈）。"""
import os
import sys
import time
import truststore

truststore.inject_into_ssl()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swdm.core.steam_api import SteamAPI  # noqa: E402

api = SteamAPI()

# 详情页（110KB HTML）
t0 = time.time()
html = api._community_get("/sharedfiles/filedetails/", {"id": "3803871160"})
t1 = time.time()
print(f"详情页请求: {t1 - t0:.2f}s  长度: {len(html or '')}")

# 第二次（节流等待）
t0 = time.time()
api._community_get("/sharedfiles/filedetails/", {"id": "3803871160"})
t1 = time.time()
print(f"详情页第2次(命中5分钟缓存): {t1 - t0:.2f}s")

# 不同 item（节流间隔）
t0 = time.time()
api._community_get("/sharedfiles/filedetails/", {"id": "3805232163"})
t1 = time.time()
print(f"另一物品(触发节流): {t1 - t0:.2f}s")

# browse 页对照
t0 = time.time()
api.browse("4000", page=1)
t1 = time.time()
print(f"browse 页: {t1 - t0:.2f}s")

print("RESULT: DONE")
