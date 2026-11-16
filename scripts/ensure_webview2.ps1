#requires -Version 5.1
param([switch]$CheckOnly,[switch]$FunctionsOnly)
function Find-BarqWebView2 {
    $client='{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach ($root in @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\','HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\','HKCU:\Software\Microsoft\EdgeUpdate\Clients\')) {
        $value=Get-ItemProperty -LiteralPath ($root+$client) -Name pv -ErrorAction SilentlyContinue
        if ($value -and $value.pv) {
            try { if ([version]$value.pv -gt [version]'0.0.0.0') { return [string]$value.pv } } catch { }
        }
    }
    return $null
}
function Ensure-BarqWebView2([switch]$CheckOnly) {
    $version=Find-BarqWebView2
    if ($version) { Write-BarqPrereq ('WebView2 runtime present: '+$version);return }
    if ($CheckOnly) { throw 'Microsoft WebView2 runtime is missing' }
    $file=Receive-BarqFile @('https://go.microsoft.com/fwlink/p/?LinkId=2124703') (Join-Path $script:PrereqCache 'MicrosoftEdgeWebview2Setup.exe') '' 'Microsoft Corporation'
    Invoke-BarqInstaller $file @('/silent','/install') 'WebView2' 900
    if (-not (Find-BarqWebView2)) { throw ('WebView2 installation was not verified; see '+$script:PrereqCache) }
    Write-BarqPrereq 'WebView2 runtime installed and verified'
}
if (-not $FunctionsOnly) {
    $ErrorActionPreference='Stop'
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'WebView2 requires Windows' }
    $webViewCheckOnly=$CheckOnly
    . (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $script:PrereqCache=Join-Path $env:LOCALAPPDATA 'Bq\deps\bootstrap'
    $null=New-Item -ItemType Directory -Path $script:PrereqCache -Force
    $script:PrereqLog=Join-Path $script:PrereqCache 'build-prerequisites.log'
    Ensure-BarqWebView2 -CheckOnly:$webViewCheckOnly
}
