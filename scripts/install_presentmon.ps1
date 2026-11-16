#requires -Version 5.1
param([switch]$Stage)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_prerequisites.ps1') -FunctionsOnly
[Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$script:PrereqCache=Join-Path $env:LOCALAPPDATA 'Bq\deps\bootstrap'
$null=New-Item -ItemType Directory -Path $script:PrereqCache -Force
$script:PrereqLog=Join-Path $script:PrereqCache 'build-prerequisites.log'
# A bundled, verified executable already works without another network transfer.
$bundled=Join-Path (Split-Path $PSScriptRoot -Parent) '_internal\tools\presentmon\PresentMon-2.6.0-x64.exe'
if (-not $Stage -and (Test-BarqDownload $bundled 'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af')) { Write-BarqPrereq 'Bundled FPS tool verified';exit 0 }
$staged=Join-Path (Split-Path $PSScriptRoot -Parent) 'tools\presentmon\PresentMon-2.6.0-x64.exe'
if ($Stage -and (Test-BarqDownload $staged 'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af')) { Write-BarqPrereq 'Source-bundled FPS tool verified';exit 0 }
$file=Receive-BarqFile @('https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe') (Join-Path $script:PrereqCache 'PresentMon-2.6.0-x64.exe') 'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af' -TimeoutSeconds 30 -Attempts 1
$target=Join-Path $env:LOCALAPPDATA 'Bq\tools\presentmon'
if ($Stage) { $target=Join-Path (Split-Path $PSScriptRoot -Parent) 'tools\presentmon' }
$null=New-Item -ItemType Directory -Path $target -Force
Copy-Item -LiteralPath $file -Destination (Join-Path $target 'PresentMon-2.6.0-x64.exe') -Force
 $license=Join-Path (Split-Path $PSScriptRoot -Parent) 'tools\presentmon\LICENSE.txt'
if ((Test-Path -LiteralPath $license) -and ((Split-Path $license -Parent) -ne $target)) { Copy-Item -LiteralPath $license -Destination (Join-Path $target 'LICENSE.txt') -Force }
Write-BarqPrereq ('Verified PresentMon ready in '+$target+'; capture permissions are tested at measurement time.')
