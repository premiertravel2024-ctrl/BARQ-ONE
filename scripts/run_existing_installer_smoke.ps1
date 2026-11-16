# Retry the REAL isolated Setup smoke gate without recompiling BARQ.
# Finds the latest existing Setup.exe from the BARQ short-path build stages.
param([string]$Setup = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$version = '2.31.0'
$release = Join-Path $root 'release'
New-Item -ItemType Directory -Path $release -Force | Out-Null
if ([string]::IsNullOrWhiteSpace($Setup)) {
  $candidates = @()
  $sourceInstaller = Join-Path $release "BARQ_Setup_$version.exe"
  if (Test-Path -LiteralPath $sourceInstaller -PathType Leaf) {
    $candidates += Get-Item -LiteralPath $sourceInstaller
  }
  $local = [Environment]::GetFolderPath('LocalApplicationData')
  $stageRoot = Join-Path $local 'Bq\b'
  if (Test-Path -LiteralPath $stageRoot -PathType Container) {
    foreach ($stage in (Get-ChildItem -LiteralPath $stageRoot -Directory -ErrorAction SilentlyContinue)) {
      $candidate = Join-Path $stage.FullName "release\BARQ_Setup_$version.exe"
      if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $candidates += Get-Item -LiteralPath $candidate
      }
    }
  }
  if ($candidates.Count -eq 0) {
    throw "No compiled BARQ_Setup_$version.exe found. First run BUILD_BARQ.bat."
  }
  $Setup = ($candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
$Setup = (Resolve-Path -LiteralPath $Setup -ErrorAction Stop).Path
Write-Host "[BARQ] Rechecking already compiled setup: $Setup" -ForegroundColor Cyan
Write-Host "[BARQ] Reports are written to: $release" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'smoke_install.ps1') -Setup $Setup -Version $version -ReportDir $release
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
  throw "Installer smoke checker exited $LASTEXITCODE"
}
