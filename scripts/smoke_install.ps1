# Verify an actual Inno Setup install in a SHORT, isolated per-user directory.
# On failure, keep a useful excerpt of the Inno log; NEVER treat a failed
# installer as a successful release. This script also supports rerunning the
# smoke test on an already compiled Setup.exe without rebuilding all of BARQ.
param(
  [Parameter(Mandatory=$true)][string]$Setup,
  [Parameter(Mandatory=$true)][string]$Version,
  [Parameter(Mandatory=$true)][string]$ReportDir,
  [switch]$KeepFailedInstall
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Setup = (Resolve-Path -LiteralPath $Setup -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $ReportDir -PathType Container)) {
  New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
}
$ReportDir = (Resolve-Path -LiteralPath $ReportDir -ErrorAction Stop).Path
$local = [Environment]::GetFolderPath('LocalApplicationData')
if ([string]::IsNullOrWhiteSpace($local)) { $local = [IO.Path]::GetTempPath() }
# Shorter than %TEMP%\BARQ-smoke-<full GUID>. Long Python-package paths inside
# BARQ's onedir distribution can otherwise exceed the Win32 MAX_PATH limit.
$smokeBase = Join-Path $local 'Bq\smoke'
New-Item -ItemType Directory -Path $smokeBase -Force | Out-Null
$smokeId = [Guid]::NewGuid().ToString('N')
$target = Join-Path $smokeBase ('i' + $smokeId.Substring(0, 10))
$report = Join-Path $ReportDir 'installed-self-test.json'
$installLog = Join-Path $ReportDir 'installer-smoke.log'
$diagnostics = Join-Path $ReportDir 'installer-smoke-diagnostics.txt'
$resultPath = Join-Path $ReportDir 'installer-smoke-result.json'
$stage = 'starting'
$exitCode = $null
$success = $false
$installerLaunched = $false
foreach ($p in @($report, $installLog, $diagnostics, $resultPath)) {
  if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
}
function Get-InstallLogTail {
  if (-not (Test-Path -LiteralPath $installLog -PathType Leaf)) {
    return '[Inno Setup did not create a log. Check antivirus/SmartScreen, permissions and Setup startup.]'
  }
  try {
    $lines = @(Get-Content -LiteralPath $installLog -Encoding UTF8 -ErrorAction Stop)
    if ($lines.Count -eq 0) { return '[Installer log was empty.]' }
    return (($lines | Select-Object -Last 130) -join "`r`n")
  } catch {
    return '[Could not read installer log: ' + $_.Exception.Message + ']'
  }
}
try {
  $stage = 'inno-setup-install'
  # Inno Setup /DIR and /LOG must be quoted explicitly: user names may contain
  # spaces. Keep a distinct smoke AppId so upgrades/shortcuts are not touched.
  $installArgs = @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS',
    '/SP-', '/BARQSMOKE=1', ('/SMOKEID=' + $smokeId),
    ('/DIR="' + $target + '"'), ('/LOG="' + $installLog + '"')
  )
  Write-Host ('[BARQ SMOKE] Installing into short directory: ' + $target)
  Write-Host ('[BARQ SMOKE] Inno Setup log: ' + $installLog)
  $install = Start-Process -FilePath $Setup -ArgumentList $installArgs -PassThru -ErrorAction Stop
  $installerLaunched = $true
  if (-not $install.WaitForExit(240000)) {
    $install.Kill()
    $install.WaitForExit(10000) | Out-Null
    throw 'Installer smoke timed out (240 seconds).'
  }
  $exitCode = $install.ExitCode
  if ($exitCode -ne 0) {
    # Exit 5 in Inno Setup means cancelled during installation, OR a file
    # error got an automatic Abort because /SUPPRESSMSGBOXES is enabled.
    # Do NOT guess the file: inspect Inno Setup's real /LOG output.
    throw "Installer smoke failed (Inno exit $exitCode). Read $diagnostics and $installLog"
  }
  $stage = 'verify-installed-files'
  $installed = Join-Path $target 'BARQ.exe'
  foreach ($file in @('BARQ.exe','BARQ_Wake.exe','SHOW_BARQ_FILES.bat','BARQ_SYSTEM_ACCESS_INSTALL_REPORT_AR.md',
  'hardware-monitor\LibreHardwareMonitor.exe','hardware-monitor\LibreHardwareMonitorLib.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $file) -PathType Leaf)) {
      throw "Installer omitted: $file"
    }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $target 'models\wake') -PathType Container)) {
    throw 'Installer omitted the Arabic wake model directory.'
  }
  $stage = 'wake-runtime-self-test'
  $wakeSmoke = Start-Process -FilePath (Join-Path $target 'BARQ_Wake.exe') `
    -ArgumentList @('--self-test') -WorkingDirectory $target -PassThru -WindowStyle Hidden
  if (-not $wakeSmoke.WaitForExit(60000)) { $wakeSmoke.Kill(); throw 'Installed wake helper smoke timed out.' }
  if ($wakeSmoke.ExitCode -ne 0) { throw "Installed wake helper runtime dependencies failed: exit $($wakeSmoke.ExitCode)" }
  $stage = 'app-runtime-self-test'
  $test = Start-Process -FilePath $installed -ArgumentList @('--self-test', ('"' + $report + '"')) `
    -WorkingDirectory $target -PassThru
  if (-not $test.WaitForExit(90000)) { $test.Kill(); throw 'Installed executable smoke timed out.' }
  if ($test.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "Installed BARQ.exe self-test failed (exit $($test.ExitCode); report exists: $(Test-Path -LiteralPath $report))"
  }
  $data = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($data.status -ne 'ok' -or -not $data.frozen -or $data.version -ne $Version -or $data.ui -ne 'react' -or -not $data.cleanup_completed) {
    throw 'Installed executable reported invalid health or version.'
  }
  $success = $true
  Write-Host '[BARQ SMOKE] Installed Setup + wake + BARQ runtime self-tests PASSED.' -ForegroundColor Green
} catch {
  $problem = $_.Exception.Message
  $tail = Get-InstallLogTail
  # Save a full transcript before uninstalling the failed smoke install.
  $content = @(
    'BARQ Installer Smoke Diagnostic',
    'Stage: ' + $stage,
    'Exit code: ' + $exitCode,
    'Error: ' + $problem,
    'Setup: ' + $Setup,
    'Install directory: ' + $target,
    'Log: ' + $installLog,
    '--- LAST 130 INSTALLER LOG LINES ---',
    $tail
  ) -join "`r`n"
  Set-Content -LiteralPath $diagnostics -Value $content -Encoding UTF8
  Write-Host $content -ForegroundColor Yellow
  throw "BARQ installer smoke FAILED at [$stage]. Diagnostic: $diagnostics. Original: $problem"
} finally {
  # Persist status independently of success/failure. A failing smoke never
  # produces a build-ok marker. Use a private short-lived test AppId.
  $resultObject = [ordered]@{
    status = $(if ($success) { 'ok' } else { 'failed' })
    version = $Version
    stage = $stage
    exit_code = $exitCode
    installer_log = $installLog
    diagnostics = $diagnostics
    install_directory = $target
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
  }
  $resultObject | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultPath -Encoding UTF8
  $uninstaller = Join-Path $target 'unins000.exe'
  if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
    try {
      $remove = Start-Process -FilePath $uninstaller `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -PassThru -ErrorAction Stop
      if (-not $remove.WaitForExit(90000)) { $remove.Kill(); Write-Warning 'Smoke uninstall timed out.' }
      elseif ($remove.ExitCode -ne 0) { Write-Warning "Smoke uninstall returned $($remove.ExitCode)" }
    } catch { Write-Warning ("Smoke cleanup failed: " + $_.Exception.Message) }
  }
  if ($success -or -not $KeepFailedInstall) {
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}
