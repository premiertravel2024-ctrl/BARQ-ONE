# BARQ ONE source uploader: requires Git for Windows and GitHub authentication.
# The script never force pushes and writes diagnostics into the user's TEMP folder.
param()
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = 'https://github.com/premiertravel2024-ctrl/BARQ-ONE.git'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $env:TEMP 'BARQ-ONE-UPLOAD-LOG.txt'
$uploaded = $false

try {
    Start-Transcript -Path $log -Force | Out-Null
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host 'BARQ ONE - GitHub upload / installer build' -ForegroundColor Cyan
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host "Source folder: $project"
    Write-Host "Diagnostic log: $log"
    Set-Location -LiteralPath $project

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is not installed or is missing from PATH. Install Git for Windows from https://git-scm.com/download/win, reopen this window and rerun this file.'
    }
    & git --version
    if ($LASTEXITCODE -ne 0) { throw 'Git could not start.' }

    foreach ($required in @('.github/workflows/windows-build.yml', 'frontend/package-lock.json', 'api_routes/listening_rooms.py', 'frontend/src/components/listening/ListeningRoom.tsx')) {
        if (-not (Test-Path -LiteralPath (Join-Path $project $required))) {
            throw "Missing project file: $required. Extract ALL ZIP files before running this script."
        }
    }

    # Keep personal secrets and local state excluded, and handle lengthy Windows paths.
    $env:GIT_TERMINAL_PROMPT = '1'
    $env:GCM_INTERACTIVE = 'auto'
    $env:GIT_ASKPASS = ''
    if (-not (Test-Path -LiteralPath '.git')) {
        Write-Host '[1/6] Initializing a new local Git repository...'
        & git init -b main
        if ($LASTEXITCODE -ne 0) { throw 'git init failed.' }
    }
    & git config core.longpaths true
    if ($LASTEXITCODE -ne 0) { throw 'Failed to set core.longpaths.' }

    Write-Host '[2/6] Setting the BARQ-ONE remote...'
    $remotes = @(& git remote)
    if ($LASTEXITCODE -ne 0) { throw 'Failed to list Git remotes.' }
    if ($remotes -contains 'origin') {
        $origin = (& git remote get-url origin | Out-String).Trim()
        if ($origin -ne $repo) {
            throw "Existing origin is '$origin', expected '$repo'. No remote was overwritten."
        }
    } else {
        & git remote add origin $repo
        if ($LASTEXITCODE -ne 0) { throw 'git remote add failed.' }
    }

    Write-Host '[3/6] Adding source files and creating a commit...'
    & git add -A
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        & git -c user.name='BARQ Source Upload' -c user.email='barq-source-upload@users.noreply.github.com' commit -m 'Upload BARQ ONE source with integrated listening room'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    } else {
        Write-Host 'Nothing new to commit.'
    }

    Write-Host '[4/6] Preparing the local main branch...'
    $branch = (& git branch --show-current | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read current Git branch.' }
    if ($branch -ne 'main') {
        & git branch -M main
        if ($LASTEXITCODE -ne 0) { throw 'Failed to set main branch.' }
    }

    Write-Host '[5/6] Pushing to your PRIVATE BARQ-ONE repository...'
    Write-Host 'If GitHub asks you to sign in, please approve it in your browser.' -ForegroundColor Yellow
    & git push --set-upstream origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'GitHub rejected the push. Check GitHub sign-in/permissions and look above for the Git error. GitHub account must be premiertravel2024-ctrl.'
    }

    Write-Host '[6/6] Checking the remote branch...'
    $localSha = (& git rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read local commit SHA.' }
    $remoteLine = (& git ls-remote origin refs/heads/main | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not verify the remote branch after pushing.' }
    $remoteSha = ($remoteLine -split '\s+')[0]
    if ($remoteSha -ne $localSha) { throw "GitHub SHA mismatch: local=$localSha remote=$remoteSha" }

    $uploaded = $true
    Write-Host "SUCCESS: GitHub main now points to $remoteSha" -ForegroundColor Green
    Write-Host 'Actions: https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions' -ForegroundColor Green
    Write-Host 'Wait for the Windows workflow to finish; download installer from the run Artifacts only after success.'
    Start-Process 'https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions' | Out-Null
}
catch {
    Write-Host ''
    Write-Host 'UPLOAD FAILED:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Log saved here: $log" -ForegroundColor Yellow
    Write-Host 'Send the log text or a screenshot of this window for a precise diagnosis.'
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
if (-not $uploaded) { exit 1 }
exit 0
