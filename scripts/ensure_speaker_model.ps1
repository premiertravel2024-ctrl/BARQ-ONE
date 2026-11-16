# Download the open-source WeSpeaker model before BARQ Windows source staging.
# Only fixed HTTPS sources and a pinned SHA-256 are permitted.
# The model is needed by the native Windows/speaker-recognition build gate.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$modelDir = Join-Path $root 'models\speaker'
$file = Join-Path $modelDir 'wespeaker_en_voxceleb_resnet34_LM.onnx'
$expected = 'E9848563DA86F263117134DFD7AD63C92355B37DE492B55E325400C9D9C39012'
$urls = @(
  'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx',
  'https://huggingface.co/anujpatel863/Separate/resolve/c9b28337a09ccbf537f811a12ef2ee79b521c881/wespeaker_en_voxceleb_resnet34_LM.onnx'
)
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

function Test-VerifiedSpeakerModel([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
  try {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() -eq $expected
  } catch {
    return $false
  }
}

if (Test-VerifiedSpeakerModel $file) {
  Write-Host '[BARQ SPEAKER] Verified local WeSpeaker model (SHA-256 OK).' -ForegroundColor Green
  return
}

if (Test-Path -LiteralPath $file -PathType Leaf) {
  Write-Warning '[BARQ SPEAKER] Model exists but SHA-256 is wrong; refusing to package it.'
}

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
  throw 'Missing curl.exe. Windows 10/11 includes curl; install the official Windows curl runtime.'
}

$partial = "$file.download"
if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }

foreach ($url in $urls) {
  try {
    Write-Host ('[BARQ SPEAKER] Downloading verified speaker model from '+([Uri]$url).Host+'...') -ForegroundColor Cyan
    & curl.exe --fail --location --silent --show-error --retry 2 --connect-timeout 20 --max-time 360 --output $partial $url
    if ($LASTEXITCODE -ne 0) { throw "Download error: curl exit $LASTEXITCODE" }
    if (-not (Test-VerifiedSpeakerModel $partial)) {
      throw 'Downloaded model does not match the pinned SHA-256'
    }
    Move-Item -LiteralPath $partial -Destination $file -Force
    if (-not (Test-VerifiedSpeakerModel $file)) {
      throw 'Saved model failed SHA-256 verification'
    }
    Write-Host '[BARQ SPEAKER] Speaker model successfully downloaded and verified.' -ForegroundColor Green
    return
  } catch {
    Write-Warning ('[BARQ SPEAKER] '+$_.Exception.Message)
    if (Test-Path -LiteralPath $partial -PathType Leaf) {
      Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    }
  }
}

throw 'Speaker model download failed from both pinned sources. Check network/proxy and retry. BARQ will not build with an unverified model.'
