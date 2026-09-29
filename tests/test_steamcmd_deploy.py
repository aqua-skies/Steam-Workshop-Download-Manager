"""内置 steamcmd 自动部署测试（解压真实内置 zip，不联网）。"""
from __future__ import annotations

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="swdm_deploy_")
os.environ["APPDATA"] = _TMP
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io as _io  # noqa: E402

for _m in [m for m in list(sys.modules) if m.startswith("swdm")]:
    del sys.modules[_m]

from swdm.core import ensure_dirs  # noqa: E402
from swdm.core import steamcmd_deploy as d  # noqa: E402

ensure_dirs()

out = _io.StringIO()
def p(*a):
    print(*a, file=out)

ok = True
def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    p(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")

# 前提：内置 zip 存在（随源码/安装包分发）
check("内置 steamcmd.zip 存在", d.has_bundled_zip(), d.bundled_steamcmd_zip()[-40:])

# 干净环境：未部署
check("初始未部署", not d.is_deployed())

# 自动部署
exe = d.ensure_steamcmd()
check("ensure_steamcmd 返回路径", os.path.isfile(exe), exe[-50:])
check("部署后 is_deployed", d.is_deployed())
size = os.path.getsize(exe)
check("steamcmd.exe 大小合理（>1MB）", size > 1_000_000, f"{size} 字节")

# 重复调用不重复解压（幂等）
exe2 = d.ensure_steamcmd()
check("重复调用幂等", exe == exe2)

# 状态报告
st = d.deployment_status()
check("状态含 deployed=True", st["deployed"] is True)
check("状态含 exe 路径", os.path.isfile(st["exe"]))

result = "\n".join(out.getvalue().splitlines())
print(result)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")

import shutil  # noqa: E402

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
