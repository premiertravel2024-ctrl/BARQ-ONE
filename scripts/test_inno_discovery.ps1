param()
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('barq-inno-discovery-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path (Join-Path $root 'Programs\Inno Setup 6') -Force
$oldLocal=$env:LOCALAPPDATA;$oldInno=$env:INNO_SETUP_COMPILER;$oldProgram=$env:ProgramFiles;$oldX86=${env:ProgramFiles(x86)}
$wrong=Join-Path $root 'version7.exe';$correct=Join-Path $root 'Programs\Inno Setup 6\ISCC.exe'
Set-Content -LiteralPath $wrong -Value 'fixture-v7'
Set-Content -LiteralPath $correct -Value 'fixture-v6'
function Get-Command { return [pscustomobject]@{Source=$wrong} }
# Zero PE version is legitimate. Readiness comes from the compiler probe.
$probe={param($Path) [pscustomobject]@{Ready=($Path -ne $wrong);Reason='Engine 7 is incompatible';Diagnostic='fixture'}}
function Get-ItemProperty { throw 'No registry in fixture' }
try {
    $env:LOCALAPPDATA=$root;$env:INNO_SETUP_COMPILER=$wrong;$env:ProgramFiles=$root;${env:ProgramFiles(x86)}=$root
    $found=& (Join-Path $PSScriptRoot 'find_inno.ps1') -CompilerProbe $probe
    if ($found -ne $correct) { throw 'Compatible user compiler was hidden by incompatible PATH/env version' }
    Write-Host 'PASS: version 6 is found despite incompatible compiler on PATH and in environment'
    $env:INNO_SETUP_COMPILER=$correct
    $found=& (Join-Path $PSScriptRoot 'find_inno.ps1') -CompilerProbe $probe
    if ($found -ne $correct) { throw 'Compatible explicit compiler was not honored' }
    Write-Host 'PASS: compatible explicit compiler honored'
    Remove-Item -LiteralPath $correct -Force
    $rejected=$false
    try { $null=& (Join-Path $PSScriptRoot 'find_inno.ps1') -CompilerProbe $probe } catch { $rejected=$_.Exception.Message -match 'Inno Setup 6' }
    if (-not $rejected) { throw 'Incompatible compiler was accepted' }
    Write-Host 'PASS: incompatible compiler is never returned as a valid build tool'
} finally {
    $env:LOCALAPPDATA=$oldLocal;$env:INNO_SETUP_COMPILER=$oldInno;$env:ProgramFiles=$oldProgram;${env:ProgramFiles(x86)}=$oldX86
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'BARQ Inno discovery checks passed: 3'
