@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BARQ ONE - GitHub Upload and Windows EXE Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0UPLOAD_BARQ_ONE_FIXED.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
 echo Source uploaded and verified on GitHub. Check the Windows build in GitHub Actions.
) else (
 echo Upload failed. See error above and %TEMP%\BARQ-ONE-UPLOAD-LOG.txt
)
echo.
pause
exit /b %RESULT%
