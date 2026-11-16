# Optional per-user login shortcut; user runs this explicitly.
$target = Join-Path $PSScriptRoot 'START_BARQ_WAKE_AR.vbs'
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'BARQ Wake.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Save()
Write-Host "BARQ wake Startup shortcut installed: $link"
