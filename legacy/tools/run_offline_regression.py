"""Offline regression runner used by the 1.4.1 packaging gate (t43).

Mirrors ``tests/run_all.ps1`` while avoiding host shell/env flakiness:
- runs every non-live ``tests/test_*.py`` in a fresh subprocess
- judges by the stdout ``RESULT:`` line (project convention), not exit code
- writes a machine readable summary and a copy of the human readable log
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
OUT_TXT = TESTS / "_offline_regression.txt"
OUT_JSON = TESTS / "_offline_regression.json"
TIMEOUT_SECONDS = 900

SKIP = {
    "test_acceptance",
    "test_smoke",
    "test_tags",
    "test_deps_live",
    "test_deps_e2e",
    "test_real_download",
    "test_online_parse",
    "test_find_api",
    "test_prefetch",
    "test_steamcmd_deploy",
    "test_engine_autodeploy",
    "test_cultist",
    "test_cultist_deps",
    "test_game_dir_e2e",
    "test_tag_parse_real",
    "test_stress",
    "test_bundle_ctx",
    "test_bundle_methods",
    # 2026-09-30: this host's fake-IP proxy makes these live tests hang/timeout;
    # they are excluded from the offline baseline and documented as environment failures.
    "test_bulk_games",
    "test_multi_game",
    "test_page_content",
}


def main() -> int:
    started = datetime.now(timezone.utc)
    files = sorted(p for p in TESTS.glob("test_*.py") if p.stem not in SKIP)
    results = []
    failures = []
    noresults = []
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    for path in files:
        proc = None
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                env=env,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            returncode = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            returncode = None
        match = re.search(r"^RESULT:.*$", stdout, re.MULTILINE)
        line = match.group(0).strip() if match else ""
        passed = bool(re.search(r"RESULT: ALL PASS\b", line) or re.fullmatch(r"RESULT: PASS\b", line))
        item = {
            "file": path.name,
            "result_line": line,
            "returncode": returncode,
            "passed": passed,
            "noresult": not line,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
        }
        results.append(item)
        if not line:
            noresults.append(path.name)
            status = "NORESULT"
        elif passed:
            status = "PASS"
        else:
            status = "FAIL"
            failures.append(path.name)
        print(f"{status:<8} {path.name} {line}", flush=True)

    summary = {
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(files),
        "pass": sum(1 for r in results if r["passed"]),
        "fail": len(failures),
        "noresult": len(noresults),
        "failed": failures,
        "noresult_files": noresults,
        "skipped": sorted(SKIP),
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"{r['file']} -> {'PASS' if r['passed'] else ('NORESULT' if r['noresult'] else 'FAIL')} | {r['result_line']}" for r in results]
    header = [
        "SWDM offline regression",
        f"Started: {summary['started_utc']}",
        f"Finished: {summary['finished_utc']}",
        f"SUMMARY: pass={summary['pass']} fail={summary['fail']} noresult={summary['noresult']} total={summary['total']}",
        "SKIP: " + ", ".join(summary["skipped"]),
    ]
    OUT_TXT.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    print()
    print(f"SUMMARY: pass={summary['pass']} fail={summary['fail']} noresult={summary['noresult']} total={summary['total']}")
    if failures:
        print("FAILED: " + ", ".join(failures))
    if noresults:
        print("NORESULT: " + ", ".join(noresults))
    print(f"JSON: {OUT_JSON}")
    return 0 if summary["fail"] == 0 and summary["noresult"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
