"""端到端：干净环境下 SteamCMDEngine 自动部署并使用内置 steamcmd。

模拟用户刚装好程序、系统里没有 steamcmd 的场景：引擎应自动解压内置
steamcmd.zip 并定位到它（需求 2：安装程序自动安装 steamcmd）。
"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_engine_e2e_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

for _m in [m for m in list(sys.modules) if m.startswith("swdm")]:
    del sys.modules[_m]

from swdm.core import SteamCMDEngine, ensure_dirs  # noqa: E402
from swdm.core import steamcmd_deploy as d  # noqa: E402
from swdm.core.paths import DEPLOYED_STEAMCMD_EXE  # noqa: E402

ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# 干净环境
check("初始未部署", not d.is_deployed())

# 模拟系统未安装 steamcmd（本机有真实安装，清空搜索路径以验证内置部署分支）
import swdm.core.steamcmd_engine as sce  # noqa: E402

sce._SEARCH_PATHS = []

# 引擎不指定 exe_path（模拟用户未配置），且系统无 steamcmd
eng = SteamCMDEngine(anonymous=True, exe_path="")
resolved = eng.resolve_exe()
check("resolve_exe 成功定位", os.path.isfile(resolved), resolved[-60:])
check("定位到内置部署的 exe",
      os.path.normcase(resolved) == os.path.normcase(DEPLOYED_STEAMCMD_EXE),
      os.path.basename(resolved))
check("resolve 后引擎记住路径", eng.exe_path == resolved)
check("部署已完成", d.is_deployed())

# 再次构造引擎：直接命中已部署（不重复解压）
eng2 = SteamCMDEngine(anonymous=True, exe_path="")
resolved2 = eng2.resolve_exe()
check("二次构造直接命中", resolved2 == resolved)

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
