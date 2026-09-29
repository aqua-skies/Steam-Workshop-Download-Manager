$ErrorActionPreference = "Continue"
Set-Location "C:\Users\Lenovo\Desktop\程序设计\steam mod program"
$env:PYTHONUTF8 = "1"
$env:QT_QPA_PLATFORM = "offscreen"
$skip = @("test_acceptance","test_smoke","test_tags","test_deps_live","test_deps_e2e","test_real_download","test_online_parse","test_find_api","test_prefetch","test_steamcmd_deploy","test_engine_autodeploy","test_cultist","test_cultist_deps","test_game_dir_e2e","test_tag_parse_real","test_stress")
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
