# Locate and FUNCTIONALLY verify Inno Setup 6. FileMajorPart may legitimately be 0.
param([scriptblock]$CompilerProbe)
$ErrorActionPreference='Stop'
if (-not $CompilerProbe) {
    . (Join-Path $PSScriptRoot 'inno_compiler_probe.ps1')
    $CompilerProbe={param($CompilerPath) Test-BarqInnoCompiler $CompilerPath}
}
$candidates=@()
if ($env:INNO_SETUP_COMPILER) { $candidates+=$env:INNO_SETUP_COMPILER }
if ($env:LOCALAPPDATA) { $candidates+=(Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe') }
if ($env:ProgramFiles) { $candidates+=(Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe') }
if (${env:ProgramFiles(x86)}) { $candidates+=(Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe') }
$commands=@(Get-Command ISCC.exe -CommandType Application -All -ErrorAction SilentlyContinue)
foreach ($command in $commands) { if ($command.Source) { $candidates+=$command.Source } }
$keys=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1')
foreach ($key in $keys) {
    try {
        $item=Get-ItemProperty -LiteralPath $key -ErrorAction Stop
        $location=$item.PSObject.Properties['InstallLocation'];$uninstall=$item.PSObject.Properties['UninstallString']
        $dir=if ($location) { [string]$location.Value } else { '' }
        if (-not $dir -and $uninstall -and [string]$uninstall.Value -match '^\s*"([^"]+)"') { $dir=Split-Path $matches[1] -Parent }
        if ($dir) { $candidates+=(Join-Path $dir 'ISCC.exe') }
    } catch { }
}
$failures=@()
foreach ($path in ($candidates | Select-Object -Unique)) {
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    try {
        $proof=& $CompilerProbe $path
        if ($proof.Ready) { Write-Output $path;return }
        $failures+=($path+': '+$proof.Reason+'; diagnostic: '+$proof.Diagnostic)
    } catch { $failures+=($path+': '+$_.Exception.Message) }
}
if ($failures.Count) { throw ('Inno Setup 6 was found but its compiler failed verification: '+($failures -join ' | ')) }
throw ('Inno Setup 6 ISCC.exe not found. Checked: '+(($candidates|Select-Object -Unique) -join ', '))
