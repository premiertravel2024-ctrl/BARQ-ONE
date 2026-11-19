[CmdletBinding(DefaultParameterSetName='Build')]
param(
    [Parameter(ParameterSetName='BuildAndPublish')][switch]$Publish,
    [Parameter(ParameterSetName='PublishOnly')][switch]$PublishOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Repo = 'premiertravel2024-ctrl/BARQ-ONE-Updates'
$Origin = "https://github.com/$Repo"
$ChannelFile = Join-Path $Root 'assets\update-channel.json'
$PreviousChannel = $null
$ChannelChanged = $false
$PreviousOrigin = $env:BARQ_UPDATE_ORIGIN

function Assert-Exit([string]$Step, [int]$Code) {
    if ($Code -ne 0) { throw "$Step failed (exit $Code)." }
}

Push-Location $Root
try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'This build requires Windows x64.'
    }
    $Version = & py -3.11 -c 'from core.version import VERSION; print(VERSION)'
    Assert-Exit 'Read BARQ version' $LASTEXITCODE
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid BARQ version.' }
    $Tag = "v$Version"
    $Installer = "release/BARQ_Setup_$Version.exe"
    $ProofPath = 'release/local-update-channel.json'
    $env:BARQ_UPDATE_ORIGIN = $Origin
    $PublicKey = $env:BARQ_UPDATE_PUBLIC_KEY

    if ($Publish -or $PublishOnly) {
        if (!$PublicKey -or !$env:BARQ_UPDATE_PRIVATE_KEY) {
            throw 'Set the existing BARQ update public and private keys in this PowerShell session.'
        }
        & gh auth status --hostname github.com
        Assert-Exit 'GitHub authentication' $LASTEXITCODE
    }

    if (!$PublishOnly) {
        if ($PublicKey) {
            if ([Convert]::FromBase64String($PublicKey).Length -ne 32) { throw 'Invalid BARQ public key.' }
            if (Test-Path -LiteralPath $ChannelFile) { $PreviousChannel = [IO.File]::ReadAllBytes($ChannelFile) }
            $ChannelChanged = $true
            $Config = @{origin=$Origin; public_key=$PublicKey} | ConvertTo-Json -Compress
            [IO.File]::WriteAllText($ChannelFile, $Config, [Text.UTF8Encoding]::new($false))
        }
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build_windows.ps1')
        Assert-Exit 'Verified Windows build' $LASTEXITCODE
    }

    $Report = Get-Content -LiteralPath 'release/installed-self-test.json' -Raw | ConvertFrom-Json
    if ($Report.status -ne 'ok' -or $Report.version -ne $Version -or !$Report.frozen) {
        throw 'Windows installer self-test did not pass.'
    }
    $Evidence = Get-Content -LiteralPath 'release/release-evidence.json' -Raw | ConvertFrom-Json
    $Digest = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Digest -ne $Evidence.sha256.PSObject.Properties[$Installer].Value) {
        throw 'Installer does not match the build evidence.'
    }
    Write-Host "Verified installer: $Installer"
    if (!$PublishOnly -and $PublicKey) {
        @{origin=$Origin; public_key=$PublicKey; sha256=$Digest} | ConvertTo-Json -Compress |
            Set-Content -LiteralPath $ProofPath -Encoding UTF8
    }
    if (!$Publish -and !$PublishOnly) {
        if (!$PublicKey) { Write-Host 'Test build only. A publishable build requires the existing public key.' }
        return
    }

    $Proof = Get-Content -LiteralPath $ProofPath -Raw | ConvertFrom-Json
    if ($Proof.origin -ne $Origin -or $Proof.public_key -ne $PublicKey -or $Proof.sha256 -ne $Digest) {
        throw 'Rebuild with the existing public key before publishing.'
    }
    $SigningEnv = Join-Path ([IO.Path]::GetTempPath()) ('barq-sign-' + [guid]::NewGuid().ToString('N'))
    try {
        & py -3.11 -m venv $SigningEnv
        Assert-Exit 'Create isolated signing environment' $LASTEXITCODE
        $Python = Join-Path $SigningEnv 'Scripts\python.exe'
        & $Python -m pip install 'cryptography>=42,<51' 'httpx>=0.27,<1'
        Assert-Exit 'Install signing dependencies' $LASTEXITCODE
        & $Python -m scripts.publish_update sign --artifact release --tag $Tag
        Assert-Exit 'Sign update manifest' $LASTEXITCODE
    } finally { Remove-Item -LiteralPath $SigningEnv -Recurse -Force -ErrorAction SilentlyContinue }

    $ErrorActionPreference = 'Continue'
    try {
        $Draft = & gh release view $Tag --repo $Repo --json isDraft --jq '.isDraft' 2>$null
        $ViewResult = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    if ($ViewResult -eq 0) {
        if ("$Draft" -ne 'true') { throw "Release $Tag is already public; use a new version." }
        & gh release upload $Tag $Installer 'release/latest.json' --repo $Repo --clobber
    } else {
        & gh release create $Tag $Installer 'release/latest.json' --repo $Repo --draft --title "BARQ ONE $Version" --notes 'Windows x64.'
    }
    Assert-Exit 'Upload installer and manifest to draft' $LASTEXITCODE
    & gh release edit $Tag --repo $Repo --draft=false --latest
    Assert-Exit 'Publish update' $LASTEXITCODE

    $Expected = (Get-FileHash -LiteralPath 'release/latest.json' -Algorithm SHA256).Hash
    $Downloaded = [IO.Path]::GetTempFileName()
    try {
        for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
            & curl.exe --fail --silent --location --max-time 20 --header 'Cache-Control: no-cache' "$Origin/releases/latest/download/latest.json" --output $Downloaded
            if ($LASTEXITCODE -eq 0 -and (Get-FileHash -LiteralPath $Downloaded -Algorithm SHA256).Hash -eq $Expected) {
                Write-Host "Published and verified: $Origin/releases/tag/$Tag"
                return
            }
            if ($Attempt -lt 10) { Start-Sleep -Seconds 10 }
        }
        throw "Release $Tag was published, but the public manifest could not yet be verified."
    } finally { Remove-Item -LiteralPath $Downloaded -Force -ErrorAction SilentlyContinue }
} finally {
    if ($ChannelChanged) {
        if ($null -eq $PreviousChannel) { Remove-Item -LiteralPath $ChannelFile -Force -ErrorAction SilentlyContinue }
        else { [IO.File]::WriteAllBytes($ChannelFile, $PreviousChannel) }
    }
    $env:BARQ_UPDATE_ORIGIN = $PreviousOrigin
    Pop-Location
}
