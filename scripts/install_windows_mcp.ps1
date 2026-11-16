# BARQ Windows-MCP integration installer. Opted in via BARQ Setup wizard.
# Official upstream: https://github.com/CursorTouch/Windows-MCP (MIT)
# Uses a per-user tool install; DOES NOT grant admin privileges or start a network listener.
param([switch]$Repair)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$targetVersion = '0.8.8'
$stateDir = Join-Path $env:LOCALAPPDATA 'AI Router Agent'
$logDir = Join-Path $stateDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'windows-mcp-install.log'
$launcher = Join-Path $env:USERPROFILE '.local\bin\windows-mcp.exe'
function Note([string]$message) {
  $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message)
  Add-Content -LiteralPath $log -Value $line -Encoding UTF8
  Write-Host $line
}
try {
  Note 'Starting Windows-MCP per-user setup; pinned package 0.8.8'
  if ((Test-Path -LiteralPath $launcher) -and (-not $Repair)) {
    Note 'Detected existing Windows-MCP launcher. Leaving installation untouched.'
    exit 0
  }
  $uv = $null
  $known = @((Join-Path $env:USERPROFILE '.local\bin\uv.exe'), (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe'))
  foreach ($candidate in $known) { if (Test-Path -LiteralPath $candidate) { $uv = $candidate; break } }
  if (-not $uv) {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { $uv = $cmd.Source }
  }
  if (-not $uv) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
      Note 'Installing uv from official WinGet package astral-sh.uv'
      & $winget.Source install --id astral-sh.uv -e --source winget --silent --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object { Note "$($_)" }
      if ($LASTEXITCODE -ne 0) { Note "WinGet returned $LASTEXITCODE; trying official uv installer" }
      foreach ($candidate in $known) { if (Test-Path -LiteralPath $candidate) { $uv = $candidate; break } }
      if (-not $uv) { $cmd = Get-Command uv -ErrorAction SilentlyContinue; if ($cmd) { $uv = $cmd.Source } }
    }
  }
  if (-not $uv) {
    Note 'Retrieving official uv installation script over HTTPS'
    $installer = Join-Path $env:TEMP ('barq-uv-installer-' + [guid]::NewGuid().ToString('N') + '.ps1')
    try {
      Invoke-WebRequest -Uri 'https://astral.sh/uv/0.13.6/install.ps1' -OutFile $installer -UseBasicParsing -TimeoutSec 90
      $env:UV_NO_MODIFY_PATH = '1'
      & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $installer
      if ($LASTEXITCODE -ne 0) { throw 'Official uv installer failed' }
    } finally { Remove-Item $installer -ErrorAction SilentlyContinue }
    $uv = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
  }
  if (-not (Test-Path -LiteralPath $uv)) { throw 'uv was not found after installation' }
  Note ('Installing windows-mcp==' + $targetVersion + ' with an isolated Python 3.14 environment')
  # Python and dependencies are downloaded to per-user uv cache. They are NOT bundled in BARQ.
  & $uv tool install --python 3.14 "windows-mcp==$targetVersion" --force 2>&1 | ForEach-Object { Note "$($_)" }
  if ($LASTEXITCODE -ne 0) { throw "uv tool install returned $LASTEXITCODE" }
  if (-not (Test-Path -LiteralPath $launcher)) { throw 'windows-mcp.exe was not created' }
  Note 'Windows-MCP installation successful. BARQ will launch it on demand using local stdio.'
  exit 0
} catch {
  Note ('INSTALL FAILED: ' + $_.Exception.Message)
  Write-Warning ('Windows-MCP could not be installed. BARQ native Windows tools will continue working. Log: ' + $log)
  exit 1
}
