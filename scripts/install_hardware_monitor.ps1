# BARQ local sensors: a pinned, integrity-checked official LibreHardwareMonitor release.
# This installer NEVER elevates privileges or changes Windows security settings.
# The GUI/WMI channel is optional: BARQ can read LibreHardwareMonitorLib.dll directly.
param([string]$OfflineZip = '', [switch]$InstallOnly)
$ErrorActionPreference = 'Stop'
$Version = 'v0.9.6'
$ReleaseUrl = 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'
$ExpectedSha256 = '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
$AppRoot = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $AppRoot 'hardware-monitor'
$ReadScript = Join-Path $PSScriptRoot 'read_hardware_monitor.ps1'
$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ('barq-lhm-' + [guid]::NewGuid().ToString('N'))
$ZipPath = Join-Path $Stage 'LibreHardwareMonitor.zip'
$Cleanup = $false
try {
    $Bundled = Join-Path $Target ('bundled-' + $Version)
    $Exe = Get-Item -LiteralPath (Join-Path $Bundled 'LibreHardwareMonitor.exe') -ErrorAction SilentlyContinue
    if (-not $Exe) {
        $Exe = Get-ChildItem -LiteralPath $Target -Filter 'LibreHardwareMonitor.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    $Dll = if ($Exe) { Get-ChildItem -LiteralPath $Exe.DirectoryName -Filter 'LibreHardwareMonitorLib.dll' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1 } else { $null }
    if (-not $Exe -or -not $Dll) {
        New-Item -ItemType Directory -Force -Path $Stage | Out-Null
        $Cleanup = $true
        if ($OfflineZip) {
            if (-not (Test-Path -LiteralPath $OfflineZip -PathType Leaf)) { throw 'Offline sensor archive not found.' }
            Copy-Item -LiteralPath $OfflineZip -Destination $ZipPath -Force
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $ReleaseUrl -OutFile $ZipPath -UseBasicParsing -TimeoutSec 150
        }
        $Hasher = [System.Security.Cryptography.SHA256]::Create()
        $ZipStream = [System.IO.File]::OpenRead($ZipPath)
        try {
            $Sha = [System.BitConverter]::ToString($Hasher.ComputeHash($ZipStream)).Replace('-', '').ToLowerInvariant()
        } finally {
            $ZipStream.Dispose()
            $Hasher.Dispose()
        }
        if ($Sha -ne $ExpectedSha256) { throw ('Sensor archive SHA256 mismatch: installation cancelled. Actual SHA256: ' + $Sha) }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        try {
            foreach ($Entry in $Archive.Entries) {
                $Part = $Entry.FullName.Replace('/', '\')
                if ($Part.StartsWith('\') -or $Part -match '(^|\\)\.\.(\\|$)' -or $Part -match '^[A-Za-z]:') {
                    throw 'Unsafe path in official hardware monitor archive.'
                }
            }
        } finally { $Archive.Dispose() }
        $Extracted = Join-Path $Stage 'unpacked'
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Extracted)
        $Candidate = Get-ChildItem -LiteralPath $Extracted -Filter 'LibreHardwareMonitor.exe' -Recurse -File | Select-Object -First 1
        if (-not $Candidate) { throw 'Official archive lacks LibreHardwareMonitor.exe.' }
        $LibCandidate = Join-Path $Candidate.DirectoryName 'LibreHardwareMonitorLib.dll'
        if (-not (Test-Path -LiteralPath $LibCandidate -PathType Leaf)) { throw 'Official archive lacks LibreHardwareMonitorLib.dll.' }
        New-Item -ItemType Directory -Force -Path $Target | Out-Null
        # Copy the whole release, including required DLLs and driver files.
        Copy-Item -Path (Join-Path $Candidate.DirectoryName '*') -Destination $Target -Recurse -Force
        $Exe = Get-Item -LiteralPath (Join-Path $Target 'LibreHardwareMonitor.exe')
        $Dll = Get-Item -LiteralPath (Join-Path $Target 'LibreHardwareMonitorLib.dll')
        Write-Output ('[BARQ SENSORS] Official LibreHardwareMonitor ' + $Version + ' installed and SHA256 verified.')
    } else {
        Write-Output ('[BARQ SENSORS] Existing local LibreHardwareMonitor detected: ' + $Exe.FullName)
    }
    if ($InstallOnly) {
        Write-Output '[BARQ SENSORS] STAGED: sensor binaries ready for installer packaging.'
        exit 0
    }
    # First try the local read-only DLL. Do NOT require WMI, Windows service,
    # starting a GUI, Administrator elevation, or a network connection to read.
    if (Test-Path -LiteralPath $ReadScript -PathType Leaf) {
        $Reading = & $ReadScript -LibraryPath $Dll.FullName
        if ($LASTEXITCODE -eq 0 -and $Reading) {
            Write-Output '[BARQ SENSORS] READY: direct CPU/GPU temperature sensor reading.'
            exit 0
        }
    }
    try {
        $Sensors = @(Get-CimInstance -Namespace 'root\LibreHardwareMonitor' -ClassName Sensor -ErrorAction Stop |
            Where-Object { $_.SensorType -eq 'Temperature' -and $null -ne $_.Value })
        if ($Sensors.Count -gt 0) {
            Write-Output '[BARQ SENSORS] READY: WMI temperature sensor reading.'
            exit 0
        }
    } catch { }
    Write-Warning '[BARQ SENSORS] Installed but no readable CPU sensor. Hardware access may require a Windows approval / supported driver. BARQ will not invent a value.'
    exit 3
} catch {
    Write-Warning ('[BARQ SENSORS] Installation / verification failed: ' + $_.Exception.Message)
    Write-Warning 'Official release: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/tag/v0.9.6'
    exit 1
} finally {
    if ($Cleanup) { Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue }
}
