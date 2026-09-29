"""游戏专属下载目录管理测试（纯逻辑，不联网、不下载）。"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_gamedirs_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

from swdm.core import ensure_dirs  # noqa: E402
from swdm.core.config import get_config  # noqa: E402
from swdm.core.game_dirs import (  # noqa: E402
    clear_game_dir,
    configured_game_dirs,
    game_content_root,
    game_dir_entries,
    game_install_dir,
    set_game_dir,
)
from swdm.core.paths import LIBRARY_DIR  # noqa: E402

ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# 初始：无配置，回退全局
check("初始无专属配置", configured_game_dirs() == {})
check("未配置游戏回退全局目录", game_install_dir("4000") == str(LIBRARY_DIR),
      game_install_dir("4000"))

# 设置专属目录
custom = os.path.join(_TMP, "MyGModMods")
d = set_game_dir("4000", custom)
check("set_game_dir 返回生效目录", d == custom, d)
check("配置后读取一致", game_install_dir("4000") == custom, game_install_dir("4000"))
check("configured_game_dirs 含 4000", "4000" in configured_game_dirs())

# 内容根目录拼接
root = game_content_root("4000")
check("内容根目录拼接正确",
      root == os.path.join(custom, "steamapps", "workshop", "content", "4000"), root)

# 其它游戏仍回退全局
check("未配置游戏仍回退全局", game_install_dir("999999") == str(LIBRARY_DIR))

# 清除配置
clear_game_dir("4000")
check("清除后回退全局", game_install_dir("4000") == str(LIBRARY_DIR))
check("清除后 configured 为空", configured_game_dirs() == {})

# 多游戏配置 + 表格条目
set_game_dir("4000", os.path.join(_TMP, "A"))
set_game_dir("252490", os.path.join(_TMP, "B"))
entries = game_dir_entries()
p("  条目:", [(e["appid"], e["name"], os.path.basename(e["dir"])) for e in entries])
check("表格含 2 个条目", len(entries) == 2, str(len(entries)))
check("条目含游戏名", all(e["name"] for e in entries))
check("条目按名排序", [e["name"] for e in entries] == sorted(e["name"] for e in entries))

# 持久化：重新加载配置仍保留
get_config().save()
dirs = configured_game_dirs()
check("持久化后仍有 2 条", len(dirs) == 2, str(dirs))

# 空串/空白路径处理
set_game_dir("4000", "   ")
check("空白路径视为清除", game_install_dir("4000") == str(LIBRARY_DIR))

result = "\n".join(out.getvalue().splitlines())
print(result)
rf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gamedirs.txt")
with open(rf, "w", encoding="utf-8") as f:
    f.write(result + "\n")
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
