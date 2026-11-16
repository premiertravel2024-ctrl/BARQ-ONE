# Portable behavior tests. Does not download or install programs on the host.
param([string]$Source=(Join-Path $PSScriptRoot 'build_prerequisites.ps1'))
$ErrorActionPreference='Stop'
. $Source -FunctionsOnly
$script:checks=0
$originalLocalAppData=$env:LOCALAPPDATA
function Assert-Barq([bool]$Value,[string]$Name) {
    if (-not $Value) { throw ('FAIL: '+$Name) }
    $script:checks++;Write-Host ('PASS: '+$Name)
}
$originalFindPython=${function:Find-BarqPython}
$originalFindNode=${function:Find-BarqNode}
$originalFindInno=${function:Find-BarqInno}
$originalInstallNode=${function:Install-BarqNode}
$originalReceive=${function:Receive-BarqFile}
$originalTest=${function:Test-BarqDownload}
$script:ready=@{python=$true;node=$true;inno=$true};$script:installs=@();$script:fallbacks=@()
function Find-BarqPython { if($script:ready.python){return 'python-ready'} }
function Find-BarqNode { if($script:ready.node){return 'node-ready'} }
function Find-BarqInno { if($script:ready.inno){return 'inno-ready'} }
function Install-BarqPython { $script:installs+='python';$script:ready.python=$true }
function Install-BarqNode { $script:installs+='node';$script:ready.node=$true }
function Install-BarqInno { $script:installs+='inno';$script:ready.inno=$true }
function Invoke-BarqWinget([string]$Id) { $script:fallbacks+=$Id;$script:ready.inno=$true }
$records=Ensure-BarqBuildTools
Assert-Barq ($records.Count -eq 3 -and $script:installs.Count -eq 0) 'existing tools are reused without reinstall'
$script:ready=@{python=$false;node=$false;inno=$false}
$records=Ensure-BarqBuildTools
Assert-Barq (($script:installs -join ',') -eq 'python,node,inno') 'missing tools install before build in dependency order'
Assert-Barq (@($records|Where-Object{-not $_.ready}).Count -eq 0) 'each installed tool is actually re-probed'
$script:installs=@();$script:ready.node=$false
$records=Ensure-BarqBuildTools -CheckOnly
Assert-Barq ($script:installs.Count -eq 0 -and -not $records[1].ready) 'check-only performs no installation'
$script:ready.node=$true;$script:ready.inno=$false
function Install-BarqInno { throw 'network unavailable' }
$records=Ensure-BarqBuildTools
Assert-Barq ($script:fallbacks[-1] -eq 'JRSoftware.InnoSetup' -and $records[2].ready) 'official catalog fallback is probed before success'
$script:ready.inno=$false
function Install-BarqInno { }
$rejected=$false
try { $null=Ensure-BarqBuildTools } catch { $rejected=$_.Exception.Message -match 'not usable' }
Assert-Barq $rejected 'installer exit without usable tool never counts as success'
$script:ready.inno=$false
function Install-BarqInno { throw 'installer is still running' }
$before=$script:fallbacks.Count;$rejected=$false
try { $null=Ensure-BarqBuildTools } catch { $rejected=$true }
Assert-Barq ($rejected -and $script:fallbacks.Count -eq $before) 'no overlapping fallback while an installer is still running'
# Historical regression: successful installation plus missing process metadata
# must be re-probed before a second installer is attempted.
$script:ready=@{python=$true;node=$true;inno=$false}
function Install-BarqInno { $script:ready.inno=$true;throw 'exit code unavailable' }
$before=$script:fallbacks.Count
$records=Ensure-BarqBuildTools
Assert-Barq ($records[2].ready -and $script:fallbacks.Count -eq $before) 'installed compiler is detected before any fallback despite missing exit metadata'
$script:probeCount=0
function Find-BarqInno { $script:probeCount++;if($script:probeCount -ge 4){return 'delayed-compiler'} }
function Install-BarqInno { }
$records=Ensure-BarqBuildTools
Assert-Barq ($records[2].ready -and $script:probeCount -eq 4) 'post-install registration delay is re-probed within a bounded budget'
# Test download orchestration with stubbed network and authentication.
$script:downloads=0;$script:valid=$false
function Test-BarqDownload { return $script:valid }
function Get-BarqApp { return $null }
function Start-Sleep { }
function Invoke-WebRequest([string]$Uri,[string]$OutFile,[switch]$UseBasicParsing,[int]$TimeoutSec) {
    $script:downloads++
    if ($script:downloads -lt 2) { throw 'transient connection reset' }
    Set-Content -LiteralPath $OutFile -Value 'verified fixture'
    $script:valid=$true
}
$root=Join-Path ([IO.Path]::GetTempPath()) ('barq-bootstrap-test-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
try {
    $target=Join-Path $root 'python.exe'
    $file=Receive-BarqFile @('https://www.python.org/fixture.exe') $target '' 'Python Software Foundation'
    Assert-Barq ($script:downloads -eq 2 -and (Test-Path $file)) 'transient download retries then atomically promotes verified cache'
    $null=Receive-BarqFile @('https://www.python.org/fixture.exe') $target '' 'Python Software Foundation'
    Assert-Barq ($script:downloads -eq 2) 'verified cache avoids another download'
    $script:valid=$false;$script:downloads=0
    function Invoke-WebRequest { Set-Content -LiteralPath $target -Value 'unsigned fixture' }
    $rejected=$false
    try { $null=Receive-BarqFile @('https://www.python.org/fixture.exe') $target '' 'Python Software Foundation' } catch { $rejected=$true }
    Assert-Barq $rejected 'invalid download authenticity is never accepted'
    $rejected=$false
    try { $null=Receive-BarqFile @('http://invalid.example/file.exe') $target } catch { $rejected=$true }
    Assert-Barq $rejected 'plain HTTP is rejected'
    # Validate the real Node installation function's argument construction.
    ${function:Install-BarqNode}=$originalInstallNode
    $env:LOCALAPPDATA=$root
    function Receive-BarqFile([string[]]$Urls,[string]$Destination,[string]$Sha256) {
        Assert-Barq ($Urls.Count -eq 2 -and $Urls[0] -eq 'https://nodejs.org/dist/v22.23.4/node-v22.23.4-win-x64.zip' -and $Urls[1] -eq 'https://nodejs.org/download/release/v22.23.4/node-v22.23.4-win-x64.zip') 'Node fallback URLs are two complete official URLs'
        Assert-Barq ($Sha256.Length -eq 64) 'Node archive is pinned by SHA256'
        return $Destination
    }
    function Expand-BarqNode { }
    $script:PrereqCache=$root
    Install-BarqNode
} finally { $env:LOCALAPPDATA=$originalLocalAppData;Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host ('BARQ prerequisite behavior checks passed: '+$script:checks)
