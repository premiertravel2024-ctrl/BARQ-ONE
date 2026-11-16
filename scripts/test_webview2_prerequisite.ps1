param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
. (Join-Path $PSScriptRoot 'ensure_webview2.ps1') -FunctionsOnly
$script:checks=0;$script:version='140.0.0.1';$script:installs=0
function Assert-WebView([bool]$Value,[string]$Name) {
    if (-not $Value) { throw ('FAIL: '+$Name) }
    $script:checks++;Write-Host ('PASS: '+$Name)
}
function Find-BarqWebView2 { return $script:version }
function Receive-BarqFile([string[]]$Urls,[string]$Destination,[string]$Sha256,[string]$Publisher) {
    if ($Urls[0] -ne 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -or $Publisher -ne 'Microsoft Corporation') { throw 'Wrong runtime source or publisher' }
    return 'verified-microsoft-installer.exe'
}
function Invoke-BarqInstaller { $script:installs++;$script:version='140.0.0.1' }
Ensure-BarqWebView2
Assert-WebView ($script:installs -eq 0) 'existing runtime is reused'
$script:version=$null;$rejected=$false
try { Ensure-BarqWebView2 -CheckOnly } catch { $rejected=$true }
Assert-WebView ($rejected -and $script:installs -eq 0) 'check-only reports missing without installing'
$script:PrereqCache=[IO.Path]::GetTempPath()
Ensure-BarqWebView2
Assert-WebView ($script:installs -eq 1 -and $script:version) 'missing runtime installed from Microsoft and re-probed'
$script:version=$null
function Invoke-BarqInstaller { }
$rejected=$false
try { Ensure-BarqWebView2 } catch { $rejected=$true }
Assert-WebView $rejected 'success exit alone cannot prove runtime readiness'
Write-Host ('BARQ WebView2 behavior checks passed: '+$script:checks)
