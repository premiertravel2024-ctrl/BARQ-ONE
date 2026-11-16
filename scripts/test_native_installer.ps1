# Real child processes, pipe redirection, exit codes, quoting and timeout behavior.
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
$root=Join-Path ([IO.Path]::GetTempPath()) ('barq native installer '+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$script:PrereqCache=$root;$script:checks=0
function Assert-Native([bool]$Value,[string]$Name) {
    if (-not $Value) { throw ('FAIL: '+$Name) }
    $script:checks++;Write-Host ('PASS: '+$Name)
}
$fixture=Join-Path $root 'fixture with spaces.ps1'
@'
param([int]$Code=0,[int]$Size=8,[int]$Delay=0,[string]$Marker='fixture')
[Console]::Out.WriteLine($Marker)
[Console]::Out.Write((New-Object string ([char]'o'),$Size))
[Console]::Error.WriteLine('native-error-marker')
[Console]::Error.Write((New-Object string ([char]'e'),$Size))
if ($Delay) { Start-Sleep -Seconds $Delay }
exit $Code
'@ | Set-Content -LiteralPath $fixture -Encoding UTF8
# PSHOME works in containers where /proc is in a different PID namespace.
$nativeShell=@('pwsh.exe','powershell.exe','pwsh') | ForEach-Object { Join-Path $PSHOME $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $nativeShell) { throw 'Current PowerShell executable not found in PSHOME' }
$base=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$fixture+'"'))
$originalNative=${function:Invoke-BarqNativeProcess}
try {
    # The fixture path and its marker both contain spaces; a literal & is DATA.
    Invoke-BarqInstaller $nativeShell ($base+@('-Marker','"quoted value & literal"')) 'real-zero' 10
    $meta=Get-Content -LiteralPath (Join-Path $root 'real-zero-result.json') -Raw | ConvertFrom-Json
    Assert-Native ($meta.ExitCode -eq 0 -and -not $meta.TimedOut) 'real redirected process reports numeric exit zero'
    Assert-Native ((Get-Content (Join-Path $root 'real-zero-stdout.log') -Raw).Contains('quoted value & literal')) 'quoted path and argument with spaces are preserved without shell execution'
    $failed=$false
    try { Invoke-BarqInstaller $nativeShell ($base+@('-Code','37')) 'real-nonzero' 10 } catch { $failed=$_.Exception.Message -match 'returned 37' -and $_.Exception.Message -match 'native-error-marker' }
    Assert-Native $failed 'real exit failure includes actual code and useful stderr'
    Invoke-BarqInstaller $nativeShell ($base+@('-Size','300000')) 'real-full-pipes' 10
    Assert-Native ((Get-Item (Join-Path $root 'real-full-pipes-stdout.log')).Length -ge 300000 -and (Get-Item (Join-Path $root 'real-full-pipes-stderr.log')).Length -ge 300000) 'stdout and stderr larger than pipe buffers do not deadlock'
    Invoke-BarqInstaller $nativeShell ($base+@('-Size','2400000')) 'real-log-cap' 10
    Assert-Native ((Get-Item (Join-Path $root 'real-log-cap-stdout.log')).Length -eq 2097152 -and (Get-Item (Join-Path $root 'real-log-cap-stderr.log')).Length -eq 2097152) 'diagnostic cap still drains excess output without deadlock'
    for ($i=0;$i -lt 4;$i++) { Invoke-BarqInstaller $nativeShell $base ('fast-'+$i) 10 }
    Assert-Native $true 'four rapid successful exits never become blank-code failures'
    $out=Join-Path $root 'timeout-out.log';$err=Join-Path $root 'timeout-err.log'
    $result=Invoke-BarqNativeProcess $nativeShell ($base+@('-Delay','3')) $out $err 1
    Assert-Native ($result.TimedOut -and $null -eq $result.ExitCode) 'timeout is explicit and never reported as success'
    Assert-Native $result.RunningAtReturn 'timeout leaves the already-running installer alive'
    Start-Sleep -Seconds 4 # fixture finishes naturally; the test never kills it
    # Inject the historical null metadata and Windows reboot-success result.
    function Invoke-BarqNativeProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=$null;ProcessId=1;LogsComplete=$true} }
    $failed=$false
    try { Invoke-BarqInstaller 'fixture' @() 'null-result' } catch { $failed=$_.Exception.Message -match 'exit code unavailable' }
    Assert-Native $failed 'missing exit metadata has a clear message instead of a blank code'
    function Invoke-BarqNativeProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=3010;ProcessId=1;LogsComplete=$true} }
    Invoke-BarqInstaller 'fixture' @() 'reboot-success'
    Assert-Native $true 'Windows success requiring restart is accepted without rebooting'
} finally {
    ${function:Invoke-BarqNativeProcess}=$originalNative
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host ('BARQ native installer checks passed: '+$script:checks)
