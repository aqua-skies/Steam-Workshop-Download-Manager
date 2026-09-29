# SWDM 一键构建脚本（PowerShell）
# 用法：在项目根目录执行  pwsh -File build.ps1
# 产物：build\dist\SWDM\（绿色版目录）与 installer\Output\SWDM-Setup-<ver>.exe（安装包）
#
# 可选参数：
#   -SkipInstaller   只构建绿色版，不调用 ISCC
#   -Clean           构建前清空 build\dist 与 build\work

[CmdletBinding()]
param(
  [switch]$SkipInstaller,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Find-Iscc {
  $candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
  ) | Where-Object { $_ -and (Test-Path $_) }
  if ($candidates) { return $candidates[0] }
  return $null
}

Write-Host "== SWDM 构建 ==" -ForegroundColor Cyan

# 0. 图标 -----------------------------------------------------------------
$icon = Join-Path $root "swdm\resources\icon.ico"
if (-not (Test-Path $icon)) {
  Write-Host "[1/4] 生成应用图标..." -ForegroundColor Yellow
  python (Join-Path $root "installer\make_icon.py")
  if ($LASTEXITCODE -ne 0) { throw "图标生成失败" }
} else {
  Write-Host "[1/4] 图标已存在，跳过生成" -ForegroundColor Yellow
}

# 1. 清理（可选）----------------------------------------------------------
if ($Clean) {
  Write-Host "[2/4] 清理旧构建..." -ForegroundColor Yellow
  Remove-Item -Recurse -Force (Join-Path $root "build\dist") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $root "build\work") -ErrorAction SilentlyContinue
} else {
  Write-Host "[2/4] 跳过清理（-Clean 可启用）" -ForegroundColor Yellow
}

# 2. PyInstaller ----------------------------------------------------------
Write-Host "[3/4] PyInstaller 构建（onedir / windowed）..." -ForegroundColor Yellow
& python -m PyInstaller (Join-Path $root "swdm.spec") `
  --noconfirm `
  --workpath (Join-Path $root "build") `
  --distpath (Join-Path $root "build\dist") `
  --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败（详见 build\pyinstaller.log）" }

$distExe = Join-Path $root "build\dist\SWDM\SWDM.exe"
if (-not (Test-Path $distExe)) { throw "未找到预期产物：$distExe" }
$sizeMB = [math]::Round((Get-ChildItem (Join-Path $root "build\dist\SWDM") -Recurse -File |
  Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "  绿色版目录：build\dist\SWDM\（约 $sizeMB MB）" -ForegroundColor Green

# 3. Inno Setup -----------------------------------------------------------
if ($SkipInstaller) {
  Write-Host "[4/4] 已跳过安装包编译（-SkipInstaller）" -ForegroundColor Yellow
  return
}

$iscc = Find-Iscc
if (-not $iscc) {
  Write-Warning "未找到 ISCC.exe，已跳过安装包编译。请安装 Inno Setup 6：winget install JRSoftware.InnoSetup"
  Write-Warning "安装后可单独编译：& 'ISCC.exe' 'installer\swdm.iss'"
  return
}

Write-Host "[4/4] Inno Setup 编译安装包..." -ForegroundColor Yellow
& $iscc (Join-Path $root "installer\swdm.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败（exit $LASTEXITCODE）" }

$setup = Get-ChildItem (Join-Path $root "installer\Output") -Filter "SWDM-Setup-*.exe" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "  安装包：installer\Output\$(($setup).Name)（$([math]::Round($setup.Length/1MB,1)) MB）" -ForegroundColor Green
Write-Host ""
Write-Host "== 构建完成 ==" -ForegroundColor Cyan
Write-Host "  绿色版：build\dist\SWDM\SWDM.exe（可直接运行排错；放入 portable.marker 即便携模式）"
Write-Host "  安装包：installer\Output\$(($setup).Name)"
