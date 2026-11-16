# BARQ Toolkit - one-command, per-user-first Windows setup.
# Sources: winget official catalog, uv official runtime and pinned official LibreHardwareMonitor release.
# Never bypasses UAC, tampers with security settings, opens a network MCP listener or auto-approves risky actions.
#requires -Version 5.1
[CmdletBinding()]
param([switch]$PlanOnly, [switch]$SkipOptional)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Run on Windows 10/11.' }
$toolkit = Join-Path $env:LOCALAPPDATA 'BARQ\toolkit'
$logdir = Join-Path $toolkit 'logs'
$null = New-Item -ItemType Directory -Path $logdir -Force
$log = Join-Path $logdir 'install.log'
$reportPath = Join-Path $toolkit 'installed-tools.json'
$records = New-Object 'System.Collections.Generic.List[object]'
function Write-Log([string]$msg) {
  $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$msg)
  Write-Host $line; Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}
function Refresh-Path {
  $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
  $user = [Environment]::GetEnvironmentVariable('Path','User')
  $parts = @($machine,$user,(Join-Path $env:USERPROFILE '.local\bin'),$env:Path) | Where-Object { $_ }
  $env:Path = ($parts -join ';')
}
function Find-Command([string]$Name, [string[]]$Candidates=@()) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1
  if ($command) { return $command.Source }
  foreach ($path in $Candidates) { if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) { return $path } }
  return $null
}
function Add-Result([string]$Name,[string]$Status,[string]$Path='', [string]$Reason='') {
  $records.Add([pscustomobject]@{tool=$Name;status=$Status;path=$Path;reason=$Reason})
  Write-Log ("{0}: {1} {2}" -f $Name,$Status,$Reason)
}
Refresh-Path
$winget = Find-Command 'winget.exe'
$programFiles = ${env:ProgramFiles}
$local = $env:LOCALAPPDATA
# winget IDs are exact, not free-form strings or model input. Do not auto-upgrade existing applications.
$packages = @(
  @{Name='Git';Id='Git.Git';Command='git.exe';Paths=@("$programFiles\Git\cmd\git.exe")},
  @{Name='GitHub CLI';Id='GitHub.cli';Command='gh.exe';Paths=@("$programFiles\GitHub CLI\gh.exe")},
  @{Name='Node.js LTS';Id='OpenJS.NodeJS.LTS';Command='node.exe';Paths=@("$programFiles\nodejs\node.exe")},
  @{Name='VS Code';Id='Microsoft.VisualStudioCode';Command='code.cmd';Paths=@("$local\Programs\Microsoft VS Code\bin\code.cmd","$programFiles\Microsoft VS Code\bin\code.cmd")},
  @{Name='Python 3.11';Id='Python.Python.3.11';Command='py.exe';Paths=@("$env:WINDIR\py.exe","$local\Programs\Python\Launcher\py.exe")},
  @{Name='PowerShell 7';Id='Microsoft.PowerShell';Command='pwsh.exe';Paths=@("$programFiles\PowerShell\7\pwsh.exe")},
  @{Name='7-Zip';Id='7zip.7zip';Command='7z.exe';Paths=@("$programFiles\7-Zip\7z.exe")},
  @{Name='FFmpeg';Id='Gyan.FFmpeg';Command='ffmpeg.exe';Paths=@()},
  @{Name='ripgrep';Id='BurntSushi.ripgrep.MSVC';Command='rg.exe';Paths=@()},
  @{Name='fd';Id='sharkdp.fd';Command='fd.exe';Paths=@()}
)
if ($SkipOptional) { $packages = @($packages | Where-Object { $_.Name -in @('Git','GitHub CLI','Node.js LTS','VS Code','Python 3.11','PowerShell 7') }) }
Write-Log 'BARQ Toolkit setup beginning (not elevated by this script).'
foreach ($pkg in $packages) {
  $found = Find-Command $pkg.Command $pkg.Paths
  if ($found) { Add-Result $pkg.Name 'available' $found; continue }
  if ($PlanOnly) { Add-Result $pkg.Name 'planned' '' ('winget: '+$pkg.Id); continue }
  if (-not $winget) { Add-Result $pkg.Name 'missing' '' 'winget unavailable; install App Installer from Microsoft Store';continue }
  try {
    Write-Log ('Installing WinGet package '+$pkg.Id)
    & $winget install --id $pkg.Id --exact --source winget --no-upgrade --silent --disable-interactivity --accept-source-agreements --accept-package-agreements 2>&1 | ForEach-Object { Write-Log ([string]$_) }
    $rc=$LASTEXITCODE
    Refresh-Path
    $found = Find-Command $pkg.Command $pkg.Paths
    if ($found) { Add-Result $pkg.Name 'available' $found }
    elseif ($rc -eq 0) { Add-Result $pkg.Name 'installed-restart-required' '' 'Restart BARQ/Windows to refresh executable aliases or PATH' }
    else { Add-Result $pkg.Name 'failed' '' ('winget exit code '+$rc+'; check install.log') }
  } catch { Add-Result $pkg.Name 'failed' '' $_.Exception.Message }
}
# Python 3.11 stays dedicated to BARQ. Windows-MCP is installed in uv's separate Python 3.14 env.
$uvPaths=@((Join-Path $env:USERPROFILE '.local\bin\uv.exe'))
$uv=Find-Command 'uv.exe' $uvPaths
if (-not $uv -and -not $PlanOnly) {
  if ($winget) {
    try {
      & $winget install --id astral-sh.uv --exact --source winget --silent --disable-interactivity --accept-source-agreements --accept-package-agreements 2>&1 | ForEach-Object { Write-Log ([string]$_) }
    } catch { Write-Log ('uv winget install error: '+$_.Exception.Message) }
  }
  Refresh-Path
  $uv=Find-Command 'uv.exe' $uvPaths
}
if ($uv) { Add-Result 'uv' 'available' $uv }
elseif ($PlanOnly) { Add-Result 'uv' 'planned' '' 'winget astral-sh.uv' }
else { Add-Result 'uv' 'missing' '' 'Install uv from https://docs.astral.sh/uv/ and rerun' }
$mcp=Join-Path $env:USERPROFILE '.local\bin\windows-mcp.exe'
if (Test-Path -LiteralPath $mcp -PathType Leaf) { Add-Result 'Windows-MCP' 'available' $mcp }
elseif ($PlanOnly) { Add-Result 'Windows-MCP' 'planned' '' 'uv tool install --python 3.14 windows-mcp==0.8.8' }
elseif ($uv) {
  try {
    & $uv tool install --python 3.14 'windows-mcp==0.8.8' 2>&1 | ForEach-Object { Write-Log ([string]$_) }
    if ((Test-Path -LiteralPath $mcp -PathType Leaf)) { Add-Result 'Windows-MCP' 'available' $mcp }
    else { Add-Result 'Windows-MCP' 'failed' '' 'uv returned without creating executable' }
  } catch { Add-Result 'Windows-MCP' 'failed' '' $_.Exception.Message }
} else { Add-Result 'Windows-MCP' 'missing' '' 'uv is required' }
# Official v0.9.6 fixed checksum, verified BEFORE extraction. No third-party download mirror.
$lhmFolder=Join-Path $toolkit 'hardware-monitor'
$lhmExe=Join-Path $lhmFolder 'LibreHardwareMonitor.exe'
$lhmDll=Join-Path $lhmFolder 'LibreHardwareMonitorLib.dll'
$lhmUrl='https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'
$lhmHash='086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
if ((Test-Path -LiteralPath $lhmExe -PathType Leaf) -and (Test-Path -LiteralPath $lhmDll -PathType Leaf)) { Add-Result 'LibreHardwareMonitor' 'available' $lhmExe }
elseif ($PlanOnly) { Add-Result 'LibreHardwareMonitor' 'planned' '' 'Official pinned v0.9.6 / SHA256 verified' }
else {
  $stage=Join-Path $env:TEMP ('barq-lhm-'+[guid]::NewGuid().ToString('N'))
  try {
    $null=New-Item -ItemType Directory -Path $stage -Force
    $zip=Join-Path $stage 'lhm.zip'
    Invoke-WebRequest -Uri $lhmUrl -OutFile $zip -UseBasicParsing -TimeoutSec 180
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lhmHash) { throw 'Official ZIP SHA256 mismatch - not installed' }
    Add-Type -AssemblyName System.IO.Compression
    $archive=[System.IO.Compression.ZipFile]::OpenRead($zip)
    try {
      foreach ($entry in $archive.Entries) {
        $part=$entry.FullName.Replace('/','\')
        if ($part.StartsWith('\') -or $part -match '(^|[\\/])\.\.([\\/]|$)' -or $part -match '^[A-Za-z]:') { throw 'Unsafe path in archive' }
      }
    } finally { $archive.Dispose() }
    $unpack=Join-Path $stage 'unpacked'
    Expand-Archive -LiteralPath $zip -DestinationPath $unpack
    $candidate=Get-ChildItem -LiteralPath $unpack -Filter 'LibreHardwareMonitor.exe' -Recurse -File | Select-Object -First 1
    if (-not $candidate) { throw 'Missing monitor EXE in release' }
    if (-not (Test-Path -LiteralPath (Join-Path $candidate.DirectoryName 'LibreHardwareMonitorLib.dll'))) { throw 'Missing library DLL' }
    $null=New-Item -ItemType Directory -Path $lhmFolder -Force
    Copy-Item -Path (Join-Path $candidate.DirectoryName '*') -Destination $lhmFolder -Recurse -Force
    Add-Result 'LibreHardwareMonitor' 'available' $lhmExe
  } catch { Add-Result 'LibreHardwareMonitor' 'failed' '' $_.Exception.Message }
  finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
# Report is inventory, NOT a source of commands or authority/permission for BARQ.
$data = [ordered]@{
 schema=1;created_utc=(Get-Date).ToUniversalTime().ToString('o');source='BARQ Toolkit official/pinned installers'
 toolkit_root=$toolkit;tools=@($records.ToArray())
}
$data | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Log ('Inventory saved to: '+$reportPath)
Write-Log ('Toolkit setup complete: '+(@($records | Where-Object status -eq 'available').Count)+' available / '+$records.Count+' checked')
Write-Host 'Restart BARQ after setup. Sensor support must still be tested on this PC (not all CPUs expose a temperature).'
