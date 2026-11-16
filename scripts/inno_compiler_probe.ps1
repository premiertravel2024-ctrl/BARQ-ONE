# Functional Inno readiness, not PE FileMajorPart (official ISCC resources use 0).
function Test-BarqInnoCompiler([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return [pscustomobject]@{Ready=$false;Reason='Compiler file missing';Path=$Path} }
    # Cache only within THIS PowerShell process; re-probe after any root resource
    # changes. This avoids compiling six identical failures during bounded retries.
    $resources=@(Get-ChildItem -LiteralPath (Split-Path $Path -Parent) -File -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object { $_.Name+'|'+$_.Length+'|'+$_.LastWriteTimeUtc.Ticks }) -join ';'
    $key=$Path+'::'+$resources
    if (-not (Get-Variable -Name BarqInnoReadinessCache -Scope Global -ErrorAction SilentlyContinue)) { $global:BarqInnoReadinessCache=@{} }
    if ($global:BarqInnoReadinessCache.ContainsKey($key)) { return $global:BarqInnoReadinessCache[$key] }
    $cache=if($env:LOCALAPPDATA){Join-Path $env:LOCALAPPDATA 'Bq\deps\bootstrap'}else{Join-Path ([IO.Path]::GetTempPath()) 'barq-inno-probe'}
    $probe=Join-Path $cache ('inno-probe-'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $probe -Force
    $diagnostic=Join-Path $probe 'probe-result.json'
    $info=[ordered]@{Ready=$false;Reason='Probe not completed';Path=$Path;Version='';Diagnostic=$diagnostic}
    try {
        if (-not (Get-Command Invoke-BarqNativeProcess -CommandType Function -ErrorAction SilentlyContinue)) {
            . (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
        }
        $scriptFile=Join-Path $probe 'probe.iss'
        $payload=Join-Path $probe 'payload.txt';$output=Join-Path $probe 'output'
        Set-Content -LiteralPath $payload -Value 'BARQ compiler readiness test' -Encoding UTF8
        @"
#define ProbeName "BARQ Compiler Readiness"
[Setup]
AppName={#ProbeName}
AppVersion=1.0
DefaultDirName={tmp}\BARQ-Compiler-Probe
OutputDir=$output
OutputBaseFilename=barq-compiler-probe
PrivilegesRequired=lowest
Uninstallable=no
CreateUninstallRegKey=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
[Files]
Source: "$payload"; DestDir: "{app}"
[Code]
var DownloadPage: TDownloadWizardPage;
procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('BARQ', 'Readiness only', nil);
end;
"@ | Set-Content -LiteralPath $scriptFile -Encoding UTF8
        $out=Join-Path $probe 'stdout.log';$err=Join-Path $probe 'stderr.log'
        $result=Invoke-BarqNativeProcess $Path @(('"'+$scriptFile+'"')) $out $err 20
        if ($result.TimedOut) { throw 'Compiler probe timed out; no probe installer was executed' }
        if ($null -eq $result.ExitCode) { throw 'Compiler probe exit code unavailable' }
        $text=(@(Get-Content -LiteralPath $out -Raw -ErrorAction SilentlyContinue)+@(Get-Content -LiteralPath $err -Raw -ErrorAction SilentlyContinue)) -join "`n"
        if ($result.ExitCode -ne 0) { throw ('Compiler probe returned '+$result.ExitCode+'. '+$text.Substring(0,[Math]::Min(700,$text.Length))) }
        # ISCC itself is a versionless front-end; the ENGINE announces its real version.
        if ($text -notmatch '(?im)Compiler engine version:\s*(?:Inno Setup\s+)?(?<Version>6\.\d+(?:\.\d+){0,2})(?![\d.])') {
            throw 'Compiler did not identify a compatible Inno Setup 6 engine'
        }
        $info.Version=$matches.Version
        $exe=Join-Path $output 'barq-compiler-probe.exe'
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Compiler exited successfully without the probe executable' }
        $bytes=[IO.File]::ReadAllBytes($exe)
        if ($bytes.Length -lt 1024 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) { throw 'Compiler probe output was not a valid-sized Windows executable' }
        # This generated executable is NEVER launched. Prove compiler, preprocessor,
        # runtime templates and LZMA2 resources work together, then remove the output.
        $info.Ready=$true;$info.Reason='Inno engine '+$info.Version+' successfully compiled the readiness script'
        Remove-Item -LiteralPath $output -Recurse -Force
    } catch { $info.Reason=$_.Exception.Message }
    [pscustomobject]$info | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $diagnostic -Encoding UTF8
    $proof=[pscustomobject]$info
    $global:BarqInnoReadinessCache[$key]=$proof
    return $proof
}
