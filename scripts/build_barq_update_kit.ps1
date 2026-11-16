param(
  [Parameter(Mandatory=$false)][string]$SourceRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
  $root = (Resolve-Path -LiteralPath $SourceRoot).Path
  foreach ($required in @('BUILD_BARQ.bat','desktop.py','scripts\build_short_path.py','scripts\installer_update.iss','frontend\src\App.tsx')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $required) -PathType Leaf)) {
      throw "Update kit is incomplete: $required. Extract the entire ZIP to one folder, then use BUILD_UPDATE.bat."
    }
  }
  Write-Host 'BARQ update kit: self-contained project detected.' -ForegroundColor Cyan
  Write-Host "Build source: $root"
  # The source here is bundled with the update. Never modify the installed app at build time.
  $release = Join-Path $root 'release'
  New-Item -ItemType Directory -Force -Path $release | Out-Null
  $update = Join-Path $release 'BARQ_Update_2.30.0_VoiceWake.exe'
  if (Test-Path -LiteralPath $update) { Remove-Item -LiteralPath $update -Force }
  # Cache the official Windows NumPy binary before staging. This is a source-local
  # cache (not a global installation); SHA-256 checked against PyPI.
  Write-Host 'Checking and automatically downloading missing voice-test dependencies...' -ForegroundColor Cyan
  & py -3.11 (Join-Path $root 'scripts\prepare_voice_wheels.py')
  if ($LASTEXITCODE -ne 0) { throw 'Voice dependency download failed. Fix network connection and retry.' }
  Write-Host '[1/3] Running the full source build and verified tests (this may take some time)...' -ForegroundColor Cyan
  & py -3.11 (Join-Path $root 'scripts\build_short_path.py') --source $root
  if ($LASTEXITCODE -ne 0) { throw "BARQ build failed. The installed application is unchanged. Review messages above." }
  $portable = Join-Path $release 'BARQ_Portable_2.30.0.zip'
  $marker = Join-Path $release 'build-ok-v2.30.0.marker'
  if (-not (Test-Path -LiteralPath $portable -PathType Leaf) -or -not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw 'Verified Windows build or its completion marker missing. Existing BARQ is unchanged.'
  }
  $markerContents = (Get-Content -LiteralPath $marker -Raw -Encoding UTF8).Trim()
  if (-not $markerContents.StartsWith('ok|BARQ|2.30.0|')) { throw 'Invalid build validation marker.' }
  Write-Host '[2/3] Unpacking validated Windows binaries for the update...' -ForegroundColor Cyan
  $dist = Join-Path $root 'dist'
  $bin = Join-Path $dist 'BARQ'
  if(Test-Path -LiteralPath $bin){Remove-Item -LiteralPath $bin -Recurse -Force}
  New-Item -ItemType Directory -Force -Path $dist | Out-Null
  Expand-Archive -LiteralPath $portable -DestinationPath $dist -Force
  foreach ($exe in @('BARQ.exe','BARQ_Wake.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $exe) -PathType Leaf)) { throw "Packaged runtime missing: $exe" }
  }
  Write-Host '[3/3] Compiling an update for the existing installation. No Vosk re-download.' -ForegroundColor Cyan
  $findInno = Join-Path $root 'scripts\find_inno.ps1'
  $compiler = & $findInno
  if (-not $compiler -or -not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'Inno Setup 6 compiler not found.' }
  & $compiler (Join-Path $root 'scripts\installer_update.iss')
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $update -PathType Leaf)) { throw 'Failed to compile BARQ update.' }
  Write-Host "SUCCESS! Update installer: $update" -ForegroundColor Green
  Start-Process explorer.exe -ArgumentList @($release)
} catch {
  Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'Your installed BARQ and existing Arabic voice model have not been changed by this build step.' -ForegroundColor Yellow
  exit 1
}
