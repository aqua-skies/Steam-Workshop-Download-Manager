$ErrorActionPreference = "Continue"
Set-Location -Path (Split-Path -Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$env:QT_QPA_PLATFORM = "offscreen"
# skip: live-network / stress / smoke scripts are NOT part of the offline
# regression baseline (test_bundle_ctx/methods are no-assert JS bundle probes,
# real-network and emit no RESULT line). Network scripts hang/timeout when the
# local fake-IP proxy is down (2026-09-30); re-run them individually to
# confirm they are environmental, not code regressions.
# NOTE: keep this file ASCII-only. A UTF-8-no-BOM file with Chinese comments
# is mis-decoded by powershell.exe 5.1 (ANSI codepage), which silently merges
# the last comment line into the $skip assignment and disables the skip list
# (90 scripts incl. hanging network scripts). pwsh 7 and a UTF-8 BOM both
# parse it correctly; ASCII-only is immune in every shell.
$skip = @("test_acceptance","test_smoke","test_tags","test_deps_live","test_deps_e2e","test_real_download","test_online_parse","test_find_api","test_prefetch","test_steamcmd_deploy","test_engine_autodeploy","test_cultist","test_cultist_deps","test_game_dir_e2e","test_tag_parse_real","test_stress","test_bundle_ctx","test_bundle_methods","test_bulk_games","test_multi_game","test_page_content")
$tests = Get-ChildItem tests -Filter "test_*.py" | Where-Object { $skip -notcontains $_.BaseName } | Sort-Object Name
$pass = 0
$fail = 0
$noresult = 0
$err = @()
foreach ($f in $tests) {
    $out = & python $f.FullName 2>&1 | Out-String
    $line = ($out -split "`n" | Where-Object { $_ -match "RESULT:" } | Select-Object -First 1).Trim()
    if (-not $line) {
        $noresult++
        Write-Host ("NORESULT  {0}" -f $f.BaseName)
        continue
    }
    if ($line -match "ALL PASS" -or $line -match "^RESULT: PASS") {
        $pass++
        Write-Host ("PASS      {0}" -f $f.BaseName)
    } else {
        $fail++
        $err += $f.BaseName
        Write-Host ("FAIL      {0}  {1}" -f $f.BaseName, $line)
    }
}
Write-Host ""
Write-Host ("SUMMARY: pass={0} fail={1} noresult={2} total={3}" -f $pass, $fail, $noresult, $tests.Count)
if ($err.Count) { Write-Host ("FAILED: {0}" -f ($err -join ", ")) }
