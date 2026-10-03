# Steam Web API rate benchmark (re-calibration of 1.x backoff parameters)
$ids = (Get-Content "$env:TEMP\bench_ids.txt" -Encoding UTF8) -split ',' | Where-Object { $_ }
$proxy = "http://127.0.0.1:7897"
$log = "$env:TEMP\bench_rate.txt"
"idx,phase,status,ms,result,len" | Set-Content $log -Encoding UTF8

function Req($id) {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    $r = Invoke-WebRequest -Uri "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/" -Method POST -Body "itemcount=1&publishedfileids[0]=$id" -TimeoutSec 30 -UseBasicParsing -Proxy $proxy -ErrorAction Stop
    $sw.Stop()
    $code = $r.StatusCode
    $len = $r.Content.Length
    $r9 = if ($r.Content -match '"result":(\d),"resultcount"') { $matches[1] } else { "?" }
  } catch {
    $sw.Stop()
    $code = $_.Exception.Response.StatusCode.value__ -as [int]
    if (-not $code) { $code = 0 }
    $len = 0; $r9 = "EXC"
  }
  return @{ code = $code; ms = [int]$sw.ElapsedMilliseconds; r9 = $r9; len = $len }
}

# Phase A: zero delay, find first failure
$i = 0; $firstFail = -1
foreach ($id in $ids[0..29]) {
  $r = Req $id; $i++
  "$i,A,$($r.code),$($r.ms),$($r.r9),$($r.len)" | Add-Content $log -Encoding UTF8
  if ($r.code -ne 200 -or $r.r9 -ne "1") { $firstFail = $i; Write-Output "A: first fail at $i code=$($r.code) r9=$($r.r9)"; break }
}
if ($firstFail -lt 0) { Write-Output "A: 30/30 requests returned 200+result1, no throttle at zero delay" }

# Phase B: recovery probe 5/10/30s
if ($firstFail -ge 0) {
  foreach ($wait in 5, 10, 30) {
    Start-Sleep -Seconds $wait
    $r = Req $ids[$firstFail % $ids.Count]
    "$wait,B,$($r.code),$($r.ms),$($r.r9),$($r.len)" | Add-Content $log -Encoding UTF8
    Write-Output "B: after ${wait}s code=$($r.code) r9=$($r.r9)"
    if ($r.code -eq 200 -and $r.r9 -eq "1") { Write-Output "B: recovered in ${wait}s"; break }
  }
}

# Phase C: min safe interval scan (1s / 2s / 5s x 15)
foreach ($iv in 1, 2, 5) {
  $ok = 0; $fail = 0
  foreach ($id in $ids[30..44]) {
    $r = Req $id
    "$iv,C,$($r.code),$($r.ms),$($r.r9),$($r.len)" | Add-Content $log -Encoding UTF8
    if ($r.code -eq 200 -and $r.r9 -eq "1") { $ok++ } else { $fail++ }
    Start-Sleep -Seconds $iv
  }
  Write-Output "C: interval=${iv}s ok=$ok fail=$fail"
}
Write-Output "BENCH DONE"
