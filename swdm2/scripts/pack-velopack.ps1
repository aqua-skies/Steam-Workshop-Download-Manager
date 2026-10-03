# SWDM 2.0 pack script (D6.1 Velopack, t58) - ASCII-only (PS5.1 CJK encoding safety)
# Usage:
#   .\scripts\pack-velopack.ps1 -Version 0.6.0            # publish+pack current source
#   .\scripts\pack-velopack.ps1 -Version 0.5.0 -Baseline  # baseline for upgrade path
# Toolchain notes: docs/packaging_2.0.md
#   vpk via local extract (dotnet tool install blocked by SDK 8.0.425 path enum bug)

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$Baseline,
    [string]$PackId = 'Swdm2',
    [string]$MainExe = 'Swdm2.App.exe',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$Proxy = 'http://127.0.0.1:7897'
$VpkDll = "$RepoRoot\swdm2\.dtmp\vpk\ext2\tools\net8.0\any\vpk.dll"
$Project = "$RepoRoot\swdm2\src\Swdm2.App\Swdm2.App.csproj"
$Suffix = if ($Baseline) { '050' } else { '060' }
$PublishDir = "$RepoRoot\swdm2\.dtmp\publish-$Suffix"
$Artifacts = "$RepoRoot\artifacts"

$env:HTTPS_PROXY = $Proxy
$env:HTTP_PROXY = $Proxy
$env:TMP = "$RepoRoot\swdm2\.dtmp"
$env:TEMP = "$RepoRoot\swdm2\.dtmp"

Write-Host "== D6.1 Velopack pack: $PackId $Version (baseline=$Baseline) =="

# 1) publish: SelfContained decision (docs/packaging_2.0.md, product-priority principle)
#    no trim: WPF reflection risk > size benefit
if (-not (Test-Path $PublishDir)) {
    Write-Host "-- dotnet publish (self-contained win-x64) --"
    & dotnet publish $Project -c Release -r win-x64 --self-contained true `
        -p:PublishTrimmed=false -p:Version=$Version -o $PublishDir --nologo -v q
    if ($LASTEXITCODE -ne 0) { throw "publish failed exit=$LASTEXITCODE" }
} else {
    Write-Host "-- reuse publish dir $PublishDir --"
}

$exe = Join-Path $PublishDir $MainExe
if (-not (Test-Path $exe)) { throw "main exe missing: $exe" }
$ver = (Get-Item $exe).VersionInfo.FileVersion
Write-Host "-- main exe FileVersion=$ver (expect $Version.0)"

# 2) vpk pack: self-contained carries runtime, no external --framework injection
if (-not (Test-Path $VpkDll)) { throw "vpk.dll missing: $VpkDll (see docs/packaging_2.0.md)" }
$channel = if ($Baseline) { 'win-baseline' } else { 'win' }
Write-Host "-- vpk pack (channel=$channel) --"
& dotnet $VpkDll pack `
    --packId $PackId `
    --packVersion $Version `
    --packDir $PublishDir `
    --mainExe $MainExe `
    --packAuthors 'aqua-skies' `
    --packTitle 'SWDM 2.0 - Steam Workshop Download Manager' `
    --channel $channel `
    --delta none `
    --outputDir $Artifacts
if ($LASTEXITCODE -ne 0) { throw "vpk pack failed exit=$LASTEXITCODE" }

# 3) artifact listing
Write-Host "-- artifacts --"
Get-ChildItem $Artifacts -Recurse -File |
    ForEach-Object { "$([math]::Round($_.Length / 1MB, 1))MB " + $_.FullName.Substring($RepoRoot.Length) }
Write-Host "== done =="
