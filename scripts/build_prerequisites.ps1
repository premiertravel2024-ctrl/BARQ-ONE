#requires -Version 5.1
[CmdletBinding()]
param([switch]$CheckOnly,[switch]$FunctionsOnly)
# Bootstrap uses Windows PowerShell only: Python, npm and winget may all be absent.
# No security-policy changes, machine PATH edits or forced machine restart.
function Write-BarqPrereq([string]$Message) {
    Write-Host ('[BARQ SETUP] '+$Message)
    if ($script:PrereqLog) { Add-Content -LiteralPath $script:PrereqLog -Value ((Get-Date -Format o)+' '+$Message) -Encoding UTF8 }
}
function Add-BarqProcessPath([string]$Folder) {
    if ($Folder -and (Test-Path -LiteralPath $Folder -PathType Container)) {
        $separator=[IO.Path]::PathSeparator
        $env:PATH=$Folder+$separator+$env:PATH
    }
}
function Get-BarqApp([string]$Name,[string[]]$Candidates=@()) {
    foreach ($path in $Candidates) { if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) { return $path } }
    $command=Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}
function Find-BarqPython {
    $candidates=@(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'),
        (Join-Path $env:WINDIR 'py.exe')
    )
    $onPath=Get-BarqApp 'py.exe'
    if ($onPath) { $candidates=@($onPath)+$candidates }
    foreach ($launcher in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { continue }
        try {
            $output=& $launcher -3.11 (Join-Path $PSScriptRoot 'verify_python_build.py') 2>&1
            if ($LASTEXITCODE -eq 0) { Add-BarqProcessPath (Split-Path $launcher -Parent);return $launcher }
        } catch { }
    }
    return $null
}
function Find-BarqNode {
    $private=Join-Path $env:LOCALAPPDATA 'Bq\tools\node-v22.23.4-win-x64'
    foreach ($node in @((Join-Path $private 'node.exe'),(Get-BarqApp 'node.exe'))) {
        if (-not $node -or -not (Test-Path -LiteralPath $node -PathType Leaf)) { continue }
        $folder=Split-Path $node -Parent
        if (-not (Test-Path -LiteralPath (Join-Path $folder 'npm.cmd'))) { continue }
        try {
            $version=& $node --version 2>&1
            if ($LASTEXITCODE -ne 0 -or [string]$version -notmatch '^v(2[0246])\.') { continue }
            $arch=& $node -p 'process.arch' 2>&1
            if ($LASTEXITCODE -ne 0 -or [string]$arch -ne 'x64') { continue }
            $npm=& (Join-Path $folder 'npm.cmd') --version 2>&1
            if ($LASTEXITCODE -eq 0) { Add-BarqProcessPath $folder;return $node }
        } catch { }
    }
    return $null
}
function Find-BarqInno {
    try {
        $path=& (Join-Path $PSScriptRoot 'find_inno.ps1')
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            $env:INNO_SETUP_COMPILER=$path;return $path
        }
    } catch {
        $message=$_.Exception.Message
        if ($script:InnoLastProbeError -ne $message) { Write-BarqPrereq ('Inno compiler detection: '+$message) }
        $script:InnoLastProbeError=$message
    }
    return $null
}
function Test-BarqDownload([string]$Path,[string]$Sha256='',[string]$Publisher='') {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -lt 100) { return $false }
    if ($Sha256 -and (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Sha256) { return $false }
    if ($Publisher) {
        $signature=Get-AuthenticodeSignature -LiteralPath $Path
        if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch $Publisher) { return $false }
    }
    return $true
}
function Receive-BarqFile([string[]]$Urls,[string]$Destination,[string]$Sha256='',[string]$Publisher='',[int]$TimeoutSeconds=900,[int]$Attempts=3) {
    if (Test-BarqDownload $Destination $Sha256 $Publisher) { Write-BarqPrereq ('Using verified cached '+(Split-Path $Destination -Leaf));return $Destination }
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force }
    $partial=$Destination+'.partial'+[IO.Path]::GetExtension($Destination)
    for ($attempt=1;$attempt -le $Attempts;$attempt++) {
        foreach ($url in $Urls) {
            if (Test-BarqDownload $partial $Sha256 $Publisher) { Move-Item -LiteralPath $partial -Destination $Destination -Force;return $Destination }
            if ($url -notmatch '^https://') { throw 'Only official HTTPS downloads are accepted' }
            Write-BarqPrereq ('Downloading '+(Split-Path $Destination -Leaf)+' (attempt '+$attempt+'/'+$Attempts+')')
            try {
                $curl=Get-BarqApp 'curl.exe'
                if ($curl) {
                    & $curl --fail --location --retry 2 --connect-timeout 20 --max-time $TimeoutSeconds --retry-max-time $TimeoutSeconds --continue-at - --output $partial $url
                    if ($LASTEXITCODE -ne 0) {
                        $downloadExit=$LASTEXITCODE
                        if ($downloadExit -in @(22,33,36)) { Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue }
                        throw ('Download exit '+$downloadExit)
                    }
                } else {
                    Invoke-WebRequest -Uri $url -OutFile $partial -UseBasicParsing -TimeoutSec ([Math]::Min(300,$TimeoutSeconds))
                }
                if (-not (Test-BarqDownload $partial $Sha256 $Publisher)) {
                    Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                    throw 'Download authenticity/integrity check failed; the file was not executed'
                }
                Move-Item -LiteralPath $partial -Destination $Destination -Force
                return $Destination
            } catch { Write-BarqPrereq $_.Exception.Message }
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds ([Math]::Pow(2,$attempt)) }
    }
    throw ('Unable to obtain a verified '+(Split-Path $Destination -Leaf)+'. Rerun to resume; downloads remain in '+(Split-Path $Destination -Parent))
}
# Start-Process's returned Process object can lose ExitCode on Windows when
# standard streams are redirected (#5421/#20400). Own the Process from creation.
function Initialize-BarqNativeProcess {
    if ('Barq.PrerequisiteProcess' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
namespace Barq {
    public sealed class PrerequisiteResult {
        public int? ExitCode;
        public int ProcessId;
        public bool TimedOut;
        public bool LogsComplete;
        public bool RunningAtReturn;
    }
    public static class PrerequisiteProcess {
        private static void Pump(Stream input, string path) {
            // Drain BOTH pipes concurrently, even when the diagnostic cap is reached.
            // No PowerShell callback on a thread-pool thread; no runspace deadlocks.
            using (var output = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite)) {
                byte[] buffer = new byte[8192]; int read; long written = 0;
                while ((read = input.Read(buffer, 0, buffer.Length)) > 0) {
                    int keep = (int)Math.Max(0, Math.Min(read, 2097152L - written));
                    if (keep > 0) { output.Write(buffer, 0, keep); output.Flush(); written += keep; }
                }
            }
        }
        public static PrerequisiteResult Run(string file, string args, string stdout, string stderr, int timeoutMs) {
            var process = new Process();
            process.StartInfo = new ProcessStartInfo(file, args);
            process.StartInfo.UseShellExecute = false;
            process.StartInfo.CreateNoWindow = true;
            process.StartInfo.RedirectStandardOutput = true;
            process.StartInfo.RedirectStandardError = true;
            if (!process.Start()) { process.Dispose(); throw new InvalidOperationException("Native installer did not start"); }
            int pid = process.Id;
            var output = Task.Run(() => Pump(process.StandardOutput.BaseStream, stdout));
            var error = Task.Run(() => Pump(process.StandardError.BaseStream, stderr));
            var drains = Task.WhenAll(output, error);
            // Captured process remains alive until both streams finish. Never kill a
            // still-running installer merely because our time budget expired.
            if (!process.WaitForExit(timeoutMs)) {
                bool stillRunning = !process.HasExited;
                drains.ContinueWith(task => process.Dispose());
                return new PrerequisiteResult { TimedOut = true, ProcessId = pid, RunningAtReturn = stillRunning };
            }
            int exitCode = process.ExitCode; // Native int from OUR original handle.
            bool drained = false;
            try { drained = drains.Wait(3000); } catch (AggregateException) { }
            if (drained) process.Dispose();
            else drains.ContinueWith(task => process.Dispose());
            return new PrerequisiteResult { ExitCode = exitCode, ProcessId = pid, LogsComplete = drained };
        }
    }
}
'@
}
function Invoke-BarqNativeProcess([string]$File,[string[]]$Arguments,[string]$Stdout,[string]$Stderr,[int]$TimeoutSeconds) {
    Initialize-BarqNativeProcess
    # Call sites supply their fixed, already quoted native arguments, including
    # /DIR="path with spaces". No shell, command concatenation or user code.
    return [Barq.PrerequisiteProcess]::Run($File,($Arguments -join ' '),$Stdout,$Stderr,($TimeoutSeconds*1000))
}
function Invoke-BarqInstaller([string]$File,[string[]]$Arguments,[string]$Name,[int]$TimeoutSeconds=900) {
    Write-BarqPrereq ('Installing '+$Name)
    $out=Join-Path $script:PrereqCache ($Name+'-stdout.log')
    $err=Join-Path $script:PrereqCache ($Name+'-stderr.log')
    $result=Invoke-BarqNativeProcess $File $Arguments $out $err $TimeoutSeconds
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $script:PrereqCache ($Name+'-result.json')) -Encoding UTF8
    if ($result.TimedOut) {
        throw ($Name+' installer is still running after its time budget (PID '+$result.ProcessId+'). No second installer was started. See '+$script:PrereqCache)
    }
    if ($null -eq $result.ExitCode) { throw ($Name+' exit code unavailable; installation was not assumed successful. See '+$script:PrereqCache) }
    $exitCode=[int]$result.ExitCode
    Write-BarqPrereq ($Name+' finished with exit code '+$exitCode)
    if ($exitCode -notin @(0,3010)) {
        $detail=''
        if (Test-Path -LiteralPath $err) { $detail=(@(Get-Content -LiteralPath $err -Tail 6 -ErrorAction SilentlyContinue) -join ' ') }
        if ($detail.Length -gt 500) { $detail=$detail.Substring(0,500) }
        throw ($Name+' installer returned '+$exitCode+'. '+$detail+' See '+$script:PrereqCache)
    }
}
function Wait-BarqBuildTool([string]$Probe) {
    for ($attempt=0;$attempt -lt 6;$attempt++) {
        $found=& $Probe
        if ($found) { return $found }
        if ($attempt -lt 5) { Start-Sleep -Milliseconds 500 }
    }
    return $null
}
function Invoke-BarqWinget([string]$Id) {
    $winget=Get-BarqApp 'winget.exe'
    if (-not $winget) { throw 'WinGet fallback unavailable' }
    Invoke-BarqInstaller $winget @('install','--id',$Id,'--exact','--source','winget','--scope','user','--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements') ('winget-'+$Id) 900
    $machine=[Environment]::GetEnvironmentVariable('Path','Machine')
    $user=[Environment]::GetEnvironmentVariable('Path','User')
    $env:PATH=$env:PATH+';'+$user+';'+$machine
}
function Install-BarqPython {
    $path=Receive-BarqFile @('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe') (Join-Path $script:PrereqCache 'python-3.11.9-amd64.exe') '' 'Python Software Foundation'
    # Last PSF 3.11 Windows installer; project requires CPython 3.11 x64.
    $target=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'
    $nativeLog=Join-Path $script:PrereqCache 'python-install.log'
    Invoke-BarqInstaller $path @('/quiet','InstallAllUsers=0','Include_launcher=1','InstallLauncherAllUsers=0','Include_pip=1','Include_test=0','PrependPath=1',('TargetDir="'+$target+'"'),'/log',('"'+$nativeLog+'"')) 'Python311'
    Add-BarqProcessPath (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher')
    Add-BarqProcessPath $target
}
function Expand-BarqNode([string]$Archive,[string]$Target) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name=$entry.FullName.Replace('\','/')
            if ($name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)|:') { throw 'Unsafe Node archive entry' }
        }
    } finally { $zip.Dispose() }
    $stage=Join-Path (Split-Path $Target -Parent) ('node-stage-'+[guid]::NewGuid().ToString('N'))
    try {
        $null=New-Item -ItemType Directory -Path $stage -Force
        Expand-Archive -LiteralPath $Archive -DestinationPath $stage
        $source=Join-Path $stage 'node-v22.23.4-win-x64'
        if (-not (Test-Path -LiteralPath (Join-Path $source 'node.exe')) -or -not (Test-Path -LiteralPath (Join-Path $source 'npm.cmd'))) { throw 'Incomplete official Node archive' }
        if (-not (Test-BarqDownload (Join-Path $source 'node.exe') '' 'OpenJS|Node.js Foundation')) { throw 'Node executable signature invalid' }
        if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
        Move-Item -LiteralPath $source -Destination $Target
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}
function Install-BarqNode {
    $name='node-v22.23.4-win-x64.zip'
    $hash='cbc74b5e0982c9dbb41525fd8fb5dcd32fbee237863f7829072f4639a1ce5f20'
    $zip=Receive-BarqFile @(('https://nodejs.org/dist/v22.23.4/'+$name),('https://nodejs.org/download/release/v22.23.4/'+$name)) (Join-Path $script:PrereqCache $name) $hash
    $parent=Join-Path $env:LOCALAPPDATA 'Bq\tools'
    $null=New-Item -ItemType Directory -Path $parent -Force
    $target=Join-Path $parent 'node-v22.23.4-win-x64'
    Expand-BarqNode $zip $target
    Add-BarqProcessPath $target
}
function Install-BarqInno {
    $path=Receive-BarqFile @('https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe','https://files.jrsoftware.org/is/6/innosetup-6.7.4.exe') (Join-Path $script:PrereqCache 'innosetup-6.7.4.exe') '' 'Pyrsys B\.V\.'
    $target=Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6'
    Invoke-BarqInstaller $path @('/SP-','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',('/DIR="'+$target+'"'),('/LOG="'+(Join-Path $script:PrereqCache 'inno-install.log')+'"')) 'InnoSetup6'
    $env:INNO_SETUP_COMPILER=Join-Path $target 'ISCC.exe'
}
function Ensure-BarqBuildTools([switch]$CheckOnly) {
    $packages=@(
        @{Name='Python 3.11 x64 + launcher';Probe='Find-BarqPython';Install='Install-BarqPython';Winget='Python.Python.3.11'},
        @{Name='Node.js x64 + npm';Probe='Find-BarqNode';Install='Install-BarqNode';Winget='OpenJS.NodeJS.LTS'},
        @{Name='Inno Setup 6';Probe='Find-BarqInno';Install='Install-BarqInno';Winget='JRSoftware.InnoSetup'}
    )
    $records=@()
    foreach ($package in $packages) {
        Write-BarqPrereq ('Checking '+$package.Name)
        $found=& $package.Probe
        if (-not $found -and -not $CheckOnly) {
            try { & $package.Install } catch {
                Write-BarqPrereq ($package.Name+': '+$_.Exception.Message)
                if ($_.Exception.Message -match 'still running') { throw }
                $found=Wait-BarqBuildTool $package.Probe
                if (-not $found) {
                    Write-BarqPrereq ('Trying official WinGet catalog fallback for '+$package.Name)
                    Invoke-BarqWinget $package.Winget
                } else { Write-BarqPrereq ($package.Name+' is already installed and verified; fallback skipped') }
            }
            $found=Wait-BarqBuildTool $package.Probe
            if (-not $found) {
                $detail=if($package.Probe -eq 'Find-BarqInno'){$script:InnoLastProbeError}else{''}
                throw ($package.Name+' is not usable after installation. '+$detail+' No build was started. See '+$script:PrereqLog)
            }
        }
        $records+=@{tool=$package.Name;ready=[bool]$found;path=$found}
    }
    return ,$records
}
$script:InnoLastProbeError=''
$script:PrereqLog=$null
$script:PrereqCache=$null
if (-not $FunctionsOnly) {
    $ErrorActionPreference='Stop'
    if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'BARQ build requires Windows 10/11 x64.' }
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $script:PrereqCache=Join-Path $env:LOCALAPPDATA 'Bq\deps\bootstrap'
    $null=New-Item -ItemType Directory -Path $script:PrereqCache -Force
    $script:PrereqLog=Join-Path $script:PrereqCache 'build-prerequisites.log'
    $records=Ensure-BarqBuildTools -CheckOnly:$CheckOnly
    $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $script:PrereqCache 'build-tools.json') -Encoding UTF8
    if (@($records | Where-Object { -not $_.ready }).Count) { throw ('Build tools missing; see '+$script:PrereqLog) }
    Write-BarqPrereq 'All required build programs are verified; continuing the existing build/tests.'
}
