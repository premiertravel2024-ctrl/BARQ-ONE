param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
. (Join-Path $PSScriptRoot 'inno_compiler_probe.ps1')
$root=Join-Path ([IO.Path]::GetTempPath()) ('barq-inno-functional-'+[guid]::NewGuid().ToString('N'))
$compilerDir=Join-Path $root 'compiler';$null=New-Item -ItemType Directory -Path $compilerDir -Force
$compiler=Join-Path $compilerDir 'ISCC.exe';Set-Content -LiteralPath $compiler -Value 'fixture without a PE version resource'
$fixture=Join-Path $compilerDir 'compiler-fixture.ps1'
@'
param([string]$ScriptFile,[string]$Mode)
if ($Mode -eq 'missing-dll') { [Console]::Error.WriteLine('ISCmplr.dll could not be loaded');exit 2 }
$version=if($Mode -eq 'seven'){'7.1.1'}else{'6.7.4'}
[Console]::WriteLine('Compiler engine version: Inno Setup '+$version)
$text=Get-Content -LiteralPath $ScriptFile -Raw
$output=[regex]::Match($text,'(?m)^OutputDir=(.+)$').Groups[1].Value.Trim()
if ($Mode -ne 'empty') {
 $null=New-Item -ItemType Directory -Path $output -Force
 $bytes=New-Object byte[] 2048
 if ($Mode -ne 'bad-output') { $bytes[0]=77;$bytes[1]=90 }
 [IO.File]::WriteAllBytes((Join-Path $output 'barq-compiler-probe.exe'),$bytes)
}
exit 0
'@ | Set-Content -LiteralPath $fixture -Encoding UTF8
$native=@('pwsh.exe','powershell.exe','pwsh')|ForEach-Object{Join-Path $PSHOME $_}|Where-Object{Test-Path -LiteralPath $_}|Select-Object -First 1
$originalNative=${function:Invoke-BarqNativeProcess};$oldLocal=$env:LOCALAPPDATA;$oldCompiler=$env:INNO_SETUP_COMPILER
$global:BarqInnoFixtureMode='six';$global:BarqInnoFixtureInvoked=0;$script:checks=0
function Assert-Probe([bool]$Value,[string]$Name) { if(-not $Value){throw ('FAIL: '+$Name)};$script:checks++;Write-Host ('PASS: '+$Name) }
function Invoke-BarqNativeProcess([string]$File,[string[]]$Arguments,[string]$Stdout,[string]$Stderr,[int]$TimeoutSeconds) {
 $global:BarqInnoFixtureInvoked++
 $argsForFixture=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$fixture+'"'),'-ScriptFile',$Arguments[0],'-Mode',$global:BarqInnoFixtureMode)
 return & $originalNative $native $argsForFixture $Stdout $Stderr $TimeoutSeconds
}
try {
 $env:LOCALAPPDATA=Join-Path $root 'profile';$env:INNO_SETUP_COMPILER=$compiler
 Assert-Probe (([Diagnostics.FileVersionInfo]::GetVersionInfo($compiler)).FileMajorPart -eq 0) 'fixture reproduces zero PE FileMajorPart'
 $proof=Test-BarqInnoCompiler $compiler
 Assert-Probe ($proof.Ready -and $proof.Version -eq '6.7.4') 'real child compilation protocol accepts engine 6 despite zero PE metadata'
 Assert-Probe ((Test-Path $proof.Diagnostic) -and -not (Test-Path (Join-Path (Split-Path $proof.Diagnostic -Parent) 'output'))) 'diagnostic kept and successful probe executable removed without running it'
 $again=Test-BarqInnoCompiler $compiler
 Assert-Probe ($again.Ready -and $global:BarqInnoFixtureInvoked -eq 1) 'unchanged compiler resources reuse the verified in-process proof'
 $global:BarqInnoFixtureMode='seven';Set-Content $compiler -Value 'changed resources for seven'
 $proof=Test-BarqInnoCompiler $compiler
 Assert-Probe (-not $proof.Ready -and $proof.Reason -match 'compatible Inno Setup 6') 'resource changes invalidate proof and engine 7 is rejected'
 $global:BarqInnoFixtureMode='missing-dll';Set-Content $compiler -Value 'changed resources for missing dll'
 $proof=Test-BarqInnoCompiler $compiler
 Assert-Probe (-not $proof.Ready -and $proof.Reason -match 'returned 2' -and $proof.Reason -match 'ISCmplr.dll') 'missing compiler engine keeps actual error code and diagnostic'
 $global:BarqInnoFixtureMode='empty';Set-Content $compiler -Value 'changed resources for no output'
 $proof=Test-BarqInnoCompiler $compiler
 Assert-Probe (-not $proof.Ready -and $proof.Reason -match 'without the probe executable') 'exit zero alone is not proof of a usable compiler'
 $global:BarqInnoFixtureMode='bad-output';Set-Content $compiler -Value 'changed resources for malformed output'
 $proof=Test-BarqInnoCompiler $compiler
 Assert-Probe (-not $proof.Ready -and $proof.Reason -match 'not a valid-sized') 'malformed generated output is rejected'
 $global:BarqInnoFixtureMode='six';Set-Content $compiler -Value 'repaired resources for six'
 $found=& (Join-Path $PSScriptRoot 'find_inno.ps1')
 Assert-Probe ($found -eq $compiler) 'discovery uses functional proof rather than zero PE file version'
} finally {
 $env:LOCALAPPDATA=$oldLocal;$env:INNO_SETUP_COMPILER=$oldCompiler
 ${function:Invoke-BarqNativeProcess}=$originalNative
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
 Remove-Variable -Name BarqInnoReadinessCache,BarqInnoFixtureMode,BarqInnoFixtureInvoked -Scope Global -ErrorAction SilentlyContinue
}
Write-Host ('BARQ Inno functional checks passed: '+$script:checks)
