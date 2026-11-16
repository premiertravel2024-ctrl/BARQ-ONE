# BARQ ONE native Windows x64 build, driven by a local desktop or dedicated runner.
# No git credentials or GitHub registration tokens are needed by this script.
param([switch]$PreflightOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$release = Join-Path $root 'release'
New-Item -ItemType Directory -Path $release -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $release "local-windows-build-$stamp.log"
$version = '2.40.2'
$installer = Join-Path $release "BARQ_Setup_$version.exe"
$portable = Join-Path $release "BARQ_Portable_$version.zip"
$marker = Join-Path $release "build-ok-v$version.marker"
$start = Get-Date

function Require-Command([string]$name, [string]$guidance) {
    $item=Get-Command $name -ErrorAction SilentlyContinue
    if (-not $item) { throw "$name not found. $guidance" }
}
function Require-Exit([string]$label, [int]$code) {
    if ($code -ne 0) { throw "$label failed (exit $code)" }
}

Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Host 'BARQ ONE - native Windows build and verification' -ForegroundColor Cyan
    Write-Host "Source: $root"
    Write-Host "Build log: $log"
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'Windows 10/11 x64 required for BARQ installer compilation'
    }
    Require-Command 'powershell.exe' 'Windows PowerShell 5.1 is required'
    Require-Command 'py.exe' 'Install Python 3.11 x64 with Python Launcher'
    Require-Command 'node.exe' 'Install Node.js 22 LTS'
    Require-Command 'npm.cmd' 'Node.js npm is required for React'
    Write-Host ('Windows: '+[Environment]::OSVersion.Version.ToString())
    & py.exe -3.11 --version
    Require-Exit 'Python 3.11 x64' $LASTEXITCODE
    & node.exe --version
    Require-Exit 'Node' $LASTEXITCODE
    & npm.cmd --version
    Require-Exit 'npm' $LASTEXITCODE

    $findInno=Join-Path $PSScriptRoot 'find_inno.ps1'
    if (-not (Test-Path -LiteralPath $findInno)) { throw 'Inno Setup locator missing from full BARQ source' }
    $compiler = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $findInno
    Require-Exit 'Inno Setup locator' $LASTEXITCODE
    $compiler=(@($compiler) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -Last 1)
    if (-not $compiler) { throw 'Inno Setup 6 ISCC.exe not installed; install it before building' }

    $drive=[IO.Path]::GetPathRoot($root)
    $disk=Get-PSDrive -Name $drive.Substring(0,1)
    $free=[math]::Round($disk.Free/1GB,1)
    Write-Host "Free space: $free GB"
    if ($disk.Free -lt 12GB) { throw 'Need at least 12 GB free for build dependencies, staging and EXE' }

    foreach ($p in @('frontend\package-lock.json','requirements-desktop.txt',
                      'requirements-computer-control.txt','scripts\build_windows.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $p) -PathType Leaf)) {
            throw "Incomplete BARQ source: missing $p"
        }
    }
    if ($PreflightOnly) {
        Write-Host 'Preflight passed. No dependencies installed and no build started.' -ForegroundColor Green
        exit 0
    }

    $buildScript=Join-Path $PSScriptRoot 'build_windows.ps1'
    Write-Host 'Executing existing fail-fast BARQ release pipeline...' -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript
    Require-Exit 'BARQ Windows build pipeline' $LASTEXITCODE

    foreach ($file in @($installer,$portable,$marker)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Release verification failed: missing $file"
        }
        if ((Get-Item -LiteralPath $file).LastWriteTime -lt $start.AddSeconds(-5)) {
            throw "Release verification failed: stale artifact $file"
        }
    }
    if (-not ((Get-Content -LiteralPath $marker -Raw) -match 'fresh-react')) {
        throw 'Release verification failed: stale React bundle marker'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $release 'installed-self-test.json'))) {
        throw 'Installed application self-test evidence is missing'
    }
    $installed=Get-Content (Join-Path $release 'installed-self-test.json') -Raw | ConvertFrom-Json
    if ($installed.status -ne 'ok' -or $installed.version -ne $version -or -not $installed.frozen) {
        throw 'Installed application smoke test did not pass'
    }
    Write-Host 'BARQ installer and portable ZIP built and verified.' -ForegroundColor Green
    Write-Host "Installer: $installer"
    Write-Host "Portable: $portable"
    Get-FileHash -Algorithm SHA256 -LiteralPath $installer, $portable |
        Format-Table Path,Hash -AutoSize
}
catch {
    Write-Host ('BUILD FAILED: '+$_.Exception.Message) -ForegroundColor Red
    Write-Host "Send the sanitized build log for diagnosis: $log" -ForegroundColor Yellow
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
