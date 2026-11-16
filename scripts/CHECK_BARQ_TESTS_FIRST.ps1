# Windows Python release-test diagnostic for a complete BARQ source ZIP.
# If frontend dependencies are missing, installs EXACT locked npm packages
# using BARQ's audited helper; never builds React or produces EXE.
# Then runs the original strict Python tests, including real UI smoke tests.
param(
  [string]$BuildPython = '',
  [switch]$OneTest
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($env:OS -ne 'Windows_NT') { throw 'BARQ Windows test diagnostics require Windows' }

if (-not $BuildPython) {
  $stage=Join-Path $env:LOCALAPPDATA 'Bq\b'
  if (-not (Test-Path -LiteralPath $stage -PathType Container)) {
    throw "No previous BARQ build environment found in $stage"
  }
  $candidates=@(
    Get-ChildItem -LiteralPath $stage -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {
      $exe=Join-Path $_.FullName '.buildvenv\Scripts\python.exe'
      if (Test-Path -LiteralPath $exe -PathType Leaf) {
        [PSCustomObject]@{Path=$exe;Date=$_.LastWriteTime}
      }
    } | Sort-Object Date -Descending
  )
  if (-not $candidates -or -not $candidates[0]) {
    throw "No prepared Python build venv found under $stage. Run BARQ build once to create it."
  }
  $BuildPython=$candidates[0].Path
}
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
  throw "No Python executable at $BuildPython"
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'release') | Out-Null
Write-Host "Python: $BuildPython" -ForegroundColor Cyan
Write-Host "Source: $root"
Push-Location $root
$previousPythonPath=$env:PYTHONPATH
try {
  # sys.path must import source edits made AFTER a previous full-stage build.
  $env:PYTHONPATH=$root
  & $BuildPython -c "import pytest,pytest_timeout; print('pytest environment READY')"
  if ($LASTEXITCODE -ne 0) { throw "Existing build venv lacks pytest and pytest-timeout." }
  if (-not $OneTest) {
    # An extracted source ZIP intentionally has no node_modules. Standalone
    # Python checks still include REAL TS/React smoke tests, so install the
    # exactly-locked frontend build dependencies BEFORE starting pytest.
    # Reuse BARQ's audited npm-ci helper (lock-integrity and retry policy);
    # never skip the frontend tests or silently allow missing esbuild.
    $frontend=Join-Path $root 'frontend'
    $frontendReady=$false
    Push-Location $frontend
    try {
      & node.exe -e "require.resolve('esbuild'); require.resolve('typescript'); require.resolve('vite')"
      if ($LASTEXITCODE -eq 0) {
        & node.exe scripts/verify-esbuild.cjs
        $frontendReady=($LASTEXITCODE -eq 0)
      }
    } finally {
      Pop-Location
    }
    if (-not $frontendReady) {
      Write-Host "[BARQ PREREQUISITES] Locked frontend dependencies are missing. Running npm ci through BARQ's official helper..." -ForegroundColor Yellow
      & $BuildPython -u (Join-Path $PSScriptRoot 'build_dependency_manager.py') --frontend
      if ($LASTEXITCODE -ne 0) {
        throw "Cannot install locked frontend dependencies. See release/dependency-npm.log. Python UI tests were NOT skipped."
      }
    }
    Push-Location $frontend
    try {
      & node.exe -e "require.resolve('esbuild'); require.resolve('typescript'); require.resolve('vite')"
      if ($LASTEXITCODE -ne 0) { throw "Vite/TypeScript/esbuild remain missing after locked npm ci." }
      & node.exe scripts/verify-esbuild.cjs
      if ($LASTEXITCODE -ne 0) { throw "esbuild native binary verification failed; tests cannot start." }
    } finally {
      Pop-Location
    }
    Write-Host "[BARQ PREREQUISITES] Frontend build tools verified for Python smoke tests." -ForegroundColor Green
  }
  if ($OneTest) {
    & $BuildPython -X faulthandler -m pytest -v --tb=short --timeout=90 "tests/test_v231_toolkit_setup_and_discovery.py::test_fixed_lhm_toolkit_install_is_detected"
    $code=$LASTEXITCODE
  } else {
    & $BuildPython -u -m scripts.run_python_build_tests
    $code=$LASTEXITCODE
  }
  if ($code -ne 0) {
    Write-Host "[BARQ TESTS FAILED] Exit=$code" -ForegroundColor Red
    Write-Host "Reports: $root\release\python-tests-shards.json and python-tests-failures.txt"
    exit $code
  }
  Write-Host "[BARQ TESTS PASSED] All selected test gates completed." -ForegroundColor Green
} finally {
  $env:PYTHONPATH=$previousPythonPath
  Pop-Location
}
