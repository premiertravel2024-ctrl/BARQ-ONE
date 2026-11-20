# Fail-fast Windows pipeline: locked frontend dependencies, import guard, strict React compilation, Python tests, EXE smoke test, Setup.
param([switch]$StagedBuild, [switch]$UseBundledUI)

$ErrorActionPreference = 'Stop'
# Force UTF-8 across pytest and its Windows child processes (avoid cp1252 charmap).
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
# A previous installer never counts as evidence of a new successful build.
# Clear old output for the SAME version before building, even on a failed rebuild.
$version = '2.41.19'
$oldSetup = Join-Path $root "release\BARQ_Setup_$version.exe"
if (Test-Path -LiteralPath $oldSetup) { Remove-Item -LiteralPath $oldSetup -Force }
$buildMarker = Join-Path $root "release\build-ok-v$version.marker"
if (Test-Path -LiteralPath $buildMarker) { Remove-Item -LiteralPath $buildMarker -Force }

function Invoke-Step([string]$Label, [scriptblock]$Block) {
  Write-Host "`n==> $Label" -ForegroundColor Cyan
  & $Block
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)" }
}
if ($env:OS -ne 'Windows_NT') { throw 'Build requires Windows 10/11 x64.' }
# This must run BEFORE the Python launcher, npm and Inno preflight checks.
$prerequisiteScript=Join-Path $PSScriptRoot 'build_prerequisites.ps1'
if (-not (Test-Path -LiteralPath $prerequisiteScript)) { throw 'Missing build_prerequisites.ps1; extract the full source ZIP.' }
& $prerequisiteScript
& (Join-Path $PSScriptRoot 'ensure_webview2.ps1')
& (Join-Path $PSScriptRoot 'test_build_prerequisites.ps1')
& (Join-Path $PSScriptRoot 'test_webview2_prerequisite.ps1')

# Optional telemetry must not prevent the core assistant from building offline.
try { & (Join-Path $PSScriptRoot 'install_presentmon.ps1') -Stage } catch { Write-Warning ('FPS tool staging deferred: '+$_.Exception.Message) }

# The dependency preflight below locates npm.cmd even when this shell has a stale PATH.
# Do not reject Node installed by the BARQ toolkit based only on Get-Command npm.
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11 x64 and enable Python Launcher (py).' }
# Never pass quoted Python source via PowerShell -c. Windows PowerShell 5.1
# strips nested quotes when preparing native argv, triggering SyntaxError.
# Calling a .py script avoids ALL command-line quote interpretation.
$pythonCheck = Join-Path $PSScriptRoot 'verify_python_build.py'
if (-not (Test-Path -LiteralPath $pythonCheck -PathType Leaf)) {
  throw "Missing Python verification script: $pythonCheck"
}
& py -3.11 $pythonCheck
if ($LASTEXITCODE -ne 0) {
  throw 'Python 3.11 x64 check failed. Run: py -3.11 --version. Use Python 3.11 (64-bit).'
}
Write-Host 'Python build toolchain verified.' -ForegroundColor Green
# Verify THIS build's actual source, before npm or pytest. A stale extracted
# source must fail early instead of repeating 11 identical import errors.
& py -3.11 (Join-Path $PSScriptRoot 'verify_fastapi_build_source.py')
if ($LASTEXITCODE -ne 0) { throw 'FastAPI source preflight failed: stale or incompatible api.py.' }
# This release gate runs from scripts/ in a short-path staging directory.
# Check root-relative imports BEFORE npm, Python venv and frontend compilation.
& py -3.11 (Join-Path $PSScriptRoot 'run_python_build_tests.py') --check-imports
if ($LASTEXITCODE -ne 0) { throw 'Build test runner cannot import BARQ project services. Check the selected source folder.' }

foreach ($wakePath in @('voice\wake.py', 'scripts\barq_wake_vosk.py', 'scripts\install_arabic_wake.py', 'START_BARQ_WAKE_AR.vbs', 'INSTALL_ARABIC_WAKE.bat')) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $wakePath) -PathType Leaf)) { throw "Missing wake assistant source: $wakePath" }
}
& py -3.11 (Join-Path $PSScriptRoot 'verify_source_integrity.py')
if ($LASTEXITCODE -ne 0) { throw 'Source archive integrity failed. Re-extract the FULL SOURCE ZIP.' }
& py -3.11 (Join-Path $PSScriptRoot 'verify_release_consistency.py')
if ($LASTEXITCODE -ne 0) { throw 'Release metadata preflight failed; build blocked.' }
# Cheap, dependency-free guard: validate the actual GitHub Actions dependency
# graph before spending time installing npm/Python packages. The installer
# must require both the React build and early native Windows regressions.
& py -3.11 (Join-Path $PSScriptRoot 'verify_ci_dependencies.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows CI release dependency preflight failed; build blocked.' }
# Catch missing npm, long downloads on a nearly full disk, or an absent lockfile
# before copying into a fresh short-path build (no download in this check).
if (-not $UseBundledUI) {
  & py -3.11 (Join-Path $PSScriptRoot 'build_dependency_manager.py') --check
  if ($LASTEXITCODE -ne 0) { throw 'Dependency prerequisites missing. Run CHECK_BARQ_DOWNLOADS.bat for details.' }
  # A running terminal may keep an old PATH after winget installs Node.js.
  # Add a known npm.cmd directory to the current process PATH only, no registry edits.
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    $nodeFolders = @(
      (Join-Path $env:ProgramFiles 'nodejs'),
      (Join-Path $env:LOCALAPPDATA 'Programs\nodejs'),
      (Join-Path $env:APPDATA 'npm'),
      (Join-Path $env:USERPROFILE 'scoop\apps\nodejs-lts\current')
    )
    foreach ($folder in $nodeFolders) {
      if (Test-Path -LiteralPath (Join-Path $folder 'npm.cmd') -PathType Leaf) {
        $env:PATH = "$folder;$env:PATH"
        Write-Host "Using installed Node/npm folder: $folder" -ForegroundColor DarkGreen
        break
      }
    }
  }
}
# Check the actual opt-in code BEFORE spending time on npm; the compiled bundle
# will be checked again below to catch stale or tree-shaken frontend assets.
& py -3.11 (Join-Path $PSScriptRoot 'verify_desktop_consent_bundle.py') --root $root --source-only
if ($LASTEXITCODE -ne 0) { throw 'Computer/voice consent source preflight failed; build blocked.' }
& py -3.11 (Join-Path $PSScriptRoot 'audit_release_readiness.py')
if ($LASTEXITCODE -ne 0) { throw 'BARQ release readiness audit failed; refusing to package incomplete voice/application source.' }
$compilerCheck = & (Join-Path $PSScriptRoot 'find_inno.ps1')
if (-not $compilerCheck -or -not (Test-Path -LiteralPath $compilerCheck -PathType Leaf)) {
  throw 'Inno Setup 6 ISCC.exe was not found. Install Inno Setup before building.'
}
Write-Host "Inno Setup detected: $compilerCheck" -ForegroundColor DarkGreen


# Keep every dependency and build tool under a short path, even if the ZIP was
# extracted into a long Downloads directory. No administrator or registry edit.
# The native agent requires a WeSpeaker ONNX model that is intentionally not
# committed to Git. Fetch and SHA-256 verify it BEFORE short-path staging,
# otherwise the staged build fails after installing Python dependencies.
# Also run this check in staged builds, so direct stage invocations fail closed.
Write-Host "`n==> Ensuring verified speaker recognition model" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'ensure_speaker_model.ps1')

if (-not $StagedBuild) {
  if ($UseBundledUI) {
    & py -3.11 (Join-Path $PSScriptRoot 'build_short_path.py') --source $root --bundled-ui
  } else {
    & py -3.11 (Join-Path $PSScriptRoot 'build_short_path.py') --source $root
  }
  exit $LASTEXITCODE
}
if ($root.Length -gt 80) { throw 'Staged build directory exceeds the short-path budget.' }
New-Item -ItemType Directory -Force -Path (Join-Path $root 'release') | Out-Null
Start-Transcript -Path (Join-Path $root 'release\windows-build.log') -Force
$buildStarted = Get-Date
# Fail on a broken Python 3.11 venv BEFORE paying for npm ci and React compilation.
# The verified environment is reused for pip/tests/PyInstaller later below.
# The stdlib venv command can fail in Windows ensurepip even with a valid
# Python 3.11 installation. The helper logs the actual failure, attempts uv
# seeding / target-venv pip bootstrap and verifies venv isolation before exit.
# Do not skip the Python dependency/test gates if all methods fail.
Invoke-Step 'Creating isolated Python 3.11 build environment' {
  & py -3.11 (Join-Path $PSScriptRoot 'create_build_venv.py')
}
$python = Join-Path $root '.buildvenv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Build Python environment missing after bootstrap. See release\python-venv-setup.log.' }
& $python -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'Build venv has no working pip. See release\python-venv-setup.log.' }


# Respect the user's locally installed GE SS Two font without redistributing it.
$localFont = Join-Path $root 'web\fonts\ge-ss-two-medium.otf'
$buildFontDir = Join-Path $root 'frontend\public\fonts'
if (Test-Path -LiteralPath $localFont -PathType Leaf) {
  New-Item -ItemType Directory -Force -Path $buildFontDir | Out-Null
  Copy-Item -LiteralPath $localFont -Destination (Join-Path $buildFontDir 'ge-ss-two-medium.otf') -Force
}
if ($UseBundledUI) {
  # Recovery path: use the LAST bundled, previously compiled React UI. This is
  # not a recompile and does not include later frontend source-only changes.
  Write-Warning 'RECOVERY MODE: using the bundled React UI snapshot, not rebuilding React/TypeScript.'
  Write-Warning 'Source UI changes in this release will require a normal build to be visible.'
  $bundle = Join-Path $root 'web\react'
  $entry = Join-Path $bundle 'index.html'
  $assetsDir = Join-Path $bundle 'assets'
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw 'Bundled React entry missing. Use BUILD_BARQ.bat after fixing the frontend build.'
  }
  if (-not (Test-Path -LiteralPath $assetsDir -PathType Container)) {
    throw 'Bundled React assets missing. Recovery build blocked.'
  }
  $html = Get-Content -LiteralPath $entry -Raw -Encoding UTF8
  $bundleFiles = @([regex]::Matches($html, '(?:src|href)="(/assets/[^"]+)"'))
  if ($bundleFiles.Count -lt 2) { throw 'Bundled React HTML has no valid JavaScript/CSS references.' }
  foreach ($ref in $bundleFiles) {
    $relative = $ref.Groups[1].Value.TrimStart('/').Replace('/', [IO.Path]::DirectorySeparatorChar)
    $asset = Join-Path $bundle $relative
    if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
      throw "Bundled React reference missing: $relative"
    }
    if ((Get-Item -LiteralPath $asset).Length -eq 0) {
      throw "Bundled React asset is empty: $relative"
    }
  }
  Write-Host ('Verified bundled UI files: {0}' -f $bundleFiles.Count) -ForegroundColor Yellow
} else {
  Push-Location (Join-Path $root 'frontend')
  try {
    if (-not (Test-Path 'package-lock.json' -PathType Leaf)) {
      throw 'Missing frontend/package-lock.json. Reproducible release builds REQUIRE a committed lockfile.'
    }
    # Force npm devDependencies even if the machine has NODE_ENV=production or omit=dev configured.
    # Vite and esbuild are build-time tools and must be installed for a full release build.
    # The helper invokes EXACT locked npm ci --no-audit --no-fund --include=dev
    # using a persistent, per-user cache and bounded transient-network retries.
    # The lockfile and esbuild/native verification gates remain mandatory.
    Invoke-Step 'Installing EXACT locked React dependencies (including esbuild)' {
      & $python (Join-Path $PSScriptRoot 'build_dependency_manager.py') --frontend
    }
    # Fail immediately with a helpful, precise diagnosis instead of cascading into unrelated tests.
    Invoke-Step 'Verifying local esbuild binary' { node scripts/verify-esbuild.cjs }
    # Catch permission-policy regressions before expensive TS/React and Python gates.
    Invoke-Step 'Testing scoped autopilot permission guard' { node ../scripts/test_autopilot_guard.cjs }
    Invoke-Step 'Verifying installed Lucide exports' { npm run verify:icons }
    Invoke-Step 'Type-checking the complete frontend' { npm run typecheck }
    Invoke-Step 'Testing workspace UI and build regression guards' { npm run test:ui }
    Invoke-Step 'Testing personal assistant voice-text commands' { npm run test:personal }
    Invoke-Step 'Testing companion fast paths and speech glow' { npm run test:companion }
    Invoke-Step 'Testing local screen chat execution' { npm run test:screen }
    Invoke-Step 'Testing direct folder lookup and exact matching' { npm run test:folders }
    Invoke-Step 'Testing frontend dependency import guard' { npm run test:imports }
    Invoke-Step 'Testing frontend store, API and streaming' { npm run test:frontend }
    Invoke-Step 'Testing live voice audio crash protection' { node ../tests-js/live_voice_crash_regression.cjs }
    Invoke-Step 'Testing contextual chat coordination' { npm run test:chat }
    Invoke-Step 'Testing approval dispatch and deferred continuation' { npm run test:approvals }
    Invoke-Step 'Testing workspace synchronization and draft protection' { npm run test:workspace }
    Invoke-Step 'Type-checking and building React UI' { npm run build }
    # The capture regression checks the AudioWorklet emitted by Vite.
    Invoke-Step 'Testing voice capture and command handoff' { npm run test:voice }
  } finally { Pop-Location }
}
if (-not (Test-Path 'frontend/public/audio/live-capture.js' -PathType Leaf)) { throw 'Live voice source AudioWorklet missing: frontend/public/audio/live-capture.js' }
if (-not (Test-Path 'web/react/audio/live-capture.js' -PathType Leaf)) { throw 'Live voice production AudioWorklet missing: web/react/audio/live-capture.js. Rebuild React UI.' }
$audioWorklet = Get-Content -LiteralPath 'web/react/audio/live-capture.js' -Raw -Encoding UTF8
if (-not $audioWorklet.Contains("registerProcessor('barq-capture'")) { throw 'Live voice AudioWorklet is invalid: barq-capture processor is not registered.' }
if (-not (Test-Path 'web/react/index.html')) { throw 'React dist/index.html is missing.' }
$assets = @(Get-ChildItem 'web/react/assets' -File -ErrorAction SilentlyContinue)
if ($assets.Count -eq 0) { throw 'React assets are missing.' }
# The last BARQ releases sometimes installed a stale pre-built UI. Fail closed:
# a genuine v2.41.19 workspace requires its own freshly compiled React marker.
if (-not $UseBundledUI) {
  $studioMarker = 'v2.41.19-build-gated-ui'
  $fresh = @(Get-ChildItem 'web/react/assets' -Filter '*.js' -File | Where-Object {
      Select-String -LiteralPath $_.FullName -SimpleMatch -Pattern $studioMarker -Quiet
  })
  if ($fresh.Count -eq 0) { throw 'Fresh React build did not contain the v2.41.19 workspace marker. Installer blocked to prevent installing outdated UI.' }
  $wakeUi = @(Get-ChildItem 'web/react/assets' -Filter '*.js' -File | Where-Object {
      Select-String -LiteralPath $_.FullName -SimpleMatch -Pattern '/v1/voice/wake/pending' -Quiet
  })
  if ($wakeUi.Count -eq 0) { throw 'Fresh React build is missing the wake listener. Installer blocked to avoid a stale voice UI.' }
  # Check the ACTUAL compiled consent controls and their current runtime
  # endpoints/events. The old v2.41.1-desktop-consent-tooltip-fix marker was
  # removed in a prior UI refactor and caused a false build failure even when
  # `npm run build` succeeded. Keep the security check, not the obsolete token.
  & py -3.11 (Join-Path $PSScriptRoot 'verify_desktop_consent_bundle.py') --root $root
  if ($LASTEXITCODE -ne 0) { throw 'Fresh React build is missing working computer consent settings. Installer blocked.' }

}


# Frontend dependency check, type-check, and Vite compilation have already succeeded.
# Python packages use a persistent cache, but the venv remains isolated and fresh.
# Use a dedicated Python venv; never package the developer machine's Python environment.
# Install both requirement sets in ONE resolver pass to avoid repeated NumPy,
# voice and Windows-control wheel downloads. -r requirements-desktop.txt is
# still mandatory; the helper additionally reads requirements-computer-control.txt.
# Do NOT make pip's optional self-upgrade an unconditional internet build gate.
Invoke-Step 'Installing Python desktop dependencies' {
  & $python (Join-Path $PSScriptRoot 'build_dependency_manager.py') --python --python-executable $python
}
Invoke-Step 'Verifying native screen and computer agent support' {
  & $python (Join-Path $PSScriptRoot 'verify_agent_runtime.py')
}
# The acoustic wake test imports NumPy; it must be present in the same venv as pytest.
# A targeted check makes missing DLLs or a wrong wheel actionable BEFORE the full gate.
Invoke-Step 'Verifying direct microphone runtime into BARQ desktop before Python tests' {
  & $python (Join-Path $root 'scripts\verify_voice_build_dependencies.py')
}

# Run the complete Python suite through a monitored child process. Do NOT skip
# failed tests or package the EXE on timeout. Report the active test and save a
# streamed log in release/, rather than leaving a silent dot progress display.
# Verify the installed FastAPI and the actual imported API before pytest collection.
# Full traceback makes package-version conflicts diagnosable without screenshots.
& $python (Join-Path $PSScriptRoot 'verify_fastapi_build_source.py') --runtime
if ($LASTEXITCODE -ne 0) { throw 'FastAPI runtime import preflight failed; pytest has not started.' }

# Confirm the exact source and the REAL Windows Temp path before the full suite.
# This catches a stale unpatched build source without skipping a single test.
Write-Host "`n==> Verifying BARQ Windows Temp search scope fix" -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot 'verify_temp_search_build.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows Temp search preflight failed. Installer blocked. Verify source folder and share the full traceback.' }

Write-Host "`n==> Running project unit and API tests (verbose, bounded)" -ForegroundColor Cyan
# Module execution also preserves the project root on sys.path; importing the
# release gate by filename alone previously triggered ModuleNotFoundError.
& $python -m scripts.run_python_build_tests
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Python test gate FAILED or TIMED OUT. Installer correctly blocked.' -ForegroundColor Red
  Write-Host ("Open diagnostics: {0}" -f (Join-Path $root 'release\python-tests.log')) -ForegroundColor Yellow
  Write-Host ("Last test: {0}" -f (Join-Path $root 'release\python-tests-last-test.txt')) -ForegroundColor Yellow
  Write-Host ("All failed tests: {0}" -f (Join-Path $root 'release\python-tests-failures.txt')) -ForegroundColor Yellow
  throw "Python tests failed (exit $LASTEXITCODE)"
}


# Capture microphone inside BARQ.exe. All three native voice dependencies were
# installed and validated BEFORE pytest, preventing a test/build mismatch.

$pyArgs = @(
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
  '--name', 'BARQ', '--icon', 'assets/app.ico',
  '--collect-all', 'webview', '--collect-all', 'google.genai',
  '--collect-all', 'vosk', '--collect-all', 'sounddevice', '--collect-all', 'numpy',
  '--collect-all', 'pystray', '--collect-all', 'PIL', '--collect-submodules', 'mutagen',
  '--collect-submodules', 'uvicorn', '--collect-submodules', 'keyring.backends',
  '--collect-submodules', 'build', '--collect-submodules', 'api_routes', '--collect-submodules', 'brain',
  '--collect-submodules', 'mission', '--collect-submodules', 'coding',
  '--hidden-import', 'clr',
  '--collect-submodules', 'computer_control', '--collect-submodules', 'mcp', '--collect-submodules', 'launcher', '--collect-submodules', 'pywinauto',
  '--collect-submodules', 'comtypes',
  '--collect-submodules', 'pyautogui', '--collect-submodules', 'keyboard',
  '--collect-submodules', 'mss', '--collect-submodules', 'send2trash',
  '--collect-submodules', 'playwright', '--collect-submodules', 'pycaw', '--collect-submodules', 'screen_brightness_control',
  '--add-data', 'web;web', '--add-data', 'config;config', '--add-data', 'assets;assets',
  '--add-data', 'scripts/read_screen_ocr.ps1;scripts',
  '--add-data', 'scripts/read_hardware_monitor.ps1;scripts',
  '--add-data', 'scripts/install_hardware_monitor.ps1;scripts',
  '--add-data', 'models/speaker;models/speaker',
  '--collect-all','sherpa_onnx', '--collect-all','winsdk',
  'desktop.py'
)
if (Test-Path (Join-Path $root 'tools/presentmon/PresentMon-2.6.0-x64.exe')) { $pyArgs+=@('--add-data','tools/presentmon;tools/presentmon') }
Invoke-Step 'Packaging native Windows .exe with Python + React' { & $python @pyArgs }
# Optional Arabic wake is built into a standalone EXE so end-users do NOT
# need Python/pip/Vosk installed globally. The ~318MB Arabic MODEL remains an
# explicit, post-install download choice; no hidden background microphone.
# Vosk, sounddevice, pystray and Pillow were installed by the same pinned
# desktop requirements above. No second PyPI resolution/upgrade is necessary.
Invoke-Step 'Verifying isolated Arabic wake runtime for Windows packaging' {
  & $python (Join-Path $PSScriptRoot 'verify_voice_build_dependencies.py')
}
$wakeArgs = @(
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
  '--name', 'BARQ_Wake', '--paths', '.',
  '--collect-all', 'vosk', '--collect-all', 'sounddevice',
  '--collect-all', 'pystray', '--collect-all', 'PIL',
  'scripts/barq_wake_vosk.py'
)
Invoke-Step 'Packaging offline wake listener and model installer' { & $python @wakeArgs }
$wakeExe = Join-Path $root 'dist\BARQ_Wake.exe'
if (-not (Test-Path -LiteralPath $wakeExe -PathType Leaf)) { throw 'Standalone Arabic wake helper was not packaged.' }
Invoke-Step 'Smoke testing standalone wake dependencies without the microphone' { & $wakeExe --self-test }
Copy-Item -LiteralPath $wakeExe -Destination (Join-Path $root 'dist\BARQ\BARQ_Wake.exe') -Force
$installedWake = Join-Path $root 'dist\BARQ\BARQ_Wake.exe'
if (-not (Test-Path $installedWake -PathType Leaf)) { throw 'Packaged wake helper missing from installer input.' }

$exe = Join-Path $root 'dist\BARQ\BARQ.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'PyInstaller returned success without producing dist\BARQ\BARQ.exe. Inno Setup cannot run before this step.' }
$bundledFiles = @(Get-ChildItem -LiteralPath (Join-Path $root 'dist\BARQ') -Force)
if ($bundledFiles.Count -lt 2) { throw 'PyInstaller produced an incomplete BARQ directory. Installer compilation blocked.' }

$report = Join-Path $root 'release\self-test.json'
$smokeStdout = Join-Path $root 'release\self-test.stdout.log'
$smokeStderr = Join-Path $root 'release\self-test.stderr.log'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'release') | Out-Null
foreach ($previous in @($report, $smokeStdout, $smokeStderr)) {
  if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Force }
}
# --windowed builds have a GUI subsystem. In Windows PowerShell, & $exe may return
# before the process finishes, so checking the report immediately is a race.
Write-Host "`n==> Smoke-testing the actual packaged Windows executable" -ForegroundColor Cyan
$quotedReport = '"' + $report + '"'
$smokeProcess = Start-Process -FilePath $exe -ArgumentList @('--self-test', $quotedReport) `
  -WorkingDirectory (Split-Path $exe -Parent) `
  -RedirectStandardOutput $smokeStdout -RedirectStandardError $smokeStderr `
  -Wait -PassThru -ErrorAction Stop
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
  $stderrText = if (Test-Path -LiteralPath $smokeStderr) { Get-Content -LiteralPath $smokeStderr -Raw -ErrorAction SilentlyContinue } else { '' }
  throw "Packaged EXE exited with code $($smokeProcess.ExitCode) but created no self-test report. Check: $smokeStderr`n$stderrText"
}
$smoke = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
if ($smokeProcess.ExitCode -ne 0 -or $smoke.status -ne 'ok' -or $smoke.ui -ne 'react' -or -not $smoke.frozen -or $smoke.version -ne $version -or -not $smoke.live_voice_worklet -or -not $smoke.voice_runtime_bundled -or -not $smoke.cleanup_completed) {
  throw "Packaged .exe failed health checks (exit $($smokeProcess.ExitCode)): $($smoke | ConvertTo-Json -Compress)"
}
Write-Host 'Packaged .exe self-test PASSED' -ForegroundColor Green

# Both Setup and portable ship with the verified local sensor provider.
$monitorRoot = Join-Path $root 'hardware-monitor'
$monitorDll = Join-Path $monitorRoot 'LibreHardwareMonitorLib.dll'
$monitorExe = Join-Path $monitorRoot 'LibreHardwareMonitor.exe'
if (!(Test-Path -LiteralPath $monitorDll -PathType Leaf) -or !(Test-Path -LiteralPath $monitorExe -PathType Leaf)) {
  Invoke-Step 'Staging official LibreHardwareMonitor v0.9.6 for offline use' {
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install_hardware_monitor.ps1') -InstallOnly
  }
}
if (!(Test-Path -LiteralPath $monitorDll -PathType Leaf) -or !(Test-Path -LiteralPath $monitorExe -PathType Leaf)) {
  throw 'The required local hardware sensor toolkit is missing.'
}
Copy-Item -LiteralPath $monitorRoot -Destination (Join-Path $root 'dist\BARQ') -Recurse -Force
$compiler = & (Join-Path $PSScriptRoot 'find_inno.ps1')
if (-not $compiler) { throw 'Inno Setup compiler could not be found.' }
# Call the same compiler discovered during the preflight. The input is anchored to
# its absolute path, so changing the current directory cannot break the source paths.
$installerScript = Join-Path $root 'scripts\installer.iss'
Invoke-Step 'Building Windows Setup.exe (Inno Setup)' { & $compiler $installerScript }
$setup = Join-Path $root "release\BARQ_Setup_$version.exe"
if (-not (Test-Path $setup)) { throw 'Installer missing after Inno Setup completed.' }
if ((Get-Item -LiteralPath $setup).LastWriteTime -lt $buildStarted) { throw 'Installer predates this build.' }
Invoke-Step 'Installing and testing Setup in an isolated temporary folder' {
  & (Join-Path $PSScriptRoot 'smoke_install.ps1') -Setup $setup -Version $version -ReportDir (Join-Path $root 'release')
}
$portable = Join-Path $root "release\BARQ_Portable_$version.zip"
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Force }
Compress-Archive -Path (Join-Path $root 'dist\BARQ') -DestinationPath $portable -CompressionLevel Optimal
Invoke-Step 'Writing release SHA256 evidence' { & $python (Join-Path $PSScriptRoot 'release_evidence.py') }
Write-Host "`nWindows build complete" -ForegroundColor Green
Write-Host "Portable app : $exe"
Write-Host "Windows Setup: $setup"
Write-Host "Validation   : $report"
$uiBuildKind = if ($UseBundledUI) { 'bundled-recovery' } else { 'fresh-react' }
Set-Content -LiteralPath (Join-Path $root 'release\UI_BUILD_MODE.txt') -Value $uiBuildKind -Encoding UTF8
# Written only after React, pytest, EXE self-test and Inno Setup have all passed.
if ($UseBundledUI) {
  Write-Warning 'Recovery output is NOT a verified fresh-source release.'
  $buildMarker = Join-Path $root "release\recovery-v$version.marker"
}
Set-Content -LiteralPath $buildMarker -Value "ok|BARQ|$version|$((Get-Date).ToUniversalTime().ToString('o'))|$uiBuildKind" -Encoding UTF8
Stop-Transcript

